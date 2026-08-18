"""Die stdout-Laufschrift muss im SCHMALEN Pane wirklich alles hergeben.

Der Fall: in einem kleinen tmux-Pane ist die stdout-Spalte ~28 Zeichen breit.
Eine Log-Zeile mit 70 Zeichen wurde dort hart abgeschnitten — das Ende hat man
nie gesehen. Jetzt läuft sie durch.

Der Test startet die ECHTE TUI im Pseudo-Terminal gegen ein Mini-Backend, das
auf /api/state EINE sehr lange Log-Zeile liefert, und liest ab, was wirklich
über den Schirm geht: das Wort ganz am ENDE der Zeile muss auftauchen (mit
Lauf) bzw. ausbleiben (ohne Lauf).
"""
import os
import sys
import re
import json
import time
import signal
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tui_fuzz import pty_supported, _set_winsize, PYBIN, ROOT  # noqa: E402

pytestmark = pytest.mark.skipif(
    not pty_supported(), reason="braucht Linux-PTY mit Controlling-TTY")

# Vorne ein bekanntes Präfix (das sieht man auch abgeschnitten), hinten eine
# Marke, die NUR durch Durchlaufen sichtbar wird.
ANFANG = "TOOL kalender eintragen"
ENDE = "ZIELMARKE"
LANG = ANFANG + " zahnarzt dienstag vierzehn uhr " + ENDE


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
        if self.path.startswith("/api/state"):
            self._json({"logs": [{"time": "12:00:00", "text": LANG}]})
            return
        self._json({})

    def do_POST(self):
        try:
            ln = int(self.headers.get("Content-Length", 0))
            self.rfile.read(ln)
        except (ValueError, OSError):
            pass
        self._json({})


def _strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][B0]|\x1b[=>]", "", s)


def _lauf(wunsch, tmp_path, sekunden=6.0):
    """TUI mit gesetztem Lauf-Wunsch starten → alles, was über den Schirm ging."""
    import pty, fcntl, termios, select

    pfad = tmp_path / "stdout_lauf"
    pfad.write_text(wunsch + "\n", encoding="utf-8")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]

    master, slave = pty.openpty()
    _set_winsize(slave, 30, 100)             # linke Spalte = 28 Zeichen
    env = dict(os.environ, TERM="xterm-256color", ZENTRALE_URL=url,
               ZENTRALE_NO_AUDIO="1",
               ZENTRALE_LAUF_FILE=str(pfad),
               ZENTRALE_LAUF_TAKT="0.03")    # im Test rennt die Schrift
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    def preexec():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    p = subprocess.Popen([PYBIN, "tui/zentrale_tui.py"], cwd=ROOT,
                         stdin=slave, stdout=slave, stderr=subprocess.DEVNULL,
                         env=env, close_fds=True, preexec_fn=preexec)
    os.close(slave)
    buf = bytearray()
    stop = threading.Event()

    def drain():
        while not stop.is_set():
            try:
                r, _, _ = select.select([master], [], [], 0.2)
                if r:
                    buf.extend(os.read(master, 65536))
            except OSError:
                break

    threading.Thread(target=drain, daemon=True).start()
    try:
        time.sleep(sekunden)
        text = _strip_ansi(bytes(buf).decode("utf-8", "replace"))
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
    return text


def test_lange_zeile_laeuft_bis_zum_ende_durch(tmp_path):
    text = _lauf("an", tmp_path)
    assert ANFANG[:12] in text, "die Zeile stand nie am Anfang"
    assert ENDE in text, "das Ende der Log-Zeile kam nie zum Vorschein"


def test_ausgeschaltet_bleibt_es_beim_ehrlichen_schnitt(tmp_path):
    text = _lauf("aus", tmp_path)
    assert ANFANG[:12] in text, "ohne Lauf muss der Anfang trotzdem stehen"
    assert ENDE not in text, "aus heißt aus — da darf nichts wandern"
