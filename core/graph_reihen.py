# core/graph_reihen.py
#
# Reine Helfer über die Messwerte eines Graphen (core/graphs.py): Zahl
# prüfen, Minuten als Uhrzeit, Dauer einer Zeitspanne, die Zahlenreihe je
# Typ, der letzte Wert als Text, die Sparkline ▁▂▃▄▅▆▇█. Kein Lesen, kein
# Schreiben, keine Imports.
#
# Warum ein eigenes Modul (2026-10-10): das Graph-Werkzeug der TUI
# (tui/ansichten/graphen.py, tui/ansichten/basis.py) und die Graph-Kachel
# (core/kachel_graph.py) sollen einen Graphen GLEICH lesen — Leitlinie
# „dasselbe Objekt, nicht kopiert". Die Helfer wohnten bis dahin in der TUI
# und sind hierher umgezogen; die TUI nimmt sie von hier (Tür `tui/` → Kern,
# bauplan_kern.md). Die TUI läuft auch auf einem Aussenposten ohne Backend,
# darum steht die Datei in deploy/aussenposten.txt und importiert nichts
# aus dem Kern.
#
# Typen (core/graphs.py): number = freie Zahl, scale = 1–5, time = Uhrzeit
# (Minuten seit Mitternacht), period = Zeitspanne (value = Start-Minute,
# end = End-Minute, End < Start heißt über Mitternacht).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

BLOECKE = "▁▂▃▄▅▆▇█"


def zahl(x):
    """x als ENDLICHE Zahl zurück, sonst None. Bool/Text/Liste/None/NaN/Inf →
    None. Alle Werte kommen über JSON rein, da kann Müll dabei sein — diese
    Schleuse hält ihn von den Rechenpfaden (int()/round()/float()) fern."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    if x != x or x in (float("inf"), float("-inf")):   # NaN (x!=x) oder Inf
        return None
    return x


def uhr(m):
    """Minuten → 'HH:MM' (24:00 für 1440). Müll → '—' statt Crash."""
    m = zahl(m)
    if m is None:
        return "—"
    m = int(round(m))
    if m >= 1440:
        return "24:00"
    return "%02d:%02d" % (m // 60, m % 60)


def dauer(m):
    """Minuten einer Spanne → '7h30' (Schlaf & Co.). Müll → '—'."""
    m = zahl(m)
    if m is None:
        return "—"
    m = int(round(m))
    return "%dh%02d" % (m // 60, m % 60)


def periode_dauer(start, end):
    """Dauer in Minuten; End < Start = über Mitternacht (Schlaf)."""
    return (int(end) - int(start)) % 1440


def wert(gtype, e):
    """Ein Messwert-Eintrag → die Zahl, die ein Bild zeigt (period: die
    Dauer), oder None, wenn er keine saubere Zahl trägt."""
    if not isinstance(e, dict):
        return None
    v = zahl(e.get("value"))
    if v is None:
        return None
    if gtype == "period":
        end = zahl(e.get("end"))
        return None if end is None else periode_dauer(v, end)
    return float(v)


def reihe(gtype, rows):
    """Zahlenreihe für die Sparkline, je nach Typ (period → Dauer). Robust:
    überspringt Einträge, die keine sauberen Zahlen sind (statt zu crashen)."""
    out = []
    for e in rows if isinstance(rows, list) else []:
        v = wert(gtype, e)
        if v is not None:
            out.append(v)
    return out


def wert_text(g, v):
    """Eine Zahl der Reihe (siehe wert) als Text, je nach Typ des Graphen."""
    t = (g or {}).get("type")
    if t == "time":
        return uhr(v)
    if t == "period":
        return dauer(v)
    v = zahl(v)
    if v is None:
        return "—"
    unit = (" " + str(g.get("unit"))) if (g or {}).get("unit") else ""
    return "%g%s" % (v, unit)


def letzter(g, rows):
    """Letzter Wert als Text (type-abhängig formatiert)."""
    if not isinstance(g, dict):
        g = {}
    vals = [e for e in (rows if isinstance(rows, list) else [])
            if isinstance(e, dict) and e.get("value") is not None]
    if not vals:
        return "—"
    e, t = vals[-1], g.get("type")
    if t == "time":
        return uhr(e.get("value"))
    if t == "period":
        if e.get("end") is None:
            return uhr(e.get("value"))
        return uhr(e.get("value")) + "–" + uhr(e.get("end"))
    v = zahl(e.get("value"))
    if v is None:
        return "—"
    unit = (" " + str(g.get("unit"))) if g.get("unit") else ""
    return "%g%s" % (v, unit)


def blockspark(vals):
    """Sparkline ▁▂▃▄▅▆▇█ aus Zahlenwerten (wie viz.js blockSpark).
    Robust: filtert alles raus, was keine endliche Zahl ist."""
    nums = [n for n in (zahl(v) for v in vals) if n is not None] \
        if isinstance(vals, (list, tuple)) else []
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    rng = (hi - lo) or 1
    return "".join(BLOECKE[round((v - lo) / rng * (len(BLOECKE) - 1))] for v in nums)
