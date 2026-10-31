"""Mouse and touchpad on the canvas (2026-10-31, Sasha: "I assumed you can
navigate around with two fingers on the touchpad, intuitively"):
tui/bausteine/sgr_mouse.py (reading SGR reports, mouse mode on/off) and the
canvas side (tui/bausteine/canvas.py `rad`, `zeiger`), then through the
real TUI bundle into Desk and Schematix (tui/zentrale_tui.py `maus_lesen`).
The real terminal path is in tests/test_canvas_pan_apps.py (PTY)."""
import curses

import pytest

from test_fussleiste import welt  # noqa: F401  – fixture: the TUI without a screen
from test_schematix_tui import _bild, _schirm, _t
from tui import zentrale_tui as zt
from tui.bausteine import canvas as cv
from tui.bausteine import sgr_mouse as sm
from tui.bausteine.canvas_arten import standard_arten

E = sm.Ereignis


def _strom(text):
    """A key stream: getch/ungetch over the characters of text."""
    folge = [ord(c) for c in text]

    def getch():
        return folge.pop(0) if folge else -1

    def ungetch(c):
        folge.insert(0, c)

    return getch, ungetch, folge


def _rad(knopf, n=1, x=10, y=5):
    return "\x1b[<%d;%d;%dM" % (knopf, x, y) * n


# ── Reading the reports ───────────────────────────────────────────────

def test_deuten_wheel_buttons_shift_and_left_button():
    assert sm.deuten(64, 1, 1, "M") == E("wheel", 0, 0, 0, -1)
    assert sm.deuten(65, 3, 2, "M") == E("wheel", 2, 1, 0, 1)
    assert sm.deuten(66, 1, 1, "M") == E("wheel", 0, 0, -1, 0)      # two fingers sideways
    assert sm.deuten(67, 1, 1, "M") == E("wheel", 0, 0, 1, 0)
    assert sm.deuten(64 | 4, 1, 1, "M") == E("wheel", 0, 0, -1, 0)  # shift + wheel = sideways
    assert sm.deuten(0, 5, 6, "M") == E("press", 4, 5, 0, 0)
    assert sm.deuten(32, 5, 6, "M") == E("drag", 4, 5, 0, 0)
    assert sm.deuten(0, 5, 6, "m") == E("release", 4, 5, 0, 0)
    assert sm.deuten(2, 5, 6, "M") is None                           # right button: not ours
    assert sm.deuten(35, 5, 6, "M") is None                          # motion without a button


@pytest.mark.parametrize("start", ["esc", "key_mouse"])
def test_lesen_takes_both_starts_and_sums_a_burst(start):
    """tmux-256color: everything as characters; xterm-256color: ncurses
    turns "ESC [ <" into KEY_MOUSE (measured with ncurses 6.4)."""
    text = _rad(65, 40) + _rad(67, 3) + "q"
    if start == "esc":
        getch, ungetch, folge = _strom(text[1:])
        erg = sm.lesen(27, getch, ungetch)
    else:
        getch, ungetch, folge = _strom(text[3:].replace("\x1b[<", "\x00"))
        real = getch

        def getch():
            c = real()
            return sm.KEY_MOUSE if c == 0 else c
        erg = sm.lesen(sm.KEY_MOUSE, getch, ungetch)
    assert erg == [E("wheel", 9, 4, 3, 40)]
    assert folge == [ord("q")]                                       # the key after it stays


def test_lesen_puts_back_what_is_no_mouse_report():
    getch, ungetch, folge = _strom("x")                              # alt+x
    assert sm.lesen(27, getch, ungetch) is None and folge == [ord("x")]
    getch, ungetch, folge = _strom("[A")
    assert sm.lesen(27, getch, ungetch) is None and folge == [ord("["), ord("A")]
    getch, ungetch, folge = _strom("")                               # a lone esc
    assert sm.lesen(27, getch, ungetch) is None and folge == []
    assert sm.lesen(ord("a"), *_strom("")[:2]) is None


def test_lesen_keeps_press_drag_release_in_order_and_merges_drags():
    text = "\x1b[<0;5;5M\x1b[<32;6;5M\x1b[<32;7;5M\x1b[<32;9;6M\x1b[<0;9;6m"
    getch, ungetch, _f = _strom(text[1:])
    assert sm.lesen(27, getch, ungetch) == [E("press", 4, 4, 0, 0), E("drag", 8, 5, 0, 0),
                                           E("release", 8, 5, 0, 0)]


