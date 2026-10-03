"""
Die Startseite ist ein Rad.

Sasha, 02.10.2026: *„statt fett in der mitte ki zu haben und unten shortcuts
mit denen man in die apps kommt soll mittig so eine ansicht sein, durch die
man durchroutieren kann. [...] ki aktiviert man nur noch mit leertaste
direkt. die anderen shortcuts fallen alle weg. zurück zu home kommt man
durch esc. mach das wheel nich ganz mittig, leicht unten."*

Geprueft wird an der ECHTEN TUI im Pseudo-Terminal — was wirklich ueber den
Schirm geht. Ein Zeichen-Zweig laesst sich nicht sinnvoll stueckweise
testen: er faellt erst zur Laufzeit um, und dann steht der Kasten leer da,
ohne dass irgendein Test etwas gemerkt haette.

Die reine Rad-Mathematik steht weiter unten, ohne Terminal.
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


def _lauf(tasten=b""):
    """Die TUI kurz laufen lassen, nach 2 s `tasten` schicken
    -> alles, was ueber den Schirm ging."""
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
        time.sleep(2.5)
        if tasten:
            os.write(master, tasten)
        time.sleep(1.5)
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


@pytest.fixture(scope="module")
def schirm():
    return _lauf()


def _modul():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_tui_rad", os.path.join(ROOT, "tui", "zentrale_tui.py"))
    modul = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(modul)
    except SystemExit:
        pass
    return modul


def test_der_kasten_heisst_zentrale(schirm):
    assert "ZENTRALE" in schirm
    assert "ZENTRALE · AI" not in schirm     # der KI-Kasten ist weg


def test_vorn_steht_die_erste_app(schirm):
    assert "K L A V I E R" in schirm


def test_die_nachbarn_stehen_daneben(schirm):
    for was in ("post", "tutor"):
        assert was in schirm, was


def test_keine_buchstaben_leiste_mehr(schirm):
    assert "weglegen" not in schirm
    assert "q weglegen" not in schirm
    assert "space ki" in schirm


def test_pfeil_rechts_dreht_weiter():
    """Pfeil rechts -> post steht vorn."""
    assert "P O S T" in _lauf(b"\x1bOC")


def test_pfeil_links_dreht_rueckwaerts_ueber_den_anfang():
    """Vom klavier nach links landet man hinten bei der letzten App
    (seit 03.10.2026 elektronik), nicht am Rand. Mit Farben klappt dort das
    Pixel-Symbol auf (Schriftzug ELEKTRONIK), ohne den gewohnten Rahmen."""
    schirm = _lauf(b"\x1bOD")
    assert "ELEKTRONIK" in schirm or "E L E K T R O N I K" in schirm


# ── reine Rad-Mathematik ────────────────────────────────────────────────

NAMEN = ["klavier", "post", "kalender", "fokus"]


def _vorn(zeilen):
    return [t for _dy, _dx, t, st in zeilen if st == "vorn"]


def test_rad_zeigt_vorn_die_gewaehlte():
    m = _modul()
    assert _vorn(m.rad_zeilen(NAMEN, 0, 70, 30)) == ["K L A V I E R"]
    assert _vorn(m.rad_zeilen(NAMEN, 1, 70, 30)) == ["P O S T"]
    assert _vorn(m.rad_zeilen(NAMEN, 5, 70, 30)) == ["P O S T"]   # zweite runde
    assert _vorn(m.rad_zeilen(NAMEN, -1, 70, 30)) == ["F O K U S"]


def test_im_drehen_kein_rahmen():
    """Zwischen zwei Apps steht keine vorn — sonst springt der Rahmen."""
    zeilen = _modul().rad_zeilen(NAMEN, 0.5, 70, 30)
    assert not [z for z in zeilen if z[3] in ("vorn", "rahmen")]


def test_vorn_ist_unten_hinten_ist_oben():
    """Das Rad liegt und wird leicht von oben gesehen."""
    zeilen = _modul().rad_zeilen(["a", "b", "c", "d", "e", "f", "g", "h"],
                                 0, 70, 30)
    vorn = next(z for z in zeilen if z[3] == "vorn")
    fern = [z for z in zeilen if z[3] == "fern"]
    assert fern and all(f[0] < vorn[0] for f in fern)


def test_rad_bleibt_in_der_breite():
    for breite in (40, 60, 71, 120):
        for dy, dx, t, _st in _modul().rad_zeilen(NAMEN, 0, breite, 30):
            assert -breite // 2 < dx and dx + len(t) <= breite // 2, (breite, t)


def test_zu_schmal_kein_rad():
    assert _modul().rad_zeilen(NAMEN, 0, 20, 30) == []


def test_rad_gleitet_und_rastet_ein():
    m = _modul()
    pos = 0.0
    for _ in range(40):
        pos = m.rad_schritt(pos, 1)
    assert pos == 1.0


def test_der_ring_bleibt_ein_zeichen_kein_rahmen():
    """Ring-Helfer (heute nicht auf der Startseite) bleiben heil."""
    m = _modul()
    h, w = 34, 69
    punkte = m.ring_punkte(h, w)
    hoehe = max(p[0] for p in punkte) - min(p[0] for p in punkte)
    assert hoehe < (h - 2) // 2


# ── Pixel-Symbole im Rad (elektronik) ───────────────────────────────────

def test_symbol_app_ist_hinten_eine_pille_und_vorn_ein_symbol():
    m = _modul()
    namen = ["klavier", "post", "kalender", "elektronik"]
    zeilen = m.rad_zeilen(namen, 0, 70, 30, {"elektronik": 0.0})
    pillen = [z for z in zeilen if z[3] in ("pille", "pille_fern")]
    assert pillen and pillen[0][2] == " elektronik "
    vorn = m.rad_zeilen(namen, 3, 70, 30, {"elektronik": 0.0})
    assert [z for z in vorn if z[3] == "symbol:elektronik"]
    assert not [z for z in vorn if z[3] in ("vorn", "rahmen")]


def test_symbol_bleibt_beim_wegdrehen_bis_es_zu_ist():
    m = _modul()
    namen = ["klavier", "post", "kalender", "elektronik"]
    zeilen = m.rad_zeilen(namen, 3.4, 70, 30, {"elektronik": 0.5})
    assert [z for z in zeilen if z[3] == "symbol:elektronik"]


def test_ohne_symbole_bleibt_alles_wie_es_war():
    m = _modul()
    alt = m.rad_zeilen(NAMEN, 0, 70, 30)
    assert alt == m.rad_zeilen(NAMEN, 0, 70, 30, None)


def test_klappen_auf_schnell_und_zu_noch_schneller():
    m = _modul()
    o = 0.0
    for _ in range(8):                 # 8 Frames à 33 ms ≈ 0,26 s
        o = m.rad_offen_schritt(o, True, 0.033)
    assert o == 1.0
    for _ in range(6):                 # ≈ 0,2 s
        o = m.rad_offen_schritt(o, False, 0.033)
    assert o == 0.0
