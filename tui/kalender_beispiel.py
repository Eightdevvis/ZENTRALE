"""Beispiel-Kalender in genau der Form, die /api/calendar liefert.

Wozu: die Vorschau (scripts/kalender_vorschau.py) und die Tests der
Ansichten (tests/test_kalender_ansichten.py) brauchen Daten, ohne dass ein
Backend läuft. Die TUI darf core/kalender.py nicht importieren (Bauplan
„Türen"), deshalb wird hier die Ausgabe-Form von entries_in_range /
week_view / month_view nachgebaut — nur die Form, keine Kalender-Logik:
Spannen werden pro Tag kopiert (spanning, von, bis, span_first, span_last,
Pro-Tag-Uhrzeit aus `times`), Routinen tragen recurring=True.

Die Termine sind die aus dem Entwurf (.scratch-kalender-ansichten.html):
Oktober 2026, heute Sa 03.10.
"""
from __future__ import annotations

from datetime import date, timedelta

MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember")

# Einmal-Termine; `bis` macht eine Spanne, `times` die Uhrzeit je Tag.
TERMINE = [
    {"day": "2026-10-03", "label": "Tag der Dt. Einheit"},
    {"day": "2026-10-05", "label": "Zahnarzt", "time": "14:00", "ende": "15:00"},
    {"day": "2026-10-07", "label": "Messe", "bis": "2026-10-09",
     "times": {"2026-10-07": "10:00-18:00", "2026-10-08": "09:00-17:00",
               "2026-10-09": "10:00-14:00"}},
    {"day": "2026-10-09", "label": "Wochenende Berlin", "bis": "2026-10-11",
     "times": {"2026-10-09": "18:00", "2026-10-11": "14:00"}},
    {"day": "2026-10-14", "label": "Kino", "time": "19:00", "ende": "21:30"},
]
# Routinen: Wochentage 0=Mo … 6=So.
ROUTINEN = [
    {"label": "Geige", "tage": (1, 3), "time": "10:00", "ende": "11:00"},
    {"label": "Parkour", "tage": (5,), "time": "18:30", "ende": "20:00"},
]
HEUTE = "2026-10-03"
# Bezugstag zum Blättern: die Woche mit Messe und Berlin (Entwurf C).
REF = "2026-10-07"


def eintraege(start: date, ende: date, termine=None, routinen=None) -> dict:
    """{iso: [einträge]} für [start, ende] in der Form von entries_in_range."""
    termine = TERMINE if termine is None else termine
    routinen = ROUTINEN if routinen is None else routinen
    out: dict = {}
    for t in termine:
        d0 = date.fromisoformat(t["day"])
        roh = {k: v for k, v in t.items() if k not in ("day", "bis", "times")}
        roh.setdefault("layer", "termine")
        if t.get("bis"):
            d1 = date.fromisoformat(t["bis"])
            cur = max(d0, start)
            while cur <= min(d1, ende):
                kopie = dict(roh, spanning=True, von=t["day"], bis=t["bis"],
                             span_first=(cur == d0), span_last=(cur == d1))
                zeit = (t.get("times") or {}).get(cur.isoformat())
                if zeit:
                    kopie["time"] = zeit
                else:
                    kopie.pop("time", None)
                out.setdefault(cur.isoformat(), []).append(kopie)
                cur += timedelta(days=1)
        elif start <= d0 <= ende:
            out.setdefault(t["day"], []).append(roh)
    cur = start
    while cur <= ende:
        for r in routinen:
            if cur.weekday() in r["tage"]:
                e = {"layer": "routinen", "label": r["label"], "recurring": True}
                for k in ("time", "ende", "ausfall", "deaktiviert"):
                    if r.get(k):
                        e[k] = r[k]
                out.setdefault(cur.isoformat(), []).append(e)
        cur += timedelta(days=1)
    for iso in out:
        out[iso].sort(key=lambda e: e.get("time", "00:00"))
    return dict(sorted(out.items()))


def api_daten(view: str = "week", ref: str = HEUTE, heute: str = HEUTE,
              termine=None, routinen=None) -> dict:
    """Eine /api/calendar-Antwort (ohne weekplan/cycle/alarms-Inhalt)."""
    r = date.fromisoformat(ref)
    if view == "month":
        first = r.replace(day=1)
        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        start = first - timedelta(days=first.weekday())
        end = last + timedelta(days=6 - last.weekday())
        extra = {"month": first.strftime("%Y-%m"), "first": first.isoformat(),
                 "last": last.isoformat(),
                 "label": "%s %d" % (MONATE[first.month - 1], first.year)}
    else:
        start = r - timedelta(days=r.weekday())
        end = start + timedelta(days=6)
        extra = {"label": "%s–%s" % (start.strftime("%d.%m."), end.strftime("%d.%m.%Y"))}
    return dict(extra, view=view, ref=ref, today=heute, start=start.isoformat(),
                end=end.isoformat(), days=eintraege(start, end, termine, routinen),
                alarms=[], cycle={}, weekplan={"lid": None, "items": []})
