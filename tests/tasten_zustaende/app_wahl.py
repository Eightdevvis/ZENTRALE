"""App aus dem Schaufenster öffnen (tui/ansichten/app_oeffnen.py, 2026-10-25):
zwei eingerichtete Ansichten → der Kasten „wie öffnen?"."""

BUDGET = {"name": "budget", "titel": "Budget", "quelle": "zentrale://shop/apps/budget",
          "ansichten_installiert": [
              {"id": "browser", "titel": "im browser", "url": "http://127.0.0.1:8742/"},
              {"id": "terminal", "titel": "im terminal", "start": True}]}

ZUSTAENDE = {"wahl": lambda u: u.app_wahl.oeffnen(dict(BUDGET))}
