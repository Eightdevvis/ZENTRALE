"""Schaufenster: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle). Die Welt
hat zwei Kategorien: Icons (post, karte; Themen pixel, post, karte) und Apps
(leer), test_fussleiste.antwort."""
import curses

from tui import zentrale_tui as zt


def regal(u):
    u.shop.oeffnen()


ZUSTAENDE = {
    "regal": regal,
    "regal:ohne_thema": lambda u: (regal(u), u.SHOP.update(themen=[])),
    "leer": lambda u: (regal(u), zt.taste_verteilen(u, curses.KEY_RIGHT)),     # Apps
    "leer:thema": lambda u: (regal(u), u.SHOP.update(stuecke=[], thema="pixel")),
    "fehler": lambda u: (regal(u), u.SHOP.update(kategorien=[], stuecke=[], themen=[],
                                                 msg="backend nicht erreichbar")),
}
