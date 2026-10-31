"""Panning on the canvas building block, through the real TUI bundle, the
same input sequence for both apps on it: Desk and Schematix
(tui/bausteine/canvas.py `_pan`, memory/system/gefahrzonen.md "Pan without
limits"). 2026-10-31, Sasha: "in schematix … es fliegt zu schnell und is
dann stuck" — held W/A/S/D carried the view hundreds of cells a second past
the content into empty space. Desk had the same bug, its small desks just
hid it.

A burst of N key repeats must move a bounded amount per key, stay on the
growable surface (content + one view on every side — never lost in the
void), and the opposite key must move back at once."""
import copy
import fcntl
import json
import os
import pty
import select
import signal
import subprocess
import termios
import threading

import pytest

from _tui_fuzz import pty_supported
from tui.bausteine import canvas as cv
from test_fussleiste import welt  # noqa: F401  – fixture: the TUI without a screen
from test_schematix_tui import _bild, _schirm, _t
from tui.bausteine import pixel_icons

BURST = 120                     # ~6 s of key repeat at 20/s, all at once
# At most one view past the content: a held key (quarter view per step)
# brings the board back within a handful of steps.
RUECKWEG = 2 * cv.PAN_VIEW_DIVISOR + 2


class Uhr:
    """Key repeat faster than WIEDERHOLUNG_S: full acceleration every time."""

    def __init__(self):
        self.t = 100.0

    def __call__(self):
        self.t += 0.02
        return self.t


def _desk(u):
    u.desk.oeffnen()
    _t(u, 10)                                     # open "Elektronik"
    return u.DESK["canvas"]


def _schematix(u):
    u.schematix.starten = lambda f: f()
    u.schematix.oeffnen()
    return u.SCHEMATIX["canvas"]


def _sichtbar(c):
    """Pieces that overlap the view."""
    return [e["id"] for e in c.elemente
            if e["x"] < c.vx + c.vw and e["x"] + e["w"] > c.vx
            and e["y"] < c.vy + c.vh and e["y"] + e["h"] > c.vy]


