"""
Lebenslauf + Hot Reload der TUI.

02.10.2026: ZENTRALE ging mitten in der Arbeit zu, ohne jede Spur — ein
Updater-Test hatte ihr ein SIGTERM geschickt. Seitdem schreibt die TUI jeden
Start, jedes Ende und jedes Signal (samt frisch gestarteter Prozesse) in ein
Log, das nie geloescht wird. Und Sasha wollte Hot Reload: neuer Code in tui/
ersetzt die laufende TUI per exec, das Fenster bleibt.

Gefahren wird eine KOPIE von tui/ + core/ in tmp_path — nie die Dateien des
Checkouts, sonst wuerde ein Test die echte ZENTRALE neu laden.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tui_fuzz import PYBIN, ROOT, _set_winsize, pty_supported  # noqa: E402

from tui import zentrale_tui as z  # noqa: E402
from tui.ansichten import befehle  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"logs": []} if self.path.startswith("/api/state")
                          else {}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_POST(self):
        self.do_GET()


class _Tui:
    """Eine TUI aus einer Kopie des Codes, im Pseudo-Terminal."""

    def __init__(self, tmp_path, extra_env=None):
        import fcntl
        import pty
        import termios
        self.code = tmp_path / "code"
        for d in ("tui", "core"):
            shutil.copytree(os.path.join(ROOT, d), self.code / d,
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.log = tmp_path / "tui.log"
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.master, slave = pty.openpty()
        _set_winsize(slave, 40, 140)
        env = dict(os.environ, TERM="xterm-256color", ZENTRALE_NO_AUDIO="1",
                   ZENTRALE_URL="http://127.0.0.1:%d" % self.srv.server_address[1],
                   ZENTRALE_TUI_LOG=str(self.log),
                   ZENTRALE_TUI_CRASH_LOG=str(tmp_path / "crash.log"))
        for k in ("DISPLAY", "WAYLAND_DISPLAY", "ZENTRALE_TUI_RELOADED",
                  "ZENTRALE_TUI_RAD", "ZENTRALE_TUI_OFFEN"):
            env.pop(k, None)
        env.update(extra_env or {})

        def preexec():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.p = subprocess.Popen([PYBIN, "tui/zentrale_tui.py"], cwd=str(self.code),
                                  stdin=slave, stdout=slave,
                                  stderr=subprocess.DEVNULL, env=env,
                                  close_fds=True, preexec_fn=preexec)
        os.close(slave)
        self._stop = threading.Event()
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self):
        import select
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([self.master], [], [], 0.2)
                if r:
                    os.read(self.master, 65536)
            except OSError:
                break

    def text(self):
        try:
            return self.log.read_text(encoding="utf-8")
        except OSError:
            return ""

    def warte(self, was, sekunden=12):
        ende = time.time() + sekunden
        while time.time() < ende:
            if was in self.text():
                return True
            time.sleep(0.2)
        return False

    def zu(self):
        self._stop.set()
        self.srv.shutdown()
        if self.p.poll() is None:
            self.p.kill()
            self.p.wait()
        try:
            os.close(self.master)
        except OSError:
            pass


@pytest.fixture
def tui(tmp_path):
    if not pty_supported():
        pytest.skip("braucht Linux-PTY mit Controlling-TTY")
    t = _Tui(tmp_path)
    yield t
    t.zu()


def _aendern(t, zusatz):
    pfad = t.code / "tui" / "zentrale_tui.py"
    with open(pfad, "a", encoding="utf-8") as f:
        f.write(zusatz)


def test_start_steht_im_lebenslauf(tui):
    assert tui.warte("START  frisch")


def test_sigterm_hinterlaesst_grund_und_verdaechtige(tui):
    assert tui.warte("START")
    time.sleep(1.0)
    tui.p.send_signal(signal.SIGTERM)
    tui.p.wait(timeout=10)
    log = tui.text()
    assert "SIGNAL SIGTERM" in log
    assert "kurz vorher gestartet" in log
    assert "ENDE  durch Signal 15" in log
    assert tui.p.returncode == 128 + 15


def test_hot_reload_bei_neuem_code(tui):
    assert tui.warte("START  frisch")
    time.sleep(1.5)
    _aendern(tui, "\n# hot-reload-probe\n")
    assert tui.warte("HOT RELOAD  neuer Code"), tui.text()
    assert tui.warte("START  neu geladen"), tui.text()
    assert tui.p.poll() is None, "exec ersetzt den Prozess, er stirbt nicht"


def test_kaputter_code_wird_nicht_geladen(tui):
    assert tui.warte("START  frisch")
    time.sleep(1.5)
    _aendern(tui, "\ndef kaputt(:\n")
    assert tui.warte("HOT RELOAD verworfen"), tui.text()
    assert "neu geladen" not in tui.text()
    assert tui.p.poll() is None, "die alte TUI laeuft weiter"


# ── reine Helfer ──────────────────────────────────────────────────────────

def test_lebenslauf_rotiert(tmp_path, monkeypatch):
    pfad = str(tmp_path / "l.log")
    monkeypatch.setattr(z, "LEBENSLAUF_MAX", 100)
    for i in range(20):
        z.lebenslauf("zeile %d" % i, pfad)
    assert os.path.exists(pfad + ".1")
    assert os.path.getsize(pfad) < 400


def test_lebenslauf_wirft_nie(tmp_path):
    z.lebenslauf("x", "/proc/gibtsnicht/l.log")      # kein Fehler


def test_code_fehler_findet_syntaxfehler(tmp_path):
    gut = tmp_path / "a.py"
    gut.write_text("x = 1\n")
    assert z.code_fehler([str(gut)]) is None
    schlecht = tmp_path / "b.py"
    schlecht.write_text("def (:\n")
    assert z.code_fehler([str(gut), str(schlecht)]).startswith("b.py:1")


def test_frische_prozesse_findet_einen_frischen():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        time.sleep(0.3)
        assert p.pid in {pid for pid, _ in z.frische_prozesse(10)}
    finally:
        p.kill()
        p.wait()


def test_reload_befehl():
    action, _m, _msg = befehle.parse_command("/reload", "auto")
    assert action == "RELOAD"


def test_hot_reload_behaelt_die_offene_app(tmp_path):
    """Sasha, 08.10.2026: nach dem Neuladen landete man auf der Startseite.
    Jetzt: Kalender offen → nach dem Hot Reload wieder offen."""
    if not pty_supported():
        pytest.skip("braucht Linux-PTY mit Controlling-TTY")
    t = _Tui(tmp_path, extra_env={"ZENTRALE_TUI_RAD": "2"})
    try:
        assert t.warte("START  frisch")
        time.sleep(1.5)
        os.write(t.master, b"\r")          # Kalender aus dem Rad öffnen
        time.sleep(1.5)
        _aendern(t, "\n# hot-reload-probe-app\n")
        assert t.warte("HOT RELOAD  neuer Code"), t.text()
        assert t.warte("wieder offen: c"), t.text()
    finally:
        t.zu()
