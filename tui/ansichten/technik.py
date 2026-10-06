# tui/ansichten/technik.py
#
# Was früher fest in den Seitenspalten klebte: welche KI-Backends erreichbar
# sind, die Telemetrie, das stdout-Log (mit Laufschrift) und der ausgehende
# Traffic. Seit 03.10.2026 auch als Technik-Ansicht aus dem Technik-Rad. Bis
# 06.10.2026 Closures in run_ui (tui/zentrale_tui.py), die reinen Helfer auf
# Modulebene dort; siehe memory/system/tui_bauplan.md.

import curses
import os
import time

from .basis import _num


# Telemetrie-Reihen: (label, key, einheit). Quelle ist /api/telemetry.pc
# (lokaler Host). Nicht verfügbare Werte (v=None) werden übersprungen.
TELE_ROWS = [("CPU", "cpu", "%"), ("RAM", "ram", "%"), ("TEMP", "temp", "°C")]

# stdout-Token -> Farbgruppe (wie die Browser-Front)
LOG_PREFIX_COLOR = {
    "NET": "net", "GRAPH": "graph", "EVENT": "event", "STT": "audio",
    "TTS": "audio", "WEBHOOK": "hook", "CONSOLIDATE": "graph",
    "STATE": "dim", "CLOCK": "num", "GESTURE": "acc", "LOGGED": "event",
    "LOKALE KI": "acc", "EVENT IN": "event", "EVENT OUT": "event",
}


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


# ── stdout-Laufschrift ("der Lauf") ────────────────────────────────────────
#
# Die stdout-Spalte ist die schmalste im Layout, und in einem kleinen tmux-Pane
# wird fast jede Log-Zeile hinten abgeschnitten — man liest den halben Satz und
# rät den Rest. Statt zu kürzen LÄUFT eine zu lange Zeile durch: der Text
# rotiert nach links, hinten schließt er über einen Trenner wieder an seinen
# eigenen Anfang an. Eine Runde zeigt damit den ganzen String.
#
# Drei Regeln, die das erträglich statt nervig machen:
#   • Nur was nicht passt, bewegt sich. Was ganz in die Box geht, steht still —
#     sonst zappelt das halbe Panel ohne Not (und im breiten Fenster nie).
#   • Jede Runde beginnt mit einer kurzen Pause am Zeilenanfang, sonst erwischt
#     das Auge den Satzanfang nie.
#   • Der Schritt hängt an der UHR, nicht am Bildaufbau: die Schrift läuft
#     gleich schnell, egal wie oft die TUI gerade zeichnet.
#
# An/aus per Taste 's' bzw. '/lauf'; der Wunsch überlebt den Neustart in
# ~/.config/zentrale/stdout_lauf — wie beim Theme eine Datei, ein Wort.
LAUF_TRENNER = "   ·   "     # verbindet Ende und Anfang sichtbar
LAUF_HALT = 4                # Schritte Pause am Zeilenanfang je Runde


def _lauf_takt():
    """Sekunden pro Zeichen-Schritt. ~5,5 Zeichen/s ist ein Tempo, bei dem man
    mitliest statt hinterherzuhecheln; ZENTRALE_LAUF_TAKT stellt es um (Tests
    lassen es rasen, und wem es zu zäh ist, dreht auf)."""
    try:
        n = float(os.environ.get("ZENTRALE_LAUF_TAKT") or 0.18)
    except ValueError:
        return 0.18
    return n if 0.005 <= n <= 5 else 0.18


LAUF_TAKT = _lauf_takt()
# Bildtakt, während etwas läuft: halb so lang wie ein Zeichen-Schritt, damit
# die Bewegung gleichmäßig aussieht — aber nie schneller als 40 ms (CPU) und
# nie träger als die ruhigen 250 ms der Schleife.
LAUF_TICK_MS = int(max(40, min(250, LAUF_TAKT * 1000 / 2)))


def lauf_schritt(jetzt):
    """Monotone Sekunden → Schrittzähler der Laufschrift (Müll → 0)."""
    try:
        n = float(jetzt)
    except (TypeError, ValueError):
        return 0
    if n != n or n in (float("inf"), float("-inf")):   # NaN/Inf
        return 0
    try:
        return int(n / LAUF_TAKT)
    except (OverflowError, ValueError):    # 1e308 / LAUF_TAKT läuft über
        return 0


