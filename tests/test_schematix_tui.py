"""Schematix in the TUI (tui/ansichten/schematix.py, schematix_bild.py,
schematix_arten.py; memory/hub/schematix.md, look: schematix_style.md)
without a terminal: the real TUI bundle of tests/test_fussleiste.py with the
fake map of tests/_schematix_fake.py, drawn into a recording screen.

With SCHEMATIX_CAPTURE=<folder> the screens are also written there — as
text, and as a PNG with the real colour roles when Pillow is there (render
checks for Sasha; nothing is written otherwise)."""
import copy
import curses
import os

import pytest

import _schematix_fake
import _schematix_png
import test_fussleiste as F
from test_fussleiste import welt  # noqa: F401  – fixture: the TUI without a screen
from tui import zentrale_tui as zt
from tui.ansichten import schematix_bild
from tui.bausteine import pixel_icons

H, W = 46, 150
CAPTURE = os.environ.get("SCHEMATIX_CAPTURE")
CODE = 1 << 40                          # attributes the capture hands out start here


class Aufnahme(F.Schirm):
    """A screen that keeps what was drawn (characters and attributes)."""

    def __init__(self):
        super().__init__()
        self.erase()

    def getmaxyx(self):
        return (H, W)

    def erase(self):
        self.zeilen = [[(" ", 0)] * W for _ in range(H)]

    def addstr(self, y, x, text, attr=0):
        for i, ch in enumerate(str(text)):
            if 0 <= y < H and 0 <= x + i < W:
                self.zeilen[y][x + i] = (ch, attr)

    addnstr = addstr

    def text(self):
        return "\n".join("".join(ch for ch, _a in z).rstrip() for z in self.zeilen)


COLOURS = {}


