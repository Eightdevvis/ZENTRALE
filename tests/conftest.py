"""
Gemeinsames Test-Setup.

Zwei Dinge, die jeder Test braucht:

1. Import-Pfade: Die Module liegen in core/ und werden im echten Lauf gefunden,
   weil main.py / ui-app.py das Projekt-Root bzw. core/ selbst auf sys.path
   legen. Für die Tests stellen wir denselben Pfad her: Root + core/ vorne dran,
   damit `import state`, `from ui.app import app`, `import tui.zentrale_tui` etc.
   ohne ein installiertes Paket auflösen.

2. Lokale KI: Wir fahren die Tests IMMER ohne lokale KI
   (ZENTRALE_LOKALE_KI=aus). So spricht nichts Ollama an, kein News-Fetcher,
   keine Mail — und wir können prüfen, dass die KI-Endpoints hart abgeriegelt
   sind.
"""
import atexit
import os
import sys
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
for p in (CORE, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# Ki-frei + Mail aus, BEVOR irgendein Modul die Env liest.
os.environ.setdefault("ZENTRALE_LOKALE_KI", "aus")
os.environ.setdefault("ZENTRALE_MAIL", "off")

# 3. Kein Testlauf meldet sich auf Sashas Desktop.
#
# Der Zwilling dieser Zeile steht in scripts/zentrale_testguard.py (der greift
# auch aus einem alten Worktree, dessen conftest diese hier nicht kennt); die
# Begründung steht dort ausführlich. Kurz: der Treiber-Test in test_takt.py
# fährt absichtlich das echte core/takt_treiber.py:sprechen, und dessen letzter
# Schritt schickt eine echte Systembenachrichtigung raus — jahrelang jedes Mal
# ein Popup "Geige gleich. Los." mitten in Sashas Sitzung.
os.environ.setdefault("ZENTRALE_NOTIFY", "0")

# 4. Buchhaltung in eine Wegwerf-Datei umlenken.
#
# Die Cloud-Tests fahren einen gefälschten API-Client mit erfundenen
# Token-Zahlen — der läuft ganz normal durch usage.buchen(). Ohne diese Zeile
# schrieb ein Testlauf 345 Claude-Calls für 0,20 € in data/ai_usage.json.
# Damit wäre die Kostenanzeige gelogen UND der Budget-Deckel würde gegen
# Ausgaben rechnen, die es nie gab.
_USAGE_TMP = os.path.join(tempfile.gettempdir(),
                          f"zentrale_usage_test_{os.getpid()}.json")
os.environ.setdefault("ZENTRALE_USAGE_FILE", _USAGE_TMP)
atexit.register(lambda: os.path.exists(_USAGE_TMP) and os.remove(_USAGE_TMP))

# 4b. Transkript und Gedächtnis in ein Wegwerf-Verzeichnis umlenken.
#
# Die Konsolidierungs-Tests fahren den echten Weg bis transkript.schreiben —
# und der schrieb fest nach data/ai_transcripts/. Gefunden am 2026-10-06:
# 165 von 236 Zeilen in Sashas echtem Transkript waren Probesätze wie „ich
# mag kaffee" / „es heisst brummer", seit August, bei jedem Testlauf neu.
# Ein Transkript, das zu zwei Dritteln aus Tests besteht, ist kein
# Rohmaterial mehr, sondern eine Lüge über das, was gesagt wurde.
_DATEN_TMP = tempfile.mkdtemp(prefix="zentrale_daten_test_")
os.environ.setdefault("ZENTRALE_TRANSKRIPT_DIR", os.path.join(_DATEN_TMP, "ai_transcripts"))
os.environ.setdefault("ZENTRALE_GEDAECHTNIS_DIR", os.path.join(_DATEN_TMP, "gedaechtnis"))
# Gespräche (core/gespraeche.py, seit 2026-10-07): derselbe Riegel. Jeder
# Test bekommt dazu unten noch einen eigenen Ordner, damit das „aktive
# Gespräch" eines Tests nicht in den nächsten hineinreicht.
os.environ.setdefault("ZENTRALE_GESPRAECHE_DIR", os.path.join(_DATEN_TMP, "gespraeche"))
atexit.register(lambda: shutil.rmtree(_DATEN_TMP, ignore_errors=True))
# Die Sandbox-Arbeitsordner (core/sandbox.py) liegen im Betrieb unter
# ~/.cache/zentrale/sandbox — Testläufe legen ihre in den Wegwerf-Ordner.
os.environ.setdefault("ZENTRALE_SANDBOX_DIR", os.path.join(_DATEN_TMP, "sandbox"))
# Die Ablage (core/ablage.py, Phase 5): Dokumente und Anhänge. Dazu unten
# pro Test ein eigener Ordner.
os.environ.setdefault("ZENTRALE_ABLAGE_DIR", os.path.join(_DATEN_TMP, "ablage"))
# Apps (core/apps.py, Hub-Bauplan Schritt 1, 2026-10-09): eine Test-App statt
# des echten Sprach-Tutors neben dem Repo. Ihre Adresse zeigt ins Leere —
# kein Testlauf schickt Ereignisse an einen laufenden Tutor-Server.
os.environ.setdefault("ZENTRALE_APP_PFAD_TUTOR",
                      os.path.join(ROOT, "tests", "fixtures", "app_tutor"))
# Bewertungen der Antworten (core/rueckmeldungen.py, 2026-10-08). Dazu unten
# pro Test ein eigener Ordner.
# Sashas Nutzerordner (core/nutzer_ordner.py, 2026-10-09: Input/ und Output/,
# im Betrieb ~/Zentrale): kein Test legt dort etwas an oder liest von dort.
os.environ.setdefault("ZENTRALE_NUTZER_ORDNER", os.path.join(_DATEN_TMP, "nutzer"))
os.environ.setdefault("ZENTRALE_RUECKMELDUNGEN_DIR", os.path.join(_DATEN_TMP, "rueckmeldungen"))
# Desk View (core/desk.py, 2026-10-09): im Betrieb data/desk/. Dazu unten
# pro Test ein eigener Ordner.
os.environ.setdefault("ZENTRALE_DESK_ORDNER", os.path.join(_DATEN_TMP, "desk"))
# Abgleich über die Mitte (core/abgleich.py, 2026-10-08): örtlicher Zustand,
# Schlüssel und Mitte nie die echten. Die Mitte zeigt auf ein Verzeichnis,
# das es nicht gibt — ein Test, der vergisst, seine eigene Wegwerf-Mitte zu
# setzen, scheitert, statt GitHub zu erreichen.
os.environ.setdefault("ZENTRALE_ABGLEICH_DIR", os.path.join(_DATEN_TMP, "abgleich"))
os.environ.setdefault("ZENTRALE_ABGLEICH_SCHLUESSEL", os.path.join(_DATEN_TMP, "abgleich.schluessel"))
os.environ.setdefault("ZENTRALE_ABGLEICH_MITTE", os.path.join(_DATEN_TMP, "keine-mitte.git"))
os.environ.pop("ZENTRALE_ABGLEICH_WEG", None)
# Zugangsschlüssel des Backends (core/zugang.py, 2026-10-08): nie der echte —
# weder liest ein Test ihn, noch schickt eine Test-TUI ihn mit, noch legt
# ein Test einen neuen über den echten. Den Modus bestimmt kein Rest aus der
# Shell; Tests setzen ihn selbst.
os.environ.setdefault("ZENTRALE_ZUGANG_SCHLUESSEL", os.path.join(_DATEN_TMP, "zugang.schluessel"))
os.environ.pop("ZENTRALE_ZUGANG", None)
# Die Modell-Listen der Anbieter (core/modell_liste.py, 2026-10-07): im
# Betrieb ~/.cache/zentrale/modelle.json. Und kein Test fragt einen echten
# Anbieter — ein Test, der einen Schlüssel setzt, löste sonst eine echte
# Anfrage aus. Tests der Liste schalten das Holen selbst an und ersetzen
# das Netz.
os.environ.setdefault("ZENTRALE_MODELL_CACHE_DIR", os.path.join(_DATEN_TMP, "modelle"))
os.environ.setdefault("ZENTRALE_MODELL_LISTE_HOLEN", "aus")

# 4c. KI-Einstellungen und Keys: nie die echten.
#
# ai_config liest beim Import data/ai_config.json und legt die Keys daraus
# in os.environ. In Tests hieß das: Sashas echtes Budget, Backend und
# Kalender-Speicher entschieden mit, ob ein Test grün war (gefunden
# 2026-10-07 nach dem Kalender-Umzug: „leere Einstellung → json" wurde rot,
# weil die echte Datei „ics" sagte) — und echte API-Keys lagen in der
# Testumgebung. Jetzt: leeres Wegwerf-Verzeichnis, und Keys aus der Shell
# werden ausgeräumt. Ein Test, der einen Key braucht, setzt ihn selbst.
_CFG_TMP = os.path.join(_DATEN_TMP, "ai_config")
os.makedirs(_CFG_TMP, exist_ok=True)
os.environ.setdefault("ZENTRALE_AI_CONFIG_DIR", _CFG_TMP)
for _k in ("ANTHROPIC_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
           "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"):
    os.environ.pop(_k, None)

# 5. Theme-Dateien in ein Wegwerf-Verzeichnis umlenken.
#
# Dieselbe Klasse Fehler wie Punkt 3, nur teurer, weil man sie SIEHT: der
# TUI-Fuzzer (tests/test_tui_fuzz.py) startet die echte TUI in einem Pseudo-
# Terminal und drückt zufällige Tasten — darunter 't'. Ohne diese Zeilen
# schaltete also JEDER volle Testlauf Sashas echtes Theme wild um: Terminal,
# nvim, Browser, Desktop und bat zogen brav nach, und im Betrieb sah das aus
# wie ein zufälliger Glitch. Genau danach ist tagelang an der falschen Stelle
# gesucht worden (siehe memory/system/dashboard.md).
#
# Umgelenkt werden BEIDE Dateien der Kopplung (Wunsch + Ergebnis) und der
# Cache, in dem das Änderungsprotokoll liegt. Einzelne Tests dürfen die
# Variablen weiterhin per monkeypatch auf ihr eigenes tmp_path biegen.
_THEME_TMP = os.path.join(tempfile.gettempdir(),
                          f"zentrale_theme_test_{os.getpid()}")
os.makedirs(_THEME_TMP, exist_ok=True)
os.environ.setdefault("ZENTRALE_THEME_FILE", os.path.join(_THEME_TMP, "theme"))
os.environ.setdefault("ZENTRALE_THEME_NOW", os.path.join(_THEME_TMP, "theme.now"))
# Playwright sucht Chromium unter $XDG_CACHE_HOME/ms-playwright — nach der
# Umlenkung (hier und schon in scripts/zentrale_testguard.py) fände der
# Browser-Test (tests/test_browser.py) das heruntergeladene Chromium nicht
# mehr. Auch HOME ist dort schon umgebogen, also das echte Heim aus der
# Benutzertabelle. Der Ort wird nur gelesen (2026-10-09).
import pwd  # noqa: E402
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(
    pwd.getpwuid(os.getuid()).pw_dir, ".cache", "ms-playwright"))
