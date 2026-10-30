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


# ── Step 14: scheming — move, add, remove, make real ────────────────────

def _puts(u, prefix):
    return [p for m, p in u.aufrufe if m == "PUT" and p.startswith(prefix)]


def test_moving_a_piece_sends_the_whole_board(offen):
    u, _s = offen
    u.SCHEMATIX["canvas"].fokus = "node:minipc"
    _t(u, 10, curses.KEY_RIGHT, curses.KEY_RIGHT, 10)
    assert _puts(u, "/api/schematix/schemes/home")


def test_plus_places_a_planned_thing_in_the_hand(offen):
    u, s = offen
    _t(u, "+")
    assert u.SCHEMATIX["picker"]["pieces"]
    text = _bild(u, s, "14_picker")
    assert "ADD A PIECE" in text.upper() and "Switch" in text
    u.SCHEMATIX["picker"]["sel"] = 2                           # the switch (a kind of thing)
    _t(u, 10)
    c = u.SCHEMATIX["canvas"]
    assert c.modus == "greifen" and c.fokus == "device:switch-1"
    assert c.element("device:switch-1")["piece"]["state"] == "planned"
    _t(u, 10)
    assert _puts(u, "/api/schematix/schemes/home")


def test_a_live_piece_already_there_is_not_placed_twice(offen):
    u, _s = offen
    _t(u, "+", 10)                                             # minipc: already on the scheme
    assert u.SCHEMATIX["canvas"].fokus == "node:minipc" and "already" in u.SCHEMATIX["msg"]


def test_d_removes_a_planned_piece_after_asking(offen, monkeypatch):
    from tui import ansichten as A
    u, s = offen
    sent = []
    real = A.schematix.api_call
    monkeypatch.setattr(A.schematix, "api_call",
                        lambda p, m="GET", b=None, **k: sent.append(b) or real(p, m, b, **k))
    u.SCHEMATIX["canvas"].fokus = "device:router"
    _t(u, "d")
    assert "remove Router from the scheme? y / n" in _bild(u, s)
    _t(u, "y")
    ids = {p["id"] for p in sent[-1]["pieces"]}
    assert "device:router" not in ids and "node:pc" in ids
    assert sent[-1]["stand"] == "s1"


def test_m_makes_a_planned_thing_real(offen):
    u, _s = offen
    u.SCHEMATIX["canvas"].fokus = "device:router"
    _t(u, "m")
    assert _puts(u, "/api/schematix/things/router")


def test_the_real_starter_scheme_drawn(welt, _test_ordner, monkeypatch):  # noqa: F811
    """The TUI against the real core (Flask test client): the scheme "home"
    from heimnetz.md — planned router, live tablet link, this node live."""
    import ai_config
    from tui import ansichten as A
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(_test_ordner / "ai_config.json"))
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(ai_config, "_config", {"abgleich_apps": {"fokus": True, "tutor": False}})
    monkeypatch.setenv("ZENTRALE_NODE_NAME", "laptop")
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "datei")
    from ui.app import app
    app.config.update(TESTING=True)
    client = app.test_client()
    u = welt()

    def api(path, method="GET", body=None, timeout=3.0, **_k):
        r = client.open(path, method=method, json=body)
        return r.json
    monkeypatch.setattr(A.schematix, "api_call", api)
    s = _schirm(u)
    u.schematix.oeffnen()
    _bild(u, s, "14_home_top")
    c = u.SCHEMATIX["canvas"]
    c.fokus = "node:laptop"
    c.folgen(c.element("node:laptop")); c.springen()
    text = _bild(u, s, "14_home_nodes")
    assert "▣ LAPTOP" in text and "◂ this device" in text
    router = c.element("device:router")["piece"]
    assert router["state"] == "planned" and router["address"] == "192.168.50.254"
    c.fokus = "device:router"
    c.folgen(c.element("device:router")); c.springen()
    text = _bild(u, s, "14_home_router")
    assert "Router (Flint 2)" in text and "not yet" in text


