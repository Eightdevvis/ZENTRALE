#!/usr/bin/env python3
# tui/zentrale_tui.py
#
# ════════════════════════════════════════════════════════════════════════
# ZENTRALE — Terminal-Kassette (TUI)
# ------------------------------------------------------------------------
# "ZENTRALE in klein" OHNE Browser. Rendert das Dashboard direkt im Terminal
# (curses), gegen dasselbe Flask-Backend wie die anderen Kassetten:
#
#     GET /api/state      (1 s)  -> sensoren, stdout-logs, outbound, uptime
#     GET /api/telemetry  (2 s)  -> CPU/RAM/TEMP der lokalen Maschine
#
# Warum: ein Browser-Tab frisst auf einer RAM-schwachen Maschine 300-600 MB+;
# das ganze Backend dagegen ~32 MB. Wer kein Browser braucht, spart genau
# diesen Posten. Der ASCII/VT323-Look der ZENTRALE passt eh ins Terminal.
#
# BEWUSST nur Python-stdlib (curses + urllib + json + threading) — null
# Extra-Dependencies, passt zur Offline-/Lean-Philosophie des Projekts.
#
# Die KI ist in dieser Kassette aus (das Backend läuft im ki-freien Modus,
# siehe core/kassette.py). Die TUI fragt KEINE KI-Endpoints ab.
#
# Start: scripts/start_tui.sh bzw. der Symlink `zentrale-tui` fährt das
# Backend (ki-frei) hoch und startet dann diese TUI im Vordergrund.
# Standalone gegen ein laufendes Backend:  venv/bin/python tui/zentrale_tui.py
# Selbsttest ohne Terminal:                venv/bin/python tui/zentrale_tui.py --selftest
# ════════════════════════════════════════════════════════════════════════

import os
import sys
import json
import time
import threading
from datetime import date, timedelta
import subprocess
import urllib.request
import urllib.error

BASE_URL = (os.environ.get("ZENTRALE_URL") or "http://localhost:5000").rstrip("/")

# Dateien öffnet man in der echten bash unten (tmux-Split, siehe
# scripts/start_tui.sh) via `xdg-open <datei>` — die TUI selbst macht das nicht.

# Sensor-Beschriftung: (ruhe-text, aktiv-text) — gleiche Sprache wie laptop.html
WARD = {
    "button": ("bereit", "TRIGGER"),
    "light":  ("dunkel", "hell"),
    "motion": ("PIR",    "TRIGGER"),
    "door":   ("zu",     "offen"),
}
SENSOR_ORDER = ["button", "light", "motion", "door"]

# Telemetrie-Reihen: (label, key, einheit). Quelle ist /api/telemetry.pc
# (lokaler Host). Nicht verfügbare Werte (v=None) werden übersprungen.
TELE_ROWS = [("CPU", "cpu", "%"), ("RAM", "ram", "%"), ("TEMP", "temp", "°C")]

# stdout-Token -> Farbgruppe (wie die Web-Kassetten)
LOG_PREFIX_COLOR = {
    "NET": "net", "GRAPH": "graph", "EVENT": "event", "STT": "audio",
    "TTS": "audio", "WEBHOOK": "hook", "CONSOLIDATE": "graph",
    "STATE": "dim", "CLOCK": "num", "GESTURE": "acc", "LOGGED": "event",
    "KASSETTE": "acc", "EVENT IN": "event", "EVENT OUT": "event",
}


# ── Daten-Schicht: pollt im Hintergrund, hält den letzten Snapshot ─────────
class Store:
    """Thread-safer Snapshot-Halter. Ein Poller-Thread füllt, die UI liest."""

    def __init__(self):
        self._lock = threading.Lock()
        self.state = {}        # /api/state
        self.metrics = None    # /api/telemetry
        self.graphs = []       # /api/graphs (Definitionen, für lifestyle-Box)
        self.graph_vals = {}   # graph_id -> /api/data/<id> (Messwerte)
        self.connected = False
        self._stop = threading.Event()

    def _get(self, path, timeout=2.0):
        url = BASE_URL + path
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _poll_graphs(self):
        """Graph-Definitionen + ihre Messwerte ziehen (für die lifestyle-Box)."""
        try:
            gs = self._get("/api/graphs") or []
            gv = {}
            for g in gs:
                try:
                    gv[g["id"]] = self._get("/api/data/" + g["id"]) or []
                except (urllib.error.URLError, OSError, ValueError):
                    gv[g["id"]] = []
            with self._lock:
                self.graphs = gs
                self.graph_vals = gv
        except (urllib.error.URLError, OSError, ValueError):
            pass

    def poll_once(self):
        """Einmal alle Endpoints ziehen (für --selftest und den Loop)."""
        ok = False
        try:
            st = self._get("/api/state")
            with self._lock:
                self.state = st
            ok = True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        try:
            tm = self._get("/api/telemetry")
            if isinstance(tm, dict) and not tm.get("error"):
                with self._lock:
                    self.metrics = tm
        except (urllib.error.URLError, OSError, ValueError):
            pass
        self._poll_graphs()
        with self._lock:
            self.connected = ok
        return ok

    def run(self):
        """Poll-Loop: state jede Sekunde, telemetry alle 2 s."""
        tick = 0
        while not self._stop.is_set():
            try:
                st = self._get("/api/state")
                with self._lock:
                    self.state = st
                    self.connected = True
            except (urllib.error.URLError, OSError, ValueError):
                with self._lock:
                    self.connected = False
            if tick % 2 == 0:
                try:
                    tm = self._get("/api/telemetry")
                    if isinstance(tm, dict) and not tm.get("error"):
                        with self._lock:
                            self.metrics = tm
                except (urllib.error.URLError, OSError, ValueError):
                    pass
            if tick % 5 == 0:                  # langsam: manuell geloggte Graph-Werte
                self._poll_graphs()
            tick += 1
            self._stop.wait(1.0)

    def stop(self):
        self._stop.set()

    def snapshot(self):
        with self._lock:
            return dict(self.state), (dict(self.metrics) if self.metrics else None), self.connected

    def graphs_snapshot(self):
        """(graphs, graph_vals) für die lifestyle-Box. Eigene Methode, weil sie
        langsamer frischt als state/telemetry."""
        with self._lock:
            return list(self.graphs), dict(self.graph_vals)


# ── Hilfsfunktionen (UI-unabhängig, testbar) ───────────────────────────────

# Mindestgröße fürs Rendern: darunter passt das Dashboard-Layout nicht und wir
# zeigen nur den "zu klein"-Hinweis. Das Start-Skript (scripts/start_tui.sh)
# deckelt die untere bash beim Boot anhand DERSELBEN 14, damit dem TUI hier
# immer genug bleibt — die beiden Zahlen müssen zusammenpassen.
MIN_LINES = 14
MIN_COLS = 60


def terminal_too_small(h, w):
    """True, wenn das Terminal kleiner als die Mindest-Renderfläche ist."""
    return h < MIN_LINES or w < MIN_COLS


