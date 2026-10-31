"""Panning on the canvas building block, through the real TUI bundle, the
same input sequence for both apps on it: Desk and Schematix
(tui/bausteine/canvas.py `_pan`, memory/system/gefahrzonen.md "Pan without
limits"). 2026-10-31, Sasha: "in schematix … es fliegt zu schnell und is
dann stuck" — held W/A/S/D carried the view hundreds of cells a second past
the content into empty space. Desk had the same bug, its small desks just
hid it.

A burst of N key repeats must move a bounded amount per key, never leave
the content behind, and the opposite key must move back at once."""
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
from test_fussleiste import welt  # noqa: F401  – fixture: the TUI without a screen
from test_schematix_tui import _bild, _schirm, _t

BURST = 120                     # ~6 s of key repeat at 20/s, all at once


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
        assert _sichtbar(c), (taste, c.vx, c.vy)  # the board is still there
        vx, vy = c.vx, c.vy
        c.uhr = Uhr()
        c.uhr.t += 10                             # a pause: base step again
        _t(u, zurueck)
        assert (c.vx, c.vy) != (vx, vy)           # never stuck: back moves at once


# ── The real TUI in a PTY: the same bytes into Desk and Schematix ─────────

DESK_TITEL = ["alpha", "beta", "gamma", "delta"]
SCHEMATIX_TITEL = ["☁ CLOUD", "▣ LAPTOP", "▣ MINIPC", "▣ PC", "Fokus", "Tutor", "PDF viewer", "◈ Router"]


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


def _pty_lauf(env_app, titel):
    """Open the app, send each burst at once (held key: repeats pile up),
    then force a full repaint (resize) and keep what is really on the
    screen; then the opposite key must change the screen."""
    from _tui_fuzz import PYBIN, ROOT, _set_winsize, warte_auf, warte_auf_antwort
    srv = _backend()
    buf = bytearray()
    master, slave = pty.openpty()
    _set_winsize(slave, 40, 120)
    env = dict(os.environ, TERM="xterm-256color", ZENTRALE_NO_AUDIO="1",
               ZENTRALE_URL="http://127.0.0.1:%d" % srv.server_address[1], **env_app)
    for k in ("DISPLAY", "WAYLAND_DISPLAY", "ZENTRALE_TUI_RELOADED", "TMUX"):
        env.pop(k, None)

    def preexec():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    p = subprocess.Popen([PYBIN, "tui/zentrale_tui.py"], cwd=ROOT, stdin=slave, stdout=slave,
                         stderr=subprocess.DEVNULL, env=env, close_fds=True, preexec_fn=preexec)
    os.close(slave)
    stop = threading.Event()

    def drain():
        while not stop.is_set():
            try:
                r, _, _ = select.select([master], [], [], 0.1)
                if r:
                    buf.extend(os.read(master, 65536))
            except OSError:
                break
    threading.Thread(target=drain, daemon=True).start()

    def ruhe(vorher=None, frist=3.0):
        warte_auf_antwort(lambda: len(buf), len(buf) - 1 if vorher is None else vorher,
                          ruhe=0.4, frist=frist)

    schirme, zurueck = [], []
    try:
        warte_auf(lambda: b"ZENTRALE" in buf)
        ruhe()
        os.write(master, b"\r")                               # open the app in front
        warte_auf(lambda: any(t.encode() in buf for t in titel), frist=10)
        ruhe()
        groessen = [(41, 121), (40, 120)]
        for i, (taste, gegen) in enumerate(((b"S", b"W"), (b"D", b"A"), (b"W", b"S"), (b"A", b"D"))):
            os.write(master, taste * BURST)
            ruhe(frist=15)
            vorher = len(buf)
            _set_winsize(master, *groessen[i % 2])            # SIGWINCH → full repaint
            ruhe(vorher, frist=5)
            schirme.append(bytes(buf[vorher:]).decode("utf-8", "replace"))
            vorher = len(buf)
            os.write(master, gegen)
            ruhe(vorher, frist=2)
            zurueck.append(len(buf) > vorher)
            os.write(master, taste)                           # and forth again
            ruhe()
    finally:
        stop.set()
        srv.shutdown()
        if p.poll() is None:
            p.send_signal(signal.SIGINT)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        try:
            os.close(master)
        except OSError:
            pass
    return schirme, zurueck


@pytest.mark.skipif(not pty_supported(), reason="needs a Linux PTY with a controlling TTY")
@pytest.mark.parametrize("env_app, titel", [
    ({"ZENTRALE_TUI_RAD": "9"}, DESK_TITEL),                  # elektronik → its desk
    ({"ZENTRALE_TUI_META": "2,0,0,2"}, SCHEMATIX_TITEL),      # Erschaffen wheel → schematix
], ids=["desk", "schematix"])
def test_pty_held_pan_keys_keep_the_board_on_screen(env_app, titel):
    schirme, zurueck = _pty_lauf(env_app, titel)
    assert len(schirme) == 4
    for i, s in enumerate(schirme):
        assert any(t in s for t in titel), "burst %d: the board is gone from the screen" % i
    assert all(zurueck), zurueck                              # never stuck
