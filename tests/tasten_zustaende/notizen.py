"""Notizen: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle)."""
import curses

from tui import zentrale_tui as zt


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def notiz(u):
    u.notizen.oeffnen()


def liste(u):
    notiz(u); _t(u, "n")


ZUSTAENDE = {
    "notiz": notiz,
    "notiz:frage": lambda u: (notiz(u), _t(u, "d")),            # Block „hallo" ist befüllt
    "liste": liste,
    "liste:frage": lambda u: (liste(u), _t(u, "d")),
    "titel": lambda u: (notiz(u), _t(u, "r")),
    "block:text": lambda u: (notiz(u), _t(u, 10)),
    # Listen-Block, Cursor auf dem Eintrag „a" (nicht auf der leeren neu-Zeile)
    "block:liste": lambda u: (notiz(u), _t(u, curses.KEY_DOWN, 10, curses.KEY_UP)),
    # neuer Float-Block mit einem Begriff, Cursor darauf
    "block:float": lambda u: (notiz(u), _t(u, "f", "x", 10, curses.KEY_LEFT)),
}
