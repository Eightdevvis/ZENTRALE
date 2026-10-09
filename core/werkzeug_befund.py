# core/werkzeug_befund.py
#
# Was ein Werkzeug der KI zurückgibt, wenn es mehr sagen soll als einen Text:
# WIE es ausgegangen ist (Status) und was danach WIRKLICH dasteht (Beleg).
#
# 2026-10-08, nach Sashas Kalender-Testlauf (Gespräch 20261008-132404):
# „Jetzt sauber: donnerstags 18:10–19:00" — tatsächlich stand 18:10 ohne Ende
# da, das Werkzeug hatte nur „OK, Routine eingetragen" gesagt. Die KI hat ihre
# ABSICHT als Ergebnis berichtet, und nichts im Ergebnis hat ihr widersprochen.
# Ehrlichkeit war eine Bitte im Prompt, keine Bauweise. Jetzt:
#
#   - jedes Werkzeug-Ergebnis an die KI beginnt mit einer Kopfzeile
#     „[ergebnis: ok|fehlgeschlagen|keine_antwort|abgelehnt]"
#     (gesetzt in werkzeug_schleife.run_tool) — maschinenlesbar, nicht aus
#     der Wortwahl zu erraten;
#   - schreibende Werkzeuge lesen nach dem Schreiben nach und geben den
#     echten Stand als Beleg mit (Feld `beweis` im Werkzeug-Register).
#
# Dazu die Schiene des laufenden Zugs (klein/gross): einige Ausführer zeigen
# auf der gross-Schiene mehr (Kennungen im Kalender), ohne dass das gemessene
# qwen auf klein etwas anderes zu lesen bekommt.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): weiß nichts vom Fach.

import contextvars

# „teilweise" gibt es seit 2026-10-09 nicht mehr (Sasha: „das programm macht
# etwas richtig ODER bricht KONTROLLIERT KOMPLETT AB mit genauem
# fehlercode"). Ein schreibendes Werkzeug ist ERLEDIGT (ok) oder ABGEBROCHEN
# (fehlgeschlagen, nichts geändert, mit Code aus core/fehlercodes.py).
# „teilweise" hieß: das Werkzeug hat etwas anderes getan als verlangt — ein
# Fehler des Werkzeugs, den die KI ausbaden sollte.
OK = "ok"
FEHLGESCHLAGEN = "fehlgeschlagen"
KEINE_ANTWORT = "keine_antwort"
ABGELEHNT = "abgelehnt"
STATUS = (OK, FEHLGESCHLAGEN, KEINE_ANTWORT, ABGELEHNT)


class Befund(str):
    """Ein Werkzeug-Ergebnis MIT Status und Beleg.

    Ein str, damit alles, was bisher Texte weiterreicht (Log, Verlauf, Tests,
    die Ergebnisse vergleichen), unverändert weiterläuft. Der Text ist der
    ganze Satz an die KI; `beleg` ist der nachgelesene Stand allein (für
    Tests und die Prüfung „jedes schreibende Werkzeug belegt"). `code` ist
    der Fehlercode eines Abbruchs (core/fehlercodes.py). `vollstaendig` (seit
    2026-10-09, Suchen im Nutzerordner): True/False, ob eine Suche alles
    abgelaufen hat; None bei allem, was keine Suche ist."""

    def __new__(cls, text: str, status: str = OK, beleg: str = "", code: str = "",
                vollstaendig: bool | None = None):
        if status not in STATUS:
            raise ValueError(f"unbekannter Status: {status!r}")
        obj = super().__new__(cls, text)
        obj.status = status
        obj.beleg = beleg or ""
        obj.code = code or ""
        obj.vollstaendig = vollstaendig
        return obj


def erledigt(satz: str, beleg: str = "", zusatz: str = "") -> Befund:
    """ERLEDIGT: `satz` sagt in fester Form, was jetzt dasteht — aus dem
    nachgelesenen Stand, nicht aus den Argumenten. `zusatz`: Hinweise
    dahinter (Warnungen), die nicht zum Beleg gehören."""
    text = satz + (" " + zusatz if zusatz else "")
    return Befund(text.strip(), OK, beleg=beleg or satz)


def abgebrochen(was: str, code: str, grund: str, nichts: str = "nichts geändert") -> Befund:
    """ABGEBROCHEN, kontrolliert: nichts ist geändert (oder der alte Stand
    ist wiederhergestellt), und der Code sagt, warum. Feste Form:
    „<was> ABGEBROCHEN – <nichts>. Fehler <CODE>: <grund>"."""
    grund = str(grund or "").strip().strip("[]").strip()
    text = f"{was} ABGEBROCHEN – {nichts}. Fehler {code}: {grund}".rstrip()
    if not text.endswith((".", "!", "?", ")")):
        text += "."
    return Befund(text, FEHLGESCHLAGEN, code=code)