@pytest.mark.parametrize("oeffnen", [_desk, _schematix], ids=["desk", "schematix"])
def test_a_burst_of_pan_keys_is_bounded_never_lost_and_recovers(welt, oeffnen):  # noqa: F811
    u = welt()
    s = _schirm(u)
    c = oeffnen(u)
    _bild(u, s)                                   # the view learns its size
    c.uhr = Uhr()
    deckel_x = max(6, c.vw // 4)
    deckel_y = max(3, c.vh // 4)
    for taste, zurueck in (("S", "W"), ("D", "A"), ("W", "S"), ("A", "D")):
        for _ in range(BURST):
            vx, vy = c.vx, c.vy
            _t(u, taste)
            assert abs(c.vx - vx) <= deckel_x and abs(c.vy - vy) <= deckel_y
        for _ in range(12):                       # let the glide settle
            _bild(u, s)
        assert not c.bewegt_sich()
        lo_x, hi_x, lo_y, hi_y = c.pan_bounds()
        assert lo_x <= c.vx <= hi_x and lo_y <= c.vy <= hi_y, (taste, c.vx, c.vy)
        vx, vy = c.vx, c.vy
        c.uhr = Uhr()
        c.uhr.t += 10                             # a pause: base step again
        _t(u, zurueck)
        assert (c.vx, c.vy) != (vx, vy)           # never stuck: back moves at once
        c.uhr = Uhr()
        for _ in range(RUECKWEG):                 # a short way back finds the board
            if _sichtbar(c):
                break
            _t(u, zurueck)
        assert _sichtbar(c), (taste, c.vx, c.vy)


# ── The real TUI in a PTY: the same bytes into Desk and Schematix ─────────

DESK_TITEL = ["alpha", "beta", "gamma", "delta"]
# What only the board shows: names and lines of the pieces, and the rows of
# the device icons (one run of glyphs each, so they come through the PTY whole).
SCHEMATIX_TITEL = ["the account's sync", "zentrale 44", "i: versions", "not yet", "Fokus", "Tutor",
                   "PDF viewer", "Router"] + [row.strip() for kind in ("laptop", "mini-pc", "tower", "router")
                                              for row in pixel_icons.cells(kind)]


def _backend():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import _schematix_fake
    desk = {"name": "Elektronik", "stand": "s1", "verbindungen": [], "elemente": [
        {"id": t, "art": "notiz", "x": (i % 2) * 40, "y": (i // 2) * 12, "w": 14, "h": 4, "text": t}
        for i, t in enumerate(DESK_TITEL)]}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

        def do_GET(self):
            p = self.path.split("?")[0]
            if p.startswith("/api/schematix") or p == "/api/pieces":
                return self._json(_schematix_fake.answer(self.path, "GET"))
            if p == "/api/desk":
                return self._json({"desks": [{"name": "Elektronik"}]})
            if p.startswith("/api/desk/"):
                return self._json(copy.deepcopy(desk))
            self._json({})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            self.rfile.read(n)
            self._json({"ok": True})
        do_PUT = do_POST

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _Tui:
    """The real TUI in a PTY with the fake backend, the app opened in front."""

    def __init__(self, env_app, titel):
        from _tui_fuzz import PYBIN, ROOT, _set_winsize, warte_auf, warte_auf_antwort
        self._warte_auf_antwort, self._set_winsize = warte_auf_antwort, _set_winsize
        self.titel = titel
        self.srv = _backend()
        self.buf = bytearray()
        self.master, slave = pty.openpty()
        _set_winsize(slave, 40, 120)
        env = dict(os.environ, TERM="xterm-256color", ZENTRALE_NO_AUDIO="1",
                   ZENTRALE_URL="http://127.0.0.1:%d" % self.srv.server_address[1], **env_app)
        for k in ("DISPLAY", "WAYLAND_DISPLAY", "ZENTRALE_TUI_RELOADED", "TMUX", "ZENTRALE_TUI_MAUS"):
            env.pop(k, None)

        def preexec():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.p = subprocess.Popen([PYBIN, "tui/zentrale_tui.py"], cwd=ROOT, stdin=slave,
                                  stdout=slave, stderr=subprocess.DEVNULL, env=env,
                                  close_fds=True, preexec_fn=preexec)
        os.close(slave)
        self.stop = threading.Event()
        self.leser = threading.Thread(target=self._drain, daemon=True)
        self.leser.start()
        self.groesse = 0
        self.zu = False
        try:
            warte_auf(lambda: b"ZENTRALE" in self.buf)
            self.ruhe()
            os.write(self.master, b"\r")                      # open the app in front
            warte_auf(lambda: any(t.encode() in self.buf for t in titel), frist=10)
            self.ruhe()
        except Exception:
            self.ende()
            raise

    def _drain(self):
        while not self.stop.is_set():
            try:
                r, _, _ = select.select([self.master], [], [], 0.1)
                if r:
                    self.buf.extend(os.read(self.master, 65536))
            except OSError:
                break

    def ruhe(self, vorher=None, frist=3.0, still=0.4):
        self._warte_auf_antwort(lambda: len(self.buf),
                                len(self.buf) - 1 if vorher is None else vorher,
                                ruhe=still, frist=frist)

    def senden(self, daten, frist=3.0, still=0.4):
        """Send, wait until the screen is quiet again -> whether it changed."""
        vorher = len(self.buf)
        os.write(self.master, daten)
        self.ruhe(vorher, frist=frist, still=still)
        return len(self.buf) > vorher

    def schirm(self):
        """Force a full repaint (resize) and return what is on the screen."""
        vorher = len(self.buf)
        self.groesse ^= 1
        self._set_winsize(self.master, *((41, 121) if self.groesse else (40, 120)))
        self.ruhe(vorher, frist=5, still=0.25)
        return bytes(self.buf[vorher:]).decode("utf-8", "replace")

    def brett_da(self):
        s = self.schirm()
        return any(t in s for t in self.titel)

    def zurueck_finden(self, daten):
        """Send `daten` again and again (a short hold / a swipe back) until
        the board is on the screen — at most RUECKWEG times."""
        for _ in range(RUECKWEG):
            if self.brett_da():
                return True
            self.senden(daten, frist=3, still=0.15)
        return self.brett_da()

    def ende(self, quit_taste=None):
        """Quit (Ctrl+C as a character: raw mode) or stop; -> the exit code."""
        if self.zu:
            return self.p.returncode
        self.zu = True
        try:
            if quit_taste is not None and self.p.poll() is None:
                os.write(self.master, quit_taste)
                try:
                    self.p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    pass
            if self.p.poll() is None:
                self.p.send_signal(signal.SIGINT)
                try:
                    self.p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.p.kill()
                    self.p.wait()
        finally:
            self.stop.set()
            self.leser.join(timeout=2)                        # it has read what was left
            self.srv.shutdown()
            try:
                os.close(self.master)
            except OSError:
                pass
        return self.p.returncode


APPS = pytest.mark.parametrize("env_app, titel", [
    ({"ZENTRALE_TUI_RAD": "9"}, DESK_TITEL),                  # elektronik → its desk
    ({"ZENTRALE_TUI_META": "2,0,0,2"}, SCHEMATIX_TITEL),      # Erschaffen wheel → schematix
], ids=["desk", "schematix"])
NEEDS_PTY = pytest.mark.skipif(not pty_supported(), reason="needs a Linux PTY with a controlling TTY")


@NEEDS_PTY
@APPS
def test_pty_held_pan_keys_stay_on_the_surface_and_find_back(env_app, titel):
    """Send each burst at once (held key: repeats pile up); the view may
    end up a view past the content, but the opposite key moves at once and
    a short hold brings the board back."""
    t = _Tui(env_app, titel)
    try:
        for taste, gegen in ((b"S", b"W"), (b"D", b"A"), (b"W", b"S"), (b"A", b"D")):
            t.senden(taste * BURST, frist=15)
            assert t.senden(gegen), "never stuck: the way back moves at once"
            assert t.zurueck_finden(gegen * 3), "the board is not found again after %r" % taste
    finally:
        t.ende()


def _rad(knopf, n=1, x=60, y=20):
    """n SGR wheel reports (64 up, 65 down, 66 left, 67 right)."""
    return ("\x1b[<%d;%d;%dM" % (knopf, x, y)).encode() * n


@NEEDS_PTY
@APPS
def test_pty_wheel_bursts_pan_bounded_and_mouse_mode_is_restored(env_app, titel):
    """Two-finger scroll / wheel (2026-10-31): vertical and horizontal
    bursts move the view a bounded amount (a fast swipe can't fling the
    board off the screen), many bursts never get lost, one notch back moves
    at once, and on quit the terminal gets its mouse modes back."""
    t = _Tui(env_app, titel)
    try:
        assert b"\x1b[?1002h" in t.buf and b"\x1b[?1006h" in t.buf   # reporting asked for
        for knopf, gegen in ((65, 64), (67, 66), (64, 65), (66, 67)):
            t.senden(_rad(knopf, BURST), frist=5)
            assert t.brett_da(), "one swipe flung the board away (button %d)" % knopf
            for _ in range(5):                                # keep swiping to the edge …
                t.senden(_rad(knopf, BURST), frist=3, still=0.1)
            assert t.senden(_rad(gegen)), "never stuck: one notch back moves at once"
            assert t.zurueck_finden(_rad(gegen, BURST)), "lost after swiping with button %d" % knopf
        code = t.ende(quit_taste=b"\x03")
    finally:
        t.ende()
    assert code == 0
    an, aus = t.buf.rfind(b"\x1b[?1002h"), t.buf.rfind(b"\x1b[?1002l")
    assert aus > an, "mouse reporting left on after quitting"
    assert t.buf.rfind(b"\x1b[?1006l") > t.buf.rfind(b"\x1b[?1006h")
