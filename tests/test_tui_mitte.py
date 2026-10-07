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


def _lauf(tasten=b"", nach=1.5):
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
        time.sleep(nach)
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


def _befehle():
    from tui.ansichten import befehle
    return befehle


def _rad():
    """Geometrie von Rad und Galaxie — seit 06.10.2026 in tui/ansichten/startseite.py
    (memory/system/tui_bauplan.md)."""
    from tui.ansichten import startseite
    return startseite


def test_der_kasten_heisst_zentrale(schirm):
    assert "ZENTRALE" in schirm
    assert "ZENTRALE · AI" not in schirm     # der KI-Kasten ist weg


def test_vorn_steht_die_erste_app(schirm):
    # mit Farben klappt vorn das Pixel-Symbol auf (Schriftzug KLAVIER)
    assert "KLAVIER" in schirm or "K L A V I E R" in schirm


def test_die_nachbarn_stehen_daneben(schirm):
    for was in ("post", "tutor"):
        assert was in schirm, was


def test_keine_buchstaben_leiste_mehr(schirm):
    assert "weglegen" not in schirm
    assert "q weglegen" not in schirm
    assert "space ki" in schirm


def test_pfeil_rechts_dreht_weiter():
    """Pfeil rechts dreht direkt das gewählte App-Rad -> post steht vorn."""
    schirm = _lauf(b"\x1bOC")
    assert "POST" in schirm or "P O S T" in schirm


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
    m = _rad()
    assert _vorn(m.rad_zeilen(NAMEN, 0, 70, 30)) == ["K L A V I E R"]
    assert _vorn(m.rad_zeilen(NAMEN, 1, 70, 30)) == ["P O S T"]
    assert _vorn(m.rad_zeilen(NAMEN, 5, 70, 30)) == ["P O S T"]   # zweite runde
    assert _vorn(m.rad_zeilen(NAMEN, -1, 70, 30)) == ["F O K U S"]


def test_im_drehen_kein_rahmen():
    """Zwischen zwei Apps steht keine vorn — sonst springt der Rahmen."""
    zeilen = _rad().rad_zeilen(NAMEN, 0.5, 70, 30)
    assert not [z for z in zeilen if z[3] in ("vorn", "rahmen")]


def test_vorn_ist_unten_hinten_ist_oben():
    """Das Rad liegt und wird leicht von oben gesehen."""
    zeilen = _rad().rad_zeilen(["a", "b", "c", "d", "e", "f", "g", "h"],
                                 0, 70, 30)
    vorn = next(z for z in zeilen if z[3] == "vorn")
    fern = [z for z in zeilen if z[3] == "fern"]
    assert fern and all(f[0] < vorn[0] for f in fern)


def test_rad_bleibt_in_der_breite():
    for breite in (40, 60, 71, 120):
        for dy, dx, t, _st in _rad().rad_zeilen(NAMEN, 0, breite, 30):
            assert -breite // 2 < dx and dx + len(t) <= breite // 2, (breite, t)


def test_zu_schmal_kein_rad():
    assert _rad().rad_zeilen(NAMEN, 0, 20, 30) == []


def test_rad_gleitet_und_rastet_ein():
    m = _rad()
    pos = 0.0
    for _ in range(40):
        pos = m.rad_schritt(pos, 1)
    assert pos == 1.0


# ── Pixel-Symbole im Rad (elektronik) ───────────────────────────────────

def test_symbol_app_ist_hinten_eine_pille_und_vorn_ein_symbol():
    m = _rad()
    namen = ["klavier", "post", "kalender", "elektronik"]
    zeilen = m.rad_zeilen(namen, 0, 70, 30, {"elektronik": 0.0})
    pillen = [z for z in zeilen if z[3] in ("pille", "pille_fern")]
    assert pillen and pillen[0][2] == " elektronik "
    vorn = m.rad_zeilen(namen, 3, 70, 30, {"elektronik": 0.0})
    assert [z for z in vorn if z[3] == "symbol:elektronik"]
    assert not [z for z in vorn if z[3] in ("vorn", "rahmen")]


