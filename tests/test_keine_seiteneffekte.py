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


# ── Riegel 2: Code aus einer Arbeitskopie ───────────────────────────────────
#
# Die Waechter oben pruefen die Umlenkung — also den Weg, auf dem ein Testlauf
# an der echten Konfiguration vorbeigeleitet wird. Der zweite Riegel sitzt im
# Betriebscode selbst und gilt auch dann, wenn gar nicht getestet wird: aus
# einem Worktree heraus darf nichts Sashas laufende Konfiguration schreiben.

def test_guard_verweigert_der_arbeitskopie_die_echte_datei(monkeypatch):
    """Worktree + echte Konfiguration = das einzige Nein."""
    import theme
    monkeypatch.setattr(theme, "ist_arbeitskopie", lambda: True)
    erlaubt, grund = theme.darf_schreiben(ECHT_THEME)
    assert not erlaubt
    assert grund == "arbeitskopie"


def test_guard_laesst_den_haupt_checkout_in_ruhe(monkeypatch):
    """Sonst koennte die echte TUI ihr Theme nicht mehr schalten."""
    import theme
    monkeypatch.setattr(theme, "ist_arbeitskopie", lambda: False)
    assert theme.darf_schreiben(ECHT_THEME)[0]


def test_guard_stoert_einen_umgelenkten_testlauf_nicht(monkeypatch, tmp_path):
    """Selbst aus dem Worktree: ein tmp-Pfad ist nicht die echte Konfig."""
    import theme
    monkeypatch.setattr(theme, "ist_arbeitskopie", lambda: True)
    assert theme.darf_schreiben(str(tmp_path / "theme"))[0]


def test_set_schreibt_aus_der_arbeitskopie_nicht(monkeypatch, tmp_path):
    """Der Riegel greift im echten Schreibweg, nicht nur in der Abfrage."""
    import theme
    ziel = tmp_path / "theme"
    ziel.write_text("auto\n")
    st = theme.ThemeState(path=str(ziel), log_path=str(tmp_path / "log"))
    monkeypatch.setattr(theme, "darf_schreiben", lambda p: (False, "arbeitskopie"))
    assert st.set("night") is False
    assert ziel.read_text().strip() == "auto"


# ── Der venv-Riegel ─────────────────────────────────────────────────────────
#
# scripts/sitecustomize_testguard.py ist die Stelle, die auch VERALTETE
# Arbeitsverzeichnisse abfaengt — die bringen ihre eigene alte conftest mit,
# benutzen aber dasselbe venv. Hier geprueft wird die reine Logik; ob der
# Symlink haengt, sagt scripts/zentrale-venv-guard.

