# core/kalender_regel.py
#
# Wann findet eine Routine statt? — die EINE Stelle, die eine RRULE in
# konkrete Tage übersetzt.
#
# Warum ein eigenes kleines Modul: dieselbe Rechnung brauchen die
# Kalender-Fassade (Anzeige, Alarme, "trifft diese Routine heute?") und die
# .ics-Abbildung (welche Tage fallen in eine Pause → EXDATE). Stünde sie in
# beiden, rechneten sie irgendwann verschieden — und dann zeigt Google eine
# Geigenstunde, die ZENTRALE für ausgefallen hält. In kalender.py kann sie
# nicht stehen, weil die Abbildung tiefer liegt als die Fassade (sonst
# Import-Kreis).
#
# Zwei Bedeutungen eines Routinen-Anfangs:
#   * ohne `seit` (alle Routinen aus der alten JSON): die Regel gilt
#     "schon immer". Gerechnet wird wie seit Mai 2026 — der Regel-Anfang
#     ist der Beginn des abgefragten Zeitraums.
#   * mit `seit` (Routinen, die von außen kommen, z. B. am Handy angelegt):
#     die Regel beginnt an diesem Tag; davor gibt es kein Vorkommen.

from datetime import date, datetime

from dateutil.rrule import rrulestr


def _dtstart_text(tag: date) -> str:
    return datetime.combine(tag, datetime.min.time()).strftime("%Y%m%dT%H%M%S")


def seit_datum(r: dict) -> date | None:
    """Das `seit`-Feld als Datum, None wenn es fehlt oder Murks ist (dann
    gilt die Routine wie früher "schon immer")."""
    s = r.get("seit") if isinstance(r, dict) else None
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def vorkommen(r: dict, start: date, end: date) -> list[datetime]:
    """Alle Vorkommen der Routine `r` in [start, end] (beide inklusive), als
    datetime um Mitternacht des Tages — genau so, wie kalender.py es seit
    jeher gerechnet hat. Wirft bei ungültiger Regel (die Aufrufer fangen
    das, wie vorher)."""
    rule_str = r["rrule"]
    until = datetime.combine(end, datetime.max.time())
    seit = seit_datum(r)
    if seit is None:
        anfang = start
    else:
        if seit > end:
            return []
        anfang = seit
    rule = rrulestr(f"DTSTART:{_dtstart_text(anfang)}\nRRULE:{rule_str}")
    raus = []
    for occ in rule:
        if occ > until:
            break
        if occ.date() >= start:
            raus.append(occ)
    return raus


def regel_gueltig(rule_str: str) -> bool:
    """Lässt sich die Regel überhaupt rechnen? (Dieselbe Prüfung, mit der
    add_routine ungültige Regeln abweist.)"""
    try:
        rrulestr(f"DTSTART:{_dtstart_text(date.today())}\nRRULE:{rule_str}")
        return True
    except Exception:
        return False
