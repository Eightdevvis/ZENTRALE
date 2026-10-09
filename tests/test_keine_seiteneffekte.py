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


# ── Riegel 3: aus einem Testlauf faellt kein Applier an ─────────────────────
#
# Der eigentliche Schadensweg, und der unscheinbarste. Applier schreiben nicht
# in Dateien, sondern in Sitzungs-Dienste (xfconf, gsettings, tmux-Server) —
# die haengen NICHT an HOME. Keine Umlenkung der Welt faengt sie ein; sie
# treffen immer die Sitzung des angemeldeten Menschen.
#
# Ausgeloest wurde das von einer Stelle, die harmlos aussieht: jeder Applier
# ruft `zentrale-themed --once`, wenn er theme.now nicht findet. Im Wegwerf-HOME
# eines Testlaufs fehlt die Datei IMMER — also startete selbst ein `--dry-run`
# aus einem Test einen Einmal-Lauf des Dienstes, und der hat alle Applier scharf
# gestartet. Sashas Desktop sprang um, waehrend theme und theme.now unveraendert
# dastanden; im Protokoll stand nichts, weil keine Theme-Datei angefasst wurde.

def test_dienst_startet_im_testlauf_keine_applier(monkeypatch, tmp_path):
    """Der Kern-Riegel: im Testlauf faellt kein einziger Applier an."""
    import theme
    monkeypatch.setenv("ZENTRALE_TESTLAUF", "1")
    monkeypatch.setenv("ZENTRALE_THEME_NOW", str(tmp_path / "theme.now"))
    gestartet = []
    st = theme.ThemeState(path=str(tmp_path / "theme"),
                          log_path=str(tmp_path / "log"))
    (tmp_path / "theme").write_text("night\n")
    d = theme.ThemeDaemon(state=st, runner=gestartet.append)
    assert d.tick() == "night", "theme.now soll trotzdem geschrieben werden"
    assert gestartet == [], "im Testlauf darf KEIN Applier starten: %s" % gestartet