def test_symbol_bleibt_beim_wegdrehen_bis_es_zu_ist():
    m = _rad()
    namen = ["klavier", "post", "kalender", "elektronik"]
    zeilen = m.rad_zeilen(namen, 3.4, 70, 30, {"elektronik": 0.5})
    assert [z for z in zeilen if z[3] == "symbol:elektronik"]


def test_ohne_symbole_bleibt_alles_wie_es_war():
    m = _rad()
    alt = m.rad_zeilen(NAMEN, 0, 70, 30)
    assert alt == m.rad_zeilen(NAMEN, 0, 70, 30, None)


def test_klappen_auf_schnell_und_zu_noch_schneller():
    m = _rad()
    o = 0.0
    for _ in range(8):                 # 8 Frames à 33 ms ≈ 0,26 s
        o = m.rad_offen_schritt(o, True, 0.033)
    assert o == 1.0
    for _ in range(6):                 # ≈ 0,2 s
        o = m.rad_offen_schritt(o, False, 0.033)
    assert o == 0.0


# ── Die Galaxie (seit 03.10.2026) ──────────────────────────────────────
# Sasha: *„das ganze eine galaxie [...] das technikwheel ein sonnensystem,
# genauso wie das andere rad auch [...] beide die in der galaxie zusammen
# rotieren"* — EINE Fläche; die Bahn so riesig, *„dass man es eigentlich
# gar nich richtig sieht"*: die beiden liegen nebeneinander, ←/→ wechselt.

def test_startseite_ist_eine_galaxie(schirm):
    assert "✦ APPS" in schirm                                 # apps gewählt, mittig
    assert "KLAVIER" in schirm or "K L A V I E R" in schirm
    assert "netz" in schirm                  # technik liegt angeschnitten am Rand
    assert "LIFESTYLE" not in schirm         # die Seitenspalten sind weg
    assert "alt+←→ rad wechseln" in schirm


def test_alt_pfeil_rechts_waehlt_technik():
    assert "✦ TECHNIK" in _lauf(b"\x1b[1;3C", nach=2.5)   # die Galaxie dreht 1,6 s


def test_pfeil_allein_wechselt_das_rad_nicht():
    assert "✦ TECHNIK" not in _lauf(b"\x1bOC")


def test_galaxie_gewaehltes_mittig_anderes_draussen():
    """Sasha: das nicht gewählte Rad etwas weiter weg, darf abgeschnitten
    sein — das gewählte steht mittig."""
    m = _rad()
    breiten = (0.55, 0.36)
    for gpos in (0, 1):
        lage = {i: (q, n) for i, q, n in m.galaxie_lage(gpos, breiten)}
        assert lage[gpos] == (0.0, 1.0)                     # gewählt: Mitte
        q, n = lage[1 - gpos]
        assert n == 0.0
        assert abs(q) + breiten[1 - gpos] > 1               # ragt aus dem Bild
        assert abs(q) - breiten[1 - gpos] < 1               # … aber nicht ganz
    halb = [q for _, q, _ in m.galaxie_lage(0.5, breiten)]
    assert halb[0] < 0 < halb[1]                            # im Gleiten dazwischen


def test_technik_rad_oeffnet_die_systemansicht():
    schirm = _lauf(b"\x1b[1;3C\r")
    assert "TECHNIK · SYSTEM" in schirm
    assert "EXTERNAL" in schirm and "TELEMETRIE" in schirm


