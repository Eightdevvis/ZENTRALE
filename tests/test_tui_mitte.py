"""
Die Mitte gehoert ZENTRALE selbst.

Sasha, 20.08.2026: *„die ganzen befehle die in der mitte stehen rutschen
einfach in die leiste unten. in der mitte bleibt stehen zentrale ai. sie
zeigt sich als einen mit ascii gezeichneten ring."*

Geprueft wird an der ECHTEN TUI im Pseudo-Terminal — was wirklich ueber den
Schirm geht. Ein Zeichen-Zweig laesst sich nicht sinnvoll stueckweise
testen: er faellt erst zur Laufzeit um, und dann steht der Kasten leer da,
ohne dass irgendein Test etwas gemerkt haette.

Die reine Ring-Mathematik steht in test_tui_helpers.py.
"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tui_fuzz import PYBIN, ROOT, _set_winsize, pty_supported  # noqa: E402

pytestmark = pytest.mark.skipif(
    not pty_supported(), reason="braucht Linux-PTY mit Controlling-TTY")


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
        self._json({} if not self.path.startswith("/api/state")
                   else {"logs": []})

    def do_POST(self):
        try:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
        except (ValueError, OSError):
            pass
        self._json({})


def _strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][B0]|\x1b[=>]", "", s)


@pytest.fixture(scope="module")
def schirm():
    """Die TUI kurz laufen lassen -> alles, was ueber den Schirm ging."""
    import fcntl
    import pty
    import select
    import termios

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % srv.server_address[1]

    master, slave = pty.openpty()
    _set_winsize(slave, 40, 140)
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
        time.sleep(4.0)
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


def test_in_der_mitte_steht_sie_selbst(schirm):
    assert "ZENTRALE · AI" in schirm      # Kasten-Titel (draw_box schreibt gross)


def test_kein_name_im_ring(schirm):
    """Sasha, 20.08.2026: der Name mittendrin kann weg. Der Kasten heisst
    schon so, und der kleine Ring soll fuer sich stehen."""
    assert "zentrale ai" not in schirm


def test_der_ring_wird_gezeichnet(schirm):
    """WELCHES Zeichen es ist, haengt von der Lage ab — und die haengt an
    der Maschine, auf der der Test laeuft. Gezaehlt wird deshalb ueber alle
    Ring-Zeichen; ein Test, der eine bestimmte Lage erzwingen will, wuerde
    auf dem naechsten Rechner grundlos rot."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_tui", os.path.join(ROOT, "tui", "zentrale_tui.py"))
    modul = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(modul)
    except SystemExit:
        pass
    treffer = sum(schirm.count(g) for g in set(modul.RING_GLYPHEN.values()))
    assert treffer > 15


def test_der_ring_bleibt_ein_zeichen_kein_rahmen():
    """Ein Drittel dessen, was passen wuerde. Der Kasten hat schon einen
    Rahmen; ein zweiter, der ihn fast ausfuellt, ist keiner mehr."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_tui2", os.path.join(ROOT, "tui", "zentrale_tui.py"))
    modul = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(modul)
    except SystemExit:
        pass
    h, w = 34, 69
    punkte = modul.ring_punkte(h, w)
    hoehe = max(p[0] for p in punkte) - min(p[0] for p in punkte)
    assert hoehe < (h - 2) // 2


def test_die_befehle_stehen_nicht_mehr_in_der_mitte(schirm):
    """Was frueher mittig stand ('KASSETTE · TUI' und die Einladungsliste)."""
    assert "KASSETTE" not in schirm
    assert "g · graph-werkzeug" not in schirm


def test_die_befehle_stehen_jetzt_unten(schirm):
    """Und zwar VOLLSTAENDIG. Die alte Fussleiste trug nur eine Auswahl —
    fokus, notizen, post und klavier fehlten dort."""
    for was in ("fokus", "notizen", "graph", "karte", "kalender",
                "post", "ki", "tutor", "klavier", "beenden"):
        assert was in schirm, was


def test_beenden_steht_vorn(schirm):
    """Die Leiste wird bei schmalem Fenster hinten abgeschnitten. Stand 'q
    beenden' am Ende, fiel ausgerechnet die Taste weg, die man sucht, wenn
    man nicht mehr weiterweiss."""
    zeile = next(z for z in schirm.splitlines() if "fokus" in z and "graph" in z)
    assert zeile.index("beenden") < zeile.index("fokus")


def test_die_leiste_traegt_ihren_zustand_mit(schirm):
    """Theme und Laufschrift sind keine Tasten-Namen, sondern Anzeigen —
    wer sie umschaltet, will sehen, was jetzt gilt."""
    assert re.search(r"theme[^·]*:", schirm)
    assert re.search(r"lauf[^·]*:", schirm)


def test_die_leiste_passt_in_ein_schmales_fenster(schirm):
    """140 Spalten sind nicht viel — im Scratchpad-Fenster ist es enger.
    Passt sie nicht, faellt hinten etwas ab, und man merkt es nicht."""
    zeile = next(z for z in schirm.splitlines() if "fokus" in z and "graph" in z)
    assert "theme:" in zeile, "der Theme-Zustand fiel hinten ab"