@pytest.fixture(autouse=True)
def _colour_capture(monkeypatch):
    """Capturing: every colour Schematix asks for gets its own attribute, so
    the PNG shows the real roles (fg, bg, bold)."""
    if not CAPTURE:
        return
    seen = {}

    def attr(_app, _role, fg, bg, bold):
        key = (fg or "#b4c8bf", bg or "#05060a", bool(bold))
        if key not in seen:
            seen[key] = CODE + len(seen)
            COLOURS[seen[key]] = key
        return seen[key]
    monkeypatch.setattr(schematix_bild, "_attr", attr)


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
    if CAPTURE and name:
        os.makedirs(CAPTURE, exist_ok=True)
        with open(os.path.join(CAPTURE, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        if _schematix_png.available():
            _schematix_png.write(s.zeilen, COLOURS, os.path.join(CAPTURE, name + ".png"))
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


def _mit_karte(u, monkeypatch, m):
    """Open Schematix on another map (the rest of the fake backend stays)."""
    from tui import ansichten as A
    real = A.schematix.api_call

    def api(p, method="GET", body=None, **k):
        if p.split("?")[0] == "/api/schematix/map":
            return copy.deepcopy(m)
        return real(p, method, body, **k)
    monkeypatch.setattr(A.schematix, "api_call", api)
    u.schematix.starten = lambda f: f()
    u.schematix.oeffnen()


def test_board_shows_planes_sigils_icons_and_traces(offen):
    u, s = offen
    text = _bild(u, s, "01_board")
    assert "━1 sync" in text and "━5 power" in text            # layers on: ━
    assert "// cloud" in text and "// nodes" in text           # every plane says what it is
    assert "// bands" in text and "// traces" in text          # the data column
    assert "live 01/02" in text
    assert "◎ Fokus" in text and "⍥ Tutor" in text             # software: sigil + name
    assert "cloud" in text and "the account's sync" in text
    assert "▄▄▄▄" in text                                      # the step between two planes
    assert "╱" in text and "·" in text                         # textures: hatching, grid
    assert "◦" in text and "┄" in text                         # vias, an unplugged trace
    assert "◇ no" in text                                     # the planned pc, cut by the view edge
    for kind, planned in (("laptop", False), ("mini-pc", False), ("tower", True)):
        assert pixel_icons.cells(kind, hatched=planned)[0] in text   # nodes drawn as what they are
    # the name stands below the icon
    zeilen = text.splitlines()
    icon = pixel_icons.cells("laptop")
    y = next(i for i, z in enumerate(zeilen) if icon[-1] in z)
    assert "laptop" in zeilen[y + 1]


def test_pieces_stand_on_a_plate_the_texture_stops_there(offen):
    """The surfaces: a piece is drawn on surface-piece, the planes around it
    on their own surface — depth by material, not by a box."""
    u, s = offen
    grounds = []
    real = schematix_bild.farbe

    def farbe(app, rolle, grund="board"):
        grounds.append(grund)
        return real(app, rolle, grund)
    schematix_bild.farbe = farbe
    try:
        _bild(u, s)
    finally:
        schematix_bild.farbe = real
    assert {"surface-piece", "surface-cloud", "surface-software", "surface-nodes",
            "surface-things", "board"} <= set(grounds)


def test_a_layer_key_hides_its_wires(offen):
    u, s = offen
    assert u.SCHEMATIX["canvas"].verbindungen
    _t(u, "1")
    assert u.SCHEMATIX["layers"]["data"] is False and not u.SCHEMATIX["canvas"].verbindungen
    assert "┄1 sync" in _bild(u, s)
    _t(u, "3")                                                 # hardware: things go too
    assert "device:router" not in {e["id"] for e in u.SCHEMATIX["canvas"].elemente}


def test_versions_panel_folds_open_on_a_node(offen):
    u, s = offen
    u.SCHEMATIX["canvas"].fokus = "node:minipc"
    h = u.SCHEMATIX["canvas"].element("node:minipc")["h"]
    _t(u, "i")
    el = u.SCHEMATIX["canvas"].element("node:minipc")
    assert el["offen"] and el["h"] > h and u.SCHEMATIX["canvas"].fokus == "node:minipc"
    text = _bild(u, s, "02_versions")
    assert "contracts: ports 1" in text and "auto-update: on" in text
    assert "╭─────" in text and "│" in text                    # focus: a thin outline, not ┏━┓
    assert "┏━" not in text


def test_colours_are_knobs_with_measured_contrast(offen):
    u, s = offen
    _t(u, "c")
    text = _bild(u, s, "10_colours")
    assert "COLOUR ROLES" in text.upper() and "7.0:1" in text
    assert "dim on it" in text and "texture, no floor" in text and "on board" in text
    _t(u, curses.KEY_DOWN, 10)                                 # ink → the colour wheel
    assert u.SCHEMATIX["farbe"] is not None
    _t(u, 27)
    assert u.SCHEMATIX["farbe"] is None and u.SCHEMATIX["ebene"] == "colours"


def test_the_colour_list_scrolls_to_the_selected_role(offen):
    u, s = offen
    _t(u, "c")
    n = len(u.SCHEMATIX["palette"]["roles"])
    u.SCHEMATIX["colour_sel"] = n - 1
    assert "› texture-things" in _bild(u, s)


def test_esc_closes(offen):
    u, _s = offen
    _t(u, 27)
    assert u.SCHEMATIX["active"] is False


# ── The look (memory/hub/schematix_style.md): dense software, planned
#    pieces, every device icon — captures for Sasha ──────────────────────

def _dense():
    m = copy.deepcopy(_schematix_fake.MAP)
    names = ["kalender", "mail", "notizen", "graphen", "karte", "klavier", "werkstatt", "schematix",
             "budget", "zyklus"]
    pieces = [p for p in m["pieces"] if p["band"] != "software"]
    for i, name in enumerate(names):
        node, col = ("laptop", 0) if i % 2 == 0 else ("minipc", 50)
        p = _schematix_fake._app(name, node, col + (i // 2 % 2) * 27,
                                 ("synced", "off", "open")[i % 3])
        p["y"] = 8 + (i // 4) * 5
        pieces.append(p)
        if p["sync"] != "open":
            m["wires"].append(_schematix_fake._wire(name, node, "live" if p["sync"] == "synced" else "off"))
    m["pieces"] = pieces
    m["bands"] = [{"id": "cloud", "y": 0}, {"id": "software", "y": 8}, {"id": "nodes", "y": 26},
                  {"id": "things", "y": 38}]
    for p in m["pieces"]:
        if p["band"] == "nodes":
            p["y"] = 26
        elif p["band"] == "things":
            p["y"] = 38
    return m


def test_capture_a_dense_software_layer(welt, monkeypatch):  # noqa: F811
    u = welt()
    s = _schirm(u)
    _mit_karte(u, monkeypatch, _dense())
    text = _bild(u, s, "04_dense_software")
    assert "☽ Kalender" in text and "⎈ Schematix" in text
    assert text.count("⇅ synced") >= 3 and "stays on this device" in text


def _all_things():
    """Every kind of device the icon file knows, alternately planned and
    documented — the icon sheet."""
    m = copy.deepcopy(_schematix_fake.MAP)
    m["pieces"] = [p for p in m["pieces"] if p["band"] != "things"]
    for i, kind in enumerate(k for k in pixel_icons.kinds() if k != "cloud"):
        m["pieces"].append({
            "id": "device:%s" % kind, "ref": "zentrale://schematix/things/%s/" % kind, "kind": "device",
            "title": kind.replace("-", " ").title(), "role": kind, "thing_kind": kind,
            "state": "planned" if i % 2 else "documented", "band": "things", "needs": [], "offers": [],
            "address": "192.168.50.%d" % (200 + i) if i % 4 == 1 else None,
            "x": (i % 5) * 23, "y": 32 + (i // 5) * 11, "w": 24, "h": 4})
    return m


def test_capture_every_device_icon_with_its_name_below(welt, monkeypatch):  # noqa: F811
    u = welt()
    s = _schirm(u)
    m = _all_things()
    _mit_karte(u, monkeypatch, m)
    _bild(u, s)                                                # the view learns its size
    c = u.SCHEMATIX["canvas"]
    c.vx, c.vy = -2, 29
    c.springen()
    text = _bild(u, s, "05_icons_planned_and_documented")
    zeilen = text.splitlines()
    things = [p for p in m["pieces"] if p["kind"] == "device"]
    assert len(things) >= 14                                   # every kind of the icon file
    for p in things:
        icon = pixel_icons.cells(p["thing_kind"], hatched=p["state"] == "planned")
        y = next((i for i, z in enumerate(zeilen) if p["title"] in z), None)
        assert y is not None, p["title"]
        assert icon[-1].strip() in zeilen[y - 1], p["title"]   # the name right below the icon
    assert "◇ not yet" in text and "▣ documented" in text


def test_planned_pieces_are_hatched_and_dotted(offen):
    u, s = offen
    c = u.SCHEMATIX["canvas"]
    el = c.element("node:pc")
    text = _bild(u, s)
    assert pixel_icons.cells("laptop", hatched=True) != pixel_icons.cells("laptop")   # filled parts hatch
    assert pixel_icons.cells("tower", hatched=True)[0] in text
    assert el["piece"]["state"] == "planned"
    assert "╭┄" in text and "┊" in text


def test_a_hot_reload_reopens_schematix():
    """zentrale_tui.py remembers the open app across a hot reload; Schematix
    is one of them (2026-10-31: it was missing, the reload landed on the wheel)."""
    import ast
    src = open(zt.__file__, encoding="utf-8").read()
    node = next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "_offen_apps")
    names = [e.elts[0].value for e in node.value.elts]
    assert "schematix" in names


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
    text = _bild(u, s, "11_picker")
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


def test_x_removes_a_planned_piece_after_asking(offen, monkeypatch):
    from tui import ansichten as A
    u, s = offen
    sent = []
    real = A.schematix.api_call
    monkeypatch.setattr(A.schematix, "api_call",
                        lambda p, m="GET", b=None, **k: sent.append(b) or real(p, m, b, **k))
    u.SCHEMATIX["canvas"].fokus = "device:router"
    _t(u, "x")
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
    _bild(u, s, "03a_home_top")
    c = u.SCHEMATIX["canvas"]
    c.fokus = "node:laptop"
    c.folgen(c.element("node:laptop")); c.springen()
    text = _bild(u, s, "03b_home_nodes")
    assert "laptop" in text and "◂ this device" in text and pixel_icons.cells("laptop")[0] in text
    router = c.element("device:router")["piece"]
    assert router["state"] == "planned" and router["address"] == "192.168.50.254"
    c.fokus = "device:router"
    c.folgen(c.element("device:router")); c.springen()
    text = _bild(u, s, "03c_home_things")
    assert "Router (Flint 2)" in text and "not yet" in text
    assert "Tablet" in text and pixel_icons.cells("tablet")[0] in text          # documented, drawn as a tablet
    assert pixel_icons.cells("router", hatched=True)[-1] in text                 # planned: hatched


# ── Step 15: rewire by drawing ──────────────────────────────────────────

def test_an_unfitting_socket_shows_a_red_x_and_refuses(offen):
    u, s = offen
    c = u.SCHEMATIX["canvas"]
    c.fokus = "app:cloud"
    _t(u, "v")
    c.ziel = "app:pdf@laptop"                                  # PDF viewer needs files, cloud offers sync
    text = _bild(u, s, "06_red_x")
    assert "✕" in text
    before = list(c.verbindungen)
    _t(u, 10)
    assert c.modus == "ruhe" and c.verbindungen == before      # did not attach
    assert u.SCHEMATIX["msg"] == "✕ PDF viewer needs `files`, Cloud offers `sync`"
    text = _bild(u, s, "07_refused")
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
        text = _bild(u, s, "12_plugs")
        assert "sync/laptop/fokus" in text
        _t(u, "x")
        assert u.SCHEMATIX["pending"]["sync/laptop/fokus"]["state"] == "off"
        _t(u, 27, "r")
        assert sent[-1][0] == "/api/schematix/run" and sent[-1][1]["apply"] is False
        assert sent[-1][1]["changes"][0]["id"] == "sync/laptop/fokus"
        text = _bild(u, s, "08_run_diff")
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
        text = _bild(u, s, "09a_run_refused")
        assert "refused — nothing switched" in text
        _t(u, 27)
        assert "✕ app:fokus needs sync" in _bild(u, s, "09b_pinned")
    finally:
        A.schematix.api_call = real


def test_same_version_from_another_node(offen):
    u, _s = offen
    u.SCHEMATIX["canvas"].fokus = "node:minipc"
    _t(u, "u")
    assert _puts(u, "/api/schematix/same-version")