def test_dashboard_an_holt_die_alten_spalten_zurueck(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_DASHBOARD_FILE", str(tmp_path / "dashboard"))
    schirm = _lauf(b"/dashboard an\r")
    assert "LIFESTYLE" in schirm and "OUTBOUND" in schirm
    assert (tmp_path / "dashboard").read_text().strip() == "an"


def test_meta_taste_waehlt_dreht_und_oeffnet():
    m = _rad()
    meta, rad, trad = {"gsel": 0, "fokus": 0}, {"sel": 0}, {"sel": 0}
    m.meta_taste(meta, rad, trad, "rechts")
    assert rad["sel"] == 1 and meta["fokus"] == 0       # pfeil dreht direkt
    assert m.meta_taste(meta, rad, trad, "alt_rechts") is None
    assert meta["fokus"] == 1 and meta["gsel"] == 1     # alt+pfeil wechselt das rad
    m.meta_taste(meta, rad, trad, "rechts")
    assert trad["sel"] == 1 and rad["sel"] == 1         # dreht nur das gewählte
    assert m.meta_taste(meta, rad, trad, "enter") == ("technik", m.TECH_APPS[1][0])
    m.meta_taste(meta, rad, trad, "alt_links")
    assert m.meta_taste(meta, rad, trad, "enter") == ("app", m.RAD_APPS[1][0])


def test_dashboard_befehl():
    befehle = _befehle()
    assert befehle.parse_command("/dashboard an", "auto")[0] == "DASH_ON"
    assert befehle.parse_command("/dashboard aus", "auto")[0] == "DASH_OFF"
    assert befehle.parse_command("/dashboard", "auto")[0] == "DASH_TOGGLE"


def test_galaxie_dreht_schwer_und_rollt_weich_aus():
    """Sasha: *„smoother und schwerfälliger, schließlich ist das ne giga
    galaxie die dreht"* — träge Anfahrt, weiches Ende, exakt am Ziel."""
    m = _rad()
    d = m.GALAXIE_DAUER
    assert d >= 1.2                                        # schwer, kein Zucken
    assert m.galaxie_schritt(0, 1, 0) == 0.0
    assert m.galaxie_schritt(0, 1, d) == 1.0
    assert abs(m.galaxie_schritt(0, 1, d / 2) - 0.5) < 1e-9
    anfang = m.galaxie_schritt(0, 1, d * 0.1)
    mitte = m.galaxie_schritt(0, 1, d * 0.55) - m.galaxie_schritt(0, 1, d * 0.45)
    assert anfang < 0.03 and mitte > 3 * anfang            # langsam los, dann zügig
    werte = [m.galaxie_schritt(1, 0, d * k / 20) for k in range(21)]
    assert werte == sorted(werte, reverse=True)            # nie zurückzucken


# ── Schleuder-Gag ───────────────────────────────────────────────────────
# Sasha: *„wenn man die pfeiltaste zulange gedrückt hält [...] dass die app
# symbole dann irgendwann voll rausfliegen (resetted sich dann wenn man das
# wheel kurz in ruhe lässt)"*

def _schwung(m, druecke_pro_s, sekunden, fps=30):
    """Höchster Schwung bei so vielen Drücken pro Sekunde."""
    dt, t, naechster, schwung, hoch = 1 / fps, 0.0, 0.0, 0.0, 0.0
    while t < sekunden:
        if t >= naechster:
            schwung += 1
            naechster += 1 / druecke_pro_s
        schwung = m.schwung_schritt(schwung, dt)
        hoch = max(hoch, schwung)
        t += dt
    return hoch


def test_normales_tippen_schleudert_nie():
    m = _rad()
    assert _schwung(m, 5, 10) < m.SCHLEUDER_AB


def test_gehaltene_taste_reisst_nach_rund_einer_sekunde_ab():
    m = _rad()
    assert _schwung(m, 30, 0.5) < m.SCHLEUDER_AB
    assert _schwung(m, 30, 2.0) > m.SCHLEUDER_AB


def test_wurf_alle_auf_einmal_und_geradeaus():
    """Alle Apps reissen im selben Moment ab und fliegen auf einer GERADEN
    weg — kein grösserer Kreis."""
    m = _rad()
    teile = m.schleuder_wurf(NAMEN, 0, 1, 70, 30)
    assert [t[0] for t in teile] == NAMEN                  # alle zugleich
    for name, y, x, vy, vx in teile:
        assert (vx, vy) != (0, 0)
        p0, p1, p2 = [(y + vy * t, x + vx * t) for t in (0.0, 0.5, 1.0)]
        kreuz = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
        assert abs(kreuz) < 1e-9, name                      # kollinear = gerade
    vorn = teile[0]                                         # klavier steht vorn (unten)
    assert vorn[4] < 0 and abs(vorn[3]) < 1e-9              # dreht nach links → fliegt links weg
    assert m.schleuder_wurf(NAMEN, 0, -1, 70, 30)[0][4] > 0  # andersrum → rechts


def test_wurf_zeilen_entfernen_sich_mit_der_zeit():
    m = _rad()
    teile = m.schleuder_wurf(NAMEN, 0, 1, 70, 30)
    nah, fern = m.wurf_zeilen(teile, 0.0), m.wurf_zeilen(teile, 1.0)
    weite = lambda zs: max(abs(dx) for _dy, dx, _t, _st in zs)  # noqa: E731
    assert weite(fern) > weite(nah) + 30



# ── Pixel-Symbole für alle Apps (03.10.2026) ────────────────────────────
# Sasha: *„im gleichen pixel art style ein neues symbol für die anderen apps
# auch. überasch einfach mal, für post [...] nen brief, für karte nen globus"*

def _pixel():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_tui_pixel", os.path.join(ROOT, "tui", "pixel.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_jede_app_im_rad_hat_ein_symbol():
    m, px = _rad(), _pixel()
    for _taste, name in m.RAD_APPS:
        assert name in m.RAD_SYMBOLE
        assert name == "elektronik" or name in px.MOTIVE, name


def test_symbole_in_allen_stufen_und_farben():
    px = _pixel()
    for name in list(px.MOTIVE) + ["elektronik"]:
        for farben in ("nacht", "tag"):
            for offen in (0.0, 0.02, 0.3, 0.7, 1.0):
                zeilen, schrift = px.symbol_zellen(name, offen, 1200, farben, "mix")
                assert len(zeilen) == px.EL_H and all(len(z) == px.EL_W for z in zeilen)
                if offen < .5:
                    assert not schrift                  # zu: noch kein Schriftzug
            text = "".join(ch for _c, ch, _f, _b in schrift)
            assert text == name.upper(), (name, text)   # offen: Name auf der Platte
            grund, farbe = px.symbol_pille(name, False, farben)
            assert grund != farbe


def test_ruhe_animation_bewegt_sich():
    """Offen lebt jedes Symbol ein bisschen (Globus dreht, Taste leuchtet …)."""
    px = _pixel()
    for name in px.MOTIVE:
        bilder = {str(px.symbol_pixel(name, 1.0, t, "nacht")) for t in range(0, 3000, 150)}
        assert len(bilder) > 1, name


def test_pillen_bleiben_farbig_und_karte_ist_gruen():
    """Sasha, 04.10.2026: weggedrehte Pillen wurden grau; die Karte soll grün."""
    px = _pixel()
    grau = {16, 59, 102, 145, 188, 231} | set(range(232, 256))
    for name in list(px.MOTIVE) + ["elektronik"]:
        for farben in ("nacht", "tag"):
            for fern in (False, True):
                grund, _ = px.symbol_pille(name, fern, farben)
                assert px.rgb_256(grund) not in grau, (name, farben, fern)
    r, g, b = px.symbol_pille("karte", False, "nacht")[0]
    assert g > r and g > b


# ── Das Auge der KI ─────────────────────────────────────────────────────
# Sasha: *„wenn man dann leertaste die ki aufmacht mach ein großes
# animiertes auge in die mitte im stil der app icons"*

def test_auge_hat_seine_groesse_und_lebt():
    px = _pixel()
    zeilen = px.auge_zellen(1.0, 300, False, "nacht", "mix")
    assert len(zeilen) == px.AUGE_H and all(len(z) == px.AUGE_W for z in zeilen)
    zustaende = {px.auge_zustand(1.0, t) for t in range(0, 12000, 60)}
    assert {z[0] for z in zustaende} > {1.0}                 # es blinzelt
    assert len({(z[1], z[2]) for z in zustaende}) > 2         # es schaut sich um
    assert px.auge_zustand(0.0, 0)[0] == 0.0                  # beim Öffnen zu …
    assert px.auge_zustand(1.0, 1000)[0] == 1.0               # … dann auf


def test_auge_denkt():
    px = _pixel()
    ruhig = px.auge_pixel(1.0, 900, False, "nacht")
    denkt = px.auge_pixel(1.0, 900, True, "nacht")
    assert ruhig != denkt
    assert len({px.auge_zustand(1.0, t, True)[3:] for t in range(0, 3000, 50)}) > 3


def test_ki_chat_zeigt_das_auge():
    schirm = _lauf(b" ")
    assert "frag die ki" in schirm
    assert any(chr(c) in schirm for c in range(0x1FB00, 0x1FB3C))   # Sextanten = Pixelbild
