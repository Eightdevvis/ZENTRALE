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
# Start: scripts/start_tui.sh bzw. der Symlink `zentrale-tui` fährt das
# Backend (ohne lokale KI) hoch und startet dann diese TUI im Vordergrund.
# Standalone gegen ein laufendes Backend:  venv/bin/python tui/zentrale_tui.py
# Selbsttest ohne Terminal:                venv/bin/python tui/zentrale_tui.py --selftest
# ════════════════════════════════════════════════════════════════════════

import os
import re
import sys
import atexit
import json
import time
import threading
import queue
from datetime import date, timedelta
import subprocess
import urllib.request
import urllib.error
import urllib.parse

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

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
LAUF_TICK_MS = ansichten.technik.LAUF_TICK_MS   # Takt der Schleife, während eine Zeile läuft
BEENDEN = ansichten.basis.BEENDEN       # 'q' aus einer Ansicht: Hauptschleife verlassen


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


# ── Befehlszeile: pure Logik (curses-frei, daher unit-testbar) ───────────────
TUI_COMMANDS = [
    ("/help",  "alle Befehle und Tasten zeigen"),
    ("/theme", "Theme: auto | hell | dunkel  (auch 't')"),
    ("/cloud", "Cloud-Drossel: on | off  (Datenschutz/Kosten)"),
    ("/local", "Lokale KI drosseln: on | off  (Ollama-Leitung)"),
    ("/tutor", "Sprach-Tutor TEXT-panel (Mitte, Cloud/Qwen); 'u' öffnet das Zimmer-Fenster"),
    ("/lauf",  "stdout-Laufschrift: an | aus  (auch 's')"),
    ("/dashboard", "altes 3-Spalten-Dashboard: an | aus  (aus = Meta-Rad)"),
    ("/reload", "nur die TUI mit neuem Code laden (passiert bei Code-Änderung auch von selbst)"),
    ("/reboot", "ZENTRALE neu starten: Backend + Fenster, neuer Code"),
    ("/quit",  "ZENTRALE-TUI wirklich beenden  ('q' legt das Fenster nur weg)"),
]
TUI_KEYS = [
    ("←→",    "Startseite: das gewählte Rad drehen — vorn steht die App, die enter öffnet"),
    ("alt+←→", "Startseite: das Rad wechseln (apps | technik), die Galaxie dreht mit"),
    ("enter", "Startseite: die App vorn im gewählten Rad öffnen"),
    ("esc",   "zurück, Stufe für Stufe bis zur Startseite; dort klappt esc ZENTRALE zu (wie $mod+z)"),
    # Die Apps im Rad — seit 02.10.2026 nicht mehr per Buchstabe,
    # sondern übers Rad (Sasha). Links steht deshalb der Name im Rad.
    ("graph", "Graph-Werkzeug (Mitte): anlegen / eintragen · p vorhersage-ergänzung · r tages-reminder"),
    ("notizen", "Notizen (Mitte): freie notiz aus blöcken · ↑↓ block · t/l/f text/liste/float · e bearbeiten · d weg (fragt bei inhalt) · r titel · n übersicht · esc speichern & zu"),
    ("karte", "Karte (Mitte): pan ↑↓←→/hjkl · zoom +/− · 0 reset · Alt+↑↓←→ Land fokussieren · o=Overlay (Handel→Politik→aus) · ,/. Zeit ←→ · ; jetzt · w=Fenster"),
    ("kalender", "Kalender (Mitte): ↑↓ wählen · e bearbeiten · a neu · d löschen/Routine-aus · x erledigte/deaktivierte ein/aus · l Fokus in die Listen-Sidebar (dort a/r/d/space, kein Move) · → blättern · v Woche/Monat"),
    ("post", "Post/Mail (Mitte): enter rein · e eingang (neu/ungelesen, ●=ungelesen) · f abhaken (gelesen+einsortieren) · lesen: ←→ vor/zurück, ↓ ausklappen/scrollen, ↑ scrollen · v lesen/liste · a antw · s einsort · d lösch · x abgleich · esc zurück"),
    ("space", "KI-Chat (Mitte): tippen + enter fragt die lokale KI (PC-Hirn via tunnel) · ↑↓ scrollen · esc zu"),
    ("tutor", "Persona-Zimmer (eigenes fenster): die person wohnt drin, läuft rum, redet mit stimme · tippen+enter im fenster · Alt+M stumm · ohne DISPLAY → text-panel · /tutor = text-panel"),
    ("fokus", "Fokus (Mitte): oben projekte, drunter alle listen · enter reindiven · a/s neu · space abhaken · r name · d weg · p projekt · f setzt den knoten als alleinigen fokus (rendert dann allein in der FOCUS-box) · m/> verschieben"),
    ("klavier", "Klavier (Mitte): die Tastatur IST die Klaviatur — y x c v b n m , . - weiß, s d g h j l ö schwarz · ←→ oktave · space nimmt eine melodie auf (fragt beim stoppen nach dem namen) · ↑↓ melodie wählen · enter abspielen · r umbenennen · D löschen · k/esc zu"),
    ("/",   "Befehlszeile öffnen"),
]

