"""
Ansichten A/B/C in der echten TUI: v dreht jetziger → A → B → C → jetziger.

Sasha, 07.10.2026: alle drei Entwürfe einbauen, mit v umschaltbar; der
jetzige Kalender bleibt eine Station im Kreis und ist der einzige Ort zum
Bearbeiten, Woche↔Monat geht dort mit Tab.

Gefahren wird die echte TUI im Pseudo-Terminal gegen ein Mini-Backend, das
die Beispieltermine (tui/ansichten/kalender_beispiel.py) als /api/calendar
liefert. Geprüft wird, was über den Schirm geht, und dass keine Ansicht beim
Zeichnen eine Ausnahme wirft (die TUI fängt sie ab und schreibt sie ins
Frame-Fehler-Log — ohne dieses Log fiele ein kaputter Zweig nicht auf).
"""

import json
import os
import re
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

KALENDER_IM_RAD = 2          # startseite.RAD_APPS: klavier, post, kalender …
ABFRAGEN = []


class _Handler(BaseHTTPRequestHandler):
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
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/calendar":
            q = dict(urllib.parse.parse_qsl(u.query))
            ABFRAGEN.append((q.get("view"), q.get("ref")))
            self._json(kb.api_daten(q.get("view", "week"), q.get("ref", kb.HEUTE)))
        elif u.path.startswith("/api/state"):
            self._json({"logs": []})
        else:
            self._json({})

    def do_POST(self):
        self._json({})


def _strip(s):
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][B0]|\x1b[=>]", "", s)


def _lauf(tmp_path, schritte):
    """TUI starten, Kalender öffnen, `schritte` = [(tasten, name), …] senden.
    -> ({name: was nach diesem Schritt über den Schirm ging}, frame_fehler)"""
    import fcntl
    import pty
    import select
    import termios

    ABFRAGEN.clear()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    fehlerlog = tmp_path / "frame-fehler.log"
    master, slave = pty.openpty()
    _set_winsize(slave, 46, 150)
    env = dict(os.environ, TERM="xterm-256color", ZENTRALE_NO_AUDIO="1",
               ZENTRALE_URL="http://127.0.0.1:%d" % srv.server_address[1],
               ZENTRALE_TUI_RAD=str(KALENDER_IM_RAD),
               ZENTRALE_TUI_FRAME_ERR_LOG=str(fehlerlog))
    for k in ("DISPLAY", "WAYLAND_DISPLAY", "ZENTRALE_TUI_RELOADED"):
        env.pop(k, None)

    def preexec():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    p = subprocess.Popen([PYBIN, "tui/zentrale_tui.py"], cwd=ROOT, stdin=slave,
                         stdout=slave, stderr=subprocess.DEVNULL, env=env,
                         close_fds=True, preexec_fn=preexec)
    os.close(slave)
    buf = bytearray()
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
    stuecke = {}
    try:
        time.sleep(2.5)
        os.write(master, b"\r")              # Kalender aus dem Rad öffnen
        time.sleep(1.2)
        for tasten, name in schritte:
            vorher = len(buf)
            os.write(master, tasten)
            time.sleep(1.2)
            stuecke[name] = _strip(bytes(buf[vorher:]).decode("utf-8", "replace"))
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
    fehler = fehlerlog.read_text() if fehlerlog.exists() else ""
    return stuecke, fehler


def test_v_dreht_durch_alle_ansichten_und_zurueck(tmp_path):
    s, fehler = _lauf(tmp_path, [(b"v", "A"), (b"v", "B"), (b"v", "C"),
                                 (b"v", "jetzt")])
    assert fehler == "", "eine Ansicht wirft beim Zeichnen:\n" + fehler
    assert "TERMINE" in s["A"].upper() and "KALENDER" in s["A"].upper()
    assert "KALENDER · OKTOBER 2026" in s["B"]
    import datetime as _dt
    assert "WOCHE %d" % _dt.date.today().isocalendar()[1] in s["C"].upper()
    assert "Woche" in s["jetzt"] or "Monat" in s["jetzt"], "zurück im jetzigen Kalender"
    # A/B holen Monats-, C Wochendaten über denselben /api/calendar
    views = {v for v, _r in ABFRAGEN}
    assert {"month", "week"} <= views


def test_blaettern_in_jeder_ansicht_wirft_nicht(tmp_path):
    rechts, links, null = b"\x1bOC", b"\x1bOD", b"0"
    s, fehler = _lauf(tmp_path, [
        (b"v" + rechts + rechts + links + null, "A"),
        (b"v" + rechts + links + b"x" + b"x", "B"),
        (b"v" + rechts + rechts + links + null, "C"),
    ])
    assert fehler == "", "Blättern wirft:\n" + fehler
    refs = [r for _v, r in ABFRAGEN]
    assert "2026-11-01" in refs, "A/B blättern monatsweise"


def test_tab_bleibt_woche_monat(tmp_path):
    s, fehler = _lauf(tmp_path, [(b"\t", "tab")])
    assert fehler == ""
    assert ("month", ) in {(v,) for v, _r in ABFRAGEN}