def status_von(ergebnis) -> str:
    """Der Status eines Ergebnisses. Ein Befund sagt ihn selbst; ein alter
    Text-Ausführer wird an seiner Form erkannt: Fehler kommen dort seit jeher
    als „[Fehler …]"/„[Nicht …]" in eckigen Klammern."""
    if isinstance(ergebnis, Befund):
        return ergebnis.status
    text = str(ergebnis or "").lstrip()
    if not text:
        return FEHLGESCHLAGEN
    if text.startswith(("[Fehler", "[Nicht ", "[Unbekanntes Tool",
                        "[Download fehlgeschlagen", "[Anlegen fehlgeschlagen")):
        return FEHLGESCHLAGEN
    return OK


def kopfzeile(status: str) -> str:
    return f"[ergebnis: {status}]"


def mit_kopf(ergebnis) -> str:
    """Der Text, der als Werkzeug-Ergebnis ans Modell geht: Kopfzeile, dann
    der Text. Nie „None" (2026-10-08: ask_choice) — ein leeres Ergebnis heißt
    das auch."""
    if ergebnis is None or not str(ergebnis).strip():
        return (kopfzeile(FEHLGESCHLAGEN) + "\n(Das Werkzeug hat nichts "
                "zurückgegeben — es ist NICHT belegt, dass etwas passiert ist.)")
    return kopfzeile(status_von(ergebnis)) + "\n" + str(ergebnis)


# ── Die Schiene des laufenden Werkzeug-Aufrufs ─────────────────────────
# Gesetzt von werkzeug_schleife.run_tool genau um den Aufruf des Ausführers
# herum (kein yield dazwischen, also kein Durchsickern in andere Züge).
# Ohne Angabe gilt klein: das ist das bisherige Verhalten.
_schiene = contextvars.ContextVar("zentrale_schiene", default="klein")


def schiene() -> str:
    return _schiene.get()


def schiene_setzen(name: str):
    """-> Marke für schiene_zuruecksetzen."""
    return _schiene.set(name or "klein")


def schiene_zuruecksetzen(marke) -> None:
    try:
        _schiene.reset(marke)
    except (ValueError, RuntimeError):
        _schiene.set("klein")


# ── Die Werkzeug-Spur im Verlauf ───────────────────────────────────────
# 2026-10-09, Prüfstand f01: Der Verlauf der KI enthielt nur ihre Antworten,
# nicht ihre Werkzeuge. Sagte die Antwort nichts vom Löschen, wusste die KI
# im nächsten Zug nicht mehr, dass sie gelöscht hatte — und erzählte Sasha,
# da sei nie etwas gewesen. Jetzt hängt an jeder gespeicherten Antwort eine
# Zeile mit dem, was geschrieben wurde oder schiefging (mit Status und dem
# Anfang des Ergebnisses). Lesende Aufrufe bleiben draußen: ihr Inhalt ist
# lang und lässt sich neu lesen. Gebaut nur aus Gespeichertem → dieselben
# Bytes in jedem Zug, der Prompt-Cache bleibt.

SPUR_KOPF = ("[Werkzeug-Spur dieses Zugs — vom System nachgetragen, nicht Teil "
             "deiner Antwort; Sasha sieht sie nicht:")


SPUR_ERGEBNIS_MAX = 300


def spur_zeile(werkzeuge) -> str:
    """Die Spur aus den gemerkten Werkzeugen einer Antwort ({name, args,
    ergebnis?, status?, schreibt?, fehler?}); "" wenn nichts zu sagen ist."""
    zeilen = []
    for w in werkzeuge or []:
        status = w.get("status") or (FEHLGESCHLAGEN if w.get("fehler") else "")
        if not (w.get("schreibt") or w.get("name") == "ask_choice"
                or status not in ("", OK)):
            continue
        ergebnis = " ".join(str(w.get("ergebnis") or "").split()) or "(kein Ergebnis gemerkt)"
        # Der Verlauf hält seit 2026-10-09 das ganze Ergebnis (Sasha will es
        # lesen können); der KI reicht der Anfang — sonst wird jeder Zug teurer.
        if len(ergebnis) > SPUR_ERGEBNIS_MAX:
            ergebnis = ergebnis[:SPUR_ERGEBNIS_MAX - 1] + "…"
        zeilen.append(f"- {w.get('name')}({w.get('args') or ''}) → "
                      f"{status or '?'}: {ergebnis}")
    if not zeilen:
        return ""
    return SPUR_KOPF + "\n" + "\n".join(zeilen) + "]"