def test_modus_writes_only_on_change_and_restores_around_a_program():
    raus = []
    m = sm.Modus(raus.append)
    m.setzen(True); m.setzen(True)
    assert raus == [sm.AN]
    with m.ausgesetzt():
        assert raus[-1] == sm.AUS and not m.an
    assert raus[-1] == sm.AN and m.an
    m.setzen(False)
    assert raus == [sm.AN, sm.AUS, sm.AN, sm.AUS]
    assert b"1002" in sm.AN and b"1006" in sm.AN and b"1000" in sm.AN
    assert sm.AUS == sm.AN.replace(b"h", b"l").replace(b"1000l\x1b[?1002l\x1b[?1006l",
                                                       b"1006l\x1b[?1002l\x1b[?1000l")


def test_gewuenscht_respects_the_chat_mouse_switch():
    assert sm.gewuenscht({}) and not sm.gewuenscht({"ZENTRALE_TUI_MAUS": "aus"})


class _Schirm:
    def __init__(self, codes):
        self.codes = list(codes)

    def timeout(self, _ms):
        pass

    def getch(self):
        return self.codes.pop(0) if self.codes else -1


def test_piled_up_arrows_are_swallowed_other_keys_stay(monkeypatch):
    """Without mouse reporting the wheel comes as a pile of arrows
    (alternate scroll) — one step per frame."""
    zurueck = []
    monkeypatch.setattr(curses, "ungetch", zurueck.append)
    s = _Schirm([curses.KEY_DOWN] * 30 + [ord("x")])
    assert sm.pfeile_schlucken(curses.KEY_DOWN, s) == 30 and zurueck == [ord("x")]
    assert sm.pfeile_schlucken(ord("d"), _Schirm([ord("d")])) == 0


# ── The canvas side ───────────────────────────────────────────────────

def _leinwand():
    els = [{"id": i, "art": "notiz", "x": x, "y": y, "w": 10, "h": 4, "text": i}
           for i, x, y in (("a", 0, 0), ("b", 30, 0), ("c", 0, 12))]
    c = cv.Canvas(standard_arten(cv.Arten()), els, [])
    c.vx, c.vy, c.vw, c.vh = -10, -5, 80, 24
    c.ursprung = (2, 3)                                  # drawn at row 2, column 3
    return c


def _auf(c, wx, wy):
    """Screen cell of world cell (wx, wy)."""
    return wx - c.vx + c.ursprung[1], wy - c.vy + c.ursprung[0]


