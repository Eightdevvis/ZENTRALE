"""Karte: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle)."""
import test_fussleiste as F


def karte(u):
    u.karte.oeffnen()
    F.zeichnen(u)                      # Basiskarte holen (bounds fürs Schwenken)


def zeit(damals=None):
    """Overlay an, das eine Zeitachse liefert (das gefälschte Backend kennt
    keine — die Antwort wird hier hingelegt, fürs Raster der Karte)."""
    def aufbau(u):
        karte(u)
        M = u.M
        M.update(overlay=True, overlay_at=damals, ogrid=M["grid"],
                 odata={"lines": [], "points": [], "vintage": "2026",
                        "time": {"min": "2026-01-01", "max": "2026-10-01"}})
    return aufbau


ZUSTAENDE = {
    "karte": karte,
    "karte:zeit": zeit(),
    "karte:zeit:damals": zeit("2026-06-01"),
}
