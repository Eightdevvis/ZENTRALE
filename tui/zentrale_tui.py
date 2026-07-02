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
import queue
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
        self.reminders = []    # /api/graphs/reminders (heute fällig, noch nicht geloggt)
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
            try:
                rm = self._get("/api/graphs/reminders") or []
            except (urllib.error.URLError, OSError, ValueError):
                rm = []
            with self._lock:
                self.graphs = gs
                self.graph_vals = gv
                self.reminders = rm if isinstance(rm, list) else []
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

    def reminders_snapshot(self):
        """Heute fällige Graph-Reminder (id/name/remind_at) für den TUI-Nag."""
        with self._lock:
            return list(self.reminders)

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

# Marker-Symbole für time-Graphen in der lifestyle-Überlagerung. Früher war der
# Marker fest der Stern ★; jetzt gibt es eine Palette, aus der jeder time-Graph
# (in Anlege-Reihenfolge) SEIN eigenes Symbol bekommt — der Stern bleibt der
# erste/Default, danach variiert es (andere Sterne, Blumen, Schneeflocken …),
# damit sich mehrere Zeitpunkt-Graphen im selben 24h-Gitter nicht nur über die
# Farbe unterscheiden. Bewusst nur einfach-breite Dingbats (keine Emoji-Breite),
# lange Liste → genug zum Durchzykeln.
TIME_SYMBOLS = "★✦✿❀❁✽✻✷✶✴✳❈❉❋✼✾✩✫✭✮✯❆"


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
    print("  ai-backends         :", "local=%s cloud=%s cloud_enabled=%s%s" % (
        bool(bk.get("local")), bool(bk.get("cloud")), bk.get("cloud_enabled", True),
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
    ("/cloud", "Cloud-Drossel: on | off  (Datenschutz/Kosten)"),
    ("/quit",  "ZENTRALE-TUI beenden  (auch 'q')"),
]
TUI_KEYS = [
    ("q",   "beenden"),
    ("t",   "Theme wechseln (auto/hell/dunkel)"),
    ("g",   "Graph-Werkzeug (Mitte): anlegen / eintragen · p vorhersage-ergänzung · r tages-reminder"),
    ("l",   "Listen (Mitte): anlegen · einträge abhaken (space) / löschen · p als projekt rechts"),
    ("m",   "Karte (Mitte): pan ↑↓←→/hjkl · zoom +/− · 0 reset · Alt+↑↓←→ Land fokussieren · o=Handelsrouten · w=Fenster"),
    ("c",   "Kalender (Mitte): ↑↓ wählen · e bearbeiten · a neu · d löschen/Routine-aus · x erledigte/deaktivierte ein/aus · l Fokus in die Listen-Sidebar (dort a/r/d/space, kein Move) · → blättern · v Woche/Monat"),
    ("p",   "Post/Mail (Mitte): enter rein · lesen: ←→ vor/zurück, ↓ ausklappen/scrollen, ↑ scrollen · v lesen/liste · a antw · s einsort · d lösch · esc zurück"),
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
        ("n", "neu"), ("p", "~vorhersage"), ("r", "reminder"),
        ("d", "löschen"), ("esc", "zu"),
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
        ("d", "löschen / aus"), ("x", "erledigte zeigen"),
        ("l", "liste-fokus"), ("←→", "woche"), ("v", "monat"),
    ],
    "cal:month": [
        ("←→", "blättern"), ("v", "woche"), ("a", "neu"),
        ("x", "erledigte zeigen"), ("0", "heute"), ("esc", "zu"),
    ],
    "cal:list": [
        ("↑↓", "wählen"), ("space", "abhaken"), ("s", "sortieren"),
        ("a", "neu"), ("r", "umbenennen"), ("d", "löschen"), ("l/esc", "zurück"),
    ],
    "cal:sort": [
        ("↑↓", "verschieben"), ("s/esc", "fertig"),
    ],
    "mail:cats": [
        ("↑↓", "wählen"), ("enter", "öffnen"), ("r", "poll"),
        ("z", "neu zählen"), ("esc", "zu"),
    ],
    "mail:list": [
        ("↑↓", "wählen"), ("enter", "lesen"), ("a", "antworten"),
        ("s", "einsortieren"), ("d", "löschen"), ("z", "neu zählen"), ("esc", "zurück"),
    ],
    "mail:read": [
        ("←→", "vor/zurück"), ("↓", "ausklappen/scrollen"), ("↑", "scrollen/zu"),
        ("a", "antworten"), ("s", "einsortieren"), ("d", "löschen"), ("v", "liste"),
        ("z", "neu zählen"), ("esc", "zurück"),
    ],
}
CTX_TITLES = {
    "home": "start", "graph": "graph", "list:list": "listen",
    "list:view": "liste", "list:pick": "einordnen", "map": "karte",
    "cal:week": "kalender · woche", "cal:month": "kalender · monat",
    "cal:list": "kalender · liste", "cal:sort": "kalender · sortieren",
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
    if name == "cloud":                          # Cloud-Kill-Switch (POST macht der Aufrufer)
        if arg in ("on", "an"):   return "CLOUD_ON", theme_mode, ""
        if arg in ("off", "aus"): return "CLOUD_OFF", theme_mode, ""
        return "CLOUD_TOGGLE", theme_mode, ""
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
    ROLES = ["acc", "warn", "net", "graph", "event", "audio", "hook", "span",
             "num", "dim", "faint", "bright", "ink", "band"]
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
            "span":  (curses.COLOR_YELLOW,  216, 0),    # Mehrtages-Klammer: weiches Orange
            "num":   (curses.COLOR_YELLOW,  222, 0),
            "dim":   (curses.COLOR_WHITE,   231, 0),    # normaler Text: reinweiß = max Kontrast
            "faint": (curses.COLOR_WHITE,   245, 0),    # Rahmen: sichtbares Grau (nicht gedimmt)
            "bright":(curses.COLOR_WHITE,   231, curses.A_BOLD),
            "ink":   (curses.COLOR_WHITE,   231, 0),
            # Schlaf-Bande: gedämpftes Dunkelmagenta als ZELLEN-HINTERGRUND
            "band_fg": 245, "band_bg": 53,
            # Ombre der Sidebar-Liste: 256-Grau-Rampe, die nach unten in den
            # (schwarzen) Hintergrund verblasst → „weiter unten = transparenter".
            "ombre": [252, 246, 241, 237, 235],
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
            "span":  (curses.COLOR_RED,     166, 0),    # Mehrtages-Klammer: kräftiges Orange (auf Weiss lesbar)
            "num":   (curses.COLOR_BLUE,    26,  0),
            "dim":   (curses.COLOR_BLACK,   16,  0),    # schwarzer Text auf weiß
            "faint": (curses.COLOR_BLUE,    67,  0),    # Rahmen blau-grau (auf weiß sichtbar)
            "bright":(curses.COLOR_BLACK,   16,  curses.A_BOLD),
            "ink":   (curses.COLOR_BLACK,   16,  0),
            # Schlaf-Bande: hell-magenta angehauchtes Grau als ZELLEN-HINTERGRUND
            "band_fg": 240, "band_bg": 225,
            # Ombre der Sidebar-Liste: nach unten in den (weißen) Hintergrund
            # verblassend → Grau wird heller.
            "ombre": [238, 244, 248, 251, 253],
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
            # Ombre ohne Farbe: nur zwei Stufen (normal → gedimmt)
            C["ombre"] = [0, 0, curses.A_DIM, curses.A_DIM, curses.A_DIM]
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
            # Banden-KANTE als Vordergrund: band-bg-Farbe als fg auf Theme-bg.
            # Damit lassen sich Halbblöcke ▀/▄ am oberen/unteren Rand der Schlaf-
            # Bande in Bandfarbe zeichnen → sub-zellen-feine Ränder (sonst schnappt
            # der Balken auf ganze Zeilen ≈ 2–3 h und wirkt grob/hackig).
            curses.init_pair(pp, th["band_bg"], bg)
            C["band_edge"] = curses.color_pair(pp)
            pp += 1
        else:
            C["band"] = C["faint"]
            C["band_is_bg"] = False
        # Ombre-Rampe der Sidebar-Liste: eigene Grau-Paare (nur 256-Farben),
        # sonst zweistufiger A_DIM-Fallback.
        if c256:
            C["ombre"] = []
            for g in th.get("ombre", [245]):
                curses.init_pair(pp, g, bg)
                C["ombre"].append(curses.color_pair(pp))
                pp += 1
        else:
            C["ombre"] = [C["dim"], C["dim"], C["faint"],
                          C["faint"], C["faint"] | curses.A_DIM]
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

    # ── Graph-Reminder-Nag ──────────────────────────────────────────────
    # Poppt EINMAL pro Sitzung ein „bitte eintragen"-Kästchen, wenn ein Graph
    # mit Tages-Reminder heute noch nicht geloggt ist (store.reminders ←
    # /api/graphs/reminders). Eine Taste klickt es weg → bis Sitzungsende Ruhe
    # für die gezeigten Graphen (nag_dismissed); neu fällige nagen weiter.
    nag_active = False       # Kästchen steht gerade offen?
    nag_items = []           # was es listet (ids für die Dismiss-Markierung)
    nag_dismissed = set()    # in dieser Sitzung weggeklickte graph-ids

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
         "shown": set(),               # in der Überlagerung gezeigte graph-ids:
                                       # leer=alle (Übersicht), 1=solo+editieren,
                                       # mehrere=Kombi (nur Anzeige, später)
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
    #   showhidden: erledigte/abgeschaltete Einträge mit-anzeigen? Ein GEMEINSAMER
    #            Schalter (Taste 'x') über dreierlei „passiert nicht": einzeln
    #            deaktivierte Routine-Vorkommen (deaktiviert), per Zeitraum-Pause
    #            ausgefallene (ausfall, z.B. Ferien) UND abgehakte Wochenplan-
    #            Items (done). Default aus → der Kalender startet aufgeräumt;
    #            'x' blendet alles gemeinsam ein bzw. wieder aus.
    #   listfocus: Fokus in der rechten Sidebar-Liste (flache »week«-Liste)?
    #            Taste 'l' schiebt rein (nur Wochenansicht), Esc/'l' wieder raus.
    #            lsel = Auswahl-Index in der Sidebar; im Fokus bearbeitbar
    #            (a neu / r umbenennen / d löschen / Space abhaken) — KEIN Move
    #            in andere Listen (isolierte Einheit).
    #   linput/lmode/ledit_iid: Text-Eingabe der Sidebar. linput=None ⇒ inaktiv,
    #            sonst getippter Text; lmode "add"|"rename"; ledit_iid = iid beim
    #            Umbenennen.
    #   lsort: Sortier-Modus in der Sidebar (Taste 's')? Dann verschieben ↑↓ das
    #            fokussierte Item statt die Auswahl (POST …/reorder).
    K = {"active": False, "view": "week", "ref": date.today().isoformat(),
         "data": None, "msg": "", "mode": "view", "sel": 0, "confirmdel": False,
         "astage": 0, "aday": "", "atime": "", "alabel": "", "amsg": "",
         "atype": "entry", "editing": None, "ract": None, "rconfirm": False,
         "showhidden": False, "listfocus": False, "lsel": 0,
         "linput": None, "lmode": "add", "ledit_iid": None, "lsort": False,
         "spantgt": None}
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
            "off": 0, "data": None, "msg": "", "_ts": 0.0, "busy": "",
            "mails": None, "mails_live": False,   # mails: None=lädt, []=leer
            "fcache": {},         # Kategorie → zuletzt geholte Mail-Liste (Reopen instant)
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

    # ── Mail-I/O läuft im Hintergrund, NIE im Render/Input-Thread ─────────
    # Jede IMAP-Op (zählen, Ordner holen, Body, einsortieren, löschen) kann bei
    # Outlook Sekunden dauern. Früher lief das synchron im Zeichnen/Tasten-Loop
    # → die ganze TUI fror ein, esc klemmte, und man sah nicht, WAS gerade lud.
    # Jetzt arbeitet EIN Worker-Thread die Jobs ab; das Panel liest nur den
    # Zustand und zeigt `busy` an. `key` dedupt (kein Job-Stau beim schnellen
    # Blättern), `busy` verschwindet erst, wenn nichts mehr wartet.
    MAIL_Q = queue.Queue()
    MAIL_PENDING = set()
    MAIL_PLOCK = threading.Lock()

    def _mail_submit(key, label, fn):
        """Einen Mail-Job in den Hintergrund geben. Läuft/wartet schon einer mit
        gleichem `key`, wird NICHT doppelt eingereiht (Dedup). Leeres `label` =
        stiller Job (z.B. der billige 3s-Auto-Refresh, kein IMAP → kein Flackern)."""
        with MAIL_PLOCK:
            if key in MAIL_PENDING:
                return
            MAIL_PENDING.add(key)
        if label:
            MAIL["busy"] = label
        MAIL_Q.put((key, label, fn))

    def _mail_worker():
        while True:
            key, label, fn = MAIL_Q.get()
            if label:
                MAIL["busy"] = label
            try:
                fn()
            except Exception:
                pass
            finally:
                with MAIL_PLOCK:
                    MAIL_PENDING.discard(key)
                if MAIL_Q.empty():
                    MAIL["busy"] = ""

    threading.Thread(target=_mail_worker, daemon=True, name="mail-io").start()

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

    # Farb-Palette der Überlagerung, je Graph eine (durchgezykelt).
    LIFE_COL = ["graph", "acc", "warn", "net", "event", "audio", "hook", "num"]

    def draw_overlay(otop, oleft, oh, ow, gs_cache, gv_cache, labeled=False):
        """ÜBERLAGERUNG aller Graphen in EINEM Gitter (X=Datum/Zeitstrahl, Y je
        Typ eigene Achse). Zeichnet NUR Inhalt in das Rechteck (otop,oleft,oh,ow)
        — den Rahmen setzt der Aufrufer. Zwei Modi, geteilt von rechter
        lifestyle-Box und großer Mitte-Ansicht im Graph-Werkzeug:
          labeled=False (kompakt): 1 gemeinsame 24h-Achse links, scale als
              Kreis-Zeilen im Plot, mehrzeilige Legende unten. (unverändert)
          labeled=True (groß): links GESTAPELTE beschriftete y-achsen — je
              zahl-graph eine eigene farbige achse (min/max) + die 24h-uhr;
              scale-graphen als beschriftete zeile unten; Kopf-Legende oben.
        Darstellung je Typ: period→Bande, time→eigenes Symbol auf 24h,
        scale→Kreise ◦○◉●⬤, number→dünne Linie auf eigener min/max-Spanne."""
        if oh < 4 or ow < 12:
            return
        if not gs_cache:
            safe_addstr(otop + 1, oleft + 2, "// noch keine graphen (g)", C["faint"])
            return
        plot_x = oleft + 2
        # pro Graph: {datum: roh-eintrag}, Typ, Farbe (+ Symbol bei time).
        series = []
        time_n = 0                             # laufender Index NUR über time-Graphen
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
                srec = {"name": g.get("name", "?"), "type": g.get("type"),
                        "dv": dv, "col": LIFE_COL[i % len(LIFE_COL)],
                        "predict": bool(g.get("predict"))}
                if srec["type"] == "time":
                    srec["sym"] = TIME_SYMBOLS[time_n % len(TIME_SYMBOLS)]
                    time_n += 1
                series.append(srec)
        if not series:
            safe_addstr(otop + 1, oleft + 2, "// noch keine werte", C["faint"])
            return

        num_series = [s for s in series if s["type"] == "number"]
        scale_series = [s for s in series if s["type"] == "scale"]
        # Auswahl NUR aus scale-graphen (z.B. solo scale) → die Skala bekommt
        # eine eigene 1–5-y-achse mit Kreisen IM Gitter (die 24h-uhr wäre hier
        # sinnlos, die Boden-Zeile bliebe der Plot leer). Misch-Übersicht bleibt
        # unverändert: da rendert scale weiter als Zeile unten.
        only_scale = bool(scale_series) and len(scale_series) == len(series)

        # ── Layout je Modus: base/plot_h, linker Gutter (Achsen), Legende ──
        if labeled:
            AX_W = 5                           # breite EINER zahl-achsen-spalte
            n_ax = len(num_series)
            ix_clock = plot_x + AX_W * n_ax    # y-labels rechts vom zahl-gutter
            day_x0 = ix_clock + 3              # 2 achsen-spalten + │
            header_h = 1                       # kopf-legende
            scale_h = 1 if (scale_series and not only_scale) else 0
            base = otop + header_h
            plot_bottom = otop + oh - 1 - scale_h
            plot_h = max(2, plot_bottom - base + 1)
            leg_lines = None
        else:
            inner_h = oh - 2
            plot_w0 = max(2, ow - 4)
            leg_lines, cur_w = [[]], 0
            for s in series:
                nm = s["name"][:8]
                tok = "─ " + nm
                if cur_w + len(tok) + 1 > plot_w0 and leg_lines[-1]:
                    leg_lines.append([]); cur_w = 0
                leg_lines[-1].append((nm, s["col"], s["type"], s.get("sym")))
                cur_w += len(tok) + 1
            max_leg = min(len(leg_lines), max(1, inner_h - 3))
            plot_h = max(2, inner_h - max_leg)
            base = otop + 1
            ix_clock = plot_x
            day_x0 = plot_x + 3

        def row_clock(m):                      # 24h-Skala: 0 unten, 1440 oben
            m = max(0, min(1440, m))
            return base + (plot_h - 1) - int(round(m / 1440.0 * (plot_h - 1)))

        def row_norm(v, lo, hi):               # eigene Spanne: lo unten, hi oben
            n = 0.5 if hi is None or hi == lo else (float(v) - lo) / (hi - lo)
            n = max(0.0, min(1.0, n))
            return base + (plot_h - 1) - int(round(n * (plot_h - 1)))

        def row_scale(v):                      # 1–5-Skala: 1 unten, 5 oben
            n = (max(1.0, min(5.0, float(v))) - 1) / 4.0
            return base + (plot_h - 1) - int(round(n * (plot_h - 1)))

        # Tages-Spalten (X = Zeitstrahl, heute rechts, ältester Tag links).
        # kompakt: GENAU 1 Spalte/Tag, füllt die Breite (viele Tage).
        # groß: Fenster = tatsächliche Datenspanne (frühester wert … heute),
        #   über die volle Breite GESTRECKT, damit die Daten den Platz füllen
        #   statt rechts an der Achse zu kleben (mehrere Spalten/Tag möglich).
        today = date.today()
        day_x_end = oleft + ow - 2
        avail = max(1, day_x_end - day_x0 + 1)
        if labeled:
            all_dates = [dd for s in series for dd in s["dv"].keys()]
            span = avail
            if all_dates:
                try:
                    ey, em, ed = (int(x) for x in min(all_dates).split("-"))
                    span = (today - date(ey, em, ed)).days + 1
                except Exception:
                    span = avail
            ndays = max(1, min(span, 366))
            window = [(today - timedelta(days=k)).isoformat() for k in range(ndays - 1, -1, -1)]
            if ndays == 1:
                day_col = {window[0]: day_x_end}
            else:
                day_col = {d: day_x0 + int(round(i / (ndays - 1) * (avail - 1)))
                           for i, d in enumerate(window)}
        else:
            window = [(today - timedelta(days=k)).isoformat() for k in range(avail - 1, -1, -1)]
            day_col = {d: day_x0 + i for i, d in enumerate(window)}
        day_center = day_col
        cols = window
        # Spalten-Spanne je Tag → zusammenhängende Banden auch bei Streckung
        # (kompakt: 1 Spalte, also unverändert).
        day_span = {}
        for idx, d in enumerate(window):
            x0 = day_col[d]
            x1 = (day_col[window[idx + 1]] - 1) if idx + 1 < len(window) else day_x_end
            day_span[d] = (x0, max(x0, x1))

        # Linke y-achse: 24h-uhr — ODER 1–5-skala, wenn NUR scale-graphen gewählt
        # sind (dann sind stunden sinnlos). Senkrechte Linie + Marken-Labels +
        # (groß) feines waagerechtes Hilfsraster: gepunktet, jede 2. Spalte, faint
        # und ZUERST gemalt → Banden/Marker/Linien überzeichnen es. Erleichtert
        # das Ablesen der Werte-Höhe quer über den Zeitstrahl.
        for r in range(plot_h):
            safe_addstr(base + r, day_x0 - 1, "│", C["faint"])
        if only_scale:
            axrows = [(row_scale(v), str(v)) for v in (1, 2, 3, 4, 5)]
        else:
            marks = (0, 3, 6, 9, 12, 15, 18, 21, 24) if (labeled and plot_h >= 8) else (0, 6, 12, 18, 24)
            axrows = [(row_clock(hh * 60), "%02d" % (hh % 24)) for hh in marks]
        if labeled:
            for gr in {r for r, _l in axrows}:
                for cx in range(day_x0, day_x_end + 1, 2):
                    safe_addstr(gr, cx, "·", C["faint"])
        for gr, lbl in axrows:
            safe_addstr(gr, ix_clock, lbl.rjust(2), C["faint"])

        NPRED = 7

        def predicted_days(s):
            """{datum: schätz-entry _pred=True} für Fenster-Lücken — nur wenn der
            Graph predict trägt (sonst {}); nichts vor dem ersten echten Wert."""
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

        # 1. period/Schlaf als zusammenhängende Bande HINTER allem.
        band_glyph = " " if C.get("band_is_bg") else "▒"
        band_cells = set()
        band_fine = bool(C.get("band_is_bg")) and ("band_edge" in C)

        def frow(m):                           # 24h-Skala als FRAKTIONALE Zeile
            m = max(0, min(1440, m))
            return base + (plot_h - 1) - (m / 1440.0 * (plot_h - 1))

        def draw_band_seg(cx, a, b, pred):
            ftop, fbot = frow(b), frow(a)      # ftop <= fbot (screen)
            rt, rb = int(round(ftop)), int(round(fbot))
            g = "░" if pred else band_glyph    # geschätzt = schraffiert
            fine = band_fine and not pred and rb > rt
            for r in range(rt, rb + 1):
                if fine and r == rt:           # Oberkante: unterer Zellteil → ▄
                    cover = (r + 0.5) - ftop
                    if cover >= 0.75:
                        safe_addstr(r, cx, g, C["band"]); band_cells.add((r, cx))
                    elif cover >= 0.25:
                        safe_addstr(r, cx, "▄", C["band_edge"])
                elif fine and r == rb:         # Unterkante: oberer Zellteil → ▀
                    cover = fbot - (r - 0.5)
                    if cover >= 0.75:
                        safe_addstr(r, cx, g, C["band"]); band_cells.add((r, cx))
                    elif cover >= 0.25:
                        safe_addstr(r, cx, "▀", C["band_edge"])
                else:
                    safe_addstr(r, cx, g, C["band"]); band_cells.add((r, cx))

        for s in series:
            if s["type"] != "period":
                continue
            for d, e in list(s["dv"].items()) + list(predicted_days(s).items()):
                span = day_span.get(d)
                v, end = _num(e.get("value")), _num(e.get("end"))
                if span is None or v is None or end is None:
                    continue
                st, en = int(round(v)), int(round(end))
                segs = ([(st, en)] if en >= st else [(st, 1440), (0, en)])
                for a, b in segs:
                    for cx in range(span[0], span[1] + 1):   # ganze Tages-Breite
                        draw_band_seg(cx, a, b, bool(e.get("_pred")))

        def latt(r, c, col):                   # in Banden-Zellen: @band-Variante
            if (r, c) in band_cells and (col + "@band") in C:
                return C[col + "@band"]
            return C[col]

        # 2. scale: Kreise ◦○◉●⬤. Drei Fälle:
        #   kompakt        → je graph EINE Kreis-Zeile (gestapelt unten im Plot)
        #   groß+only_scale → Kreise auf 1–5-HÖHE im Gitter (eigene y-achse)
        #   groß+gemischt   → als beschriftete Zeile ganz unten (siehe unten)
        CIRC = "◦○◉●⬤"
        if not labeled:
            srow = 0
            for s in scale_series:
                ry = base + plot_h - 1 - srow
                srow += 1
                if ry < base:
                    continue
                col = s["col"]
                for d, e in list(s["dv"].items()) + list(predicted_days(s).items()):
                    cx = day_center.get(d)
                    v = _num(e.get("value"))
                    if cx is None or v is None:
                        continue
                    idx = max(0, min(4, int(round(v)) - 1))
                    attr = latt(ry, cx, "faint") if e.get("_pred") else latt(ry, cx, col)
                    safe_addstr(ry, cx, CIRC[idx], attr)
        elif only_scale:
            for s in scale_series:
                col = s["col"]
                for d, e in list(s["dv"].items()) + list(predicted_days(s).items()):
                    cx = day_center.get(d)
                    v = _num(e.get("value"))
                    if cx is None or v is None:
                        continue
                    idx = max(0, min(4, int(round(v)) - 1))
                    ry = row_scale(v)
                    attr = latt(ry, cx, "faint") if e.get("_pred") else latt(ry, cx, col)
                    safe_addstr(ry, cx, CIRC[idx], attr)

        # 3. time: eigenes Symbol je Graph auf der 24h-Skala.
        for s in series:
            if s["type"] != "time":
                continue
            col = s["col"]
            sym = s.get("sym") or TIME_SYMBOLS[0]
            for d, e in list(s["dv"].items()) + list(predicted_days(s).items()):
                cx = day_center.get(d)
                v = _num(e.get("value"))
                if cx is None or v is None:
                    continue
                r = row_clock(int(round(v)))
                attr = latt(r, cx, "faint") if e.get("_pred") else latt(r, cx, col)
                safe_addstr(r, cx, sym, attr)

        # 4. number: dünne Linie auf eigener min/max-Spanne (+ groß: y-achse).
        for j, s in enumerate(num_series):
            col, dv = s["col"], s["dv"]
            vis = [_num(dv[d].get("value")) for d in cols if d in dv]
            vis = [x for x in vis if x is not None]
            lo, hi = (min(vis), max(vis)) if vis else (None, None)
            pts = []
            for d, e in dv.items():
                cx = day_center.get(d)
                v = _num(e.get("value"))
                if cx is None or v is None:
                    continue
                pts.append((cx, row_norm(v, lo, hi)))
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
            for d, e in predicted_days(s).items():
                cx = day_center.get(d)
                v = _num(e.get("value"))
                if cx is None or v is None:
                    continue
                safe_addstr(row_norm(v, lo, hi), cx, "·", latt(row_norm(v, lo, hi), cx, "faint"))
            # groß: beschriftete y-achse dieses zahl-graphen im linken Gutter
            if labeled and lo is not None:
                axx = plot_x + j * AX_W
                def _axlbl(x):                 # kurz + ohne hässliches Trailing-'.'
                    if abs(x) >= 10 or x == round(x):
                        return "%d" % int(round(x))
                    return "%.1f" % x
                safe_addstr(base, axx, _axlbl(hi)[:AX_W - 1].rjust(AX_W - 1), C[col])
                safe_addstr(base + plot_h - 1, axx, _axlbl(lo)[:AX_W - 1].rjust(AX_W - 1), C[col])

        if labeled:
            # Kopf-Legende (name+symbol/marker je Graph, farbig) in EINER Zeile.
            hx = plot_x
            for s in series:
                if s["type"] == "period":
                    mk = "▓"
                elif s["type"] == "scale":
                    mk = "●"
                elif s["type"] == "time":
                    mk = s.get("sym") or TIME_SYMBOLS[0]
                else:
                    mk = "─"
                nm = s["name"][:9]
                if hx + len(nm) + 3 > oleft + ow - 1:
                    break
                safe_addstr(otop, hx, mk, C[s["col"]])
                addclip(otop, hx + 2, nm, oleft + ow - 1 - (hx + 2), C["dim"])
                hx += 2 + len(nm) + 1
            # scale-Zeile unten: je graph name + Kreis-Verlauf der letzten werte.
            # Nur bei gemischter Auswahl — only_scale rendert im Gitter (oben).
            if scale_series and not only_scale:
                sy = otop + oh - 1
                sx = plot_x
                safe_addstr(sy, sx, "skala:", C["faint"]); sx += 7
                for s in scale_series:
                    nm = s["name"][:8]
                    if sx + len(nm) + 2 > oleft + ow - 8:
                        break
                    addclip(sy, sx, nm, oleft + ow - 1 - sx, C["dim"]); sx += len(nm) + 1
                    dvs = sorted((e for e in s["dv"].values() if isinstance(e, dict)),
                                 key=lambda e: str(e.get("date", "")))
                    for e in dvs[-8:]:
                        if sx >= oleft + ow - 6:
                            break
                        vv = _num(e.get("value"))
                        if vv is None:
                            continue
                        safe_addstr(sy, sx, CIRC[max(0, min(4, int(round(vv)) - 1))], C[s["col"]])
                        sx += 1
                    sx += 2
                if sx < oleft + ow - 5:
                    safe_addstr(sy, oleft + ow - 5, "1–5", C["faint"])
        else:
            # kompakte Legende unter dem Plot: farbiges Marker-Sample + Name.
            for li, line in enumerate(leg_lines[:max_leg]):
                yy = base + plot_h + li
                cx = plot_x
                for nm, col, typ, sym in line:
                    if typ == "period":
                        safe_addstr(yy, cx, band_glyph, C["band"])
                    elif typ == "scale":
                        safe_addstr(yy, cx, "●", C[col])
                    elif typ == "time":
                        safe_addstr(yy, cx, sym or TIME_SYMBOLS[0], C[col])
                    else:
                        safe_addstr(yy, cx, "─", C[col])
                    addclip(yy, cx + 2, nm, (ow - 4) - (cx - plot_x) - 2, C["dim"])
                    cx += 2 + len(nm) + 1

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

        elif G["view"] == "remind" and G["graphs"]:
            nm = str(G["graphs"][G["sel"]].get("name") or "")
            addclip(by + 1, ix, "REMINDER: " + nm, iw, C["bright"])
            addclip(by + 3, ix, "täglich erinnern ab welcher uhrzeit?", iw, C["dim"])
            addclip(by + 5, ix, "uhrzeit (HH:MM): " + G["input"] + "_", iw, C["bright"])
            addclip(by + 7, ix, "erinnert dich, bis du für den tag eingetragen hast.", iw, C["faint"])
            addclip(bottom, ix, ("HH:MM · enter an · esc zurück  " + G["msg"]).strip(), iw, C["faint"])

        elif G["view"] in ("list", "view"):
            # EINE vereinte Ansicht: dieselbe große Überlagerung (draw_overlay,
            # beschriftete y-achsen) OBEN, darunter die Graphliste. G["shown"]
            # (Menge von ids) filtert die Überlagerung — leer = ALLE (Übersicht),
            # genau EINE = solo: nur dieser Graph + seine Eingabezeile unten.
            # (Kombis später: shown mit mehreren → nur Anzeige, kein Eintrag.)
            shown = G.get("shown") or set()
            subset = [g for g in G["graphs"] if isinstance(g, dict)
                      and (not shown or g.get("id") in shown)]
            solo = G["def"] if (len(shown) == 1 and G["def"]) else None
            typ = solo.get("type") if solo else None
            input_row = by + bh - 3
            # ── Überlagerung oben (auf subset gefiltert), so groß wie es geht ──
            ly = by + 1
            if subset and bh >= 18 and iw >= 26:
                avail = ((input_row - 1) - (by + 1)) if solo else (bh - 3)
                ng = len([g for g in G["graphs"] if isinstance(g, dict)])
                list_h = min(2 + ng, max(4, avail // 2))
                ov_h = avail - list_h
                if ov_h >= 8:
                    draw_overlay(by + 1, bx, ov_h, bw, subset, gv_cache, labeled=True)
                    ly = by + 1 + ov_h             # Liste beginnt unter der Ansicht
            hdr = ("nur %s" % (solo.get("name") or "?")) if solo else "GRAPHEN"
            addclip(ly, ix, hdr, iw, C["bright"])
            if not solo:
                safe_addstr(ly, bx + bw - 9, "[n neu]", C["acc"])
            safe_addstr(ly + 1, ix, "─" * iw, C["faint"])
            list_bottom = (input_row - 1) if solo else bottom
            yy = ly + 2
            if not G["graphs"]:
                addclip(yy, ix, "noch keine — 'n' legt einen an", iw, C["faint"])
            else:
                # Fenster um den Cursor, damit ↑↓ (auch im Solo) nicht aus dem
                # sichtbaren Ausschnitt läuft, wenn mehr Graphen als Platz da sind.
                navail = max(1, list_bottom - (ly + 2))
                ntot = len(G["graphs"])
                gstart = max(0, min(G["sel"] - navail + 1, ntot - navail)) if ntot > navail else 0
                for i in range(gstart, ntot):
                    if yy >= list_bottom:
                        break
                    g = G["graphs"][i]
                    if not isinstance(g, dict):
                        continue
                    cur = (i == G["sel"])
                    on = (not shown) or (g.get("id") in shown)    # in Überlagerung sichtbar?
                    rows = gv_cache.get(g.get("id")) or []
                    spark = blockspark(graph_series(g.get("type"), rows)[-8:])
                    pred = "~" if g.get("predict") else " "   # ~ = Lücken werden geschätzt
                    mk = "●" if on else "○"                   # ●=gezeigt · ○=abgewählt
                    line = "%s%s%s%-11s %-6s %s" % (
                        "›" if cur else " ", mk, pred, str(g.get("name") or "")[:11],
                        _tlabel(g.get("type")), spark)
                    if g.get("remind"):                       # @HH:MM = täglicher Reminder
                        line += "  @" + (g.get("remind_at") or "")
                    attr = C["bright"] if cur else (C["dim"] if on else C["faint"])
                    addclip(yy, ix, line, iw, attr)
                    yy += 1
            if solo:
                # Eingabezeile des solo-Graphen (Tag-Nav, HH:MM, 1–5 — wie gehabt).
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
                if typ == "time":
                    addclip(input_row, ix, "%s · zeit: %s_%s" % (dl, G["input"], eh), iw, C["bright"])
                    hint = "HH:MM · enter speichern · ↑↓ graph · ←→ tag · esc alle"
                elif typ == "period":
                    c1 = G["input"] + ("_" if G["pstage"] == 0 else "")
                    c2 = G["input2"] + ("_" if G["pstage"] == 1 else "")
                    addclip(input_row, ix, "%s · von: %s  bis: %s%s" % (dl, c1, c2, eh), iw, C["bright"])
                    hint = "HH:MM · enter von→bis · ↑↓ graph · ←→ tag · esc alle"
                elif typ == "scale":
                    addclip(input_row, ix, "1–5 trägt für %s ein%s" % (dl, eh), iw, C["acc"])
                    hint = "1–5 eintragen · ↑↓ graph · ←→ tag · esc alle"
                else:  # number
                    addclip(input_row, ix, "%s · wert: %s_%s" % (dl, G["input"], eh), iw, C["bright"])
                    hint = "ziffern · enter speichern · ↑↓ graph · ←→ tag · esc alle"
                addclip(bottom, ix, (hint + "  " + G["msg"]).strip(), iw, C["faint"])
            elif G["msg"]:                     # Shortcuts liegen unter '/'; nur Feedback
                addclip(bottom, ix, G["msg"], iw, C["faint"])
            else:
                addclip(bottom, ix, "enter solo · n neu · p ~vorhersage · r reminder · d weg · esc zu", iw, C["faint"])

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
            # Woche bleibt die normale Mo-So-Kalenderwoche; nur die Wochenplan-
            # Items (week_plan) rollen — auf ihr nächstes Vorkommen in den 7
            # Tagen ab heute verankert, erscheinen am passenden Datum.
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
                if e.get("deaktiviert") and not K["showhidden"]:
                    continue   # ausgeblendet (nur mit 'x'); MUSS exakt zur Skip-
                    # Bedingung im Wochen-Render passen, sonst zeigt der ›-Cursor
                    # auf den falschen Termin (di-Index läuft synchron mit).
                out.append({"iso": iso, "label": e.get("label", ""),
                            "layer": e.get("layer", "termine"),
                            "recurring": bool(e.get("recurring")),
                            "deaktiviert": bool(e.get("deaktiviert")),
                            "spanning": bool(e.get("spanning")),
                            "von": e.get("von"), "bis": e.get("bis"),
                            "span_first": bool(e.get("span_first")),
                            "span_last": bool(e.get("span_last")),
                            "time": e.get("time"), "ende": e.get("ende"),
                            "ort": e.get("ort")})
        return out

    def k_sidebar_items():
        """Die SICHTBAREN Items der flachen »week«-Sidebar (abgehakte fallen mit
        dem 'x'-Schalter raus). Gleiche Filterung wie im Render → Handler und
        Zeichnung sehen exakt dieselbe Reihenfolge/Länge (lsel bleibt gültig)."""
        d = K["data"]
        wp = d.get("weekplan") if isinstance(d, dict) else None
        items = wp.get("items") if isinstance(wp, dict) else None
        if not isinstance(items, list):
            return []
        return [it for it in items if isinstance(it, dict)
                and (K["showhidden"] or not it.get("done"))]

    def k_sidebar_lid():
        """id der »week«-Liste aus der letzten Antwort (oder None)."""
        d = K["data"]
        wp = d.get("weekplan") if isinstance(d, dict) else None
        return wp.get("lid") if isinstance(wp, dict) else None

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

        if K["atype"] == "span":               # MEHRTÄGIGER (ganztägiger) Termin
            von = k_parse_day(K["aday"])
            bis = k_parse_day(K["atime"])      # Stufe 1 hält das Bis-Datum
            if von is None or bis is None:
                K["amsg"] = "datum? TT.MM"; return
            if bis < von:
                K["amsg"] = "bis < von"; return
            try:
                api_call("/api/calendar/entry", method="POST",
                         body={"day": von, "bis": bis, "label": label})
                K["msg"] = "mehrtägig angelegt: " + label
                K["ref"] = von; K["data"] = None
                K["mode"] = "view"; K["astage"] = 0; K["atype"] = "entry"
                K["aday"] = K["atime"] = K["alabel"] = K["amsg"] = ""
            except Exception:
                K["amsg"] = "speichern fehlgeschlagen"
            return

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
        elif it.get("spanning"):
            # Mehrtägig: „bearbeiten" heißt Uhrzeit NUR für diesen Tag setzen
            # (leer = wieder ganztags). Eingabe unten in der ›-Leiste.
            K["linput"] = it.get("time") or ""; K["lmode"] = "spantime"
            K["spantgt"] = (it["layer"], it.get("von"), it["label"], it["iso"])
            K["msg"] = ""
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

    def _k_entry_line(e, day_iso=None):
        """Eine Termin-Zeile kompakt: Zeit(spanne) + Label (+ Ort). Ausfall
        (Ferien) als ℹ-Hinweis statt Termin. Mehrtägige Termine (spanning)
        laufen NICHT hier durch — die zeichnet der Wochen-Render als durchgehende
        Klammer in der linken Spann-Gosse (day_iso bleibt nur der Kompatibilität
        halber im Signatur)."""
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
            is_span = (K["atype"] == "span")
            if K["editing"]:
                title = "TERMIN ÄNDERN"
            elif is_rt:
                title = "NEUE ROUTINE"
            elif is_span:
                title = "MEHRTÄGIG"
            else:
                title = "NEUER TERMIN"
            addclip(fy, ix, title, iw, C["bright"])
            # Typ-Umschalter (nur bei Neuanlage, nicht beim Ändern).
            if not K["editing"]:
                tabs = [("Termin", not is_rt and not is_span),
                        ("Routine", is_rt), ("Mehrtägig", is_span)]
                xx = ix + len(title) + 3
                for name, on in tabs:
                    seg = ("[%s]" % name) if on else (" %s " % name)
                    safe_addstr(fy, xx, seg, C["acc"] if on else C["faint"])
                    xx += len(seg) + 1
                safe_addstr(fy, xx + 1, "(Tab)", C["faint"])
            if is_rt:
                addclip(fy + 2, ix, "Tag:   " + K["aday"] + (cz if K["astage"] == 0 else "")
                        + "   (Mo/Di/.., mehrere mit Komma)", iw,
                        C["bright"] if K["astage"] == 0 else C["dim"])
            else:
                lbl0 = "Von:   " if is_span else "Datum: "
                addclip(fy + 2, ix, lbl0 + K["aday"] + (cz if K["astage"] == 0 else "")
                        + "   (TT.MM, leer=heute)", iw, C["bright"] if K["astage"] == 0 else C["dim"])
            if is_span:
                addclip(fy + 3, ix, "Bis:   " + K["atime"] + (cz if K["astage"] == 1 else "")
                        + "   (TT.MM, letzter tag)", iw, C["bright"] if K["astage"] == 1 else C["dim"])
            else:
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

        span_hint = ""                 # ▶-Hinweis, wenn ein Spann-Tag gewählt ist
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
                if isinstance(ents, list) and not K["showhidden"]:
                    ents = [e for e in ents
                            if not (isinstance(e, dict)
                                    and (e.get("deaktiviert") or e.get("ausfall")))]
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
            # Wochenansicht: normale Mo-So-Kalenderwoche. Pro Tag ein
            # zeilen-ausgerichtetes BAND — links die Termine (auswählbar,
            # ›-Cursor/K["sel"]), rechts die zugeordneten Items der »week«-Liste
            # (week_plan rollt: dieser Wochentag = sein nächstes Vorkommen ab
            # heute, erscheint also am passenden Datum dieser Woche). Die Bänder
            # stapeln sich, jeder Tag hat seine eigene Höhe → Montag-Items können
            # NICHT in die Dienstag-Zeile bluten. Passt alles in die Box →
            # natürliche Höhe (gestreckt); reicht der Platz nicht → pro Tag
            # einklappen ("…+N"). Reihenfolge der Termine = k_selectable().
            try:
                start = date.fromisoformat(d["start"]); end = date.fromisoformat(d["end"])
            except (KeyError, ValueError):
                return
            # Sidebar = flache »week«-Liste (wochenunabhängig), EINE Spalte über
            # die volle Höhe — NICHT mehr pro Tag. sitems = sichtbare Items
            # (abgehakte via 'x' aus). lsel defensiv klemmen.
            sitems = k_sidebar_items()
            if K["lsel"] >= len(sitems):
                K["lsel"] = max(0, len(sitems) - 1)
            nsel = len(k_selectable())
            if K["sel"] >= nsel:
                K["sel"] = max(0, nsel - 1)

            # Spalten: links Termine, rechts Wochenplan (nur wenn breit genug).
            rcw = max(0, (iw - 3) * 2 // 5)        # ~40 % für die Plan-Spalte
            if rcw < 8:
                rcw = 0                             # zu schmal → keine Plan-Spalte
            lcw = iw - rcw - (1 if rcw else 0)     # Rest links (− Trenner)
            divx = ix + lcw                         # Spalte des "│"-Trenners

            # Pro Tag die Zeilen einsammeln. di läuft über ALLE Termine in
            # k_selectable-Reihenfolge (sortierte Tage, Eintragsreihenfolge);
            # Ausfälle (Ferien) sind reine Info (di=None, nicht auswählbar).
            days_rows = []
            di = 0
            span_map = {}          # (von,label,layer) → {"label", "cells":[(day_idx,di)]}
            day_idx = 0
            cur = start
            while cur <= end:
                iso = cur.isoformat()
                ents = days.get(iso)
                if not isinstance(ents, list):
                    ents = []
                left = []                           # [(txt, attr, di|None)]
                for e in ents:
                    if not isinstance(e, dict):
                        continue
                    if e.get("ausfall"):
                        # Ferien/Pausen-Ausfall (add_pause über Zeitraum) ist
                        # dieselbe Sorte „passiert nicht" wie einzeln deaktiviert
                        # → GLEICHER Toggle. Reine Info (di=None), berührt den
                        # Auswahl-Index nie → kein Sync-Problem mit k_selectable.
                        if not K["showhidden"]:
                            continue
                        left.append(("  " + _k_entry_line(e, iso), C["faint"], None))
                        continue
                    if e.get("deaktiviert") and not K["showhidden"]:
                        continue   # ausgeblendet: NICHT zeichnen und di NICHT
                        # erhöhen → Index bleibt synchron mit k_selectable().
                    cur_di = di; di += 1
                    if e.get("spanning"):
                        # Mehrtägig: NICHT inline (sonst reißt die Klammer, sobald
                        # der Tag andere Termine hat) → sammeln für die linke
                        # Spann-Gosse. di trotzdem zählen → Sync mit k_selectable;
                        # auswählbar bleibt es (Cursor hebt die Gosse des Tages).
                        key = (e.get("von"), e.get("label"), e.get("layer"))
                        sm = span_map.setdefault(
                            key, {"label": e.get("label") or "?", "cells": []})
                        sm["cells"].append((day_idx, cur_di))
                        continue
                    if e.get("deaktiviert"):
                        left.append(("✗ " + _k_entry_line(e, iso) + "  (aus)", C["faint"], cur_di))
                    elif cur_di == K["sel"]:
                        left.append((_k_entry_line(e, iso), C["bright"] | curses.A_REVERSE, cur_di))
                    else:
                        left.append((_k_entry_line(e, iso), C["dim"], cur_di))
                # Rechte Spalte pro Tag gibt es nicht mehr — die Sidebar ist EINE
                # flache Liste (unten separat). right bleibt leer, damit die
                # Höhenverteilung nur die Termine (links) berücksichtigt.
                days_rows.append((cur, iso, left, []))
                day_idx += 1
                cur += timedelta(days=1)

            # Spann-Gosse links: je Mehrtages-Termin EINE durchgehende Klammer über
            # alle betroffenen Tages-Zeilen; überlappende Spannen bekommen eigene
            # Spalten (Lanes, Greedy). gw = Gossenbreite → die Tages-Spalte rückt
            # um gw(+1) nach rechts, damit die Klammer außerhalb der Daten steht.
            spans = []
            for _key, sm in span_map.items():
                idxs = [c[0] for c in sm["cells"]]
                spans.append({"label": sm["label"], "cells": sm["cells"],
                              "d0": min(idxs), "d1": max(idxs)})
            spans.sort(key=lambda s: (s["d0"], s["d1"]))
            lane_end = []                           # letzter belegter day_idx je Lane
            for s in spans:
                s["lane"] = None
                for li in range(len(lane_end)):
                    if s["d0"] > lane_end[li]:
                        lane_end[li] = s["d1"]; s["lane"] = li; break
                if s["lane"] is None:
                    s["lane"] = len(lane_end); lane_end.append(s["d1"])
            gw = min(len(lane_end), max(0, (iw - rcw) // 4))
            cx = ix + (gw + 1 if gw else 0)         # Start-Spalte der Tages-Inhalte
            lw = (divx - cx) if rcw else (ix + iw - cx)
            if lw < 6:                              # Notbremse: zu schmal → keine Gosse
                gw = 0; cx = ix; lw = lcw if rcw else iw

            # Höhen verteilen: Bedarf je Tag = max(links, rechts, 1) Inhaltszeilen
            # (+1 Kopfzeile). Passt die Summe → jeder bekommt seinen Bedarf;
            # sonst fair aufteilen und den Rest reihum an die Hungrigen geben.
            y0 = by + 2
            avail = bottom - y0
            nd = len(days_rows)
            needs = [max(len(l), len(r), 1) for (_c, _i, l, r) in days_rows]
            caps = [0] * nd
            budget = avail - nd                     # je Tag eine Kopfzeile abziehen
            if budget > 0 and nd:
                base = budget // nd
                for i in range(nd):
                    caps[i] = min(needs[i], base)
                leftover = budget - sum(caps)
                i = 0
                while leftover > 0 and any(caps[j] < needs[j] for j in range(nd)):
                    if caps[i] < needs[i]:
                        caps[i] += 1; leftover -= 1
                    i = (i + 1) % nd

            # Bleibt nach dem Füllen Höhe übrig (großes Display), als etwas Luft
            # ZWISCHEN die Tage geben, statt sie unten zu sammeln — dezent
            # (max 2 Leerzeilen je Lücke), Trenner läuft durch.
            gap = min(2, max(0, (avail - (nd + sum(caps))) // max(1, nd - 1)))

            day_top = [None] * nd                   # y der Kopfzeile je Tag
            day_bot = [None] * nd                   # y der letzten Zeile je Tag
            yy = y0
            for idx, (cd, iso, left, right) in enumerate(days_rows):
                if yy >= bottom:
                    break
                day_top[idx] = yy
                is_today = (iso == today)
                hdr = "%s %s" % (KAL_WD[cd.weekday()], cd.strftime("%d.%m."))
                addclip(yy, cx, hdr + ("  ‹heute›" if is_today else ""),
                        lw, C["bright"] if is_today else C["acc"])
                if rcw:
                    safe_addstr(yy, divx, "│", C["faint"])
                day_bot[idx] = yy
                yy += 1
                cap = caps[idx]
                for r in range(cap):
                    if yy >= bottom:
                        break
                    if rcw:
                        safe_addstr(yy, divx, "│", C["faint"])
                    # Linke Spalte: Termine (letzte sichtbare Zeile klappt den Rest ein).
                    if r < len(left):
                        if r == cap - 1 and len(left) > cap:
                            addclip(yy, cx, "  …+%d" % (len(left) - cap + 1), lw, C["faint"])
                        else:
                            txt, attr, dd = left[r]
                            if dd is None:
                                addclip(yy, cx, txt, lw, attr)
                            else:
                                mark = "› " if dd == K["sel"] else "  "
                                addclip(yy, cx, mark + txt, lw, attr)
                    elif not left and r == 0:
                        addclip(yy, cx + 2, "—", lw - 2, C["faint"])
                    # (rechte Spalte: siehe Sidebar-Block nach der Tages-Schleife)
                    day_bot[idx] = yy
                    yy += 1
                # Luft zwischen den Tagen (nicht nach dem letzten); Trenner durch.
                if gap and idx < nd - 1:
                    for _g in range(gap):
                        if yy >= bottom:
                            break
                        if rcw:
                            safe_addstr(yy, divx, "│", C["faint"])
                        yy += 1

            # ── Spann-Gosse zeichnen: durchgehende Klammer + senkrechter Titel ──
            # ┌ am ersten sichtbaren Tag, └ am letzten; dazwischen laufen die
            # Titel-Buchstaben AM STÜCK nach unten (ein Zeichen pro Zeile), Rest
            # als │. Der ausgewählte Tag (Cursor) hebt seinen Klammer-Abschnitt
            # invers hervor — so bleibt die Spanne per ↑↓ ansteuerbar (e/d).
            for s in spans:
                lane = s["lane"]
                if lane >= gw or s["d0"] >= nd or s["d1"] >= nd:
                    continue
                ytop, ybot = day_top[s["d0"]], day_bot[s["d1"]]
                if ytop is None or ybot is None:
                    continue
                gx = ix + lane
                title = s["label"] or "?"
                sel_day = next((dd for (dd, ddi) in s["cells"] if ddi == K["sel"]), None)
                for y in range(ytop, ybot + 1):
                    if y == ytop:
                        chc = "┌"
                    elif y == ybot:
                        chc = "└"
                    else:
                        pos = y - (ytop + 1)
                        chc = title[pos] if pos < len(title) else "│"
                    hot = (sel_day is not None and day_top[sel_day] is not None
                           and day_top[sel_day] <= y <= day_bot[sel_day])
                    safe_addstr(y, gx, chc,
                                (C["bright"] | curses.A_REVERSE) if hot else C["span"])
                if sel_day is not None:
                    span_hint = "▶ %s · %s" % (title, days_rows[sel_day][1])

            # ── Sidebar: flache »week«-Liste (rechte Spalte, volle Höhe) ──
            # Unabhängig von den Tages-Bändern. 'l' schiebt den Fokus hierher
            # (‹fokus›), dann bearbeitbar (a/r/d/Space). Abgehakte via 'x' aus.
            if rcw:
                for yv in range(y0, bottom):        # Trenner über die volle Höhe
                    safe_addstr(yv, divx, "│", C["faint"])
                foc = K["listfocus"]
                sx = divx + 1                        # Cursor-Gosse ab hier
                sw = ix + iw - sx                    # Restbreite rechts
                if K["linput"] is not None and K["lmode"] in ("add", "rename"):
                    head = "liste  ‹" + ("neu" if K["lmode"] == "add"
                                         else "umbenennen") + " unten›"
                elif K["lsort"]:
                    head = "liste  ‹sortieren ↑↓›"
                elif foc:
                    head = "liste  ‹fokus›"
                else:
                    head = "liste"
                addclip(y0, sx + 1, head, sw - 1, C["bright"] if foc else C["acc"])
                sy = y0 + 1
                avail = max(0, bottom - sy)          # verfügbare Zeilen
                step = 2                             # 1 Leerzeile Abstand je Item
                cap = max(1, (avail + 1) // step)    # so viele Items passen
                n = len(sitems)
                off = (min(max(0, K["lsel"] - cap // 2), max(0, n - cap))
                       if (foc and n > cap) else 0)
                if n == 0:
                    addclip(sy, sx + 1, "— leer (a: neu)", sw - 1, C["faint"])
                else:
                    # Ombre: nach unten (visible-Position) progressiv transparenter.
                    ombre = C.get("ombre") or [C["dim"]]
                    shown = 0
                    i = off
                    while i < n and shown < cap:
                        yy2 = sy + shown * step
                        if shown == cap - 1 and (n - off) > cap:
                            addclip(yy2, sx + 1, "…+%d" % (n - off - cap + 1),
                                    sw - 1, C["faint"])
                            break
                        it = sitems[i]
                        done = bool(it.get("done"))
                        cur_s = foc and i == K["lsel"]
                        head_mark = ("⇅ " if (cur_s and K["lsort"])
                                     else ("› " if cur_s else "  "))
                        txt = (head_mark + ("✓ " if done else "• ")
                               + str(it.get("text", ""))
                               + (" ↔" if it.get("linked") else ""))
                        attr = ((C["bright"] | curses.A_REVERSE) if cur_s
                                else ombre[min(shown, len(ombre) - 1)])
                        addclip(yy2, sx, txt, sw, attr)
                        i += 1
                        shown += 1

        info = "%s · %s" % ("woche" if K["view"] == "week" else "monat", label)
        if span_hint:
            info += "   " + span_hint
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
            MAIL["data"] = api_call("/api/mail", timeout=8.0)
            MAIL["msg"] = ""
        except Exception:
            MAIL["data"] = {"failed": True}
            MAIL["msg"] = "mail: backend?"
        MAIL["_ts"] = time.time()

    def _do_refresh_counts(force=False):
        """Live-Ordnerzählung im Backend anstoßen (Backend zählt im eigenen
        Thread, der POST kehrt schnell zurück). `force` umgeht die Backend-TTL —
        nötig, wenn sich die Zahlen gerade geändert haben (nach Umsortieren)."""
        try:
            q = "/api/mail/refresh-counts" + ("?force=1" if force else "")
            api_call(q, method="POST", timeout=8.0)
        except Exception:
            pass

    def mail_refresh_counts():
        """Zählung im Hintergrund anstoßen — friert die TUI nicht ein."""
        _mail_submit(("counts",), "zähle ordner…", _do_refresh_counts)

    def _mail_fetch_folder(name, force=False):
        """Die Mails einer Kategorie holen (läuft im Worker). Schreibt das
        Ergebnis nur, wenn der Nutzer nicht inzwischen weitergeschaltet hat, und
        zeigt einen ECHTEN Fehler statt ihn als „(Ordner leer)" zu verschleiern.
        `force=1` umgeht den Backend-Cache (nach Umsortieren/Löschen). Meldet das
        Backend, dass es im Hintergrund frisch nachzieht (`refreshing`), holen wir
        das Ergebnis nach kurzer Wartezeit noch einmal, damit die frische Liste
        einschwenkt."""
        mails, live, err, refreshing = None, False, None, False
        try:
            q = "/api/mail/folder?cat=" + urllib.parse.quote(name or "")
            if force:
                q += "&force=1"
            r = api_call(q, timeout=30.0)
            if isinstance(r, dict) and r.get("error"):
                mails, err = [], str(r.get("error"))
            elif isinstance(r, dict):
                mails = r.get("mails") if isinstance(r.get("mails"), list) else []
                live = bool(r.get("live"))
                refreshing = bool(r.get("refreshing"))
            else:
                mails = []
        except urllib.error.HTTPError as e:
            mails = []
            try:
                j = json.loads(e.read().decode("utf-8"))
                err = str(j.get("error", "HTTP %d" % e.code))
            except Exception:
                err = "HTTP %d" % e.code
        except Exception as ex:
            mails, err = [], "%s (backend?)" % type(ex).__name__
        if MAIL["cat"] != name:            # Nutzer ist weiter → Ergebnis verwerfen
            return
        MAIL["mails"] = mails
        MAIL["mails_live"] = live
        MAIL["msg"] = ("ordner: " + err) if err else ""
        if not err and isinstance(mails, list):
            MAIL["fcache"][name] = mails   # Reopen zeigt das sofort
        if refreshing and not err:
            # Backend zieht gerade frisch nach → gleich nochmal (still) abholen.
            t = threading.Timer(2.0, lambda n=name: _mail_submit(
                ("folder-refresh", n), "", lambda: _mail_fetch_folder(n)))
            t.daemon = True
            t.start()

    def mail_open_category(name):
        """Eine Kategorie öffnen: Ansicht sofort umschalten. Liegt der Ordner noch
        im TUI-Cache, zeigen wir ihn SOFORT und frischen still im Hintergrund auf
        (kein „lädt ordner…"-Warten mehr beim Wieder-Aufmachen); sonst holt der
        Worker ihn (Backend serviert i.d.R. instant aus SEINEM Cache)."""
        MAIL["cat"] = name
        MAIL["level"] = "mails"
        MAIL["off"] = 0
        MAIL["mode2"] = "read"; MAIL["msel"] = 0
        MAIL["expanded"] = False; MAIL["bodyoff"] = 0
        MAIL["body"] = None; MAIL["bodyfor"] = None
        MAIL["picking"] = False; MAIL["confirmdel"] = False
        cached = MAIL["fcache"].get(name)
        MAIL["mails"] = cached                 # sofort zeigen (None ⇒ „lädt…")
        MAIL["mails_live"] = cached is not None
        MAIL["msg"] = ""
        _mail_submit(("folder", name),
                     "" if cached is not None else "lädt ordner…",
                     lambda n=name: _mail_fetch_folder(n))

    def mail_cur():
        """Die aktuell ausgewählte Mail (oder None)."""
        ms = MAIL["mails"] or []
        return ms[MAIL["msel"]] if 0 <= MAIL["msel"] < len(ms) else None

    def _do_body(uid, it):
        """Body EINER Mail holen (läuft im Worker). Nachbarn zum Vorwärmen
        mitschicken; ECHTEN Fehlergrund zeigen statt „backend?"."""
        ms = MAIL["mails"] or []
        acct = it.get("account") or ""
        try:
            sel = ms.index(it)
        except ValueError:
            sel = MAIL["msel"]
        neigh = []
        for j in (sel + 1, sel - 1):
            if 0 <= j < len(ms):
                nb = ms[j]
                nu = nb.get("uid")
                # Cache ist konto-skaliert → nur gleichkontige Nachbarn vorwärmen.
                if nu is not None and (nb.get("account") or "") == acct:
                    neigh.append(str(nu))
        try:
            q = ("/api/mail/body?cat=" + urllib.parse.quote(MAIL["cat"] or "")
                 + "&uid=" + str(uid)
                 + "&account=" + urllib.parse.quote(it.get("account") or ""))
            if neigh:
                q += "&prefetch=" + urllib.parse.quote(",".join(neigh))
            r = api_call(q, timeout=30.0)
            body = r if isinstance(r, dict) else {"error": "?"}
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read().decode("utf-8"))
                body = {"error": j.get("error", "HTTP %d" % e.code)}
            except Exception:
                body = {"error": "HTTP %d" % e.code}
        except Exception as ex:
            body = {"error": "%s (Backend erreichbar?)" % type(ex).__name__}
        MAIL["body"] = body
        MAIL["bodyfor"] = uid

    def mail_request_body():
        """Body der aktuellen Mail im Hintergrund anfordern (dedupt je uid).
        Blockiert NICHT — der Worker füllt MAIL['body'], das Panel zeigt solange
        „lädt Text…". Schon geladen/gecacht → sofort da."""
        it = mail_cur()
        if not it:
            MAIL["body"] = None; MAIL["bodyfor"] = None
            return
        uid = it.get("uid")
        if MAIL["bodyfor"] == uid and isinstance(MAIL["body"], dict):
            return
        _mail_submit(("body", it.get("account"), uid), "lädt text…",
                     lambda u=uid, item=it: _do_body(u, item))

    def _do_assign(sender, category):
        try:
            r = api_call("/api/mail/assign", method="POST",
                         body={"sender": sender, "category": category},
                         timeout=60.0)
            moved = (r or {}).get("moved", 0) if isinstance(r, dict) else 0
            MAIL["msg"] = "absender → %s (%d verschoben)" % (category, moved)
        except Exception:
            MAIL["msg"] = "einsortieren: backend?"
        # force=1: Backend-Cache umgehen, damit die umsortierten Mails hier
        # wirklich rausfallen (sonst zeigte der Cache sie noch).
        _mail_fetch_folder(MAIL["cat"], force=True)
        MAIL["body"] = None; MAIL["bodyfor"] = None
        _do_refresh_counts(force=True)    # Zahlen haben sich geändert

    def mail_assign(category):
        """Den ABSENDER der aktuellen Mail einer Kategorie zuordnen UND alle
        seine vorhandenen Mails dorthin verschieben (im Hintergrund — das kann
        bei Outlook lange dauern, die TUI bleibt derweil bedienbar)."""
        it = mail_cur()
        MAIL["picking"] = False
        if not it:
            return
        sender = it.get("from") or ""
        MAIL["msg"] = "sortiere absender ein…"
        _mail_submit(("assign", sender, category), "sortiere absender ein…",
                     lambda s=sender, c=category: _do_assign(s, c))

    def _do_delete(cat, uid, acct):
        try:
            r = api_call("/api/mail/delete", method="POST",
                         body={"cat": cat, "uid": uid, "account": acct},
                         timeout=30.0)
            if isinstance(r, dict) and r.get("ok"):
                MAIL["mails"] = [m for m in (MAIL["mails"] or [])
                                 if not (m.get("uid") == uid
                                         and m.get("account") == acct)]
                MAIL["fcache"][cat] = MAIL["mails"]   # Cache mitziehen (Reopen)
                MAIL["body"] = None; MAIL["bodyfor"] = None
                MAIL["msg"] = "gelöscht (Papierkorb)"
            else:
                MAIL["msg"] = "löschen abgelehnt"
        except Exception:
            MAIL["msg"] = "löschen: backend?"
        _do_refresh_counts(force=True)

    def mail_delete():
        """Die aktuelle Mail in den Papierkorb (umkehrbar) — im Hintergrund."""
        it = mail_cur()
        MAIL["confirmdel"] = False
        if not it:
            return
        MAIL["msg"] = "löscht…"
        _mail_submit(("delete", it.get("account"), it.get("uid")), "löscht…",
                     lambda c=MAIL["cat"], u=it.get("uid"),
                            a=it.get("account"): _do_delete(c, u, a))

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

    def _do_poll():
        try:
            r = api_call("/api/mail/poll", method="POST", timeout=8.0)
            if isinstance(r, dict) and r.get("error"):
                MAIL["msg"] = "kein key — keyring-set nötig"
            elif isinstance(r, dict) and r.get("already"):
                MAIL["msg"] = "poll läuft schon…"
            else:
                MAIL["msg"] = "poll gestartet — siehe log links"
        except Exception:
            MAIL["msg"] = "poll: backend?"

    def mail_poll():
        """Live-Poll im Backend anstoßen (im Hintergrund). Der Fortschritt läuft
        über das Log links. Braucht Passphrase (Env/Keyring)."""
        _mail_submit(("poll",), "poll…", _do_poll)

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
            _mail_submit("load", "", mail_load)   # billig, still (kein IMAP)
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
            if MAIL["busy"]:
                head += "  ⟳ " + MAIL["busy"]
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
                # Bei einem Ordner-Fehler den ECHTEN Grund zeigen, nicht „leer".
                addclip(body_top, ix, MAIL["msg"] or "(Ordner leer)", iw, C["faint"])
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
            mail_request_body()
            who = (it.get("from") or "?").strip()
            subj = (it.get("subject") or "").strip() or "(kein Betreff)"
            addclip(body_top, ix, "Von:     " + who, iw, C["bright"])
            addclip(body_top + 1, ix, "Betreff: " + subj, iw, C["acc"])
            addclip(body_top + 2, ix, "─" * iw, iw, C["faint"])
            txt_top = body_top + 3
            txt_h = bottom - txt_top
            # Body nur zeigen, wenn er zur AKTUELLEN Mail gehört — sonst „lädt…".
            b = MAIL["body"] if MAIL["bodyfor"] == it.get("uid") else None
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
                        addclip(txt_top + prev_h, ix, "  … (↓ zum Ausklappen)",
                                iw, C["faint"])
            if MAIL["confirmdel"]:
                hint = "wirklich löschen? j/n"
            else:                              # Shortcuts liegen unter '/'; nur Position/Feedback
                hint = MAIL["msg"] or ("%d/%d" % (MAIL["msel"] + 1, n))
            addclip(bottom, ix, hint, iw, C["faint"])
            return

        # ── Ebene 1: nur die Kategorien (Auswahl) ─────────────────────
        head = "Postfach · %d Kategorien" % len(cats)
        if MAIL["busy"]:
            head += "  ⟳ " + MAIL["busy"]
        elif polling:
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
        mail_request_body()
        MAIL["replying"] = True
        MAIL["reply_text"] = ""
        MAIL["reply_origoff"] = 0
        MAIL["reply_confirm"] = False
        MAIL["msg"] = ""

    def _do_reply(payload):
        try:
            r = api_call("/api/mail/reply", method="POST", body=payload,
                         timeout=60.0)
            if isinstance(r, dict) and r.get("ok"):
                MAIL["msg"] = "✓ Antwort gesendet"
            else:
                MAIL["msg"] = "senden fehlgeschlagen: %s" % (
                    (r or {}).get("error", "?") if isinstance(r, dict) else "?")
        except Exception:
            MAIL["msg"] = "senden: backend?"

    def mail_reply_send():
        """Den getippten Text als Antwort senden (SMTP via Backend, im
        Hintergrund). Der Editor schließt sofort, das Senden läuft im Worker."""
        it = mail_cur()
        if not it or not MAIL["reply_text"].strip():
            MAIL["reply_confirm"] = False
            MAIL["msg"] = "leer — nichts gesendet"
            MAIL["replying"] = False
            return
        payload = {"cat": MAIL["cat"], "uid": it.get("uid"),
                   "account": it.get("account"), "text": MAIL["reply_text"]}
        MAIL["replying"] = False
        MAIL["reply_confirm"] = False
        MAIL["msg"] = "sende antwort…"
        _mail_submit(("reply", it.get("uid")), "sendet antwort…",
                     lambda p=payload: _do_reply(p))

    def _do_reply_draft(payload):
        try:
            r = api_call("/api/mail/reply", method="POST", body=payload,
                         timeout=60.0)
            if isinstance(r, dict) and r.get("ok"):
                MAIL["msg"] = "✎ als Entwurf gespeichert"
            else:
                MAIL["msg"] = "entwurf fehlgeschlagen: %s" % (
                    (r or {}).get("error", "?") if isinstance(r, dict) else "?")
        except Exception:
            MAIL["msg"] = "entwurf: backend?"

    def mail_reply_draft():
        """Den getippten Text als ECHTEN Entwurf in den Drafts-Ordner legen (IMAP
        APPEND via Backend) — nichts geht raus, in Outlook/Handy weiterschreibbar.
        Editor schließt sofort, das Speichern läuft im Worker."""
        it = mail_cur()
        if not it or not MAIL["reply_text"].strip():
            MAIL["reply_confirm"] = False
            MAIL["msg"] = "leer — kein entwurf"
            MAIL["replying"] = False
            return
        payload = {"cat": MAIL["cat"], "uid": it.get("uid"),
                   "account": it.get("account"), "text": MAIL["reply_text"],
                   "draft": True}
        MAIL["replying"] = False
        MAIL["reply_confirm"] = False
        MAIL["msg"] = "speichere entwurf…"
        _mail_submit(("draft", it.get("uid")), "speichere entwurf…",
                     lambda p=payload: _do_reply_draft(p))

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
        title = "antwort" + ("  · j/e/n?" if MAIL["reply_confirm"] else "")
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
            hint = "j senden · e entwurf · n verwerfen · w weiter"
        else:
            hint = "tippen · enter=zeile · esc=fertig/senden"
        addclip(by + bh - 2, rix, hint[:riw], riw, C["faint"])

    def in_text_entry():
        """Tippt der Nutzer gerade einen Freitext (Name, Eintrag, Antwort)?
        Dann bleibt '/' ein normales Zeichen und öffnet NICHT die Befehlszeile."""
        if G["active"]:
            return G["view"] in ("new", "view", "remind")   # Name/Wert/Reminder-Uhrzeit
        if L["active"]:
            return L["adding"] or L["view"] in ("new", "move_new")
        if K["active"]:
            # Termin/Routine anlegen+bearbeiten ODER Sidebar-Item neu/umbenennen
            return K["mode"] == "add" or K["linput"] is not None
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
            if K["listfocus"]:
                return "cal:sort" if K["lsort"] else "cal:list"
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

        if nag_active:
            if ch != -1:                       # jede Taste klickt den Reminder weg (Sitzung)
                for r in nag_items:
                    nag_dismissed.add(r.get("id"))
                nag_active = False
                if ch in (ord("g"), ord("G")):  # g = gleich ins Graph-Werkzeug
                    G["active"] = True; G["view"] = "list"; G["msg"] = ""; g_load()
        elif help_latched:
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
                if res in ("CLOUD_ON", "CLOUD_OFF", "CLOUD_TOGGLE"):
                    # Cloud-Kill-Switch umlegen (POST ans Backend, front-agnostisch
                    # dieselbe Quelle wie der Browser). Danach EXTERNAL sofort frisch.
                    try:
                        if res == "CLOUD_TOGGLE":
                            on = not store.backends_snapshot().get("cloud_enabled", True)
                        else:
                            on = (res == "CLOUD_ON")
                        st = api_call("/api/ai/backends", "POST", {"cloud_enabled": on})
                        store._poll_backends()
                        cmd_msg = "cloud " + ("AN" if (st or {}).get("cloud_enabled") else "GEDROSSELT")
                    except (urllib.error.URLError, OSError, ValueError):
                        cmd_msg = "cloud-schalter fehlgeschlagen"
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
                        G["shown"] = {G["def"]["id"]}   # solo: nur dieser gezeigt
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
                elif ch in (ord("r"), ord("R")):              # tages-reminder an/aus
                    if G["graphs"]:
                        cur = G["graphs"][G["sel"]]
                        if cur.get("remind"):                 # an → direkt aus
                            try:
                                api_call("/api/graphs/%s/remind" % cur["id"], method="POST",
                                         body={"remind": False})
                                g_load(); G["msg"] = "reminder aus"
                            except Exception:
                                G["msg"] = "reminder fehlgeschlagen"
                        else:                                 # aus → uhrzeit eintippen
                            G["input"] = cur.get("remind_at") or "20:00"
                            G["msg"] = ""; G["view"] = "remind"
            elif G["view"] == "remind":
                # Uhrzeit für den Tages-Reminder eintippen (HH:MM), enter setzt an.
                if ch == 27:
                    G["view"] = "list"; G["msg"] = ""
                elif ch in (10, 13, curses.KEY_ENTER):
                    if G["graphs"]:
                        cur = G["graphs"][G["sel"]]
                        try:
                            api_call("/api/graphs/%s/remind" % cur["id"], method="POST",
                                     body={"remind": True, "at": G["input"].strip()})
                            g_load(); G["msg"] = "reminder an " + G["input"].strip()
                            G["view"] = "list"
                        except Exception:
                            G["msg"] = "uhrzeit ungültig (HH:MM)"
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    G["input"] = G["input"][:-1]
                elif (48 <= ch <= 57 or ch == ord(":")) and len(G["input"]) < 5:
                    G["input"] += chr(ch)
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
                    else:                                      # zurück zur Übersicht (alle zeigen)
                        G["view"] = "list"; G["shown"] = set()
                        G["input"] = ""; G["input2"] = ""
                        G["pstage"] = 0; G["msg"] = ""; G["dayoff"] = 0
                elif ch in (curses.KEY_UP, curses.KEY_DOWN):    # solo-Graph wechseln (↑↓)
                    if G["graphs"]:
                        step = -1 if ch == curses.KEY_UP else 1
                        G["sel"] = max(0, min(len(G["graphs"]) - 1, G["sel"] + step))
                        G["def"] = G["graphs"][G["sel"]]
                        G["shown"] = {G["def"]["id"]}
                        G["input"] = ""; G["input2"] = ""; G["pstage"] = 0
                        G["dayoff"] = 0; G["msg"] = ""
                        g_load_vals()
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
                is_span = (K["atype"] == "span")   # mehrtägig: Stufe 1 = Bis-Datum
                if ch == 9 and not K["editing"]:   # Tab → Termin→Routine→Mehrtägig
                    K["atype"] = {"entry": "routine", "routine": "span",
                                  "span": "entry"}[K["atype"]]
                    K["aday"] = ""; K["atime"] = ""; K["astage"] = 0; K["amsg"] = ""
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
                        if is_span:                # Stufe 1 = Bis-Datum (Pflicht)
                            if k_parse_day(K["atime"]) is None:
                                K["amsg"] = "bis-datum? TT.MM"
                            else:
                                K["astage"] = 2; K["amsg"] = ""
                        elif K["atime"].strip() and parse_clock(K["atime"]) is None:
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
                            K["aday"] += cc            # (Von-)Datum: TT.MM
                    elif K["astage"] == 1:
                        if is_span and (cc.isdigit() or cc in "./-") and len(K["atime"]) < 10:
                            K["atime"] += cc           # Bis-Datum: TT.MM
                        elif (not is_span) and (cc.isdigit() or cc == ":") and len(K["atime"]) < 5:
                            K["atime"] += cc           # Zeit: HH:MM
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
            elif K["linput"] is not None:      # ›-Leisten-Eingabe: Sidebar (a/r) ODER Spannen-Zeit
                if ch == 27:                   # Esc → Eingabe abbrechen
                    K["linput"] = None; K["ledit_iid"] = None; K["spantgt"] = None
                elif ch in (10, 13, curses.KEY_ENTER):
                    txt = K["linput"].strip()
                    if K["lmode"] == "spantime":    # per-Tag-Uhrzeit einer Spanne
                        if txt and parse_clock(txt) is None:
                            K["msg"] = "zeit? HH:MM (leer=ganztags)"
                        else:
                            tgt = K["spantgt"]
                            if tgt:
                                layer, von, label, day = tgt
                                api_call("/api/calendar/entry/spantime", method="POST",
                                         body={"layer": layer, "von": von, "label": label,
                                               "day": day, "time": txt})
                                K["msg"] = ("zeit gesetzt: " + txt) if txt else "wieder ganztags"
                                k_fetch()
                            K["linput"] = None; K["spantgt"] = None
                    else:                           # Sidebar-Liste: neu / umbenennen
                        lid = k_sidebar_lid()
                        if txt and lid:
                            if K["lmode"] == "add":
                                api_call("/api/lists/%s/items" % lid, method="POST",
                                         body={"text": txt})
                            elif K["ledit_iid"] is not None:
                                api_call("/api/lists/%s/items/%s/rename" % (lid, K["ledit_iid"]),
                                         method="POST", body={"text": txt})
                            k_fetch()
                        K["linput"] = None; K["ledit_iid"] = None
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    K["linput"] = K["linput"][:-1]
                elif 32 <= ch <= 126 and len(K["linput"]) < 60:
                    K["linput"] += chr(ch)
            elif K["confirmdel"]:              # Lösch-Nachfrage (Einmal-Termin) offen
                if ch in (ord("j"), ord("J"), ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
                    sels = k_selectable()
                    if sels and 0 <= K["sel"] < len(sels) and not sels[K["sel"]]["recurring"]:
                        it = sels[K["sel"]]
                        # Mehrtägig: über den Start-Tag (von) löschen → ganze Spanne weg.
                        day = it.get("von") or it["iso"]
                        k_delete_sel((day, it["label"], it["layer"]))
                    K["confirmdel"] = False
                elif ch != -1:                 # alles andere bricht ab
                    K["confirmdel"] = False; K["msg"] = ""
            elif K["listfocus"]:               # Fokus in der Sidebar-Liste
                # Isolierte Einheit: bearbeiten ja (a/r/d/Space) + sortieren (s),
                # aber KEIN Move in andere Listen. lid/Items aus der letzten Antwort.
                lid = k_sidebar_lid()
                sit = k_sidebar_items()
                if ch in (ord("c"), ord("C")):                 # c → Kalender ganz zu
                    K["active"] = False; K["listfocus"] = False; K["lsort"] = False
                elif ch in (ord("q"), ord("Q")):
                    break
                elif ch in (ord("t"), ord("T")):
                    theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
                elif K["lsort"]:                               # ── Sortier-Modus ──
                    if ch in (27, ord("s"), ord("S"), ord("l"), ord("L"),
                              10, 13, curses.KEY_ENTER):
                        K["lsort"] = False; K["msg"] = ""      # sortieren fertig
                    elif ch in (curses.KEY_UP, ord("k"), curses.KEY_DOWN, ord("j")):
                        delta = -1 if ch in (curses.KEY_UP, ord("k")) else 1
                        if lid and 0 <= K["lsel"] < len(sit):
                            iid = sit[K["lsel"]]["id"]
                            api_call("/api/lists/%s/items/%s/reorder" % (lid, iid),
                                     method="POST", body={"delta": delta})
                            k_fetch()
                            for idx2, itx in enumerate(k_sidebar_items()):
                                if itx.get("id") == iid:       # Cursor dem Item nachziehen
                                    K["lsel"] = idx2; break
                else:                                          # ── normaler Fokus ──
                    if ch in (27, curses.KEY_LEFT, ord("h"), ord("l")):  # zurück zum Kalender
                        K["listfocus"] = False; K["msg"] = ""
                    elif ch in (curses.KEY_UP, ord("k")):
                        K["lsel"] = max(0, K["lsel"] - 1)
                    elif ch in (curses.KEY_DOWN, ord("j")):
                        K["lsel"] = min(max(0, len(sit) - 1), K["lsel"] + 1)
                    elif ch in (ord(" "), 10, 13, curses.KEY_ENTER):   # abhaken (mit Link-Sync)
                        if lid and 0 <= K["lsel"] < len(sit):
                            api_call("/api/lists/%s/items/%s/toggle" % (lid, sit[K["lsel"]]["id"]),
                                     method="POST")
                            k_fetch()
                    elif ch in (ord("s"), ord("S")):           # s → Sortier-Modus
                        if sit:
                            K["lsort"] = True; K["msg"] = ""
                    elif ch in (ord("a"), ord("A")):           # a → neues Item
                        K["linput"] = ""; K["lmode"] = "add"; K["ledit_iid"] = None; K["msg"] = ""
                    elif ch in (ord("r"), ord("R")):           # r → umbenennen
                        if 0 <= K["lsel"] < len(sit):
                            K["linput"] = str(sit[K["lsel"]].get("text", ""))
                            K["lmode"] = "rename"; K["ledit_iid"] = sit[K["lsel"]]["id"]; K["msg"] = ""
                    elif ch in (ord("d"), ord("D")):           # d → löschen (nur Kopie, nicht Quelle)
                        if lid and 0 <= K["lsel"] < len(sit):
                            api_call("/api/lists/%s/items/%s" % (lid, sit[K["lsel"]]["id"]),
                                     method="DELETE")
                            k_fetch()
                    elif ch in (ord("x"), ord("X")):           # erledigte ein/aus gilt auch hier
                        K["showhidden"] = not K["showhidden"]; K["lsel"] = 0
                        K["msg"] = "erledigte: " + ("an" if K["showhidden"] else "aus")
                    elif ch in (ord("v"), ord("V"), 9):        # Monat hat keine Sidebar → Fokus raus
                        K["listfocus"] = False; k_toggle(); K["sel"] = 0; K["msg"] = ""
            else:                              # View-Modus: blättern/auswählen
                if ch in (27, ord("c"), ord("C")):             # Esc/c → Kalender zu
                    K["active"] = False
                elif ch in (ord("q"), ord("Q")):               # q → ganze TUI beenden
                    break
                elif ch in (curses.KEY_LEFT, ord("h")):
                    k_step(-1); K["sel"] = 0; K["msg"] = ""
                elif ch == curses.KEY_RIGHT:                   # → nächste Periode (l ist jetzt Sidebar)
                    k_step(1); K["sel"] = 0; K["msg"] = ""
                elif ch in (ord("l"), ord("L")):               # l → Fokus in die Sidebar-Liste
                    if K["view"] == "week":
                        K["listfocus"] = True; K["lsel"] = 0; K["msg"] = ""
                    else:
                        K["msg"] = "liste nur in der wochenansicht"
                elif ch in (curses.KEY_UP, ord("k")):
                    K["sel"] = max(0, K["sel"] - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    K["sel"] = K["sel"] + 1    # Klemmung passiert beim Zeichnen
                elif ch in (ord("v"), ord("V"), 9):            # v/Tab → Woche↔Monat
                    k_toggle(); K["sel"] = 0; K["msg"] = ""
                elif ch == ord("0"):                           # 0 → zurück zu heute
                    k_today(); K["sel"] = 0; K["msg"] = ""
                elif ch in (ord("x"), ord("X")):               # x → erledigtes ein-/ausblenden
                    # Ein Schalter für alles „passiert nicht": deaktivierte +
                    # ausgefallene (Ferien/Pause) Termine + abgehakte Plan-Punkte.
                    # Nur Anzeige-Filter → kein Neu-Laden nötig.
                    K["showhidden"] = not K["showhidden"]; K["sel"] = 0
                    K["msg"] = "erledigte: " + ("an" if K["showhidden"] else "aus")
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
                elif ch in (ord("e"), ord("E")):               # e → als Entwurf sichern
                    mail_reply_draft()
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
                elif ch == 27:                                 # Esc → zurück zu Kategorien
                    MAIL["level"] = "cats"; MAIL["msg"] = ""
                elif ch in (ord("p"), ord("P")):               # p → Panel ganz zu
                    MAIL["active"] = False
                elif ch in (ord("q"), ord("Q")):
                    break
                elif ch in (ord("v"), ord("V"), 9):            # v/Tab → lesen↔liste
                    MAIL["mode2"] = "list" if MAIL["mode2"] == "read" else "read"
                    MAIL["expanded"] = False; MAIL["bodyoff"] = 0; MAIL["msg"] = ""
                elif MAIL["mode2"] == "read" and ch in (curses.KEY_LEFT,
                                                        curses.KEY_RIGHT):
                    # ←/→ = vorige/nächste Mail im Stapel (gepuffert zusammenfassen,
                    # damit schnelles Durchklicken nicht pro Taste den Body lädt).
                    delta = 1 if ch == curses.KEY_RIGHT else -1
                    stdscr.nodelay(True)
                    while True:
                        nx = stdscr.getch()
                        if nx == curses.KEY_RIGHT:
                            delta += 1
                        elif nx == curses.KEY_LEFT:
                            delta -= 1
                        else:
                            if nx != -1:
                                curses.ungetch(nx)
                            break
                    stdscr.timeout(250)
                    MAIL["msel"] = max(0, MAIL["msel"] + delta)  # Obergrenze beim Zeichnen
                    MAIL["expanded"] = False; MAIL["bodyoff"] = 0; MAIL["msg"] = ""
                elif MAIL["mode2"] == "read" and ch in (curses.KEY_DOWN, ord("j"),
                                                        ord(" ")):
                    # ↓ aus der Vorschau = ausklappen; im Text = runterscrollen.
                    if not MAIL["expanded"]:
                        MAIL["expanded"] = True; MAIL["bodyoff"] = 0
                    else:
                        step = 5 if ch == ord(" ") else 1
                        stdscr.nodelay(True)
                        while True:
                            nx = stdscr.getch()
                            if nx in (curses.KEY_DOWN, ord("j")):
                                step += 1
                            elif nx in (curses.KEY_UP, ord("k")):
                                step -= 1
                            else:
                                if nx != -1:
                                    curses.ungetch(nx)
                                break
                        stdscr.timeout(250)
                        MAIL["bodyoff"] = max(0, MAIL["bodyoff"] + step)
                    MAIL["msg"] = ""
                elif MAIL["mode2"] == "read" and ch in (curses.KEY_UP, ord("k")):
                    # ↑ = hochscrollen; ganz oben nochmal ↑ → wieder einklappen.
                    if MAIL["expanded"]:
                        if MAIL["bodyoff"] > 0:
                            step = 1
                            stdscr.nodelay(True)
                            while True:
                                nx = stdscr.getch()
                                if nx in (curses.KEY_UP, ord("k")):
                                    step += 1
                                elif nx in (curses.KEY_DOWN, ord("j")):
                                    step -= 1
                                else:
                                    if nx != -1:
                                        curses.ungetch(nx)
                                    break
                            stdscr.timeout(250)
                            MAIL["bodyoff"] = max(0, MAIL["bodyoff"] - step)
                        else:
                            MAIL["expanded"] = False
                    MAIL["msg"] = ""
                elif MAIL["mode2"] == "list" and ch in (curses.KEY_LEFT, ord("h")):
                    MAIL["level"] = "cats"; MAIL["msg"] = ""   # Liste: ← zurück
                elif MAIL["mode2"] == "list" and ch in (
                        curses.KEY_UP, curses.KEY_DOWN, ord("k"), ord("j"),
                        ord("n"), ord("N"), ord(" ")):
                    # LISTE: rauf/runter wählt eine Mail (gepuffert zusammenfassen).
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
                    MAIL["msel"] = max(0, MAIL["msel"] + delta)
                    MAIL["bodyoff"] = 0; MAIL["msg"] = ""
                elif MAIL["mode2"] == "list" and ch in (10, 13, curses.KEY_ENTER,
                                                        curses.KEY_RIGHT, ord("l")):
                    MAIL["mode2"] = "read"               # aus Liste: gewählte lesen
                    MAIL["expanded"] = False; MAIL["bodyoff"] = 0
                elif ch == curses.KEY_NPAGE:                   # Bild↓ → Body runter
                    MAIL["bodyoff"] = MAIL["bodyoff"] + 5
                elif ch == curses.KEY_PPAGE:                   # Bild↑ → Body hoch
                    MAIL["bodyoff"] = max(0, MAIL["bodyoff"] - 5)
                elif ch in (ord("s"), ord("S")):               # einsortieren (Absender)
                    MAIL["picking"] = True; MAIL["picksel"] = 0; MAIL["msg"] = ""
                elif ch in (ord("d"), ord("D")):               # löschen (Papierkorb)
                    MAIL["confirmdel"] = True; MAIL["msg"] = ""
                elif ch in (ord("a"), ord("A")):               # antworten (Split-Editor)
                    mail_reply_open()
                elif ch in (ord("r"), ord("R")):
                    mail_poll(); MAIL["data"] = None
                elif ch in (ord("z"), ord("Z")):               # z → Zahlen JETZT neu zählen
                    _mail_submit(("counts",), "zähle ordner…",
                                 lambda: _do_refresh_counts(force=True))
                    MAIL["msg"] = "zähle neu…"
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
                elif ch in (ord("z"), ord("Z")):               # z → Zahlen JETZT neu zählen
                    _mail_submit(("counts",), "zähle ordner…",
                                 lambda: _do_refresh_counts(force=True))
                    MAIL["msg"] = "zähle neu…"
                elif ch in (ord("t"), ord("T")):
                    theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
        else:                                  # Normal-Modus: Shortcuts aktiv
            if ch in (ord("q"), ord("Q")):
                break
            elif ch in (ord("t"), ord("T")):   # Theme zyklieren
                theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
            elif ch in (ord("g"), ord("G")):   # Graph-Werkzeug öffnen
                G["active"] = True; G["view"] = "list"; G["msg"] = ""
                G["shown"] = set(); g_load()   # immer in der Übersicht (alle) starten
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

        # Graph-Reminder: ist heute was fällig (und noch nicht weggeklickt), das
        # Nag-Kästchen aufmachen — aber nicht mitten in Tipperei/Overlay/Dialog.
        if not nag_active and not in_text_entry() and not cmd_mode and not help_latched:
            due = [r for r in store.reminders_snapshot()
                   if isinstance(r, dict) and r.get("id") not in nag_dismissed]
            if due:
                nag_active = True
                nag_items = due

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
        if bk.get("cloud"):
            ctxt, cattr = "✓ " + (bk.get("cloud_provider") or ""), C["bright"]
        elif bk.get("cloud_enabled") is False:      # manuell gedrosselt
            ctxt, cattr = "✗ gedrosselt", C["warn"]
        else:
            ctxt, cattr = "✗", C["faint"]
        safe_addstr(top + 2, lx + 2, "CLOUD", C["acc"])
        safe_addstr(top + 2, lx + 9, ctxt, cattr)

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
        #   time   → Symbol auf der 24h-Skala (Zeitpunkt, keine Linie); je
        #            Graph EIN eigenes aus TIME_SYMBOLS (★ als Default/erstes)
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
        # Inhalt der lifestyle-Box: kompakte Überlagerung aller Graphen
        # (geteilte Routine, auch groß im Graph-Werkzeug — siehe draw_overlay).
        draw_overlay(top, rx, life_h, rightw, gs_cache, gv_cache, labeled=False)

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
        if K["active"] and K.get("linput") is not None:
            # Eingabe lebt HIER unten (mehr Platz als die schmale Sidebar-Kopf-
            # zeile): Sidebar neu/umbenennen ODER die Pro-Tag-Uhrzeit einer Spanne.
            prompt = ({"add": "neuer eintrag: ", "rename": "umbenennen: ",
                       "spantime": "zeit (leer=ganztags): "}
                      .get(K["lmode"], "umbenennen: "))
            safe_addstr(input_row, 1, "›", C["acc"])
            shown = (prompt + K["linput"])[-(W - 6):]
            addclip(input_row, 3, shown, W - 6, C["bright"])
            safe_addstr(input_row, 3 + len(shown), "_", C["bright"])
        elif cmd_mode:
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

        # ── Graph-Reminder-Nag (zuletzt → liegt über allem) ───────────────
        if nag_active and nag_items:
            lines = ["heute noch nicht geloggt:"]
            for r in nag_items:
                at = r.get("remind_at") or ""
                lines.append("  • " + str(r.get("name") or r.get("id") or "")
                             + (("  @" + at) if at else ""))
            lines.append("")
            lines.append("g = eintragen · sonst wegklicken")
            nw = min(W - 4, max(26, max(len(s) for s in lines) + 4))
            nh = len(lines) + 2
            nx = max(0, (W - nw) // 2)
            ny = max(0, (H - nh) // 2)
            draw_box(ny, nx, nh, nw, "bitte eintragen", C["warn"])
            for i, s in enumerate(lines):
                addclip(ny + 1 + i, nx + 2, s, nw - 4,
                        C["bright"] if i == 0 else C["faint"])

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
