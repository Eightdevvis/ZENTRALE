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

# 3. Buchhaltung in eine Wegwerf-Datei umlenken.
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
