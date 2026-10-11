"""Werkstatt: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle)."""
import curses

from tui import zentrale_tui as zt


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def start(u):
    u.werkstatt.oeffnen()


ZUSTAENDE = {
    "start": start,
    # neue app bauen → Name „x" → Symbol: Bild, zufällig (zwei Punkte)
    "wahl": lambda u: (start(u), _t(u, 10, "x", 10)),
    "wahl:eins": lambda u: (start(u), _t(u, curses.KEY_DOWN, 10)),   # vorlagen: nur Desk View
    # neue app bauen → Name „ab", Cursor zwischen a und b (⌫ und del haben
    # beide etwas zu löschen, ← und → beide Platz)
    "tippen": lambda u: (start(u), _t(u, 10, "a", "b", curses.KEY_LEFT)),
}
