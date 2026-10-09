# core/profil/modelle/zusatzpruefer.py
#
# Zusatz-Prüfer für Modell-Profile (qwen): Fehlerbilder, die Python sehen
# kann und die Claude nicht hat — deshalb hier und nicht in
# core/ehrlichkeit.py, wo jeder Zug jedes Modells sie bezahlen würde.
#
# Warum Python statt Prompt (2026-10-09, qwen-Nacht): der Arbeitsweise-Block
# sagt qwen-plus ausdrücklich „nicht ‚soll ich?' fragen, das Werkzeug
# rufen" — und trotzdem endete in Runde 3 jede zweite Änderung mit „Ich
# ändere den Termin auf 16:30–17:15. Soll ich das jetzt durchführen?".
# Welcher Fall es traf, war Zufall: eine Bitte im Prompt ist eine Bitte.
#
# Drei Prüfungen, jede höchstens EINMAL je Zug, und nur, wenn der Prüfer der
# Schiene selbst nichts zu sagen hatte:
#
#   erlaubnis   Sasha wollte eine Änderung, die Antwort bittet um Erlaubnis
#               („soll ich …?", „sag Bescheid, dann mach ich's"), und in
#               diesem Zug wurde nichts geschrieben. (Runde 4)
#   als_text    Die Antwort IST ein Werkzeug-Aufruf als Text
#               („read_calendar(zeitraum=naechste_woche)") — qwen schreibt
#               den Aufruf manchmal hin, statt ihn zu machen. (Runde 7)
#   stichwort   „Gibt es nicht / nicht im Kalender", obwohl jede Kalender-
#               Suche dieses Zugs nur ein Stichwort probierte und leer kam
#               („die uni-sachen" → suche="uni" → nichts; die Termine heißen
#               „Analysis I"). (Runde 7)
#   tat         Sasha wollte eine Änderung, die Antwort meldet sie als
#               erledigt („ist gelöscht", „Alles korrigiert"), und in diesem
#               Zug lief kein schreibendes Werkzeug mit [ergebnis: ok].
#               Strenger als der Tat/Wort-Prüfer der Schiene, der auf wenige
#               Falschtreffer gebaut ist und „Der Friseurtermin … ist
#               gelöscht." ohne „jetzt" nicht als Behauptung zählt (Runde 7,
#               m03) — genau so endete das Gespräch 20261009-150713 („Alles
#               korrigiert"). Gilt nur, wenn Sasha in DIESER Nachricht etwas
#               ändern wollte. (Runde 8)
#   zeit        Nach einer Änderung nennt die Antwort eine Zeitspanne
#               („19:30 bis 20:30"), die in keinem Werkzeug-Ergebnis dieses
#               Zugs steht — das Werkzeug hatte 19:30–20:00 gespeichert
#               (Abschlusslauf m04: Absicht als Ergebnis gemeldet, wie am
#               08.10. „18:10–19:00"). (Runde 12)
#
# Eine echte Rückfrage (Tag fehlt, zwei Termine passen) bleibt erlaubt —
# die Hinweise sagen das ausdrücklich.

import re

# Sasha will, dass sich etwas ändert — oder stimmt einem Vorschlag zu.
_WILL = re.compile(
    r"\b(trag|eintrag\w*|lösch\w*|loesch\w*|verschieb\w*|änder\w*|aender\w*|"
    r"umleg\w*|fällt|faellt|ab jetzt|ist jetzt|sind jetzt|soll(en)?|mach\w*|"
    r"ok|okay|ja|jo|passt|genau|bitte|gerne?)\b")

# Die Antwort bittet um Erlaubnis, statt zu handeln.
_FRAGT_ERLAUBNIS = re.compile(
    r"(soll ich|möchtest du,? dass ich|willst du,? dass ich|darf ich|sollen wir|"
    r"jetzt durchführen|soll das so)[^?]{0,240}\?|"
    r"sag (kurz |einfach |mir )?bescheid[^.?!]{0,40}(dann|und) (mach|trag|änder|pass|leg)")

# Ein Werkzeug-Aufruf als Text: name(…) und sonst (fast) nichts.
_AUFRUF_TEXT = re.compile(r"^\W*`?([a-z_]{4,})\s*\((.{0,400})\)`?\W*$", re.S)

# „gibt es nicht" über den Kalender.
_NICHT_IM_KALENDER = re.compile(
    r"\b(kein\w*|nicht)\b[^.?!\n]{0,60}\b(im kalender|gefunden|drin|eingetragen|da)\b|"
    r"\bnichts gefunden\b")

