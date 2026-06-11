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
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")
for p in (CORE, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# Ki-frei + Mail aus, BEVOR irgendein Modul die Env liest.
os.environ.setdefault("ZENTRALE_KASSETTE", "tui")
os.environ.setdefault("ZENTRALE_MAIL", "off")
