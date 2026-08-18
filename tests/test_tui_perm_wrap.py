"""Die Erlaubnis-Frage der KI muss auch im SCHMALEN Fenster ganz lesbar sein.

Der Fall: die KI ruft `frage_knopf`, die TUI zeigt Frage + Knöpfe unten im
Chat-Kasten. Früher wurde beides hart auf die Kastenbreite gekürzt — in einem
schmalen Terminal stand da ein halber Satz, und man klickte blind auf einen
Knopf. Jetzt wird umgebrochen (und der Verlauf gibt den Platz her).

Der Test startet die ECHTE TUI im Pseudo-Terminal gegen ein Mini-Backend, das
auf /api/chat eine lange Frage mit langen Optionen streamt, und liest ab, was
wirklich auf dem Schirm landet.
"""
import os
import sys
import re
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tui_fuzz import pty_supported, _set_winsize, PYBIN, ROOT  # noqa: E402

pytestmark = pytest.mark.skipif(
    not pty_supported(), reason="braucht Linux-PTY mit Controlling-TTY")

FRAGE = ("darf ich den termin zahnarzt am dienstag um vierzehn uhr "
         "wirklich ganz aus dem kalender loeschen")
OPTIONEN = ["ja bitte loeschen", "nein lieber behalten", "erst anzeigen"]


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
        self._json({})

    def do_POST(self):
        try:
            ln = int(self.headers.get("Content-Length", 0))
            self.rfile.read(ln)
        except (ValueError, OSError):
            pass
        if not self.path.startswith("/api/chat"):
            self._json({})
            return
        # SSE: Erlaubnis-Frage schicken und den Stream offen halten — genau so
        # wartet das echte Backend auf die Antwort.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        evt = {"permission": {"frage": FRAGE, "optionen": OPTIONEN}}
        try:
            self.wfile.write(("data: " + json.dumps(evt) + "\n\n").encode())
            self.wfile.flush()
            for _ in range(120):                 # ~12 s offen halten
                time.sleep(0.1)
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except OSError:
            pass


def _strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][B0]|\x1b[=>]", "", s)


def _run(rows, cols):
    """TUI im PTY starten, Chat öffnen, Frage abschicken → Bildschirmtext."""
    import pty, fcntl, termios, select, signal, subprocess
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]

    master, slave = pty.openpty()
    _set_winsize(slave, rows, cols)
    env = dict(os.environ, TERM="xterm-256color", ZENTRALE_URL=url,
               ZENTRALE_NO_AUDIO="1")
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
        time.sleep(2.5)                      # erster Frame
        os.write(master, b"a")               # KI-Chat auf
        time.sleep(0.6)
        os.write(master, b"hallo\r")         # Frage senden → Stream läuft
        time.sleep(2.5)
        # curses zeichnet nur Änderungen — ein Resize erzwingt einen VOLLEN
        # Frame, sonst steht die Frage nur im (längst vergangenen) Delta.
        _set_winsize(master, rows, cols - 1)
        time.sleep(0.8)
        del buf[:]                           # ab hier nur noch der letzte Frame
        _set_winsize(master, rows, cols)
        time.sleep(1.5)
        text = _strip_ansi(bytes(buf).decode("utf-8", "replace"))
    finally:
        stop.set()
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
        srv.shutdown()
    return text


@pytest.mark.parametrize("rows,cols", [(30, 62), (24, 80), (40, 100)])
def test_frage_und_knoepfe_werden_umgebrochen_statt_abgeschnitten(rows, cols):
    text = _run(rows, cols)
    fehlt = [w for w in FRAGE.split() if w not in text]
    assert not fehlt, ("abgeschnitten bei %dx%d — fehlende wörter: %s"
                       % (rows, cols, fehlt))
    for opt in OPTIONEN:                     # jeder Knopf muss lesbar sein
        fehlt_o = [w for w in opt.split() if w not in text]
        assert not fehlt_o, ("knopf %r unvollständig bei %dx%d: %s"
                             % (opt, rows, cols, fehlt_o))
    # und der Verlauf darf dabei nicht verschwinden (Fuß frisst nur, was er braucht)
    assert "du: hallo" in text, "verlauf weg bei %dx%d" % (rows, cols)