os.environ.setdefault("XDG_CACHE_HOME", os.path.join(_THEME_TMP, "cache"))


@atexit.register
def _theme_tmp_aufraeumen():
    import shutil
    shutil.rmtree(_THEME_TMP, ignore_errors=True)


# 5b. TUI-Lebenslauf und Crash-Log umlenken (Zwilling im venv-Riegel).
#
# Jede Test-TUI raeumt beim Start ihr Crash-Log weg — ohne Umlenkung das
# ECHTE /tmp/zentrale-tui-crash.log der laufenden ZENTRALE.
os.environ.setdefault("ZENTRALE_TUI_LOG", os.path.join(_THEME_TMP, "tui.log"))
os.environ.setdefault("ZENTRALE_TUI_CRASH_LOG",
                      os.path.join(_THEME_TMP, "tui-crash.log"))
# PC-Status (core/pc_status.py) nie in die echte Datei der Maschine schreiben.
os.environ.setdefault("ZENTRALE_PEER_STATUS", os.path.join(_THEME_TMP, "peer.json"))
# Merkzettel des Kalender-Sync-Wächters (scripts/kalender_sync.py) nie echt.
os.environ.setdefault("ZENTRALE_KALENDER_SYNC_STAND", os.path.join(_THEME_TMP, "sync_stand.json"))
# Dashboard-Wunsch (/dashboard an|aus): Tests sehen immer das Meta-Rad,
# egal was Sasha gerade eingestellt hat, und schreiben nie seine Datei.
os.environ.setdefault("ZENTRALE_DASHBOARD_FILE", os.path.join(_THEME_TMP, "dashboard"))
# Kein Testlauf gilt als "unter der Systemeinheit" (start_tui.sh), auch wenn
# pytest aus einer ZENTRALE heraus gestartet wurde — sonst könnte Esc auf der
# Startseite einer Test-TUI Sashas echtes Fenster wegklappen.
os.environ.pop("ZENTRALE_TUI_SUPERVISED", None)