# Kontext-Shortcuts: welche Tasten zeigt '/' im jeweils fokussierten Fenster.
# Single Source of Truth — die Box-Fußzeilen tragen diese langen Listen NICHT
# mehr fest ein (sie schnitten ab); '/' blendet sie bei Bedarf auf. Die Tasten
# selbst greifen weiterhin direkt, ganz ohne Slash. Schlüssel = Kontext aus
# current_ctx(); Reihenfolge spiegelt die alten Fußzeilen.
CTX_KEYS = {
    "home": [
        ("←→", "rad drehen"), ("alt+←→", "rad wechseln"),
        ("enter", "app öffnen"), ("space", "ki-chat"), ("esc", "zentrale zuklappen"),
        ("/dashboard", "altes dashboard"), ("/theme", "theme"),
        ("/lauf", "stdout-lauf"), ("/quit", "beenden"),
    ],
    "technik": [
        ("esc", "zurück ins technik-system"),
    ],
    "note:edit": [
        ("↑↓", "block wählen"), ("t/l/f", "neu: text/liste/float"),
        ("e/enter", "bearbeiten"), ("d", "block weg"), ("r", "titel"),
        ("n", "übersicht"), ("esc", "speichern & zu"),
    ],
    "note:list": [
        ("↑↓", "wählen"), ("enter", "öffnen"), ("n", "neu"),
        ("d", "löschen"), ("esc", "zurück"),
    ],
    "piano": [
        ("y x c v b n m , . -", "weiße tasten"), ("s d g h j l ö", "schwarze"),
        ("←→", "oktave"), ("⌫", "letzte note weg"), ("space", "aufnahme an/aus"),
        ("↑↓", "melodie wählen"), ("enter", "abspielen / stopp"),
        ("r", "umbenennen"), ("D", "melodie löschen"),
        ("L", "licht: neon/regenbogen/aus"), ("t", "theme"), ("k/esc", "zu"),
    ],
    "ai": [
        ("tippen", "frage"), ("enter", "senden"),
        ("↑↓", "scrollen"), ("esc", "zu"),
    ],
    "elektronik": [
        ("esc", "zurück zum rad"),
    ],
    "tutor": [
        ("enter", "start / reden"), ("/lang", "sprache"),
        ("/provider", "anbieter"), ("/model", "modell"),
        ("/models", "wahl zeigen"), ("/tutorstop", "beenden"),
        ("↑↓", "scrollen"), ("esc", "zu"),
    ],
    "graph": [
        ("↑↓", "wählen"), ("enter", "öffnen"),
        ("n", "neu"), ("p", "~vorhersage"), ("r", "reminder"),
        ("d", "löschen"), ("esc", "zu"),
    ],
    "list:forest": [
        ("↑↓", "wählen"), ("enter", "rein / hak"), ("s", "rein+neu"),
        ("n", "neue liste"), ("f", "fokus"), ("r", "name"), ("p", "projekt"),
        ("m/>", "verschieben"), ("d", "weg"), ("esc/l", "zu"),
    ],
    "list:view": [
        ("enter", "rein / hak"), ("space", "hak"), ("a/s", "neu"),
        ("↑ bis oben", "bernstein: enter = abgeschlossene"),
        ("r", "name"), ("p", "projekt"), ("f", "fokus"), (">", "einordnen"),
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
        ("↑↓", "wählen"), ("enter", "öffnen"), ("e", "eingang"), ("r", "poll"),
        ("x", "abgleich"), ("z", "neu zählen"), ("esc", "zu"),
    ],
    "mail:list": [
        ("↑↓", "wählen"), ("enter", "lesen"), ("f", "abhaken"), ("a", "antworten"),
        ("s", "einsortieren"), ("d", "löschen"), ("x", "abgleich"),
        ("z", "neu zählen"), ("esc", "zurück"),
    ],
    "mail:read": [
        ("←→", "vor/zurück"), ("↓", "ausklappen/scrollen"), ("↑", "scrollen/zu"),
        ("f", "abhaken"), ("a", "antworten"), ("s", "einsortieren"), ("d", "löschen"),
        ("v", "liste"), ("x", "abgleich"), ("z", "neu zählen"), ("esc", "zurück"),
    ],
}
CTX_TITLES = {
    "home": "start", "graph": "graph", "list:forest": "fokus",
    "list:view": "liste", "list:pick": "einordnen", "map": "karte",
    "cal:week": "kalender · woche", "cal:month": "kalender · monat",
    "cal:list": "kalender · liste", "cal:sort": "kalender · sortieren",
    "mail:cats": "post", "mail:list": "post · liste", "mail:read": "post · lesen",
    "ai": "ki-chat", "tutor": "tutor",
    "note:edit": "notiz", "note:list": "notizen", "piano": "klavier",
    "technik": "technik",
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
    if name in ("local", "lokal", "ki"):         # Lokal-Kill-Switch (POST macht der Aufrufer)
        if arg in ("on", "an"):   return "LOCAL_ON", theme_mode, ""
        if arg in ("off", "aus"): return "LOCAL_OFF", theme_mode, ""
        return "LOCAL_TOGGLE", theme_mode, ""
    if name in ("tutor", "sprache"):             # Sprach-Tutor-Panel öffnen (Mitte)
        return "TUTOR_OPEN", theme_mode, ""
    if name in ("reload", "neuladen"):           # nur die TUI, neuer Code, Fenster bleibt
        return "RELOAD", theme_mode, ""
    if name in ("reboot", "neustart", "restart"):  # ganze ZENTRALE neu (Aufrufer beendet)
        return "REBOOT", theme_mode, ""
    if name in ("lauf", "laufschrift"):          # stdout-Laufschrift (Schalter macht der Aufrufer)
        if arg in ("on", "an"):   return "LAUF_ON", theme_mode, ""
        if arg in ("off", "aus"): return "LAUF_OFF", theme_mode, ""
        return "LAUF_TOGGLE", theme_mode, ""
    if name in ("dashboard", "dash"):            # altes 3-Spalten-Layout (Schalter macht der Aufrufer)
        if arg in ("on", "an"):   return "DASH_ON", theme_mode, ""
        if arg in ("off", "aus"): return "DASH_OFF", theme_mode, ""
        return "DASH_TOGGLE", theme_mode, ""
    return None, theme_mode, "unbekannter befehl: /" + name


# ── Das Rad (Startseite) ─────────────────────────────────────────────────────
# Sasha, 02.10.2026: statt KI fett in der Mitte und Tasten-Leiste unten ein
# Durchklicker — ←/→ dreht ein Rad, vorne steht EINE App, enter geht rein.
# Die Apps sitzen auf einem liegenden Ring, den man leicht von oben sieht:
# vorne = unten, gross und hell; hinten = oben, klein und blass. Gedreht
# wird über `pos` (Kommazahl), damit der Übergang gleitet statt springt.
RAD_APPS = [
    ("k", "klavier"), ("p", "post"), ("c", "kalender"), ("f", "fokus"),
    ("n", "notizen"), ("g", "graph"), ("m", "karte"), ("u", "tutor"),
    ("e", "elektronik"),
]
# Apps mit Pixel-Symbol (tui/pixel.py): im Rad eine Pille, vorn klappt das
# Symbol auf. Seit 03.10.2026: elektronik (Sasha), am selben Abend alle
# anderen auch (pixel.MOTIVE: Brief, Globus, Kalenderblatt, Klaviatur …).
RAD_SYMBOLE = tuple(a[1] for a in RAD_APPS)
def _rad_start():
    """Nach einem Hot Reload steht das Rad, wo es war."""
    try:
        return int(os.environ.get("ZENTRALE_TUI_RAD", "0"))
    except ValueError:
        return 0


RAD = {"sel": _rad_start(), "pos": float(_rad_start()),  # sel = Ziel, pos = wo das Rad gerade steht
       "offen": {}, "offen_seit": {},     # je Symbol-App: 0 zu … 1 offen, seit wann ganz offen
       "takt": 0.0, "schnell": False}     # letzter Frame; klappt gerade etwas (→ schneller Takt)

# ── Die Galaxie (Startseite seit 03.10.2026) ─────────────────────────────────
# Sasha: das 3-Spalten-Dashboard braucht es nicht mehr. Die Startseite ist
# EINE Fläche, eine Galaxie: das App-Rad und das Technik-Rad (was vorher in
# den Seitenspalten stand) sind zwei Sonnensysteme auf einer RIESIGEN Bahn —
# so gross, dass man im Ausschnitt nur einen flachen Bogen sieht und die
# beiden praktisch nebeneinander liegen. ←/→ wechselt zwischen ihnen, der
# Ausschnitt gleitet dabei ein Stück zum gewählten. enter geht ins gewählte
# System (dann dreht ←/→ dessen Apps, enter öffnet), esc wieder raus. Die alte Ansicht bleibt als Backup: /dashboard an.
TECH_APPS = [("system", "external + telemetrie"), ("stdout", "das ganze log"),
             ("netz", "outbound + laufzeit")]


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


def meta_taste(meta, rad, trad, taste):
    """Eine Taste auf der Galaxie-Startseite. PURE bis auf die drei
    Zustands-Dicts. Sasha: ←/→ dreht direkt das gewählte Rad, alt+←/→
    wechselt das Rad, enter öffnet die App vorn.
    taste: "links" | "rechts" | "alt_links" | "alt_rechts" | "enter".
    -> None | ("app", buchstabe) | ("technik", name)"""
    if taste in ("alt_links", "alt_rechts"):   # nebeneinander: links = apps, rechts = technik
        meta["gsel"] = meta["fokus"] = 1 if taste == "alt_rechts" else 0
        return None
    ziel = rad if meta["fokus"] == 0 else trad
    if taste == "links":
        ziel["sel"] -= 1
        rad_anstoss(ziel, -1)
    elif taste == "rechts":
        ziel["sel"] += 1
        rad_anstoss(ziel, 1)
    elif taste == "enter":
        if meta["fokus"] == 0:
            return ("app", RAD_APPS[rad_index(rad["sel"])][0])
        return ("technik", TECH_APPS[rad_index(trad["sel"], len(TECH_APPS))][0])
    return None


# ── Der Schleuder-Gag (Sasha, 03.10.2026) ────────────────────────────────────
# Hält man die Pfeiltaste zu lange, dreht das Rad so schnell, dass die Apps
# abreissen: ALLE im selben Moment, und jede fliegt GERADEAUS weiter, in die
# Richtung, in die sie sich gerade gedreht hat (tangential, wie ein Stein
# aus der Schleuder). Das leere Rad dreht weiter. Kurz in Ruhe lassen → alle
# sitzen wieder drauf. Jeder Druck gibt Schwung, Schwung verfliegt; normales
# Tippen kommt nie über die Schwelle, eine Tastenwiederholung (~25-30/s)
# nach rund einer Sekunde schon.
SCHWUNG_ZERFALL = 0.6        # Sekunden (e-Faltung)
SCHLEUDER_AB = 12.0          # ab so viel Schwung reissen die Apps ab
SCHLEUDER_RUHE = 1.0         # so lange nichts gedrückt → sie sind zurück
SCHLEUDER_TEMPO = 70.0       # Spalten pro Sekunde im Flug


def rad_anstoss(rad, richtung=1, jetzt=None):
    """Ein Pfeildruck am Rad: Schwung +1, Drehrichtung und Zeitpunkt merken."""
    rad["schwung"] = rad.get("schwung", 0.0) + 1.0
    rad["richtung"] = 1 if richtung >= 0 else -1
    rad["letzt"] = time.monotonic() if jetzt is None else jetzt


def schwung_schritt(schwung, dt):
    """Schwung verfliegt. PURE."""
    import math
    return schwung * math.exp(-max(0.0, dt) / SCHWUNG_ZERFALL)


def schleuder_wurf(labels, pos, richtung, breite, hoehe, tempo=SCHLEUDER_TEMPO):
    """Der Moment des Abreissens. PURE. Gleiche Ellipse wie rad_zeilen.
    -> [(name, dy, dx_mitte, vy, vx)]: Startpunkt jeder App relativ zur
    Radmitte und ihre gerade Flugrichtung (Zellen pro Sekunde) — die
    Tangente der Drehung. Zeilen sind etwa doppelt so hoch wie Spalten
    breit, darum zählt die Senkrechte im Bild doppelt."""
    import math
    n = len(labels)
    rx = min(breite // 2 - 10, 38)
    ry = max(1, min(3, (hoehe - 4) // 4))
    if n == 0 or rx < 12:
        return []
    aus = []
    for i, name in enumerate(labels):
        w = ((i - pos) / n) * 2 * math.pi
        # pos wächst → w schrumpft: Bewegung = -richtung · d(Ort)/dw
        tx = -richtung * math.cos(w) * rx
        ty = -richtung * -math.sin(w) * ry
        laenge = math.hypot(tx, 2 * ty) or 1.0
        aus.append((name, math.cos(w) * ry, math.sin(w) * rx,
                    tempo * ty / laenge, tempo * tx / laenge))
    return aus


def wurf_zeilen(teile, t):
    """Wo sind die abgerissenen Apps `t` Sekunden nach dem Wurf? PURE.
    Gerade Linie, kein Bogen. -> [(dy, dx, name, "nah")] wie rad_zeilen."""
    aus = []
    for name, y, x, vy, vx in teile:
        ny, nx = y + vy * t, x + vx * t
        aus.append((int(round(ny)), int(round(nx - len(name) / 2)), name, "nah"))
    return aus


# Eine Giga-Galaxie dreht schwer (Sasha): langsam anlaufen, sanft ausrollen.
GALAXIE_DAUER = 1.6          # Sekunden für einen Wechsel


def galaxie_schritt(von, nach, t, dauer=GALAXIE_DAUER):
    """Stellung der Galaxie `t` Sekunden nach Fahrtbeginn. PURE.
    Ease-in-out (Sinus): träge los, gleichmäßig, weich aus — kein Ruck an
    den Enden. Nach `dauer` steht sie exakt auf `nach`."""
    import math
    if dauer <= 0 or t >= dauer:
        return float(nach)
    if t <= 0:
        return float(von)
    return von + (nach - von) * (1 - math.cos(math.pi * t / dauer)) / 2


def galaxie_lage(gpos, breiten, luecke=0.1):
    """Wo liegen die Sonnensysteme im Ausschnitt bei Kamera-Stellung `gpos`
    (0 = erstes gewählt … n-1 = letztes)? PURE.
    `breiten` = Anteil der Bildbreite je System, `luecke` = Abstand zwischen
    zwei Systemen (ebenfalls Bildanteil).
    -> [(i, quer, naehe)]: quer = Mitte des Systems, -1 (linker Rand) … 1
    (rechter Rand), darf darüber hinaus gehen; naehe 1 = gewählt, 0 = ein
    System oder weiter weg.
    Die Kamera steht auf dem gewählten System (Mitte); die anderen liegen
    weiter draussen und dürfen am Rand abgeschnitten sein (Sasha)."""
    mitten, x = [], 0.0
    for i, b in enumerate(breiten):
        if i:
            x += breiten[i - 1] + luecke + b
        mitten.append(x)
    n = len(mitten)
    g = max(0.0, min(float(n - 1), gpos))
    k = min(int(g), n - 2) if n > 1 else 0
    kamera = mitten[k] + (g - k) * ((mitten[k + 1] - mitten[k]) if n > 1 else 0.0)
    return [(i, m - kamera, max(0.0, 1 - abs(i - gpos))) for i, m in enumerate(mitten)]


def dashboard_datei():
    """Pfad des Dashboard-Wunsches. ZENTRALE_DASHBOARD_FILE sticht (Tests)."""
    return (os.environ.get("ZENTRALE_DASHBOARD_FILE")
            or os.path.expanduser("~/.config/zentrale/dashboard"))


def rad_symbol_vorn():
    """Name der Symbol-App, die gerade vorn STEHT (Rad in Ruhe) — sonst None."""
    pos = RAD["pos"]
    if abs(pos - round(pos)) >= 0.08:
        return None
    name = RAD_APPS[rad_index(int(round(pos)))][1]
    return name if name in RAD_SYMBOLE else None


def rad_offen_schritt(offen, vorn, dt):
    """Ein Frame Klappen: vorn in 0,23 s auf, sonst in 0,17 s zu."""
    if vorn:
        return min(1.0, offen + dt / 0.23)
    return max(0.0, offen - dt / 0.17)


def rad_schritt(pos, sel):
    """Ein Frame Drehung: pos gleitet auf sel zu und rastet am Ende ein."""
    d = sel - pos
    return float(sel) if abs(d) < 0.02 else pos + d * 0.3


def rad_index(sel, n=None):
    """Welche App steht bei Auswahl `sel` vorn? `sel` zählt frei weiter
    (auch negativ), damit das Rad beim Umlauf nicht zurückspult."""
    return sel % (n or len(RAD_APPS))


def rad_zeilen(labels, pos, breite, hoehe, symbole=None):
    """Das Rad als Plot-Anweisungen, hinten zuerst. -> [(dy, dx, text, stil)]

    (0,0) ist die Radmitte, `dx` ist der linke Rand des Texts. Stile:
    spur (Laufbahn), fern / nah (Apps nach Tiefe), vorn + rahmen (die
    gewählte App, sobald das Rad steht).

    `symbole` {name: offen} — Apps mit Pixel-Symbol: hinten als Pille
    (Stil pille / pille_fern, Text mit je einem Leerzeichen Polster), vorn
    bzw. solange noch offen als `symbol:<name>` (dx = Mitte, Text leer).
    """
    import math
    n = len(labels)
    rx = min(breite // 2 - 10, 38)
    ry = max(1, min(3, (hoehe - 4) // 4))
    if n == 0 or rx < 12:
        return []
    aus = []
    # Laufbahn: eine Ellipse aus Punkten, hinter allem.
    gesehen = set()
    for i in range(int(4 * math.pi * rx)):
        w = 2 * math.pi * i / int(4 * math.pi * rx)
        zelle = (int(round(math.cos(w) * ry)), int(round(math.sin(w) * rx)))
        if zelle not in gesehen:
            gesehen.add(zelle)
            aus.append((zelle[0], zelle[1], "·", "spur"))
    # Apps nach Tiefe sortiert: hinten zuerst, vorn malt drüber.
    steht = abs(pos - round(pos)) < 0.08
    apps = []
    for i, name in enumerate(labels):
        w = ((i - pos) / n) * 2 * math.pi
        tiefe = math.cos(w)                      # 1 = vorn, -1 = hinten
        apps.append((tiefe, i, name, w))
    apps.sort()
    for tiefe, i, name, w in apps:
        dy = int(round(tiefe * ry))
        mitte = int(round(math.sin(w) * rx))
        if symbole is not None and name in symbole:
            if (tiefe > 0.97 and steht) or symbole[name] > 0:
                aus.append((dy, mitte, "", "symbol:" + name))
            elif tiefe > -0.8:
                aus.append((dy, mitte - len(name) // 2 - 1, " " + name + " ",
                            "pille" if tiefe > 0.2 else "pille_fern"))
            continue
        if tiefe > 0.97 and steht:
            text = " ".join(name.upper())
            x = mitte - len(text) // 2
            aus.append((dy - 1, x - 2, "╭" + "─" * (len(text) + 2) + "╮", "rahmen"))
            aus.append((dy, x - 2, "│ " + " " * len(text) + " │", "rahmen"))
            aus.append((dy, x, text, "vorn"))
            aus.append((dy + 1, x - 2, "╰" + "─" * (len(text) + 2) + "╯", "rahmen"))
        elif tiefe > -0.8:                       # ganz hinten verschwindet sie
            aus.append((dy, mitte - len(name) // 2, name,
                        "nah" if tiefe > 0.2 else "fern"))
    return aus


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
            scr.put(yy, ov_x + 2, r[1], 11, attrs["acc"])     # /dashboard passt
            scr.put(yy, ov_x + 14, r[2], ov_w - 16, attrs["dim"])
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

    # Tag/Nacht-Modus: die Datei ist die einzige Wahrheit (core/theme.py).
    # Warum es keine eigene Modus-Variable mehr gibt, steht bei
    # Kontext.theme_mode_now (tui/ansichten/kontext.py).
    _theme = _load_theme_state()

    # ── Der Kontext: was alle Ansichten teilen (Farben, Theme, Zeichnen) ──
    z = ansichten.kontext.Kontext(stdscr, store, has_color, _theme)
    C, PIX, PIX_MODUS, addclip = z.C, z.PIX, z.PIX_MODUS, z.addclip
    apply_theme, draw_box = z.apply_theme, z.draw_box
    pix_attr, resolved_theme, safe_addstr = z.pix_attr, z.resolved_theme, z.safe_addstr
    set_theme_mode, theme_mode_now = z.set_theme_mode, z.theme_mode_now
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
    # die bei der nächsten Taste wieder wegklappt. Logik: parse_command /
    # overlay_rows (Modulebene, curses-frei → testbar).
    cmd_mode = False        # tippen wir gerade einen Befehl?
    cmd_buf = ""            # inkl. führendem '/'
    help_latched = False    # volle Hilfe stehen lassen (nach '/help')
    cmd_msg = ""            # kurze Rückmeldung (z.B. unbekannter Befehl)

    # ── stdout-Laufschrift (Taste 's' / '/lauf') ────────────────────────
    # Wunsch aus der Datei, damit ein Aus über den Neustart hält. `laeuft`
    # merkt sich vom letzten Bild, ob TATSÄCHLICH etwas rotiert — daran hängt
    # unten die Tick-Rate: nur dann zeichnen wir schneller als die ruhigen
    # 250 ms, und nur solange wirklich eine Zeile zu lang ist.
    LAUF = {"an": lauf_lesen(), "laeuft": False}
    z.LAUF = LAUF            # draw_stdout (ansichten/technik.py) liest den Wunsch

    # ── Graph-Reminder-Nag ──────────────────────────────────────────────
    # Poppt EINMAL pro Sitzung ein „bitte eintragen"-Kästchen, wenn ein Graph
    # mit Tages-Reminder heute noch nicht geloggt ist (store.reminders ←
    # /api/graphs/reminders). Eine Taste klickt es weg → bis Sitzungsende Ruhe
    # für die gezeigten Graphen (nag_dismissed); neu fällige nagen weiter.
    nag_active = False       # Kästchen steht gerade offen?
    nag_items = []           # was es listet (ids für die Dismiss-Markierung)
    nag_dismissed = set()    # in dieser Sitzung weggeklickte graph-ids


    # ── Elektronik (Mitte, aus dem Rad) — Sasha 03.10.2026: neuer Bereich,
    # bleibt erst mal leer; der Auftritt ist das Pixel-Symbol im Rad.
    ELEK = {"active": False}
    # Altes 3-Spalten-Dashboard als Backup (/dashboard an). Aus = Meta-Rad.
    DASH = {"an": schalter_lesen(dashboard_datei(), False)}


    def draw_rad(y0, h, bx, bw, labels, rad, symbole_an=False, gedimmt=False,
                 mitte=None, mass=None, blass=False):
        """Ein Rad in den Kasten (y0, bx, h, bw) zeichnen, Mitte bei 5/8 der
        Höhe. `rad` = {"sel", "pos"}; symbole_an nur fürs App-Rad (RAD).
        Galaxie: `mitte` (y, x) setzt den Mittelpunkt frei, `mass` (breite,
        hoehe) die Grösse; der Kasten bleibt die Grenze.
        Zu schmal für die Ellipse → eine schlichte Liste, vorn mit ▸."""
        rad["pos"] = rad_schritt(rad["pos"], rad["sel"])
        cyc, ccx = mitte or (y0 + (h * 5) // 8, bx + bw // 2)
        jetzt_s = time.monotonic()
        dt_s = min(0.1, jetzt_s - rad.get("t_schl", jetzt_s))
        rad["t_schl"] = jetzt_s
        rad["schwung"] = schwung_schritt(rad.get("schwung", 0.0), dt_s)
        rb, rh = mass or (bw, h - 2)
        if rad.get("wurf") is None and rad["schwung"] > SCHLEUDER_AB:
            rad["wurf"] = (jetzt_s, schleuder_wurf(labels, rad["pos"],   # abgerissen!
                                                   rad.get("richtung", 1), rb, rh))
        elif rad.get("wurf") and jetzt_s - rad.get("letzt", 0.0) > SCHLEUDER_RUHE:
            rad["wurf"] = None                    # in Ruhe gelassen → alle wieder drauf
            rad["schwung"] = 0.0
        if rad.get("wurf"):
            symbole_an = False                    # im Flug kein aufklappendes Symbol
        rad_stil = {"spur": C["faint"], "fern": C["faint"],
                    "nah": C["faint"] if gedimmt else C["dim"],
                    "rahmen": C["faint"] if gedimmt else C["acc"],
                    "vorn": C["dim"] if gedimmt else C["bright"] | curses.A_BOLD}
        if blass:                                 # weit weg: alles nur noch ein Hauch
            rad_stil = dict.fromkeys(rad_stil, C["faint"])
        # Pixel-Symbole (tui/pixel.py): hinten eine Pille, vorn klappt das
        # Symbol auf (0,23 s), beim Wegdrehen wieder zu (0,17 s). Ohne 256
        # Farben bleibt es beim gewohnten Rahmen-Schriftzug.
        jetzt = time.monotonic()
        symbole = None
        pix_bg = C.get("pix_bg")
        if symbole_an:
            dt = min(0.1, jetzt - RAD["takt"]) if RAD["takt"] else 0.0
            RAD["takt"] = jetzt
            if pix_bg is not None and PIX_MODUS != "off":
                vorn = rad_symbol_vorn()
                symbole = {}
                for name in RAD_SYMBOLE:
                    alt = RAD["offen"].get(name, 0.0)
                    neu = rad_offen_schritt(alt, vorn == name, dt)
                    if neu >= 1 and alt < 1:
                        RAD["offen_seit"][name] = jetzt
                    RAD["offen"][name] = symbole[name] = neu
                RAD["schnell"] = any(0 < v < 1 for v in symbole.values()) or (
                    vorn is not None and symbole.get(vorn, 0) < 1)
            else:
                RAD["schnell"] = False
        farben = "nacht" if pix_bg is not None and sum(pix_bg) < 384 else "tag"
        pmodus = "half" if PIX_MODUS == "half" else "mix"

        def zeichne_symbol(name, y, x):
            """Pixel-Symbol, Schriftplatte auf Zeile y, mittig um x."""
            offen = round(symbole.get(name, 0.0), 2)
            t_ms = 0
            if offen >= 1:
                t_ms = int((jetzt - RAD["offen_seit"].get(name, jetzt)) * 1000) // 60 * 60
            zeilen, schrift = pixel.symbol_zellen(name, offen, t_ms, farben, pmodus)
            r0, c0 = y - pixel.EL_LABEL_ZEILE, x - pixel.EL_W // 2
            for r, line in enumerate(zeilen):
                yy = r0 + r
                if not (y0 < yy < y0 + h - 1):
                    continue
                for c, z in enumerate(line):
                    xx = c0 + c
                    if z and bx < xx < bx + bw - 1:
                        safe_addstr(yy, xx, z[0], pix_attr(z[1], z[2]))
            for c, ch, fg, bg in schrift:
                if (y0 < r0 + pixel.EL_LABEL_ZEILE < y0 + h - 1
                        and bx < c0 + c < bx + bw - 1):       # nie über den Rahmen
                    safe_addstr(r0 + pixel.EL_LABEL_ZEILE, c0 + c, ch,
                                pix_attr(fg, bg) | curses.A_BOLD)

        zeilen = rad_zeilen(labels, rad["pos"], rb, rh, symbole)
        if rad.get("wurf"):                       # leeres Rad + geradeaus fliegende Apps
            t0, teile = rad["wurf"]
            zeilen = [z for z in zeilen if z[3] == "spur"] + wurf_zeilen(teile, jetzt_s - t0)
        if not zeilen and labels and mitte is None:
            # Liste statt Ellipse: die gewählte mittig, Nachbarn drumherum.
            vorn = rad_index(rad["sel"], len(labels))
            platz = max(1, h - 2)
            lo, hi = -((len(labels) - 1) // 2), len(labels) // 2   # jede App einmal
            for k in range(max(lo, -(platz // 2)), min(hi, platz - platz // 2 - 1) + 1):
                name = labels[(vorn + k) % len(labels)]
                yy = y0 + 1 + platz // 2 + k
                if k == 0:
                    addclip(yy, bx + 2, "▸ " + name.upper(), bw - 4, rad_stil["vorn"])
                else:
                    addclip(yy, bx + 4, name, bw - 6, C["faint"])
            return
        for dy, dx, txt, st in zeilen:
            y, x = cyc + dy, ccx + dx
            if st.startswith("symbol:"):
                zeichne_symbol(st[7:], y, x)
                continue
            if st in ("pille", "pille_fern"):            # getönter Grund, halbe Kappen
                if y0 < y < y0 + h - 1 and bx < x - 1 and x + len(txt) + 1 < bx + bw:
                    grund, schrift = pixel.symbol_pille(txt.strip(), st == "pille_fern", farben)
                    safe_addstr(y, x - 1, "▐", pix_attr(grund, pix_bg))
                    safe_addstr(y, x, txt, pix_attr(schrift, grund)
                                | (curses.A_BOLD if st == "pille" else 0))
                    safe_addstr(y, x + len(txt), "▌", pix_attr(grund, pix_bg))
                continue
            if y0 < y < y0 + h - 1 and bx < x and x + len(txt) < bx + bw:
                safe_addstr(y, x, txt, rad_stil.get(st, C["faint"]))


    def in_text_entry():
        """Tippt der Nutzer gerade einen Freitext (Name, Eintrag, Antwort)?
        Dann bleibt '/' ein normales Zeichen und öffnet NICHT die Befehlszeile."""
        if G["active"]:
            return G["view"] in ("new", "view", "remind")   # Name/Wert/Reminder-Uhrzeit
        if L["active"]:
            return L["adding"] or L["view"] == "move_new"
        if K["active"]:
            # Termin/Routine anlegen+bearbeiten ODER Sidebar-Item neu/umbenennen
            return K["mode"] == "add" or K["linput"] is not None
        if MAIL["active"]:
            return MAIL["replying"]
        if NOTE["active"]:
            # Ebene 2 (Block bearbeiten) oder Titel tippen → Freitext, '/' literal.
            return NOTE["layer"] == 2 or NOTE["titling"]
        if PIANO["active"]:
            # Beim Namen-Tippen ist '/' ein Zeichen; sonst ist die ganze
            # Tastatur Klaviatur — die Befehlszeile hat da nichts verloren.
            return True
        if AI["active"]:
            # Ganzes Panel ist Prompt-Eingabe → '/' bleibt ein Zeichen, öffnet
            # nicht die Befehlszeile. (Bei offener Erlaubnis-Frage ignoriert der
            # AI-Zweig alles außer j/n/Zahl/esc.)
            return True
        if TUTOR["active"]:
            # Ganze Zeile ist Eingabe (reden ODER '/befehl') → '/' bleibt ein
            # Zeichen, die Tutor-Zeile parst Slash-Befehle selbst (Browser-Konsole).
            return True
        return False

    def current_ctx():
        """Kontext-Schlüssel des fokussierten Fensters für die '/'-Anzeige.
        None = Tipp-Screen ohne eigene Shortcut-Liste."""
        if G["active"]:
            return "graph" if G["view"] == "list" else None
        if L["active"]:
            v = L["view"]
            if v == "forest" and not L["adding"] and not L["confirm"]:
                return "list:forest"
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
        if AI["active"]:
            return "ai"
        if TUTOR["active"]:
            return "tutor"
        if PIANO["active"]:
            return "piano"
        if ELEK["active"]:
            return "elektronik"
        if TECH["active"]:
            return "technik"
        if NOTE["active"]:
            # Ebene 2 / Titel-Eingabe sind Freitext → '/' ist dort ein Zeichen,
            # das Overlay geht gar nicht erst auf (siehe in_text_entry). Bleibt
            # Ebene 1 (block-navigation) bzw. die Übersicht.
            if NOTE["titling"] or NOTE["layer"] == 2:
                return None
            return "note:list" if NOTE["view"] == "list" else "note:edit"
        return "home"

    chat = ansichten.chat.Chat(z)
    AI = chat.AI
    ai_titel, draw_ai = chat.ai_titel, chat.draw_ai
    chat.start()
    sprachtutor = ansichten.sprachtutor.Sprachtutor(z)
    TUTOR = sprachtutor.TUTOR
    draw_tutor = sprachtutor.draw_tutor
    post = ansichten.post.Post(z)
    MAIL, draw_mail = post.MAIL, post.draw_mail
    draw_reply = post.draw_reply
    post.start()
    kalender = ansichten.kalender.Kalender(z)
    K, draw_calendar = kalender.K, kalender.draw_calendar
    graphen = ansichten.graphen.Graphen(z)
    G, draw_graph_tool = graphen.G, graphen.draw_graph_tool
    draw_overlay, g_load = graphen.draw_overlay, graphen.g_load
    fokus = ansichten.fokus.Fokus(z)
    L, draw_list_tool = fokus.L, fokus.draw_list_tool
    proj_render = fokus.proj_render
    notizen = ansichten.notizen.Notizen(z)
    NOTE, draw_note_tool = notizen.NOTE, notizen.draw_note_tool
    klavier = ansichten.klavier.Klavier(z)
    PIANO, draw_piano_tool = klavier.PIANO, klavier.draw_piano_tool
    karte = ansichten.karte.Karte(z)
    M, draw_map, m_alt_arrow = karte.M, karte.draw_map, karte.m_alt_arrow
    m_anim_step = karte.m_anim_step
    technik = ansichten.technik.Technik(z)
    TECH, draw_external = technik.TECH, technik.draw_external
    draw_stdout, draw_tech = technik.draw_stdout, technik.draw_tech
    draw_telemetrie = technik.draw_telemetrie
    # Hot Reload (siehe RELOAD): Stand der eigenen Quellen beim Start merken.
    code_alt = code_stand(code_dateien())
    code_kandidat = None
    code_check_t = 0.0

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
                elif not (in_text_entry() or cmd_mode or AI["streaming"]
                          or TUTOR["streaming"]):
                    fehler = code_fehler(code_dateien())
                    if fehler:
                        cmd_msg = "neuer code kaputt, bleibe beim alten: " + fehler
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
        fast = ((M["active"] and M.get("anim")) or (AI["active"] and AI["streaming"])
                or (TUTOR["active"] and TUTOR["streaming"]) or PIANO["active"]
                or RAD["pos"] != RAD["sel"] or RAD["schnell"]
                or TRAD["pos"] != TRAD["sel"] or META["gpos"] != META["gsel"]
                or RAD.get("wurf") or TRAD.get("wurf"))
        stdscr.timeout(33 if fast else 60 if AI["active"]      # das Auge lebt
                       else (LAUF_TICK_MS if LAUF["laeuft"] else 250))
        ch = stdscr.getch()

        if nag_active:
            if ch != -1:                       # jede Taste klickt den Reminder weg (Sitzung)
                for r in nag_items:
                    nag_dismissed.add(r.get("id"))
                nag_active = False
                if ch in (ord("g"), ord("G")):  # g = gleich ins Graph-Werkzeug
                    G["active"] = True; G["view"] = "list"; G["msg"] = ""
                    G["gscroll"] = 0; g_load()
        elif help_latched:
            if ch != -1:                       # jede Taste schließt die Hilfe wieder
                help_latched = False
        elif cmd_mode:
            if ch == 27:                       # Esc → Befehl abbrechen
                cmd_mode = False; cmd_buf = ""
            elif ch in (10, 13, curses.KEY_ENTER):
                # parse_command bleibt eine reine Funktion (gut testbar): sie
                # rechnet nur den neuen Modus aus, geschrieben wird er hier.
                res, _neuer_modus, cmd_msg = parse_command(cmd_buf,
                                                           theme_mode_now())
                set_theme_mode(_neuer_modus)
                cmd_mode = False; cmd_buf = ""
                if res == "QUIT":
                    ENDE["echt"] = True       # wirklich beenden, nicht nur weglegen
                    break
                if res == "HELP":
                    help_latched = True
                if res == "RELOAD":
                    fehler = code_fehler(code_dateien())
                    if fehler:
                        cmd_msg = "neuer code kaputt, bleibe beim alten: " + fehler
                    else:
                        RELOAD["an"] = True
                        break
                if res == "REBOOT":
                    # Nur das Signal setzen und raus — neu aufgebaut wird von
                    # start_tui.sh (siehe NEUSTART_CODE). Ohne Skript drumherum
                    # waere das ein Beenden, kein Neustart: dann lieber sagen.
                    if neustart_moeglich():
                        NEUSTART["an"] = True
                        break
                    cmd_msg = ("neustart geht nur ueber zentrale-tui "
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
                        cmd_msg = "cloud " + ("AN" if (st or {}).get("cloud_enabled") else "GEDROSSELT")
                    except (urllib.error.URLError, OSError, ValueError):
                        cmd_msg = "cloud-schalter fehlgeschlagen"
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
                        cmd_msg = "lokale ki " + ("AN" if (st or {}).get("local_enabled") else "GEDROSSELT")
                    except (urllib.error.URLError, OSError, ValueError):
                        cmd_msg = "lokal-schalter fehlgeschlagen"
                if res in ("LAUF_ON", "LAUF_OFF", "LAUF_TOGGLE"):
                    LAUF["an"] = (not LAUF["an"]) if res == "LAUF_TOGGLE" else (res == "LAUF_ON")
                    lauf_schreiben(LAUF["an"])
                    cmd_msg = "stdout-lauf " + ("an" if LAUF["an"] else "aus")
                if res in ("DASH_ON", "DASH_OFF", "DASH_TOGGLE"):
                    DASH["an"] = (not DASH["an"]) if res == "DASH_TOGGLE" else (res == "DASH_ON")
                    schalter_schreiben(dashboard_datei(), DASH["an"])
                    TECH["active"] = False     # gibt es im alten Layout nicht
                    cmd_msg = "dashboard " + ("an (3 spalten)" if DASH["an"] else "aus (meta-rad)")
                if res == "TUTOR_OPEN":
                    # Panel öffnen wie Taste 'u': Status holen + falls Backend da
                    # und keine Session, die Persona SOFORT loslegen lassen.
                    sprachtutor.oeffnen_panel()
                    cmd_msg = "tutor"
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
            if graphen.taste(ch) == BEENDEN:
                break
        elif L["active"]:                      # Listen-Werkzeug hat den Fokus
            if fokus.taste(ch) == BEENDEN:
                break
        elif M["active"]:                      # Karte hat den Fokus
            if karte.taste(ch) == BEENDEN:
                break
        elif K["active"]:                      # Kalender hat den Fokus
            if kalender.taste(ch) == BEENDEN:
                break
        elif MAIL["active"] and MAIL["replying"]:   # Antwort-Editor hat den Fokus
            post.taste_antwort(ch)
        elif MAIL["active"]:                   # Post/Mail-Panel hat den Fokus
            if post.taste(ch) == BEENDEN:
                break
        elif NOTE["active"]:                   # Notiz-Werkzeug hat den Fokus
            if notizen.taste(ch) == BEENDEN:
                break
        elif ELEK["active"]:                   # Elektronik-Bereich hat den Fokus
            if ch == 27:
                ELEK["active"] = False
        elif TECH["active"]:                   # Technik-Ansicht hat den Fokus
            if ch == 27:
                TECH["active"] = False
        elif PIANO["active"]:                  # Klavier hat den Fokus
            klavier.taste(ch)
        elif TUTOR["active"]:                  # Sprach-Tutor hat den Fokus
            sprachtutor.taste(ch)
        elif AI["active"]:                     # KI-Chat hat den Fokus
            chat.taste(ch)
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
                    alt = m_alt_arrow(ch)
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
            elif ch in (ord("u"), ord("U")):   # 'u' öffnet DIREKT das Persona-Zimmer (natives Fenster)
                if os.environ.get("ZENTRALE_ROOM_PARENT"):
                    # Die TUI wurde AUS dem Zimmer heraus geöffnet (Wand-Kiosk,
                    # room.py Alt+Z): das Zimmer liegt darunter und läuft weiter.
                    # 'u' heißt hier »zurück ins Zimmer« — TUI zu, kein zweites
                    # Zimmer, das sich mit dem ersten ums Mikro streitet.
                    break
                sprachtutor.oeffnen()
            elif ch in (ord("n"), ord("N")):   # Notiz-Werkzeug öffnen (direkt in eine Notiz)
                notizen.oeffnen()
            elif ch in (ord("k"), ord("K")):   # Klavier öffnen (wie im Browser: k)
                klavier.oeffnen()
            elif ch in (ord("e"), ord("E")):   # Elektronik-Bereich (noch leer)
                ELEK["active"] = True
            elif ch in (ord("f"), ord("F")):   # Fokus-Werkzeug öffnen (primäre Taste)
                fokus.oeffnen()
            # '/' wird global oben abgefangen (greift in JEDEM Fenster), darum
            # hier kein eigener Zweig mehr.
        # KEY_RESIZE oder Timeout → einfach neu zeichnen

        # Farbe nachziehen: ein Wort aus theme.now. Damit ist hier ALLES
        # abgedeckt, ohne Fallunterscheidung — die Uhr-Rotation, ein 't' hier
        # und eine Änderung durch irgendwen sonst sehen für uns gleich aus.
        want = resolved_theme()
        if want != cur_theme:
            cur_theme = want
            apply_theme(cur_theme)

        # Weiche Kamerafahrt zum fokussierten Land (eine Ease-Stufe pro Frame).
        if M["active"] and M.get("anim"):
            m_anim_step()

        state, metrics, connected = store.snapshot()
        gs_cache, gv_cache = store.graphs_snapshot()
        cyc_cache = store.cycle_snapshot()      # Zyklus-Tönung der lifestyle-Box
        # Nur der fokussierte Teilbaum ([node] oder []); der Store zieht bereits
        # /api/projects/focused. Kein Fallback auf alle Projekte — die volle
        # Übersicht gibt es allein in der Projektansicht (Taste 'f').
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
            continue

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
            draw_external(top, lx, leftw, store.backends_snapshot())
            tele_h = draw_telemetrie(top + ext_h, lx, leftw, metrics)
            std_h = body_h - ext_h - tele_h
            if std_h >= 3:
                laeuft_jetzt = draw_stdout(top + ext_h + tele_h, lx, std_h, leftw,
                                           state.get("logs", []) or [])

        if not AI["active"]:
            AI["auge_t0"] = None                       # nächstes Öffnen: Lider gehen neu auf

        # ── MITTE: Graph-Werkzeug / Karte (oder Einladung, sie zu öffnen) ──
        if G["active"]:
            draw_box(top, mx, body_h, midw, "graph-werkzeug")
            draw_graph_tool(top, mx, body_h, midw, gv_cache)
        elif L["active"]:
            draw_box(top, mx, body_h, midw, "fokus")
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
        elif AI["active"]:
            draw_box(top, mx, body_h, midw, ai_titel())
            draw_ai(top, mx, body_h, midw)
        elif TUTOR["active"]:
            draw_box(top, mx, body_h, midw, "tutor")
            draw_tutor(top, mx, body_h, midw)
        elif NOTE["active"]:
            draw_box(top, mx, body_h, midw, "notiz" if NOTE["view"] == "edit" else "notizen")
            draw_note_tool(top, mx, body_h, midw)
        elif PIANO["active"]:
            draw_box(top, mx, body_h, midw, "klavier")
            draw_piano_tool(top, mx, body_h, midw)
        elif ELEK["active"]:
            draw_box(top, mx, body_h, midw, "elektronik")
            leer = "hier entsteht der elektronik-bereich"
            addclip(top + body_h // 2, mx + max(2, (midw - len(leer)) // 2), leer,
                    midw - 4, C["faint"])
            addclip(top + body_h - 2, mx + 2, "esc zurück zum rad", midw - 4, C["faint"])
        elif TECH["active"]:
            draw_box(top, mx, body_h, midw, "technik · " + TECH["view"])
            laeuft_jetzt = draw_tech(top, mx, body_h, midw, state, metrics, nets) or laeuft_jetzt
        elif not DASH["an"]:
            # ── Startseite: die Galaxie (seit 03.10.2026) ─────────────
            # EINE Fläche. Zwei Sonnensysteme (Apps, Technik) auf einer
            # riesigen Bahn — im Ausschnitt nur ein flacher Bogen, die
            # beiden liegen praktisch nebeneinander. ✦ = Sonne des Systems,
            # GROSS = gewählt, ● = man ist drin.
            draw_box(top, 0, body_h, W, "zentrale")
            jetzt_g = time.monotonic()
            fahrt = META["fahrt"]
            if META["gpos"] != META["gsel"] and (fahrt is None or fahrt[1] != META["gsel"]):
                fahrt = META["fahrt"] = (META["gpos"], META["gsel"], jetzt_g)  # neu / umgelenkt
            if fahrt:
                META["gpos"] = galaxie_schritt(fahrt[0], fahrt[1], jetzt_g - fahrt[2])
                if META["gpos"] == fahrt[1]:
                    META["fahrt"] = None
            gcx = W // 2
            gcy = top + (body_h * 9) // 16
            bogen = max(1, body_h // 12)              # so viel sackt der Bogen zum Rand ab
            innen = lambda yy, xx: top < yy < top + body_h - 1 and 0 < xx < W - 1  # noqa: E731
            systeme = [("apps", [a[1] for a in RAD_APPS], RAD),
                       ("technik", [a[0] for a in TECH_APPS], TRAD)]
            breiten = (0.55, 0.36)                    # das App-Rad trägt 9 Apps, Technik 3
            rad_h = max(6, body_h // 2)
            lage = []                                 # (i, naehe, cy, cx, rx, ry, rad_b)
            for i, quer, naehe in galaxie_lage(META["gpos"], breiten):
                rad_b = int(W * breiten[i])
                lage.append((i, naehe, gcy - int(round(quer * quer * bogen)),
                             gcx + int(round(quer * W / 2)),
                             min(rad_b // 2 - 10, 38), max(1, min(3, (rad_h - 4) // 4)),
                             rad_b))
            # der Bogen der Galaxie: kaum zu sehen, weit gepunktet, und dort
            # ausgespart, wo ein Sonnensystem liegt
            for xx in range(2, W - 2, 5):
                q = (xx - gcx) / (W / 2)
                yy = gcy - int(round(q * q * bogen))
                if innen(yy, xx) and not any(abs(yy - l[2]) <= l[5] + 1
                                             and abs(xx - l[3]) <= l[4] + 8 for l in lage):
                    safe_addstr(yy, xx, "·", C["faint"])
            for i, naehe, cy, cx, _rx, _ry, rad_b in lage:
                name, labels, rad = systeme[i]
                gewaehlt = META["fokus"] == i and naehe > 0.98
                # Sonne ZUERST: ein aufgeklapptes Pixel-Symbol (elektronik)
                # ragt bis in die Mitte und muss über ihr liegen, nicht drunter.
                if gewaehlt:
                    sonne, sonne_attr = "✦ " + name.upper(), C["acc"] | curses.A_BOLD
                else:
                    sonne, sonne_attr = "✦ " + name, C["faint"]
                sx = cx - len(sonne) // 2
                if innen(cy, sx) and innen(cy, sx + len(sonne)):
                    safe_addstr(cy, sx, sonne, sonne_attr)
                # Pixel-Symbole nur im nahen Rad — weit draussen und blass
                # wäre ein leuchtend blaues Feld genau falsch.
                draw_rad(top, body_h, 0, W, labels, rad, symbole_an=(i == 0 and naehe >= 0.5),
                         gedimmt=not gewaehlt, mitte=(cy, cx),
                         mass=(rad_b, rad_h), blass=naehe < 0.5)
            lz = "up %s · net %s" % (up, "traffic !" if nets else "offline ✓")
            addclip(top + 1, max(2, W - len(lz) - 3), lz, W - 4,
                    C["warn"] if nets else C["faint"])
            if body_h >= 24:                          # unten die letzten Log-Zeilen
                laeuft_jetzt = draw_stdout(top + body_h - 5, 0, 5, W,
                                           state.get("logs", []) or [], None) or laeuft_jetzt
        else:
            # ── Startseite: das Rad ───────────────────────────────────
            # Bis 02.10.2026 stand hier der KI-Ring (ring_zeilen, archiviert:
            # memory/archive/tui_ki_ring.md) mit der
            # Tasten-Leiste unten. Jetzt ein Rad zum Durchdrehen, bewusst
            # UNTER der Mitte: der Platz darüber ist für das, was ZENTRALE
            # künftig von sich aus zeigt (kommt Stück für Stück).
            draw_box(top, mx, body_h, midw, "zentrale")
            draw_rad(top, body_h, mx, midw, [a[1] for a in RAD_APPS], RAD, symbole_an=True)

        # Zappelt gerade wirklich etwas? Nur dann tickt die Schleife schneller
        # (siehe oben) — ein breites Fenster bleibt bei den ruhigen 250 ms.
        LAUF["laeuft"] = laeuft_jetzt

        if DASH["an"]:
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
            draw_overlay(top, rx, life_h, rightw, gs_cache, gv_cache, labeled=False,
                         cyc=cyc_cache)

            # ── PROJECTS (zwischen lifestyle und outbound) ────────────────────
            # VERSCHACHTELT (Quelle: store.projects_snapshot ← /api/projects, Baum).
            # Knoten OHNE Unterprojekte: Titel + Erfüllungsleiste (2 Zeilen). Knoten
            # MIT Unterprojekten: dünner Rahmen (Titel im oberen Rand) um die rekursiv
            # gezeichneten Kinder, KEINE eigene Leiste. Reine Anzeige; markiert wird im
            # Listen-Werkzeug ('p' auf Liste bzw. Eintrag). Bei Platzmangel wird
            # einfach ab dem Punkt aufgehört (kein Überlauf, kein Crash).
            if proj_h:
                draw_box(top + life_h, rx, proj_h, rightw, "focus")
                y_max = top + life_h + proj_h - 2          # letzte innere Zeile
                x0, w0 = rx + 2, max(4, rightw - 4)

                # Dieselbe Routine wie die Projektansicht (Mitte) → BYTE-GLEICHE
                # Darstellung. Ohne Cursor/Fokus-Marke; proj_cache ist ohnehin nur
                # der eine fokussierte Knoten (oder leer → Box wird gar nicht erst
                # gezeichnet, da proj_h dann 0 ist).
                y, rendered = top + life_h + 1, 0
                for p in proj_cache:
                    if y > y_max or not isinstance(p, dict):
                        break
                    y = proj_render(p, x0, y, w0, y_max)
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
        # Seit 02.10.2026 keine App-Buchstaben mehr (die Apps stehen im
        # Rad): nur noch die vier Tasten, die überall gelten. Eine KI-Antwort,
        # die im Hintergrund fertig wurde, meldet sich hier mit ●.
        ki = "space ki" + (" ●" if AI.get("neu") else "")
        if DASH["an"] or current_ctx() != "home":
            fuss = " ←→ drehen · enter öffnen · %s · esc zurück" % ki
        else:
            fuss = " ←→ drehen · alt+←→ rad wechseln · enter öffnen · %s · esc zu" % ki
        addclip(footer_row, 0, fuss, W - 1, C["faint"])

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
                # Ctrl-C = gewollter Quit (wie /quit). Sauberer Exit (rc 0), damit
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
        sys.stdout.flush()
        atexit._run_exitfuncs()       # exec überspringt atexit (z.B. Tasten-Wiederholung zurück)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # /reboot: kein Fehler, sondern eine Bitte an das Start-Skript — es killt
    # sein Backend (bzw. startet den Kern-Dienst neu) und ruft die TUI erneut auf.
    if NEUSTART["an"]:
        sys.exit(NEUSTART_CODE)


if __name__ == "__main__":
    main()