# ── Step 15: rewire by drawing ──────────────────────────────────────────

def test_an_unfitting_socket_shows_a_red_x_and_refuses(offen):
    u, s = offen
    c = u.SCHEMATIX["canvas"]
    c.fokus = "app:cloud"
    _t(u, "v")
    c.ziel = "app:pdf@laptop"                                  # PDF viewer needs files, cloud offers sync
    text = _bild(u, s, "15_red_x")
    assert "✕" in text
    before = list(c.verbindungen)
    _t(u, 10)
    assert c.modus == "ruhe" and c.verbindungen == before      # did not attach
    assert u.SCHEMATIX["msg"] == "✕ PDF viewer needs `files`, Cloud offers `sync`"
    text = _bild(u, s, "15_refused")
    assert "✕ PDF viewer needs `files`" in text                # the short error at the socket


def test_a_fitting_wire_waits_for_run(offen):
    u, _s = offen
    c = u.SCHEMATIX["canvas"]
    c.fokus = "app:cloud"
    _t(u, "v")
    c.ziel = "app:fokus@laptop"
    _t(u, 10)                                                  # wired already: "unplug it?"
    assert "unplug" in u.schematix.status_text()
    _t(u, "y")
    assert u.SCHEMATIX["pending"]["sync/laptop/fokus"]["state"] == "off"
    assert "scheming" in u.schematix.titel()


def test_unplug_in_the_plugs_panel_then_run_shows_the_diff_and_switches(offen):
    u, s = offen
    from tui import ansichten as A
    sent = []
    real = A.schematix.api_call
    A.schematix.api_call = lambda p, m="GET", b=None, **k: sent.append((p, b)) or real(p, m, b, **k)
    try:
        u.SCHEMATIX["canvas"].fokus = "app:fokus@laptop"
        _t(u, "p")
        text = _bild(u, s, "15_plugs")
        assert "sync/laptop/fokus" in text
        _t(u, "x")
        assert u.SCHEMATIX["pending"]["sync/laptop/fokus"]["state"] == "off"
        _t(u, 27, "r")
        assert sent[-1][0] == "/api/schematix/run" and sent[-1][1]["apply"] is False
        assert sent[-1][1]["changes"][0]["id"] == "sync/laptop/fokus"
        text = _bild(u, s, "15_run_diff")
        assert "the scheme compiles" in text and "~ Tutor data" in text
        _t(u, 10)                                              # enter switches
        runs = [b for p, b in sent if p == "/api/schematix/run"]
        assert runs[-1]["apply"] is True and u.SCHEMATIX["pending"] == {}
        assert "switched" in u.SCHEMATIX["msg"]
    finally:
        A.schematix.api_call = real


def test_run_errors_are_pinned_on_the_board(offen):
    u, s = offen
    from tui import ansichten as A
    real = A.schematix.api_call
    refused = {"ok": False, "diff": [], "errors": [{"code": "unmet-requirement", "piece": "app:fokus",
                                                    "text": "app:fokus needs sync — nothing is plugged in"}]}
    A.schematix.api_call = lambda p, m="GET", b=None, **k: refused if p == "/api/schematix/run" \
        else real(p, m, b, **k)
    try:
        _t(u, "r")
        assert u.SCHEMATIX["fehler"] == {"app:fokus@laptop": "app:fokus needs sync — nothing is plugged in"}
        text = _bild(u, s, "15_run_refused")
        assert "refused — nothing switched" in text
        _t(u, 27)
        assert "✕ app:fokus needs sync" in _bild(u, s, "15_pinned")
    finally:
        A.schematix.api_call = real


def test_same_version_from_another_node(offen):
    u, _s = offen
    u.SCHEMATIX["canvas"].fokus = "node:minipc"
    _t(u, "s")
    assert _puts(u, "/api/schematix/same-version")
