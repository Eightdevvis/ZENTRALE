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
#     „[ergebnis: ok|teilweise|fehlgeschlagen|keine_antwort|abgelehnt]"
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

OK = "ok"
TEILWEISE = "teilweise"
FEHLGESCHLAGEN = "fehlgeschlagen"
KEINE_ANTWORT = "keine_antwort"
ABGELEHNT = "abgelehnt"
STATUS = (OK, TEILWEISE, FEHLGESCHLAGEN, KEINE_ANTWORT, ABGELEHNT)


class Befund(str):
    """Ein Werkzeug-Ergebnis MIT Status und Beleg.

    Ein str, damit alles, was bisher Texte weiterreicht (Log, Verlauf, Tests,
    die Ergebnisse vergleichen), unverändert weiterläuft. Der Text ist der
    ganze Satz an die KI; `beleg` ist der nachgelesene Stand allein (für
    Tests und die Prüfung „jedes schreibende Werkzeug belegt")."""

    def __new__(cls, text: str, status: str = OK, beleg: str = ""):
        if status not in STATUS:
            raise ValueError(f"unbekannter Status: {status!r}")
        obj = super().__new__(cls, text)
        obj.status = status
        obj.beleg = beleg or ""
        return obj


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