# 6. Kein Testlauf darf Geld ausgeben.
#
# Gelernt am 2026-09-04: `test_ki_endpoint_locked_ohne_lokale_ki` prüfte, dass
# der Chat ohne lokale KI zu bleibt — und ging davon aus, dass in der
# Testumgebung ohnehin kein Backend erreichbar ist. Sobald ein DASHSCOPE-/
# Anthropic-Key da war und das Netz stand, stimmte diese Annahme nicht mehr:
# der Test schickte einen ECHTEN Claude-Call los (~0,07 € pro Lauf) und fiel
# dann um. Ein Testlauf, der Geld kostet, ist kein Testlauf.
#
# Deshalb ist die Suite jetzt hart offline: der Erreichbarkeits-Check von
# ai_backends liefert in Tests immer False, die Cloud gilt also als nicht da.
# Das ist auch inhaltlich richtig — ZENTRALE ist ein Offline-System, und die
# Cloud-Logik gehört gegen gefälschte Clients geprüft, nicht gegen den echten
# Anbieter (siehe tests/test_cloud_core.py, das genau das tut).
#
# Wer WIRKLICH gegen die echte Leitung prüfen will, markiert seinen Test mit
# `@pytest.mark.kostet_geld`. Solche Tests laufen NICHT im normalen Lauf
# (pytest.ini schließt sie aus) und müssen von Hand angestoßen werden:
#     venv/bin/python -m pytest -m kostet_geld
# Der grosse Live-Pruefstand liegt ohnehin ausserhalb der Suite
# (scripts/pruefstand.py, memory/ki/pruefstand.md; ~0,5–1 € pro Durchgang).
import pytest