def test_dienst_startet_im_echten_lauf_sehr_wohl_applier(monkeypatch, tmp_path):
    """Gegenprobe — sonst faerbt die Maschine nie wieder um."""
    import theme
    monkeypatch.delenv("ZENTRALE_TESTLAUF", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ZENTRALE_THEME_NOW", str(tmp_path / "theme.now"))
    gestartet = []
    st = theme.ThemeState(path=str(tmp_path / "theme"),
                          log_path=str(tmp_path / "log"))
    (tmp_path / "theme").write_text("night\n")
    d = theme.ThemeDaemon(state=st, runner=gestartet.append)
    d.tick()
    assert "zentrale-tmux-theme" in gestartet, gestartet
    assert len(gestartet) == len(theme.APPLIERS)


# bat fehlt hier BEWUSST: es schreibt in eine normale Datei unter HOME, die im
# Testlauf laengst umgelenkt ist, und wird deshalb nicht abgeriegelt — sonst
# waeren die Tests blind, die genau dieses Schreiben pruefen. Der Riegel gilt
# nur fuer Applier, die in eine laufende Sitzung schreiben.
@pytest.mark.parametrize("applier", [
    "zentrale-term-theme", "zentrale-browser-theme", "zentrale-desktop-theme",
    "zentrale-tmux-theme",
])
def test_applier_schreibt_im_testlauf_nichts(applier, tmp_path):
    """Jeder Sitzungs-Applier verhaelt sich im Testlauf wie --dry-run.

    Scharf aufgerufen (ohne Flag) darf er die Sitzung nicht anfassen, aber
    seine Zeile trotzdem ausgeben — daran haengen die Applier-Tests.
    """
    now = tmp_path / "theme.now"
    now.write_text("night\n")
    pfad = os.path.join(ROOT, "scripts", applier)
    umgebung = dict(os.environ, ZENTRALE_TESTLAUF="1",
                    ZENTRALE_THEME_NOW=str(now))
    scharf = subprocess.run(["bash", pfad], capture_output=True, text=True,
                            env=umgebung, timeout=30)
    trocken = subprocess.run(["bash", pfad, "--dry-run"], capture_output=True,
                             text=True, env=umgebung, timeout=30)
    assert scharf.returncode == 0, scharf.stderr[-500:]
    assert scharf.stdout.strip() == trocken.stdout.strip(), (
        "%s hat im Testlauf NICHT wie --dry-run reagiert" % applier)
    assert scharf.stdout.strip(), "Ausgabe fehlt — Applier-Tests brauchen sie"


# ── Der venv-Riegel ─────────────────────────────────────────────────────────
#
# scripts/zentrale_testguard.py ist die Stelle, die auch VERALTETE
# Arbeitsverzeichnisse abfaengt — die bringen ihre eigene alte conftest mit,
# benutzen aber dasselbe venv. Hier geprueft wird die reine Logik; ob der
# Symlink haengt, sagt scripts/zentrale-venv-guard.

def _guard_modul():
    import importlib.util
    pfad = os.path.join(ROOT, "scripts", "zentrale_testguard.py")
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

    Der Riegel laeuft beim Interpreter-START — da steht in sys.argv[0] noch
    "-m". Nur sys.orig_argv zeigt, was wirklich aufgerufen wurde. Ohne diesen
    Fall lief die Erkennung im haeufigsten Aufruf ins Leere.
    """
    guard = _guard_modul()
    umgebung = {}
    ziel = guard.anwenden(umgebung, ["/pfad/venv/bin/python", "-m", "pytest"],
                          "/tmp", 4714)
    assert ziel, "python -m pytest wurde nicht als Testlauf erkannt"
    assert umgebung["ZENTRALE_THEME_FILE"].startswith(ziel)


def test_venv_riegel_biegt_HOME_aus_einer_arbeitskopie_um():
    """Der Fall, an dem die zweite Fassung scheiterte.

    Ein Stand vom 2026-08-16 kennt ZENTRALE_THEME_FILE nicht und expandiert
    "~" hart — die Env-Umlenkung geht bei ihm ins Leere. Deshalb bekommt ein
    Lauf aus einer Arbeitskopie ein Wegwerf-HOME.
    """
    guard = _guard_modul()
    umgebung = {"HOME": "/home/sasha"}
    ziel = guard.anwenden(umgebung, ["python", "-m", "pytest"], "/tmp", 4715,
                          "/home/sasha/codicus/ZENTRALE/.claude/worktrees/alt")
    assert umgebung["HOME"].startswith(ziel), "HOME zeigt weiter auf das echte"


def test_venv_riegel_laesst_HOME_im_haupt_checkout_stehen():
    """Dort ist die conftest aktuell — kein Grund, die Umgebung wegzunehmen."""
    guard = _guard_modul()
    umgebung = {"HOME": "/home/sasha"}
    guard.anwenden(umgebung, ["python", "-m", "pytest"], "/tmp", 4716,
                   "/home/sasha/codicus/ZENTRALE")
    assert umgebung["HOME"] == "/home/sasha"


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
    """Haengt der Riegel im site-packages des laufenden Interpreters?"""
    import sysconfig
    return os.path.exists(os.path.join(sysconfig.get_paths()["purelib"],
                                       "zentrale_testguard.pth"))


def test_kein_testlauf_meldet_sich_auf_dem_desktop():
    """Eine Benachrichtigung ist der einzige Nebeneffekt, den kein Wegwerf-
    HOME abfaengt: sie geht an notify-send und damit direkt an den Menschen.

    Gekostet hat das ein Popup "Geige gleich. Los." bei jedem Lauf von
    tests/test_takt.py — dessen Treiber-Test faehrt absichtlich das echte
    core/takt_treiber.py:sprechen, und dessen letzter Schritt meldet nach draussen.
    """
    sys.path.insert(0, os.path.join(ROOT, "core"))
    import melden

    assert os.environ.get("ZENTRALE_NOTIFY") == "0"
    assert melden.AN is False, "melden.AN liest die Variable beim Import"
    assert melden.desktop("darf nie ankommen") is False


def test_der_takt_treiber_meldet_im_testlauf_nichts(monkeypatch):
    """Der Riegel am Ort des Schadens: der Treiber laeuft ganz normal durch
    (inklusive Lage-Abfrage), nur nach draussen geht nichts."""
    sys.path.insert(0, os.path.join(ROOT, "core"))
    sys.path.insert(0, os.path.join(ROOT, "ui"))
    import ai
    import ai_backends
    import takt_treiber
    import melden

    # Nur nach DRAUSSEN darf nichts gehen: die Lage-Abfrage (i3-msg) laeuft
    # ueber dasselbe subprocess.run und ist voellig in Ordnung.
    geschickt = []

    def mitschreiben(cmd, *a, **k):
        if cmd and cmd[0] == "notify-send":
            geschickt.append(cmd)
        return None

    monkeypatch.setattr(melden.subprocess, "run", mitschreiben)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: "local")
    monkeypatch.setattr(ai, "chat_stream",
                        lambda h, **k: iter(["Geige gleich. ", "Los."]))

    assert takt_treiber.sprechen({"marke": "x", "auftrag": "y"}) is True
    assert geschickt == [], "eine echte Meldung hat den Testlauf verlassen"


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
        "        'zeigt auf die echte Konfiguration: %s' % p\n"
        "def test_stumm():\n"
        "    assert os.environ.get('ZENTRALE_NOTIFY') == '0',\\\n"
        "        'der Riegel laesst Benachrichtigungen durch'\n")

    umgebung = {k: v for k, v in os.environ.items()
                if k not in ("ZENTRALE_THEME_FILE", "ZENTRALE_THEME_NOW",
                             "ZENTRALE_USAGE_FILE", "ZENTRALE_TESTLAUF",
                             "ZENTRALE_NOTIFY",
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


# ── Kill-Riegel: ein Testlauf schiesst niemanden ab ausser seinen Kindern ──
#
# 02.10.2026: ein Updater-Test hat Sashas LAUFENDE ZENTRALE per SIGTERM
# geschlossen (der Updater fand jede tui/zentrale_tui.py der Maschine).

def _riegel_modul():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import zentrale_testguard
    return zentrale_testguard


class _FakeOs:
    def __init__(self):
        self.gesendet = []
        self.kill = lambda pid, sig: self.gesendet.append((pid, sig))
        self.killpg = lambda pg, sig: self.gesendet.append(("pg", pg, sig))


def test_kill_riegel_laesst_eigene_kinder_zu():
    g = _riegel_modul()
    fake = _FakeOs()
    eltern = {300: 200, 200: 100}          # 300 -> 200 -> 100 (wir)
    g.kill_riegel(fake, 100, eltern.get)
    fake.kill(300, 15)
    fake.killpg(200, 15)
    assert fake.gesendet == [(300, 15), ("pg", 200, 15)]


def test_kill_riegel_verweigert_fremde_prozesse():
    g = _riegel_modul()
    fake = _FakeOs()
    eltern = {500: 1, 300: 100}
    g.kill_riegel(fake, 100, eltern.get)
    with pytest.raises(PermissionError):
        fake.kill(500, 15)                 # fremd: z.B. Sashas echte TUI
    with pytest.raises(PermissionError):
        fake.killpg(500, 15)
    fake.kill(500, 0)                      # "lebt er?" bleibt erlaubt
    assert fake.gesendet == [(500, 0)]


@pytest.mark.skipif(not _riegel_installiert(),
                    reason="venv ohne Riegel — scripts/zentrale-venv-guard läuft nicht")
def test_kill_riegel_greift_in_diesem_testlauf():
    """Der echte Lauf: dieses pytest darf seinen eigenen Elternprozess nicht
    signalisieren (SIGCONT wäre harmlos — es kommt gar nicht erst raus)."""
    import signal
    with pytest.raises(PermissionError, match="zentrale_testguard"):
        os.kill(os.getppid(), signal.SIGCONT)


def test_tui_logs_sind_im_testlauf_umgelenkt():
    for var in ("ZENTRALE_TUI_LOG", "ZENTRALE_TUI_CRASH_LOG"):
        p = os.environ.get(var, "")
        assert p and not p.startswith("/tmp/zentrale-tui-crash"), var
        assert ".local/state" not in p, var


def test_transkript_und_gedaechtnis_zeigen_nie_ins_echte_data():
    """Der Riegel gegen das Leck vom 2026-10-06: die Konsolidierungs-Tests
    schrieben ins echte Transkript, weil der Pfad fest verdrahtet war. Zeigt
    einer dieser Pfade während der Tests wieder ins Repo-data/, ist der
    Riegel in tests/conftest.py weg — dann hier rot, bevor Daten leiden."""
    import gedaechtnis
    import transkript
    echt = os.path.realpath(os.path.join(ROOT, "data"))
    for name, pfad in (("transkript", transkript._DIR), ("gedaechtnis", gedaechtnis._DIR)):
        assert not os.path.realpath(pfad).startswith(echt), \
            f"{name}._DIR zeigt im Test ins echte data/: {pfad}"



def test_ki_einstellungen_und_keys_sind_nicht_die_echten():
    """Tests sehen weder Sashas echte ai_config.json noch seine API-Keys
    (2026-10-07: ein Kalender-Test hing an der echten Einstellung)."""
    import ai_config
    import providers
    echt = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "data"))
    assert not os.path.realpath(ai_config._DIR).startswith(echt)
    gesetzt = [p["key_env"] for p in providers.PROVIDERS.values()
               if os.environ.get(p["key_env"])]
    assert gesetzt == [], gesetzt


def test_sandbox_arbeitsordner_liegt_im_test_nicht_im_echten_cache():
    """Code-Läufe aus Tests legen ihre Arbeitsordner nie in Sashas echten
    ~/.cache/zentrale/sandbox und nie ins Repo (2026-10-07, Phase 7)."""
    import sandbox
    basis = os.path.realpath(sandbox.basis_ordner())
    assert not basis.startswith(os.path.realpath(os.path.expanduser("~/.cache"))), basis
    assert not basis.startswith(os.path.realpath(ROOT)), basis

def test_modell_liste_cache_und_netz_sind_im_test_umgelenkt():
    """Die Modell-Listen der Anbieter (core/modell_liste.py, 2026-10-07):
    der Cache liegt im Test nie in Sashas ~/.cache oder im Repo, und kein
    Test fragt von sich aus einen echten Anbieter."""
    import modell_liste
    pfad = os.path.realpath(modell_liste._cache_pfad())
    assert not pfad.startswith(os.path.realpath(os.path.expanduser("~/.cache"))), pfad
    assert not pfad.startswith(os.path.realpath(ROOT)), pfad
    assert modell_liste._holen_an() is False


def test_gespraeche_zeigen_nie_ins_echte_data():
    """Gespräche (core/gespraeche.py, 2026-10-07) werden von den Chat-Tests
    wirklich geschrieben. Zeigt der Ordner im Test ins echte data/, ist der
    Riegel in tests/conftest.py weg."""
    import gespraeche
    echt = os.path.realpath(os.path.join(ROOT, "data"))
    assert not os.path.realpath(gespraeche._DIR).startswith(echt), gespraeche._DIR
    assert not os.environ["ZENTRALE_GESPRAECHE_DIR"].startswith(echt)


def test_ein_chat_zug_legt_nichts_im_echten_data_an(monkeypatch):
    """Ende zu Ende: ein /api/chat-Zug samt Erinnerung schreibt Gespräche —
    und unter dem echten data/gespraeche entsteht dabei nichts."""
    import ai_backends
    import kern
    import gespraeche
    from ui.app import app
    echt = os.path.join(ROOT, "data", "gespraeche")
    vorher = sorted(os.listdir(echt)) if os.path.isdir(echt) else None
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")

    class Modul:
        chat_stream = staticmethod(lambda h, **k: iter(["hallo"]))
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    app.config.update(TESTING=True)
    app.test_client().post("/api/chat", json={"message": "x"}).get_data()
    assert gespraeche.liste()
    nachher = sorted(os.listdir(echt)) if os.path.isdir(echt) else None
    assert nachher == vorher

def test_skill_ordner_liegt_im_test_nicht_im_echten_data():
    """Skills (Phase 4, 2026-10-07) liegen unter der Gedächtnis-Wurzel und
    hängen an derselben Umlenkung. Geprüft gegen data/ dieses Checkouts UND
    des Haupt-Checkouts (aus einem Worktree heraus sind das zwei)."""
    import gedaechtnis
    pfad = os.path.realpath(gedaechtnis.bereich_ordner(gedaechtnis.SKILLS))
    haupt = ROOT.split(os.sep + ".claude" + os.sep + "worktrees" + os.sep)[0]
    for echt in (os.path.join(ROOT, "data"), os.path.join(haupt, "data")):
        assert not pfad.startswith(os.path.realpath(echt)), pfad


def test_gedaechtnis_routen_und_suche_lassen_das_echte_data_in_ruhe():
    """Phase 3 (2026-10-07): PUT /api/gedaechtnis schreibt Sashas Kernakten —
    im Test nur in den Wegwerf-Ordner. Und search_chats liest Gespräche und
    Transkript nur aus der Umlenkung. Geprüft gegen data/ dieses Checkouts
    UND des Haupt-Checkouts: dort ändert sich keine Kernakten-Datei."""
    import chat_suche
    import gedaechtnis
    from ui.app import app
    haupt = ROOT.split(os.sep + ".claude" + os.sep + "worktrees" + os.sep)[0]

    def stand():
        raus = {}
        for basis in (ROOT, haupt):
            for name in ("hausregeln", "sasha", "ziele"):
                for endung in (".md", ".md.bak"):
                    p = os.path.join(basis, "data", "gedaechtnis", name + endung)
                    raus[p] = os.stat(p).st_mtime_ns if os.path.exists(p) else None
        return raus

    vorher = stand()
    app.config.update(TESTING=True)
    c = app.test_client()
    assert c.put("/api/gedaechtnis/ziele", json={"text": "- Probe"}).status_code == 200
    c.get("/api/gedaechtnis")
    chat_suche.suchen_text("probe")
    assert stand() == vorher
    for echt in (os.path.join(ROOT, "data"), os.path.join(haupt, "data")):
        assert not os.path.realpath(gedaechtnis._DIR).startswith(os.path.realpath(echt))
def test_ablage_liegt_im_test_nicht_im_echten_data():
    """Die Ablage (core/ablage.py, Phase 5, 2026-10-07) wird von den Tests
    wirklich beschrieben. Geprüft gegen data/ dieses Checkouts UND des
    Haupt-Checkouts (aus einem Worktree heraus sind das zwei)."""
    import ablage
    pfad = os.path.realpath(ablage.ordner())
    haupt = ROOT.split(os.sep + ".claude" + os.sep + "worktrees" + os.sep)[0]
    for echt in (os.path.join(ROOT, "data"), os.path.join(haupt, "data")):
        assert not pfad.startswith(os.path.realpath(echt)), pfad
    assert not os.environ["ZENTRALE_ABLAGE_DIR"].startswith(os.path.realpath(ROOT))


def test_ein_dokument_im_chat_legt_nichts_im_echten_data_an(monkeypatch):
    """Ende zu Ende: create_document in einem /api/chat-Zug — unter dem
    echten data/ablage entsteht dabei nichts."""
    import ablage
    import ai_backends
    import kern
    import ki_werkzeuge
    from ui.app import app
    echt = os.path.join(ROOT, "data", "ablage")
    vorher = sorted(os.listdir(echt)) if os.path.isdir(echt) else None
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")

    def gen(h, **k):
        ki_werkzeuge._verteilen("create_document", {"titel": "t", "inhalt": "x"})
        yield "ok"

    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    app.config.update(TESTING=True)
    app.test_client().post("/api/chat", json={"message": "x"}).get_data()
    assert ablage.liste()
    nachher = sorted(os.listdir(echt)) if os.path.isdir(echt) else None
    assert nachher == vorher


def test_projekte_liegen_im_test_nicht_im_echten_data():
    """Projekte (Phase 6, 2026-10-07) liegen unter der Gedächtnis-Wurzel und
    hängen an derselben Umlenkung. Ein Anlegen samt Wissen und Zuordnung über
    die Routen lässt data/gedaechtnis/projekte dieses Checkouts UND des
    Haupt-Checkouts unverändert."""
    import gedaechtnis
    import projekte
    from ui.app import app
    haupt = ROOT.split(os.sep + ".claude" + os.sep + "worktrees" + os.sep)[0]
    echte = [os.path.join(b, "data", "gedaechtnis", "projekte") for b in (ROOT, haupt)]

    def stand():
        return {p: (sorted(os.listdir(p)) if os.path.isdir(p) else None) for p in echte}

    vorher = stand()
    pfad = os.path.realpath(projekte.ordner())
    for echt in (os.path.join(ROOT, "data"), os.path.join(haupt, "data")):
        assert not pfad.startswith(os.path.realpath(echt)), pfad
    app.config.update(TESTING=True)
    c = app.test_client()
    name = "waechter-probe-%d" % os.getpid()
    r = c.post("/api/projekte", json={"name": name, "anweisungen": "x"})
    assert r.status_code == 201
    pid = r.get_json()["id"]
    c.post(f"/api/projekte/{pid}/wissen", json={"name": "a", "text": "b"})
    c.post("/api/chat/clear", json={"projekt": pid})
    assert stand() == vorher


def test_skill_umzug_und_erstbefuellung_lassen_das_echte_data_in_ruhe():
    """Seit 2026-10-07 zieht jeder Zugriff alte Skill-Dateien ins Claude-
    Format um, liefert Vorlagen nach und hängt für „kurz" eine Hausregel an.
    Im Test geschieht das nur in der Umlenkung: unter data/gedaechtnis/ dieses
    Checkouts und des Haupt-Checkouts ändert sich nichts (Skills, Hausregeln)."""
    import gedaechtnis
    import skills
    haupt = ROOT.split(os.sep + ".claude" + os.sep + "worktrees" + os.sep)[0]

    def stand():
        raus = {}
        for basis in (ROOT, haupt):
            wurzel = os.path.join(basis, "data", "gedaechtnis")
            for name in ("hausregeln.md", "hausregeln.md.bak"):
                p = os.path.join(wurzel, name)
                raus[p] = os.stat(p).st_mtime_ns if os.path.exists(p) else None
            ordner = os.path.join(wurzel, "skills")
            for ort, _, dateien in (os.walk(ordner) if os.path.isdir(ordner) else ()):
                for d in dateien:
                    p = os.path.join(ort, d)
                    raus[p] = os.stat(p).st_mtime_ns
            raus[ordner] = sorted(os.listdir(ordner)) if os.path.isdir(ordner) else None
        return raus

    vorher = stand()
    skills.alle()
    skills.prompt_block()
    skills.laden("skill-creator")
    assert stand() == vorher
    for echt in (os.path.join(ROOT, "data"), os.path.join(haupt, "data")):
        assert not os.path.realpath(skills.ordner()).startswith(os.path.realpath(echt))
        assert not os.path.realpath(gedaechtnis._DIR).startswith(os.path.realpath(echt))


def test_rueckmeldungen_liegen_im_test_nicht_im_echten_data():
    """Bewertungen (core/rueckmeldungen.py, 2026-10-08) werden von den Tests
    wirklich geschrieben — nie unter data/rueckmeldungen dieses Checkouts
    oder des Haupt-Checkouts. Ende zu Ende über die Route."""
    import gespraeche
    import rueckmeldungen
    from ui.app import app
    haupt = ROOT.split(os.sep + ".claude" + os.sep + "worktrees" + os.sep)[0]
    echte = [os.path.join(b, "data", "rueckmeldungen") for b in (ROOT, haupt)]

    def stand():
        return [sorted((n, os.stat(os.path.join(e, n)).st_mtime_ns) for n in os.listdir(e))
                if os.path.isdir(e) else None for e in echte]
    vorher = stand()
    gid = gespraeche.neu("t")
    nid = gespraeche.anhaengen(gid, "assistant", "x")["id"]
    app.config.update(TESTING=True)
    r = app.test_client().post("/api/rueckmeldung",
                               json={"gespraech": gid, "nachricht": nid, "wert": 1})
    assert r.status_code == 200 and rueckmeldungen.ereignisse()
    assert stand() == vorher
    pfad = os.path.realpath(rueckmeldungen.ordner())
    for e in echte:
        assert not pfad.startswith(os.path.realpath(os.path.dirname(e)))
    assert not os.environ["ZENTRALE_RUECKMELDUNGEN_DIR"].startswith(os.path.realpath(ROOT))


def test_abgleich_zeigt_nie_auf_echten_zustand_schluessel_oder_github():
    """Abgleich über die Mitte (core/abgleich.py, 2026-10-08): örtlicher
    Zustand, Schlüssel und Mitte sind in Tests umgelenkt — kein Testlauf
    erreicht GitHub, liest Sashas Schlüssel oder überschreibt seine Basis."""
    import abgleich
    import abgleich_schluessel
    echt_dir = os.path.expanduser(abgleich.VORGABE_DIR)
    echt_key = os.path.expanduser(abgleich_schluessel.VORGABE_PFAD)
    assert os.path.realpath(abgleich.ordner()) != os.path.realpath(echt_dir)
    assert os.path.realpath(abgleich_schluessel.pfad()) != os.path.realpath(echt_key)
    adresse = os.environ["ZENTRALE_ABGLEICH_MITTE"]
    assert "github" not in adresse and "@" not in adresse
    assert not os.path.exists(adresse)
    for var in ("ZENTRALE_ABGLEICH_DIR", "ZENTRALE_ABGLEICH_SCHLUESSEL"):
        assert not os.environ[var].startswith(os.path.realpath(ROOT))
    assert abgleich.weg() == "rsync"


def test_zugang_schluessel_nie_der_echte():
    """Zugangsschlüssel des Backends (core/zugang.py, 2026-10-08): in Tests
    umgelenkt — kein Test liest Sashas Schlüssel, keine Test-TUI schickt ihn
    mit, und „anlegen/erneuern" in einem Test trifft nie die echte Datei."""
    import zugang
    echt = os.path.expanduser(zugang.VORGABE_PFAD)
    assert os.path.realpath(zugang.pfad()) != os.path.realpath(echt)
    assert not os.environ["ZENTRALE_ZUGANG_SCHLUESSEL"].startswith(os.path.realpath(ROOT))
    from tui.ansichten import zugang_klient
    assert os.path.realpath(zugang_klient.pfad()) != os.path.realpath(echt)


def test_apps_zeigen_auf_die_test_app():
    """Seit 2026-10-09 schickt der Hub Ereignisse an Apps (core/hub_ereignisse.py)
    und startet sie. Im Testlauf darf das nie die echte Tutor-App sein —
    deren Server hält Sashas Lernstände."""
    import apps
    wert = apps.pfad("tutor")
    assert os.path.realpath(wert).startswith(os.path.realpath(os.path.join(ROOT, "tests"))), wert
    m = apps.manifest("tutor")
    assert m and m["adresse"].endswith(":9"), "Test-App muss ins Leere zeigen"


def test_nutzer_ordner_zeigt_nicht_auf_den_echten():
    """Input/ und Output/ (core/nutzer_ordner.py, 2026-10-09): im Betrieb
    ~/Zentrale. Ein Test, der dort sucht oder Unterordner anlegt, fasst
    Sashas echte Ablage an."""
    import nutzer_ordner
    wert = os.environ.get("ZENTRALE_NUTZER_ORDNER")
    assert wert, "ZENTRALE_NUTZER_ORDNER ist nicht gesetzt"
    echt = os.path.realpath(os.path.expanduser(nutzer_ordner.STANDARD))
    assert nutzer_ordner.wurzel(anlegen=False) != echt
    assert not nutzer_ordner.wurzel(anlegen=False).startswith(os.path.realpath(ROOT))


def test_desk_ordner_liegt_im_test_nicht_im_echten_data():
    """Desk View (core/desk.py, 2026-10-09): im Betrieb data/desk/ mit Sashas
    Zetteln. Kein Test legt dort einen Desk an oder überschreibt einen."""
    import desk
    wert = os.environ.get("ZENTRALE_DESK_ORDNER")
    assert wert, "ZENTRALE_DESK_ORDNER ist nicht gesetzt"
    assert not os.path.realpath(desk.ordner()).startswith(os.path.realpath(ROOT))
