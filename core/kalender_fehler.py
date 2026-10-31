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
    "EBENE-UNBEKANNT": "Diese Ebene gibt es nicht.",
    # Tagesrhythmus (Phasen) und Gruppen, seit 10.10.2026
    "MOTIV-UNBEKANNT": "Dieses Motiv gibt es nicht (Liste: /api/calendar/motive).",
    "KEINE-PHASE": "Das geht nur bei einer Phase des Tagesrhythmus.",
    "IST-PHASE": "Eine Phase des Tagesrhythmus ist kein Termin — das geht mit ihr nicht.",
    "PHASE-OHNE-ZEIT": "Eine Phase braucht eine Beginn-Uhrzeit.",
    "ZEITRAUM-ZU-LANG": "Der Zeitraum ist zu lang.",
    "KATEGORIE-UNBEKANNT": "Diese Gruppe gibt es nicht (Liste: /api/calendar/kategorien; eigene: custom + kategorie_name).",
    "KATEGORIE-NAME-FEHLT": "Bei custom fehlt der eigene Name (kategorie_name).",
    "KEIN-TREFFER": "Kein Eintrag passt.",
    # Titel aus Liste/Projekt (kalender_quelle), seit 10.10.2026
    "QUELLE-ART-UNBEKANNT": "Diese Art von Quelle gibt es nicht (liste, projekt).",
    "QUELLE-UNGUELTIG": "Die Quelle ist kein {art, id} mit gültiger id.",
    "QUELLE-UNBEKANNT": "Diese Liste bzw. dieses Projekt gibt es nicht (Auswahl: /api/calendar/quellen).",
    "OHNE-QUELLE": "Der Eintrag hat keine Quelle.",
    # Aussehen des Kastens (core/stil.py, Stylebox der TUI), seit 10.10.2026
    "STIL-UNGUELTIG": "Der Stil ist kein gültiges dict aus CSS-Eigenschaften (Farben als #rrggbb).",
    # Termintyp deadline (core/kalender_deadline.py), seit 20.10.2026
    "TYP-UNBEKANNT": "Diesen Termintyp gibt es nicht (normal, deadline).",
    "VORWARNUNG-UNGUELTIG": "Die Vorwarnung ist keine Dauer (Minuten oder z. B. 3d, 12h, 1d12h; höchstens 366 Tage).",
    "DEADLINE-OHNE-ZEIT": "Eine Deadline braucht eine Uhrzeit (sie ist ein Zeitpunkt).",
    "DEADLINE-MIT-ENDE": "Eine Deadline hat kein Ende (sie ist ein Zeitpunkt) — ende entfernen.",
    "DEADLINE-SPANNE": "Ein mehrtägiger Termin kann keine Deadline sein.",
    # Soll-Zeit einer Deadline (soll_abstand), seit 24.10.2026
    "SOLL-UNGUELTIG": "Der Soll-Abstand ist keine Dauer (Minuten ≤ 0 oder z. B. -3d18h; höchstens 28 Tage vor der Muss-Zeit).",
    "SOLL-NACH-MUSS": "Die Soll-Zeit liegt nach der Muss-Zeit — sie darf nur davor oder gleich liegen.",
    # One edit = one write (kalender_bearbeiten.edit, 2026-10-31)
    "AENDERUNG-ABGELEHNT": "The change does not fit the entry (time, date or rule invalid); nothing was written.",
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


def reihenfolge(beginn, ende, ueber_mitternacht: bool = False) -> None:
    """Ende ohne Beginn oder Ende ≤ Beginn ablehnen. `ueber_mitternacht`
    (nur Phasen des Tagesrhythmus, z. B. Schlaf 23:00–07:00): ein Ende vor
    dem Beginn heißt „endet am Folgetag"; nur Ende == Beginn ist falsch."""
    if ende and not beginn:
        raise KalenderAbgelehnt("ENDE-OHNE-BEGINN", f"Ende {ende} ohne Beginn-Uhrzeit")
    if ueber_mitternacht:
        if beginn and ende and ende == beginn:
            raise KalenderAbgelehnt("ENDE-VOR-BEGINN",
                                    f"Ende {ende} ist gleich dem Beginn {beginn}")
        return
    if beginn and ende and ende <= beginn:
        raise KalenderAbgelehnt("ENDE-VOR-BEGINN",
                                f"Ende {ende} liegt nicht nach Beginn {beginn}")
