# core/kassette.py
#
# Welche "Kassette" läuft gerade?
#
# ZENTRALE kennt mehrere Fronten, die sich EINE Codebase + EIN Backend teilen,
# aber unterschiedlich aussehen/funktionieren:
#
#   "monolith"  – das große Pi-Kiosk-Dashboard im Browser (KI-Kern, Chat,
#                 Audio, News). Default, wenn nichts gesetzt ist.
#   "laptop"    – die kleine Browser-Kassette für eine RAM-schwache Maschine:
#                 dasselbe Dashboard-Template wie monolith, nur die KI-Teile
#                 sind per ki_aus()-Flag herausgegated (kein Chat/Audio/News).
#   "tui"       – die Terminal-Kassette: rendert im Terminal (curses) statt im
#                 Browser, gegen dasselbe /api/state. KEIN Browser -> der mit
#                 Abstand größte RAM-Posten entfällt. KI ebenfalls aus.
#
# Die Wahl kommt über die Env-Var ZENTRALE_KASSETTE, die der jeweilige
# Start-Befehl setzt (`zentrale` -> monolith, `zentrale-laptop` -> laptop,
# `zentrale-tui` -> tui). So "erkennt" sowohl der Event-Loop (main.py) als
# auch das Flask-Backend (app.py), welche Kassette gefahren wird, ohne dass
# die beiden sich absprechen müssen – sie lesen einfach dieselbe Quelle hier.
#
# Bewusst kein Import von state/ai/etc.: dieses Modul muss völlig
# nebenwirkungsfrei und früh importierbar sein.

import os

MONOLITH = "monolith"
LAPTOP = "laptop"
TUI = "tui"

_VALID = {MONOLITH, LAPTOP, TUI}

# Kassetten, in denen die KI komplett aus ist (kein Warmup, kein News-Fetcher,
# KI-Endpoints abgeriegelt). Alles außer dem Monolith.
_KI_AUS = {LAPTOP, TUI}


def name() -> str:
    """
    Name der aktuell gefahrenen Kassette ("monolith" | "laptop" | "tui").

    Unbekannte/leere Werte fallen sicher auf "monolith" zurück – eine
    falsch gesetzte Env-Var darf nie versehentlich die KI abschalten.
    """
    raw = (os.environ.get("ZENTRALE_KASSETTE") or "").strip().lower()
    return raw if raw in _VALID else MONOLITH


def is_laptop() -> bool:
    """True, wenn die Laptop-Browser-Kassette läuft."""
    return name() == LAPTOP


def is_tui() -> bool:
    """True, wenn die Terminal-Kassette läuft."""
    return name() == TUI


def ki_aus() -> bool:
    """
    True, wenn die KI in der aktuellen Kassette hart aus ist (laptop | tui).
    Steuert sowohl den Auto-Bootup (main.py) als auch das Endpoint-Gate (app.py).
    """
    return name() in _KI_AUS


def template() -> str:
    """
    Das Jinja-Template für die Browser-Route.

    Es gibt nur EINE Front (monolith.html); der Unterschied zwischen den
    Kassetten läuft allein über den ki_aus()-Flag, den index() ans Template
    durchreicht (KI-Blöcke werden dann nicht gerendert). Kein Datei-Split mehr.
    Für tui irrelevant (kein Browser) – falls die Route doch aufgerufen wird,
    bekommt sie dieselbe, KI-frei gegatete Seite.
    """
    return "monolith.html"
