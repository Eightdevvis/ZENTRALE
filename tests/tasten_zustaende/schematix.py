"""Schematix: a way to every view of its key table (tests/test_tastentabellen.py
presses every key there). The map is tests/_schematix_fake.py: the node
`minipc` in the middle has a piece in every direction."""
import test_fussleiste as F
from tui import zentrale_tui as zt

TAB = 9


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def _board(u):
    u.schematix.oeffnen()
    F.zeichnen(u)


def _node(u):
    _board(u)
    u.SCHEMATIX["canvas"].fokus = "node:minipc"


def _colours(u):
    _board(u); _t(u, "c")


def _farbe(u, *mehr):
    _colours(u)
    u.SCHEMATIX["colour_sel"] = 6                  # "focus": a saturated colour
    _t(u, 10, "+", *mehr)                          # wheel open, zoomed in once


ZUSTAENDE = {
    "board": _board,
    "node": _node,
    "colours": _colours,
    "farbe:kreis": _farbe,
    "farbe:regler": lambda u: _farbe(u, TAB),
    "farbe:hex": lambda u: _farbe(u, "#", "f", "f", "f"),      # 3 digits: enter takes it
}
