"""
Gemeinsames Test-Setup.

Zwei Dinge, die jeder Test braucht:

1. Import-Pfade: Die Module liegen in core/ und werden im echten Lauf gefunden,
   weil main.py / ui-app.py das Projekt-Root bzw. core/ selbst auf sys.path
   legen. Für die Tests stellen wir denselben Pfad her: Root + core/ vorne dran,
   damit `import state`, `from ui.app import app`, `import tui.zentrale_tui` etc.
   ohne ein installiertes Paket auflösen.

2. Kassette: Wir fahren die Tests IMMER ki-frei (ZENTRALE_KASSETTE=tui). So
   spricht nichts Ollama an, kein News-Fetcher, keine Mail — und wir können
   prüfen, dass die KI-Endpoints in dieser Kassette hart abgeriegelt sind.
"""
import atexit
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
for p in (CORE, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# Ki-frei + Mail aus, BEVOR irgendein Modul die Env liest.
os.environ.setdefault("ZENTRALE_KASSETTE", "tui")
os.environ.setdefault("ZENTRALE_MAIL", "off")

# 3. Kein Testlauf meldet sich auf Sashas Desktop.
#
# Der Zwilling dieser Zeile steht in scripts/zentrale_testguard.py (der greift
# auch aus einem alten Worktree, dessen conftest diese hier nicht kennt); die
# Begründung steht dort ausführlich. Kurz: der Treiber-Test in test_takt.py
# fährt absichtlich das echte ui/app.py:_takt_sprechen, und dessen letzter
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
os.environ.setdefault("XDG_CACHE_HOME", os.path.join(_THEME_TMP, "cache"))


@atexit.register
def _theme_tmp_aufraeumen():
    import shutil
    shutil.rmtree(_THEME_TMP, ignore_errors=True)


# 6. Kein Testlauf darf Geld ausgeben.
#
# Gelernt am 2026-09-04: `test_ki_endpoint_locked_in_tui_kassette` prüfte, dass
# der Chat in der ki-freien Kassette zu bleibt — und ging davon aus, dass in der
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
# (scripts/pruefstand.py, ~0,19 € pro Abnahme).
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