# „ist gelöscht", „Alles korrigiert", „eingetragen." — ein Erledigt-Wort.
_ERLEDIGT = re.compile(
    r"\b(eingetragen|gelöscht|entfernt|verschoben|angelegt|geändert|aktualisiert|"
    r"angepasst|korrigiert|gestrichen|pausiert|erledigt|umgestellt|verlegt|"
    r"rausgenommen|raus|weg)\b")
_NICHT_ODER_WENN = re.compile(
    r"\b(nicht|nichts|kein\w*|noch nicht|wenn|falls|sobald|soll|sollen|würde|"
    r"könnte|kann|möchtest|willst)\b")

ERLAUBNIS = (
    "[Prüfung] Du bittest {nutzer} um Erlaubnis für etwas, das {er} schon verlangt "
    "hat, und hast in diesem Zug nichts geändert. Die Ja/Nein-Frage vor jeder "
    "Änderung stellt ZENTRALE selbst, sobald du das Werkzeug rufst. Führ es "
    "jetzt aus (vorher read_calendar, wenn dir die Kennung fehlt). Fehlt "
    "wirklich eine Angabe (Tag, Uhrzeit, Ende einer Serie, welcher von zwei "
    "Terminen), frag genau danach — ohne „soll ich“.")
ALS_TEXT = (
    "[Prüfung] Deine Antwort ist ein Werkzeug-Aufruf als Text — {nutzer} sieht "
    "nur diese Zeile, ausgeführt wurde nichts. Ruf das Werkzeug wirklich auf "
    "und antworte dann.")
STICHWORT = (
    "[Prüfung] Du sagst, es gibt nichts — aber jede Kalender-Suche in diesem "
    "Zug probierte nur ein Stichwort ('suche'), und Titel heißen oft anders "
    "(„die uni-sachen“ sind „Analysis I“, „Tutorium …“). Lies den Zeitraum "
    "OHNE 'suche' (z. B. naechste_30_tage) und sieh selbst nach, bevor du "
    "es behauptest.")


TAT = (
    "[Prüfung] Deine Antwort meldet eine Änderung als erledigt — aber in "
    "diesem Zug lief kein schreibendes Werkzeug mit [ergebnis: ok]. Ruf das "
    "Werkzeug jetzt auf (die Ja/Nein-Frage stellt ZENTRALE selbst), oder "
    "sag ehrlich, dass noch nichts geändert ist.")


def meldet_erledigt(antwort: str) -> bool:
    """Ein Satz ohne Frage, Verneinung oder Bedingung mit einem Erledigt-Wort."""
    for satz in re.split(r"(?<=[.!?\n])\s+", (antwort or "").casefold()):
        if "?" in satz or _NICHT_ODER_WENN.search(satz):
            continue
        if _ERLEDIGT.search(satz):
            return True
    return False


ZEIT = (
    "[Prüfung] Deine Antwort nennt {spannen}, aber kein Werkzeug-Ergebnis "
    "dieses Zugs zeigt das — dort steht, was wirklich gespeichert ist. "
    "Stimmt der Eintrag nicht, korrigiere ihn mit dem Werkzeug; sonst nenn "
    "die Zeit aus dem Ergebnis.")

_SPANNE = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*(?:uhr\s*)?(?:–|-|—|bis)\s*"
                     r"(\d{1,2})[:.](\d{2})\b")


def spannen(text: str) -> set:
    return {f"{int(a)}:{b}–{int(c)}:{d}"
            for a, b, c, d in _SPANNE.findall((text or "").casefold())}


def unbelegte_spannen(antwort: str, protokoll: list) -> list:
    belegt = set()
    for s_ in protokoll:
        belegt |= spannen(str(getattr(s_, "text", "")))
    return sorted(spannen(antwort) - belegt)


def fragt_statt_tut(nutzer: str, antwort: str) -> bool:
    return bool(_WILL.search((nutzer or "").casefold())
                and _FRAGT_ERLAUBNIS.search((antwort or "").casefold()))


def aufruf_als_text(antwort: str, werkzeuge: set) -> bool:
    m = _AUFRUF_TEXT.match((antwort or "").strip())
    return bool(m and m.group(1) in werkzeuge)


def nur_stichwort_leer(antwort: str, protokoll: list) -> bool:
    lesen = [s for s in protokoll if getattr(s, "name", "") == "read_calendar"]
    if not lesen or not _NICHT_IM_KALENDER.search((antwort or "").casefold()):
        return False
    return all((getattr(s, "args", None) or {}).get("suche")
               and "keine einträge" in str(getattr(s, "text", "")).casefold()
               for s in lesen)