@pytest.fixture(autouse=True)
def _keine_echten_cloud_calls(request, monkeypatch):
    if request.node.get_closest_marker("kostet_geld"):
        return                      # bewusst angefordert, von Hand gestartet
    import ai_backends
    monkeypatch.setattr(ai_backends, "_reachable", lambda *a, **k: False)
    # status() cacht 5 s — ein Rest aus einem früheren Test (oder aus dem
    # Import) würde die Cloud sonst weiter als erreichbar melden.
    ai_backends._cache["val"] = None
    ai_backends._cache["t"] = 0.0
    yield
    ai_backends._cache["val"] = None
    ai_backends._cache["t"] = 0.0


# 7. Der Kalender eines Testlaufs liegt nie in Sashas data/.
#
# Bis 2026-10-06 bogen die Kalender-Tests CAL_PATH einzeln um; wer es vergaß,
# las (und schrieb!) die echte data/ai_calendar.json — aus dem Haupt-Checkout
# heraus Sashas echten Kalender. Seit es neben der JSON einen .ics-Ordner,
# Verlauf, Snapshots und Grabsteine gibt, die alle neben CAL_PATH liegen
# (core/kalender_speicher.py), wäre ein Versehen noch teurer: ein Test im
# .ics-Modus legte data/kalender/ an. Deshalb biegt diese Fixture JEDEN Test
# auf ein Wegwerf-Verzeichnis; Tests, die selbst umbiegen, gewinnen.
#
# Der git-Spiegel (core/kalender_spiegel.py) schreibt im Betrieb nach
# ~/.local/share/zentrale/kalender-git — in Tests nie. Wer ihn prüft, setzt
# die Einstellung selbst auf einen tmp-Pfad.
os.environ.setdefault("ZENTRALE_KALENDER_GIT_SPIEGEL", "aus")


