#!/usr/bin/env python3
# tui/zentrale_tui.py
#
# ════════════════════════════════════════════════════════════════════════
# ZENTRALE — TUI (Terminal)
# ------------------------------------------------------------------------
# "ZENTRALE in klein" OHNE Browser. Rendert das Dashboard direkt im Terminal
# (curses), gegen dasselbe Flask-Backend wie früher die Browser-Fronten:
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
# EINE Ausnahme, und nur auf Anforderung: das Klavier-Werkzeug (Taste 'k')
# lädt beim Öffnen core/tone.py nach (numpy + sounddevice), weil Klang auf dem
# Knoten entstehen MUSS, an dem der Mensch sitzt — über HTTP lässt sich kein
# Lautsprecher bedienen. Fehlt beides, bleibt das Klavier still und
# funktioniert weiter (Noten, Aufnahme, Melodien); die TUI startet unverändert.
#
# KI: die TUI ist die Hauptfront des Assistenten (Taste 'a'), rechnet aber
# selbst nichts — sie spricht nur HTTP: /api/chat (SSE-Stream),
# /api/chat/history, /api/permission_answer (Erlaubnis-Gate), /api/ai/status
# (wer denkt, Kosten). Welcher Kern antwortet, entscheidet das Backend
# (ai_backends.chat_available()). Das lokale Backend von start_tui.sh läuft
# ohne lokale KI (ZENTRALE_LOKALE_KI=aus, ai_backends.lokale_ki_aus()) — es
# spricht nie ein Ollama an, eine Cloud-KI darf es aber nutzen.
#
# Aufbau (seit 06.10.2026): diese Datei ist Einstieg, Daten-Poller (Store),
# Hot Reload, Lebenslauf und die Hauptschleife (run_ui → taste_verteilen /
# bild_zeichnen). Jede Ansicht — Chat, Kalender, Post, Karte, Klavier … — ist
# eine Klasse in tui/ansichten/ und bekommt einen Kontext statt Closure-
# Variablen. Wohin etwas Neues gehört: memory/system/tui_bauplan.md.
#
# Start: scripts/start_tui.sh bzw. der Symlink `zentrale-tui` fährt das
# Backend (ohne lokale KI) hoch und startet dann diese TUI im Vordergrund.
# Standalone gegen ein laufendes Backend:  venv/bin/python tui/zentrale_tui.py
# Selbsttest ohne Terminal:                venv/bin/python tui/zentrale_tui.py --selftest
# ════════════════════════════════════════════════════════════════════════

import os
import sys
import atexit
import json
import time
import threading
import types
import subprocess
import urllib.request
import urllib.error
import urllib.parse

try:                                    # die Ansichten (tui/ansichten/, memory/system/tui_bauplan.md)
    from tui import ansichten
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import ansichten

# Backend-Adresse und HTTP-Zugriff wohnen in ansichten/basis.py — EINE Stelle
# für die TUI und alle Ansichten.
BASE_URL = ansichten.basis.BASE_URL
api_call = ansichten.basis.api_call
venv_python = ansichten.basis.venv_python
PROJEKT = ansichten.basis.PROJEKT
parse_clock, fmt_clock, _num = ansichten.basis.parse_clock, ansichten.basis.fmt_clock, ansichten.basis._num
# Helfer der Ansichten, die selftest() direkt braucht (Werte ohne curses).
graph_last, graph_series = ansichten.graphen.graph_last, ansichten.graphen.graph_series
blockspark = ansichten.graphen.blockspark
bar = ansichten.fokus.bar
fmt_uptime, tele_value = ansichten.technik.fmt_uptime, ansichten.technik.tele_value
TELE_ROWS = ansichten.technik.TELE_ROWS
# Welches Fenster hat den Fokus (Freitext? welche Tastenhilfe?): ansichten/fenster.py
in_text_entry, current_ctx = ansichten.fenster.in_text_entry, ansichten.fenster.current_ctx
LAUF_TICK_MS = ansichten.technik.LAUF_TICK_MS   # Takt der Schleife, während eine Zeile läuft
BEENDEN = ansichten.basis.BEENDEN       # 'q' aus einer Ansicht: Hauptschleife verlassen
STRG_C = 3                              # Strg+C als Zeichen (raw-Modus, run_ui)
fussleiste = ansichten.fussleiste       # die Tastenzeile ganz unten


def _theme_modul():
    """core/theme.py importieren (Pfad einhängen, falls nötig)."""
    core_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    import theme
    return theme


def _load_theme_state():
    """core/theme.py laden und einen ThemeState bauen.

    Bewusst KEIN Fallback auf eine eingebaute Kopie: der Tag/Nacht-Modus darf
    genau eine Implementierung haben. Eine zweite, die einspringt, wenn der
    Import scheitert, wäre wieder der doppelte Zustand, der hier gerade
    abgeschafft wurde — dann lieber ein klarer Fehler beim Start.
    """
    return _theme_modul().ThemeState()

# ── Ist der PC da? (core/pc_status.py — EINE Quelle für alle) ──────────────
# Die TUI hält den Stand warm (alle 15 s, billig: 1 s TCP auf die letzte
# Adresse) und zeigt ihn oben. Skripte und Claude fragen dieselbe Datei über
# `zentrale-pc-status`, statt jeder für sich minutenlang zu suchen.
PEER = {"d": None}


def peer_wach(stop=None, takt=15.0):
    _theme_modul()                       # hängt core/ in sys.path
    try:
        import pc_status
    except Exception:
        return
    while not (stop and stop.is_set()):
        try:
            PEER["d"] = pc_status.pruefen()
        except Exception:
            pass
        if stop:
            stop.wait(takt)
        else:
            time.sleep(takt)


def peer_anzeige(d):
    """('PC ✓', gut?) bzw. ('PC ✗', False); None, solange nichts bekannt ist."""
    if not d:
        return None
    name = "PC" if d.get("peer", "pc") == "pc" else "LAPTOP"
    return (name + (" ✓" if d.get("verbunden") else " ✗"), bool(d.get("verbunden")))


# Dateien öffnet man in einem normalen Terminal via `xdg-open <datei>` — die TUI
# selbst macht das nicht (reine Anzeige).

# Sensor-Beschriftung: (ruhe-text, aktiv-text) — gleiche Sprache wie laptop.html
WARD = {
    "button": ("bereit", "TRIGGER"),
    "light":  ("dunkel", "hell"),
    "motion": ("PIR",    "TRIGGER"),
    "door":   ("zu",     "offen"),
}
SENSOR_ORDER = ["button", "light", "motion", "door"]


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
        self.cycle = {}        # /api/cycle (Zyklus-Vorhersage, nur mit »periode«-Graph)
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
            # Zyklus-Vorhersage nur holen, wenn es den »periode«-Graphen
            # überhaupt gibt — sonst ein Request alle 5 s für ein leeres {}.
            cy = {}
            if any(isinstance(g, dict) and (g.get("name") or "").strip().lower() == "periode"
                   for g in gs):
                try:
                    cy = self._get("/api/cycle") or {}
                except (urllib.error.URLError, OSError, ValueError):
                    cy = {}
            with self._lock:
                self.graphs = gs
                self.graph_vals = gv
                self.reminders = rm if isinstance(rm, list) else []
                self.cycle = cy if isinstance(cy, dict) else {}
        except (urllib.error.URLError, OSError, ValueError):
            pass

    def _poll_projects(self):
        """NUR den fokussierten Projekt-Teilbaum ziehen (FOCUS-Box). Kein
        Fallback auf alle Projekte — die Gesamtübersicht lebt allein in der
        Projektansicht (Taste 'f', holt /api/projects selbst). Als Liste
        gehalten ([node] oder []), damit die Box-Render-Schleife unverändert
        läuft."""
        try:
            foc = self._get("/api/projects/focused")
            with self._lock:
                self.projects = [foc] if isinstance(foc, dict) else []
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

    def cycle_snapshot(self):
        """Zyklus-Vorhersage (/api/cycle) für die Tönung in der lifestyle-Box.
        {} = kein »periode«-Graph / noch keine Werte."""
        with self._lock:
            return dict(self.cycle)

    def reminders_snapshot(self):
        """Heute fällige Graph-Reminder (id/name/remind_at) für den TUI-Nag."""
        with self._lock:
            return list(self.reminders)

    def projects_snapshot(self):
        """Der fokussierte Projekt-Teilbaum als Liste ([node] oder []) für die
        FOCUS-Box — NICHT alle Projekte (die Übersicht lebt in der Projektansicht)."""
        with self._lock:
            return [dict(p) for p in self.projects if isinstance(p, dict)]

    def backends_snapshot(self):
        """AI-Backend-Status ({local,cloud,cloud_provider,any}) für die EXTERNAL-Box."""
        with self._lock:
            return dict(self.backends)


