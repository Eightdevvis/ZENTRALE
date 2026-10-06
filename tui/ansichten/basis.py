# tui/ansichten/basis.py
#
# Was jede Ansicht braucht und nichts mit curses zu tun hat: wo das Backend
# steht, wie man es anspricht, und wie man ein Zusatzfenster im Virtualenv
# startet. Lag bis 06.10.2026 oben in tui/zentrale_tui.py; seit die Ansichten
# eigene Module sind, wohnt es hier — zentrale_tui.py importiert es von hier,
# damit es genau EINE Stelle gibt (siehe memory/system/tui_bauplan.md).

import json
import os
import sys
import urllib.request

BASE_URL = (os.environ.get("ZENTRALE_URL") or "http://localhost:5000").rstrip("/")

# Die Projekt-Wurzel (…/ZENTRALE): für scripts/ (Karten-Fenster, Zimmer) und
# core/ (Ton). Achtung: von hier aus sind es DREI Ebenen (tui/ansichten/
# basis.py), von zentrale_tui.py aus zwei. Ansichten nehmen deshalb nie ihr
# eigenes __file__, sondern PROJEKT (tests/test_tui_ansichten.py prüft das).
PROJEKT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Was eine Ansicht aus taste(ch) zurückgibt, wenn die ganze TUI enden soll
# ('q' in einem Werkzeug). Früher stand dort ein `break` direkt in der
# Hauptschleife; als Methode kann der Zweig die Schleife nicht mehr selbst
# verlassen, also sagt er es ihr.
# (Nicht ENDE: so heißt in zentrale_tui.py schon das /quit-Dict.)
BEENDEN = "beenden"


# Die Zusatzfenster (Karte, Persona-Zimmer) brauchen pygame, also den Virtualenv
# — die TUI selbst ist stdlib-only und laeuft auf dem Pi unter dem System-Python.
# Der venv-Ordner heisst NICHT ueberall gleich: PC/Laptop 'venv', der Pi '.venv'
# (scripts/deploy_pi.sh legt ihn so an, siehe memory/betrieb/deployment.md).
# Frueher stand hier hart 'venv' → auf dem Pi fiel der Start still auf
# sys.executable zurueck (System-Python OHNE pygame) und das Fenster ging gar
# nicht auf. Darum beide Namen probieren.
VENV_DIRS = ("venv", ".venv")


def venv_python(root):
    """Pfad zum Python des Projekt-Virtualenv, oder sys.executable als Fallback."""
    for name in VENV_DIRS:
        cand = os.path.join(root, name, "bin", "python")
        if os.path.exists(cand):
            return cand
    return sys.executable


def api_call(path, method="GET", body=None, timeout=3.0):
    """
    Schreibender/lesender API-Zugriff fürs Graph-Werkzeug (GET/POST/DELETE).
    Anders als Store._get (Hintergrund-Polling) wird das hier synchron bei
    Benutzeraktionen aufgerufen (anlegen/eintragen/löschen) – ein paar ms
    Block im Key-Handler ist okay. Wirft bei Fehler (Caller fängt ab).
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else None


# ── Uhrzeiten: Minuten seit Mitternacht ↔ 'HH:MM' ─────────────────────
# Kalender und Graph-Werkzeug lesen beide Uhrzeiten ein; die Werte kommen
# über JSON und dürfen Müll sein, ohne dass etwas abstürzt.

def parse_clock(s):
    """'23:15' | '2315' | '7' | '24:00' → Minuten seit Mitternacht (0–1440) oder None."""
    if not isinstance(s, str):   # nur Strings parsen, alles andere → None (kein Crash)
        return None
    s = s.strip().replace(".", ":")
    if not s:
        return None
    if ":" in s:
        a, _, b = s.partition(":")
        if not a.isdigit() or (b and not b.isdigit()):
            return None
        h, m = int(a), int(b) if b else 0
    elif s.isdigit():
        if len(s) <= 2:
            h, m = int(s), 0
        else:
            s = s.zfill(4)
            h, m = int(s[:-2]), int(s[-2:])
    else:
        return None
    if h == 24 and m == 0:
        return 1440
    if h > 23 or m > 59:
        return None
    return h * 60 + m


def _num(x):
    """x als ENDLICHE Zahl zurück, sonst None. Bool/Text/Liste/None/NaN/Inf →
    None. Alle Werte kommen über JSON rein, da kann Müll dabei sein — diese
    Schleuse hält ihn von den Rechenpfaden (int()/round()/float()) fern."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    if x != x or x in (float("inf"), float("-inf")):   # NaN (x!=x) oder Inf
        return None
    return x


def fmt_clock(m):
    """Minuten → 'HH:MM' (24:00 für 1440). Müll → '—' statt Crash."""
    m = _num(m)
    if m is None:
        return "—"
    m = int(round(m))
    if m >= 1440:
        return "24:00"
    return "%02d:%02d" % (m // 60, m % 60)