@pytest.fixture(autouse=True)
def _kalender_nie_in_echten_daten(tmp_path_factory, monkeypatch):
    import kalender
    ordner = tmp_path_factory.mktemp("kalender_default")
    monkeypatch.setattr(kalender, "CAL_PATH", ordner / "ai_calendar.json")
    monkeypatch.setattr(kalender, "ICS_DIR", None)
    yield


# 7b. Jeder Test hat seine eigenen Gespräche.
#
# Die Chat-Routen schreiben seit 2026-10-07 in core/gespraeche.py; ohne
# frischen Ordner sähe ein Test das aktive Gespräch und die Erinnerungen des
# vorigen. Der Ordner liegt (wie oben per Env) nie in Sashas data/.
@pytest.fixture(autouse=True)
def _gespraeche_frisch(tmp_path_factory, monkeypatch):
    import gespraeche
    monkeypatch.setattr(gespraeche, "_DIR", str(tmp_path_factory.mktemp("gespraeche")))
    gespraeche._cache.clear()
    yield
    gespraeche._cache.clear()


# 7c. Jeder Test hat seine eigene Ablage (core/ablage.py, 2026-10-07).
@pytest.fixture(autouse=True)
def _ablage_frisch(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("ZENTRALE_ABLAGE_DIR", str(tmp_path_factory.mktemp("ablage")))
    yield


# 7d. Jeder Test hat seine eigenen Bewertungen (core/rueckmeldungen.py, 2026-10-08).
@pytest.fixture(autouse=True)
def _rueckmeldungen_frisch(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("ZENTRALE_RUECKMELDUNGEN_DIR", str(tmp_path_factory.mktemp("rueckmeldungen")))
    yield


# 7e. Jeder Test hat seine eigenen Desks (core/desk.py, 2026-10-09).
@pytest.fixture(autouse=True)
def _desk_frisch(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("ZENTRALE_DESK_ORDNER", str(tmp_path_factory.mktemp("desk")))
    yield


# 8. Kalender-Tests laufen gegen BEIDE Speicher.
#
# Der Umstieg auf .ics (memory/werkzeuge/kalender_ics_bauplan.md) verspricht:
# die öffentlichen Kalender-Funktionen verhalten sich gleich, egal ob die
# alte JSON oder der .ics-Ordner dahinter liegt. Das beweist am besten die
# Suite, die es schon gibt: jeder Test mit der Marke `kalender_beide` läuft
# zweimal, einmal pro Speicher (Env ZENTRALE_KALENDER_SPEICHER, die
# ai_config.setting zuerst liest).
def pytest_generate_tests(metafunc):
    if metafunc.definition.get_closest_marker("kalender_beide"):
        # VORN einreihen: Fixtures wie `cal` schreiben schon beim Aufbau in
        # den Kalender — der Speicher muss vorher feststehen.
        if "_kalender_speicher_art" not in metafunc.fixturenames:
            metafunc.fixturenames.insert(0, "_kalender_speicher_art")
        metafunc.parametrize("_kalender_speicher_art", ["json", "ics"],
                             ids=["json", "ics"], indirect=True)


@pytest.fixture
def _kalender_speicher_art(request, monkeypatch):
    art = request.param
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", art)
    import kalender_ics
    kalender_ics.cache_leeren()
    yield art
    kalender_ics.cache_leeren()