def test_wheel_pans_capped_per_frame_and_stays_on_the_surface():
    c = _leinwand()
    kx, ky = max(cv.PAN_X, c.vw // 4), max(cv.PAN_Y, c.vh // 4)
    vy = c.vy
    c.rad(0, 1)
    assert c.vy == vy + cv.RAD_Y
    for dx, dy in ((0, 500), (500, 0), (0, -500), (-500, 0)):
        for _ in range(40):
            vx, vy = c.vx, c.vy
            c.rad(dx, dy)
            assert abs(c.vx - vx) <= kx and abs(c.vy - vy) <= ky         # no fling
        lo_x, hi_x, lo_y, hi_y = c.pan_bounds()
        assert lo_x <= c.vx <= hi_x and lo_y <= c.vy <= hi_y
        vor = (c.vx, c.vy)
        c.rad(-(dx > 0) + (dx < 0), -(dy > 0) + (dy < 0))                 # one notch back
        assert (c.vx, c.vy) != vor


def test_click_puts_the_cursor_and_selects_the_piece_under_it():
    c = _leinwand()
    c.zeiger("press", *_auf(c, 32, 1))
    c.zeiger("release", *_auf(c, 32, 1))
    assert c.fokus == "b" and (c.cx, c.cy) == (32, 1)
    c.zeiger("press", *_auf(c, 20, 1))                   # empty space: no focus, cursor there
    c.zeiger("release", *_auf(c, 20, 1))
    assert c.fokus is None and (c.cx, c.cy) == (20, 1)
    c.zeiger("press", 0, 0)                              # outside the drawn view: nothing
    assert (c.cx, c.cy) == (20, 1)


def test_drag_carries_a_piece_and_release_drops_it_like_enter():
    c = _leinwand()
    c.zeiger("press", *_auf(c, 2, 1))
    assert c.zeiger("drag", *_auf(c, 7, 3)) is None and c.modus == "greifen"
    c.zeiger("drag", *_auf(c, 9, 4))
    erg = c.zeiger("release", *_auf(c, 9, 4))
    a = c.element("a")
    assert (a["x"], a["y"]) == (7, 3) and c.modus == "ruhe"
    assert erg == cv.Ergebnis("geaendert", a, "verschoben")


def test_drag_on_empty_space_drags_the_surface():
    c = _leinwand()
    vx, vy = c.vx, c.vy
    c.zeiger("press", *_auf(c, 20, 8))
    sx, sy = _auf(c, 20, 8)
    c.zeiger("drag", sx - 5, sy - 2)
    assert (c.vx, c.vy) == (vx + 5, vy + 2) and c.modus == "ruhe"
    assert c.zeiger("release", sx - 5, sy - 2) is None


def test_mouse_waits_while_a_question_is_open():
    c = _leinwand()
    c.fokus = "a"
    c.taste("loeschen")
    vor = (c.vx, c.vy)
    c.maus([E("wheel", 0, 0, 0, 3), E("press", *_auf(c, 32, 1), 0, 0)])
    assert (c.vx, c.vy) == vor and c.modus == "frage" and c.fokus == "a"


# ── Through the real TUI bundle: Desk and Schematix ───────────────────

def _desk(u):
    u.desk.oeffnen()
    _t(u, 10)
    return u.DESK["canvas"]


def _schematix(u):
    u.schematix.starten = lambda f: f()
    u.schematix.oeffnen()
    return u.SCHEMATIX["canvas"]


@pytest.fixture
def maus_an(monkeypatch):
    """The canvas mouse switched on without writing to the terminal."""
    m = sm.Modus(lambda b: None)
    monkeypatch.setattr(sm, "MODUS", m)
    monkeypatch.setattr(curses, "ungetch", lambda c: None)
    return m


def _melden(u, text):
    """Hand a report to the main loop's reader, as getch delivers it."""
    u.stdscr.folge = [ord(c) for c in text[1:]]
    return zt.maus_lesen(u, 27)


@pytest.mark.parametrize("oeffnen", [_desk, _schematix], ids=["desk", "schematix"])
def test_the_app_in_front_wants_the_mouse_and_gets_wheel_and_click(welt, maus_an, oeffnen):  # noqa: F811
    u = welt()
    s = _schirm(u)
    s.folge = []
    c = oeffnen(u)
    _bild(u, s)                                          # the view learns size and place
    zt.canvas_maus_pflegen(u)
    assert maus_an.an
    kx, ky = max(cv.PAN_X, c.vw // 4), max(cv.PAN_Y, c.vh // 4)
    for knopf in (65, 67, 64, 66):                       # down, right, up, left
        for _ in range(15):
            vx, vy = c.vx, c.vy
            assert _melden(u, _rad(knopf, 120, 40, 15))
            assert abs(c.vx - vx) <= kx and abs(c.vy - vy) <= ky
        lo_x, hi_x, lo_y, hi_y = c.pan_bounds()
        assert lo_x <= c.vx <= hi_x and lo_y <= c.vy <= hi_y
    e = c.elemente[0]
    zt.bild_zeichnen(u)
    c.springen()
    c.folgen(e)
    c.springen()
    sx, sy = e["x"] + 1 - c.vx + c.ursprung[1], e["y"] + 1 - c.vy + c.ursprung[0]
    _melden(u, "\x1b[<0;%d;%dM\x1b[<0;%d;%dm" % (sx + 1, sy + 1, sx + 1, sy + 1))
    assert c.fokus == e["id"]
    # Something on top (the command line): the mouse report is used up, nothing moves.
    u.bz.cmd_mode = True
    vor = (c.vx, c.vy)
    assert _melden(u, _rad(65, 5))
    assert (c.vx, c.vy) == vor
    u.bz.cmd_mode = False
    # The app closes: reporting goes off.
    _t(u, 27)
    zt.canvas_maus_pflegen(u)
    if u.SCHEMATIX["active"] or (u.DESK["active"] and u.DESK["ebene"] == "canvas"):
        _t(u, 27)
        zt.canvas_maus_pflegen(u)
    assert not maus_an.an


def test_mouse_off_means_reports_are_not_read(welt, monkeypatch):  # noqa: F811
    m = sm.Modus(lambda b: None)
    monkeypatch.setattr(sm, "MODUS", m)
    u = welt()
    _schirm(u)
    assert not zt.maus_lesen(u, 27)                      # esc goes its usual way
    monkeypatch.setenv("ZENTRALE_TUI_MAUS", "aus")
    _desk(u)
    zt.canvas_maus_pflegen(u)
    assert not m.an


def test_desk_swallows_piled_up_arrows(welt):  # noqa: F811
    """No mouse reporting (alternate scroll): a swipe arrives as 40 arrows
    at once — the cursor moves one step, not forty."""
    u = welt()
    s = _schirm(u)
    c = _desk(u)
    _bild(u, s)
    c.uhr = None                                         # base step: count the steps alone
    s.folge = [curses.KEY_DOWN] * 40
    _t(u, curses.KEY_DOWN)
    y0 = c.cy
    s.folge = [curses.KEY_DOWN] * 40
    _t(u, curses.KEY_DOWN)
    assert c.cy - y0 == cv.CURSOR_Y and s.folge == []