class ZusatzPruefer:
    """Legt sich um den Prüfer der Schiene (ehrlichkeit.Pruefer): alles
    andere reicht er durch."""

    def __init__(self, basis, nutzer_text: str, werkzeuge: set = frozenset()):
        self._basis = basis
        self._nutzer = nutzer_text or ""
        self._werkzeuge = set(werkzeuge)
        self._schon = set()

    def __getattr__(self, name):
        return getattr(self._basis, name)

    def _befund(self, text: str) -> str | None:
        protokoll = list(getattr(self._basis, "protokoll", []))
        geschrieben = any(getattr(s, "schreibt", False) and getattr(s, "status", "") == "ok"
                          for s in protokoll)
        if aufruf_als_text(text, self._werkzeuge):
            return "als_text"
        if (not geschrieben and _WILL.search(self._nutzer.casefold())
                and meldet_erledigt(text)):
            return "tat"
        if not geschrieben and fragt_statt_tut(self._nutzer, text):
            return "erlaubnis"
        if nur_stichwort_leer(text, protokoll):
            return "stichwort"
        if geschrieben and unbelegte_spannen(text, protokoll):
            return "zeit"
        return None

    def nach_antwort(self, text: str, *, letzte_runde: bool):
        k = self._basis.nach_antwort(text, letzte_runde=letzte_runde)
        if k or letzte_runde:
            return k
        if getattr(self._basis, "modus", "an") != "an":
            return None
        art = self._befund(text)
        if art is None or art in self._schon:
            return None
        if art == "zeit":
            protokoll = list(getattr(self._basis, "protokoll", []))
            zeit = ZEIT.replace("{spannen}", ", ".join(unbelegte_spannen(text, protokoll)))
        self._schon.add(art)
        # Zählt als Korrekturrunde der Schiene (Anzeige „Prüfung 1/5").
        try:
            self._basis.korrekturen += 1
        except Exception:
            pass
        import nutzer_angaben
        return nutzer_angaben.einsetzen(
            {"erlaubnis": ERLAUBNIS, "als_text": ALS_TEXT, "stichwort": STICHWORT,
             "tat": TAT, "zeit": zeit if art == "zeit" else ""}[art])


# Für tool_choice (qwen, Runde 5): Sasha will am Kalender etwas ändern —
# enger als _WILL, denn hier wird ein Werkzeug ERZWUNGEN.
_KALENDER_WILL = re.compile(
    r"\b(trag\w*|eintrag\w*|lösch\w*|loesch\w*|verschieb\w*|änder\w*|aender\w*|"
    r"fällt|faellt|ab jetzt|ab sofort|ist jetzt|sind jetzt|termin\w*|routine\w*|"
    r"kalender|pause)\b|\bum \d|\bhalb (eins|zwei|drei|vier|fünf|sechs|sieben|acht|"
    r"neun|zehn|elf|zwölf)\b|\d{1,2}[:.]\d{2}")
_JA = re.compile(r"^\W*(ok(ay)?|ja|jo|jup|klar|passt|genau|mach( das| es)?|gerne?|bitte|"
                 r"los|sure|yes)\b")


# „noch nix eintragen", „nicht löschen", „nur nachschauen": kein Änderungswunsch
# (Runde 9, f08 — die erzwungene Kalender-Suche lenkte qwen vom LSF ab).
_VERNEINT = re.compile(
    r"\b(nicht|nix|nichts|kein\w*)\s+(\w+\s+){0,2}(ein)?(trag|lösch|loesch|änder|aender|"
    r"verschieb)\w*|\bnur\s+(nach)?(schau|guck|seh|such)\w*")


def will_aendern(verlauf: list) -> bool:
    """Will Sasha in seiner neuesten Nachricht den Kalender ändern — oder
    stimmt er einer Frage aus der letzten Antwort zu?"""
    nutzer = letzte_nachricht(verlauf).casefold()
    if _VERNEINT.search(nutzer):
        return False
    if _KALENDER_WILL.search(nutzer):
        return True
    if _JA.search(nutzer):
        vorher = next((str(m.get("content") or "") for m in reversed(verlauf or [])
                       if m.get("role") == "assistant"), "")
        return "?" in vorher
    return False


def letzte_nachricht(verlauf: list) -> str:
    for m in reversed(verlauf or []):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""
