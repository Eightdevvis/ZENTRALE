"""
Ansicht A bedienen wie calcurse — in der echten TUI.

Die TUI läuft im Pseudo-Terminal gegen ein Mini-Backend, das die
Beispieltermine liefert und jeden schreibenden Aufruf mitschreibt. Geprüft
wird, was beim Backend ankommt, wenn man tippt wie in calcurse: a, Startzeit,
Ende, Titel; d auf einem Termin; Tab in den TODO-Kasten und a.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tui_fuzz import PYBIN, ROOT, _set_winsize, pty_supported  # noqa: E402

from tui.ansichten import kalender_beispiel as kb  # noqa: E402

pytestmark = pytest.mark.skipif(
    not pty_supported(), reason="braucht Linux-PTY mit Controlling-TTY")

GESCHRIEBEN = []
KONFLIKTE = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/calendar":
            q = dict(urllib.parse.parse_qsl(u.query))
            d = kb.api_daten(q.get("view", "week"), q.get("ref", kb.HEUTE),
                             heute=time.strftime("%Y-%m-%d"))
            d["weekplan"] = {"lid": "l_week", "items": [
                {"id": 1, "text": "Steuer", "done": False}]}
            self._json(d)
        elif u.path.startswith("/api/state"):
            self._json({"logs": []})
        else:
            self._json({})

    def _schreiben(self, methode):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(n) or b"null") if n else None
        if self.path == "/api/calendar/konflikte":
            return self._json({"konflikte": list(KONFLIKTE)})
        GESCHRIEBEN.append((methode, self.path, body))
        self._json({"ok": True})

    def do_POST(self):
        self._schreiben("POST")

    def do_PUT(self):
        self._schreiben("PUT")

    def do_DELETE(self):
        self._schreiben("DELETE")


def _lauf(tmp_path, tasten):
    import fcntl
    import pty
    import select
    import termios
    GESCHRIEBEN.clear()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    fehlerlog = tmp_path / "frame-fehler.log"
    master, slave = pty.openpty()
    _set_winsize(slave, 46, 150)
    env = dict(os.environ, TERM="xterm-256color", ZENTRALE_NO_AUDIO="1",
               ZENTRALE_URL="http://127.0.0.1:%d" % srv.server_address[1],
               ZENTRALE_TUI_RAD="2", ZENTRALE_TUI_FRAME_ERR_LOG=str(fehlerlog))
    for k in ("DISPLAY", "WAYLAND_DISPLAY", "ZENTRALE_TUI_RELOADED"):
        env.pop(k, None)

    def preexec():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    p = subprocess.Popen([PYBIN, "tui/zentrale_tui.py"], cwd=ROOT, stdin=slave,
                         stdout=slave, stderr=subprocess.DEVNULL, env=env,
                         close_fds=True, preexec_fn=preexec)
    os.close(slave)
    stop = threading.Event()

    def drain():
        while not stop.is_set():
            try:
                r, _, _ = select.select([master], [], [], 0.1)
                if r:
                    os.read(master, 65536)
            except OSError:
                break

    threading.Thread(target=drain, daemon=True).start()
    try:
        time.sleep(2.5)
        os.write(master, b"\r")             # Kalender öffnen
        time.sleep(1.0)
        os.write(master, b"v")              # → Ansicht A
        time.sleep(1.0)
        for t in tasten:
            os.write(master, t)
            time.sleep(0.35)
        time.sleep(1.0)
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
    return list(GESCHRIEBEN), (fehlerlog.read_text() if fehlerlog.exists() else "")


def _tipp(text):
    return [c.encode() for c in text] + [b"\r"]


def _formular(titel, von, bis):
    """Im Kasten: Titel, Tab bis „Von" (Tag, Ganztägig überspringen), Bis, Enter."""
    return ([b"a"] + [c.encode() for c in titel] + [b"\t", b"\t", b"\t"]
            + [c.encode() for c in von] + [b"\t"] + [c.encode() for c in bis] + [b"\r"])


def test_anlegen_wie_calcurse(tmp_path):
    w, fehler = _lauf(tmp_path, _formular("Zahnarzt", "14:00", "15:00"))
    assert fehler == "", fehler
    assert ("POST", "/api/calendar/entry") in [(m, p) for m, p, _b in w]
    body = [b for m, p, b in w if p == "/api/calendar/entry"][0]
    assert (body["time"], body["ende"], body["label"]) == ("14:00", "15:00", "Zahnarzt")
    assert body["day"] == time.strftime("%Y-%m-%d")


def test_kollision_fragt_und_nein_speichert_nicht(tmp_path):
    KONFLIKTE[:] = ["⚠ Kollision: Geige und Zahnarzt überlappen sich"]
    try:
        w, fehler = _lauf(tmp_path, _formular("Zahnarzt", "10:00", "11:00") + [b"n"])
    finally:
        KONFLIKTE.clear()
    assert fehler == ""
    assert not [p for m, p, _b in w if p == "/api/calendar/entry"]


def test_todo_kasten_mit_tab_und_a(tmp_path):
    w, fehler = _lauf(tmp_path, [b"\t", b"\t", b"a"] + _tipp("Blumen gießen") + [b"!"])
    assert fehler == ""
    assert ("POST", "/api/lists/l_week/items", {"text": "Blumen gießen"}) in w
    assert any(p == "/api/lists/l_week/items/1/toggle" for _m, p, _b in w)


def test_herumtasten_wirft_nie(tmp_path):
    """Alle Tasten einmal quer durch, mit Esc dazwischen — keine Ausnahme."""
    tasten = []
    for k in [b"j", b"k", b"\x1bOC", b"\x1bOD", b"t", b"T", b"w", b"W", b"m", b"M",
              b"\r", b" ", b"e", b"1", b"\x1b", b"d", b"n", b"r", b"\x1b", b"c", b"p",
              b"\t", b"\x1bOA", b"\x1bOB", b"0", b"$", b"\t", b"+", b"-", b"\t",
              b"g", b"\r", b"x", b"x", b"\x1b"]:
        tasten.append(k)
    w, fehler = _lauf(tmp_path, tasten)
    assert fehler == "", fehler