def fmt_uptime(u):
    # Defensiv: alles, was sich nicht in eine ganze Zahl pressen lässt (None,
    # Liste, Text, NaN), wird zu "—" statt zu einem Crash — der State kommt
    # über HTTP/JSON, da kann theoretisch Müll ankommen.
    try:
        if u is None:
            return "—"
        u = int(u)
    except (TypeError, ValueError, OverflowError):   # OverflowError: int(inf)
        return "—"
    return ":".join("%02d" % n for n in (u // 3600, (u // 60) % 60, u % 60))


def bar(pct, length=10):
    """Zweifarbiger Balken-String: n gefüllt + Rest leer. (Ohne Farbe hier.)"""
    n = round(max(0.0, min(100.0, pct)) / 100.0 * length)
    return "█" * n + "░" * (length - n)


def blockspark(vals):
    """ASCII-Sparkline ▁▂▃▄▅▆▇█ aus Zahlenwerten (wie viz.js blockSpark).
    Robust: filtert alles raus, was keine endliche Zahl ist."""
    blocks = "▁▂▃▄▅▆▇█"
    nums = [n for n in (_num(v) for v in vals) if n is not None] \
        if isinstance(vals, (list, tuple)) else []
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    rng = (hi - lo) or 1
    return "".join(blocks[round((v - lo) / rng * (len(blocks) - 1))] for v in nums)


# Graph-Typen fürs Werkzeug: (id, kurz-label, ein-zeilen-hinweis)
GRAPH_TYPES = [
    ("number", "zahl",    "freie messwerte (kurve)"),
    ("scale",  "skala",   "1–5 bewertung"),
    ("time",   "zeit",    "uhrzeit pro datum (z.b. einschlafzeit)"),
    ("period", "periode", "zeitspanne pro datum (z.b. schlaf 23:00–07:00)"),
]


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


def period_duration(start, end):
    """Dauer in Minuten; End < Start = über Mitternacht (Schlaf)."""
    return (int(end) - int(start)) % 1440


def graph_series(gtype, rows):
    """Zahlenreihe für die Sparkline, je nach Typ (period → Dauer). Robust:
    überspringt Einträge, die keine sauberen Zahlen sind (statt zu crashen)."""
    out = []
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict):
            continue
        v = _num(e.get("value"))
        if v is None:
            continue
        if gtype == "period":
            end = _num(e.get("end"))
            if end is None:
                continue
            out.append(period_duration(v, end))
        else:
            out.append(float(v))
    return out


def graph_last(g, rows):
    """Letzter Wert als Text für die lifestyle-Box (type-abhängig formatiert)."""
    if not isinstance(g, dict):
        g = {}
    vals = [e for e in (rows if isinstance(rows, list) else [])
            if isinstance(e, dict) and e.get("value") is not None]
    if not vals:
        return "—"
    e, t = vals[-1], g.get("type")
    if t == "time":
        return fmt_clock(e.get("value"))
    if t == "period":
        if e.get("end") is None:
            return fmt_clock(e.get("value"))
        return fmt_clock(e.get("value")) + "–" + fmt_clock(e.get("end"))
    v = _num(e.get("value"))
    if v is None:
        return "—"
    unit = (" " + str(g.get("unit"))) if g.get("unit") else ""
    return "%g%s" % (v, unit)


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


def tele_value(metrics, key):
    """(pct, text) für eine Telemetrie-Reihe, oder None wenn nicht verfügbar."""
    src = (metrics or {}).get("pc") if isinstance(metrics, dict) else None
    if not isinstance(src, dict):
        return None
    m = src.get(key)
    if not isinstance(m, dict):
        return None
    v = _num(m.get("v"))   # nur endliche Zahlen verrechnen, sonst "nicht verfügbar"
    if v is None:
        return None
    pct = (v - 30) / 60 * 100 if key == "temp" else v   # Temp ehrlich 30–90°C
    unit = next((u for (lbl, k, u) in TELE_ROWS if k == key), "")
    return pct, "%d%s" % (round(v), unit)


def log_prefix(text):
    """Erstes Wort -> Farbgruppe (oder None). Erkennt auch 'EVENT IN/OUT'."""
    for key in ("EVENT IN", "EVENT OUT"):
        if text.startswith(key):
            return key, LOG_PREFIX_COLOR[key]
    head = text.split(" ", 1)[0]
    if head in LOG_PREFIX_COLOR:
        return head, LOG_PREFIX_COLOR[head]
    return None, None


# ── Selbsttest: ein Snapshot als Text, ohne curses (kein TTY nötig) ─────────
def selftest():
    store = Store()
    print("ZENTRALE TUI selftest → %s" % BASE_URL)
    ok = store.poll_once()
    state, metrics, _ = store.snapshot()
    print("  backend erreichbar :", ok)
    if not ok:
        print("  (Backend nicht erreichbar — läuft `zentrale-laptop`/`zentrale-tui`?)")
        return 1
    sn = state.get("sensors", {})
    print("  sensoren           :", {k: bool(sn.get(k)) for k in SENSOR_ORDER})
    print("  uptime             :", fmt_uptime(state.get("uptime_s")))
    print("  datum              :", state.get("time"))
    print("  stdout-zeilen       :", len(state.get("logs", [])))
    print("  outbound-zeilen     :", len(state.get("internet_logs", [])))
    for lbl, key, _u in TELE_ROWS:
        tv = tele_value(metrics, key)
        print("  tele %-5s         :" % lbl, "%s %s" % (bar(tv[0]), tv[1]) if tv else "n/a")
    gs, gv = store.graphs_snapshot()
    print("  graphen            :", [g.get("id") for g in gs] or "—")
    for g in gs:
        rows = gv.get(g["id"]) or []
        ser = graph_series(g.get("type"), rows)
        print("    %-16s :" % g.get("name"), "[%s]" % g.get("type"),
              blockspark(ser), "zuletzt", graph_last(g, rows))
    last = state.get("logs", [])[-1] if state.get("logs") else None
    if last:
        print("  letzte log-zeile    :", last.get("time"), last.get("text"))
    return 0


# ── Befehlszeile: pure Logik (curses-frei, daher unit-testbar) ───────────────
TUI_COMMANDS = [
    ("/help",  "alle Befehle und Tasten zeigen"),
    ("/theme", "Theme: auto | hell | dunkel  (auch 't')"),
    ("/quit",  "ZENTRALE-TUI beenden  (auch 'q')"),
]
TUI_KEYS = [
    ("q",   "beenden"),
    ("t",   "Theme wechseln (auto/hell/dunkel)"),
    ("g",   "Graph-Werkzeug (Mitte): anlegen / eintragen"),
    ("m",   "Karte (Mitte): pan ↑↓←→/hjkl · zoom +/− · 0 reset · f=Stil · o=Handelsrouten · w=Fenster"),
    ("/",   "Befehlszeile öffnen"),
    ("Esc", "Befehl bzw. Hilfe schließen"),
]


def parse_command(buf, theme_mode):
    """
    Wertet einen getippten Befehl aus. PURE Funktion (kein curses, kein State):
      (buf inkl. '/', aktuelles theme_mode) -> (action, neues theme_mode, msg)
    action: None | "QUIT" | "HELP".  msg: kurze Rückmeldung (z.B. Fehler).
    """
    parts = buf[1:].strip().split()
    if not parts:
        return None, theme_mode, ""
    name = parts[0].lower()
    arg = parts[1].lower() if len(parts) > 1 else None
    if name in ("quit", "q", "exit"):
        return "QUIT", theme_mode, ""
    if name in ("help", "h", "?"):
        return "HELP", theme_mode, ""
    if name in ("theme", "t"):
        mapping = {"hell": "day", "dunkel": "night", "day": "day",
                   "night": "night", "auto": "auto"}
        if arg in mapping:
            theme_mode = mapping[arg]
        else:                                   # ohne Arg: zyklieren wie 't'
            theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
        return None, theme_mode, ""
    return None, theme_mode, "unbekannter befehl: /" + name


def overlay_rows(cmd_buf, help_latched):
    """
    Welche Zeilen zeigt das Befehls-Overlay? PURE Funktion → (titel, rows).
    rows-Einträge: ("cmd", name, desc) | ("key", taste, desc) | ("sep",) |
    ("info", "", text). '/help' (oder help_latched) → volle Hilfe inkl. Tasten,
    sonst live-gefilterte Befehlsliste nach dem getippten Präfix.
    """
    full = help_latched or cmd_buf.startswith("/help")
    if full:
        rows = [("cmd", n, d) for n, d in TUI_COMMANDS]
        rows += [("sep",)]
        rows += [("key", k, d) for k, d in TUI_KEYS]
        return "hilfe", rows
    pref = cmd_buf[1:].split(" ")[0].lower()
    hits = [(n, d) for n, d in TUI_COMMANDS if n[1:].startswith(pref)]
    rows = [("cmd", n, d) for n, d in hits] or [("info", "", "kein treffer")]
    return "befehle", rows


# ── curses-UI ───────────────────────────────────────────────────────────────
def run_ui(stdscr, store):
    import curses

    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(250)

    has_color = curses.has_colors()
    if has_color:
        curses.start_color()
        curses.use_default_colors()

    # ── Themes (wie die Web-Kassetten: hell/dunkel) ────────────────────
    # Pro Rolle: (8-Farben-fg, 256-Farben-fg, extra-Attribut). bg pro Theme.
    # Light-Mode: KEIN Gelb auf Weiß (unlesbar) → warn/num = rot/blau.
    # Dark-Mode: ULTRA HIGH CONTRAST — hartes Schwarz, reinweißer Text (231),
    # Rahmen ein klar sichtbares Grau (245). Grün NIE bold (= sonst Neon),
    # gedämpftes Salbeigrün (108) statt grellem Standard-Grün.
    ROLES = ["acc", "warn", "net", "graph", "event", "audio", "hook", "num",
             "dim", "faint", "bright", "ink"]
    THEMES = {
        "night": {
            "bg8": curses.COLOR_BLACK, "bg256": 16,
            #         8-Farbe              256   extra
            "acc":   (curses.COLOR_GREEN,   108, 0),
            "warn":  (curses.COLOR_YELLOW,  226, curses.A_BOLD),
            "net":   (curses.COLOR_CYAN,    51,  curses.A_BOLD),
            "graph": (curses.COLOR_MAGENTA, 213, curses.A_BOLD),
            "event": (curses.COLOR_GREEN,   108, 0),
            "audio": (curses.COLOR_GREEN,   108, 0),
            "hook":  (curses.COLOR_YELLOW,  215, 0),
            "num":   (curses.COLOR_YELLOW,  222, 0),
            "dim":   (curses.COLOR_WHITE,   231, 0),    # normaler Text: reinweiß = max Kontrast
            "faint": (curses.COLOR_WHITE,   245, 0),    # Rahmen: sichtbares Grau (nicht gedimmt)
            "bright":(curses.COLOR_WHITE,   231, curses.A_BOLD),
            "ink":   (curses.COLOR_WHITE,   231, 0),
        },
        "day": {
            "bg8": curses.COLOR_WHITE, "bg256": 231,
            "acc":   (curses.COLOR_GREEN,   65,  0),
            "warn":  (curses.COLOR_RED,     124, curses.A_BOLD),
            "net":   (curses.COLOR_BLUE,    26,  curses.A_BOLD),
            "graph": (curses.COLOR_MAGENTA, 90,  curses.A_BOLD),
            "event": (curses.COLOR_GREEN,   65,  0),
            "audio": (curses.COLOR_GREEN,   65,  0),
            "hook":  (curses.COLOR_RED,     130, 0),
            "num":   (curses.COLOR_BLUE,    26,  0),
            "dim":   (curses.COLOR_BLACK,   16,  0),    # schwarzer Text auf weiß
            "faint": (curses.COLOR_BLUE,    67,  0),    # Rahmen blau-grau (auf weiß sichtbar)
            "bright":(curses.COLOR_BLACK,   16,  curses.A_BOLD),
            "ink":   (curses.COLOR_BLACK,   16,  0),
        },
    }
    C = {}

    def apply_theme(tname):
        if not has_color:
            for r in ROLES:
                C[r] = 0
            C["bright"] = curses.A_BOLD
            C["dim"] = curses.A_BOLD       # heller Text im Mono-Fallback
            C["faint"] = curses.A_DIM
            C["acc"] = curses.A_BOLD
            return
        c256 = curses.COLORS >= 256
        th = THEMES[tname]
        bg = th["bg256"] if c256 else th["bg8"]
        for i, r in enumerate(ROLES, start=1):
            c8, c2, extra = th[r]
            fg = c2 if c256 else c8
            # 8-Farben: reinweißer Text geht nur via A_BOLD (bright white)
            if not c256 and fg == curses.COLOR_WHITE and r in ("dim", "ink", "bright"):
                extra |= curses.A_BOLD
            curses.init_pair(i, fg, bg)
            C[r] = curses.color_pair(i) | extra
        # leere Zellen (erase) bekommen den Theme-Hintergrund
        stdscr.bkgd(" ", C["ink"])

    # Theme-Modus: auto (nach Uhrzeit) | day | night. Taste 't' zykliert.
    theme_mode = "auto"
    def resolved_theme():
        if theme_mode == "auto":
            h = int(time.strftime("%H"))
            return "day" if 5 <= h < 21 else "night"
        return theme_mode
    cur_theme = resolved_theme()
    apply_theme(cur_theme)

    # Esc soll sofort reagieren (sonst wartet ncurses ~1s auf eine Escape-
    # Sequenz, bevor es ein einzelnes Esc durchreicht).
    try:
        curses.set_escdelay(25)
    except Exception:
        pass

    # ── Befehlszeile (unten, per '/' geöffnet) ──────────────────────────
    # Eigene Eingabezeile IN der TUI – die Shell ist im Alternate-Screen nicht
    # erreichbar. '/' öffnet sie, eine Live-Liste klappt nach oben auf und
    # filtert mit jedem Buchstaben, Enter führt aus, Esc bzw. Backspace über den
    # Slash hinaus schließt wieder. '/help' latcht die volle Hilfe (inkl. Tasten),
    # die bei der nächsten Taste wieder wegklappt. Logik: parse_command /
    # overlay_rows (Modulebene, curses-frei → testbar).
    cmd_mode = False        # tippen wir gerade einen Befehl?
    cmd_buf = ""            # inkl. führendem '/'
    help_latched = False    # volle Hilfe stehen lassen (nach '/help')
    cmd_msg = ""            # kurze Rückmeldung (z.B. unbekannter Befehl)

    # ── Graph-Werkzeug (füllt die MITTE-Box, Taste 'g') ─────────────────
    # Geteilte Logik (core/graphs.py + /api/graphs), hier in der TUI verbaut.
    # Eigenes Mini-Zustandsmodell statt vieler nonlocal-Variablen:
    #   active : Werkzeug hat den Fokus (Tasten gehen an das Werkzeug)
    #   view   : "list" (auswählen) | "new" (anlegen) | "view" (eintragen)
    #   input  : Texteingabe (Name im new, Wert im view)
    G = {"active": False, "view": "list", "graphs": [], "sel": 0,
         "def": None, "vals": [], "input": "", "newtype": "number", "msg": "",
         "input2": "", "pstage": 0,    # input2/pstage: Perioden-Eingabe (von→bis)
         "confirm": False}             # Lösch-Nachfrage aktiv (Mini-Dialog)

    # ── Karte (füllt die MITTE-Box, Taste 'm') ──────────────────────────
    # Maps-System Schritt 1: grobe Basiskarte (Küsten 1:110m). Die TUI ist
    # ein reiner Zeichner — alle Geo-Logik liegt im Backend (core/map/ →
    # /api/map/base, siehe memory/maps_system.md). Wir halten nur den
    # Viewport (Mittelpunkt lon/lat + Zoom) und die letzte Server-Antwort.
    #   active : Karte hat den Fokus (Pan/Zoom-Tasten gehen an die Karte)
    #   cx,cy  : Mittelpunkt in lon/lat (Start: 0°/20°, ganze Welt zentriert)
    #   zoom   : 0 = ganze Welt; +1 je Zoomstufe (slippy-Semantik)
    #   data   : letzte /api/map/base-Antwort (None ⇒ beim nächsten Zeichnen neu holen)
    #   grid   : (cols,rows), für die data geholt wurde — bei Resize neu holen
    M = {"active": False, "cx": 0.0, "cy": 20.0, "zoom": 0.0,
         "data": None, "grid": None, "msg": "", "proc": None,
         "style": "braille",    # STANDARD: gefülltes Land in Braille-Punkten
                                # ('f' schaltet auf 'outline' = Küsten-Bresenham)
         "overlay": False,      # Handelsrouten-Overlay (Achse 2) ein/aus
         "odata": None,         # letzte /api/map/layer/trade-Antwort (None ⇒ neu holen)
         "ogrid": None}         # (cols,rows), für die odata geholt wurde
    MAP_COAST = "▓"          # Küsten-/Land-Kantenglyph (gedämpft, kein Vollblock)
    MAP_CHOKE = "◆"          # Chokepoint-Marker (Handelsrouten-Overlay)

    def m_fetch(cols, rows):
        """Karte fürs aktuelle Viewport+Raster synchron holen (localhost, wenige
        ms — wie das Graph-Werkzeug bei Benutzeraktionen). Je nach Stil entweder
        Küsten-Linien (/api/map/base, aspect=0.5 weil ein Zeichen ~2:1 ist) oder
        die gefüllte Braille-Karte (/api/map/braille). Beides liefert core/map/."""
        try:
            if M["style"] == "braille":
                q = ("/api/map/braille?cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d"
                     % (M["cx"], M["cy"], M["zoom"], cols, rows))
            else:
                q = ("/api/map/base?cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d&aspect=0.5"
                     % (M["cx"], M["cy"], M["zoom"], cols, rows))
            M["data"] = api_call(q, timeout=2.0)
            M["grid"] = (cols, rows)
            M["msg"] = ""
        except Exception:
            # Fehler-Marker (truthy!) statt None: verhindert, dass draw_map
            # bei totem Backend JEDEN Frame neu (mit Timeout) anfragt und die UI
            # einfriert. Erst ein Pan/Zoom/Resize (setzt data=None bzw. ändert
            # grid) löst einen neuen Versuch aus.
            M["data"] = {"failed": True}
            M["grid"] = (cols, rows)
            M["msg"] = "karte: backend?"

    def m_fetch_overlay(cols, rows):
        """Handelsrouten-Overlay (Sub-Layer Chokepoints) fürs aktuelle Viewport
        holen — projizierte Marker + Provenienz von /api/map/layer/trade. Wie
        m_fetch synchron; Fehler-Marker statt Dauer-Refetch bei totem Backend."""
        try:
            q = ("/api/map/layer/trade?sub=chokepoints"
                 "&cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d&aspect=0.5"
                 % (M["cx"], M["cy"], M["zoom"], cols, rows))
            M["odata"] = api_call(q, timeout=2.0) or {"failed": True}
        except Exception:
            M["odata"] = {"failed": True}

    def m_pan(fx, fy):
        """Mittelpunkt um einen Bruchteil der sichtbaren Spanne verschieben.
        Spanne kommt aus den zuletzt gelieferten bounds [w,s,e,n] — so braucht
        die TUI selbst KEINE Projektion. data=None erzwingt Neuladen."""
        d = M["data"]
        if not d or "bounds" not in d:   # noch nichts geladen ODER Fehler-Marker
            return                        # ({"failed": True}) → nichts zu schwenken
        w, s, e, n = d["bounds"]
        M["cx"] = max(-180.0, min(180.0, M["cx"] + fx * (e - w)))
        M["cy"] = max(-85.0, min(85.0, M["cy"] + fy * (n - s)))
        M["data"] = None
        M["odata"] = None        # Overlay-Marker mit-neu projizieren

    def m_zoom(dz):
        M["zoom"] = max(0.0, min(8.0, M["zoom"] + dz))
        M["data"] = None
        M["odata"] = None

    def m_window():
        """Die Karte im NATIVEN Fenster aufklappen (pygame, scripts/map_window.py)
        — wie /slide PDFs extern in zathura öffnet. Kein curses-Limit: echte
        antialiased Vektorgrafik. Wir reichen den aktuellen Viewport (cx/cy/zoom)
        mit, damit das Fenster genau dort aufgeht, wo die TUI gerade steht.
        Detached gestartet (eigener Prozess), die TUI läuft normal weiter."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        py = os.path.join(root, "venv", "bin", "python")
        script = os.path.join(root, "scripts", "map_window.py")
        if not os.environ.get("DISPLAY"):
            M["msg"] = "kein DISPLAY (X11?)"
            return
        if not os.path.exists(script):
            M["msg"] = "map_window.py fehlt"
            return
        # NUR EIN Fenster pro TUI: curses' getch() feuert bei gehaltener Taste
        # (Auto-Repeat) mehrfach — ohne diese Sperre würde jeder Tick einen neuen
        # Prozess starten (→ zig Fenster auf einmal). Läuft das vorige noch
        # (poll() is None), öffnen wir keins. Erst wenn es zu ist, geht ein neues.
        proc = M.get("proc")
        if proc is not None and proc.poll() is None:
            M["msg"] = "fenster läuft schon"
            return
        try:
            M["proc"] = subprocess.Popen(
                [py if os.path.exists(py) else sys.executable, script,
                 "--cx", "%.5f" % M["cx"], "--cy", "%.5f" % M["cy"],
                 "--zoom", "%.2f" % M["zoom"]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            M["msg"] = "natives fenster geöffnet"
        except Exception as exc:
            M["msg"] = "fenster-start: %s" % exc

    def g_load():
        """Definitionen frisch ziehen (nach Aktionen / beim Öffnen)."""
        try:
            G["graphs"] = api_call("/api/graphs") or []
        except Exception:
            G["graphs"] = []
        if G["sel"] >= len(G["graphs"]):
            G["sel"] = max(0, len(G["graphs"]) - 1)

    def g_load_vals():
        """Messwerte des gewählten Graphen ziehen (sortiert nach Datum)."""
        G["vals"] = []
        if G["def"]:
            try:
                rows = api_call("/api/data/" + G["def"]["id"]) or []
                G["vals"] = sorted([e for e in rows if e.get("value") is not None],
                                   key=lambda e: str(e.get("date", "")))
            except Exception:
                pass

    def g_save(v, end=None):
        """Wert für HEUTE eintragen (teilt sich /api/log mit der Data-Collection).
        end gesetzt → Zeitperiode (value=Start-Minute, end=End-Minute)."""
        data = {"date": time.strftime("%Y-%m-%d"), "value": v}
        if end is not None:
            data["end"] = end
        try:
            api_call("/api/log", method="POST",
                     body={"category": G["def"]["id"], "data": data})
            g_load_vals()
            t = G["def"].get("type")
            if t == "period":
                G["msg"] = "eingetragen: %s–%s" % (fmt_clock(v), fmt_clock(end))
            elif t == "time":
                G["msg"] = "eingetragen: %s" % fmt_clock(v)
            else:
                G["msg"] = "eingetragen: %g" % v
        except Exception:
            G["msg"] = "speichern fehlgeschlagen"

    def safe_addstr(y, x, text, attr=0):
        h, w = stdscr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        # Zentrale Zeichen-Primitive → hier hart machen, dann ist der GANZE
        # Render-Pfad immun: alles zu str zwingen und Null-Bytes ersetzen
        # (curses.addstr wirft an \x00 ein ValueError, nicht curses.error).
        if not isinstance(text, str):
            text = str(text)
        if "\x00" in text:
            text = text.replace("\x00", " ")
        if x < 0:
            text = text[-x:]
            x = 0
        text = text[: max(0, w - x)]
        try:
            stdscr.addstr(y, x, text, attr)
        except (curses.error, ValueError):
            pass  # untere rechte Zelle wirft immer; ValueError = exotischer String

    def addclip(y, x, text, maxw, attr=0):
        """Wie safe_addstr, aber kürzt vorher auf maxw — verhindert, dass
        z.B. lange stdout-Zeilen aus ihrer Box in die Nachbarspalte laufen."""
        if maxw <= 0:
            return
        if not isinstance(text, str):
            text = str(text)
        safe_addstr(y, x, text[:maxw], attr)

    def draw_box(y, x, h, w, title, title_attr=0):
        if h < 2 or w < 2:
            return
        safe_addstr(y, x, "┌" + "─" * (w - 2) + "┐", C["faint"])
        for i in range(1, h - 1):
            safe_addstr(y + i, x, "│", C["faint"])
            safe_addstr(y + i, x + w - 1, "│", C["faint"])
        safe_addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘", C["faint"])
        if title:
            safe_addstr(y, x + 2, " " + title.upper() + " ", title_attr or C["acc"])

    def _tlabel(tid):
        for t2, lbl, _h in GRAPH_TYPES:
            if t2 == tid:
                return lbl
        return tid

    def draw_time_plot(py, bx, bw, ph, rows, is_period):
        """24h-Gitter: X = letzte Einträge (Datum), Y = Uhrzeit (00:00 unten,
        24:00 oben). time → Punkt ●; period → Balken █ (über Mitternacht
        gesplittet, da die Achse an Mitternacht verankert ist)."""
        if ph < 3:
            return
        ix = bx + 2
        plot_x = ix + 3                       # 3 Spalten für die Stunden-Labels
        plot_w = (bx + bw - 2) - plot_x
        if plot_w < 2:
            return

        def row_of(m):                        # 0 → unterste Zeile, 1440 → oberste
            m = max(0, min(1440, m))
            return py + (ph - 1) - int(round(m / 1440.0 * (ph - 1)))

        for r in range(ph):                   # Y-Achse
            safe_addstr(py + r, plot_x - 1, "│", C["faint"])
        for hh in (0, 6, 12, 18, 24):         # Stunden-Marken
            safe_addstr(row_of(hh * 60), ix, "%02d" % (hh % 24), C["faint"])

        def fill(cx, m1, m2):                 # Balken zwischen zwei Minuten (kein Wrap)
            a, b = sorted((row_of(m1), row_of(m2)))
            for r in range(a, b + 1):
                safe_addstr(r, cx, "█", C["graph"])

        for ci, e in enumerate(rows[-plot_w:]):
            cx = plot_x + ci
            s = e.get("value")
            if s is None:
                continue
            if is_period:
                en = e.get("end")
                if en is None:
                    continue
                if en >= s:
                    fill(cx, s, en)
                else:                         # Wrap über Mitternacht
                    fill(cx, s, 1440)
                    fill(cx, 0, en)
            else:
                safe_addstr(row_of(s), cx, "●", C["graph"])

    def draw_graph_tool(by, bx, bh, bw, gv_cache):
        """Inhalt der MITTE-Box, wenn das Graph-Werkzeug Fokus hat."""
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2          # Hinweiszeile unten in der Box
        if iw < 8:
            return

        if G["view"] == "new":
            addclip(by + 1, ix, "NEUER GRAPH", iw, C["bright"])
            addclip(by + 3, ix, "name: " + G["input"] + "_", iw, C["bright"])
            safe_addstr(by + 5, ix, "typ:", C["dim"]); tx = ix + 6
            for tid, lbl, _h in GRAPH_TYPES:
                on = (G["newtype"] == tid)
                chip = ("[" + lbl + "]") if on else (" " + lbl + " ")
                if tx + len(chip) > bx + bw - 2:
                    break
                safe_addstr(by + 5, tx, chip, C["acc"] if on else C["faint"])
                tx += len(chip) + 1
            addclip(by + 7, ix, next((h for t, l, h in GRAPH_TYPES if t == G["newtype"]), ""), iw, C["faint"])
            addclip(bottom, ix, ("tab typ · enter anlegen · esc zurück  " + G["msg"]).strip(), iw, C["faint"])

        elif G["view"] == "view" and G["def"]:
            d = G["def"]
            typ = d.get("type")
            unit = (" · " + d["unit"]) if d.get("unit") else ""
            addclip(by + 1, ix, "%s  (%s%s)" % (d["name"], _tlabel(typ), unit), iw, C["bright"])
            rows = G["vals"]
            input_row = by + bh - 3

            if typ in ("time", "period"):
                addclip(by + 2, ix, "%d einträge · zuletzt %s" % (len(rows), graph_last(d, rows)), iw, C["dim"])
                if rows:
                    draw_time_plot(by + 3, bx, bw, input_row - 1 - (by + 3), rows, typ == "period")
                else:
                    addclip(by + 3, ix, "— noch keine einträge —", iw, C["faint"])
                if typ == "time":
                    addclip(input_row, ix, "zeit: " + G["input"] + "_", iw, C["bright"])
                    addclip(bottom, ix, ("HH:MM · enter speichern · esc zu  " + G["msg"]).strip(), iw, C["faint"])
                else:
                    c1 = G["input"] + ("_" if G["pstage"] == 0 else "")
                    c2 = G["input2"] + ("_" if G["pstage"] == 1 else "")
                    addclip(input_row, ix, "von: " + c1 + "   bis: " + c2, iw, C["bright"])
                    addclip(bottom, ix, ("HH:MM · enter von→bis · esc zu  " + G["msg"]).strip(), iw, C["faint"])
            else:
                ser = graph_series(typ, rows)
                if ser:
                    addclip(by + 2, ix, blockspark(ser[-iw:]), iw, C["graph"])
                    addclip(by + 3, ix, "%d werte · zuletzt %s" % (len(ser), graph_last(d, rows)), iw, C["dim"])
                else:
                    addclip(by + 2, ix, "— noch keine werte —", iw, C["faint"])
                if typ == "scale":
                    addclip(input_row, ix, "taste 1–5 trägt für heute ein", iw, C["acc"])
                    addclip(bottom, ix, ("1–5 eintragen · esc zu  " + G["msg"]).strip(), iw, C["faint"])
                else:
                    addclip(input_row, ix, "wert: " + G["input"] + "_", iw, C["bright"])
                    addclip(bottom, ix, ("ziffern · enter speichern · esc zu  " + G["msg"]).strip(), iw, C["faint"])

        else:  # "list"
            addclip(by + 1, ix, "GRAPHEN", iw, C["bright"])
            safe_addstr(by + 1, bx + bw - 9, "[n neu]", C["acc"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            yy = by + 3
            if not G["graphs"]:
                addclip(yy, ix, "noch keine — 'n' legt einen an", iw, C["faint"])
            else:
                for i, g in enumerate(G["graphs"]):
                    if yy >= bottom:
                        break
                    if not isinstance(g, dict):
                        continue
                    sel = (i == G["sel"])
                    rows = gv_cache.get(g.get("id")) or []
                    spark = blockspark(graph_series(g.get("type"), rows)[-8:])
                    line = "%s %-12s %-7s %s" % (
                        "›" if sel else " ", str(g.get("name") or "")[:12], _tlabel(g.get("type")), spark)
                    addclip(yy, ix, line, iw, C["bright"] if sel else C["dim"])
                    yy += 1
            addclip(bottom, ix, "↑↓ wählen · enter öffnen · n neu · d löschen · esc zu", iw, C["faint"])

            if G["confirm"] and G["graphs"]:        # Mini-Dialog über die Liste legen
                nm = G["graphs"][G["sel"]]["name"]
                q = "»%s« löschen?" % nm[:18]
                dw = min(iw, max(len(q), 16) + 4)
                dx = bx + (bw - dw) // 2
                dy = by + bh // 2 - 2
                draw_box(dy, dx, 4, dw, "LÖSCHEN", C["warn"])
                addclip(dy + 1, dx + 2, q, dw - 4, C["bright"])
                addclip(dy + 2, dx + 2, "j/enter = ja · sonst abbrechen", dw - 4, C["faint"])

    def draw_map(by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn die Karte Fokus hat. Holt bei Bedarf
        frische Daten (Resize/Pan/Zoom). Zwei Stile (Taste 'f'): 'outline' rastert
        die Küsten-Linien per Bresenham, 'braille' druckt die fertig gefüllte
        Braille-Karte zeilenweise. Beides kommt fertig projiziert vom Backend."""
        iw, ih = bw - 2, bh - 2
        if iw < 4 or ih < 3:
            return
        # Die unterste Box-Innenzeile bleibt für die Status-/Hilfe-Zeile frei.
        map_ih = ih - 1
        if (not M["data"]) or M["grid"] != (iw, map_ih):
            m_fetch(iw, map_ih)
        d = M["data"]
        ox, oy = bx + 1, by + 1
        if not d or d.get("failed") or not (d.get("lines") or d.get("braille")):
            addclip(by + 1, ox, M["msg"] or "lade karte…", iw, C["faint"])
            return

        if M["style"] == "braille" and d.get("braille"):
            # Gefülltes Land als fertige Braille-Zeilen — die TUI druckt nur.
            for r, row in enumerate(d["braille"][:map_ih]):
                addclip(oy + r, ox, row, iw, C["acc"])
        else:
            def plot(c, r):
                if 0 <= c < iw and 0 <= r < map_ih:
                    safe_addstr(oy + r, ox + c, MAP_COAST, C["acc"])

            for line in d.get("lines", []):
                for i in range(len(line) - 1):
                    x0, y0 = int(round(line[i][0])), int(round(line[i][1]))
                    x1, y1 = int(round(line[i + 1][0])), int(round(line[i + 1][1]))
                    dx, dy = abs(x1 - x0), abs(y1 - y0)
                    stepx = 1 if x0 < x1 else -1
                    stepy = 1 if y0 < y1 else -1
                    err = dx - dy
                    while True:
                        plot(x0, y0)
                        if x0 == x1 and y0 == y1:
                            break
                        e2 = 2 * err
                        if e2 > -dy:
                            err -= dy; x0 += stepx
                        if e2 < dx:
                            err += dx; y0 += stepy

        # Handelsrouten-Overlay (Achse 2, Sub-Layer Chokepoints): leuchtende
        # Marker an den Engstellen + Detail der dem Fadenkreuz nächsten Stelle.
        focus = None        # (name, today-total, top-industrie) nahe der Mitte
        ovintage = None
        if M["overlay"]:
            if (not M["odata"]) or M["ogrid"] != (iw, map_ih):
                m_fetch_overlay(iw, map_ih); M["ogrid"] = (iw, map_ih)
            od = M["odata"]
            if od and not od.get("failed"):
                ovintage = od.get("vintage")
                ccol, crow = iw / 2.0, map_ih / 2.0
                best = None
                for p in od.get("points", []):
                    c, r = int(round(p["col"])), int(round(p["row"]))
                    if 0 <= c < iw and 0 <= r < map_ih:
                        safe_addstr(oy + r, ox + c, MAP_CHOKE, C["warn"])
                    dist = (p["col"] - ccol) ** 2 + (p["row"] - crow) ** 2
                    if best is None or dist < best[0]:
                        best = (dist, p)
                if best is not None:
                    p = best[1]
                    ind = (p.get("industries") or [None])[0]
                    focus = (p["name"], p.get("value"), ind)

        # Fadenkreuz in der Mitte (Orientierung, wo cx/cy liegt). NACH den Markern,
        # damit es obenauf bleibt.
        safe_addstr(oy + map_ih // 2, ox + iw // 2, "+", C["warn"])

        # Status-/Hilfezeile unten in der Box: Position, Zoom, Steuerung.
        info = "lon %+.1f lat %+.1f · z%g · %s" % (
            M["cx"], M["cy"], M["zoom"], M["style"])
        if M["overlay"]:
            if focus:
                nm, val, _ind = focus
                info += " · ◆%s %s" % (nm, "—" if val is None else val)
            else:
                info += " · ◆Handel %s" % (ovintage or "?")
        addclip(by + bh - 2, ox, info, iw, C["bright"])
        hint = "↑↓←→ +/− 0·f·o·w·esc"
        if M["msg"]:
            hint = M["msg"]
        addclip(by + bh - 2, ox + iw - len(hint), hint, len(hint), C["faint"])

    while True:
        ch = stdscr.getch()

        if help_latched:
            if ch != -1:                       # jede Taste schließt die Hilfe wieder
                help_latched = False
        elif cmd_mode:
            if ch == 27:                       # Esc → Befehl abbrechen
                cmd_mode = False; cmd_buf = ""
            elif ch in (10, 13, curses.KEY_ENTER):
                res, theme_mode, cmd_msg = parse_command(cmd_buf, theme_mode)
                cmd_mode = False; cmd_buf = ""
                if res == "QUIT":
                    break
                if res == "HELP":
                    help_latched = True
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                cmd_buf = cmd_buf[:-1]
                if not cmd_buf:                # Slash weggelöscht → zu
                    cmd_mode = False
            elif 32 <= ch <= 126 and len(cmd_buf) < 120:
                cmd_buf += chr(ch)
        elif G["active"]:                      # Graph-Werkzeug hat den Fokus
            if G["view"] == "list":
                if G["confirm"]:                              # Lösch-Nachfrage offen
                    if ch in (ord("y"), ord("Y"), ord("j"), ord("J"),
                              10, 13, curses.KEY_ENTER):
                        try:
                            api_call("/api/graphs/" + G["graphs"][G["sel"]]["id"], method="DELETE")
                            G["msg"] = "gelöscht"
                        except Exception:
                            G["msg"] = "löschen fehlgeschlagen"
                        G["confirm"] = False
                        g_load()
                    elif ch != -1:                            # alles andere → abbrechen
                        G["confirm"] = False; G["msg"] = ""
                elif ch in (27, ord("g"), ord("G")):           # Esc/g → Werkzeug zu
                    G["active"] = False
                elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
                    break
                elif ch in (curses.KEY_UP, ord("k")):
                    G["sel"] = max(0, G["sel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    G["sel"] = min(max(0, len(G["graphs"]) - 1), G["sel"] + 1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    if G["graphs"]:
                        G["def"] = G["graphs"][G["sel"]]; G["input"] = ""; G["msg"] = ""
                        G["input2"] = ""; G["pstage"] = 0
                        G["view"] = "view"; g_load_vals()
                elif ch in (ord("n"), ord("N")):
                    G["view"] = "new"; G["input"] = ""; G["newtype"] = "number"; G["msg"] = ""
                elif ch in (ord("d"), ord("D")):
                    if G["graphs"]:
                        G["confirm"] = True; G["msg"] = ""
            elif G["view"] == "new":
                if ch == 27:
                    G["view"] = "list"; G["msg"] = ""
                elif ch == 9:                                  # Tab → Typ zyklieren
                    ids = [t[0] for t in GRAPH_TYPES]
                    G["newtype"] = ids[(ids.index(G["newtype"]) + 1) % len(ids)]
                elif ch in (10, 13, curses.KEY_ENTER):
                    name = G["input"].strip()
                    if not name:
                        G["msg"] = "name fehlt"
                    else:
                        try:
                            g = api_call("/api/graphs", method="POST",
                                         body={"name": name, "type": G["newtype"]})
                            g_load()
                            for i, x in enumerate(G["graphs"]):
                                if g and x["id"] == g.get("id"):
                                    G["sel"] = i
                            G["view"] = "list"; G["msg"] = "angelegt: " + name
                        except Exception:
                            G["msg"] = "anlegen fehlgeschlagen"
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    G["input"] = G["input"][:-1]
                elif 32 <= ch <= 126 and len(G["input"]) < 40:
                    G["input"] += chr(ch)
            elif G["view"] == "view":
                typ = G["def"].get("type") if G["def"] else "number"
                enter = ch in (10, 13, curses.KEY_ENTER)
                backsp = ch in (curses.KEY_BACKSPACE, 127, 8)
                if ch == 27:                                   # Esc: bei period erst bis→von zurück
                    if typ == "period" and G["pstage"] == 1:
                        G["pstage"] = 0; G["input2"] = ""; G["msg"] = ""
                    else:
                        G["view"] = "list"; G["input"] = ""; G["input2"] = ""
                        G["pstage"] = 0; G["msg"] = ""
                elif typ == "scale":
                    if ord("1") <= ch <= ord("5"):             # 1–5 trägt sofort ein
                        g_save(int(chr(ch)))
                elif typ == "number":
                    if enter:
                        txt = G["input"].strip()
                        if txt:
                            try:
                                g_save(float(txt)); G["input"] = ""
                            except ValueError:
                                G["msg"] = "keine zahl"
                    elif backsp:
                        G["input"] = G["input"][:-1]
                    elif (48 <= ch <= 57 or ch in (ord("."), ord("-"))) and len(G["input"]) < 12:
                        G["input"] += chr(ch)
                elif typ == "time":
                    if enter:
                        m = parse_clock(G["input"])
                        if m is None:
                            G["msg"] = "zeit? HH:MM"
                        else:
                            g_save(m); G["input"] = ""
                    elif backsp:
                        G["input"] = G["input"][:-1]
                    elif (48 <= ch <= 57 or ch == ord(":")) and len(G["input"]) < 5:
                        G["input"] += chr(ch)
                elif typ == "period":
                    cur = "input" if G["pstage"] == 0 else "input2"
                    if enter:
                        if G["pstage"] == 0:
                            if parse_clock(G["input"]) is None:
                                G["msg"] = "von? HH:MM"
                            else:
                                G["pstage"] = 1; G["msg"] = ""
                        else:
                            s, e = parse_clock(G["input"]), parse_clock(G["input2"])
                            if e is None:
                                G["msg"] = "bis? HH:MM"
                            else:
                                g_save(s, end=e)
                                G["input"] = ""; G["input2"] = ""; G["pstage"] = 0
                    elif backsp:
                        G[cur] = G[cur][:-1]
                    elif (48 <= ch <= 57 or ch == ord(":")) and len(G[cur]) < 5:
                        G[cur] += chr(ch)
        elif M["active"]:                      # Karte hat den Fokus
            if ch in (27, ord("m"), ord("M")):                 # Esc/m → Karte zu
                M["active"] = False
            elif ch in (ord("q"), ord("Q")):                   # q → ganze TUI beenden
                break
            elif ch in (curses.KEY_LEFT, ord("h")):
                m_pan(-0.30, 0.0)
            elif ch in (curses.KEY_RIGHT, ord("l")):
                m_pan(0.30, 0.0)
            elif ch in (curses.KEY_UP, ord("k")):
                m_pan(0.0, 0.30)               # nach Norden
            elif ch in (curses.KEY_DOWN, ord("j")):
                m_pan(0.0, -0.30)              # nach Süden
            elif ch in (ord("+"), ord("=")):   # '=' = '+' ohne Shift
                m_zoom(1.0)
            elif ch in (ord("-"), ord("_")):
                m_zoom(-1.0)
            elif ch == ord("0"):               # zurück zur ganzen Welt
                M["cx"], M["cy"], M["zoom"], M["data"] = 0.0, 20.0, 0.0, None
            elif ch in (ord("f"), ord("F")):   # Stil: Umriss ↔ Braille-Füllung
                M["style"] = "braille" if M["style"] == "outline" else "outline"
                M["data"] = None               # Neuladen mit neuem Endpoint
            elif ch in (ord("o"), ord("O")):   # Handelsrouten-Overlay ein/aus
                M["overlay"] = not M["overlay"]
                M["odata"] = None              # beim Einschalten frisch holen
            elif ch in (ord("w"), ord("W"), 10, 13, curses.KEY_ENTER):
                m_window()                     # natives Fenster aufklappen
            elif ch in (ord("t"), ord("T")):   # Theme darf auch hier zyklieren
                theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
        else:                                  # Normal-Modus: Shortcuts aktiv
            if ch in (ord("q"), ord("Q")):
                break
            elif ch in (ord("t"), ord("T")):   # Theme zyklieren
                theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
            elif ch in (ord("g"), ord("G")):   # Graph-Werkzeug öffnen
                G["active"] = True; G["view"] = "list"; G["msg"] = ""; g_load()
            elif ch in (ord("m"), ord("M")):   # Karte öffnen
                M["active"] = True; M["data"] = None
            elif ch == ord("/"):               # Befehlszeile öffnen
                cmd_mode = True; cmd_buf = "/"; cmd_msg = ""
        # KEY_RESIZE oder Timeout → einfach neu zeichnen

        # Theme nachziehen (auto wechselt nach Uhrzeit, oder nach 't'/Befehl)
        want = resolved_theme()
        if want != cur_theme:
            cur_theme = want
            apply_theme(cur_theme)

        state, metrics, connected = store.snapshot()
        gs_cache, gv_cache = store.graphs_snapshot()
        H, W = stdscr.getmaxyx()
        stdscr.erase()

        if terminal_too_small(H, W):
            safe_addstr(0, 0, "Terminal zu klein (min 60x14).", C["warn"])
            safe_addstr(1, 0, "q = quit", C["dim"])
            stdscr.refresh()
            continue

        # ── Header ──────────────────────────────────────────────────────
        safe_addstr(0, 1, "ZEN", C["bright"] | curses.A_REVERSE)
        safe_addstr(0, 4, "TRALE", C["acc"])
        safe_addstr(0, 11, "tui · kassette", C["dim"])

        nets = state.get("internet_logs", []) or []
        if not isinstance(nets, list):
            nets = []
        if nets:
            net_txt, net_attr = "TRAFFIC !", C["warn"]
        else:
            net_txt, net_attr = "OFFLINE ✓", C["acc"]
        clock = time.strftime("%H:%M:%S")
        up = fmt_uptime(state.get("uptime_s"))
        right = "NET %s   UP %s   %s" % (net_txt, up, clock)
        safe_addstr(0, W - len(right) - 1, "NET ", C["dim"])
        safe_addstr(0, W - len(right) - 1 + 4, net_txt, net_attr)
        safe_addstr(0, W - len(right) - 1 + 4 + len(net_txt), "   UP %s   %s" % (up, clock), C["dim"])
        if not connected:
            safe_addstr(0, 26, "[backend ?]", C["warn"] | curses.A_BLINK)
        safe_addstr(1, 0, "─" * W, C["faint"])

        # ── Spalten-Geometrie ─────────────────────────────────────────────
        top = 2
        footer_row = H - 1                # Tasten-Hinweise
        input_row = H - 2                 # Befehlszeile (›)
        sep_row = H - 3                   # Trennlinie + „Luft" nach unten
        bot = H - 4                       # Body endet hier
        body_h = bot - top + 1
        leftw = max(24, int(W * 0.28))
        rightw = max(22, int(W * 0.27))
        midw = W - leftw - rightw
        lx, mx, rx = 0, leftw, leftw + midw

        # ── LINKS: telemetrie / stdout ─────────────────────────────────
        # (Sensoren-Panel entfernt 2026-06: kein echter Sensor angeschlossen.
        #  /api/state.sensors wird weiter gepollt, nur nicht mehr gezeichnet —
        #  Box zum Wiederanzeigen aus der git-History zurückholen.)
        tele_h = len(TELE_ROWS) + 2
        std_h = body_h - tele_h
        ty = top
        draw_box(ty, lx, tele_h, leftw, "telemetrie")
        for i, (lbl, key, _u) in enumerate(TELE_ROWS):
            tv = tele_value(metrics, key)
            safe_addstr(ty + 1 + i, lx + 2, "LAP·" + lbl, C["acc"])
            if tv:
                pct, text = tv
                n = round(max(0.0, min(100.0, pct)) / 100.0 * 10)
                safe_addstr(ty + 1 + i, lx + 11, "█" * n, C["acc"])
                safe_addstr(ty + 1 + i, lx + 11 + n, "░" * (10 - n), C["faint"])
                safe_addstr(ty + 1 + i, lx + leftw - len(text) - 2, text, C["bright"])
            else:
                safe_addstr(ty + 1 + i, lx + 11, "n/a", C["faint"])

        sy = ty + tele_h
        if std_h >= 3:
            draw_box(sy, lx, std_h, leftw, "stdout")
            logs = state.get("logs", []) or []
            if not isinstance(logs, list):
                logs = []
            inner = std_h - 2
            shown = logs[-inner:]
            for i, e in enumerate(shown):
                if not isinstance(e, dict):
                    continue
                yy = sy + 1 + i
                t = (e.get("time") or "")[:8]
                safe_addstr(yy, lx + 2, t, C["faint"])
                px = lx + 2 + len(t) + 1
                # Nachricht auf die Box-Innenbreite kürzen, damit nichts in die
                # Mittelspalte überläuft (lx+leftw-1 ist der rechte Rahmen).
                avail = (lx + leftw - 1) - px
                txt = (e.get("text") or "")[:max(0, avail)]
                head, grp = log_prefix(txt)
                if head and grp:
                    safe_addstr(yy, px, head, C.get(grp, C["dim"]))
                    safe_addstr(yy, px + len(head), txt[len(head):], C["dim"])
                else:
                    safe_addstr(yy, px, txt, C["dim"])

        # ── MITTE: Graph-Werkzeug / Karte (oder Einladung, sie zu öffnen) ──
        if G["active"]:
            draw_box(top, mx, body_h, midw, "graph-werkzeug")
            draw_graph_tool(top, mx, body_h, midw, gv_cache)
        elif M["active"]:
            draw_box(top, mx, body_h, midw, "karte · welt")
            draw_map(top, mx, body_h, midw)
        else:
            draw_box(top, mx, body_h, midw, "mitte")
            cyc = top + body_h // 2
            big = "KASSETTE · TUI"
            l1 = "g · graph-werkzeug"
            l2 = "m · karte"
            addclip(cyc - 1, mx + max(1, (midw - len(big)) // 2), big, midw - 2, C["bright"])
            addclip(cyc + 1, mx + max(1, (midw - len(l1)) // 2), l1, midw - 2, C["acc"])
            addclip(cyc + 2, mx + max(1, (midw - len(l2)) // 2), l2, midw - 2, C["acc"])

        # ── RECHTS: lifestyle / outbound ──────────────────────────────────
        # lifestyle = ÜBERLAGERUNG aller Graphen in EINEM Gitter. X = Datum
        # (Zeitstrahl), Y bewusst MEHRDEUTIG — jeder Graph nutzt seine eigene
        # Achse + Darstellung, alles übereinandergelegt zum Vergleich:
        #   period → Balken █ über die Zeitspanne (24h-Skala, 00:00 unten)
        #   time   → Punkt auf der 24h-Skala
        #   scale  → Punkt auf der eigenen 1–5-Skala
        #   number → Punkt auf der eigenen min/max-Spanne (sichtbare Werte)
        # Eigener Marker + Farbe je Graph (+ Legende). Quelle:
        # store.graphs_snapshot (langsames Hintergrund-Polling).
        if gs_cache:
            life_h = min(body_h - 4, max(7, body_h - 8))
        else:
            life_h = 4
        out_h = body_h - life_h
        draw_box(top, rx, life_h, rightw, "lifestyle")
        # Farb-Palette, je Graph eine (durchgezykelt). Unterschieden wird über
        # die FARBE, nicht über fette Symbole — gezeichnet als dünne Linien.
        LIFE_COL = ["graph", "acc", "warn", "net", "event", "audio", "hook", "num"]
        if gs_cache:
            plot_x = rx + 2
            plot_w = max(2, rightw - 4)
            inner_h = life_h - 2
            # pro Graph: {datum: roh-eintrag}, Typ, Farbe. Roh halten, weil period
            # zwei Werte (start+end) braucht und Zahlen ihre eigene Spanne über
            # alle sichtbaren Werte ziehen.
            series = []
            for i, g in enumerate(gs_cache):
                if not isinstance(g, dict):
                    continue
                rows = gv_cache.get(g.get("id")) or []
                dv = {}
                for e in rows if isinstance(rows, list) else []:
                    if not isinstance(e, dict):
                        continue
                    if _num(e.get("value")) is None or not e.get("date"):
                        continue
                    dv[e["date"]] = e
                if dv:
                    series.append({"name": g.get("name", "?"), "type": g.get("type"),
                                   "dv": dv, "col": LIFE_COL[i % len(LIFE_COL)]})
            # Legende packen (mehrere pro Zeile): farbiges Linien-Sample + Name —
            # verbraucht Zeilen, die dem Plot fehlen.
            leg_lines, cur_w = [[]], 0
            for s in series:
                nm = s["name"][:8]
                tok = "─ " + nm
                if cur_w + len(tok) + 1 > plot_w and leg_lines[-1]:
                    leg_lines.append([]); cur_w = 0
                leg_lines[-1].append((nm, s["col"]))
                cur_w += len(tok) + 1
            max_leg = min(len(leg_lines), max(1, inner_h - 3))
            plot_h = max(2, inner_h - max_leg)
            base = top + 1                         # oberste Plot-Zeile

            def row_clock(m):                      # 24h-Skala: 0 unten, 1440 oben
                m = max(0, min(1440, m))
                return base + (plot_h - 1) - int(round(m / 1440.0 * (plot_h - 1)))

            def row_norm(v, lo, hi):               # eigene Spanne: lo unten, hi oben
                n = 0.5 if hi is None or hi == lo else (float(v) - lo) / (hi - lo)
                n = max(0.0, min(1.0, n))
                return base + (plot_h - 1) - int(round(n * (plot_h - 1)))

            if series:
                # X = FESTES Fenster der letzten 7 Tage (heute rechts, 6 Tage
                # zurück nach links), über die volle Plotbreite verteilt — egal
                # wie viel schon gefüllt ist. Tage ohne Eintrag bleiben leer.
                NDAYS = 7
                today = date.today()
                window = [(today - timedelta(days=k)).isoformat()
                          for k in range(NDAYS - 1, -1, -1)]   # alt → neu
                col_idx = {d: (plot_w - 1 if NDAYS == 1
                               else int(round(i / (NDAYS - 1) * (plot_w - 1))))
                           for i, d in enumerate(window)}
                cols = window
                for s in series:
                    typ, col, dv = s["type"], s["col"], s["dv"]
                    # eigene min/max-Spanne nur für number (über sichtbare Werte)
                    lo = hi = None
                    if typ == "number":
                        vis = [_num(dv[d].get("value")) for d in cols if d in dv]
                        vis = [x for x in vis if x is not None]
                        if vis:
                            lo, hi = min(vis), max(vis)
                    pts = []                          # (cx, row) für die Linie
                    for d, e in dv.items():
                        ci = col_idx.get(d)
                        if ci is None:
                            continue
                        cx = plot_x + ci
                        v = _num(e.get("value"))
                        end = _num(e.get("end"))
                        if typ == "period" and end is not None:
                            # Zeitspanne → dünne VERTIKALE Linie über den Bereich
                            st, en = int(v), int(end)
                            segs = ([(st, en)] if en >= st
                                    else [(st, 1440), (0, en)])   # Wrap Mitternacht
                            for a, b in segs:
                                r0, r1 = sorted((row_clock(a), row_clock(b)))
                                for r in range(r0, r1 + 1):
                                    safe_addstr(r, cx, "│", C[col])
                            continue
                        if typ in ("time", "period"):
                            r = row_clock(int(v))
                        elif typ == "scale":
                            r = row_norm(v, 1, 5)
                        else:                                     # number
                            r = row_norm(v, lo, hi)
                        pts.append((cx, r))
                    # Einzelpunkte zu einer dünnen Linie verbinden (Steigung →
                    # ╱ steigt, ╲ fällt, ─ flach; senkrecht → │). Einzelner Punkt → ·
                    pts.sort()
                    if len(pts) == 1:
                        safe_addstr(pts[0][1], pts[0][0], "·", C[col])
                    else:
                        for (c1, r1), (c2, r2) in zip(pts, pts[1:]):
                            if c2 == c1:
                                for r in range(min(r1, r2), max(r1, r2) + 1):
                                    safe_addstr(r, c1, "│", C[col])
                                continue
                            ch = "─" if r2 == r1 else ("╲" if r2 > r1 else "╱")
                            for c in range(c1, c2 + 1):
                                t = (c - c1) / (c2 - c1)
                                r = int(round(r1 + t * (r2 - r1)))
                                safe_addstr(r, c, ch, C[col])
                # Legende unter den Plot: farbiges Linien-Sample + Name
                for li, line in enumerate(leg_lines[:max_leg]):
                    yy = base + plot_h + li
                    cx = plot_x
                    for nm, col in line:
                        safe_addstr(yy, cx, "─", C[col])
                        addclip(yy, cx + 2, nm, plot_w - (cx - plot_x) - 2, C["dim"])
                        cx += 2 + len(nm) + 1
            else:
                safe_addstr(top + 1, rx + 2, "// noch keine werte", C["faint"])
        else:
            safe_addstr(top + 1, rx + 2, "// noch keine graphen (g)", C["faint"])
        oy = top + life_h
        draw_box(oy, rx, out_h, rightw, "outbound", C["warn"])
        if nets:
            inner = out_h - 2
            for i, e in enumerate(nets[-inner:]):
                if not isinstance(e, dict):
                    continue
                yy = oy + 1 + i
                t = (e.get("time") or "")[:8]
                safe_addstr(yy, rx + 2, t, C["faint"])
                px = rx + 2 + len(t) + 1
                avail = (rx + rightw - 1) - px
                addclip(yy, px, e.get("text") or "", avail, C["warn"])
        else:
            safe_addstr(oy + 1, rx + 2, "// offline ✓", C["acc"] | curses.A_DIM)

        # ── Befehls-Overlay (klappt über den Body nach oben auf) ──────────
        if cmd_mode or help_latched:
            ov_title, rows = overlay_rows(cmd_buf, help_latched)
            ov_w = min(W - 4, 56)
            ov_h = len(rows) + 2
            ov_x = 2
            ov_y = max(top, bot - ov_h + 1)
            draw_box(ov_y, ov_x, ov_h, ov_w, ov_title)
            for i, r in enumerate(rows):
                yy = ov_y + 1 + i
                if r[0] == "cmd":
                    addclip(yy, ov_x + 2, r[1], 9, C["acc"])
                    addclip(yy, ov_x + 12, r[2], ov_w - 14, C["dim"])
                elif r[0] == "key":
                    addclip(yy, ov_x + 2, r[1], 7, C["num"])
                    addclip(yy, ov_x + 10, r[2], ov_w - 12, C["dim"])
                elif r[0] == "sep":
                    safe_addstr(yy, ov_x + 1, "─" * (ov_w - 2), C["faint"])
                else:
                    addclip(yy, ov_x + 2, r[2], ov_w - 4, C["faint"])

        # ── Trennlinie + Befehlszeile (›) ─────────────────────────────────
        safe_addstr(sep_row, 0, "─" * W, C["faint"])
        if cmd_mode:
            safe_addstr(input_row, 1, "›", C["acc"])
            shown = cmd_buf[-(W - 6):]
            addclip(input_row, 3, shown, W - 6, C["bright"])
            safe_addstr(input_row, 3 + len(shown), "_", C["bright"])
        else:
            safe_addstr(input_row, 1, "›", C["faint"])
            if cmd_msg:
                addclip(input_row, 3, cmd_msg, W - 6, C["warn"])
            else:
                safe_addstr(input_row, 3, "/ für befehle", C["faint"])

        # ── Footer (Tasten + Theme + Backend) ─────────────────────────────
        tm_txt = "auto(%s)" % cur_theme if theme_mode == "auto" else cur_theme
        addclip(footer_row, 0,
                " q quit · t theme: %s · g graph · m karte · / befehle · %s" % (tm_txt, BASE_URL),
                W - 1, C["faint"])

        stdscr.refresh()


# Default-Pfad bleibt fix (start_tui.sh liest genau diesen); per Env überstimmbar,
# damit z.B. die Fuzz-Tests pro Session ein eigenes, isoliertes Log bekommen.
CRASH_LOG = os.environ.get("ZENTRALE_TUI_CRASH_LOG") or "/tmp/zentrale-tui-crash.log"


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    # Ohne echtes Terminal kann curses nicht initialisieren (und segfaultet im
    # schlimmsten Fall beim Aufräumen). Lieber früh mit klarer Ansage + Code 2
    # raus, statt kryptisch zu sterben. Headless prüfen geht über --selftest.
    if not sys.stdout.isatty():
        sys.stderr.write("ZENTRALE-TUI braucht ein echtes Terminal (TTY).\n"
                         "Headless-Check stattdessen:  zentrale_tui.py --selftest\n")
        sys.exit(2)

    # Altes Crash-Log wegräumen, damit ein später angezeigtes Log GARANTIERT
    # aus DIESEM Lauf stammt (sonst zeigt das Start-Skript evtl. einen alten
    # Absturz an und schickt die Diagnose in die Irre).
    try:
        os.remove(CRASH_LOG)
    except OSError:
        pass

    # UTF-8-Locale, damit curses die Box-/Block-Zeichen (┌ █ ░ ✓ ·) korrekt
    # rendert statt als Müll. Muss VOR dem curses-Init stehen.
    import locale
    locale.setlocale(locale.LC_ALL, "")

    import curses
    import traceback
    store = Store()
    poller = threading.Thread(target=store.run, daemon=True)
    poller.start()

    # ── Sicherheitsnetz: die TUI darf NIEMALS an einer einzelnen Exception
    # sterben. ──────────────────────────────────────────────────────────────
    # curses.wrapper läuft in einer Retry-Schleife: wirft run_ui (z.B. weil das
    # Backend mal kurz kaputte/unerwartete Daten liefert), setzt sich die TUI
    # einfach neu auf und läuft weiter — der Nutzer sieht höchstens ein kurzes
    # Flackern statt eines Absturzes. Nur DAUERFEUER (viele Crashes in kurzer
    # Zeit → dauerhaft defekter Zustand) bricht hart ab, statt ewig zu zappeln.
    # ZENTRALE_TUI_FRAME_ERR_LOG (optional) sammelt jeden abgefangenen Traceback
    # zum Nachsehen, ohne dass er die Sitzung killt (von den Fuzz-Tests genutzt).
    frame_err_log = os.environ.get("ZENTRALE_TUI_FRAME_ERR_LOG")
    recent = []                       # monotone Zeitstempel der letzten Recoveries
    try:
        while True:
            try:
                curses.wrapper(run_ui, store)
                break                 # sauberer Quit (q / Befehl /quit)
            except KeyboardInterrupt:
                # Ctrl-C = gewollter Quit (wie 'q'). Sauberer Exit (rc 0), damit
                # das Start-Skript die tmux-Session SOFORT abräumt statt mit
                # "kein sauberer Quit" auf einen Tastendruck zu warten.
                break
            except Exception:
                tb = traceback.format_exc()
                if frame_err_log:
                    try:
                        with open(frame_err_log, "a", encoding="utf-8") as f:
                            f.write(tb + "\n--- recover ---\n")
                    except OSError:
                        pass
                now = time.monotonic()
                recent.append(now)
                recent[:] = [t for t in recent if now - t < 10.0]
                if len(recent) > 25:          # >25 Crashes in 10 s → echtes Dauerproblem
                    raise
                # sonst: transienter Fehler → run_ui neu starten, TUI lebt weiter
    except Exception:
        # Endgültig (über dem Raten-Limit): curses.wrapper hat das Terminal schon
        # zurückgesetzt; Traceback in eine Datei UND nach stderr. Exit-Code 1
        # signalisiert dem Start-Skript "kein sauberer Quit" (siehe start_tui.sh).
        tb = traceback.format_exc()
        try:
            with open(CRASH_LOG, "w", encoding="utf-8") as f:
                f.write("ZENTRALE-TUI Crash (Backend: %s)\n\n%s" % (BASE_URL, tb))
        except OSError:
            pass
        sys.stderr.write("\nZENTRALE-TUI abgestürzt:\n%s\n(gespeichert in %s)\n"
                         % (tb, CRASH_LOG))
        store.stop()
        sys.exit(1)
    finally:
        store.stop()


if __name__ == "__main__":
    main()
