# core/kalender_fehler.py
#
# Ablehnungen des Kalenders: feste Codes, eine Fehlerklasse, die Uhrzeit-
# und Reihenfolge-Prüfung. Das unterste Kalender-Modul (braucht nichts aus
# dem Kalender) — damit kalender.py, kalender_kennung.py und
# kalender_bearbeiten.py dieselbe Ablehnung werfen, ohne sich gegenseitig zu
# importieren (Import-Kreise sind im Kern-Bauplan verboten).
#
# Seit 09.10.2026: keine stillen Korrekturen mehr — was nicht passt, wird
# mit Code + lesbarem Grund abgelehnt, und dann ist nichts geschrieben.

# Die EINE Liste der Ablehnungsgründe. Die KI-Werkzeuge reichen sie mit dem
# Präfix „K-" durch und können sie nachschlagen — nicht umbenennen.
CODES = {
    "KENNUNG-UNBEKANNT": "Zu dieser Kennung gibt es keinen Eintrag.",
    "FALSCHE-ART": "Die Kennung gehört zu einer anderen Art (Termin/Spanne/Routine).",
    "ZEIT-UNGUELTIG": "Eine Uhrzeit ist nicht im Format HH:MM.",
    "DATUM-UNGUELTIG": "Ein Datum ist nicht im Format JJJJ-MM-TT.",
    "ENDE-VOR-BEGINN": "Das Ende liegt nicht nach dem Beginn.",
    "ENDE-OHNE-BEGINN": "Ein Ende ohne Beginn-Uhrzeit.",
    "RRULE-UNGUELTIG": "Die Wiederholungsregel ist ungültig.",
    "KEIN-VORKOMMEN": "Die Routine findet an diesem Tag nicht statt.",
    "TITEL-LEER": "Der Titel ist leer.",
    "SPANNE-VERDREHT": "Der letzte Tag liegt vor dem ersten.",
    "TAG-AUSSERHALB": "Der Tag gehört nicht zu dieser Spanne.",
    "UNBEKANNTES-FELD": "Ein Feld, das es hier nicht gibt.",
}


class KalenderAbgelehnt(ValueError):
    """Abgelehnt, nichts geschrieben. `code` aus CODES, `grund` lesbar."""

    def __init__(self, code: str, grund: str | None = None):
        assert code in CODES, code
        self.code = code
        self.grund = grund or CODES[code]
        super().__init__(f"{code}: {self.grund}")


def uhrzeit(feld, wert) -> str:
    """'9:5' → '09:05'; alles andere → ZEIT-UNGUELTIG."""
    if not isinstance(wert, str) or ":" not in wert:
        raise KalenderAbgelehnt("ZEIT-UNGUELTIG", f"{feld} {wert!r} ist keine Uhrzeit (HH:MM)")
    h, _, m = wert.strip().partition(":")
    try:
        h, m = int(h), int(m)
    except ValueError:
        raise KalenderAbgelehnt("ZEIT-UNGUELTIG", f"{feld} {wert!r} ist keine Uhrzeit (HH:MM)")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise KalenderAbgelehnt("ZEIT-UNGUELTIG", f"{feld} {wert!r} gibt es nicht")
    return "%02d:%02d" % (h, m)


def reihenfolge(beginn, ende) -> None:
    """Ende ohne Beginn oder Ende ≤ Beginn ablehnen."""
    if ende and not beginn:
        raise KalenderAbgelehnt("ENDE-OHNE-BEGINN", f"Ende {ende} ohne Beginn-Uhrzeit")
    if beginn and ende and ende <= beginn:
        raise KalenderAbgelehnt("ENDE-VOR-BEGINN",
                                f"Ende {ende} liegt nicht nach Beginn {beginn}")
