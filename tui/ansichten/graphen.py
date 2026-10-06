# tui/ansichten/graphen.py
#
# Das Graph-Werkzeug der TUI (Zeichner gegen /api/graphs, /api/data, Logik in
# core/graphs.py) und die Überlagerung aller Graphen in einem Gitter. Bis
# 06.10.2026 Closures in run_ui (tui/zentrale_tui.py), die Typ-/Reihen-Helfer
# auf Modulebene dort; siehe memory/system/tui_bauplan.md.

import curses
from datetime import date, timedelta

from .basis import BEENDEN, _num, api_call, fmt_clock, parse_clock


def _tlabel(tid):
    for t2, lbl, _h in GRAPH_TYPES:
        if t2 == tid:
            return lbl
    return tid


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


def cycle_axis(cyc):
    """Zyklus-Vorhersage → {iso-datum: "pms"|"next"} für die Zeitachse der
    Graph-Überlagerung. Rein rechnend, damit die Regel ohne Terminal prüfbar
    ist (tests/test_tui_cycle_axis.py).

    Die Achse bleibt, wie sie ist: sie endet HEUTE und rollt Tag für Tag
    weiter — die Vorhersage schiebt sie NICHT vor. Markiert werden darum
    schlicht die Tage des Fensters, die gerade im Bild sind; der Rest tönt
    sich von selbst ein, sobald er eingerollt ist. Auch ein vorbeigezogenes
    (überfälliges) Fenster wird markiert, es liegt dann links von heute.
    """
    if not isinstance(cyc, dict):
        return {}
    try:
        c_next = date.fromisoformat(str(cyc.get("next_start")))
        c_from = date.fromisoformat(str(cyc.get("pms_from")))
        c_to = date.fromisoformat(str(cyc.get("pms_to")))
    except (TypeError, ValueError):
        return {}
    marks = {}
    dd = c_from
    while dd <= c_to and (dd - c_from).days < 60:      # Deckel gegen Müll-Daten
        marks[dd.isoformat()] = "pms"
        dd += timedelta(days=1)
    marks[c_next.isoformat()] = "next"
    return marks


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


# Farb-Palette der Überlagerung, je Graph eine (durchgezykelt).
LIFE_COL = ["graph", "acc", "warn", "net", "event", "audio", "hook", "num"]


# Kreise der 1–5-Skala, klein bis groß.
CIRC = "◦○◉●⬤"


def _overlay_serien(gs_cache, gv_cache):
    """Die Graphen mit Werten: [{name, type, dv, col, predict[, sym]}]."""
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
    return series


# Wie viele der letzten echten Werte die Schätzung mittelt (predict).
NPRED = 7


def _vorhersage_tage(s, window):
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


def _overlay_datumsmarken(window, day_col, day_x0, day_x_end, cyc_mark):
    """Sparse Datums-Marken für die große Ansicht.
    -> [(tick-spalte, label-start, "dd.mm.", zyklus?)]"""
    date_ticks = []
    prev_end = day_x0 - 2
    for d in window:
        cx = day_col.get(d)
        if cx is None:
            continue
        parts = d.split("-")
        if len(parts) != 3:
            continue
        lbl = "%s.%s." % (parts[2], parts[1])
        lx = min(cx, day_x_end + 1 - len(lbl))   # rechts nicht überlaufen
        # Der erwartete Periodenstart kriegt IMMER sein Datum unter die
        # Marke — sonst steht da eine Linie ohne Tag. Er hat Vorrang:
        # ein zu dicht danebenstehendes Nachbar-Label weicht.
        force = (cyc_mark.get(d) == "next")
        if lx - prev_end < len(lbl) + 2:         # zu dicht am letzten label
            if not force:
                continue
            if date_ticks:
                date_ticks.pop()
        date_ticks.append((cx, lx, lbl, force))
        prev_end = lx + len(lbl)
    return date_ticks


