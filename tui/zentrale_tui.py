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
import urllib.parse

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
        self.projects = []     # /api/projects (geflaggte Listen, für PROJECTS-Box)
        self.backends = {}     # /api/ai/backends (EXTERNAL-Box: local/cloud erreichbar)
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

    def _poll_projects(self):
        """Als Projekt geflaggte Listen samt Erfüllungsgrad ziehen (PROJECTS-Box)."""
        try:
            pr = self._get("/api/projects") or []
            with self._lock:
                self.projects = pr if isinstance(pr, list) else []
        except (urllib.error.URLError, OSError, ValueError):
            pass

    def _poll_backends(self):
        """Welche AI-Backends sind erreichbar (local/cloud) – für die EXTERNAL-Box.
        Front-agnostisch dieselbe Quelle wie der Browser (/api/ai/backends)."""
        try:
            bk = self._get("/api/ai/backends") or {}
            with self._lock:
                self.backends = bk if isinstance(bk, dict) else {}
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
        self._poll_projects()
        self._poll_backends()
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
                self._poll_projects()
                self._poll_backends()          # AI-Backend-Status (EXTERNAL-Box)
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

    def projects_snapshot(self):
        """Liste der geflaggten Projekte ({id,name,done,total}) für die PROJECTS-Box."""
        with self._lock:
            return [dict(p) for p in self.projects if isinstance(p, dict)]

    def backends_snapshot(self):
        """AI-Backend-Status ({local,cloud,cloud_provider,any}) für die EXTERNAL-Box."""
        with self._lock:
            return dict(self.backends)


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


def host_label(metrics):
    """Kurz-Kürzel für die Telemetrie-Box: WELCHE Maschine liefert die Werte?

    Zwischenprüfung statt hartem Label: die /api/telemetry.pc-Werte stammen vom
    HOST DES BACKENDS, nicht von der Maschine, auf der diese TUI läuft (die TUI
    ist nur HTTP-Client). Das Backend legt seinen Hostnamen in pc.host ab
    (core/telemetry.pc_snapshot). Bekannte Hosts → griffiges Kürzel, sonst der
    echte Hostname auf 4 Zeichen gekappt (nie wieder ein falsches "LAP")."""
    src = (metrics or {}).get("pc") if isinstance(metrics, dict) else None
    host = (src.get("host") if isinstance(src, dict) else "") or ""
    h = host.lower()
    if "0ram" in h or "lap" in h:
        return "LAP"
    if "pop" in h or h == "pc":
        return "PC"
    if "zentrale" in h or h.startswith("pi"):
        return "PI"
    return host[:4].upper() or "HOST"


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
    bk = store.backends_snapshot()
    print("  ai-backends         :", "local=%s cloud=%s%s" % (
        bool(bk.get("local")), bool(bk.get("cloud")),
        (" (" + bk["cloud_provider"] + ")") if bk.get("cloud_provider") else ""))
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
    def _lcount(items):           # erledigt/gesamt über die BLÄTTER (wie in der TUI)
        d = t = 0
        for i in items or []:
            if not isinstance(i, dict):
                continue
            kids = i.get("items")
            if isinstance(kids, list) and kids:   # Ordner → nur seine Blätter
                cd, ct = _lcount(kids); d += cd; t += ct
            else:
                t += 1; d += 1 if i.get("done") else 0
        return d, t
    ll = store._get("/api/lists") or []
    print("  listen             :", [l.get("id") for l in ll] or "—")
    for l in ll:
        done, total = _lcount(l.get("items"))
        flag = " ◆projekt" if l.get("project") else ""
        print("    %-16s :" % l.get("name"), "%d/%d erledigt%s" % (done, total, flag))
    pr = store._get("/api/projects") or []
    print("  projekte (rechts)  :", [p.get("name") for p in pr] or "—")
    def _pp(node, depth=0):                       # Projekt-Baum eingerückt drucken
        kids = node.get("children") or []
        head = "    " + "  " * depth + ("▸ " if kids else "• ")
        print(head + "%s  %d/%d" % (node.get("name"), node.get("done"), node.get("total")))
        for c in kids:
            _pp(c, depth + 1)
    for p in pr:
        _pp(p)
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
    ("g",   "Graph-Werkzeug (Mitte): anlegen / eintragen · p vorhersage-ergänzung an/aus"),
    ("l",   "Listen (Mitte): anlegen · einträge abhaken (space) / löschen · p als projekt rechts"),
    ("m",   "Karte (Mitte): pan ↑↓←→/hjkl · zoom +/− · 0 reset · Alt+↑↓←→ Land fokussieren · o=Handelsrouten · w=Fenster"),
    ("c",   "Kalender (Mitte): ↑↓ wählen · e bearbeiten · a neu · d löschen/Routine-aus · ←→ blättern · v Woche/Monat"),
    ("p",   "Post/Mail (Mitte): ↑↓ blättern · enter rein · v lesen/liste · e ausklappen · Bild↑↓ scrollen · a antw · s einsort · d lösch · esc zurück"),
    ("/",   "Befehlszeile öffnen"),
    ("Esc", "Befehl bzw. Hilfe schließen"),
]

# Kontext-Shortcuts: welche Tasten zeigt '/' im jeweils fokussierten Fenster.
# Single Source of Truth — die Box-Fußzeilen tragen diese langen Listen NICHT
# mehr fest ein (sie schnitten ab); '/' blendet sie bei Bedarf auf. Die Tasten
# selbst greifen weiterhin direkt, ganz ohne Slash. Schlüssel = Kontext aus
# current_ctx(); Reihenfolge spiegelt die alten Fußzeilen.
CTX_KEYS = {
    "home": [
        ("l", "listen"), ("g", "graph"), ("m", "karte"),
        ("c", "kalender"), ("p", "post / mail"),
        ("t", "theme"), ("q", "beenden"),
    ],
    "graph": [
        ("↑↓", "wählen"), ("enter", "öffnen"),
        ("n", "neu"), ("d", "löschen"), ("esc", "zu"),
    ],
    "list:list": [
        ("enter", "öffnen"), ("n", "neu"), ("s", "kind"),
        ("r", "name"), ("p", "projekt"), (">", "einordnen"),
        ("d", "weg"), ("esc", "zu"),
    ],
    "list:view": [
        ("enter", "rein / hak"), ("space", "hak"), ("a/s", "neu"),
        ("r", "name"), ("p", "projekt"), (">", "einordnen"),
        ("m", "raus"), ("d", "weg"), ("esc", "zurück"),
    ],
    "list:pick": [
        ("↑↓", "wählen"), ("enter", "übernehmen"), ("esc", "abbrechen"),
    ],
    "map": [
        ("↑↓←→", "pan (auch hjkl)"), ("+/−", "zoom"), ("0", "reset"),
        ("Alt+↑↓←→", "land fokussieren"),
        ("o", "handelsrouten"), ("w", "fenster"), ("esc", "zu"),
    ],
    "cal:week": [
        ("↑↓", "wählen"), ("e", "bearbeiten"), ("a", "neu"),
        ("d", "löschen / aus"), ("←→", "woche"), ("v", "monat"),
    ],
    "cal:month": [
        ("←→", "blättern"), ("v", "woche"), ("a", "neu"),
        ("0", "heute"), ("esc", "zu"),
    ],
    "mail:cats": [
        ("↑↓", "wählen"), ("enter", "öffnen"), ("r", "poll"), ("esc", "zu"),
    ],
    "mail:list": [
        ("↑↓", "wählen"), ("enter", "lesen"), ("a", "antworten"),
        ("s", "einsortieren"), ("d", "löschen"), ("esc", "zurück"),
    ],
    "mail:read": [
        ("↑↓", "blättern"), ("e", "ausklappen"), ("a", "antworten"),
        ("s", "einsortieren"), ("d", "löschen"), ("v", "liste"), ("esc", "zurück"),
    ],
}
CTX_TITLES = {
    "home": "start", "graph": "graph", "list:list": "listen",
    "list:view": "liste", "list:pick": "einordnen", "map": "karte",
    "cal:week": "kalender · woche", "cal:month": "kalender · monat",
    "mail:cats": "post", "mail:list": "post · liste", "mail:read": "post · lesen",
}


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


def overlay_rows(cmd_buf, help_latched, ctx=None):
    """
    Welche Zeilen zeigt das Befehls-Overlay? PURE Funktion → (titel, rows).
    rows-Einträge: ("cmd", name, desc) | ("key", taste, desc) | ("sep",) |
    ("info", "", text).

    - '/help' (oder help_latched) → volle Hilfe inkl. globaler Tasten.
    - nacktes '/' → die Shortcuts des FOKUSSIERTEN Fensters (ctx) plus die
      globalen Slash-Befehle darunter. ctx = (titel, [(taste, desc), …]) oder
      None (dann nur die globalen Befehle).
    - '/<präfix>' → live-gefilterte Slash-Befehlsliste.
    """
    full = help_latched or cmd_buf.startswith("/help")
    if full:
        rows = [("cmd", n, d) for n, d in TUI_COMMANDS]
        rows += [("sep",)]
        rows += [("key", k, d) for k, d in TUI_KEYS]
        return "hilfe", rows
    pref = cmd_buf[1:].split(" ")[0].lower()
    if not pref:                       # nacktes '/': Kontext-Tasten + globale Befehle
        title, keys = ctx if ctx else ("befehle", [])
        rows = [("key", k, d) for k, d in keys]
        if keys:
            rows += [("sep",)]
        rows += [("cmd", n, d) for n, d in TUI_COMMANDS]
        return title, rows
    hits = [(n, d) for n, d in TUI_COMMANDS if n[1:].startswith(pref)]
    rows = [("cmd", n, d) for n, d in hits] or [("info", "", "kein treffer")]
    return "befehle", rows


class _OverlayScreen:
    """Adapter, der render_overlay_body die zwei Zeichen-Primitive reicht, ohne
    dass die Funktion curses kennt. In run_ui mit safe_addstr/addclip befuellt,
    im Test (tests/test_tui_overlay.py) mit einem Zell-Fake derselben Signatur
    → render_overlay_body ist als reine Bildfunktion pruefbar."""
    __slots__ = ("_fill", "_put")

    def __init__(self, fill, put):
        self._fill, self._put = fill, put

    def fill(self, y, x, n, ch, attr=0):
        self._fill(y, x, n, ch, attr)

    def put(self, y, x, text, maxw, attr=0):
        self._put(y, x, text, maxw, attr)


