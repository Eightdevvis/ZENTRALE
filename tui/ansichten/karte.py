# tui/ansichten/karte.py
#
# Die Weltkarte der TUI (Zeichner gegen /api/map; core/map/ rechnet,
# memory/maps/maps_system.md). Bis 06.10.2026 Closures in run_ui
# (tui/zentrale_tui.py), siehe memory/system/tui_bauplan.md.

import curses
import os
import subprocess
import urllib.error
import urllib.parse
from datetime import date, timedelta

from .basis import BEENDEN, PROJEKT, api_call, venv_python


MAP_CHOKE = "◆"          # Ereignis-/Chokepoint-Marker (Diamant)


MAP_CTRL = "●"           # Gebietskontrolle-Marker (Punkt, nach Status gefärbt)


MAP_ROUTE = "·"          # Linien-Pfad (Route/umstrittene Grenze, dezent)


# Overlay-Zyklus für Taste 'o': aus → jeder Layer der Reihe nach → aus.
OVERLAY_CYCLE = ["trade", "political"]


OVERLAY_LABEL = {"trade": "Handelsrouten", "political": "Politik/Konflikt"}


class Karte:
    """Die Karte (Mitte, Taste 'm'): Braille-Basiskarte, Pan/Zoom, Overlays
    (Handel, Politik) mit Zeitachse, Länder-Fokus mit Kamerafahrt, natives
    Fenster per 'w'. Ein reiner Zeichner gegen /api/map (Geo-Logik in
    core/map/). Zustand in self.M (auch z.M)."""

    def __init__(self, z):
        self.z = z
        # ── Karte (füllt die MITTE-Box, Taste 'm') ──────────────────────────
        # Maps-System Schritt 1: grobe Basiskarte (Küsten 1:110m). Die TUI ist
        # ein reiner Zeichner — alle Geo-Logik liegt im Backend (core/map/ →
        # /api/map/base, siehe memory/maps/maps_system.md). Wir halten nur den
        # Viewport (Mittelpunkt lon/lat + Zoom) und die letzte Server-Antwort.
        #   active : Karte hat den Fokus (Pan/Zoom-Tasten gehen an die Karte)
        #   cx,cy  : Mittelpunkt in lon/lat (Start: 0°/20°, ganze Welt zentriert)
        #   zoom   : 0 = ganze Welt; +1 je Zoomstufe (slippy-Semantik)
        #   data   : letzte /api/map/base-Antwort (None ⇒ beim nächsten Zeichnen neu holen)
        #   grid   : (cols,rows), für die data geholt wurde — bei Resize neu holen
        self.M = z.M = {"active": False, "cx": 0.0, "cy": 20.0, "zoom": 0.0,
                        "data": None, "grid": None, "msg": "", "proc": None,
                        "overlay": False,      # thematisches Overlay (Achse 2) ein/aus
                        "overlay_layer": "trade",  # welches Overlay: 'trade'|'political' (Taste o zykliert)
                        "overlay_at": None,    # Achse 3: Zeitpunkt 'YYYY-MM-DD' oder None=jetzt (Tasten ,/. ;)
                        "odata": None,         # letzte /api/map/layer/<overlay_layer>-Antwort (None ⇒ neu holen)
                        "ogrid": None,         # (cols,rows), für die odata geholt wurde
                        "focus": None,         # Name des fokussierten Landes (Alt+Pfeile), None=keins
                        "fdata": None,         # letzte /api/map/countries-Antwort (None ⇒ neu holen)
                        "fgrid": None,         # (cols,rows), für die fdata geholt wurde
                        "tcx": 0.0, "tcy": 20.0,  # Kamera-ZIEL (lon/lat) beim Fokuswechsel
                        "anim": False}         # läuft gerade eine weiche Kamerafahrt?

    def m_fetch(self, cols, rows):
        """Karte fürs aktuelle Viewport+Raster synchron holen (localhost, wenige
        ms — wie das Graph-Werkzeug bei Benutzeraktionen). Die TUI rendert das
        gefüllte Land in Braille (/api/map/braille) — der frühere Umriss-Stil ist
        raus (sah zu grob aus). Alle Geo-Mathematik bleibt in core/map/."""
        M = self.M
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

    def m_fetch_overlay(self, cols, rows):
        """Aktives Overlay-Komposit (M['overlay_layer']) fürs Viewport holen:
        Linien + Punkte + Provenienz von /api/map/layer/<layer> (ohne sub =
        Komposit). Wie m_fetch synchron; Fehler-Marker statt Dauer-Refetch bei
        totem Backend. (Backend serviert cache-first/offline-first → schnell.)"""
        M = self.M
        try:
            q = ("/api/map/layer/%s?"
                 "cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d&aspect=0.5"
                 % (M["overlay_layer"], M["cx"], M["cy"], M["zoom"], cols, rows))
            if M.get("overlay_at"):            # Achse 3: Zeitpunkt mitgeben
                q += "&at=" + M["overlay_at"]
            M["odata"] = api_call(q, timeout=2.0) or {"failed": True}
        except Exception:
            M["odata"] = {"failed": True}

    def m_time_step(self, days):
        """Achse 3: den Overlay-Zeitpunkt um `days` verschieben — aber nur, wenn
        das aktive Overlay eine Zeitachse liefert (odata['time']), sonst no-op.
        Grenzen aus min/max der Zeitreihe: über max hinaus schnappt es auf „jetzt"
        (None) zurück, unter min wird geklemmt. None = Gegenwart."""
        M = self.M
        d = M["odata"] if isinstance(M["odata"], dict) else None
        t = d.get("time") if d else None
        if not t or not t.get("min") or not t.get("max"):
            return
        cur = M.get("overlay_at") or t["max"]
        try:
            loD = date(*(int(x) for x in t["min"].split("-")))
            hiD = date(*(int(x) for x in t["max"].split("-")))
            nd = date(*(int(x) for x in cur.split("-"))) + timedelta(days=days)
        except (ValueError, TypeError):
            return
        if nd >= hiD:
            M["overlay_at"] = None             # ab „heute" → zurück auf jetzt
        elif nd <= loD:
            M["overlay_at"] = t["min"]
        else:
            M["overlay_at"] = nd.isoformat()
        M["odata"] = None                      # mit neuem at neu holen

    def m_time_now(self):
        """Achse 3 auf Gegenwart zurücksetzen."""
        M = self.M
        if M.get("overlay_at") is not None:
            M["overlay_at"] = None
            M["odata"] = None

    def m_pan(self, fx, fy):
        """Mittelpunkt um einen Bruchteil der sichtbaren Spanne verschieben.
        Spanne kommt aus den zuletzt gelieferten bounds [w,s,e,n] — so braucht
        die TUI selbst KEINE Projektion. data=None erzwingt Neuladen."""
        M = self.M
        d = M["data"]
        if not d or "bounds" not in d:   # noch nichts geladen ODER Fehler-Marker
            return                        # ({"failed": True}) → nichts zu schwenken
        w, s, e, n = d["bounds"]
        M["cx"] = max(-180.0, min(180.0, M["cx"] + fx * (e - w)))
        M["cy"] = max(-85.0, min(85.0, M["cy"] + fy * (n - s)))
        M["data"] = None
        M["odata"] = None        # Overlay-Marker mit-neu projizieren
        M["fdata"] = None        # Länder-Border mit-neu projizieren (sonst klebt sie)

    def m_zoom(self, dz):
        M = self.M
        M["zoom"] = max(0.0, min(8.0, M["zoom"] + dz))
        M["data"] = None
        M["odata"] = None
        M["fdata"] = None

    def m_window(self):
        """Die Karte im NATIVEN Fenster aufklappen (pygame, scripts/map_window.py)
        — wie /slide PDFs extern in zathura öffnet. Kein curses-Limit: echte
        antialiased Vektorgrafik. Wir reichen den aktuellen Viewport (cx/cy/zoom)
        mit, damit das Fenster genau dort aufgeht, wo die TUI gerade steht.
        Detached gestartet (eigener Prozess), die TUI läuft normal weiter."""
        M = self.M
        root = PROJEKT
        py = venv_python(root)
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
                [py, script,
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
    def m_fetch_countries(self, cols, rows):
        """Länder-Daten holen: alle Mittelpunkte (Navigation) + Umriss des
        fokussierten Landes (Border). Aufs selbe Raster wie die Braille-Basis."""
        M = self.M
        try:
            q = ("/api/map/countries?cx=%.5f&cy=%.5f&zoom=%.2f&cols=%d&rows=%d"
                 "&aspect=0.5" % (M["cx"], M["cy"], M["zoom"], cols, rows))
            if M.get("focus"):
                q += "&focus=" + urllib.parse.quote(M["focus"])
            M["fdata"] = api_call(q)
            M["fgrid"] = (cols, rows)
        except Exception:
            M["fdata"] = None

    def m_countries(self):
        """fdata sicherstellen (für das letzte bekannte Karten-Raster)."""
        M, m_fetch_countries = self.M, self.m_fetch_countries
        if M.get("fdata") is None and M.get("grid"):
            m_fetch_countries(*M["grid"])
        return M.get("fdata")

    def m_focus_init(self):
        """Ersten Fokus setzen: das Land, dessen Mittelpunkt der Bildmitte am
        nächsten liegt — und Kamera weich dorthin."""
        M, m_countries = self.M, self.m_countries
        fd = m_countries()
        if not fd or not fd.get("countries"):
            return
        best = min(fd["countries"],
                   key=lambda c: (c["lon"] - M["cx"]) ** 2 + (c["lat"] - M["cy"]) ** 2)
        M["focus"] = best["name"]
        M["tcx"], M["tcy"], M["anim"], M["fdata"] = best["lon"], best["lat"], True, None

    def m_focus_step(self, dirx, diry):
        """Zum räumlich nächsten Land in der Richtung (dirx/diry) fokussieren.
        Richtung im VISUELLEN Welt-Raum (wx/wy: oben = kleineres wy). Kosten =
        Distanz entlang der Richtung + 2× seitlicher Versatz (bevorzugt geradeaus)."""
        M, m_countries, m_focus_init = self.M, self.m_countries, self.m_focus_init
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

    def m_anim_step(self):
        """Eine Ease-Stufe der Kamerafahrt zum Fokus-Ziel (pro Frame aufgerufen,
        solange M['anim']). Refetch erzwingen, damit Karte+Border mitziehen."""
        M = self.M
        dx, dy = M["tcx"] - M["cx"], M["tcy"] - M["cy"]
        if abs(dx) < 0.08 and abs(dy) < 0.08:
            M["cx"], M["cy"], M["anim"] = M["tcx"], M["tcy"], False
        else:
            M["cx"] += dx * 0.35
            M["cy"] += dy * 0.35
        M["data"] = M["odata"] = M["fdata"] = None

    def m_alt_arrow(self, ch):
        """Alt+Pfeil → 'up'/'down'/'left'/'right'; einzelnes Esc → 'esc'; sonst
        None. (Strg+Pfeil ist schon belegt: Höhe Zentrale↔Befehlszeile.) Deckt die
        verbreiteten Alt-Formen ab, da das Terminal eine davon schickt:
          1) terminfo-Keyname kUP3… (Modifier 3 = Alt) — EIN Keycode
          2) Esc + (keypad-übersetzter) Pfeil-Keycode  (Meta=Esc-Präfix)
          3) Esc + Roh-CSI  \\033[1;3{A..D}  bzw.  \\033\\033[{A..D} / \\033O{A..D}
        Unbekannte Esc-Sequenzen landen zur Diagnose in M['msg']."""
        M, stdscr = self.M, self.z.stdscr
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

    def oeffnen(self):
        """Startseite → Karte; die Basiskarte wird beim Zeichnen frisch geholt."""
        self.M["active"] = True; self.M["data"] = None

    def taste(self, ch):
        """Eine Taste, während die Karte den Fokus hat (früher ein Zweig der
        Hauptschleife in run_ui). Gibt BEENDEN zurück, wenn die TUI enden soll."""
        M, cycle_theme, m_alt_arrow = self.M, self.z.cycle_theme, self.m_alt_arrow
        m_focus_step, m_pan, m_time_now = self.m_focus_step, self.m_pan, self.m_time_now
        m_time_step, m_window, m_zoom = self.m_time_step, self.m_window, self.m_zoom
        ca = m_alt_arrow(ch)              # Alt+Pfeil? (frisst evtl. Folgebytes)
        if ca in ("up", "down", "left", "right"):
            m_focus_step(*{"up": (0, -1), "down": (0, 1),
                           "left": (-1, 0), "right": (1, 0)}[ca])
        elif ca == "esc" or ch in (ord("m"), ord("M")):    # Esc/m → Karte zu
            M["active"] = False
        elif ch in (ord("q"), ord("Q")):                   # q → ganze TUI beenden
            return BEENDEN
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
        elif ch in (ord("o"), ord("O")):   # Overlay zyklieren
            # aus → erster Layer → nächster … → letzter → aus.
            if not M["overlay"]:
                M["overlay"] = True
                M["overlay_layer"] = OVERLAY_CYCLE[0]
            else:
                i = OVERLAY_CYCLE.index(M["overlay_layer"]) + 1
                if i >= len(OVERLAY_CYCLE):
                    M["overlay"] = False   # nach dem letzten: Overlay aus
                else:
                    M["overlay_layer"] = OVERLAY_CYCLE[i]
            M["overlay_at"] = None         # Layer-Wechsel → Zeitachse auf „jetzt"
            M["odata"] = None              # bei Wechsel/Einschalten frisch holen
        elif ch in (ord(","), ord("<")):   # Achse 3: Zeit zurück (1 Woche)
            m_time_step(-7)
        elif ch in (ord("."), ord(">")):   # Achse 3: Zeit vor (1 Woche)
            m_time_step(7)
        elif ch == ord(";"):               # Achse 3: zurück auf „jetzt"
            m_time_now()
        elif ch in (ord("w"), ord("W"), 10, 13, curses.KEY_ENTER):
            m_window()                     # natives Fenster aufklappen
        elif ch in (ord("t"), ord("T")):   # Theme darf auch hier zyklieren
            cycle_theme()

    def draw_map(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn die Karte Fokus hat. Holt bei Bedarf
        frische Daten (Resize/Pan/Zoom) und druckt die fertig gefüllte
        Braille-Karte zeilenweise (vom Backend bereits projiziert)."""
        C, M, addclip, m_fetch = self.z.C, self.M, self.z.addclip, self.m_fetch
        m_fetch_countries, m_fetch_overlay = self.m_fetch_countries, self.m_fetch_overlay
        safe_addstr = self.z.safe_addstr
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
                        # Glyph + Farbe nach cat: Kontrolle = Punkt nach Status,
                        # Ereignis = Diamant (bernstein), sonst Chokepoint (warn).
                        cat = p.get("cat") or ""
                        if cat == "control-ua":
                            st = (p.get("status") or "").upper()
                            col_attr = (C["acc"] if st == "UA"        # grün
                                        else C["graph"] if st == "RU"  # magenta (Kontrast)
                                        else C["warn"])                # umstritten
                            glyph = MAP_CTRL
                        elif cat.startswith("event-"):
                            col_attr = C["amber"]
                            glyph = MAP_CHOKE
                        else:
                            col_attr = C["warn"]
                            glyph = MAP_CHOKE
                        safe_addstr(oy + r, ox + c, glyph, col_attr)
                    dist = (p["col"] - ccol) ** 2 + (p["row"] - crow) ** 2
                    if best is None or dist < best[0]:
                        best = (dist, p)
                if best is not None:
                    focus = best[1]      # ganzer Punkt (Caption liest je nach cat)

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
            lbl = OVERLAY_LABEL.get(M["overlay_layer"], M["overlay_layer"])
            if focus:
                # Fokus-Text je nach cat: Kontrolle → Status, sonst Wert (Opfer/Verkehr).
                nm = focus.get("name", "?")
                if (focus.get("cat") or "") == "control-ua":
                    extra = focus.get("status") or "?"
                else:
                    val = focus.get("value")
                    extra = "—" if val is None else val
                info += " · [%s] %s %s" % (lbl, nm, extra)
            else:
                info += " · %s %s" % (lbl, ovintage or "?")
            # Achse 3: Zeit-Marker, sobald das Overlay eine Zeitachse liefert.
            _od = M["odata"] if isinstance(M["odata"], dict) else None
            if _od and _od.get("time"):
                info += " · ⏱%s" % (M.get("overlay_at") or "jetzt")
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