def _overlay_fenster(labeled, series, today, day_x0, day_x_end, avail, scroll):
    """Welche Tage im Bild sind und in welcher Spalte. -> (window, day_col,
    maxscroll, scroll); maxscroll = wie weit ←/→ in die Vergangenheit kann."""
    maxscroll = 0                          # wie weit man in die Vergangenheit kann
    if labeled:
        all_dates = [dd for s in series for dd in s["dv"].keys()]
        span = avail
        if all_dates:
            try:
                ey, em, ed = (int(x) for x in min(all_dates).split("-"))
                span = (today - date(ey, em, ed)).days + 1
            except Exception:
                span = avail
        if span <= avail:
            # passt komplett in die breite → wie bisher gestreckt, kein scrollen
            ndays = max(1, min(span, 366))
            window = [(today - timedelta(days=k)).isoformat() for k in range(ndays - 1, -1, -1)]
            if ndays == 1:
                day_col = {window[0]: day_x_end}
            else:
                day_col = {d: day_x0 + int(round(i / (ndays - 1) * (avail - 1)))
                           for i, d in enumerate(window)}
        else:
            # historie breiter als der platz → festes fenster (1 tag/spalte),
            # rechte kante = heute minus scroll; ←/→ pant durch die vergangenheit
            maxscroll = span - avail
            scroll = max(0, min(int(scroll), maxscroll))
            right = today - timedelta(days=scroll)
            window = [(right - timedelta(days=k)).isoformat() for k in range(avail - 1, -1, -1)]
            day_col = {d: day_x0 + i for i, d in enumerate(window)}
    else:
        window = [(today - timedelta(days=k)).isoformat() for k in range(avail - 1, -1, -1)]
        day_col = {d: day_x0 + i for i, d in enumerate(window)}
    return window, day_col, maxscroll, scroll