# ── Hilfsfunktionen (UI-unabhängig, testbar) ───────────────────────────────

# Mindestgröße fürs Rendern: darunter passt das Dashboard-Layout nicht und wir
# zeigen nur den "zu klein"-Hinweis.
MIN_LINES = 14
MIN_COLS = 60


def terminal_too_small(h, w):
    """True, wenn das Terminal kleiner als die Mindest-Renderfläche ist."""
    return h < MIN_LINES or w < MIN_COLS


# Der Lauf-WUNSCH (an/aus) gehört der Hauptschleife (Taste 's', /lauf) und
# überlebt den Neustart in einer Datei; wie die Laufschrift läuft, steht in
# tui/ansichten/technik.py (lauf_schritt, lauf_ausschnitt).
def lauf_datei():
    """Pfad des Lauf-Wunsches. ZENTRALE_LAUF_FILE sticht (Tests, fremde Knoten)."""
    return (os.environ.get("ZENTRALE_LAUF_FILE")
            or os.path.expanduser("~/.config/zentrale/stdout_lauf"))


def lauf_lesen(default=True):
    """Ein Wort aus der Datei → an/aus. Fehlt sie, gilt `default` (an)."""
    return schalter_lesen(lauf_datei(), default)


def lauf_schreiben(an):
    """Wunsch merken (siehe schalter_schreiben)."""
    return schalter_schreiben(lauf_datei(), an)


def schalter_lesen(pfad, default):
    """Ein Wort aus `pfad` → an/aus. Fehlt die Datei oder ist sie Müll,
    gilt `default`."""
    try:
        with open(pfad, encoding="utf-8") as f:
            wort = f.read().strip().lower()
    except OSError:
        return default
    if wort in ("an", "on", "1", "ja", "true"):
        return True
    if wort in ("aus", "off", "0", "nein", "false"):
        return False
    return default


def schalter_schreiben(pfad, an):
    """Wunsch merken. Nutzt denselben Riegel wie das Theme: eine Arbeitskopie
    (Worktree) fasst Sashas laufende Konfiguration NICHT an."""
    try:
        darf, _grund = _theme_modul().darf_schreiben(pfad)
    except Exception:                      # noqa: BLE001 — Merken ist Kür
        darf = True
    if not darf:
        return False
    try:
        os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
        tmp = pfad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("an\n" if an else "aus\n")
        os.replace(tmp, pfad)              # atomar, wie die Theme-Datei
        return True
    except OSError:
        return False


# ── Selbsttest: ein Snapshot als Text, ohne curses (kein TTY nötig) ─────────
def selftest():
    store = Store()
    print("ZENTRALE TUI selftest → %s" % BASE_URL)
    ok = store.poll_once()
    state, metrics, _ = store.snapshot()
    print("  backend erreichbar :", ok)
    if not ok:
        print("  (Backend nicht erreichbar — läuft `zentrale`?)")
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
    foc = store._get("/api/projects/focused")
    print("  projekte (übersicht):", [p.get("name") for p in pr] or "—",
          "· fokus:", (foc.get("name") if isinstance(foc, dict) else "—"))
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


# ── Neustart (/reboot): das Fenster beendet sich, das Skript baut neu auf ───
#
# Ein Neustart, den die TUI selbst macht, koennte nur die HAELFTE: das Backend
# gehoert ihr nicht — es laeuft entweder als Benutzer-Dienst
# (zentrale-kern.service) oder als Kind von start_tui.sh. Wer beides neu
# hochziehen will, muss dort stehen, wo beides bekannt ist: im Start-Skript.
#
# Deshalb ist /reboot hier nur ein SIGNAL: die TUI endet mit Code 42, und
# scripts/start_tui.sh (das in einer Schleife laeuft) startet Backend und
# Fenster neu — im selben Terminal, mit frisch geladenem Code.
#
# Ohne dieses Skript (TUI standalone gegen ein fremdes Backend) gaebe es
# niemanden, der wieder aufbaut: dann waere /reboot ein Beenden mit Ansage
# statt eines Neustarts. Darum setzt start_tui.sh ZENTRALE_TUI_SUPERVISED=1,
# und ohne die Variable sagt der Befehl schlicht, dass er hier nicht geht.
NEUSTART_CODE = 42
NEUSTART = {"an": False}       # von run_ui gesetzt, von main() ausgewertet


def neustart_moeglich():
    """Laeuft diese TUI unter start_tui.sh (dem Einzigen, der neu aufbauen kann)?"""
    return os.environ.get("ZENTRALE_TUI_SUPERVISED") == "1"


# ── Weglegen statt beenden: 'q' unter der Systemeinheit ─────────────────────
#
# Sasha, 18.09.2026: „zentrale fängt erst an hochzufahren bzw 'abgleich mit
# pc' und blumenwind zu zeigen wenn man das erste mal sie öffnet mit cmd z,
# ich will dass sie von anfang an wach ist damit ich nicht warten muss."
#
# Gemessen: das Fenster ging beim Anmelden auf und lief — bis 'q'. Denn 'q'
# BEENDETE die TUI, das Terminal schloss sich mit ihr, und der naechste
# $mod+z musste alles kalt hochziehen: Abgleich mit dem PC, Blumenwind,
# Python-Start. Der Kern-Dienst blieb zwar warm (das war der Sinn der
# Systemeinheit), aber das FENSTER nicht.
#
# Deshalb legt 'q' jetzt nur noch weg: die TUI ruft `zentrale-fenster
# --weglegen` (Fenster ins Scratchpad) und baut run_ui sofort wieder auf —
# versteckt, mit warmem Prozess und laufendem Poller. $mod+z holt sie dann
# ohne Wartezeit zurueck. Fuer den Benutzer sieht 'q' aus wie vorher (Fenster
# weg), nur der naechste Blick ist sofort da.
#
# Wirklich beendet wird nur noch mit /quit oder Ctrl-C (ENDE["echt"]). Und
# ohne Systemeinheit — TUI in einem gewoehnlichen Terminal, kein fokussiertes
# ZENTRALE-Fenster in i3 — gibt `--weglegen` 1 zurueck, und 'q' beendet wie
# frueher. Nichts haengt dann in einem unsichtbaren Zustand fest.
ENDE = {"echt": False}          # von run_ui gesetzt (/quit), von main() gelesen


