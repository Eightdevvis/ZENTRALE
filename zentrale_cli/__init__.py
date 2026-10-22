"""Der Befehl `zentrale` — das installierbare Gesicht des Hubs
(memory/hub/knoten_beitritt.md, „Bauplan v1 — Das Programm").

Eine Front wie die TUI: sie ruft den Kern (core/konto.py, core/abgleich.py …)
nur über die im Bauplan freigegebenen Module (memory/system/bauplan_kern.md,
„Türen") und hält selbst nichts als Bedienung. Alle Texte für Menschen
stehen in texte.py (Englisch; Deutsch kommt als zweite Sprache dazu).
"""

import os
import sys

WURZEL = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
KERN = os.path.join(WURZEL, "core")
if KERN not in sys.path:
    sys.path.insert(0, KERN)