class Graphen:
    """Das Graph-Werkzeug (Mitte, Taste 'g'): Liste, Anlegen, Eintragen,
    Reminder, Vorhersage — und die Überlagerung aller Graphen (draw_overlay),
    die auch die lifestyle-Box des alten Dashboards zeichnet. Zustand in
    self.G (auch z.G)."""

    def __init__(self, z):
        self.z = z
        # ── Graph-Werkzeug (füllt die MITTE-Box, Taste 'g') ─────────────────
        # Geteilte Logik (core/graphs.py + /api/graphs), hier in der TUI verbaut.
        # Eigenes Mini-Zustandsmodell statt vieler nonlocal-Variablen:
        #   active : Werkzeug hat den Fokus (Tasten gehen an das Werkzeug)
        #   view   : "list" (auswählen) | "new" (anlegen) | "view" (eintragen)
        #   input  : Texteingabe (Name im new, Wert im view)
        self.G = z.G = {"active": False, "view": "list", "graphs": [], "sel": 0,
                        "def": None, "vals": [], "input": "", "newtype": "number", "msg": "",
                        "input2": "", "pstage": 0,    # input2/pstage: Perioden-Eingabe (von→bis)
                        "dayoff": 0,                  # Ziel-Tag: 0=heute, N=N Tage zurück (←/→)
                        "gscroll": 0,                 # Kombigraph-Zeitfenster (nur Übersicht):
                                                      # 0=heute rechts, N=N Tage in die
                                                      # Vergangenheit gepant (←/→ scrollt)
                        "cyc": {},                    # /api/cycle: Zyklus-Vorhersage aus dem
                                                      # »periode«-Graphen ({} = keiner/keine
                                                      # werte → es wird nichts gezeigt)
                        "shown": set(),               # in der Überlagerung gezeigte graph-ids:
                                                      # leer=alle (Übersicht), 1=solo+editieren,
                                                      # mehrere=Kombi (nur Anzeige, später)
                        "confirm": False}             # Lösch-Nachfrage aktiv (Mini-Dialog)

    def g_load(self):
        """Definitionen frisch ziehen (nach Aktionen / beim Öffnen)."""
        G, g_load_cycle = self.G, self.g_load_cycle
        try:
            G["graphs"] = api_call("/api/graphs") or []
        except Exception:
            G["graphs"] = []
        if G["sel"] >= len(G["graphs"]):
            G["sel"] = max(0, len(G["graphs"]) - 1)
        g_load_cycle()

    def g_load_cycle(self):
        """Zyklus-Vorhersage ziehen (nur der »periode«-Graph hat eine). Gerechnet
        wird im Backend aus genau den Werten, die hier eingetragen werden —
        die TUI zeigt bloß den fertigen Einzeiler. {} = nichts zu zeigen.

        Ohne einen so benannten Graphen wird GAR NICHT gefragt: api_call ist
        synchron, und ein zweiter Request pro Aktion soll die Bedienung nicht
        ausbremsen (hängendes Backend = doppelte Wartezeit)."""
        G = self.G
        if not any(isinstance(g, dict)
                   and (g.get("name") or "").strip().lower() == "periode"
                   for g in (G["graphs"] or [])):
            G["cyc"] = {}
            return
        try:
            c = api_call("/api/cycle")
        except Exception:
            c = None
        # Alles kommt über HTTP/JSON: ein kaputtes Backend darf hier auch
        # Liste/String/None liefern, ohne dass der Render später stolpert.
        G["cyc"] = c if isinstance(c, dict) else {}

    def g_load_vals(self):
        """Messwerte des gewählten Graphen ziehen (sortiert nach Datum)."""
        G = self.G
        G["vals"] = []
        if G["def"]:
            try:
                rows = api_call("/api/data/" + G["def"]["id"]) or []
                G["vals"] = sorted([e for e in rows if e.get("value") is not None],
                                   key=lambda e: str(e.get("date", "")))
            except Exception:
                pass

    def g_target(self):
        """Ziel-Datum für Eintrag/Anzeige (heute minus dayoff)."""
        G = self.G
        return date.today() - timedelta(days=max(0, G.get("dayoff", 0)))

    def g_daylabel(self):
        G, g_target = self.G, self.g_target
        off = max(0, G.get("dayoff", 0))
        if off == 0:
            return "heute"
        if off == 1:
            return "gestern"
        return g_target().strftime("%d.%m.")

    def g_existing(self):
        """Vorhandener Eintrag für den Ziel-Tag (oder None) — für 'aktuell:'-Hint."""
        G, g_target = self.G, self.g_target
        ds = g_target().isoformat()
        for e in reversed(G["vals"] or []):     # jüngster zuerst
            if isinstance(e, dict) and e.get("date") == ds:
                return e
        return None

    def g_save(self, v, end=None):
        """Wert für den Ziel-Tag eintragen (Default heute; ←/→ verschiebt ihn).
        upsert=True ersetzt einen vorhandenen Eintrag desselben Datums, damit
        Nachtragen/Ändern keine Duplikate erzeugt.
        end gesetzt → Zeitperiode (value=Start-Minute, end=End-Minute)."""
        G, g_daylabel, g_load_cycle = self.G, self.g_daylabel, self.g_load_cycle
        g_load_vals, g_target = self.g_load_vals, self.g_target
        data = {"date": g_target().isoformat(), "value": v}
        if end is not None:
            data["end"] = end
        try:
            api_call("/api/log", method="POST",
                     body={"category": G["def"]["id"], "data": data, "upsert": True})
            g_load_vals()
            g_load_cycle()          # neuer Wert → Vorhersage rückt nach
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

    def oeffnen(self):
        """Startseite → Graph-Werkzeug: Übersicht aller Graphen, heute rechts."""
        G, g_load = self.G, self.g_load
        G["active"] = True; G["view"] = "list"; G["msg"] = ""
        G["shown"] = set(); G["gscroll"] = 0; g_load()  # übersicht, heute rechts

    def taste(self, ch):
        """Eine Taste, während das Graph-Werkzeug den Fokus hat (früher ein Zweig
        der Hauptschleife in run_ui). Gibt BEENDEN zurück, wenn die TUI enden soll."""
        G, g_load, g_load_vals, g_save = self.G, self.g_load, self.g_load_vals, self.g_save
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
                return BEENDEN
            elif ch in (curses.KEY_UP, ord("k")):
                G["sel"] = max(0, G["sel"] - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                G["sel"] = min(max(0, len(G["graphs"]) - 1), G["sel"] + 1)
            elif ch == curses.KEY_LEFT:                    # kombigraph in vergangenheit pannen
                G["gscroll"] = G.get("gscroll", 0) + 7; G["msg"] = ""
            elif ch == curses.KEY_RIGHT:                   # … zurück richtung heute
                G["gscroll"] = max(0, G.get("gscroll", 0) - 7); G["msg"] = ""
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
                    G["gscroll"] = 0                       # übersicht startet bei heute
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

    def draw_overlay(self, otop, oleft, oh, ow, gs_cache, gv_cache, labeled=False, scroll=0,
                     cyc=None):
        """ÜBERLAGERUNG aller Graphen in EINEM Gitter (X=Datum/Zeitstrahl, Y je
        Typ eigene Achse). Zeichnet NUR Inhalt in das Rechteck (otop,oleft,oh,ow)
        — den Rahmen setzt der Aufrufer. Zwei Modi, geteilt von rechter
        lifestyle-Box und großer Mitte-Ansicht im Graph-Werkzeug:
        cyc = Zyklus-Vorhersage (/api/cycle) oder None — tönt die PMS-Woche und
        den erwarteten Periodenstart in die Zeitachse (siehe unten).
          labeled=False (kompakt): 1 gemeinsame 24h-Achse links, scale als
              Kreis-Zeilen im Plot, mehrzeilige Legende unten. (unverändert)
          labeled=True (groß): links GESTAPELTE beschriftete y-achsen — je
              zahl-graph eine eigene farbige achse (min/max) + die 24h-uhr;
              scale-graphen als beschriftete zeile unten; Kopf-Legende oben.
        Darstellung je Typ: period→Bande, time→eigenes Symbol auf 24h,
        scale→Kreise ◦○◉●⬤, number→dünne Linie auf eigener min/max-Spanne.

        Seit 06.10.2026 in Teile zerlegt (vorher 499 Zeilen am Stück): reine
        Rechnungen als Modul-Funktionen (_overlay_serien, _overlay_fenster,
        _overlay_datumsmarken, _vorhersage_tage), die Zeichen-Schichten als
        _overlay_*-Methoden — in derselben Reihenfolge wie vorher, denn die
        Reihenfolge IST hier die Ebenen-Ordnung (später gemalt liegt oben)."""
        C, safe_addstr = self.z.C, self.z.safe_addstr
        if oh < 4 or ow < 12:
            return 0
        if not gs_cache:
            safe_addstr(otop + 1, oleft + 2, "// noch keine graphen (g)", C["faint"])
            return 0
        plot_x = oleft + 2
        series = _overlay_serien(gs_cache, gv_cache)
        if not series:
            safe_addstr(otop + 1, oleft + 2, "// noch keine werte", C["faint"])
            return 0

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
            date_h = 1                          # sparse datums-zeile GANZ unten
            scale_h = 1 if (scale_series and not only_scale) else 0
            base = otop + header_h
            plot_bottom = otop + oh - 1 - scale_h - date_h
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

        # ── Zyklus-Fenster (nur »periode«, core/cycle.py → /api/cycle) ─────
        # Nur Tönung für Tage, die ohnehin im Bild sind — die Achse endet
        # weiter HEUTE und rollt tageweise weiter (cycle_axis, oben, testbar).
        # Ist der »periode«-Graph gerade abgewählt, wird gar nichts markiert:
        # die Tönung gehört sichtbar zu SEINER Kurve.
        cyc = cyc if isinstance(cyc, dict) else {}
        if cyc.get("graph_id") not in {g.get("id") for g in gs_cache if isinstance(g, dict)}:
            cyc = {}
        cyc_mark = cycle_axis(cyc)

        window, day_col, maxscroll, scroll = _overlay_fenster(
            labeled, series, today, day_x0, day_x_end, avail, scroll)
        day_center = day_col
        cols = window
        # Spalten-Spanne je Tag → zusammenhängende Banden auch bei Streckung
        # (kompakt: 1 Spalte, also unverändert).
        day_span = {}
        for idx, d in enumerate(window):
            x0 = day_col[d]
            x1 = (day_col[window[idx + 1]] - 1) if idx + 1 < len(window) else day_x_end
            day_span[d] = (x0, max(x0, x1))

        # Datums-Marken (sparse) EINMAL bestimmen: dieselbe Spalte trägt UNTEN
        # das Label UND (groß) eine feine senkrechte Führungslinie durch den
        # Plot nach oben → man liest Datum↔Spalte exakt ab.
        date_ticks = (_overlay_datumsmarken(window, day_col, day_x0, day_x_end, cyc_mark)
                      if labeled else [])   # (tick-spalte, label-start, "dd.mm.", zyklus?)

        # ── Zyklus-Fenster als FLÄCHE, ganz zuerst ─────────────────────────
        # PMS-Woche + erwarteter Start bekommen einen Zellen-HINTERGRUND (wie
        # die Schlaf-Bande), keine Glyphen: curses kennt keine Ebenen, und
        # „hinter den Werten" geht nur so. Alles, was danach in diese Zellen
        # gemalt wird — Hilfsraster, Kurven, Marker, Kreise —, nimmt die
        # „@cyc"-Variante seiner Farbe und behält damit die Tönung als
        # Untergrund, statt ein Loch hineinzustanzen.
        # Die Schlaf-Bande wird SPÄTER gemalt und verdrängt die Fläche: echte
        # Messwerte haben Vorrang vor einer Schätzung.
        cyc_cells = set()
        cyc_bg = bool(C.get("cyc_is_bg"))
        for d, mk in cyc_mark.items():
            span = day_span.get(d)
            if span is None:
                continue
            for cx in range(span[0], span[1] + 1):
                for r in range(plot_h):
                    # 8-Farben-Rückfall: keine Fläche möglich → gepunktete
                    # Senkrechte, erwarteter Tag durchgezogen.
                    safe_addstr(base + r, cx, " " if cyc_bg else ("│" if mk == "next" else "┊"),
                                C["cycbg"])
                    if cyc_bg:
                        cyc_cells.add((base + r, cx))

        def catt(r, c, col):
            """Farbe für eine Zelle, die auf der Zyklus-Fläche liegen kann."""
            if (r, c) in cyc_cells and (col + "@cyc") in C:
                return C[col + "@cyc"]
            return C[col]

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
                    safe_addstr(gr, cx, "·", catt(gr, cx, "faint"))
            # senkrechte Führungslinien an den Datums-Marken (gestrichelt, faint,
            # ZUERST → Banden/Linien/Marker überzeichnen sie).
            for cx, _lx, _lbl, _cy in date_ticks:
                for r in range(plot_h):
                    safe_addstr(base + r, cx, "┊", catt(base + r, cx, "faint"))
        for gr, lbl in axrows:
            safe_addstr(gr, ix_clock, lbl.rjust(2), C["faint"])

        def predicted_days(s):
            """Schätzwerte für die Lücken im Fenster (siehe _vorhersage_tage)."""
            return _vorhersage_tage(s, window)

        # 1. period/Schlaf als zusammenhängende Bande HINTER allem.
        band_glyph = " " if C.get("band_is_bg") else "▒"
        band_cells = self._overlay_banden(series, base, plot_h, day_span, cyc_cells,
                                          band_glyph, predicted_days)

        def latt(r, c, col):                   # in Banden-Zellen: @band-Variante
            # Reihenfolge = Vorrang: die Schlaf-Bande liegt ÜBER der
            # Zyklus-Fläche (sie wurde später gemalt), also gewinnt sie hier
            # auch. Sonst stanzte ein Wert auf einer Bande, die zufällig im
            # PMS-Fenster liegt, die Bandfarbe weg.
            if (r, c) in band_cells and (col + "@band") in C:
                return C[col + "@band"]
            return catt(r, c, col)

        self._overlay_skala_zeit(series, scale_series, labeled, only_scale, base, plot_h,
                                 day_center, latt, row_scale, row_clock, predicted_days)

        self._overlay_zahlen(num_series, cols, labeled, base, plot_h, plot_x,
                             AX_W if labeled else 0, day_center, latt, row_norm,
                             predicted_days)

        # ◆ über dem erwarteten Periodenstart — das EINZIGE Zeichen, das die
        # Vorhersage selbst setzt (die Fläche allein sagt nicht, WELCHER Tag
        # der Start ist). Ganz zum Schluss und in der obersten Plot-Zeile: dort
        # ist praktisch nie ein Messwert, und die eine Zelle darf sichtbar
        # bleiben. Der Untergrund (Bande/Fläche) wird über latt mitgenommen.
        for d, mk in cyc_mark.items():
            if mk == "next" and d in day_col:
                safe_addstr(base, day_col[d], "◆", latt(base, day_col[d], "cyc"))

        self._overlay_legende(series, scale_series, labeled, only_scale, otop, oleft, oh, ow,
                              plot_x, base, plot_h, date_h if labeled else 0, date_ticks,
                              scroll, maxscroll, day_x0, day_x_end, leg_lines,
                              0 if labeled else max_leg, band_glyph)
        return maxscroll        # wie weit ←/→ noch in die Vergangenheit kann

    def _overlay_banden(self, series, base, plot_h, day_span, cyc_cells, band_glyph, predicted_days):
        """period-Graphen (Schlaf) als zusammenhängende Bande HINTER allem;
        halbe Zellen an den Kanten, Schätzwerte schraffiert. -> band_cells."""
        C, safe_addstr = self.z.C, self.z.safe_addstr
        band_cells = set()
        band_fine = bool(C.get("band_is_bg")) and ("band_edge" in C)

        def frow(m):                           # 24h-Skala als FRAKTIONALE Zeile
            m = max(0, min(1440, m))
            return base + (plot_h - 1) - (m / 1440.0 * (plot_h - 1))

        def edge_attr(r, c):
            """Kantenfarbe des Bandes — auf der Zyklus-Fläche mit deren
            Hintergrund, sonst mit dem Theme-Hintergrund."""
            if (r, c) in cyc_cells and "band_edge@cyc" in C:
                return C["band_edge@cyc"]
            return C["band_edge"]

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
                        safe_addstr(r, cx, "▄", edge_attr(r, cx))
                elif fine and r == rb:         # Unterkante: oberer Zellteil → ▀
                    cover = fbot - (r - 0.5)
                    if cover >= 0.75:
                        safe_addstr(r, cx, g, C["band"]); band_cells.add((r, cx))
                    elif cover >= 0.25:
                        safe_addstr(r, cx, "▀", edge_attr(r, cx))
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
        return band_cells

    def _overlay_legende(self, series, scale_series, labeled, only_scale, otop, oleft, oh, ow, plot_x, base, plot_h, date_h, date_ticks, scroll, maxscroll, day_x0, day_x_end, leg_lines, max_leg, band_glyph):
        """Legende der Überlagerung: groß Kopfzeile + Skala-Zeile + Datums-
        zeile, kompakt farbige Marker unter dem Plot."""
        C, addclip, safe_addstr = self.z.C, self.z.addclip, self.z.safe_addstr
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
                sy = otop + oh - 1 - date_h    # datums-zeile bleibt ganz unten
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
            # ── sparse datums-zeile GANZ unten: ein paar tage übers fenster
            # verteilt (dd.mm.), damit man grob sieht wann was war. ‹/› zeigen,
            # dass links älteres bzw. rechts neueres außerhalb des fensters liegt.
            drow = otop + oh - 1
            for _cx, lx, lbl, cy in date_ticks:   # exakt unter der Führungslinie
                safe_addstr(drow, lx, lbl, C["cyc"] if cy else C["faint"])
            if scroll < maxscroll:                    # älteres links außerhalb
                safe_addstr(drow, day_x0 - 1, "‹", C["dim"])
            if scroll > 0 and maxscroll > 0:          # neueres rechts außerhalb
                safe_addstr(drow, day_x_end, "›", C["dim"])
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

    def _overlay_zahlen(self, num_series, cols, labeled, base, plot_h, plot_x, AX_W, day_center, latt, row_norm, predicted_days):
        """number-Graphen: dünne Linie auf eigener min/max-Spanne (+ groß:
        beschriftete y-achse je Graph im linken Gutter)."""
        C, safe_addstr = self.z.C, self.z.safe_addstr
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

    def _overlay_skala_zeit(self, series, scale_series, labeled, only_scale, base, plot_h, day_center, latt, row_scale, row_clock, predicted_days):
        """scale-Graphen als Kreise, time-Graphen als ihr Symbol auf der 24h-Skala."""
        safe_addstr = self.z.safe_addstr
        # 2. scale: Kreise ◦○◉●⬤. Drei Fälle:
        #   kompakt        → je graph EINE Kreis-Zeile (gestapelt unten im Plot)
        #   groß+only_scale → Kreise auf 1–5-HÖHE im Gitter (eigene y-achse)
        #   groß+gemischt   → als beschriftete Zeile ganz unten (siehe unten)
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

    def draw_graph_tool(self, by, bx, bh, bw, gv_cache):
        """Inhalt der MITTE-Box, wenn das Graph-Werkzeug Fokus hat."""
        C, G, addclip, draw_box = self.z.C, self.G, self.z.addclip, self.z.draw_box
        draw_overlay, g_daylabel = self.draw_overlay, self.g_daylabel
        g_existing, safe_addstr = self.g_existing, self.z.safe_addstr
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
                    # Solo editiert einen einzelnen Tag (←/→ = dayoff) → kein
                    # Fenster-Pan; Übersicht dagegen pant per G["gscroll"].
                    ms = draw_overlay(by + 1, bx, ov_h, bw, subset, gv_cache,
                                      labeled=True, scroll=(0 if solo else G.get("gscroll", 0)),
                                      cyc=G.get("cyc"))
                    if not solo:                  # Scroll auf echte Historie clampen
                        G["gscroll"] = max(0, min(G.get("gscroll", 0), ms or 0))
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
                    # »periode«: das vorhergesagte Datum leise ans Ende der Zeile
                    # (◆ = erwarteter Start). Volle Auskunft gibt es im Solo.
                    cyc = G.get("cyc") or {}
                    if cyc.get("graph_id") == g.get("id") and cyc.get("next_start"):
                        try:
                            line += "  ◆ " + date.fromisoformat(
                                cyc["next_start"]).strftime("%d.%m.")
                        except (TypeError, ValueError):
                            pass
                    attr = C["bright"] if cur else (C["dim"] if on else C["faint"])
                    addclip(yy, ix, line, iw, attr)
                    yy += 1
            if solo:
                # Zyklus-Zeile direkt über der Eingabe — nur beim »periode«-
                # Graphen, in Altrosa (C["cyc"]), bewusst eine einzige Zeile.
                # Der Text kommt fertig vom Backend (core/cycle.summary).
                cyc = G.get("cyc") or {}
                if cyc.get("graph_id") == solo.get("id") and cyc.get("summary"):
                    # Der Text nennt die Phase schon selbst (core/cycle.summary);
                    # hier kommt nur noch die Schwankung dazu, wenn es eine gibt.
                    ct = "◆ " + str(cyc["summary"])
                    sp = _num(cyc.get("spread"))
                    if sp:
                        ct += " · ±%d t" % sp
                    addclip(input_row - 1, ix, ct, iw, C["cyc"])
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
                gs = G.get("gscroll", 0)
                zt = ("←→ zeit (%d t zurück)" % gs) if gs else "←→ zeit"
                addclip(bottom, ix, "enter solo · n neu · %s · p ~vorhersage · r reminder · d weg · esc zu" % zt, iw, C["faint"])

            if G["confirm"] and G["graphs"]:        # Mini-Dialog über die Liste legen
                nm = G["graphs"][G["sel"]]["name"]
                q = "»%s« löschen?" % nm[:18]
                dw = min(iw, max(len(q), 16) + 4)
                dx = bx + (bw - dw) // 2
                dy = by + bh // 2 - 2
                draw_box(dy, dx, 4, dw, "LÖSCHEN", C["warn"])
                addclip(dy + 1, dx + 2, q, dw - 4, C["bright"])
                addclip(dy + 2, dx + 2, "j/enter = ja · sonst abbrechen", dw - 4, C["faint"])