def render_overlay_body(scr, rows, ov_x, ov_y, ov_w, attrs):
    """Zeichnet die Innenzeilen des Befehls-Overlays — DECKEND.

    Curses kennt keine Z-Order/Opazitaet: der Body-stdout ist schon gezeichnet,
    wenn das Overlay drueberklappt. Wo eine Overlay-Zeile kuerzer war als die
    Kasten-Innenbreite, blieb frueher der stdout darunter stehen und „blutete"
    in den Kasten. Fix: JEDE Zeile zuerst ueber die volle Innenbreite blanken,
    erst dann den Inhalt drauf bestempeln.

    Curses-frei: zeichnet ausschliesslich ueber das scr-Adapterobjekt mit genau
    zwei Primitiven — fill(y,x,n,ch,attr) blankt n Zellen, put(y,x,text,maxw,attr)
    schreibt auf maxw gekuerzt. So 1:1 gegen einen Fake-Screen testbar.

    rows-Format wie overlay_rows(): ("cmd",name,desc) | ("key",taste,desc) |
    ("sep",) | ("info","",text). attrs mappt die Rollen acc/num/dim/faint.
    """
    inner_x = ov_x + 1            # erste Innenspalte (rechts vom linken Rahmen)
    inner_w = ov_w - 2            # Innenbreite zwischen den senkrechten Raendern
    for i, r in enumerate(rows):
        yy = ov_y + 1 + i
        if r[0] == "sep":
            # Trennlinie deckt die volle Innenbreite schon selbst ab
            scr.fill(yy, inner_x, inner_w, "─", attrs["faint"])
            continue
        # 1) deckend blanken  2) Inhalt drauf
        scr.fill(yy, inner_x, inner_w, " ", attrs["faint"])
        if r[0] == "cmd":
            scr.put(yy, ov_x + 2, r[1], 9, attrs["acc"])
            scr.put(yy, ov_x + 12, r[2], ov_w - 14, attrs["dim"])
        elif r[0] == "key":
            scr.put(yy, ov_x + 2, r[1], 7, attrs["num"])
            scr.put(yy, ov_x + 10, r[2], ov_w - 12, attrs["dim"])
        else:                     # "info" / Fallback
            scr.put(yy, ov_x + 2, r[2], ov_w - 4, attrs["faint"])


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
             "dim", "faint", "bright", "ink", "band"]
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
            # Schlaf-Bande: gedämpftes Dunkelmagenta als ZELLEN-HINTERGRUND
            "band_fg": 245, "band_bg": 53,
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
            # Schlaf-Bande: hell-magenta angehauchtes Grau als ZELLEN-HINTERGRUND
            "band_fg": 240, "band_bg": 225,
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
            if r == "band":
                continue                       # eigener Hintergrund, siehe unten
            c8, c2, extra = th[r]
            fg = c2 if c256 else c8
            # 8-Farben: reinweißer Text geht nur via A_BOLD (bright white)
            if not c256 and fg == curses.COLOR_WHITE and r in ("dim", "ink", "bright"):
                extra |= curses.A_BOLD
            curses.init_pair(i, fg, bg)
            C[r] = curses.color_pair(i) | extra
        # Schlaf-Bande: GEFÄRBTER HINTERGRUND, kein Vordergrund. curses kennt
        # keine Schichten — "hinter den Kurven" heißt: die Zelle bekommt eine
        # bg-Farbe, Punkt/Kurve wird als Glyph DAVOR in dieselbe Zelle gesetzt.
        # Echtes bg-Färben geht nur mit 256 Farben; sonst Schattenblock ▒.
        bi = ROLES.index("band") + 1
        if c256:
            curses.init_pair(bi, th["band_fg"], th["band_bg"])
            C["band"] = curses.color_pair(bi)
            C["band_is_bg"] = True
            # "Auf-Band"-Varianten: gleiche fg jeder Rolle, aber band-bg. Eine
            # Kurve, die DURCH die Bande läuft, wird damit gezeichnet → ihr Glyph
            # liegt sichtbar VOR dem Band, statt ein Loch (Theme-bg) zu stanzen.
            pp = len(ROLES) + 1
            for r in ROLES:
                if r in ("band", "ink"):
                    continue
                _c8, c2, extra = th[r]
                curses.init_pair(pp, c2, th["band_bg"])
                C[r + "@band"] = curses.color_pair(pp) | extra
                pp += 1
        else:
            C["band"] = C["faint"]
            C["band_is_bg"] = False
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
         "dayoff": 0,                  # Ziel-Tag: 0=heute, N=N Tage zurück (←/→)
         "confirm": False}             # Lösch-Nachfrage aktiv (Mini-Dialog)

    # ── Listen-Werkzeug (füllt die MITTE-Box, Taste 'l') ────────────────
    # Pendant zum Graph-Werkzeug, aber für abhakbare Todo-/Sammel-Listen.
    # Geteilte Logik (core/lists.py + /api/lists), hier in der TUI verbaut.
    #   active : Werkzeug hat den Fokus
    #   view   : "list" (Listen wählen) | "new" (anlegen) | "view" (Einträge)
    #            | "place" (Knoten Forest-weit einordnen, ">" auf Liste/Eintrag)
    #   sel    : ausgewählte Liste (in "list"); isel: ausgewählter Eintrag (in "view")
    #   adding : in "view" tippen wir gerade einen neuen Eintrag (input)
    #   addparent: id des Eltern-Eintrags beim Tippen (None = oberste Ebene)
    #   imode  : was die Eingabezeile tut — "add"|"sub"|"rename"
    #   edit_iid: beim Umbenennen die id des Eintrags (imode "rename")
    #   lrename: in "new" benennen wir eine bestehende Liste um (id) statt neu
    #   move_iid/nsel: zu verschiebender Eintrag + Zielauswahl ("move"/"move_new")
    #   place_kind/lid/iid: Quell-Knoten beim Einordnen ("place"); nsel = Zielindex
    # Einträge sind Mischtypen: jeder kann eigene Unterpunkte ('items') tragen.
    # In "view" navigiert man wie Ordner: ein Eintrag MIT Kindern ist eine
    # anklickbare Zeile (Enter = reingehen), kein aufgeklappter Baum. path ist
    # der Drill-Pfad (Eintrags-ids) innerhalb der offenen Liste def; isel zählt
    # die DIREKTEN Kinder der gerade offenen Ebene.
    L = {"active": False, "view": "list", "lists": [], "sel": 0,
         "def": None, "isel": 0, "path": [], "adding": False, "input": "",
         "msg": "",
         "confirm": False,             # Lösch-Nachfrage für ganze Liste
         "addparent": None,            # Eltern-id beim Anhängen (None = top)
         "imode": "add",               # Eingabezeile: add|sub|rename
         "edit_iid": None,             # umzubenennender Eintrag (imode rename)
         "lrename": None,              # umzubenennende Liste (in "new")
         "move_iid": None,             # zu verschiebender Eintrag ("move")
         # Einordnen (">", Forest-weit): Quelle = Liste ODER Eintrag
         "place_kind": None, "place_lid": None, "place_iid": None,
         "nsel": 0}                    # Zielwahl-Index (place/move/move_new)

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
         "overlay": False,      # Handelsrouten-Overlay (Achse 2) ein/aus
         "odata": None,         # letzte /api/map/layer/trade-Antwort (None ⇒ neu holen)
         "ogrid": None,         # (cols,rows), für die odata geholt wurde
         "focus": None,         # Name des fokussierten Landes (Alt+Pfeile), None=keins
         "fdata": None,         # letzte /api/map/countries-Antwort (None ⇒ neu holen)
         "fgrid": None,         # (cols,rows), für die fdata geholt wurde
         "tcx": 0.0, "tcy": 20.0,  # Kamera-ZIEL (lon/lat) beim Fokuswechsel
         "anim": False}         # läuft gerade eine weiche Kamerafahrt?
    MAP_CHOKE = "◆"          # Chokepoint-Marker (Handelsrouten-Overlay)
    MAP_ROUTE = "·"          # Schifffahrtsrouten-Pfad (dezent, unter den Markern)

    # ── Kalender (füllt die MITTE-Box, Taste 'c') ──────────────────────
    # Wie die Karte ein reiner Zeichner: alle Datums-/Layer-Logik liegt im
    # Backend (core/kalender.py → /api/calendar). Die TUI hält nur die Ansicht
    # (Woche|Monat) + das Referenzdatum zum Blättern und die letzte Antwort.
    #   active : Kalender hat den Fokus (Blätter-/Umschalt-Tasten gehen hierher)
    #   view   : "week" (Mo-So-Liste) | "month" (Monatsgitter)
    #   ref    : ISO-Datum irgendwo im gezeigten Zeitraum (Blätter-Anker)
    #   data   : letzte /api/calendar-Antwort (None ⇒ beim Zeichnen neu holen)
    #   mode   : "view" (blättern/auswählen) | "add" (Termin-Eingabe, gestaffelt)
    #            | "routine" (De-/Aktivieren-Screen eines Routine-Vorkommens)
    #   sel    : Auswahl-Index über ALLE Einträge der Woche (Einmal + Routine)
    #   astage : Add-Stufe 0=Datum/Wochentag 1=Zeit 2=Titel; aday/atime/alabel=Eingaben
    #   atype  : "entry" (Einmal-Termin) | "routine" (wöchentlich) — Tab im Add-Formular
    #   editing: None | (iso,label,layer) — Add-Formular im Ändern-Modus
    #   ract   : der im "routine"-Screen gewählte Eintrag (für De-/Aktivieren)
    K = {"active": False, "view": "week", "ref": date.today().isoformat(),
         "data": None, "msg": "", "mode": "view", "sel": 0, "confirmdel": False,
         "astage": 0, "aday": "", "atime": "", "alabel": "", "amsg": "",
         "atype": "entry", "editing": None, "ract": None, "rconfirm": False}
    KAL_WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    # Deutsche Wochentags-Kürzel → iCal-BYDAY-Codes (für Routine-Anlage)
    KAL_BYDAY = {"mo": "MO", "di": "TU", "mi": "WE", "do": "TH",
                 "fr": "FR", "sa": "SA", "so": "SU"}

    # ── Post/Mail (füllt die MITTE-Box, Taste 'p') ─────────────────────
    # Wie Karte/Kalender ein reiner Zeichner. Rein LESEND über /api/mail
    # (Kategorien + Mails aus data/mail_state.json — KEIN Key nötig). Nur der
    # Live-Poll ('r' → POST /api/mail/poll) braucht die Passphrase (Env oder
    # OS-Keyring) und läuft im Backend-Thread; der Fortschritt erscheint links
    # im Log. Aktualisiert sich alle paar Sekunden selbst.
    #
    # ZWEI EBENEN (Drill-down): Beim Öffnen sieht man NUR die Kategorien (Ebene
    # "cats") — der Review-Stapel ist einfach die Kategorie 'sasha muss gucken'
    # wie jede andere, nichts wird einem ins Gesicht geklatscht. Enter öffnet
    # eine Kategorie (Ebene "mails") und zeigt die Mails darin; esc führt zurück.
    #   active : Panel hat den Fokus
    #   level  : "cats" (Kategorien wählen) | "mails" (Mails der gewählten Kat.)
    #   sel    : Auswahl-Index in der Kategorie-Liste
    #   cat    : Name der geöffneten Kategorie (in "mails")
    #   off    : Scroll-Offset in der Mail-Liste; _ts: letzter Abruf (Auto-Refresh)
    MAIL = {"active": False, "level": "cats", "sel": 0, "cat": None,
            "off": 0, "data": None, "msg": "", "_ts": 0.0,
            "mails": None, "mails_live": False,   # mails: None=lädt, []=leer
            # Ebene 2: zwei Anzeige-Modi + Aktions-Submodi.
            "mode2": "read",      # "read" (eine Mail, Vorschau+ausklappen) | "list" (Blöcke)
            "msel": 0,            # ausgewählte Mail (in beiden Modi)
            "expanded": False,    # im read-Modus: voller Text statt Vorschau
            "bodyoff": 0,         # Scroll im Body (read, ausgeklappt)
            "body": None,         # gecachter Body der aktuellen Mail (None=lädt)
            "bodyfor": None,      # uid, zu der der Body gehört
            "picking": False,     # Einsortier-Picker offen (Kategorie wählen)
            "picksel": 0,         # Auswahl im Picker
            "confirmdel": False,  # Lösch-Nachfrage offen
            # Antwort-Editor (Split-Pane: links Original, rechts dein Text).
            "replying": False,    # Editor offen → Mitte wird breit
            "reply_text": "",     # dein getippter Antworttext
            "reply_origoff": 0,   # Scroll im Original (links)
            "reply_confirm": False}  # Verlassen-Leiste (senden/verwerfen/weiter)

    def m_fetch(cols, rows):
        """Karte fürs aktuelle Viewport+Raster synchron holen (localhost, wenige
        ms — wie das Graph-Werkzeug bei Benutzeraktionen). Die TUI rendert das
        gefüllte Land in Braille (/api/map/braille) — der frühere Umriss-Stil ist
        raus (sah zu grob aus). Alle Geo-Mathematik bleibt in core/map/."""
        try:
            q = ("/api/map/braille?cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d"
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
        """Handelsrouten-Overlay (Komposit) fürs aktuelle Viewport holen:
        Routenlinien + Chokepoint-Marker + Provenienz von /api/map/layer/trade
        (ohne sub = beide). Wie m_fetch synchron; Fehler-Marker statt
        Dauer-Refetch bei totem Backend."""
        try:
            q = ("/api/map/layer/trade?"
                 "cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d&aspect=0.5"
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
        M["fdata"] = None        # Länder-Border mit-neu projizieren (sonst klebt sie)

    def m_zoom(dz):
        M["zoom"] = max(0.0, min(8.0, M["zoom"] + dz))
        M["data"] = None
        M["odata"] = None
        M["fdata"] = None

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
            # stderr NICHT nach /dev/null: fehlt pygame/numpy (z.B. Pi ohne venv),
            # stirbt map_window.py beim Import STILL — man drueckt 'w' und nichts
            # passiert, kein Hinweis. In ein Log umgeleitet ist der Grund lesbar
            # (cat $ZENTRALE_MAP_WINDOW_LOG bzw. /tmp/zentrale-map-window.log).
            map_log = os.environ.get("ZENTRALE_MAP_WINDOW_LOG") or "/tmp/zentrale-map-window.log"
            errf = open(map_log, "a", encoding="utf-8")
            M["proc"] = subprocess.Popen(
                [py if os.path.exists(py) else sys.executable, script,
                 "--cx", "%.5f" % M["cx"], "--cy", "%.5f" % M["cy"],
                 "--zoom", "%.2f" % M["zoom"]],
                stdout=subprocess.DEVNULL, stderr=errf,
                start_new_session=True)
            errf.close()   # das Kind hat seinen eigenen Dup-FD; Eltern-Kopie zu
            M["msg"] = ""        # kein klebender Text — das Live-Badge (poll())
                                 # in draw_map zeigt „● fenster", solange es offen ist

        except Exception as exc:
            M["msg"] = "fenster-start: %s" % exc

    # ── Länder-Fokus (Alt+Pfeile): immer genau ein Land fokussiert, weiße
    # gestrichelte Border + Name; Alt+↑↓←→ springt zum räumlich nächsten Land in
    # der Richtung, die Kamera zieht weich mit. Geo-Logik im Backend
    # (/api/map/countries) — die TUI navigiert nur über Mittelpunkte + zeichnet.
    def m_fetch_countries(cols, rows):
        """Länder-Daten holen: alle Mittelpunkte (Navigation) + Umriss des
        fokussierten Landes (Border). Aufs selbe Raster wie die Braille-Basis."""
        try:
            q = ("/api/map/countries?cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d"
                 "&aspect=0.5" % (M["cx"], M["cy"], M["zoom"], cols, rows))
            if M.get("focus"):
                q += "&focus=" + urllib.parse.quote(M["focus"])
            M["fdata"] = api_call(q)
            M["fgrid"] = (cols, rows)
        except Exception:
            M["fdata"] = None

    def m_countries():
        """fdata sicherstellen (für das letzte bekannte Karten-Raster)."""
        if M.get("fdata") is None and M.get("grid"):
            m_fetch_countries(*M["grid"])
        return M.get("fdata")

    def m_focus_init():
        """Ersten Fokus setzen: das Land, dessen Mittelpunkt der Bildmitte am
        nächsten liegt — und Kamera weich dorthin."""
        fd = m_countries()
        if not fd or not fd.get("countries"):
            return
        best = min(fd["countries"],
                   key=lambda c: (c["lon"] - M["cx"]) ** 2 + (c["lat"] - M["cy"]) ** 2)
        M["focus"] = best["name"]
        M["tcx"], M["tcy"], M["anim"], M["fdata"] = best["lon"], best["lat"], True, None

    def m_focus_step(dirx, diry):
        """Zum räumlich nächsten Land in der Richtung (dirx/diry) fokussieren.
        Richtung im VISUELLEN Welt-Raum (wx/wy: oben = kleineres wy). Kosten =
        Distanz entlang der Richtung + 2× seitlicher Versatz (bevorzugt geradeaus)."""
        fd = m_countries()
        if not fd or not fd.get("countries"):
            return
        if not M.get("focus"):
            m_focus_init()                       # erster Strg+Pfeil: Fokus an
            return
        cur = next((c for c in fd["countries"] if c["name"] == M["focus"]), None)
        if cur is None:
            m_focus_init()
            return
        best = None
        for c in fd["countries"]:
            if c["name"] == cur["name"]:
                continue
            dx, dy = c["wx"] - cur["wx"], c["wy"] - cur["wy"]
            if dirx:
                along, lateral = dx * dirx, abs(dy)
            else:
                along, lateral = dy * diry, abs(dx)
            if along <= 1e-6:                    # nicht in der gewünschten Richtung
                continue
            cost = along + 2.0 * lateral
            if best is None or cost < best[0]:
                best = (cost, c)
        if best is None:
            return
        tgt = best[1]
        M["focus"] = tgt["name"]
        M["tcx"], M["tcy"], M["anim"], M["fdata"] = tgt["lon"], tgt["lat"], True, None

    def m_anim_step():
        """Eine Ease-Stufe der Kamerafahrt zum Fokus-Ziel (pro Frame aufgerufen,
        solange M['anim']). Refetch erzwingen, damit Karte+Border mitziehen."""
        dx, dy = M["tcx"] - M["cx"], M["tcy"] - M["cy"]
        if abs(dx) < 0.08 and abs(dy) < 0.08:
            M["cx"], M["cy"], M["anim"] = M["tcx"], M["tcy"], False
        else:
            M["cx"] += dx * 0.35
            M["cy"] += dy * 0.35
        M["data"] = M["odata"] = M["fdata"] = None

    def m_alt_arrow(ch):
        """Alt+Pfeil → 'up'/'down'/'left'/'right'; einzelnes Esc → 'esc'; sonst
        None. (Strg+Pfeil ist schon belegt: Höhe Zentrale↔Befehlszeile.) Deckt die
        verbreiteten Alt-Formen ab, da das Terminal eine davon schickt:
          1) terminfo-Keyname kUP3… (Modifier 3 = Alt) — EIN Keycode
          2) Esc + (keypad-übersetzter) Pfeil-Keycode  (Meta=Esc-Präfix)
          3) Esc + Roh-CSI  \\033[1;3{A..D}  bzw.  \\033\\033[{A..D} / \\033O{A..D}
        Unbekannte Esc-Sequenzen landen zur Diagnose in M['msg']."""
        try:
            nm = curses.keyname(ch)
        except (ValueError, OverflowError):
            nm = b""
        by_name = {b"kUP3": "up", b"kDN3": "down", b"kLFT3": "left", b"kRIT3": "right"}
        if nm in by_name:
            return by_name[nm]
        if ch != 27:
            return None
        # Kurz (50 ms) auf das ERSTE Folgebyte warten — fängt den Fall ab, dass
        # ESC einen Tick vor dem Rest der Sequenz ankommt; danach den Rest ohne
        # Warten leeren. Einzelnes Esc → nach 50 ms -1 → 'esc'.
        seq = []
        stdscr.timeout(50)
        first = stdscr.getch()
        if first != -1:
            seq.append(first)
            stdscr.nodelay(True)
            for _ in range(7):
                nx = stdscr.getch()
                if nx == -1:
                    break
                seq.append(nx)
        stdscr.timeout(250)
        if not seq:
            return "esc"                       # einzelnes Esc → Karte zu
        # (2) Meta=Esc + Pfeil-Keycode (keypad(True) übersetzt das \\033[A schon)
        arrow = {curses.KEY_UP: "up", curses.KEY_DOWN: "down",
                 curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right"}
        for n in seq:
            if n in arrow:
                return arrow[n]
        # (3) Roh-Escape-Sequenz (führende ESC strippen → Meta- u. CSI-Form gleich)
        s = "".join(chr(n) for n in seq if 0 <= n < 256).lstrip("\x1b")
        for k, v in (("[1;3A", "up"), ("[1;3B", "down"), ("[1;3C", "right"),
                     ("[1;3D", "left"), ("[A", "up"), ("[B", "down"),
                     ("[C", "right"), ("[D", "left"), ("OA", "up"), ("OB", "down"),
                     ("OC", "right"), ("OD", "left")):
            if s.startswith(k):
                return v
        M["msg"] = "alt? codes " + " ".join(str(n) for n in seq)   # Diagnose
        return None

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

    def g_target():
        """Ziel-Datum für Eintrag/Anzeige (heute minus dayoff)."""
        return date.today() - timedelta(days=max(0, G.get("dayoff", 0)))

    def g_daylabel():
        off = max(0, G.get("dayoff", 0))
        if off == 0:
            return "heute"
        if off == 1:
            return "gestern"
        return g_target().strftime("%d.%m.")

    def g_existing():
        """Vorhandener Eintrag für den Ziel-Tag (oder None) — für 'aktuell:'-Hint."""
        ds = g_target().isoformat()
        for e in reversed(G["vals"] or []):     # jüngster zuerst
            if isinstance(e, dict) and e.get("date") == ds:
                return e
        return None

    def g_save(v, end=None):
        """Wert für den Ziel-Tag eintragen (Default heute; ←/→ verschiebt ihn).
        upsert=True ersetzt einen vorhandenen Eintrag desselben Datums, damit
        Nachtragen/Ändern keine Duplikate erzeugt.
        end gesetzt → Zeitperiode (value=Start-Minute, end=End-Minute)."""
        data = {"date": g_target().isoformat(), "value": v}
        if end is not None:
            data["end"] = end
        try:
            api_call("/api/log", method="POST",
                     body={"category": G["def"]["id"], "data": data, "upsert": True})
            g_load_vals()
            tag = "" if G.get("dayoff", 0) == 0 else " (%s)" % g_daylabel()
            t = G["def"].get("type")
            if t == "period":
                G["msg"] = "eingetragen%s: %s–%s" % (tag, fmt_clock(v), fmt_clock(end))
            elif t == "time":
                G["msg"] = "eingetragen%s: %s" % (tag, fmt_clock(v))
            else:
                G["msg"] = "eingetragen%s: %g" % (tag, v)
        except Exception:
            G["msg"] = "speichern fehlgeschlagen"

    def l_load():
        """Listen-Definitionen (inkl. Einträge) frisch ziehen."""
        try:
            L["lists"] = api_call("/api/lists") or []
        except Exception:
            L["lists"] = []
        if L["sel"] >= len(L["lists"]):
            L["sel"] = max(0, len(L["lists"]) - 1)

    def l_flatten(items, depth=0, out=None):
        """Den Eintrags-Baum in eine flache [(item, tiefe), …]-Liste klopfen,
        Eltern vor Kindern. Cursor (isel) und Rendering laufen über diese
        flache Sicht; die Tiefe steuert nur die Einrückung."""
        if out is None:
            out = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            out.append((it, depth))
            kids = it.get("items")
            if isinstance(kids, list) and kids:
                l_flatten(kids, depth + 1, out)
        return out

    def l_count(items):
        """(erledigt, gesamt) über die BLÄTTER zählen (echte abhakbare Punkte).
        Ordner zählen nicht selbst mit — sie sind nur Gruppierung; ihr Status
        ist abgeleitet (l_done)."""
        d = t = 0
        for it in items or []:
            if not isinstance(it, dict):
                continue
            kids = it.get("items")
            if isinstance(kids, list) and kids:      # Ordner → nur seine Blätter
                cd, ct = l_count(kids)
                d += cd
                t += ct
            else:                                     # Blatt
                t += 1
                if it.get("done"):
                    d += 1
        return d, t

    def l_done(it):
        """Effektiver Erledigt-Status (Spiegel von core.lists.is_done): Blatt =
        eigenes 'done'; Ordner = erledigt, wenn ALLE Kinder erledigt sind."""
        kids = it.get("items")
        if isinstance(kids, list) and kids:
            return all(l_done(c) for c in kids if isinstance(c, dict))
        return bool(it.get("done"))

    def l_container():
        """Die gerade offene Ebene auflösen: (direkte Kinder, container-id,
        Breadcrumb-Liste) anhand L["def"] + L["path"]. container-id ist None auf
        oberster Ebene (Listen-Wurzel) bzw. die id des reingegangenen Eintrags.
        Ein gebrochener Pfad (Eintrag inzwischen weg) wird hier gekürzt."""
        if not L["def"]:
            return [], None, []
        node = L["def"]
        pid = None
        crumbs = [str(L["def"].get("name") or "")]
        valid = []
        for iid in L["path"]:
            nxt = next((it for it in (node.get("items") or [])
                        if isinstance(it, dict) and it.get("id") == iid), None)
            if nxt is None:
                break
            node = nxt
            pid = iid
            valid.append(iid)
            crumbs.append(str(nxt.get("text") or ""))
        if valid != L["path"]:
            L["path"] = valid
        return (node.get("items") or []), pid, crumbs

    def l_index_in_container(iid):
        """Index des Eintrags mit iid unter den DIREKTEN Kindern der offenen
        Ebene (0, wenn nicht da)."""
        items, _pid, _cr = l_container()
        for i, it in enumerate(items):
            if isinstance(it, dict) and it.get("id") == iid:
                return i
        return 0

    def l_find_item(items, iid):
        """Den Eintrag mit iid irgendwo im Baum (oder None)."""
        for it, _d in l_flatten(items):
            if it.get("id") == iid:
                return it
        return None

    def l_move_targets():
        """Listen, in die der gewählte Eintrag wandern darf — alle außer der
        gerade offenen (raus = in eine ANDERE Liste)."""
        cur = L["def"]["id"] if L["def"] else None
        return [l for l in L["lists"] if isinstance(l, dict) and l.get("id") != cur]

    def l_forest_targets(skind, slid, siid):
        """Alle Ziel-Knoten zum Einordnen über ALLE Listen hinweg — flach, mit
        Tiefe & Label, OHNE den eigenen Teilbaum (kein Zyklus). Jeder Eintrag:
        {lid, iid (None = Listen-Top als Ziel), label}. So kann `>` auf jeder
        Ebene jeden Knoten erreichen (oben wie unten gleich)."""
        excl = set()                                  # eigener Teilbaum (nur item-Quelle)
        if skind == "item":
            src_lst = next((l for l in L["lists"] if isinstance(l, dict) and l.get("id") == slid), None)
            src = l_find_item((src_lst or {}).get("items"), siid)
            if src is not None:
                for it, _d in l_flatten([src]):
                    excl.add(it.get("id"))
        out = []
        for l in L["lists"]:
            if not isinstance(l, dict):
                continue
            lid = l.get("id")
            if skind == "list" and lid == slid:       # ganze Quell-Liste raus
                continue
            out.append({"lid": lid, "iid": None, "label": str(l.get("name") or "")})
            for it, d in l_flatten(l.get("items")):
                if skind == "item" and lid == slid and it.get("id") in excl:
                    continue                          # eigener Teilbaum
                out.append({"lid": lid, "iid": it.get("id"),
                            "label": "  " * (d + 1) + str(it.get("text") or "")})
        return out

    def l_sync_def():
        """Nach Änderungen die offene Liste aus der frisch geladenen Registry
        neu greifen (Einträge können dazugekommen / weg sein)."""
        if not L["def"]:
            return
        cur = next((x for x in L["lists"] if x.get("id") == L["def"]["id"]), None)
        L["def"] = cur
        if cur is None:                       # Liste verschwunden → zurück zur Übersicht
            L["view"] = "list"; L["path"] = []
            return
        items, _pid, _cr = l_container()      # validiert/kürzt den Drill-Pfad
        if L["isel"] >= len(items):
            L["isel"] = max(0, len(items) - 1)

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

    def addclip(y, x, text, maxw, attr=0, strike=False):
        """Wie safe_addstr, aber kürzt vorher auf maxw — verhindert, dass
        z.B. lange stdout-Zeilen aus ihrer Box in die Nachbarspalte laufen.
        strike=True legt über jedes (schon gekürzte) Zeichen ein Combining-
        Overlay U+0336 → durchgestrichen (für abgehakte Einträge)."""
        if maxw <= 0:
            return
        if not isinstance(text, str):
            text = str(text)
        s = text[:maxw]
        if strike and s:
            # Combining-Zeichen sind Null-Breite (hängen am Vorzeichen) → die
            # sichtbare Breite bleibt maxw. safe_addstr würde aber nach Codepoints
            # kürzen und die Hälfte abschneiden; darum hier direkt setzen.
            s = "".join(c + "̶" for c in s)
            h, w = stdscr.getmaxyx()
            if 0 <= y < h and 0 <= x < w:
                try:
                    stdscr.addstr(y, x, s, attr)
                except (curses.error, ValueError):
                    pass
            return
        safe_addstr(y, x, s, attr)

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
            dl = g_daylabel()
            exv = g_existing()                     # vorhandener Eintrag am Ziel-Tag
            if not exv:
                eh = ""
            elif typ == "period":
                eh = " (aktuell %s–%s)" % (fmt_clock(exv.get("value")), fmt_clock(exv.get("end")))
            elif typ == "time":
                eh = " (aktuell %s)" % fmt_clock(exv.get("value"))
            else:
                eh = " (aktuell %g)" % (_num(exv.get("value")) or 0)

            if typ in ("time", "period"):
                addclip(by + 2, ix, "%d einträge · zuletzt %s" % (len(rows), graph_last(d, rows)), iw, C["dim"])
                if rows:
                    draw_time_plot(by + 3, bx, bw, input_row - 1 - (by + 3), rows, typ == "period")
                else:
                    addclip(by + 3, ix, "— noch keine einträge —", iw, C["faint"])
                if typ == "time":
                    addclip(input_row, ix, "%s · zeit: %s_%s" % (dl, G["input"], eh), iw, C["bright"])
                    addclip(bottom, ix, ("HH:MM · enter speichern · ←/→ tag · esc zu  " + G["msg"]).strip(), iw, C["faint"])
                else:
                    c1 = G["input"] + ("_" if G["pstage"] == 0 else "")
                    c2 = G["input2"] + ("_" if G["pstage"] == 1 else "")
                    addclip(input_row, ix, "%s · von: %s  bis: %s%s" % (dl, c1, c2, eh), iw, C["bright"])
                    addclip(bottom, ix, ("HH:MM · enter von→bis · ←/→ tag · esc zu  " + G["msg"]).strip(), iw, C["faint"])
            else:
                ser = graph_series(typ, rows)
                if ser:
                    addclip(by + 2, ix, blockspark(ser[-iw:]), iw, C["graph"])
                    addclip(by + 3, ix, "%d werte · zuletzt %s" % (len(ser), graph_last(d, rows)), iw, C["dim"])
                else:
                    addclip(by + 2, ix, "— noch keine werte —", iw, C["faint"])
                if typ == "scale":
                    addclip(input_row, ix, "1–5 trägt für %s ein%s" % (dl, eh), iw, C["acc"])
                    addclip(bottom, ix, ("1–5 eintragen · ←/→ tag · esc zu  " + G["msg"]).strip(), iw, C["faint"])
                else:
                    addclip(input_row, ix, "%s · wert: %s_%s" % (dl, G["input"], eh), iw, C["bright"])
                    addclip(bottom, ix, ("ziffern · enter speichern · ←/→ tag · esc zu  " + G["msg"]).strip(), iw, C["faint"])

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
                    pred = "~" if g.get("predict") else " "   # ~ = Lücken werden geschätzt
                    line = "%s%s%-11s %-6s %s" % (
                        "›" if sel else " ", pred, str(g.get("name") or "")[:11], _tlabel(g.get("type")), spark)
                    addclip(yy, ix, line, iw, C["bright"] if sel else C["dim"])
                    yy += 1
            if G["msg"]:                       # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, G["msg"], iw, C["faint"])
            else:
                addclip(bottom, ix, "enter öffnen · n neu · p ~vorhersage · d weg · esc zu", iw, C["faint"])

            if G["confirm"] and G["graphs"]:        # Mini-Dialog über die Liste legen
                nm = G["graphs"][G["sel"]]["name"]
                q = "»%s« löschen?" % nm[:18]
                dw = min(iw, max(len(q), 16) + 4)
                dx = bx + (bw - dw) // 2
                dy = by + bh // 2 - 2
                draw_box(dy, dx, 4, dw, "LÖSCHEN", C["warn"])
                addclip(dy + 1, dx + 2, q, dw - 4, C["bright"])
                addclip(dy + 2, dx + 2, "j/enter = ja · sonst abbrechen", dw - 4, C["faint"])

    def draw_list_tool(by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn das Listen-Werkzeug Fokus hat."""
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2          # Hinweiszeile unten in der Box
        if iw < 8:
            return

        if L["view"] == "new":
            ren = L["lrename"] is not None
            addclip(by + 1, ix, "LISTE UMBENENNEN" if ren else "NEUE LISTE", iw, C["bright"])
            addclip(by + 3, ix, "name: " + L["input"] + "_", iw, C["bright"])
            tip = "enter umbenennen · esc zurück  " if ren else "enter anlegen · esc zurück  "
            addclip(bottom, ix, (tip + L["msg"]).strip(), iw, C["faint"])

        elif L["view"] == "view" and L["def"]:
            items, _pid, crumbs = l_container()   # NUR die offene Ebene (Ordner-Sicht)
            done, total = l_count(items)
            head = " / ".join(crumbs)             # Breadcrumb: liste / ordner / …
            addclip(by + 1, ix, "%s  (%d/%d)" % (head, done, total), iw, C["bright"])
            safe_addstr(by + 1, bx + bw - 9, "[a neu]", C["acc"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            input_row = by + bh - 3
            list_bottom = (input_row - 1) if L["adding"] else bottom
            yy = by + 3
            if not items:
                addclip(yy, ix, "noch leer — 'a' hängt was an", iw, C["faint"])
            else:
                # Fenster um den Cursor, damit lange Listen scrollen statt abzuschneiden
                avail = max(1, list_bottom - yy)
                start = max(0, min(L["isel"] - avail + 1, len(items) - avail)) if len(items) > avail else 0
                for off, it in enumerate(items[start:start + avail]):
                    if not isinstance(it, dict):
                        continue
                    sel = (start + off == L["isel"])
                    kids = it.get("items")
                    folder = isinstance(kids, list) and bool(kids)
                    done = l_done(it)                 # Ordner: abgeleitet, Blatt: 'done'
                    box = "[x]" if done else "[ ]"
                    suffix = ""
                    if folder:
                        cd, ct = l_count(kids)        # Ordner-Fortschritt (Blätter)
                        suffix = "  (%d/%d)" % (cd, ct)
                    if it.get("project"):             # als Projekt markiert → ◆ (wie Listen)
                        suffix += " ◆"
                    mark = "▸ " if folder else "  "   # Ordner = anklickbar (enter rein)
                    body = "%s%s %s%s" % (mark, box, str(it.get("text") or ""), suffix)
                    attr = C["faint"] if done else (C["bright"] if sel else C["dim"])
                    # Cursor-Pfeil immer normal (sichtbar), Inhalt ggf. transparent
                    # + durchgestrichen wenn erledigt.
                    addclip(yy, ix, "› " if sel else "  ", 2, C["bright"] if sel else attr)
                    addclip(yy, ix + 2, body, iw - 2, attr, strike=done)
                    yy += 1
            if L["adding"]:
                lbl = {"sub": "unterpunkt", "rename": "umbenennen"}.get(L["imode"], "neu")
                tip = "enter umbenennen" if L["imode"] == "rename" else "enter anhängen"
                addclip(input_row, ix, lbl + ": " + L["input"] + "_", iw, C["bright"])
                addclip(bottom, ix, (tip + " · esc abbrechen  " + L["msg"]).strip(), iw, C["faint"])
            elif L["msg"]:                     # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])

        elif L["view"] == "place":         # Knoten (Liste/Eintrag) Forest-weit einordnen
            if L["place_kind"] == "list":
                src = next((x for x in L["lists"] if isinstance(x, dict) and x.get("id") == L["place_lid"]), None)
                nm = str(src.get("name") if isinstance(src, dict) else "?")
            else:
                src_lst = next((x for x in L["lists"] if isinstance(x, dict) and x.get("id") == L["place_lid"]), None)
                it = l_find_item((src_lst or {}).get("items"), L["place_iid"])
                nm = str(it.get("text") if isinstance(it, dict) else "?")
            addclip(by + 1, ix, "»%s« einordnen in:" % nm[:18], iw, C["bright"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            tg = l_forest_targets(L["place_kind"], L["place_lid"], L["place_iid"])
            yy = by + 3
            if not tg:
                addclip(yy, ix, "kein ziel da", iw, C["faint"])
            else:
                avail = max(1, bottom - yy)
                start = max(0, min(L["nsel"] - avail + 1, len(tg) - avail)) if len(tg) > avail else 0
                for off, t in enumerate(tg[start:start + avail]):
                    sel = (start + off == L["nsel"])
                    # Listen-Top (iid None) als ≡ markiert, Einträge eingerückt
                    mark = "≡ " if t["iid"] is None else "  "
                    addclip(yy, ix, "%s %s%s" % ("›" if sel else " ", mark, t["label"]),
                            iw, C["bright"] if sel else C["dim"])
                    yy += 1
            if L["msg"]:                       # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])

        elif L["view"] == "move" and L["def"]:   # Eintrag raus in eine andere Liste
            it = l_find_item(L["def"].get("items"), L["move_iid"])
            nm = str(it.get("text") if isinstance(it, dict) else "?")
            addclip(by + 1, ix, "»%s« verschieben nach:" % nm[:18], iw, C["bright"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            # Zielauswahl: erst „neue Liste", dann alle anderen Listen.
            opts = ["[+ neue Liste]"] + [str(l.get("name") or "")
                                         for l in l_move_targets()]
            yy = by + 3
            avail = max(1, bottom - yy)
            start = max(0, min(L["nsel"] - avail + 1, len(opts) - avail)) if len(opts) > avail else 0
            for off, label in enumerate(opts[start:start + avail]):
                sel = (start + off == L["nsel"])
                addclip(yy, ix, "%s %s" % ("›" if sel else " ", label),
                        iw, C["bright"] if sel else C["dim"])
                yy += 1
            if L["msg"]:                       # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])

        elif L["view"] == "move_new":            # Name für die neue Ziel-Liste
            addclip(by + 1, ix, "NEUE LISTE (ziel)", iw, C["bright"])
            addclip(by + 3, ix, "name: " + L["input"] + "_", iw, C["bright"])
            addclip(bottom, ix, ("enter anlegen+verschieben · esc zurück  " + L["msg"]).strip(), iw, C["faint"])

        else:  # "list"
            addclip(by + 1, ix, "LISTEN", iw, C["bright"])
            safe_addstr(by + 1, bx + bw - 9, "[n neu]", C["acc"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            yy = by + 3
            if not L["lists"]:
                addclip(yy, ix, "noch keine — 'n' legt eine an", iw, C["faint"])
            else:
                for i, l in enumerate(L["lists"]):
                    if yy >= bottom:
                        break
                    if not isinstance(l, dict):
                        continue
                    sel = (i == L["sel"])
                    done, total = l_count(l.get("items"))
                    proj = "◆" if l.get("project") else " "   # Projekt → rechts in PROJECTS-Box
                    line = "%s%s %-15s %d/%d" % (
                        "›" if sel else " ", proj, str(l.get("name") or "")[:15], done, total)
                    addclip(yy, ix, line, iw, C["bright"] if sel else C["dim"])
                    yy += 1
            if L["msg"]:                       # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, L["msg"], iw, C["faint"])

            if L["confirm"] and L["lists"]:        # Mini-Dialog über die Liste legen
                nm = str(L["lists"][L["sel"]].get("name") or "")
                q = "»%s« löschen?" % nm[:18]
                dw = min(iw, max(len(q), 16) + 4)
                dx = bx + (bw - dw) // 2
                dy = by + bh // 2 - 2
                draw_box(dy, dx, 4, dw, "LÖSCHEN", C["warn"])
                addclip(dy + 1, dx + 2, q, dw - 4, C["bright"])
                addclip(dy + 2, dx + 2, "j/enter = ja · sonst abbrechen", dw - 4, C["faint"])

    def draw_map(by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn die Karte Fokus hat. Holt bei Bedarf
        frische Daten (Resize/Pan/Zoom) und druckt die fertig gefüllte
        Braille-Karte zeilenweise (vom Backend bereits projiziert)."""
        iw, ih = bw - 2, bh - 2
        if iw < 4 or ih < 3:
            return
        # Die unterste Box-Innenzeile bleibt für die Status-/Hilfe-Zeile frei.
        map_ih = ih - 1
        if (not M["data"]) or M["grid"] != (iw, map_ih):
            m_fetch(iw, map_ih)
        d = M["data"]
        ox, oy = bx + 1, by + 1
        if not d or d.get("failed") or not d.get("braille"):
            addclip(by + 1, ox, M["msg"] or "lade karte…", iw, C["faint"])
            return

        # Gefülltes Land als fertige Braille-Zeilen — die TUI druckt nur.
        for r, row in enumerate(d["braille"][:map_ih]):
            addclip(oy + r, ox, row, iw, C["acc"])

        # Handelsrouten-Overlay (Achse 2, Komposit): erst die Routenlinien (dezent),
        # dann die leuchtenden Chokepoint-Marker + Detail der dem Fadenkreuz
        # nächsten Engstelle.
        focus = None        # (name, today-total, top-industrie) nahe der Mitte
        ovintage = None
        if M["overlay"]:
            if (not M["odata"]) or M["ogrid"] != (iw, map_ih):
                m_fetch_overlay(iw, map_ih); M["ogrid"] = (iw, map_ih)
            od = M["odata"]
            if od and not od.get("failed"):
                ovintage = od.get("vintage")
                # Routenlinien per Bresenham (dezenter Pfad-Glyph).
                for line in od.get("lines", []):
                    for i in range(len(line) - 1):
                        x0, y0 = int(round(line[i][0])), int(round(line[i][1]))
                        x1, y1 = int(round(line[i + 1][0])), int(round(line[i + 1][1]))
                        dx, dy = abs(x1 - x0), abs(y1 - y0)
                        sxx = 1 if x0 < x1 else -1
                        syy = 1 if y0 < y1 else -1
                        err = dx - dy
                        while True:
                            if 0 <= x0 < iw and 0 <= y0 < map_ih:
                                safe_addstr(oy + y0, ox + x0, MAP_ROUTE, C["faint"])
                            if x0 == x1 and y0 == y1:
                                break
                            e2 = 2 * err
                            if e2 > -dy:
                                err -= dy; x0 += sxx
                            if e2 < dx:
                                err += dx; y0 += syy
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

        # Länder-Fokus: weiße Border des fokussierten Landes (DÜNNE Braille-Punkte,
        # umgefärbt — nicht fette Vollzeichen) + Name. Das Backend rasterisiert den
        # Umriss in Braille-Subpixel; wir malen die Rand-Zeichen nur weiß drüber.
        if M["focus"]:
            if (not M["fdata"]) or M["fgrid"] != (iw, map_ih):
                m_fetch_countries(iw, map_ih); M["fgrid"] = (iw, map_ih)
            fdoc = (M["fdata"] or {}).get("focus")
            if fdoc:
                for cc, rr, glyph in fdoc.get("braille", []):
                    if 0 <= cc < iw and 0 <= rr < map_ih:
                        safe_addstr(oy + rr, ox + cc, glyph, C["bright"])
                # Name am Label-Anker (oder oben-mittig, falls Anker außerhalb).
                nm = fdoc.get("name", "")
                lc = fdoc.get("label") or [iw / 2, map_ih / 2]
                lx, ly = int(lc[0]), int(lc[1])
                if not (0 <= lx < iw and 0 <= ly < map_ih):
                    lx, ly = iw // 2, max(0, map_ih // 2 - 1)
                nx = max(0, min(lx - len(nm) // 2, iw - len(nm)))
                safe_addstr(oy + ly, ox + nx, nm[:iw], C["bright"])

        # Fadenkreuz in der Mitte (Orientierung, wo cx/cy liegt). NACH den Markern,
        # damit es obenauf bleibt.
        safe_addstr(oy + map_ih // 2, ox + iw // 2, "+", C["warn"])

        # Status-/Hilfezeile unten in der Box: Position, Zoom, Steuerung.
        info = "lon %+.1f lat %+.1f · z%g" % (M["cx"], M["cy"], M["zoom"])
        if M["focus"]:
            info += " · ⬚%s" % M["focus"]      # fokussiertes Land (Alt+Pfeile)
        if M["overlay"]:
            if focus:
                nm, val, _ind = focus
                info += " · ◆%s %s" % (nm, "—" if val is None else val)
            else:
                info += " · Handelsrouten %s" % (ovintage or "?")
        addclip(by + bh - 2, ox, info, iw, C["bright"])
        # Fenster-Status LIVE aus dem Prozess lesen (poll()), nicht aus klebendem
        # Text — so verschwindet „● fenster", sobald das native Fenster zu ist.
        proc = M.get("proc")
        win_open = proc is not None and proc.poll() is None
        if not win_open and M["msg"] == "fenster läuft schon":
            M["msg"] = ""        # veraltete „läuft schon"-Meldung aufräumen
        # Shortcuts liegen unter '/'; unten nur Status (● fenster) bzw. Feedback.
        hint = M["msg"] or ("● fenster" if win_open else "")
        if hint:
            addclip(by + bh - 2, ox + iw - len(hint), hint, len(hint), C["faint"])

    def k_fetch():
        """Kalender fürs aktuelle view+ref synchron holen (localhost, wenige ms).
        Fehler-Marker statt None, damit draw_calendar nicht bei totem Backend
        jeden Frame neu anfragt — erst Blättern/Umschalten löst einen neuen
        Versuch aus (setzt data=None)."""
        try:
            resp = api_call("/api/calendar?view=%s&ref=%s"
                            % (K["view"], K["ref"]), timeout=2.0)
            # Nur ein dict ist zeichenbar; null/Liste/String (auch von einem
            # kaputten Backend) → Fehler-Marker, sonst crasht draw_calendar an
            # .get(). Wie der Karten-Pfad: truthy Marker statt None verhindert
            # Dauer-Refetch jeden Frame.
            K["data"] = resp if isinstance(resp, dict) else {"failed": True}
            K["msg"] = "" if isinstance(resp, dict) else "kalender: backend?"
        except Exception:
            K["data"] = {"failed": True}
            K["msg"] = "kalender: backend?"

    def k_step(delta):
        """Eine Periode vor/zurück: Woche = ±7 Tage, Monat = ±1 Monat (auf den
        1. normalisiert, sonst springt z.B. der 31. krumm)."""
        r = date.fromisoformat(K["ref"])
        if K["view"] == "month":
            m = r.month - 1 + delta
            r = date(r.year + m // 12, m % 12 + 1, 1)
        else:
            r = r + timedelta(days=7 * delta)
        K["ref"] = r.isoformat()
        K["data"] = None

    def k_toggle():
        K["view"] = "month" if K["view"] == "week" else "week"
        K["data"] = None

    def k_today():
        K["ref"] = date.today().isoformat()
        K["data"] = None

    def k_selectable():
        """Flache Liste ALLER auswählbaren Einträge der Antwort in Render-
        Reihenfolge (Einmal-Termine UND Routine-Vorkommen; nur reine Ausfälle/
        Ferien sind nicht handelbar). Jeder Eintrag als Dict mit Typ-Infos —
        Quelle für Auswahl (K['sel']) + alle Aktionen. Reihenfolge MUSS zum
        Wochen-Render passen (sortierte Tage, Eintragsreihenfolge), sonst zeigt
        der ›-Cursor auf den falschen Termin. Defensiv gegen kaputte JSON-Daten."""
        d = K["data"]
        if not isinstance(d, dict):
            return []
        days = d.get("days")
        if not isinstance(days, dict):
            return []
        out = []
        for iso in sorted(days.keys()):
            ents = days.get(iso)
            if not isinstance(ents, list):
                continue
            for e in ents:
                if not isinstance(e, dict) or e.get("ausfall"):
                    continue   # Ausfall (Ferien) ist nur Info, nicht handelbar
                out.append({"iso": iso, "label": e.get("label", ""),
                            "layer": e.get("layer", "termine"),
                            "recurring": bool(e.get("recurring")),
                            "deaktiviert": bool(e.get("deaktiviert")),
                            "time": e.get("time"), "ende": e.get("ende"),
                            "ort": e.get("ort")})
        return out

    def k_parse_day(s):
        """Tippeingabe → ISO-Datum. Akzeptiert 'TT.MM', 'TT.MM.JJJJ',
        'JJJJ-MM-TT'; leer = heute; Jahr aus dem Blätter-Anker, wenn nur TT.MM.
        None bei Unsinn (Aufrufer meldet 'datum?')."""
        s = (s or "").strip()
        if not s:
            return date.today().isoformat()
        parts = [p for p in s.replace("-", ".").replace("/", ".").split(".") if p]
        try:
            if len(parts) == 3 and len(parts[0]) == 4:        # JJJJ.MM.TT
                y, m, dd = int(parts[0]), int(parts[1]), int(parts[2])
            elif len(parts) == 3:                              # TT.MM.JJJJ
                dd, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                if y < 100:
                    y += 2000
            elif len(parts) == 2:                              # TT.MM (Jahr aus ref)
                dd, m = int(parts[0]), int(parts[1])
                y = date.fromisoformat(K["ref"]).year
            else:
                return None
            return date(y, m, dd).isoformat()
        except (ValueError, IndexError):
            return None

    def k_parse_byday(s):
        """Wochentag-Eingabe → Liste iCal-Codes. 'Di' → ['TU'], 'Mo,Mi,Fr' →
        ['MO','WE','FR']. None bei Unsinn. Akzeptiert dt. Kürzel (erste 2 Buchst.)
        ODER direkt die Codes (MO..SU)."""
        out = []
        for p in (s or "").replace(" ", ",").split(","):
            p = p.strip()
            if not p:
                continue
            code = KAL_BYDAY.get(p[:2].lower())
            if not code and p.upper() in KAL_BYDAY.values():
                code = p.upper()
            if code and code not in out:
                out.append(code)
        return out or None

    def k_add_save():
        """Add-/Edit-Formular absenden. Routine (atype) → wöchentliche Routine
        anlegen; sonst Einmal-Termin neu (POST) oder ändern (PUT). Konflikt-
        Hinweis mitnehmen, zurück in die View."""
        label = K["alabel"].strip()
        if not label:
            K["amsg"] = "titel fehlt"; return
        time = K["atime"].strip() or None
        if time and parse_clock(time) is None:
            K["amsg"] = "zeit? HH:MM (leer=ganztags)"; return

        if K["atype"] == "routine":            # NEUE wöchentliche Routine
            days = k_parse_byday(K["aday"])
            if not days:
                K["amsg"] = "wochentag? Mo/Di/.."; return
            try:
                api_call("/api/calendar/routine", method="POST",
                         body={"label": label, "byday": days, "time": time})
                K["msg"] = "Routine angelegt: " + label
                K["data"] = None; K["mode"] = "view"; K["astage"] = 0
                K["atype"] = "entry"
                K["aday"] = K["atime"] = K["alabel"] = K["amsg"] = ""
            except Exception:
                K["amsg"] = "speichern fehlgeschlagen"
            return

        day = k_parse_day(K["aday"])
        if day is None:
            K["amsg"] = "datum? TT.MM"; return
        new = {"day": day, "label": label}
        if time:
            new["time"] = time
        try:
            if K["editing"]:
                old_iso, old_label, old_layer = K["editing"]
                res = api_call("/api/calendar/entry", method="PUT",
                               body={"day": old_iso, "label": old_label,
                                     "layer": old_layer, "new": new})
                verb = "geändert: "
            else:
                res = api_call("/api/calendar/entry", method="POST", body=new)
                verb = "angelegt: "
            conf = (res or {}).get("conflicts") or []
            K["msg"] = verb + label + (" ⚠" if conf else "")
            K["ref"] = day; K["data"] = None       # zur Woche des Termins springen
            K["mode"] = "view"; K["astage"] = 0; K["editing"] = None
            K["aday"] = K["atime"] = K["alabel"] = K["amsg"] = ""
        except Exception:
            K["amsg"] = "speichern fehlgeschlagen"

    def k_begin_edit():
        """Den ausgewählten Eintrag bearbeiten: Einmal-Termin → Ändern-Formular
        (vorbefüllt); Routine-Vorkommen → De-/Aktivieren-Screen."""
        sels = k_selectable()
        if not sels or not (0 <= K["sel"] < len(sels)):
            return
        it = sels[K["sel"]]
        if it["recurring"]:
            K["mode"] = "routine"; K["ract"] = it; K["msg"] = ""
        else:
            K["mode"] = "add"; K["astage"] = 0; K["amsg"] = ""; K["msg"] = ""
            K["atype"] = "entry"           # Ändern gibt es nur für Einmal-Termine
            K["editing"] = (it["iso"], it["label"], it["layer"])
            K["aday"] = date.fromisoformat(it["iso"]).strftime("%d.%m")
            K["atime"] = it.get("time") or ""
            K["alabel"] = it["label"]

    def k_delete_sel(item):
        day, label, layer = item
        try:
            res = api_call("/api/calendar/entry", method="DELETE",
                           body={"day": day, "label": label, "layer": layer})
            n = (res or {}).get("deleted", 0)
            K["msg"] = ("gelöscht: " + label) if n else "nichts gelöscht"
        except Exception:
            K["msg"] = "löschen fehlgeschlagen"
        K["data"] = None

    def k_routine_toggle(off):
        """Das im Routine-Screen gewählte EINZELNE Vorkommen de-/aktivieren
        (POST /api/calendar/routine/skip). off=True deaktiviert, False aktiviert."""
        it = K["ract"]
        if not it:
            K["mode"] = "view"; return
        try:
            res = api_call("/api/calendar/routine/skip", method="POST",
                           body={"layer": it["layer"], "label": it["label"],
                                 "day": it["iso"], "off": off, "time": it.get("time")})
            # `changed` ehrlich auswerten: traf der Skip keine an dem Tag
            # vorkommende Routine (z.B. Namens-Verwechslung), passiert nichts —
            # das soll der User sehen, nicht ein falsches „deaktiviert".
            if (res or {}).get("changed"):
                K["msg"] = ("deaktiviert: " if off else "aktiviert: ") + it["label"]
            else:
                K["msg"] = "keine passende Routine an dem Tag"
        except Exception:
            K["msg"] = "fehlgeschlagen (backend neu starten?)"
        K["mode"] = "view"; K["ract"] = None; K["data"] = None

    def k_routine_delete():
        """Die GANZE Routine löschen (DELETE /api/calendar/routine) — alle
        Vorkommen weg, nicht nur dieser eine Tag."""
        it = K["ract"]
        if not it:
            K["mode"] = "view"; K["rconfirm"] = False; return
        try:
            res = api_call("/api/calendar/routine", method="DELETE",
                           body={"layer": it["layer"], "label": it["label"],
                                 "day": it["iso"], "time": it.get("time")})
            n = (res or {}).get("deleted", 0)
            K["msg"] = ("Routine gelöscht: " + it["label"]) if n else "nichts gelöscht"
        except Exception:
            K["msg"] = "löschen fehlgeschlagen"
        K["mode"] = "view"; K["ract"] = None; K["rconfirm"] = False; K["data"] = None

    def _k_entry_line(e):
        """Eine Termin-Zeile kompakt: Zeit(spanne) + Label (+ Ort). Ausfall
        (Ferien) als ℹ-Hinweis statt Termin — wie render_range_for_tool."""
        if e.get("ausfall"):
            return "ℹ %s fällt aus" % e.get("label", "?")
        if e.get("time") and e.get("ende"):
            t = "%s-%s " % (e["time"], e["ende"])
        elif e.get("time"):
            t = "%s " % e["time"]
        else:
            t = ""
        ort = " @%s" % e["ort"] if e.get("ort") else ""
        return "%s%s%s" % (t, e.get("label", "?"), ort)

    def draw_calendar(by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn der Kalender Fokus hat. Holt bei Bedarf
        frische Daten (Blättern/Umschalten) und zeichnet Woche (Liste) oder
        Monat (Gitter) — die Datums-Logik kam fertig vom Backend."""
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2          # Status-/Hilfezeile unten in der Box
        if iw < 8:
            return
        if (not K["data"]) or K["data"].get("_for") != (K["view"], K["ref"]):
            k_fetch()
            if isinstance(K["data"], dict):
                K["data"]["_for"] = (K["view"], K["ref"])
        d = K["data"]
        if not d or d.get("failed"):
            addclip(by + 1, ix, K["msg"] or "lade kalender…", iw, C["faint"])
            return

        # Defensiv wie der ganze Render-Pfad: alles kommt über HTTP/JSON, ein
        # kaputtes Backend kann statt dict/list auch String/Zahl/None liefern.
        days = d.get("days")
        if not isinstance(days, dict):
            days = {}
        today = d.get("today")
        label = d.get("label", "")
        if not isinstance(label, str):
            label = ""
        alarms = d.get("alarms")
        nalarm = len(alarms) if isinstance(alarms, list) else 0
        head = ("Woche " if K["view"] == "week" else "Monat ") + label
        if nalarm:
            head += "  ⚠%d" % nalarm
        addclip(by + 1, ix, head, iw, C["bright"])

        # Add-/Edit-Formular hat Vorrang: füllt den Body, wenn mode == "add".
        if K["mode"] == "add":
            fy = by + 3
            cz = "_"                        # Cursor-Marker an der aktiven Stufe
            is_rt = (K["atype"] == "routine")
            if K["editing"]:
                title = "TERMIN ÄNDERN"
            else:
                title = "NEUE ROUTINE" if is_rt else "NEUER TERMIN"
            addclip(fy, ix, title, iw, C["bright"])
            # Typ-Umschalter (nur bei Neuanlage, nicht beim Ändern).
            if not K["editing"]:
                te = "[Termin]" if not is_rt else " Termin "
                tr = "[Routine]" if is_rt else " Routine "
                safe_addstr(fy, ix + len(title) + 3, te, C["acc"] if not is_rt else C["faint"])
                safe_addstr(fy, ix + len(title) + 3 + len(te) + 1, tr, C["acc"] if is_rt else C["faint"])
                safe_addstr(fy, ix + len(title) + 3 + len(te) + 1 + len(tr) + 2, "(Tab)", C["faint"])
            if is_rt:
                addclip(fy + 2, ix, "Tag:   " + K["aday"] + (cz if K["astage"] == 0 else "")
                        + "   (Mo/Di/.., mehrere mit Komma)", iw,
                        C["bright"] if K["astage"] == 0 else C["dim"])
            else:
                addclip(fy + 2, ix, "Datum: " + K["aday"] + (cz if K["astage"] == 0 else "")
                        + "   (TT.MM, leer=heute)", iw, C["bright"] if K["astage"] == 0 else C["dim"])
            addclip(fy + 3, ix, "Zeit:  " + K["atime"] + (cz if K["astage"] == 1 else "")
                    + "   (HH:MM, leer=ganztags)", iw, C["bright"] if K["astage"] == 1 else C["dim"])
            addclip(fy + 4, ix, "Titel: " + K["alabel"] + (cz if K["astage"] == 2 else ""),
                    iw, C["bright"] if K["astage"] == 2 else C["dim"])
            addclip(bottom, ix, ("enter weiter/speichern · esc zurück  " + K["amsg"]).strip(),
                    iw, C["faint"])
            return

        # Routine-Screen: ein einzelnes Vorkommen de-/aktivieren ODER die ganze
        # Routine löschen.
        if K["mode"] == "routine":
            it = K["ract"] or {}
            fy = by + 3
            try:
                wd = KAL_WD[date.fromisoformat(it.get("iso", "")).weekday()]
                dd = date.fromisoformat(it["iso"]).strftime("%d.%m.%Y")
            except (KeyError, ValueError):
                wd, dd = "", it.get("iso", "")
            t = (it.get("time") or "")
            addclip(fy, ix, "ROUTINE-TERMIN", iw, C["bright"])
            addclip(fy + 2, ix, "%s  ·  %s %s %s" % (it.get("label", "?"), wd, dd, t), iw, C["dim"])
            if K["rconfirm"]:
                addclip(fy + 4, ix, "GANZE Routine '%s' löschen?" % it.get("label", "?"), iw, C["warn"])
                addclip(fy + 5, ix, "(alle Vorkommen, unwiderruflich)", iw, C["faint"])
                addclip(bottom, ix, "j = ja, löschen · sonst abbrechen", iw, C["faint"])
            elif it.get("deaktiviert"):
                addclip(fy + 4, ix, "Dieser Termin ist DEAKTIVIERT.", iw, C["faint"])
                addclip(bottom, ix, "a = wieder aktivieren · x = Routine ganz löschen · esc", iw, C["faint"])
            else:
                addclip(fy + 4, ix, "Nur DIESEN Termin deaktivieren (d)?", iw, C["dim"])
                addclip(fy + 5, ix, "oder die GANZE Routine löschen (x)?", iw, C["faint"])
                addclip(bottom, ix, "d = nur dieser aus · x = ganze Routine löschen · esc", iw, C["faint"])
            return

        if K["view"] == "month":
            # Monatsgitter: 7 Spalten Mo-So, bis zu 6 Wochenzeilen.
            colw = max(3, iw // 7)
            for c, wd in enumerate(KAL_WD):
                addclip(by + 2, ix + c * colw, wd, colw, C["faint"])
            try:
                start = date.fromisoformat(d["start"]); end = date.fromisoformat(d["end"])
                first = date.fromisoformat(d["first"]); last = date.fromisoformat(d["last"])
            except (KeyError, ValueError):
                return
            row, cur = by + 3, start
            while cur <= end and row < bottom:
                c = cur.weekday()
                iso = cur.isoformat()
                in_month = first <= cur <= last
                ents = days.get(iso)
                has = bool(ents) and isinstance(ents, list)
                cell = "%2d" % cur.day + ("•" if has else "")
                if iso == today:
                    attr = C["bright"] | curses.A_REVERSE
                elif not in_month:
                    attr = C["faint"]
                elif has:
                    attr = C["acc"]
                else:
                    attr = C["dim"]
                addclip(row, ix + c * colw, cell, colw, attr)
                if c == 6:                 # Sonntag → nächste Zeile
                    row += 1
                cur += timedelta(days=1)
        else:
            # Wochenliste: pro Tag eine Kopfzeile, Termine eingerückt darunter.
            # ALLE Termine (Einmal + Routine) sind auswählbar (›-Cursor, K["sel"]);
            # nur Ausfälle (Ferien) sind reine Info. Reihenfolge = k_selectable().
            try:
                start = date.fromisoformat(d["start"]); end = date.fromisoformat(d["end"])
            except (KeyError, ValueError):
                return
            nsel = len(k_selectable())
            if K["sel"] >= nsel:
                K["sel"] = max(0, nsel - 1)
            di = 0                          # läuft über die auswählbaren Termine
            yy, cur = by + 2, start
            while cur <= end and yy < bottom:
                iso = cur.isoformat()
                ents = days.get(iso)
                if not isinstance(ents, list):
                    ents = []
                is_today = (iso == today)
                hdr = "%s %s" % (KAL_WD[cur.weekday()], cur.strftime("%d.%m."))
                addclip(yy, ix, hdr + ("  ‹heute›" if is_today else ""), iw,
                        C["bright"] if is_today else C["acc"])
                yy += 1
                shown = False
                for e in ents:
                    if yy >= bottom:
                        break
                    if not isinstance(e, dict):
                        continue
                    shown = True
                    if e.get("ausfall"):        # Info-Zeile, nicht auswählbar
                        addclip(yy, ix, "  " + _k_entry_line(e), iw, C["faint"]); yy += 1
                        continue
                    selected = (di == K["sel"])
                    deakt = bool(e.get("deaktiviert"))
                    mark = "› " if selected else "  "
                    if deakt:
                        # Deaktiviert IMMER klar gedimmt zeigen — auch wenn
                        # selektiert (sonst überdeckt das helle Invers die
                        # Markierung und es sieht aus wie „nichts passiert").
                        # Selektion bleibt über den ›-Cursor erkennbar; das
                        # ✗-Präfix + „(deaktiviert)" macht den Aus-Zustand eindeutig.
                        attr = C["faint"]
                        txt = "✗ " + _k_entry_line(e) + "  (deaktiviert)"
                    elif selected:
                        attr = C["bright"] | curses.A_REVERSE
                        txt = _k_entry_line(e)
                    else:
                        attr = C["dim"]
                        txt = _k_entry_line(e)
                    addclip(yy, ix, mark + txt, iw, attr)
                    di += 1; yy += 1
                if not shown and yy < bottom:
                    addclip(yy, ix + 2, "—", iw - 2, C["faint"]); yy += 1
                cur += timedelta(days=1)

        info = "%s · %s" % ("woche" if K["view"] == "week" else "monat", label)
        addclip(bottom, ix, info, iw, C["bright"])
        if K["confirmdel"]:                    # Shortcuts liegen unter '/'
            hint = "löschen? j/n"
        else:
            hint = K["msg"]
        if hint:
            addclip(bottom, ix + iw - len(hint), hint, len(hint), C["faint"])

    # ── Post/Mail-Panel: laden / pollen / zeichnen ─────────────────────
    def mail_load():
        """Kategorie-Übersicht read-only holen (inkl. Live-Zähl-Cache)."""
        try:
            MAIL["data"] = api_call("/api/mail", timeout=2.0)
            MAIL["msg"] = ""
        except Exception:
            MAIL["data"] = {"failed": True}
            MAIL["msg"] = "mail: backend?"
        MAIL["_ts"] = time.time()

    def mail_refresh_counts():
        """Live-Ordnerzählung im Backend anstoßen (fire-and-forget). Die echten
        Zahlen tröpfeln per Auto-Refresh nach — friert die TUI nicht ein."""
        try:
            api_call("/api/mail/refresh-counts", method="POST", timeout=2.0)
        except Exception:
            pass

    def mail_open_category(name):
        """Eine Kategorie öffnen: Mails LIVE aus dem echten Ordner holen (mit
        Key) bzw. lokalen Schnappschuss (ohne). Blockiert kurz — bewusste Aktion."""
        MAIL["cat"] = name
        MAIL["level"] = "mails"
        MAIL["off"] = 0
        MAIL["mode2"] = "read"; MAIL["msel"] = 0
        MAIL["expanded"] = False; MAIL["bodyoff"] = 0
        MAIL["body"] = None; MAIL["bodyfor"] = None
        MAIL["picking"] = False; MAIL["confirmdel"] = False
        MAIL["mails"] = None          # None ⇒ „lädt…"
        MAIL["mails_live"] = False
        MAIL["msg"] = ""
        try:
            q = "/api/mail/folder?cat=" + urllib.parse.quote(name or "")
            r = api_call(q, timeout=12.0)
            if isinstance(r, dict):
                MAIL["mails"] = r.get("mails") if isinstance(r.get("mails"), list) else []
                MAIL["mails_live"] = bool(r.get("live"))
            else:
                MAIL["mails"] = []
        except Exception:
            MAIL["mails"] = []
            MAIL["msg"] = "ordner: backend?"

    def mail_cur():
        """Die aktuell ausgewählte Mail (oder None)."""
        ms = MAIL["mails"] or []
        return ms[MAIL["msel"]] if 0 <= MAIL["msel"] < len(ms) else None

    def mail_load_body():
        """Body der aktuellen Mail live nachladen (gecacht je uid). Blockiert kurz."""
        it = mail_cur()
        if not it:
            MAIL["body"] = None; MAIL["bodyfor"] = None
            return
        uid = it.get("uid")
        if MAIL["bodyfor"] == uid and MAIL["body"] is not None:
            return
        MAIL["body"] = None          # None ⇒ „lädt…"
        try:
            q = ("/api/mail/body?cat=" + urllib.parse.quote(MAIL["cat"] or "")
                 + "&uid=" + str(uid)
                 + "&account=" + urllib.parse.quote(it.get("account") or ""))
            r = api_call(q, timeout=20.0)
            MAIL["body"] = r if isinstance(r, dict) else {"error": "?"}
        except urllib.error.HTTPError as e:
            # Den ECHTEN Grund zeigen (z.B. 409 „kein key") statt „backend?".
            try:
                j = json.loads(e.read().decode("utf-8"))
                MAIL["body"] = {"error": j.get("error", "HTTP %d" % e.code)}
            except Exception:
                MAIL["body"] = {"error": "HTTP %d" % e.code}
        except Exception as ex:
            MAIL["body"] = {"error": "%s (Backend erreichbar?)" % type(ex).__name__}
        MAIL["bodyfor"] = uid
        MAIL["bodyoff"] = 0

    def mail_refetch():
        """Die Mails der aktuellen Kategorie frisch holen (nach Umsortieren/
        Löschen verschwinden verschobene Mails hier). Behält den Modus."""
        if not MAIL["cat"]:
            return
        try:
            q = "/api/mail/folder?cat=" + urllib.parse.quote(MAIL["cat"])
            r = api_call(q, timeout=12.0)
            if isinstance(r, dict):
                MAIL["mails"] = r.get("mails") if isinstance(r.get("mails"), list) else []
                MAIL["mails_live"] = bool(r.get("live"))
        except Exception:
            pass
        ms = MAIL["mails"] or []
        MAIL["msel"] = max(0, min(MAIL["msel"], max(0, len(ms) - 1)))
        MAIL["body"] = None; MAIL["bodyfor"] = None

    def mail_assign(category):
        """Den ABSENDER der aktuellen Mail einer Kategorie zuordnen UND alle
        seine vorhandenen Mails dorthin verschieben (Backend macht das live)."""
        it = mail_cur()
        if not it:
            MAIL["picking"] = False
            return
        MAIL["picking"] = False
        try:
            r = api_call("/api/mail/assign", method="POST",
                         body={"sender": it.get("from") or "", "category": category},
                         timeout=30.0)
            moved = (r or {}).get("moved", 0) if isinstance(r, dict) else 0
            MAIL["msg"] = "absender → %s (%d verschoben)" % (category, moved)
        except Exception:
            MAIL["msg"] = "einsortieren: backend?"
        mail_refetch()                 # umsortierte Mails fallen aus dieser Liste
        mail_refresh_counts()          # echte Ordnergrößen neu zählen

    def mail_delete():
        """Die aktuelle Mail in den Papierkorb (umkehrbar) und aus der Liste raus."""
        it = mail_cur()
        ms = MAIL["mails"] or []
        if not it:
            MAIL["confirmdel"] = False
            return
        try:
            r = api_call("/api/mail/delete", method="POST",
                         body={"cat": MAIL["cat"], "uid": it.get("uid"),
                               "account": it.get("account")}, timeout=12.0)
            if isinstance(r, dict) and r.get("ok"):
                del ms[MAIL["msel"]]
                MAIL["msel"] = max(0, min(MAIL["msel"], len(ms) - 1))
                MAIL["body"] = None; MAIL["bodyfor"] = None
                MAIL["msg"] = "gelöscht (Papierkorb)"
            else:
                MAIL["msg"] = "löschen abgelehnt"
        except Exception:
            MAIL["msg"] = "löschen: backend?"
        MAIL["confirmdel"] = False

    def _wrap(text, width):
        """Text auf `width` umbrechen (wortweise), Zeilenumbrüche erhalten."""
        out = []
        for para in (text or "").replace("\r", "").split("\n"):
            if not para:
                out.append("")
                continue
            while len(para) > width:
                cut = para.rfind(" ", 0, width)
                if cut <= 0:
                    cut = width
                out.append(para[:cut])
                para = para[cut:].lstrip()
            out.append(para)
        return out

    def mail_poll():
        """Live-Poll im Backend anstoßen (POST). Kehrt sofort zurück — der
        Fortschritt läuft über das Log links. Braucht Passphrase (Env/Keyring)."""
        try:
            r = api_call("/api/mail/poll", method="POST", timeout=4.0)
            if isinstance(r, dict) and r.get("error"):
                MAIL["msg"] = "kein key — keyring-set nötig"
            elif isinstance(r, dict) and r.get("already"):
                MAIL["msg"] = "poll läuft schon…"
            else:
                MAIL["msg"] = "poll gestartet — siehe log links"
        except Exception:
            MAIL["msg"] = "poll: backend?"

    def _mail_line(it):
        """Absender + Betreff kompakt für eine Mail-Zeile."""
        who = (it.get("from") or "?").strip()
        subj = (it.get("subject") or "").strip() or "(kein Betreff)"
        return "%s — %s" % (who, subj)

    def draw_mail(by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn das Post/Mail-Panel Fokus hat. Zwei Ebenen:
        Ebene 'cats' = nur die Kategorien (zum Auswählen); Ebene 'mails' = die
        Mails der geöffneten Kategorie. Rein lesend, Auto-Refresh alle ~3s."""
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2
        if iw < 8:
            return
        if (not MAIL["data"]) or (time.time() - MAIL["_ts"] > 3):
            mail_load()
        d = MAIL["data"]
        if not isinstance(d, dict) or d.get("failed"):
            addclip(by + 1, ix, MAIL["msg"] or "lade mail…", iw, C["faint"])
            return

        cats = d.get("categories") if isinstance(d.get("categories"), list) else []
        live_counts = d.get("live_counts") if isinstance(d.get("live_counts"), dict) else {}
        refreshing = bool(d.get("counts_refreshing"))
        can_poll = bool(d.get("can_poll"))
        polling = bool(d.get("polling"))
        body_top = by + 3
        avail = bottom - body_top

        # ── Ebene 2: Mails der geöffneten Kategorie (LIVE aus dem Ordner) ─
        if MAIL["level"] == "mails" and MAIL["cat"] is not None:
            cat = MAIL["cat"]
            mails = MAIL["mails"]
            src = "live" if MAIL["mails_live"] else "lokal"
            cnt = "…" if mails is None else str(len(mails))
            modetag = "lesen" if MAIL["mode2"] == "read" else "liste"
            head = "Post · %s (%s)" % (cat[:max(4, iw - 22)], cnt)
            if mails is not None:
                head += "  [%s/%s]" % (modetag, src)
            addclip(by + 1, ix, head, iw, C["bright"])
            if mails is None:
                addclip(body_top, ix, "lädt Ordner…", iw, C["faint"])
                addclip(bottom, ix, "esc zurück", iw, C["faint"])
                return
            n = len(mails)
            MAIL["msel"] = max(0, min(MAIL["msel"], max(0, n - 1)))

            # Einsortier-Picker überlagert alles: Zielkategorie wählen.
            if MAIL["picking"]:
                pcats = [str(c.get("name", "?")) for c in cats]
                psel = max(0, min(MAIL["picksel"], max(0, len(pcats) - 1)))
                MAIL["picksel"] = psel
                addclip(body_top, ix, "Absender einsortieren in:", iw, C["acc"])
                pavail = bottom - (body_top + 1) - 1
                poff = max(0, min(psel - pavail // 2, max(0, len(pcats) - pavail))) \
                    if len(pcats) > pavail else 0
                for r, name in enumerate(pcats[poff:poff + pavail]):
                    idx = poff + r
                    mark = "» " if idx == psel else "  "
                    attr = (C["bright"] | curses.A_REVERSE) if idx == psel else C["bright"]
                    addclip(body_top + 1 + r, ix, mark + name, iw, attr)
                addclip(bottom, ix, "↑↓ wählen · enter zuordnen · esc abbrechen",
                        iw, C["faint"])
                return

            if n == 0:
                addclip(body_top, ix, "(Ordner leer)", iw, C["faint"])
                addclip(bottom, ix, "esc zurück", iw, C["faint"])
                return

            # ── Modus LISTE: Blöckchen (Absender + Titel), auswählbar ──
            if MAIL["mode2"] == "list":
                blockh = 3
                vis = max(1, avail // blockh)
                start = max(0, min(MAIL["msel"] - vis // 2, max(0, n - vis)))
                for r in range(vis):
                    idx = start + r
                    if idx >= n:
                        break
                    it = mails[idx]
                    y = body_top + r * blockh
                    seld = (idx == MAIL["msel"])
                    who = (it.get("from") or "?").strip()
                    subj = (it.get("subject") or "").strip() or "(kein Betreff)"
                    a1 = (C["bright"] | curses.A_REVERSE) if seld else C["bright"]
                    a2 = (C["dim"] | curses.A_REVERSE) if seld else C["dim"]
                    addclip(y, ix, ("» " if seld else "  ") + who, iw, a1)
                    addclip(y + 1, ix, "  " + subj, iw, a2)
                hint = "wirklich löschen? j/n" if MAIL["confirmdel"] else MAIL["msg"]
                if hint:                       # Shortcuts liegen unter '/'
                    addclip(bottom, ix, hint, iw, C["faint"])
                return

            # ── Modus LESEN: eine Mail, Vorschau / ausgeklappt ──
            it = mails[MAIL["msel"]]
            mail_load_body()
            who = (it.get("from") or "?").strip()
            subj = (it.get("subject") or "").strip() or "(kein Betreff)"
            addclip(body_top, ix, "Von:     " + who, iw, C["bright"])
            addclip(body_top + 1, ix, "Betreff: " + subj, iw, C["acc"])
            addclip(body_top + 2, ix, "─" * iw, iw, C["faint"])
            txt_top = body_top + 3
            txt_h = bottom - txt_top
            b = MAIL["body"]
            if b is None:
                addclip(txt_top, ix, "lädt Text…", iw, C["faint"])
            elif isinstance(b, dict) and b.get("error"):
                addclip(txt_top, ix, "(Text nicht ladbar: %s)" % b["error"], iw, C["faint"])
            else:
                lines = _wrap((b or {}).get("body", ""), iw)
                if MAIL["expanded"]:
                    boff = max(0, min(MAIL["bodyoff"], max(0, len(lines) - txt_h)))
                    MAIL["bodyoff"] = boff
                    for r, ln in enumerate(lines[boff:boff + txt_h]):
                        addclip(txt_top + r, ix, ln, iw, C["dim"])
                else:
                    prev_h = min(txt_h, 6)
                    for r, ln in enumerate(lines[:prev_h]):
                        addclip(txt_top + r, ix, ln, iw, C["dim"])
                    if len(lines) > prev_h:
                        addclip(txt_top + prev_h, ix, "  … (e zum Ausklappen)",
                                iw, C["faint"])
            if MAIL["confirmdel"]:
                hint = "wirklich löschen? j/n"
            else:                              # Shortcuts liegen unter '/'; nur Position/Feedback
                hint = MAIL["msg"] or ("%d/%d" % (MAIL["msel"] + 1, n))
            addclip(bottom, ix, hint, iw, C["faint"])
            return

        # ── Ebene 1: nur die Kategorien (Auswahl) ─────────────────────
        head = "Postfach · %d Kategorien" % len(cats)
        if polling:
            head += "  ⟳ poll läuft"
        elif refreshing:
            head += "  ⟳ zähle…"
        elif not can_poll:
            head += "  (kein key)"
        addclip(by + 1, ix, head, iw, C["bright"])
        n = len(cats)
        sel = max(0, min(MAIL["sel"], max(0, n - 1)))
        MAIL["sel"] = sel
        off = max(0, min(sel - avail // 2, max(0, n - avail))) if n > avail else 0
        if not cats:
            addclip(body_top, ix, "noch keine Kategorien.", iw, C["faint"])
        namew = max(4, iw - 6)
        for r, c in enumerate(cats[off:off + avail]):
            idx = off + r
            name = str(c.get("name", "?"))
            # Live-Ordnerzahl bevorzugen (echte Größe); sonst lokaler Schnappschuss.
            cnt = live_counts.get(name, c.get("count", 0))
            mark = "» " if idx == sel else "  "
            line = "%s%-*s%4d" % (mark, namew - 2, name[:namew - 2], cnt)
            attr = (C["bright"] | curses.A_REVERSE) if idx == sel else C["bright"]
            addclip(body_top + r, ix, line, iw, attr)
        src = "live" if live_counts else "lokal"
        # Shortcuts liegen unter '/'; unten nur Feedback bzw. die Datenquelle.
        hint = MAIL["msg"] or ("[%s]" % src)
        addclip(bottom, ix, hint, iw, C["faint"])

    def mail_reply_open():
        """Antwort-Editor öffnen: stellt sicher, dass der Original-Body geladen
        ist (linke Spalte), startet mit leerem Text."""
        it = mail_cur()
        if not it:
            return
        mail_load_body()
        MAIL["replying"] = True
        MAIL["reply_text"] = ""
        MAIL["reply_origoff"] = 0
        MAIL["reply_confirm"] = False
        MAIL["msg"] = ""

    def mail_reply_send():
        """Den getippten Text als Antwort senden (SMTP via Backend). Blockiert
        kurz; bei Erfolg schließt der Editor."""
        it = mail_cur()
        if not it or not MAIL["reply_text"].strip():
            MAIL["reply_confirm"] = False
            MAIL["msg"] = "leer — nichts gesendet"
            MAIL["replying"] = False
            return
        try:
            r = api_call("/api/mail/reply", method="POST",
                         body={"cat": MAIL["cat"], "uid": it.get("uid"),
                               "account": it.get("account"),
                               "text": MAIL["reply_text"]}, timeout=30.0)
            if isinstance(r, dict) and r.get("ok"):
                MAIL["msg"] = "✓ Antwort gesendet"
            else:
                MAIL["msg"] = "senden fehlgeschlagen: %s" % (
                    (r or {}).get("error", "?") if isinstance(r, dict) else "?")
        except Exception:
            MAIL["msg"] = "senden: backend?"
        MAIL["replying"] = False
        MAIL["reply_confirm"] = False

    def draw_reply(by, bx, bh, bw):
        """Antwort-Editor: zwei Kästen nebeneinander — links die Original-Mail,
        rechts dein Antwort-Text (Editor mit Cursor)."""
        gap = 1
        half = (bw - gap) // 2
        lw, rw = half, bw - gap - half
        # Linker Kasten: Original
        draw_box(by, bx, bh, lw, "original")
        it = mail_cur() or {}
        b = MAIL["body"] if isinstance(MAIL["body"], dict) else {}
        lix, liw = bx + 2, lw - 4
        addclip(by + 1, lix, "Von:     " + (it.get("from") or "?"), liw, C["dim"])
        addclip(by + 2, lix, "Betreff: " + (it.get("subject") or ""), liw, C["dim"])
        addclip(by + 3, lix, "─" * liw, liw, C["faint"])
        olines = _wrap(b.get("body", "") if b else "", liw)
        oh = (by + bh - 2) - (by + 4)
        ooff = max(0, min(MAIL["reply_origoff"], max(0, len(olines) - oh)))
        MAIL["reply_origoff"] = ooff
        for r, ln in enumerate(olines[ooff:ooff + oh]):
            addclip(by + 4 + r, lix, ln, liw, C["faint"])

        # Rechter Kasten: dein Editor
        rbx = bx + lw + gap
        title = "antwort" + ("  · SENDEN? j/n" if MAIL["reply_confirm"] else "")
        draw_box(by, rbx, bh, rw, title)
        rix, riw = rbx + 2, rw - 4
        to = ""
        try:
            import email.utils as _eu
            to = _eu.parseaddr(it.get("from", ""))[1] or it.get("from", "")
        except Exception:
            to = it.get("from", "")
        addclip(by + 1, rix, "An: " + to, riw, C["dim"])
        addclip(by + 2, rix, "─" * riw, riw, C["faint"])
        ed_top = by + 3
        ed_h = (by + bh - 2) - ed_top
        elines = _wrap(MAIL["reply_text"], riw) or [""]
        # Cursor ans Ende; nur das untere Fenster zeigen, wenn länger als Platz.
        estart = max(0, len(elines) - ed_h)
        for r, ln in enumerate(elines[estart:estart + ed_h]):
            cur = "_" if (estart + r == len(elines) - 1) else ""
            addclip(ed_top + r, rix, ln + cur, riw, C["bright"])
        if MAIL["reply_confirm"]:
            hint = "j senden · n verwerfen · w weiter schreiben"
        else:
            hint = "tippen · enter=zeile · esc=fertig/senden"
        addclip(by + bh - 2, rix, hint[:riw], riw, C["faint"])

    def in_text_entry():
        """Tippt der Nutzer gerade einen Freitext (Name, Eintrag, Antwort)?
        Dann bleibt '/' ein normales Zeichen und öffnet NICHT die Befehlszeile."""
        if G["active"]:
            return G["view"] in ("new", "view")      # Name bzw. Werteingabe
        if L["active"]:
            return L["adding"] or L["view"] in ("new", "move_new")
        if K["active"]:
            return K["mode"] == "add"                 # Termin/Routine anlegen+bearbeiten
        if MAIL["active"]:
            return MAIL["replying"]
        return False

    def current_ctx():
        """Kontext-Schlüssel des fokussierten Fensters für die '/'-Anzeige.
        None = Tipp-Screen ohne eigene Shortcut-Liste."""
        if G["active"]:
            return "graph" if G["view"] == "list" else None
        if L["active"]:
            v = L["view"]
            if v == "list":
                return "list:list"
            if v == "view" and not L["adding"]:
                return "list:view"
            if v in ("place", "move"):
                return "list:pick"
            return None
        if M["active"]:
            return "map"
        if K["active"]:
            if K["mode"] != "view":
                return None
            return "cal:week" if K["view"] == "week" else "cal:month"
        if MAIL["active"]:
            if MAIL["replying"] or MAIL.get("picking"):
                return None
            if MAIL["level"] == "cats":
                return "mail:cats"
            return "mail:read" if MAIL["mode2"] == "read" else "mail:list"
        return "home"

    while True:
        # Während einer Länder-Kamerafahrt schneller ticken (~30 fps) für weiche
        # Bewegung; sonst die ruhige 250-ms-Kadenz (spart CPU/Backend-Last).
        stdscr.timeout(33 if (M["active"] and M.get("anim")) else 250)
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
        elif ch == ord("/") and not in_text_entry():
            # '/' greift JETZT in jedem Fenster (nicht nur Home): blendet die
            # Shortcuts des fokussierten Fensters ein. In Freitext-Feldern bleibt
            # '/' ein Zeichen (siehe in_text_entry), darum hier das Guard.
            cmd_mode = True; cmd_buf = "/"; cmd_msg = ""
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
                        G["input2"] = ""; G["pstage"] = 0; G["dayoff"] = 0
                        G["view"] = "view"; g_load_vals()
                elif ch in (ord("n"), ord("N")):
                    G["view"] = "new"; G["input"] = ""; G["newtype"] = "number"; G["msg"] = ""
                elif ch in (ord("d"), ord("D")):
                    if G["graphs"]:
                        G["confirm"] = True; G["msg"] = ""
                elif ch in (ord("p"), ord("P")):              # vorhersage-ergänzung an/aus
                    if G["graphs"]:
                        cur = G["graphs"][G["sel"]]
                        try:
                            api_call("/api/graphs/%s/predict" % cur["id"], method="POST",
                                     body={"predict": not cur.get("predict")})
                            g_load()
                        except Exception:
                            G["msg"] = "predict fehlgeschlagen"
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
                        G["pstage"] = 0; G["msg"] = ""; G["dayoff"] = 0
                elif ch == curses.KEY_LEFT:                     # Ziel-Tag einen zurück
                    G["dayoff"] = min(365, G.get("dayoff", 0) + 1); G["msg"] = ""
                elif ch == curses.KEY_RIGHT:                    # … wieder vor (max heute)
                    G["dayoff"] = max(0, G.get("dayoff", 0) - 1); G["msg"] = ""
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
        elif L["active"]:                      # Listen-Werkzeug hat den Fokus
            if L["view"] == "list":
                if L["confirm"]:                              # Lösch-Nachfrage offen
                    if ch in (ord("y"), ord("Y"), ord("j"), ord("J"),
                              10, 13, curses.KEY_ENTER):
                        try:
                            api_call("/api/lists/" + L["lists"][L["sel"]]["id"], method="DELETE")
                            L["msg"] = "gelöscht"
                        except Exception:
                            L["msg"] = "löschen fehlgeschlagen"
                        L["confirm"] = False
                        l_load()
                    elif ch != -1:                            # alles andere → abbrechen
                        L["confirm"] = False; L["msg"] = ""
                elif ch in (27, ord("l"), ord("L")):           # Esc/l → Werkzeug zu
                    L["active"] = False
                elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
                    break
                elif ch in (curses.KEY_UP, ord("k")):
                    L["sel"] = max(0, L["sel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    L["sel"] = min(max(0, len(L["lists"]) - 1), L["sel"] + 1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    if L["lists"]:
                        L["def"] = L["lists"][L["sel"]]; L["isel"] = 0
                        L["path"] = []            # frisch auf oberster Ebene
                        L["adding"] = False; L["input"] = ""; L["msg"] = ""
                        L["view"] = "view"
                elif ch in (ord("n"), ord("N")):
                    L["view"] = "new"; L["lrename"] = None; L["input"] = ""; L["msg"] = ""
                elif ch in (ord("r"), ord("R")):              # gewählte Liste umbenennen
                    if L["lists"]:
                        cur = L["lists"][L["sel"]]
                        L["view"] = "new"; L["lrename"] = cur["id"]
                        L["input"] = str(cur.get("name") or ""); L["msg"] = ""
                elif ch in (ord("d"), ord("D")):
                    if L["lists"]:
                        L["confirm"] = True; L["msg"] = ""
                elif ch == ord(">"):                          # diese Liste in einen Knoten einordnen (Forest-weit)
                    if L["lists"] and len(L["lists"]) > 1:
                        L["place_kind"] = "list"
                        L["place_lid"] = L["lists"][L["sel"]]["id"]
                        L["place_iid"] = None
                        L["nsel"] = 0; L["msg"] = ""; L["view"] = "place"
                elif ch in (ord("s"), ord("S")):              # Kind direkt anhängen (Liste öffnen + Eingabe)
                    if L["lists"]:
                        L["def"] = L["lists"][L["sel"]]; L["isel"] = 0; L["path"] = []
                        L["view"] = "view"; L["adding"] = True; L["imode"] = "add"
                        L["addparent"] = None; L["edit_iid"] = None
                        L["input"] = ""; L["msg"] = ""
                elif ch in (ord("p"), ord("P")):              # als Projekt (rechts) an/aus
                    if L["lists"]:
                        cur = L["lists"][L["sel"]]
                        api_call("/api/lists/%s/project" % cur["id"], method="POST",
                                 body={"project": not cur.get("project")})
                        l_load()
            elif L["view"] == "new":
                if ch == 27:
                    L["view"] = "list"; L["lrename"] = None; L["msg"] = ""
                elif ch in (10, 13, curses.KEY_ENTER):
                    name = L["input"].strip()
                    if not name:
                        L["msg"] = "name fehlt"
                    elif L["lrename"] is not None:             # bestehende Liste umbenennen
                        try:
                            api_call("/api/lists/%s/rename" % L["lrename"], method="POST",
                                     body={"name": name})
                            L["view"] = "list"; L["lrename"] = None
                            L["msg"] = "umbenannt"; l_load()
                        except Exception:
                            L["msg"] = "umbenennen fehlgeschlagen"
                    else:
                        try:
                            l = api_call("/api/lists", method="POST", body={"name": name})
                            l_load()
                            for i, x in enumerate(L["lists"]):
                                if l and x["id"] == l.get("id"):
                                    L["sel"] = i
                            L["view"] = "list"; L["msg"] = "angelegt: " + name
                        except Exception:
                            L["msg"] = "anlegen fehlgeschlagen"
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    L["input"] = L["input"][:-1]
                elif 32 <= ch <= 126 and len(L["input"]) < 40:
                    L["input"] += chr(ch)
            elif L["view"] == "view":
                lid = L["def"]["id"] if L["def"] else None
                if L["adding"]:                               # Eintrag tippen (neu/sub/umbenennen)
                    if ch == 27:
                        L["adding"] = False; L["addparent"] = None
                        L["edit_iid"] = None; L["imode"] = "add"
                        L["input"] = ""; L["msg"] = ""
                    elif ch in (10, 13, curses.KEY_ENTER):
                        txt = L["input"].strip()
                        if txt and lid:
                            try:
                                if L["imode"] == "rename":    # bestehenden Eintrag umbenennen
                                    api_call("/api/lists/%s/items/%d/rename"
                                             % (lid, L["edit_iid"]), method="POST",
                                             body={"text": txt})
                                    new_id = L["edit_iid"]
                                else:                         # neuen Eintrag/Unterpunkt anhängen
                                    body = {"text": txt}
                                    if L["addparent"] is not None:
                                        body["parent"] = L["addparent"]
                                    new = api_call("/api/lists/%s/items" % lid, method="POST",
                                                   body=body)
                                    new_id = new.get("id") if new else None
                                # Umbenennen ist einmalig; neu/sub bleibt offen
                                # für Schnell-Eingabe mehrerer Einträge in Folge.
                                L["input"] = ""; L["edit_iid"] = None
                                close = (L["imode"] == "rename")
                                mode_add = (L["imode"] == "add")
                                if close:
                                    L["adding"] = False; L["imode"] = "add"
                                L["addparent"] = None
                                l_load(); l_sync_def()
                                # Cursor nur beim Anhängen auf der OFFENEN Ebene
                                # nachziehen; sub/rename lassen die Auswahl stehen.
                                if mode_add and new_id is not None:
                                    L["isel"] = l_index_in_container(new_id)
                            except Exception:
                                L["msg"] = "speichern fehlgeschlagen"
                    elif ch in (curses.KEY_BACKSPACE, 127, 8):
                        L["input"] = L["input"][:-1]
                    elif 32 <= ch <= 126 and len(L["input"]) < 80:
                        L["input"] += chr(ch)
                else:
                    items, pid, _cr = l_container()      # nur die offene Ebene
                    cur = items[L["isel"]] if 0 <= L["isel"] < len(items) else None
                    if ch in (27, ord("l"), ord("L")):         # Esc/l → Ebene zurück, sonst Übersicht
                        if L["path"]:
                            back = L["path"][-1]
                            L["path"] = L["path"][:-1]
                            L["isel"] = l_index_in_container(back)
                            L["msg"] = ""
                        else:
                            L["view"] = "list"; L["msg"] = ""; l_load()
                    elif ch in (ord("q"), ord("Q")):           # q → ganze TUI beenden
                        break
                    elif ch in (curses.KEY_UP, ord("k")):
                        L["isel"] = max(0, L["isel"] - 1)
                    elif ch in (curses.KEY_DOWN, ord("j")):
                        L["isel"] = min(max(0, len(items) - 1), L["isel"] + 1)
                    elif ch in (10, 13, curses.KEY_ENTER):     # Enter: Ordner rein, sonst abhaken
                        kids = cur.get("items") if cur else None
                        if cur and isinstance(kids, list) and kids:
                            L["path"] = L["path"] + [cur["id"]]; L["isel"] = 0; L["msg"] = ""
                        elif cur and lid:
                            try:
                                api_call("/api/lists/%s/items/%d/toggle" % (lid, cur["id"]),
                                         method="POST")
                                l_load(); l_sync_def()
                            except Exception:
                                L["msg"] = "umschalten fehlgeschlagen"
                    elif ch == ord(" "):                       # space: Blatt abhaken
                        kids = cur.get("items") if cur else None
                        if cur and isinstance(kids, list) and kids:
                            L["msg"] = "ordner hakt sich selbst ab"   # abgeleitet, nicht direkt
                        elif cur and lid:
                            try:
                                api_call("/api/lists/%s/items/%d/toggle" % (lid, cur["id"]),
                                         method="POST")
                                l_load(); l_sync_def()
                            except Exception:
                                L["msg"] = "umschalten fehlgeschlagen"
                    elif ch in (ord("a"), ord("A")):           # neuer Eintrag in DIESER Ebene
                        L["adding"] = True; L["imode"] = "add"
                        L["addparent"] = pid; L["edit_iid"] = None
                        L["input"] = ""; L["msg"] = ""
                    elif ch in (ord("s"), ord("S")):           # Unterpunkt zum gewählten Eintrag
                        if cur:
                            L["adding"] = True; L["imode"] = "sub"
                            L["addparent"] = cur["id"]; L["edit_iid"] = None
                            L["input"] = ""; L["msg"] = ""
                    elif ch in (ord("r"), ord("R")):           # gewählten Eintrag umbenennen
                        if cur:
                            L["adding"] = True; L["imode"] = "rename"
                            L["edit_iid"] = cur["id"]; L["addparent"] = None
                            L["input"] = str(cur.get("text") or ""); L["msg"] = ""
                    elif ch in (ord("m"), ord("M")):           # Eintrag raus in eine andere Liste
                        if cur and l_move_targets():
                            L["move_iid"] = cur["id"]; L["nsel"] = 0
                            L["msg"] = ""; L["view"] = "move"
                        elif cur:
                            L["msg"] = "keine andere liste"
                    elif ch == ord(">"):                       # diesen Punkt in einen Knoten einordnen (Forest-weit)
                        if cur and lid:
                            L["place_kind"] = "item"
                            L["place_lid"] = lid; L["place_iid"] = cur["id"]
                            L["nsel"] = 0; L["msg"] = ""; L["view"] = "place"
                    elif ch in (ord("p"), ord("P")):           # diesen Eintrag als Projekt an/aus
                        if cur and lid:
                            try:
                                api_call("/api/lists/%s/items/%d/project" % (lid, cur["id"]),
                                         method="POST", body={"project": not cur.get("project")})
                                l_load(); l_sync_def()
                            except Exception:
                                L["msg"] = "projekt fehlgeschlagen"
                    elif ch in (ord("d"), ord("D")):
                        if cur and lid:
                            try:
                                api_call("/api/lists/%s/items/%d" % (lid, cur["id"]),
                                         method="DELETE")
                                l_load(); l_sync_def()
                            except Exception:
                                L["msg"] = "löschen fehlgeschlagen"
            elif L["view"] == "place":         # Knoten (Liste/Eintrag) Forest-weit einordnen
                tg = l_forest_targets(L["place_kind"], L["place_lid"], L["place_iid"])
                back = "view" if L["place_kind"] == "item" else "list"
                if ch in (27, ord("l"), ord("L")):             # Esc/l → abbrechen
                    L["view"] = back; L["place_iid"] = None; L["msg"] = ""
                elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
                    break
                elif ch in (curses.KEY_UP, ord("k")):
                    L["nsel"] = max(0, L["nsel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    L["nsel"] = min(max(0, len(tg) - 1), L["nsel"] + 1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    if tg and 0 <= L["nsel"] < len(tg):
                        t = tg[L["nsel"]]
                        try:
                            if L["place_kind"] == "list":
                                api_call("/api/lists/%s/nest" % L["place_lid"], method="POST",
                                         body={"into": t["lid"], "parent": t["iid"]})
                            else:
                                api_call("/api/lists/%s/items/%d/move" % (L["place_lid"], L["place_iid"]),
                                         method="POST", body={"into": t["lid"], "parent": t["iid"]})
                            L["msg"] = "eingeordnet"
                        except Exception:
                            L["msg"] = "einordnen fehlgeschlagen"
                        L["view"] = back; L["place_iid"] = None
                        l_load()
                        if back == "view":
                            l_sync_def()
            elif L["view"] == "move":          # Eintrag raus in eine andere Liste
                lid = L["def"]["id"] if L["def"] else None
                targets = l_move_targets()
                nopts = 1 + len(targets)       # 0 = neue Liste, dann die Ziele
                if ch in (27, ord("l"), ord("L")):             # Esc/l → zurück zu den Einträgen
                    L["view"] = "view"; L["move_iid"] = None; L["msg"] = ""
                elif ch in (ord("q"), ord("Q")):
                    break
                elif ch in (curses.KEY_UP, ord("k")):
                    L["nsel"] = max(0, L["nsel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    L["nsel"] = min(max(0, nopts - 1), L["nsel"] + 1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    if L["nsel"] == 0:                         # → in eine NEUE Liste (Name tippen)
                        it = l_find_item(L["def"].get("items"), L["move_iid"]) if L["def"] else None
                        L["input"] = str(it.get("text") or "") if it else ""
                        L["view"] = "move_new"; L["msg"] = ""
                    elif 1 <= L["nsel"] < nopts and lid:
                        dest = targets[L["nsel"] - 1]
                        try:
                            api_call("/api/lists/%s/items/%d/move" % (lid, L["move_iid"]),
                                     method="POST", body={"into": dest["id"]})
                            L["msg"] = "verschoben"
                        except Exception:
                            L["msg"] = "verschieben fehlgeschlagen"
                        L["view"] = "view"; L["move_iid"] = None
                        l_load(); l_sync_def()
            elif L["view"] == "move_new":       # Name für die neue Ziel-Liste tippen
                lid = L["def"]["id"] if L["def"] else None
                if ch == 27:
                    L["view"] = "move"; L["input"] = ""; L["msg"] = ""
                elif ch in (10, 13, curses.KEY_ENTER):
                    name = L["input"].strip()
                    if not name:
                        L["msg"] = "name fehlt"
                    elif lid:
                        try:
                            new = api_call("/api/lists", method="POST", body={"name": name})
                            api_call("/api/lists/%s/items/%d/move" % (lid, L["move_iid"]),
                                     method="POST", body={"into": new["id"]})
                            L["msg"] = "verschoben → " + name
                            L["view"] = "view"; L["move_iid"] = None; L["input"] = ""
                            l_load(); l_sync_def()
                        except Exception:
                            L["msg"] = "verschieben fehlgeschlagen"
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    L["input"] = L["input"][:-1]
                elif 32 <= ch <= 126 and len(L["input"]) < 40:
                    L["input"] += chr(ch)
        elif M["active"]:                      # Karte hat den Fokus
            ca = m_alt_arrow(ch)              # Alt+Pfeil? (frisst evtl. Folgebytes)
            if ca in ("up", "down", "left", "right"):
                m_focus_step(*{"up": (0, -1), "down": (0, 1),
                               "left": (-1, 0), "right": (1, 0)}[ca])
            elif ca == "esc" or ch in (ord("m"), ord("M")):    # Esc/m → Karte zu
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
                M["odata"] = M["fdata"] = None
            elif ch in (ord("o"), ord("O")):   # Chokepoints-Overlay ein/aus
                M["overlay"] = not M["overlay"]
                M["odata"] = None              # beim Einschalten frisch holen
            elif ch in (ord("w"), ord("W"), 10, 13, curses.KEY_ENTER):
                m_window()                     # natives Fenster aufklappen
            elif ch in (ord("t"), ord("T")):   # Theme darf auch hier zyklieren
                theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
        elif K["active"]:                      # Kalender hat den Fokus
            if K["mode"] == "add":             # gestaffeltes Eingabe-Formular
                cur_key = ("aday", "atime", "alabel")[K["astage"]]
                is_rt = (K["atype"] == "routine")
                if ch == 9 and not K["editing"]:   # Tab → Termin/Routine umschalten
                    K["atype"] = "entry" if is_rt else "routine"
                    K["aday"] = ""; K["astage"] = 0; K["amsg"] = ""
                elif ch == 27:                 # Esc: Stufe zurück bzw. Formular verlassen
                    if K["astage"] > 0:
                        K["astage"] -= 1; K["amsg"] = ""
                    else:
                        K["mode"] = "view"; K["amsg"] = ""; K["editing"] = None
                elif ch in (10, 13, curses.KEY_ENTER):
                    if K["astage"] == 0:
                        bad = (k_parse_byday(K["aday"]) is None) if is_rt else (k_parse_day(K["aday"]) is None)
                        if bad:
                            K["amsg"] = "wochentag? Mo/Di/.." if is_rt else "datum? TT.MM"
                        else:
                            K["astage"] = 1; K["amsg"] = ""
                    elif K["astage"] == 1:
                        if K["atime"].strip() and parse_clock(K["atime"]) is None:
                            K["amsg"] = "zeit? HH:MM (leer=ganztags)"
                        else:
                            K["astage"] = 2; K["amsg"] = ""
                    else:
                        k_add_save()
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    K[cur_key] = K[cur_key][:-1]
                elif 32 <= ch <= 126:
                    cc = chr(ch)
                    if K["astage"] == 0:
                        if is_rt and (cc.isalpha() or cc in ", ") and len(K["aday"]) < 24:
                            K["aday"] += cc            # Wochentag(e): Mo,Mi,Fr
                        elif (not is_rt) and (cc.isdigit() or cc in "./-") and len(K["aday"]) < 10:
                            K["aday"] += cc            # Datum: TT.MM
                    elif K["astage"] == 1 and (cc.isdigit() or cc == ":") and len(K["atime"]) < 5:
                        K["atime"] += cc
                    elif K["astage"] == 2 and len(K["alabel"]) < 60:
                        K["alabel"] += cc
            elif K["mode"] == "routine":       # Routine-Vorkommen de-/aktivieren / Routine löschen
                it = K["ract"] or {}
                if K["rconfirm"]:              # „ganze Routine löschen?" offen
                    if ch in (ord("j"), ord("J"), ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
                        k_routine_delete()
                    elif ch != -1:
                        K["rconfirm"] = False
                elif ch == 27:                 # Esc → zurück ohne Änderung
                    K["mode"] = "view"; K["ract"] = None
                elif ch in (ord("x"), ord("X")):   # x → ganze Routine löschen (mit Nachfrage)
                    K["rconfirm"] = True
                elif it.get("deaktiviert") and ch in (ord("a"), ord("A"),
                                                      10, 13, curses.KEY_ENTER):
                    k_routine_toggle(False)    # wieder aktivieren
                elif (not it.get("deaktiviert")) and ch in (ord("d"), ord("D"),
                                                            10, 13, curses.KEY_ENTER):
                    k_routine_toggle(True)     # diesen Termin deaktivieren
            elif K["confirmdel"]:              # Lösch-Nachfrage (Einmal-Termin) offen
                if ch in (ord("j"), ord("J"), ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
                    sels = k_selectable()
                    if sels and 0 <= K["sel"] < len(sels) and not sels[K["sel"]]["recurring"]:
                        it = sels[K["sel"]]
                        k_delete_sel((it["iso"], it["label"], it["layer"]))
                    K["confirmdel"] = False
                elif ch != -1:                 # alles andere bricht ab
                    K["confirmdel"] = False; K["msg"] = ""
            else:                              # View-Modus: blättern/auswählen
                if ch in (27, ord("c"), ord("C")):             # Esc/c → Kalender zu
                    K["active"] = False
                elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
                    break
                elif ch in (curses.KEY_LEFT, ord("h")):
                    k_step(-1); K["sel"] = 0; K["msg"] = ""
                elif ch in (curses.KEY_RIGHT, ord("l")):
                    k_step(1); K["sel"] = 0; K["msg"] = ""
                elif ch in (curses.KEY_UP, ord("k")):
                    K["sel"] = max(0, K["sel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    K["sel"] = K["sel"] + 1    # Klemmung passiert beim Zeichnen
                elif ch in (ord("v"), ord("V"), 9):            # v/Tab → Woche↔Monat
                    k_toggle(); K["sel"] = 0; K["msg"] = ""
                elif ch == ord("0"):                           # 0 → zurück zu heute
                    k_today(); K["sel"] = 0; K["msg"] = ""
                elif ch in (ord("a"), ord("A")):               # a → neuer Termin (Tab: Routine)
                    K["mode"] = "add"; K["astage"] = 0; K["amsg"] = ""; K["msg"] = ""
                    K["editing"] = None; K["atype"] = "entry"
                    K["aday"] = date.fromisoformat(K["ref"]).strftime("%d.%m")
                    K["atime"] = ""; K["alabel"] = ""
                elif ch in (ord("e"), ord("E"), 10, 13, curses.KEY_ENTER):   # bearbeiten
                    if K["view"] == "week":
                        k_begin_edit()
                elif ch in (ord("d"), ord("D")):               # d → löschen / Routine-Screen
                    if K["view"] == "week":
                        sels = k_selectable()
                        if sels and 0 <= K["sel"] < len(sels):
                            if sels[K["sel"]]["recurring"]:
                                K["mode"] = "routine"; K["ract"] = sels[K["sel"]]; K["msg"] = ""
                            else:
                                K["confirmdel"] = True; K["msg"] = ""
                elif ch in (ord("t"), ord("T")):               # Theme darf auch hier zyklieren
                    theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
        elif MAIL["active"] and MAIL["replying"]:   # Antwort-Editor hat den Fokus
            if MAIL["reply_confirm"]:                          # Verlassen-Leiste
                if ch in (ord("j"), ord("J"), ord("y"), ord("Y")):
                    mail_reply_send()
                elif ch in (ord("n"), ord("N")):
                    MAIL["replying"] = False; MAIL["reply_confirm"] = False
                    MAIL["msg"] = "verworfen"
                elif ch in (ord("w"), ord("W"), 27):
                    MAIL["reply_confirm"] = False
            else:
                if ch == 27:                                   # Esc → fertig/senden-Leiste
                    MAIL["reply_confirm"] = True
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    MAIL["reply_text"] = MAIL["reply_text"][:-1]
                elif ch in (10, 13, curses.KEY_ENTER):
                    MAIL["reply_text"] += "\n"
                elif ch == curses.KEY_UP:                       # Original (links) scrollen
                    MAIL["reply_origoff"] = max(0, MAIL["reply_origoff"] - 1)
                elif ch == curses.KEY_DOWN:
                    MAIL["reply_origoff"] = MAIL["reply_origoff"] + 1
                elif 32 <= ch <= 126:
                    MAIL["reply_text"] += chr(ch)
                elif ch >= 128:                                # UTF-8 best effort (Umlaute)
                    buf = MAIL.get("_u8", b"") + bytes([ch & 0xFF])
                    try:
                        MAIL["reply_text"] += buf.decode("utf-8")
                        MAIL["_u8"] = b""
                    except UnicodeDecodeError:
                        MAIL["_u8"] = buf if len(buf) < 4 else b""
        elif MAIL["active"]:                   # Post/Mail-Panel hat den Fokus
            if MAIL["level"] == "mails":                       # Ebene 2: Mails einer Kat.
                if MAIL["picking"]:                            # Einsortier-Picker offen
                    pcats = [str(c.get("name", "?")) for c in
                             ((MAIL["data"] or {}).get("categories") or [])]
                    if ch == 27:
                        MAIL["picking"] = False; MAIL["msg"] = ""
                    elif ch in (curses.KEY_UP, ord("k")):
                        MAIL["picksel"] = max(0, MAIL["picksel"] - 1)
                    elif ch in (curses.KEY_DOWN, ord("j")):
                        MAIL["picksel"] = MAIL["picksel"] + 1
                    elif ch in (10, 13, curses.KEY_ENTER):
                        if 0 <= MAIL["picksel"] < len(pcats):
                            mail_assign(pcats[MAIL["picksel"]])
                elif MAIL["confirmdel"]:                       # Lösch-Nachfrage offen
                    if ch in (ord("j"), ord("J"), ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
                        mail_delete()
                    elif ch != -1:
                        MAIL["confirmdel"] = False; MAIL["msg"] = ""
                elif ch in (27, curses.KEY_LEFT, ord("h")):    # Esc/← → zurück zu Kategorien
                    MAIL["level"] = "cats"; MAIL["msg"] = ""
                elif ch in (ord("p"), ord("P")):               # p → Panel ganz zu
                    MAIL["active"] = False
                elif ch in (ord("q"), ord("Q")):
                    break
                elif ch in (ord("v"), ord("V"), 9):            # v/Tab → lesen↔liste
                    MAIL["mode2"] = "list" if MAIL["mode2"] == "read" else "read"
                    MAIL["expanded"] = False; MAIL["bodyoff"] = 0; MAIL["msg"] = ""
                elif ch in (curses.KEY_UP, curses.KEY_DOWN, ord("k"), ord("j"),
                            ord("n"), ord("N"), ord(" ")):
                    # Pfeil/j/k/n/N = BLÄTTERN (immer, egal ob ausgeklappt). Eine
                    # gepufferte Tastenfolge zusammenfassen, damit schnelles
                    # Blättern nicht pro Taste den Body blockierend nachlädt.
                    _DN = (curses.KEY_DOWN, ord("j"), ord("n"), ord(" "))
                    _UP = (curses.KEY_UP, ord("k"), ord("N"))
                    delta = 1 if ch in _DN else -1
                    stdscr.nodelay(True)
                    while True:
                        nx = stdscr.getch()
                        if nx in _DN:
                            delta += 1
                        elif nx in _UP:
                            delta -= 1
                        else:
                            if nx != -1:
                                curses.ungetch(nx)
                            break
                    stdscr.timeout(250)
                    MAIL["msel"] = max(0, MAIL["msel"] + delta)  # Obergrenze beim Zeichnen
                    MAIL["bodyoff"] = 0; MAIL["msg"] = ""
                elif ch == curses.KEY_NPAGE:                   # Bild↓ → Body runter
                    MAIL["bodyoff"] = MAIL["bodyoff"] + 5
                elif ch == curses.KEY_PPAGE:                   # Bild↑ → Body hoch
                    MAIL["bodyoff"] = max(0, MAIL["bodyoff"] - 5)
                elif ch in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT, ord("l")):
                    MAIL["mode2"] = "read"               # aus Liste: lesen
                elif ch in (ord("e"), ord("E")):               # ausklappen ↔ Vorschau
                    MAIL["expanded"] = not MAIL["expanded"]; MAIL["bodyoff"] = 0
                elif ch in (ord("s"), ord("S")):               # einsortieren (Absender)
                    MAIL["picking"] = True; MAIL["picksel"] = 0; MAIL["msg"] = ""
                elif ch in (ord("d"), ord("D")):               # löschen (Papierkorb)
                    MAIL["confirmdel"] = True; MAIL["msg"] = ""
                elif ch in (ord("a"), ord("A")):               # antworten (Split-Editor)
                    mail_reply_open()
                elif ch in (ord("r"), ord("R")):
                    mail_poll(); MAIL["data"] = None
                elif ch in (ord("t"), ord("T")):
                    theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
            else:                                              # Ebene 1: Kategorien wählen
                if ch in (27, ord("p"), ord("P")):             # Esc/p → Panel zu
                    MAIL["active"] = False
                elif ch in (ord("q"), ord("Q")):
                    break
                elif ch in (curses.KEY_UP, ord("k")):
                    MAIL["sel"] = max(0, MAIL["sel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    MAIL["sel"] = MAIL["sel"] + 1   # Klemmung beim Zeichnen
                elif ch in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT, ord("l")):
                    d = MAIL["data"] or {}                      # gewählte Kategorie öffnen
                    cl = d.get("categories") if isinstance(d.get("categories"), list) else []
                    if 0 <= MAIL["sel"] < len(cl):
                        mail_open_category(cl[MAIL["sel"]].get("name"))
                elif ch in (ord("r"), ord("R")):               # r → Live-Poll anstoßen
                    mail_poll(); MAIL["data"] = None
                elif ch in (ord("t"), ord("T")):
                    theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
        else:                                  # Normal-Modus: Shortcuts aktiv
            if ch in (ord("q"), ord("Q")):
                break
            elif ch in (ord("t"), ord("T")):   # Theme zyklieren
                theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
            elif ch in (ord("g"), ord("G")):   # Graph-Werkzeug öffnen
                G["active"] = True; G["view"] = "list"; G["msg"] = ""; g_load()
            elif ch in (ord("l"), ord("L")):   # Listen-Werkzeug öffnen
                L["active"] = True; L["view"] = "list"; L["msg"] = ""; l_load()
            elif ch in (ord("m"), ord("M")):   # Karte öffnen
                M["active"] = True; M["data"] = None
            elif ch in (ord("c"), ord("C")):   # Kalender öffnen
                K["active"] = True; K["data"] = None
                K["mode"] = "view"; K["sel"] = 0; K["confirmdel"] = False; K["msg"] = ""
                K["editing"] = None; K["ract"] = None; K["rconfirm"] = False; K["atype"] = "entry"
            elif ch in (ord("p"), ord("P")):   # Post/Mail-Panel öffnen (Ebene Kategorien)
                MAIL["active"] = True; MAIL["level"] = "cats"
                MAIL["sel"] = 0; MAIL["cat"] = None; MAIL["off"] = 0
                MAIL["mails"] = None; MAIL["data"] = None; MAIL["msg"] = ""
                mail_refresh_counts()          # echte Ordnergrößen im Hintergrund holen
            # '/' wird global oben abgefangen (greift in JEDEM Fenster), darum
            # hier kein eigener Zweig mehr.
        # KEY_RESIZE oder Timeout → einfach neu zeichnen

        # Theme nachziehen (auto wechselt nach Uhrzeit, oder nach 't'/Befehl)
        want = resolved_theme()
        if want != cur_theme:
            cur_theme = want
            apply_theme(cur_theme)

        # Weiche Kamerafahrt zum fokussierten Land (eine Ease-Stufe pro Frame).
        if M["active"] and M.get("anim"):
            m_anim_step()

        state, metrics, connected = store.snapshot()
        gs_cache, gv_cache = store.graphs_snapshot()
        proj_cache = store.projects_snapshot()
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
        # Im Antwort-Editor wird die MITTE breit gemacht (zwei quadratische
        # Kästen brauchen Platz) — die Seiten schrumpfen auf ein Minimum, bis
        # der Editor wieder zu ist.
        if MAIL["active"] and MAIL["replying"]:
            leftw = max(16, int(W * 0.16))
            rightw = max(16, int(W * 0.16))
        else:
            leftw = max(24, int(W * 0.28))
            rightw = max(20, int(W * 0.22))
        midw = W - leftw - rightw
        lx, mx, rx = 0, leftw, leftw + midw

        # ── LINKS: telemetrie / stdout ─────────────────────────────────
        # (Sensoren-Panel entfernt 2026-06: kein echter Sensor angeschlossen.
        #  /api/state.sensors wird weiter gepollt, nur nicht mehr gezeichnet —
        #  Box zum Wiederanzeigen aus der git-History zurückholen.)
        # EXTERNAL: erreichbare AI-Backends (local/cloud) – wie im Browser oben
        # links. Front-agnostisch dieselbe Quelle (/api/ai/backends). Titel grün
        # wenn irgendein Backend da ist, sonst Warn-Farbe.
        bk = store.backends_snapshot()
        ext_h = 4
        draw_box(top, lx, ext_h, leftw, "external",
                 C["acc"] if bk.get("any") else C["warn"])
        safe_addstr(top + 1, lx + 2, "LOKAL", C["acc"])
        safe_addstr(top + 1, lx + 9,
                    "✓ ollama" if bk.get("local") else "✗",
                    C["bright"] if bk.get("local") else C["faint"])
        safe_addstr(top + 2, lx + 2, "CLOUD", C["acc"])
        safe_addstr(top + 2, lx + 9,
                    ("✓ " + (bk.get("cloud_provider") or "")) if bk.get("cloud") else "✗",
                    C["bright"] if bk.get("cloud") else C["faint"])

        tele_h = len(TELE_ROWS) + 2
        ty = top + ext_h
        std_h = body_h - ext_h - tele_h
        draw_box(ty, lx, tele_h, leftw, "telemetrie")
        hlbl = host_label(metrics)   # Host des Backends (PC/LAP/PI), nicht hart
        for i, (lbl, key, _u) in enumerate(TELE_ROWS):
            tv = tele_value(metrics, key)
            safe_addstr(ty + 1 + i, lx + 2, hlbl + "·" + lbl, C["acc"])
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
        elif L["active"]:
            draw_box(top, mx, body_h, midw, "listen")
            draw_list_tool(top, mx, body_h, midw)
        elif M["active"]:
            draw_box(top, mx, body_h, midw, "karte · welt")
            draw_map(top, mx, body_h, midw)
        elif K["active"]:
            draw_box(top, mx, body_h, midw, "kalender")
            draw_calendar(top, mx, body_h, midw)
        elif MAIL["active"] and MAIL["replying"]:
            draw_reply(top, mx, body_h, midw)
        elif MAIL["active"]:
            draw_box(top, mx, body_h, midw, "post · mail")
            draw_mail(top, mx, body_h, midw)
        else:
            draw_box(top, mx, body_h, midw, "mitte")
            cyc = top + body_h // 2
            big = "KASSETTE · TUI"
            l1 = "g · graph-werkzeug"
            l2 = "l · listen"
            l3 = "m · karte"
            l4 = "c · kalender"
            l5 = "p · post/mail"
            addclip(cyc - 3, mx + max(1, (midw - len(big)) // 2), big, midw - 2, C["bright"])
            addclip(cyc - 1, mx + max(1, (midw - len(l1)) // 2), l1, midw - 2, C["acc"])
            addclip(cyc, mx + max(1, (midw - len(l2)) // 2), l2, midw - 2, C["acc"])
            addclip(cyc + 1, mx + max(1, (midw - len(l3)) // 2), l3, midw - 2, C["acc"])
            addclip(cyc + 2, mx + max(1, (midw - len(l4)) // 2), l4, midw - 2, C["acc"])
            addclip(cyc + 3, mx + max(1, (midw - len(l5)) // 2), l5, midw - 2, C["acc"])

        # ── RECHTS: lifestyle / outbound ──────────────────────────────────
        # lifestyle = ÜBERLAGERUNG aller Graphen in EINEM Gitter. X = Datum
        # (Zeitstrahl), Y bewusst MEHRDEUTIG — jeder Graph nutzt seine eigene
        # Achse + Darstellung, alles übereinandergelegt zum Vergleich:
        #   period → zusammenhängende Bande (Zellen-Hintergrund) über die Spanne
        #   time   → Stern ★ auf der 24h-Skala (Zeitpunkt, keine Linie)
        #   scale  → wachsende Kreise ◦○◉●⬤ auf eigener Zeile (Größe = 1–5)
        #   number → Punkt auf der eigenen min/max-Spanne (sichtbare Werte)
        # Eigener Marker + Farbe je Graph (+ Legende). Quelle:
        # store.graphs_snapshot (langsames Hintergrund-Polling).
        if gs_cache:
            # bewusst kompakt: höchstens ~11 Zeilen, Rest geht an outbound.
            life_h = max(7, min(11, body_h - 4))
        else:
            life_h = 4
        out_h = body_h - life_h
        # PROJECTS schiebt sich zwischen lifestyle und outbound — aber nur wenn
        # es überhaupt geflaggte Projekte gibt UND outbound danach mind. 5 Zeilen
        # behält (sonst lieber ganz weglassen, Tripwire hat Vorrang). Höhe ist
        # VARIABEL (verschachtelt): ein Knoten ohne Unterprojekte braucht 2 Zeilen
        # (Titel+Leiste), einer MIT Unterprojekten einen Rahmen (oben+unten) um
        # seine rekursiv gemessenen Kinder.
        def proj_measure(node, w):
            kids = node.get("children") or []
            if not kids:
                return 2
            return 2 + sum(proj_measure(c, w - 2) for c in kids)
        proj_h = 0
        if proj_cache and out_h >= 9:
            need = 2 + sum(proj_measure(p, rightw - 4) for p in proj_cache
                           if isinstance(p, dict))
            proj_h = min(need, out_h - 5)
        out_h -= proj_h
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
                                   "dv": dv, "col": LIFE_COL[i % len(LIFE_COL)],
                                   "predict": bool(g.get("predict"))})
            # Legende packen (mehrere pro Zeile): farbiges Linien-Sample + Name —
            # verbraucht Zeilen, die dem Plot fehlen.
            leg_lines, cur_w = [[]], 0
            for s in series:
                nm = s["name"][:8]
                tok = "─ " + nm
                if cur_w + len(tok) + 1 > plot_w and leg_lines[-1]:
                    leg_lines.append([]); cur_w = 0
                leg_lines[-1].append((nm, s["col"], s["type"]))
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
                # Wie in der Schlaf-Ansicht: links 3 Spalten für die Stunden-
                # Labels, dann GENAU 1 Spalte pro Tag (dünn + gleichmäßig — kein
                # dicker Block, kein schmaler erster Balken durch Rundung).
                # Heute rechts, ältester Tag links.
                ix = plot_x                           # Stunden-Labels
                day_x0 = ix + 3                       # erste Tages-Spalte
                day_w = max(1, (rx + rightw - 2) - day_x0)
                NDAYS = day_w
                today = date.today()
                window = [(today - timedelta(days=k)).isoformat()
                          for k in range(NDAYS - 1, -1, -1)]   # alt → neu
                day_col = {d: day_x0 + i for i, d in enumerate(window)}
                day_center = day_col                  # 1 Spalte → Mitte = die Spalte
                cols = window

                # 24h-Achse links: senkrechte Linie + Stunden-Marken.
                for r in range(plot_h):
                    safe_addstr(base + r, day_x0 - 1, "│", C["faint"])
                for hh in (0, 6, 12, 18, 24):
                    safe_addstr(row_clock(hh * 60), ix, "%02d" % (hh % 24), C["faint"])

                # PREDICTION: Lücken-Tage (kein echter Eintrag) werden aus dem
                # Schnitt der letzten NPRED echten Werte geschätzt — aber NUR ab
                # dem ersten echten Eintrag (nichts vor Tracking-Beginn erfinden).
                # Geschätzte Tage werden später blass/schraffiert markiert.
                NPRED = 7

                def predicted_days(s):
                    """{datum: schätz-entry mit _pred=True} für Fenster-Lücken —
                    aber NUR wenn der Graph das predict-Flag trägt (sonst {}).
                    So wird z.B. nur Schlaf ergänzt, nicht jeder Graph."""
                    if not s.get("predict"):
                        return {}
                    dv = s.get("dv") or {}
                    actual = sorted((e for e in dv.values() if isinstance(e, dict)),
                                    key=lambda e: str(e.get("date", "")))
                    if not actual:
                        return {}
                    earliest = str(actual[0].get("date", ""))
                    last = actual[-NPRED:]

                    def mean(key):
                        xs = [_num(e.get(key)) for e in last]
                        xs = [x for x in xs if x is not None]
                        return sum(xs) / len(xs) if xs else None

                    mv, me = mean("value"), mean("end")
                    out = {}
                    for d in window:
                        if d in dv or d < earliest or mv is None:
                            continue
                        e = {"date": d, "value": mv, "_pred": True}
                        if me is not None:
                            e["end"] = me
                        out[d] = e
                    return out

                # 1. DURCHGANG: period/Schlaf als zusammenhängende Bande HINTER
                # allem. Gefärbter Zellen-HINTERGRUND (band), 1 Spalte pro Tag;
                # Nachbartage stoßen aneinander → ein Band. band_cells merkt sich
                # die Zellen, damit Kurven dort mit band-bg gezeichnet werden
                # (= vor dem Band, kein Loch).
                band_glyph = " " if C.get("band_is_bg") else "▒"
                band_cells = set()
                for s in series:
                    if s["type"] != "period":
                        continue
                    for d, e in list(s["dv"].items()) + list(predicted_days(s).items()):
                        cx = day_col.get(d)
                        v, end = _num(e.get("value")), _num(e.get("end"))
                        if cx is None or v is None or end is None:
                            continue
                        st, en = int(round(v)), int(round(end))
                        segs = ([(st, en)] if en >= st
                                else [(st, 1440), (0, en)])   # Wrap Mitternacht
                        g = "░" if e.get("_pred") else band_glyph   # geschätzt = schraffiert
                        for a, b in segs:
                            r0, r1 = sorted((row_clock(a), row_clock(b)))
                            for r in range(r0, r1 + 1):
                                safe_addstr(r, cx, g, C["band"])
                                band_cells.add((r, cx))

                # Attribut für einen Linien-Glyph: in Banden-Zellen die "@band"-
                # Variante (band-bg) → Glyph liegt VOR der Bande; sonst normal.
                def latt(r, c, col):
                    if (r, c) in band_cells and (col + "@band") in C:
                        return C[col + "@band"]
                    return C[col]

                # 2. DURCHGANG: scale (1–5) als wachsende Kreise ◦○◉●⬤ auf je
                # EIGENER Zeile (von oben gestapelt). Größe kodiert den Wert,
                # Farbe trennt die Graphen — keine Verbindungslinie. Mehrere
                # Wertungsgraphen belegen so praktischerweise eigene Zeilen.
                CIRC = "◦○◉●⬤"
                srow = 0
                for s in series:
                    if s["type"] != "scale":
                        continue
                    ry = base + plot_h - 1 - srow      # Zeilen von UNTEN auffüllen
                    srow += 1
                    if ry < base:
                        continue                      # kein Platz mehr → weglassen
                    col = s["col"]
                    for d, e in list(s["dv"].items()) + list(predicted_days(s).items()):
                        cx = day_center.get(d)
                        v = _num(e.get("value"))
                        if cx is None or v is None:
                            continue
                        idx = max(0, min(4, int(round(v)) - 1))
                        attr = latt(ry, cx, "faint") if e.get("_pred") else latt(ry, cx, col)
                        safe_addstr(ry, cx, CIRC[idx], attr)

                # 3. DURCHGANG: time als einzelne Sterne ★ (Zeitpunkt, keine
                # Linie), je Tag an der Block-Mitte auf der 24h-Skala.
                for s in series:
                    if s["type"] != "time":
                        continue
                    col = s["col"]
                    for d, e in list(s["dv"].items()) + list(predicted_days(s).items()):
                        cx = day_center.get(d)
                        v = _num(e.get("value"))
                        if cx is None or v is None:
                            continue
                        r = row_clock(int(round(v)))
                        attr = latt(r, cx, "faint") if e.get("_pred") else latt(r, cx, col)
                        safe_addstr(r, cx, "★", attr)

                # 4. DURCHGANG: number als dünne Linie (eigene min/max-Spanne).
                for s in series:
                    if s["type"] != "number":
                        continue
                    col, dv = s["col"], s["dv"]
                    vis = [_num(dv[d].get("value")) for d in cols if d in dv]
                    vis = [x for x in vis if x is not None]
                    lo, hi = (min(vis), max(vis)) if vis else (None, None)
                    pts = []                          # (cx, row) für die Linie
                    for d, e in dv.items():
                        cx = day_center.get(d)
                        v = _num(e.get("value"))
                        if cx is None or v is None:
                            continue
                        pts.append((cx, row_norm(v, lo, hi)))
                    # Einzelpunkte zu einer dünnen Linie verbinden (Steigung →
                    # ╱ steigt, ╲ fällt, ─ flach; senkrecht → │). Einzelner Punkt → ·
                    pts.sort()
                    if len(pts) == 1:
                        safe_addstr(pts[0][1], pts[0][0], "·", latt(pts[0][1], pts[0][0], col))
                    else:
                        for (c1, r1), (c2, r2) in zip(pts, pts[1:]):
                            if c2 == c1:
                                for r in range(min(r1, r2), max(r1, r2) + 1):
                                    safe_addstr(r, c1, "│", latt(r, c1, col))
                                continue
                            ch = "─" if r2 == r1 else ("╲" if r2 > r1 else "╱")
                            for c in range(c1, c2 + 1):
                                t = (c - c1) / (c2 - c1)
                                r = int(round(r1 + t * (r2 - r1)))
                                safe_addstr(r, c, ch, latt(r, c, col))
                    # geschätzte Tage als blasse Einzelpunkte (nicht in die Linie)
                    for d, e in predicted_days(s).items():
                        cx = day_center.get(d)
                        v = _num(e.get("value"))
                        if cx is None or v is None:
                            continue
                        r = row_norm(v, lo, hi)
                        safe_addstr(r, cx, "·", latt(r, cx, "faint"))
                # Legende unter den Plot: farbiges Linien-Sample + Name
                for li, line in enumerate(leg_lines[:max_leg]):
                    yy = base + plot_h + li
                    cx = plot_x
                    for nm, col, typ in line:
                        if typ == "period":          # Bande statt Linie zeigen
                            safe_addstr(yy, cx, band_glyph, C["band"])
                        elif typ == "scale":         # Kreis-Sample statt Linie
                            safe_addstr(yy, cx, "●", C[col])
                        elif typ == "time":          # Stern-Sample statt Linie
                            safe_addstr(yy, cx, "★", C[col])
                        else:
                            safe_addstr(yy, cx, "─", C[col])
                        addclip(yy, cx + 2, nm, plot_w - (cx - plot_x) - 2, C["dim"])
                        cx += 2 + len(nm) + 1
            else:
                safe_addstr(top + 1, rx + 2, "// noch keine werte", C["faint"])
        else:
            safe_addstr(top + 1, rx + 2, "// noch keine graphen (g)", C["faint"])

        # ── PROJECTS (zwischen lifestyle und outbound) ────────────────────
        # VERSCHACHTELT (Quelle: store.projects_snapshot ← /api/projects, Baum).
        # Knoten OHNE Unterprojekte: Titel + Erfüllungsleiste (2 Zeilen). Knoten
        # MIT Unterprojekten: dünner Rahmen (Titel im oberen Rand) um die rekursiv
        # gezeichneten Kinder, KEINE eigene Leiste. Reine Anzeige; markiert wird im
        # Listen-Werkzeug ('p' auf Liste bzw. Eintrag). Bei Platzmangel wird
        # einfach ab dem Punkt aufgehört (kein Überlauf, kein Crash).
        if proj_h:
            draw_box(top + life_h, rx, proj_h, rightw, "projects")
            y_max = top + life_h + proj_h - 2          # letzte innere Zeile
            x0, w0 = rx + 2, max(4, rightw - 4)

            def proj_draw(node, x, y, w, y_max):
                if y > y_max or w < 4:
                    return y_max + 1
                name = str(node.get("name") or "")
                kids = node.get("children") or []
                if not kids:                            # Blatt-Projekt: Titel + Leiste
                    done = int(node.get("done") or 0)
                    total = int(node.get("total") or 0)
                    cnt = "%d/%d" % (done, total)
                    nmw = max(1, w - len(cnt) - 1)
                    addclip(y, x, name[:nmw], nmw, C["bright"])
                    safe_addstr(y, x + w - len(cnt), cnt, C["dim"])
                    if y + 1 <= y_max:
                        frac = (done / total) if total else 0.0
                        full = int(round(max(0.0, min(1.0, frac)) * w))
                        bar = "█" * full + "░" * (w - full)
                        bcol = C["acc"] if (total and done >= total) else C["graph"]
                        safe_addstr(y + 1, x, bar, bcol)
                    return y + 2
                # gerahmter Kasten: Titel im oberen Rand, Kinder rekursiv drin
                inner = w - 2
                label = (" " + name + " ")[:inner]
                safe_addstr(y, x, "┌" + label + "─" * (inner - len(label)) + "┐", C["faint"])
                safe_addstr(y, x + 1, label, C["bright"])    # Titel hervorheben
                cy = y + 1
                for c in kids:
                    if cy > y_max:
                        break
                    cy = proj_draw(c, x + 1, cy, w - 2, y_max)
                for ry in range(y + 1, min(cy, y_max + 1)):  # senkrechte Ränder
                    safe_addstr(ry, x, "│", C["faint"])
                    safe_addstr(ry, x + w - 1, "│", C["faint"])
                if cy <= y_max:                              # unterer Rand (wenn Platz)
                    safe_addstr(cy, x, "└" + "─" * (w - 2) + "┘", C["faint"])
                    return cy + 1
                return y_max + 1                             # abgeschnitten → Schluss

            y, rendered = top + life_h + 1, 0
            for p in proj_cache:
                if y > y_max or not isinstance(p, dict):
                    break
                y = proj_draw(p, x0, y, w0, y_max)
                rendered += 1
            if rendered < len(proj_cache):         # Rest passt nicht → ehrlich anzeigen
                safe_addstr(top + life_h + proj_h - 1, rx + rightw - 6,
                            "+%d" % (len(proj_cache) - rendered), C["faint"])

        oy = top + life_h + proj_h
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
            ck = current_ctx()
            ctx = (CTX_TITLES.get(ck, ck), CTX_KEYS.get(ck, [])) if ck else None
            ov_title, rows = overlay_rows(cmd_buf, help_latched, ctx)
            ov_w = min(W - 4, 56)
            ov_h = len(rows) + 2
            ov_x = 2
            ov_y = max(top, bot - ov_h + 1)
            draw_box(ov_y, ov_x, ov_h, ov_w, ov_title)
            # Innenzeilen ueber die testbare, DECKENDE Render-Funktion zeichnen.
            # Adapter reicht ihr curses-frei zwei Primitive: fill (= blanken via
            # safe_addstr) und put (= gekuerzt schreiben via addclip).
            ov_scr = _OverlayScreen(
                lambda y, x, n, ch, attr=0: safe_addstr(y, x, ch * max(0, n), attr),
                lambda y, x, text, maxw, attr=0: addclip(y, x, text, maxw, attr),
            )
            render_overlay_body(
                ov_scr, rows, ov_x, ov_y, ov_w,
                {"acc": C["acc"], "num": C["num"], "dim": C["dim"], "faint": C["faint"]},
            )

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
                " q quit · t theme: %s · g graph · m karte · c kalender · / befehle · %s" % (tm_txt, BASE_URL),
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
