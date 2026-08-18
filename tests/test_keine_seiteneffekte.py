"""
Waechter: die Testsuite darf Sashas laufende Umgebung NICHT anfassen.

Anlass ist ein Fehler, der tagelang wie ein zufaelliger Bug im Betrieb aussah.
Der TUI-Fuzzer (tests/test_tui_fuzz.py) startet die echte TUI in einem
Pseudo-Terminal und drueckt zufaellige Tasten — darunter 't', das Theme-
Zykeln. Ohne Isolation schaltete damit JEDER volle Testlauf das echte Theme um;
Terminal, nvim, Browser, Desktop und bat zogen nach. Gesucht wurde die Ursache
dann im Betriebscode, wo sie nicht war.

Deshalb hier zwei Waechter: einer prueft, dass die Umlenkung ueberhaupt greift,
der andere faehrt den Fuzzer und schaut hinterher nach, ob die echte Datei
angefasst wurde.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ECHT_THEME = os.path.expanduser("~/.config/zentrale/theme")
ECHT_NOW = os.path.expanduser("~/.config/zentrale/theme.now")


def test_theme_pfade_zeigen_nicht_auf_die_echte_konfiguration():
    """conftest muss BEIDE Dateien der Kopplung umgelenkt haben."""
    for var, echt in (("ZENTRALE_THEME_FILE", ECHT_THEME),
                      ("ZENTRALE_THEME_NOW", ECHT_NOW)):
        wert = os.environ.get(var)
        assert wert, "%s ist nicht gesetzt — Tests wuerden die echte Datei treffen" % var
        assert os.path.realpath(wert) != os.path.realpath(echt), \
            "%s zeigt auf Sashas echte Datei" % var


def test_cache_zeigt_nicht_auf_das_echte_verzeichnis():
    """Auch das Aenderungsprotokoll gehoert ins Wegwerf-Verzeichnis."""
    wert = os.environ.get("XDG_CACHE_HOME")
    assert wert
    assert os.path.realpath(wert) != os.path.realpath(
        os.path.expanduser("~/.cache"))


@pytest.mark.skipif(not os.path.exists(ECHT_THEME),
                    reason="keine echte Theme-Datei auf dieser Maschine")
def test_ein_fuzz_lauf_laesst_die_echte_theme_datei_in_ruhe(tmp_path):
    """Der eigentliche Waechter: Fuzzer fahren, echte Datei vorher/nachher.

    Laeuft als eigener pytest-Prozess, damit die conftest-Umlenkung genauso
    greift wie im echten Lauf — und damit dieser Test auch dann etwas aussagt,
    wenn jemand die Umlenkung spaeter versehentlich entfernt.
    """
    vorher = (open(ECHT_THEME).read(), os.stat(ECHT_THEME).st_mtime_ns)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_tui_fuzz.py", "-q",
         "--tb=no", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, timeout=900)
    nachher = (open(ECHT_THEME).read(), os.stat(ECHT_THEME).st_mtime_ns)
    assert nachher == vorher, (
        "Der Fuzz-Lauf hat Sashas echte Theme-Datei veraendert "
        "(%r -> %r). Die Umlenkung in tests/conftest.py greift nicht.\n%s"
        % (vorher[0], nachher[0], r.stdout[-2000:]))
