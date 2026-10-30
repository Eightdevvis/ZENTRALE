"""Schematix in the TUI (tui/ansichten/schematix.py, schematix_bild.py,
schematix_arten.py; memory/hub/schematix.md) without a terminal: the real
TUI bundle of tests/test_fussleiste.py with the fake map of
tests/_schematix_fake.py, drawn into a recording screen.

With SCHEMATIX_CAPTURE=<folder> the screens are also written there as text
(render checks for Sasha; nothing is written otherwise)."""
import curses
import os

import pytest

import test_fussleiste as F
from test_fussleiste import welt  # noqa: F401  – fixture: the TUI without a screen
from tui import zentrale_tui as zt

H, W = 46, 150


class Aufnahme(F.Schirm):
    """A screen that keeps what was drawn (characters only)."""

    def __init__(self):
        super().__init__()
        self.zeilen = [[" "] * W for _ in range(H)]

    def getmaxyx(self):
        return (H, W)

    def erase(self):
        self.zeilen = [[" "] * W for _ in range(H)]

    def addstr(self, y, x, text, attr=0):
        for i, ch in enumerate(str(text)):
            if 0 <= y < H and 0 <= x + i < W:
                self.zeilen[y][x + i] = ch

    addnstr = addstr

    def text(self):
        return "\n".join("".join(z).rstrip() for z in self.zeilen)


def _schirm(u):
    s = Aufnahme()
    u.z.stdscr = u.stdscr = s
    return s


def _bild(u, s, name=None):
    try:
        zt.bild_zeichnen(u)
    except curses.error:
        pass
    text = s.text()
    ziel = os.environ.get("SCHEMATIX_CAPTURE")
    if ziel and name:
        os.makedirs(ziel, exist_ok=True)
        with open(os.path.join(ziel, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return text


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


@pytest.fixture
def offen(welt):  # noqa: F811
    u = welt()
    s = _schirm(u)
    u.schematix.starten = lambda f: f()
    u.schematix.oeffnen()
    return u, s


def test_board_shows_cross_section_chips_and_pcb_wires(offen):
    u, s = offen
    text = _bild(u, s, "13_board")
    assert "▐1▌SYNC" in text and "▐5▌PWR" in text            # layer chips
    assert "CROSS-SECTION" in text and "LIVE" in text          # side column, gauge
    assert "☁ CLOUD" in text and "▣ MINIPC" in text           # cloud on top, nodes below
    assert "┎─" in text and "╭─" in text and "┌╌" in text     # node, app, planned frames
    assert "●" in text and "┄" in text                         # solder dots, an unplugged wire
    assert "not yet" in text


def test_a_layer_key_hides_its_wires(offen):
    u, s = offen
    assert u.SCHEMATIX["canvas"].verbindungen
    _t(u, "1")
    assert u.SCHEMATIX["layers"]["data"] is False and not u.SCHEMATIX["canvas"].verbindungen
    assert "·1·sync" in _bild(u, s)
    _t(u, "3")                                                 # hardware: things go too
    assert "device:router" not in {e["id"] for e in u.SCHEMATIX["canvas"].elemente}


def test_versions_panel_folds_open_on_a_node(offen):
    u, s = offen
    u.SCHEMATIX["canvas"].fokus = "node:minipc"
    h = u.SCHEMATIX["canvas"].element("node:minipc")["h"]
    _t(u, "i")
    el = u.SCHEMATIX["canvas"].element("node:minipc")
    assert el["offen"] and el["h"] > h and u.SCHEMATIX["canvas"].fokus == "node:minipc"
    text = _bild(u, s, "13_versions")
    assert "contracts: ports 1" in text and "auto-update: on" in text


def test_colours_are_knobs_with_measured_contrast(offen):
    u, s = offen
    _t(u, "c")
    text = _bild(u, s, "13_colours")
    assert "COLOUR ROLES" in text.upper() and "7.0:1" in text
    _t(u, curses.KEY_DOWN, 10)                                 # ink → the colour wheel
    assert u.SCHEMATIX["farbe"] is not None
    _t(u, 27)
    assert u.SCHEMATIX["farbe"] is None and u.SCHEMATIX["ebene"] == "colours"


def test_esc_closes(offen):
    u, _s = offen
    _t(u, 27)
    assert u.SCHEMATIX["active"] is False