def weglegen_statt_beenden():
    """Nach einem sauberen Ende von run_ui: Fenster weglegen und weiterlaufen?"""
    if ENDE["echt"] or NEUSTART["an"] or not neustart_moeglich():
        return False
    try:
        r = subprocess.run(["zentrale-fenster", "--weglegen"], timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def fenster_zuklappen():
    """Esc auf der Startseite (Sasha, 04.10.2026): ZENTRALE zuklappen wie
    $mod+z — das Fenster geht ins Scratchpad, die TUI läuft weiter, Rad und
    Galaxie bleiben stehen. Nur unter der Systemeinheit (start_tui.sh); in
    einem gewöhnlichen Terminal tut Esc nichts, statt zu beenden. Läuft im
    Hintergrund, damit die Oberfläche nicht auf i3 wartet."""
    if not neustart_moeglich():
        return False

    def los():
        try:
            subprocess.run(["zentrale-fenster", "--weglegen"], timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass
    threading.Thread(target=los, daemon=True).start()
    return True


# ── Lebenslauf: warum ging sie zu? ───────────────────────────────────────────
#
# 02.10.2026: ZENTRALE ging mitten in der Arbeit einfach zu, ohne jede Spur.
# Das Terminal schliesst sich mit der TUI (Meldungen weg), das Crash-Log lag in
# /tmp und wurde von jeder Test-TUI beim Start geloescht, und ein SIGTERM
# hinterliess gar nichts. Herausgekommen ist es nur ueber die Luecke in den
# Backend-Abfragen und einen Updater-Test, der jede TUI der Maschine killte.
#
# Deshalb jetzt EINE Datei, die nie geloescht wird und jeden Start und jedes
# Ende mit Grund festhaelt — bei einem Signal samt den Prozessen, die kurz
# vorher gestartet wurden (der Absender ist fast immer darunter).
LEBENSLAUF = (os.environ.get("ZENTRALE_TUI_LOG")
              or os.path.expanduser("~/.local/state/zentrale/tui.log"))
LEBENSLAUF_MAX = 512 * 1024


def lebenslauf(text, pfad=None):
    """Eine Zeile (oder ein Block) ins Lebenslauf-Log. Wirft nie."""
    pfad = pfad or LEBENSLAUF
    try:
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        try:
            if os.path.getsize(pfad) > LEBENSLAUF_MAX:
                os.replace(pfad, pfad + ".1")
        except OSError:
            pass
        with open(pfad, "a", encoding="utf-8") as f:
            f.write("%s  pid %d  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                          os.getpid(), text.rstrip("\n")))
    except OSError:
        pass


def frische_prozesse(sekunden=30, proc="/proc"):
    """Prozesse, die in den letzten `sekunden` gestartet wurden -> [(pid, cmd)].

    Ein Signal verraet in Python seinen Absender nicht. Wer gerade eben
    gestartet wurde, ist aber fast immer der Taeter (ein Testlauf, ein
    Updater, ein Skript) — die Liste macht ihn im Log sichtbar."""
    aus = []
    try:
        hz = os.sysconf("SC_CLK_TCK")
        with open(os.path.join(proc, "uptime")) as f:
            jetzt = float(f.read().split()[0])
        for name in os.listdir(proc):
            if not name.isdigit() or int(name) == os.getpid():
                continue
            try:
                with open(os.path.join(proc, name, "stat")) as f:
                    start = int(f.read().rsplit(")", 1)[1].split()[19]) / hz
                if jetzt - start > sekunden:
                    continue
                with open(os.path.join(proc, name, "cmdline"), "rb") as f:
                    cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
                if cmd:
                    aus.append((int(name), cmd[:200]))
            except (OSError, ValueError, IndexError):
                continue
    except (OSError, ValueError):
        pass
    return sorted(aus)


class Signalende(BaseException):
    """SIGTERM/SIGHUP: sauber raus (curses aufraeumen), mit Grund im Log."""
    def __init__(self, signum):
        super().__init__(signum)
        self.signum = signum


def _signal_handler(signum, _frame):
    import signal as _s
    name = _s.Signals(signum).name
    frisch = frische_prozesse()
    lebenslauf("SIGNAL %s — kurz vorher gestartet:%s" % (
        name, "".join("\n      %d  %s" % p for p in frisch) or " (nichts)"))
    raise Signalende(signum)


# ── Hot Reload: neuer Code ohne Fenster-Neustart ─────────────────────────────
#
# Sasha, 02.10.2026: „ein hot reload gibt es bei zentrale gar nich wäre aber
# auch mal schlau". Die TUI beobachtet ihre eigenen Quelldateien (tui/*.py);
# ändern sie sich (Merge nach main, Edit), ersetzt sie sich per exec durch
# sich selbst — gleiches Terminal, gleiche pid, das Fenster bleibt stehen.
# Vorher wird der neue Code kompiliert: ist er kaputt, bleibt der alte laufen
# und unten steht, wo es hakt. Nie mitten im Tippen. Das Backend hat seit
# 04.10.2026 seinen eigenen Hot Reload (core/hot_reload.py); /reboot bleibt
# für den harten Fall.
RELOAD = {"an": False}
OFFEN = {"merken": None}      # run_ui hängt ein, was beim Hot Reload offen war
TUI_DIR = os.path.dirname(os.path.abspath(__file__))


def code_dateien(ordner=TUI_DIR):
    """Alle .py unter tui/ — seit 06.10.2026 auch in Unterordnern: die
    Ansichten liegen in tui/ansichten/, und ein Merge, der nur eine Ansicht
    ändert, muss genauso neu laden wie einer an zentrale_tui.py."""
    aus = []
    for wurzel, unter, namen in os.walk(ordner):
        unter[:] = [d for d in unter if d != "__pycache__"]
        aus.extend(os.path.join(wurzel, n) for n in namen if n.endswith(".py"))
    return sorted(aus)


def code_stand(dateien):
    """Fingerabdruck des Codes: (pfad, mtime_ns, größe) je Datei."""
    stand = []
    for p in dateien:
        try:
            st = os.stat(p)
            stand.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            stand.append((p, None, None))
    return tuple(stand)


def code_fehler(dateien):
    """None, wenn alles kompiliert — sonst 'datei:zeile: meldung'."""
    for p in dateien:
        try:
            with open(p, encoding="utf-8") as f:
                compile(f.read(), p, "exec")
        except SyntaxError as e:
            return "%s:%s: %s" % (os.path.basename(p), e.lineno, e.msg)
        except (OSError, ValueError) as e:
            return "%s: %s" % (os.path.basename(p), e)
    return None


# ── Zustand der Startseite (App-Rad, Galaxie, Technik-Rad) ─────────────────
# Geometrie und Zeichnen wohnen seit 06.10.2026 in tui/ansichten/startseite.py.
# Der ZUSTAND bleibt hier auf Modulebene: er überlebt einen run_ui-Neustart
# (Weglegen, abgefangener Fehler), und main() schreibt ihn beim Hot Reload in
# die Umgebung (ZENTRALE_TUI_RAD/META), damit das Rad nach exec dasteht, wo es war.
RAD_APPS, TECH_APPS = ansichten.startseite.RAD_APPS, ansichten.startseite.TECH_APPS
meta_taste, rad_anstoss = ansichten.startseite.meta_taste, ansichten.startseite.rad_anstoss
rad_index = ansichten.startseite.rad_index


def _rad_start():
    """Nach einem Hot Reload steht das Rad, wo es war."""
    try:
        return int(os.environ.get("ZENTRALE_TUI_RAD", "0"))
    except ValueError:
        return 0


RAD = {"sel": _rad_start(), "pos": float(_rad_start()),  # sel = Ziel, pos = wo das Rad gerade steht
       "offen": {}, "offen_seit": {},     # je Symbol-App: 0 zu … 1 offen, seit wann ganz offen
       "takt": 0.0, "schnell": False}     # letzter Frame; klappt gerade etwas (→ schneller Takt)


def _meta_start():
    """Nach einem Hot Reload: Galaxie-Stellung, drin oder nicht, Technik-Stellung."""
    try:
        fokus, drin, sel = (int(t) for t in
                            os.environ.get("ZENTRALE_TUI_META", "0,0,0").split(","))
    except ValueError:
        return 0, False, 0
    return (1 if fokus == 1 else 0), bool(drin), sel


_M0 = _meta_start()
META = {"gsel": _M0[0], "gpos": float(_M0[0]),   # Galaxie: Ziel + wo sie gerade steht
        "fahrt": None,          # laufende Drehung: (von, nach, startzeit) oder None
        "fokus": _M0[0],        # welches System gewählt ist: 0 = Apps, 1 = Technik
        }
TRAD = {"sel": _M0[2], "pos": float(_M0[2])}   # Technik-Rad, wie RAD


def dashboard_datei():
    """Pfad des Dashboard-Wunsches. ZENTRALE_DASHBOARD_FILE sticht (Tests)."""
    return (os.environ.get("ZENTRALE_DASHBOARD_FILE")
            or os.path.expanduser("~/.config/zentrale/dashboard"))


# ── curses-UI ───────────────────────────────────────────────────────────────
def befehl_ausfuehren(res, bz, store, LAUF, DASH, TECH, app_start):
    """Einen Befehl der Befehlszeile ausführen (Ergebnis von parse_command).
    -> True, wenn die Hauptschleife enden soll (/quit, /reload, /reboot).

    Bis 06.10.2026 ein Zweig mitten in der Hauptschleife von run_ui. Hier
    statt in ansichten/befehle.py, weil ein Befehl alles anfassen darf:
    Hot Reload, Neustart, Backend-Schalter, Laufschrift, Dashboard, Tutor —
    die Befehlszeile selbst kennt davon nichts."""
    if res == "QUIT":
        ENDE["echt"] = True       # wirklich beenden, nicht nur weglegen
        return True
    if res == "RELOAD":
        fehler = code_fehler(code_dateien())
        if fehler:
            bz.cmd_msg = "neuer code kaputt, bleibe beim alten: " + fehler
        else:
            RELOAD["an"] = True
            return True
    if res == "REBOOT":
        # Nur das Signal setzen und raus — neu aufgebaut wird von
        # start_tui.sh (siehe NEUSTART_CODE). Ohne Skript drumherum
        # waere das ein Beenden, kein Neustart: dann lieber sagen.
        if neustart_moeglich():
            NEUSTART["an"] = True
            return True
        bz.cmd_msg = ("neustart geht nur ueber zentrale-tui "
                      "(dieses fenster wurde anders gestartet)")
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
            bz.cmd_msg = "cloud " + ("AN" if (st or {}).get("cloud_enabled") else "GEDROSSELT")
        except (urllib.error.URLError, OSError, ValueError):
            bz.cmd_msg = "cloud-schalter fehlgeschlagen"
    if res in ("LOCAL_ON", "LOCAL_OFF", "LOCAL_TOGGLE"):
        # Lokal-Kill-Switch umlegen (dieselbe Quelle wie /cloud, nur
        # local_enabled). Danach EXTERNAL sofort frisch.
        try:
            if res == "LOCAL_TOGGLE":
                on = not store.backends_snapshot().get("local_enabled", True)
            else:
                on = (res == "LOCAL_ON")
            st = api_call("/api/ai/backends", "POST", {"local_enabled": on})
            store._poll_backends()
            bz.cmd_msg = "lokale ki " + ("AN" if (st or {}).get("local_enabled") else "GEDROSSELT")
        except (urllib.error.URLError, OSError, ValueError):
            bz.cmd_msg = "lokal-schalter fehlgeschlagen"
    if res in ("LAUF_ON", "LAUF_OFF", "LAUF_TOGGLE"):
        LAUF["an"] = (not LAUF["an"]) if res == "LAUF_TOGGLE" else (res == "LAUF_ON")
        lauf_schreiben(LAUF["an"])
        bz.cmd_msg = "stdout-lauf " + ("an" if LAUF["an"] else "aus")
    if res in ("DASH_ON", "DASH_OFF", "DASH_TOGGLE"):
        DASH["an"] = (not DASH["an"]) if res == "DASH_TOGGLE" else (res == "DASH_ON")
        schalter_schreiben(dashboard_datei(), DASH["an"])
        TECH["active"] = False     # gibt es im alten Layout nicht
        bz.cmd_msg = "dashboard " + ("an (3 spalten)" if DASH["an"] else "aus (meta-rad)")
    if res == "TUTOR_OPEN":
        # Wie Taste 'u': das Zimmer der Tutor-App öffnen (seit 2026-10-09
        # eine eigene App; das Text-Panel gibt es nicht mehr).
        app_start.tutor_oeffnen()
    return False


def taste_verteilen(u, ch):
    """Eine Taste an das Fenster mit dem Fokus (früher die erste Hälfte der
    Hauptschleife von run_ui). -> BEENDEN, wenn die TUI enden soll."""
    import curses
    AI, DASH, ELEK, G, K, L, LAUF, M = u.AI, u.DASH, u.ELEK, u.G, u.K, u.L, u.LAUF, u.M
    MAIL, NOTE, PIANO, TECH, bz = u.MAIL, u.NOTE, u.PIANO, u.TECH, u.bz
    chat, erinnerung, fokus, graphen = u.chat, u.erinnerung, u.fokus, u.graphen
    kalender, karte, klavier, notizen = u.kalender, u.karte, u.klavier, u.notizen
    post, app_start, store, z = u.post, u.app_start, u.store, u.z
    if ch == STRG_C:
        # Strg+C kommt seit 07.10.2026 als Zeichen (raw-Modus, siehe run_ui).
        # Im Chat stoppt es die Antwort und beendet NIE die TUI; überall
        # sonst bleibt es, was es war: sauber beenden (main() fängt das
        # KeyboardInterrupt wie früher das echte SIGINT).
        if current_ctx(z) == "ai" and not (bz.cmd_mode or bz.help_latched
                                           or erinnerung.nag_active):
            chat.taste(ch)
            return None
        raise KeyboardInterrupt
    if erinnerung.nag_active:              # Reminder-Kästchen offen: jede Taste klickt weg
        erinnerung.taste(ch)
    elif bz.help_latched:
        if ch != -1:                       # jede Taste schließt die Hilfe wieder
            bz.help_latched = False
    elif bz.cmd_mode:
        # Tippen, Esc, Backspace erledigt die Befehlszeile; bei Enter
        # kommt das Ergebnis von parse_command zurück, befehl_ausfuehren
        # setzt es um (Backend, Fenster, Neustart — siehe dort).
        res = bz.taste(ch)
        if res is not None:
            if befehl_ausfuehren(res, bz, store, LAUF, DASH, TECH, app_start):
                return BEENDEN
    elif ch == ord("/") and not in_text_entry(z):
        # '/' greift JETZT in jedem Fenster (nicht nur Home): blendet die
        # Shortcuts des fokussierten Fensters ein. In Freitext-Feldern bleibt
        # '/' ein Zeichen (siehe in_text_entry), darum hier das Guard.
        bz.oeffnen()
    elif G["active"]:                      # Graph-Werkzeug hat den Fokus
        if graphen.taste(ch) == BEENDEN:
            return BEENDEN
    elif L["active"]:                      # Listen-Werkzeug hat den Fokus
        if fokus.taste(ch) == BEENDEN:
            return BEENDEN
    elif M["active"]:                      # Karte hat den Fokus
        if karte.taste(ch) == BEENDEN:
            return BEENDEN
    elif K["active"]:                      # Kalender hat den Fokus
        if kalender.taste(ch) == BEENDEN:
            return BEENDEN
    elif MAIL["active"] and MAIL["replying"]:   # Antwort-Editor hat den Fokus
        post.taste_antwort(ch)
    elif MAIL["active"]:                   # Post/Mail-Panel hat den Fokus
        if post.taste(ch) == BEENDEN:
            return BEENDEN
    elif NOTE["active"]:                   # Notiz-Werkzeug hat den Fokus
        if notizen.taste(ch) == BEENDEN:
            return BEENDEN
    elif ELEK["active"]:                   # Elektronik-Bereich hat den Fokus
        if ch == 27:
            ELEK["active"] = False
    elif TECH["active"]:                   # Technik-Ansicht hat den Fokus
        if ch == 27:
            TECH["active"] = False
    elif PIANO["active"]:                  # Klavier hat den Fokus
        klavier.taste(ch)
    elif AI["active"]:                     # KI-Chat hat den Fokus
        chat.taste(ch)
    elif u.DESK["active"]:                 # Desk View hat den Fokus (2026-10-09)
        u.desk.taste(ch)
    else:                                  # Startseite: das Rad
        # Seit 02.10.2026 keine Buchstaben-Shortcuts mehr (Sasha): ←/→
        # dreht, enter öffnet die App vorn, space die KI. Theme, Laufschrift
        # und Beenden gehen über die Befehlszeile (/theme, /lauf, /quit),
        # Weglegen über Cmd+z. `taste` übersetzt die Wahl in den alten
        # Buchstaben, damit die Öffnen-Zweige unten unverändert bleiben.
        taste = None
        if not DASH["an"]:
            # Galaxie (seit 03.10.2026): ←/→ dreht das gewählte Rad,
            # alt+←/→ wechselt das Rad (dieselbe Alt-Erkennung wie die Karte).
            was = {curses.KEY_LEFT: "links", curses.KEY_RIGHT: "rechts",
                   10: "enter", 13: "enter", curses.KEY_ENTER: "enter"}.get(ch)
            if was is None:
                alt = karte.m_alt_arrow(ch)
                if alt == "esc":                   # Esc allein: ZENTRALE zuklappen
                    fenster_zuklappen()
                was = {"left": "alt_links", "right": "alt_rechts"}.get(alt)
            if ch == ord(" "):
                taste = "a"
            elif was:
                wahl = meta_taste(META, RAD, TRAD, was)
                if wahl and wahl[0] == "app":
                    taste = wahl[1]
                elif wahl:
                    TECH["active"] = True; TECH["view"] = wahl[1]
        elif ch == 27:                         # altes Dashboard: Esc klappt auch zu
            fenster_zuklappen()
        elif ch == curses.KEY_LEFT:
            RAD["sel"] -= 1; rad_anstoss(RAD, -1)
        elif ch == curses.KEY_RIGHT:
            RAD["sel"] += 1; rad_anstoss(RAD, 1)
        elif ch == ord(" "):
            taste = "a"
        elif ch in (10, 13, curses.KEY_ENTER):
            taste = RAD_APPS[rad_index(RAD["sel"])][0]
        ch = ord(taste) if taste else -1
        if ch in (ord("g"), ord("G")):     # Graph-Werkzeug öffnen
            graphen.oeffnen()
        elif ch in (ord("m"), ord("M")):   # Karte öffnen
            karte.oeffnen()
        elif ch in (ord("c"), ord("C")):   # Kalender öffnen
            kalender.oeffnen()
        elif ch in (ord("p"), ord("P")):   # Post/Mail-Panel öffnen (Ebene Kategorien)
            post.oeffnen()
        elif ch in (ord("a"), ord("A")):   # KI-Chat öffnen (Thin-Client übers PC-Hirn)
            chat.oeffnen()
        elif ch in (ord("u"), ord("U")):   # 'u' öffnet das Zimmer der Tutor-App (eigenes Fenster)
            if os.environ.get("ZENTRALE_ROOM_PARENT"):
                # Die TUI wurde AUS dem Zimmer heraus geöffnet (Wand-Kiosk,
                # room.py Alt+Z): das Zimmer liegt darunter und läuft weiter.
                # 'u' heißt hier »zurück ins Zimmer« — TUI zu, kein zweites
                # Zimmer, das sich mit dem ersten ums Mikro streitet.
                return BEENDEN
            app_start.tutor_oeffnen()
        elif ch in (ord("n"), ord("N")):   # Notiz-Werkzeug öffnen (direkt in eine Notiz)
            notizen.oeffnen()
        elif ch in (ord("k"), ord("K")):   # Klavier öffnen (wie im Browser: k)
            klavier.oeffnen()
        elif ch in (ord("e"), ord("E")):   # Elektronik-Bereich (noch leer)
            ELEK["active"] = True
        elif ch in (ord("f"), ord("F")):   # Fokus-Werkzeug öffnen (primäre Taste)
            fokus.oeffnen()
        elif ch in (ord("d"), ord("D")):   # Desk View: Auswahl der Desks (2026-10-09)
            u.desk.oeffnen()
        # '/' wird global oben abgefangen (greift in JEDEM Fenster), darum
        # hier kein eigener Zweig mehr.


def bild_zeichnen(u):
    """Ein Bild: Daten holen, Kopf, Spalten, Mitte, Befehlszeile, Fuß,
    Reminder (früher die zweite Hälfte der Hauptschleife von run_ui)."""
    import curses
    AI, C, DASH, ELEK, G, K, L, LAUF = u.AI, u.C, u.DASH, u.ELEK, u.G, u.K, u.L, u.LAUF
    M, MAIL, NOTE, PIANO, PIX, TECH = u.M, u.MAIL, u.NOTE, u.PIANO, u.PIX, u.TECH
    addclip, bz, chat, dashboard = u.addclip, u.bz, u.chat, u.dashboard
    draw_box, erinnerung, fokus, graphen = u.draw_box, u.erinnerung, u.fokus, u.graphen
    kalender, karte, klavier, notizen = u.kalender, u.karte, u.klavier, u.notizen
    post, safe_addstr = u.post, u.safe_addstr
    startseite, stdscr, store, technik, z = u.startseite, u.stdscr, u.store, u.technik, u.z
    # Weiche Kamerafahrt zum fokussierten Land (eine Ease-Stufe pro Frame).
    if M["active"] and M.get("anim"):
        karte.m_anim_step()

    state, metrics, connected = store.snapshot()
    gs_cache, gv_cache = store.graphs_snapshot()
    cyc_cache = store.cycle_snapshot()      # Zyklus-Tönung der lifestyle-Box
    # Nur der fokussierte Teilbaum ([node] oder []); der Store zieht bereits
    # /api/projects/focused. Kein Fallback auf alle Projekte — die volle
    # Übersicht gibt es allein in der Projektansicht (Taste 'f').
    proj_cache = store.projects_snapshot()

    # Graph-Reminder: ist heute was fällig (und noch nicht weggeklickt), das
    # Nag-Kästchen aufmachen — aber nicht mitten in Tipperei/Overlay/Dialog.
    if (not erinnerung.nag_active and not in_text_entry(z) and not bz.cmd_mode
            and not bz.help_latched):
        erinnerung.pruefen(store)

    H, W = stdscr.getmaxyx()
    stdscr.erase()
    # Pixel-Farbpaare: zu Beginn des Bildes leeren, sobald das Budget halb
    # verbraucht ist — ein Bild braucht höchstens ~70 je Symbol, so läuft es
    # nie MITTEN im Bild über. Vorher wurde nur in der Bernsteinleiste
    # geleert; seit alle Apps animierte Symbole haben, lief es auf der
    # Startseite voll und alles Neue fiel auf Bernstein-Orange zurück.
    if PIX["voll"] or len(PIX["pairs"]) > (PIX["top"] - PIX["base"]) // 2:
        PIX["pairs"].clear(); PIX["voll"] = False

    if terminal_too_small(H, W):
        safe_addstr(0, 0, "Terminal zu klein (min 60x14).", C["warn"])
        safe_addstr(1, 0, "q = quit", C["dim"])
        stdscr.refresh()
        return

    # ── Header ──────────────────────────────────────────────────────
    safe_addstr(0, 1, "ZEN", C["bright"] | curses.A_REVERSE)
    safe_addstr(0, 4, "TRALE", C["acc"])
    safe_addstr(0, 11, "tui", C["dim"])

    nets = state.get("internet_logs", []) or []
    if not isinstance(nets, list):
        nets = []
    if nets:
        net_txt, net_attr = "TRAFFIC !", C["warn"]
    else:
        net_txt, net_attr = "OFFLINE ✓", C["acc"]
    clock = time.strftime("%H:%M:%S")
    up = fmt_uptime(state.get("uptime_s"))
    if DASH["an"]:
        right = "NET %s   UP %s   %s" % (net_txt, up, clock)
        safe_addstr(0, W - len(right) - 1, "NET ", C["dim"])
        safe_addstr(0, W - len(right) - 1 + 4, net_txt, net_attr)
        safe_addstr(0, W - len(right) - 1 + 4 + len(net_txt), "   UP %s   %s" % (up, clock), C["dim"])
    else:                             # Meta-Rad: NET/UP stehen beim Technik-Rad
        right = clock
        safe_addstr(0, W - len(right) - 1, clock, C["dim"])
    if not connected:
        safe_addstr(0, 26, "[backend ?]", C["warn"] | curses.A_BLINK)
    pa = peer_anzeige(PEER["d"])
    if pa:
        safe_addstr(0, W - len(right) - 1 - len(pa[0]) - 3, pa[0],
                    C["acc"] if pa[1] else C["dim"])
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
    if not DASH["an"]:
        # Meta-Rad: keine Seitenspalten mehr — eine offene App hat die
        # ganze Breite, die Startseite teilt sich selbst auf.
        leftw = rightw = 0
    elif MAIL["active"] and MAIL["replying"]:
        leftw = max(16, int(W * 0.16))
        rightw = max(16, int(W * 0.16))
    else:
        leftw = max(24, int(W * 0.28))
        rightw = max(20, int(W * 0.22))
    midw = W - leftw - rightw
    lx, mx, rx = 0, leftw, leftw + midw

    # ── LINKS: telemetrie / stdout (nur altes Dashboard) ───────────
    # (Sensoren-Panel entfernt 2026-06: kein echter Sensor angeschlossen.
    #  /api/state.sensors wird weiter gepollt, nur nicht mehr gezeichnet —
    #  Box zum Wiederanzeigen aus der git-History zurückholen.)
    laeuft_jetzt = False
    if DASH["an"]:
        ext_h = 4
        technik.draw_external(top, lx, leftw, store.backends_snapshot())
        tele_h = technik.draw_telemetrie(top + ext_h, lx, leftw, metrics)
        std_h = body_h - ext_h - tele_h
        if std_h >= 3:
            laeuft_jetzt = technik.draw_stdout(top + ext_h + tele_h, lx, std_h, leftw,
                                       state.get("logs", []) or [])

    if not AI["active"]:
        AI["auge_t0"] = None                       # nächstes Öffnen: Lider gehen neu auf

    # ── MITTE: Graph-Werkzeug / Karte (oder Einladung, sie zu öffnen) ──
    if G["active"]:
        draw_box(top, mx, body_h, midw, "graph-werkzeug")
        graphen.draw_graph_tool(top, mx, body_h, midw, gv_cache)
    elif L["active"]:
        draw_box(top, mx, body_h, midw, "fokus")
        fokus.draw_list_tool(top, mx, body_h, midw)
    elif M["active"]:
        draw_box(top, mx, body_h, midw, "karte · welt")
        karte.draw_map(top, mx, body_h, midw)
    elif K["active"]:
        draw_box(top, mx, body_h, midw, "kalender")
        kalender.draw_calendar(top, mx, body_h, midw)
    elif MAIL["active"] and MAIL["replying"]:
        post.draw_reply(top, mx, body_h, midw)
    elif MAIL["active"]:
        draw_box(top, mx, body_h, midw, "post · mail")
        post.draw_mail(top, mx, body_h, midw)
    elif AI["active"]:
        draw_box(top, mx, body_h, midw, chat.ai_titel(midw - 6))
        chat.draw_ai(top, mx, body_h, midw)
    elif NOTE["active"]:
        draw_box(top, mx, body_h, midw, "notiz" if NOTE["view"] == "edit" else "notizen")
        notizen.draw_note_tool(top, mx, body_h, midw)
    elif PIANO["active"]:
        draw_box(top, mx, body_h, midw, "klavier")
        klavier.draw_piano_tool(top, mx, body_h, midw)
    elif ELEK["active"]:
        draw_box(top, mx, body_h, midw, "elektronik")
        leer = "hier entsteht der elektronik-bereich"
        addclip(top + body_h // 2, mx + max(2, (midw - len(leer)) // 2), leer,
                midw - 4, C["faint"])
        addclip(top + body_h - 2, mx + 2, "esc zurück zum rad", midw - 4, C["faint"])
    elif u.DESK["active"]:
        draw_box(top, mx, body_h, midw, u.desk.titel())
        u.desk.draw_desk(top, mx, body_h, midw)
    elif TECH["active"]:
        draw_box(top, mx, body_h, midw, "technik · " + TECH["view"])
        laeuft_jetzt = technik.draw_tech(top, mx, body_h, midw, state, metrics, nets) or laeuft_jetzt
    elif not DASH["an"]:
        # ── Startseite: die Galaxie (seit 03.10.2026) ─────────────
        # EINE Fläche. Zwei Sonnensysteme (Apps, Technik) auf einer
        # riesigen Bahn — im Ausschnitt nur ein flacher Bogen, die
        # beiden liegen praktisch nebeneinander. ✦ = Sonne des Systems,
        # GROSS = gewählt, ● = man ist drin.
        laeuft_jetzt = (startseite.zeichne_galaxie(top, body_h, W, up, nets, state)
                        or laeuft_jetzt)
    else:
        # ── Startseite: das Rad ───────────────────────────────────
        # Bis 02.10.2026 stand hier der KI-Ring (ring_zeilen, archiviert:
        # memory/archive/tui_ki_ring.md) mit der
        # Tasten-Leiste unten. Jetzt ein Rad zum Durchdrehen, bewusst
        # UNTER der Mitte: der Platz darüber ist für das, was ZENTRALE
        # künftig von sich aus zeigt (kommt Stück für Stück).
        draw_box(top, mx, body_h, midw, "zentrale")
        startseite.draw_rad(top, body_h, mx, midw, [a[1] for a in RAD_APPS], RAD, symbole_an=True)

    # Zappelt gerade wirklich etwas? Nur dann tickt die Schleife schneller
    # (siehe oben) — ein breites Fenster bleibt bei den ruhigen 250 ms.
    LAUF["laeuft"] = laeuft_jetzt

    if DASH["an"]:
        dashboard.zeichne_rechts(top, rx, body_h, rightw, gs_cache, gv_cache, cyc_cache,
                                 proj_cache, nets)

    # ── Befehls-Overlay (klappt über den Body nach oben auf) ──────────
    if bz.cmd_mode or bz.help_latched:
        bz.zeichne_overlay(current_ctx(z), top, bot, W)

    # ── Trennlinie + Befehlszeile (›) ─────────────────────────────────
    safe_addstr(sep_row, 0, "─" * W, C["faint"])
    bz.zeichne_zeile(input_row, W, erreichbar=not in_text_entry(z))

    # ── Fußleiste: NUR die Tasten, die im Fenster mit dem Fokus wirken ──
    # (seit 07.10.2026, ansichten/fussleiste.py — vorher stand hier fast
    # überall dasselbe, auch „space ki", wo die Leertaste etwas anderes
    # tut). Eine KI-Antwort, die im Hintergrund fertig wurde, meldet sich
    # auf der Startseite mit ● an der Leertaste.
    eintr = fussleiste.eintraege(u)
    if chat.ungelesen() and current_ctx(z) == "home":
        eintr = [(t, w + " ●" if t == "space" else w) for t, w in eintr]
    addclip(footer_row, 0, fussleiste.zeile(eintr, W - 1), W - 1, C["faint"])

    # ── Graph-Reminder-Nag (zuletzt → liegt über allem) ───────────────
    erinnerung.zeichnen(H, W)

    stdscr.refresh()


def run_ui(stdscr, store):
    import curses

    curses.curs_set(0)
    # raw statt cbreak (curses.wrapper): Strg+C kommt als Zeichen 3 statt als
    # SIGINT — sonst beendete es die TUI, auch mitten im Chat, wo es seit
    # 07.10.2026 die Antwort stoppt (Sasha: „bei claude ist ctrl c
    # intuitiv"). Außerhalb des Chats beendet taste_verteilen wie vorher.
    # Nebenwirkung: Strg+Z (anhalten) und Strg+Backslash wirken hier nicht
    # mehr — ein angehaltenes Vollbild-Fenster war eher eine Falle. Ein
    # externer Editor (/memory) bekommt über endwin sein Terminal, danach
    # stellt reset_prog_mode raw wieder her.
    curses.raw()
    stdscr.nodelay(True)
    stdscr.timeout(250)

    has_color = curses.has_colors()
    if has_color:
        curses.start_color()
        curses.use_default_colors()

    # Tag/Nacht-Modus: die Datei ist die einzige Wahrheit (core/theme.py).
    # Warum es keine eigene Modus-Variable mehr gibt, steht bei
    # Kontext.theme_mode_now (tui/ansichten/kontext.py).
    _theme = _load_theme_state()

    # ── Der Kontext: was alle Ansichten teilen (Farben, Theme, Zeichnen) ──
    z = ansichten.kontext.Kontext(stdscr, store, has_color, _theme)
    C, PIX, addclip = z.C, z.PIX, z.addclip
    apply_theme, draw_box = z.apply_theme, z.draw_box
    resolved_theme, safe_addstr = z.resolved_theme, z.safe_addstr
    cur_theme = resolved_theme()
    apply_theme(cur_theme)

    # Die UMGEBUNG hängt NICHT mehr an der TUI: `zentrale-themed` beobachtet
    # die Wunsch-Datei, löst sie auf, schreibt theme.now und stößt Terminal,
    # Browser, Desktop und bat an. Die TUI schreibt nur den Wunsch — sie ist ein
    # Teilnehmer wie nvim, kein Verteiler. Das spart hier den ganzen früheren
    # Apparat aus Applier-Liste, Debounce-Timer und „zuletzt gemeldete Farbe";
    # die beiden Bremsen (nur bei echtem Farbwechsel, und Sammeln schneller
    # Tastendrücke) sitzen jetzt im Dienst, an einer Stelle für alle.

    # Beim Start NICHTS schreiben: die Datei steht schon, wir folgen ihr nur.
    # (Früher schrieb die TUI hier ihren hart auf "auto" gesetzten Startwert und
    # überbügelte damit bei jedem Start ein von Hand gesetztes day/night.)

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
    # die bei der nächsten Taste wieder wegklappt. Zustand, Logik und Zeichnen:
    # ansichten/befehle.py; was ein Befehl BEWIRKT: befehl_ausfuehren() oben.
    bz = ansichten.befehle.Befehlszeile(z)
    app_start = ansichten.app_start.AppStart(z, bz)   # Taste 'u': Tutor-App (2026-10-09)

    # ── stdout-Laufschrift (Taste 's' / '/lauf') ────────────────────────
    # Wunsch aus der Datei, damit ein Aus über den Neustart hält. `laeuft`
    # merkt sich vom letzten Bild, ob TATSÄCHLICH etwas rotiert — daran hängt
    # unten die Tick-Rate: nur dann zeichnen wir schneller als die ruhigen
    # 250 ms, und nur solange wirklich eine Zeile zu lang ist.
    LAUF = {"an": lauf_lesen(), "laeuft": False}
    z.LAUF = LAUF            # draw_stdout (ansichten/technik.py) liest den Wunsch

    # ── Elektronik (Mitte, aus dem Rad) — Sasha 03.10.2026: neuer Bereich,
    # bleibt erst mal leer; der Auftritt ist das Pixel-Symbol im Rad.
    ELEK = z.ELEK = {"active": False}
    # Altes 3-Spalten-Dashboard als Backup (/dashboard an). Aus = Meta-Rad.
    DASH = {"an": schalter_lesen(dashboard_datei(), False)}

    # ── Die Ansichten (tui/ansichten/, memory/system/tui_bauplan.md) ────
    # Jede bekommt den Kontext und legt ihr Zustands-Dict auch dort ab (z.AI,
    # z.K …). Die Reihenfolge ist egal, bis auf zwei: Startseite und
    # Dashboard bekommen Ansichten herein, die es dann schon geben muss.
    chat = ansichten.chat.Chat(z)
    AI = chat.AI
    chat.start()
    post = ansichten.post.Post(z)
    MAIL = post.MAIL
    post.start()
    kalender = ansichten.kalender.Kalender(z)
    K = kalender.K
    graphen = ansichten.graphen.Graphen(z)
    G = graphen.G
    fokus = ansichten.fokus.Fokus(z)
    L = fokus.L
    notizen = ansichten.notizen.Notizen(z)
    NOTE = notizen.NOTE
    klavier = ansichten.klavier.Klavier(z)
    PIANO = klavier.PIANO
    karte = ansichten.karte.Karte(z)
    M = karte.M
    desk = ansichten.desk.Desk(z)          # Desk View (2026-10-09)
    DESK = desk.DESK
    desk.zeigen = ansichten.sprung.zeigen_fuer(DESK, kalender)  # o auf einer Kachel
    technik = ansichten.technik.Technik(z)
    TECH = technik.TECH
    startseite = ansichten.startseite.Startseite(z, RAD, META, TRAD, technik)
    dashboard = ansichten.dashboard.Dashboard(z, graphen, fokus)
    # Graph-Reminder („bitte eintragen", einmal pro Sitzung): ansichten/erinnerung.py
    erinnerung = ansichten.erinnerung.Erinnerung(z, graphen)

    # Hot Reload (siehe RELOAD): Stand der eigenen Quellen beim Start merken.
    code_alt = code_stand(code_dateien())
    code_kandidat = None
    code_check_t = 0.0

    # Was die beiden Hälften der Schleife brauchen, ausdrücklich gebündelt:
    # taste_verteilen(u, ch) und bild_zeichnen(u) lesen nur von hier.
    # Hot Reload: welche App offen war, reist mit (Sasha, 08.10.2026: Termin
    # gespeichert, TUI lud neu — „und ich bin auf der hauptseite mit dem
    # wheel wieder gelandet"). Nur der Kalender nimmt auch Ansicht und Tag mit.
    _offen_apps = (("c", K, kalender), ("g", G, graphen), ("m", M, karte),
                   ("p", MAIL, post), ("a", AI, chat), ("n", NOTE, notizen),
                   ("f", L, fokus), ("d", DESK, desk))

    def offen_merken():
        for name, zustand, _ansicht in _offen_apps:
            if zustand.get("active"):
                d = {"app": name}
                if name == "c":
                    d.update(stil=K.get("stil"), ref=K.get("ref"),
                             tag=kalender.bedienung.tag().isoformat())
                return d
        return None

    OFFEN["merken"] = offen_merken
    try:
        wieder = json.loads(os.environ.pop("ZENTRALE_TUI_OFFEN", "") or "null")
    except ValueError:
        wieder = None
    if isinstance(wieder, dict):
        for name, _zustand, ansicht in _offen_apps:
            if wieder.get("app") == name:
                try:
                    ansicht.oeffnen()
                    if name == "c":
                        from datetime import date as _d
                        if wieder.get("stil") in ("A", "B", "C"):
                            K["stil"] = wieder["stil"]
                        if wieder.get("ref"):
                            K["ref"] = wieder["ref"]
                        if wieder.get("tag"):
                            kalender.bedienung.setze_tag(_d.fromisoformat(wieder["tag"]))
                    lebenslauf("HOT RELOAD: wieder offen: %s" % name)
                except Exception as e:      # lieber Startseite als Absturz
                    lebenslauf("HOT RELOAD: %s nicht wieder geöffnet: %s" % (name, e))

    u = types.SimpleNamespace(
        AI=AI, C=C, DASH=DASH, ELEK=ELEK, G=G, K=K, L=L, LAUF=LAUF, M=M, MAIL=MAIL,
        NOTE=NOTE, PIANO=PIANO, PIX=PIX, TECH=TECH, addclip=addclip, bz=bz,
        chat=chat, dashboard=dashboard, draw_box=draw_box, erinnerung=erinnerung,
        fokus=fokus, graphen=graphen, kalender=kalender, karte=karte, klavier=klavier,
        notizen=notizen, post=post, safe_addstr=safe_addstr, app_start=app_start,
        startseite=startseite, stdscr=stdscr, store=store, technik=technik, z=z,
        DESK=DESK, desk=desk)

    while True:
        # Neuer Code in tui/? Erst wenn er eine Sekunde ruht (ein Merge
        # schreibt mehrere Dateien) und kompiliert — und nie mitten im
        # Tippen, in der Befehlszeile oder während eine Antwort einläuft.
        if time.monotonic() - code_check_t >= 1.0:
            code_check_t = time.monotonic()
            code_neu = code_stand(code_dateien())
            if code_neu != code_alt:
                if code_neu != code_kandidat:
                    code_kandidat = code_neu
                elif not (in_text_entry(z) or bz.cmd_mode or AI["streaming"]):
                    fehler = code_fehler(code_dateien())
                    if fehler:
                        bz.cmd_msg = "neuer code kaputt, bleibe beim alten: " + fehler
                        lebenslauf("HOT RELOAD verworfen: " + fehler)
                        code_alt = code_neu      # erst die nächste Änderung zählt
                    else:
                        RELOAD["an"] = True
                        break

        # Während einer Länder-Kamerafahrt ODER eines laufenden KI-Streams
        # schneller ticken (~30 fps) für weiche Bewegung / live nachlaufende
        # Token; sonst die ruhige 250-ms-Kadenz (spart CPU/Backend-Last).
        # Das Klavier tickt IMMER schnell: bei 250 ms Kadenz käme der Ton
        # spürbar nach dem Tastendruck und die Tasten würden träge leuchten.
        # Läuft gerade eine stdout-Zeile durch, reicht ein Mittelding
        # (LAUF_TICK_MS ≈ halber Zeichen-Schritt) — ein Bruchteil der 30 fps.
        # Maus nur im offenen Chat (ansichten/maus.py: warum das Markieren im
        # Terminal so heil bleibt).
        chat.maus_pflegen()
        # „antwort läuft" ohne lebenden Strom-Thread → zurücksetzen
        # (2026-10-09, ansichten/chat_strom.py).
        chat.waechter()
        fast = ((M["active"] and M.get("anim")) or (AI["active"] and AI["streaming"])
                or PIANO["active"]
                or RAD["pos"] != RAD["sel"] or RAD["schnell"]
                or TRAD["pos"] != TRAD["sel"] or META["gpos"] != META["gsel"]
                or RAD.get("wurf") or TRAD.get("wurf")
                or desk.bewegt_sich())       # Desk-Ausschnitt gleitet (2026-10-10)
        # Denk-Adern (2026-10-07): ihr Bild ändert sich höchstens 10× pro
        # Sekunde (denkadern.BILDER_JE_S) — solange nur sie sich bewegen,
        # reichen 100 ms statt 33 (gemessen: etwa ein Drittel der CPU).
        adern = AI["active"] and chat.nur_adern()
        stdscr.timeout(100 if adern and not (M["active"] or PIANO["active"])
                       else 33 if fast else 60 if AI["active"]      # das Auge lebt
                       else (LAUF_TICK_MS if LAUF["laeuft"] else 250))
        ch = stdscr.getch()

        if taste_verteilen(u, ch) == BEENDEN:
            break
        # KEY_RESIZE oder Timeout → einfach neu zeichnen

        # Farbe nachziehen: ein Wort aus theme.now. Damit ist hier ALLES
        # abgedeckt, ohne Fallunterscheidung — die Uhr-Rotation, ein 't' hier
        # und eine Änderung durch irgendwen sonst sehen für uns gleich aus.
        want = resolved_theme()
        if want != cur_theme:
            cur_theme = want
            apply_theme(cur_theme)

        bild_zeichnen(u)


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
    import signal
    import traceback
    # SIGTERM (jemand beendet uns) und SIGHUP (Fenster zu) nicht mehr stumm
    # sterben lassen: Grund ins Lebenslauf-Log, dann sauber raus.
    for _sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(_sig, _signal_handler)
    lebenslauf("START  %s  backend %s  eltern %d%s" % (
        "neu geladen" if os.environ.get("ZENTRALE_TUI_RELOADED") else "frisch",
        BASE_URL, os.getppid(),
        "  (unter start_tui.sh)" if neustart_moeglich() else ""))
    # Stirbt ein Hintergrund-Thread an einer Ausnahme, landete der Traceback
    # bisher auf stderr — also mitten im curses-Bild, übermalt beim nächsten
    # Zeichnen. Am 09.10.2026 blieb so „antwort läuft" stehen, ohne Spur.
    # Jetzt steht er im Lebenslauf.
    def _thread_fehler(a):
        lebenslauf("FEHLER im Thread %s (TUI lebt weiter)\n%s" % (
            getattr(a.thread, "name", "?"),
            "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))))
    threading.excepthook = _thread_fehler
    store = Store()
    poller = threading.Thread(target=store.run, daemon=True)
    poller.start()
    if not os.environ.get("ZENTRALE_TESTLAUF"):  # Tests prüfen nie den echten PC
        threading.Thread(target=peer_wach, daemon=True).start()

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
                if RELOAD["an"]:
                    break             # Hot Reload: unten per exec ersetzen
                if weglegen_statt_beenden():
                    lebenslauf("weggelegt (läuft versteckt weiter)")
                    continue          # 'q' unter der Systemeinheit: Fenster weg, TUI bleibt warm
                lebenslauf("ENDE  " + ("/reboot" if NEUSTART["an"] else
                                       "/quit" if ENDE["echt"] else "sauber"))
                break                 # sauberer Quit (Befehl /quit, oder 'q' ohne Systemeinheit)
            except KeyboardInterrupt:
                # Ctrl-C = gewollter Quit (wie /quit) — seit 07.10.2026 (raw-
                # Modus) wirft das taste_verteilen, außer im Chat, wo Ctrl-C
                # die Antwort stoppt. Sauberer Exit (rc 0), damit
                # das Start-Skript still aufräumt statt "kein sauberer Quit" samt
                # Crash-/Backend-Log auszuspucken.
                lebenslauf("ENDE  ctrl-c (SIGINT)")
                break
            except Signalende as e:
                lebenslauf("ENDE  durch Signal %d (Grund steht eine Zeile drüber)" % e.signum)
                store.stop()
                sys.exit(128 + e.signum)
            except Exception:
                tb = traceback.format_exc()
                # Jeder abgefangene Fehler landet im Lebenslauf — auch die, die
                # die TUI überlebt. Häufen sie sich, steht hier warum.
                lebenslauf("FEHLER (abgefangen, TUI lebt weiter)\n" + tb)
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
        lebenslauf("ABSTURZ  (zu viele Fehler in 10 s)\n" + tb)
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

    # Hot Reload: denselben Prozess mit dem neuen Code ersetzen. Terminal und
    # pid bleiben, start_tui.sh merkt nichts. Wo das Rad stand, reist mit.
    if RELOAD["an"]:
        lebenslauf("HOT RELOAD  neuer Code in tui/")
        os.environ["ZENTRALE_TUI_RELOADED"] = "1"
        os.environ["ZENTRALE_TUI_RAD"] = str(RAD["sel"])
        os.environ["ZENTRALE_TUI_META"] = "%d,%d,%d" % (
            META["gsel"], 0, TRAD["sel"])
        try:
            os.environ["ZENTRALE_TUI_OFFEN"] = json.dumps(
                OFFEN["merken"]() if OFFEN.get("merken") else None)
        except Exception:
            pass
        sys.stdout.flush()
        atexit._run_exitfuncs()       # exec überspringt atexit (z.B. Tasten-Wiederholung zurück)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # /reboot: kein Fehler, sondern eine Bitte an das Start-Skript — es killt
    # sein Backend (bzw. startet den Kern-Dienst neu) und ruft die TUI erneut auf.
    if NEUSTART["an"]:
        sys.exit(NEUSTART_CODE)


if __name__ == "__main__":
    main()
