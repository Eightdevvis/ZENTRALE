"""Klavier: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle)."""
from tui import zentrale_tui as zt


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def spielen(u):                       # Melodien „lied" und „tanz" geladen
    u.klavier.oeffnen()


def leer(u):
    spielen(u); u.PIANO["mel"] = []


ZUSTAENDE = {
    "spielen": spielen,
    "spielen:leer": leer,
    # aufnehmen, eine Note, stoppen → Name tippen (ein Zeichen, damit ⌫ wirkt)
    "name": lambda u: (spielen(u), _t(u, " ", "y", " ", "a")),
    "umbenennen": lambda u: (spielen(u), _t(u, "r")),
    "frage": lambda u: (spielen(u), _t(u, "D")),
}