def lauf_ausschnitt(text, breite, schritt):
    """Sichtbarer Ausschnitt einer laufenden Zeile. PURE Funktion.

    Passt der Text in `breite`, kommt er unverändert zurück — er läuft dann
    gar nicht. Sonst rotiert `text + LAUF_TRENNER` um `schritt` Zeichen nach
    links, mit LAUF_HALT Schritten Pause bei Offset 0.
    """
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    try:
        breite = int(breite)
    except (TypeError, ValueError, OverflowError):
        return ""
    if breite <= 0:
        return ""
    if len(text) <= breite:
        return text
    ring = text + LAUF_TRENNER
    try:
        schritt = int(schritt)
    except (TypeError, ValueError, OverflowError):
        schritt = 0
    stelle = schritt % (len(ring) + LAUF_HALT)
    off = 0 if stelle < LAUF_HALT else stelle - LAUF_HALT
    return (ring + ring)[off:off + breite]


class Technik:
    """Die Technik-Bausteine: external (KI-Backends), telemetrie, stdout
    (mit Laufschrift), outbound — als Technik-Ansicht aus dem Technik-Rad
    (Vollbild) und als Spalten des alten Dashboards. Zustand in self.TECH
    (auch z.TECH); den Lauf-Wunsch (z.LAUF) besitzt run_ui (/lauf, Takt)."""

    def __init__(self, z):
        self.z = z
        # ── Technik (Vollbild, aus dem Technik-Rad) — Sasha 03.10.2026: was früher
        # in den Seitenspalten klebte. view = system | stdout | netz.
        self.TECH = z.TECH = {"active": False, "view": "system"}

    # ── Technik-Bausteine: früher fest in der linken Spalte, seit 03.10.2026
    # auch in der Technik-Ansicht und auf der Startseite des Meta-Rads. ──
    def draw_external(self, y, x, w, bk):
        """EXTERNAL: erreichbare AI-Backends (local/cloud), 4 Zeilen hoch.
        Titel grün wenn irgendein Backend da ist, sonst Warn-Farbe."""
        C, draw_box, safe_addstr = self.z.C, self.z.draw_box, self.z.safe_addstr
        draw_box(y, x, 4, w, "external", C["acc"] if bk.get("any") else C["warn"])
        if bk.get("local"):
            ltxt, lattr = "✓ ollama", C["bright"]
        elif bk.get("local_enabled") is False:      # manuell gedrosselt
            ltxt, lattr = "✗ gedrosselt", C["warn"]
        else:
            ltxt, lattr = "✗", C["faint"]
        safe_addstr(y + 1, x + 2, "LOKAL", C["acc"])
        safe_addstr(y + 1, x + 9, ltxt, lattr)
        if bk.get("cloud"):
            ctxt, cattr = "✓ " + (bk.get("cloud_provider") or ""), C["bright"]
        elif bk.get("cloud_enabled") is False:      # manuell gedrosselt
            ctxt, cattr = "✗ gedrosselt", C["warn"]
        else:
            ctxt, cattr = "✗", C["faint"]
        safe_addstr(y + 2, x + 2, "CLOUD", C["acc"])
        safe_addstr(y + 2, x + 9, ctxt, cattr)

    def draw_telemetrie(self, y, x, w, metrics):
        """TELEMETRIE: eine Balken-Zeile je TELE_ROWS-Eintrag. -> Höhe."""
        C, draw_box, safe_addstr = self.z.C, self.z.draw_box, self.z.safe_addstr
        h = len(TELE_ROWS) + 2
        draw_box(y, x, h, w, "telemetrie")
        hlbl = host_label(metrics)   # Host des Backends (PC/LAP/PI), nicht hart
        for i, (lbl, key, _u) in enumerate(TELE_ROWS):
            tv = tele_value(metrics, key)
            safe_addstr(y + 1 + i, x + 2, hlbl + "·" + lbl, C["acc"])
            if tv:
                pct, text = tv
                n = round(max(0.0, min(100.0, pct)) / 100.0 * 10)
                safe_addstr(y + 1 + i, x + 11, "█" * n, C["acc"])
                safe_addstr(y + 1 + i, x + 11 + n, "░" * (10 - n), C["faint"])
                safe_addstr(y + 1 + i, x + w - len(text) - 2, text, C["bright"])
            else:
                safe_addstr(y + 1 + i, x + 11, "n/a", C["faint"])
        return h

    def draw_stdout(self, y, x, h, w, logs, titel="stdout"):
        """Die letzten Log-Zeilen in einem Kasten (titel=None: der Kasten
        steht schon). -> True, wenn gerade eine Zeile als Laufschrift läuft."""
        C, LAUF, draw_box = self.z.C, self.z.LAUF, self.z.draw_box
        safe_addstr = self.z.safe_addstr
        if titel:
            draw_box(y, x, h, w, titel)
        if not isinstance(logs, list):
            logs = []
        laeuft = False
        schritt = lauf_schritt(time.monotonic())
        for i, e in enumerate(logs[-max(0, h - 2):] if h > 2 else []):
            if not isinstance(e, dict):
                continue
            yy = y + 1 + i
            t = (e.get("time") or "")[:8]
            safe_addstr(yy, x + 2, t, C["faint"])
            px = x + 2 + len(t) + 1
            # Nachricht auf die Box-Innenbreite kürzen, damit nichts in den
            # Nachbarkasten überläuft (x+w-1 ist der rechte Rahmen).
            avail = (x + w - 1) - px
            voll = e.get("text") or ""
            if LAUF["an"] and avail > 6 and len(voll) > avail:
                # Passt nicht → laufen lassen statt abschneiden. Die Uhrzeit
                # links bleibt stehen, nur die Nachricht rotiert. Unter ~7
                # Zeichen Platz ist eine Laufschrift nicht mehr lesbar,
                # dann bleibt es beim ehrlichen Schnitt.
                txt = lauf_ausschnitt(voll, avail, schritt)
                laeuft = True
            else:
                txt = voll[:max(0, avail)]
            # Das Präfix (EVENT IN, TOOL …) färbt sich nur, wenn die Zeile
            # gerade an ihrem Anfang steht — mitten in der Runde gibt es
            # keinen Kopf mehr, und einer ohne Zeilenanfang wäre gelogen.
            head, grp = log_prefix(txt)
            if head and grp:
                safe_addstr(yy, px, head, C.get(grp, C["dim"]))
                safe_addstr(yy, px + len(head), txt[len(head):], C["dim"])
            else:
                safe_addstr(yy, px, txt, C["dim"])
        return laeuft

    def draw_outbound(self, y, x, h, w, nets):
        """Ausgehender Traffic (Inhalt; der Kasten steht schon)."""
        C, addclip, safe_addstr = self.z.C, self.z.addclip, self.z.safe_addstr
        if nets:
            for i, e in enumerate(nets[-max(0, h - 2):]):
                if not isinstance(e, dict):
                    continue
                yy = y + 1 + i
                t = (e.get("time") or "")[:8]
                safe_addstr(yy, x + 2, t, C["faint"])
                px = x + 2 + len(t) + 1
                addclip(yy, px, e.get("text") or "", (x + w - 1) - px, C["warn"])
        else:
            safe_addstr(y + 1, x + 2, "// offline ✓", C["acc"] | curses.A_DIM)

    def draw_tech(self, top, x, h, w, state, metrics, nets):
        """Technik-Ansicht (Vollbild, Kasten steht schon). -> läuft stdout?"""
        C, TECH, addclip, draw_box = self.z.C, self.TECH, self.z.addclip, self.z.draw_box
        draw_external, draw_outbound = self.draw_external, self.draw_outbound
        draw_stdout, draw_telemetrie = self.draw_stdout, self.draw_telemetrie
        store = self.z.store
        if TECH["view"] == "stdout":
            return draw_stdout(top, x, h, w, state.get("logs", []) or [], None)
        if TECH["view"] == "netz":
            up = fmt_uptime(state.get("uptime_s"))
            addclip(top + 1, x + 2, "laufzeit  " + up, w - 4, C["bright"])
            addclip(top + 2, x + 2, "net       " + ("TRAFFIC !" if nets else "OFFLINE ✓"),
                    w - 4, C["warn"] if nets else C["acc"])
            if h > 6:
                draw_box(top + 3, x + 1, h - 4, w - 2, "outbound", C["warn"])
                draw_outbound(top + 3, x + 1, h - 4, w - 2, nets)
            return False
        # system: external + telemetrie nebeneinander, wenn Platz ist
        bk = store.backends_snapshot()
        kw = max(24, min(44, (w - 6) // 2))
        draw_external(top + 1, x + 2, kw, bk)
        if w - 6 >= 2 * kw:
            draw_telemetrie(top + 1, x + 4 + kw, kw, metrics)
        else:
            draw_telemetrie(top + 5, x + 2, kw, metrics)
        return False
