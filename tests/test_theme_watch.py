"""
Theme-Beobachter (scripts/zentrale-theme-watch).

Er protokolliert, WER ~/.config/zentrale/theme aendert — Anlass war ein
Umspringen des Themes, das rueckwirkend keinem Prozess zuzuordnen war.

Getestet wird gegen eine Wegwerf-Datei (ZENTRALE_THEME_FILE + eigenes
XDG_CACHE_HOME), Sashas echter Zustand wird nie angefasst:
  * eine echte Aenderung landet im Protokoll (mit altem und neuem Wert)
  * ein Schreiben mit GLEICHEM Inhalt nicht (sonst waere das Log im
    Minutentakt voll, weil die Applier die Datei anfassen)
  * ein Rename (so schreibt die TUI: tmp + os.replace) wird erkannt — ein
    Watch auf der Datei selbst waere danach auf einem toten inode
  * --status laeuft, auch wenn noch nichts passiert ist
"""
import os
import shutil
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH = os.path.join(ROOT, "scripts", "zentrale-theme-watch")

pytestmark = pytest.mark.skipif(shutil.which("inotifywait") is None,
                                reason="inotifywait nicht installiert")


@pytest.fixture
def umgebung(tmp_path):
    theme = tmp_path / "theme"
    theme.write_text("day\n")
    cache = tmp_path / "cache"
    cache.mkdir()
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme),
               XDG_CACHE_HOME=str(cache))
    return theme, cache / "zentrale" / "theme-watch.log", env


def _starte(env):
    p = subprocess.Popen(["bash", WATCH], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.6)          # inotifywait muss erst am Verzeichnis haengen
    return p


def _warte_auf(log, text, sekunden=6.0):
    ende = time.time() + sekunden
    while time.time() < ende:
        if log.exists() and text in log.read_text():
            return True
        time.sleep(0.1)
    return False


def _schreibe_atomar(pfad, inhalt):
    """Genau wie die TUI: tmp + rename (der alte inode verschwindet dabei)."""
    tmp = str(pfad) + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(inhalt + "\n")
    os.replace(tmp, str(pfad))


def test_protokolliert_eine_echte_aenderung(umgebung):
    theme, log, env = umgebung
    p = _starte(env)
    try:
        _schreibe_atomar(theme, "night")
        assert _warte_auf(log, "AENDERUNG day -> night"), \
            "Aenderung nicht protokolliert: %s" % (
                log.read_text() if log.exists() else "(kein log)")
    finally:
        p.terminate()
        p.wait(timeout=10)


def test_schweigt_wenn_der_inhalt_gleich_bleibt(umgebung):
    """Die Applier fassen die Datei an, ohne sie zu aendern — kein Logspam."""
    theme, log, env = umgebung
    p = _starte(env)
    try:
        _schreibe_atomar(theme, "day")      # derselbe Wert
        time.sleep(1.5)
        text = log.read_text() if log.exists() else ""
        assert "AENDERUNG" not in text, text
    finally:
        p.terminate()
        p.wait(timeout=10)


def test_merkt_den_dritten_ohne_tui_eintrag(umgebung):
    """Ohne passende TUI-Zeile muss der Eintrag den Dritten benennen."""
    theme, log, env = umgebung
    p = _starte(env)
    try:
        _schreibe_atomar(theme, "night")
        assert _warte_auf(log, "der Schreiber war ein Dritter")
    finally:
        p.terminate()
        p.wait(timeout=10)


def test_status_laeuft_auch_ohne_vorfall(umgebung):
    theme, log, env = umgebung
    r = subprocess.run(["bash", WATCH, "--status"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert "theme-watch.log" in r.stdout