def _guard_modul():
    import importlib.util
    pfad = os.path.join(ROOT, "scripts", "sitecustomize_testguard.py")
    spec = importlib.util.spec_from_file_location("_testguard", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_venv_riegel_biegt_einen_pytest_lauf_um():
    guard = _guard_modul()
    umgebung = {}
    ziel = guard.anwenden(umgebung, ["/pfad/venv/bin/pytest"], "/tmp", 4711)
    assert ziel
    assert umgebung["ZENTRALE_TESTLAUF"] == "1"
    for var in ("ZENTRALE_THEME_FILE", "ZENTRALE_THEME_NOW",
                "XDG_CACHE_HOME", "ZENTRALE_USAGE_FILE"):
        assert umgebung[var].startswith(ziel), var


def test_venv_riegel_erkennt_auch_python_m_pytest():
    """Die Form, an der die erste Fassung scheiterte.

    sitecustomize laeuft beim Interpreter-START — da steht in sys.argv[0] noch
    "-m". Nur sys.orig_argv zeigt, was wirklich aufgerufen wurde. Ohne diesen
    Fall lief die Erkennung im haeufigsten Aufruf ins Leere.
    """
    guard = _guard_modul()
    umgebung = {}
    ziel = guard.anwenden(umgebung, ["/pfad/venv/bin/python", "-m", "pytest"],
                          "/tmp", 4714)
    assert ziel, "python -m pytest wurde nicht als Testlauf erkannt"
    assert umgebung["ZENTRALE_THEME_FILE"].startswith(ziel)


def test_venv_riegel_laesst_die_echte_tui_in_ruhe():
    """Kein Testlauf = kein Eingriff. Sonst laege die TUI im Wegwerf-Ordner."""
    guard = _guard_modul()
    umgebung = {}
    assert guard.anwenden(umgebung, ["python", "tui/zentrale_tui.py"],
                          "/tmp", 4711) is None
    assert umgebung == {}


def test_venv_riegel_legt_fuer_kindprozesse_nichts_neues_an():
    """Die vom Fuzzer gestartete TUI erbt die Pfade — und faengt nicht neu an."""
    guard = _guard_modul()
    umgebung = {"ZENTRALE_TESTLAUF": "1", "PYTEST_VERSION": "8",
                "ZENTRALE_THEME_FILE": "/tmp/geerbt/theme"}
    assert guard.anwenden(umgebung, ["python", "tui/zentrale_tui.py"],
                          "/tmp", 4712) is None
    assert umgebung["ZENTRALE_THEME_FILE"] == "/tmp/geerbt/theme"


def test_venv_riegel_ueberschreibt_gesetzte_werte_nicht():
    """setdefault, wie in conftest — ein Test darf auf sein tmp_path biegen."""
    guard = _guard_modul()
    umgebung = {"ZENTRALE_THEME_FILE": "/tmp/eigenes/theme"}
    guard.anwenden(umgebung, ["/pfad/venv/bin/pytest"], "/tmp", 4713)
    assert umgebung["ZENTRALE_THEME_FILE"] == "/tmp/eigenes/theme"


def _riegel_installiert():
    """Haengt sitecustomize.py im site-packages des laufenden Interpreters?"""
    import sysconfig
    return os.path.exists(os.path.join(sysconfig.get_paths()["purelib"],
                                       "sitecustomize.py"))


@pytest.mark.skipif(not _riegel_installiert(),
                    reason="venv ohne Riegel — scripts/zentrale-venv-guard läuft nicht")
def test_venv_riegel_greift_in_einem_echten_subprozess(tmp_path):
    """Der Waechter mit den echten Handgriffen — und der einzige, der den
    Fehler der ersten Fassung gefunden haette.

    Die Tests darueber rufen `anwenden()` mit erfundenen Argumenten auf; ob
    die Erkennung im wirklichen Interpreter-Start zuschlaegt, sagen sie nicht.
    Deshalb hier ein echtes `python -m pytest` auf eine Wegwerf-Testdatei
    AUSSERHALB des Repos (damit keine conftest von uns mitlaeuft) und mit aus
    der Umgebung geloeschten Variablen (damit nichts geerbt wird): uebrig
    bleibt genau der venv-Riegel.
    """
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import os\n"
        "def test_umgelenkt():\n"
        "    p = os.environ.get('ZENTRALE_THEME_FILE', '')\n"
        "    assert p, 'der venv-Riegel hat gar nichts gesetzt'\n"
        "    echt = os.path.expanduser('~/.config/zentrale')\n"
        "    assert not os.path.realpath(p).startswith(os.path.realpath(echt)),\\\n"
        "        'zeigt auf die echte Konfiguration: %s' % p\n")

    umgebung = {k: v for k, v in os.environ.items()
                if k not in ("ZENTRALE_THEME_FILE", "ZENTRALE_THEME_NOW",
                             "ZENTRALE_USAGE_FILE", "ZENTRALE_TESTLAUF",
                             "XDG_CACHE_HOME", "PYTEST_VERSION",
                             "PYTEST_CURRENT_TEST")}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "-q", "--tb=short",
         "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=umgebung, capture_output=True, text=True,
        timeout=300)
    assert r.returncode == 0, (
        "Der venv-Riegel greift bei `python -m pytest` nicht:\n%s%s"
        % (r.stdout[-2000:], r.stderr[-500:]))
