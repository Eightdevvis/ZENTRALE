#!/usr/bin/env python3
"""Test vectors for changing events on the phone — made with the REAL core.

The phone edits existing .ics files in Dart (mobile/lib/kalender/event_edit.dart)
and sends them as proposals (memory/betrieb/abgleich_fremde_knoten.md,
"Termine vom Handy"). This script writes what the core expects into
mobile/test/daten/kalender_aendern_testvektoren.json:

  x_aus     lists of days -> X-ZENTRALE-AUS exactly as the core encodes them
  reasons   every reason code of core/abgleich_vorschlaege.REASONS (the phone
            must translate each one)
  cases     an input file (written by the core, or Google-like by hand), an
            action, and the event data the core reads after the core makes
            the same change itself (icalendar + kalender_ics_abbildung) —
            the phone's edited file must read the same.

Invented events only, never Sasha's data. Run from the repo:
    venv/bin/python scripts/handy_aendern_testvektoren.py
then `flutter test` in mobile/.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

from icalendar import Calendar  # noqa: E402

import abgleich_vorschlaege as vs  # noqa: E402
import kalender_ics_abbildung as abb  # noqa: E402

TARGET = Path(ROOT) / "mobile" / "test" / "daten" / "kalender_aendern_testvektoren.json"
FIXED = dt.datetime(2026, 10, 1, 8, 0, tzinfo=dt.timezone.utc)
UID_R = "1" * 32 + "@zentrale"
UID_T = "2" * 32 + "@zentrale"
UID_G = "google-abc@google.com"
UID_Z = "google-utc@google.com"


def _daten(roh: bytes) -> dict:
    return abb.datei_lesen(roh)[0]["daten"]


def _routine(aus=()):
    kal = abb.routine_kalender({"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU",
                                "time": "17:00", "ende": "17:45", "seit": "2026-11-03",
                                "ort": "Musikschule", "aus": list(aus)}, UID_R, jetzt=FIXED)
    return abb.zusammenfuehren(None, kal, UID_R)


def _termin():
    kal = abb.termin_kalender("2026-11-19", {"label": "Zahnarzt", "time": "10:00", "ende": "11:00",
                                             "ort": "Dr. Lenz"}, UID_T, jetzt=FIXED)
    return abb.zusammenfuehren(None, kal, UID_T)


GOOGLE_TZ = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Google Inc//Google Calendar 70.9054//EN\r\n"
    "BEGIN:VEVENT\r\nDTSTART;TZID=Europe/Berlin:20261104T180000\r\n"
    "DTEND;TZID=Europe/Berlin:20261104T200000\r\nRRULE:FREQ=WEEKLY;BYDAY=WE\r\n"
    "DTSTAMP:20261001T080000Z\r\nUID:" + UID_G + "\r\nSUMMARY:Chorprobe\r\n"
    "DESCRIPTION:Noten mitbringen\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:Chor\r\n"
    "TRIGGER:-PT30M\r\nEND:VALARM\r\nEND:VEVENT\r\n"
    "BEGIN:VTIMEZONE\r\nTZID:Europe/Berlin\r\nBEGIN:STANDARD\r\nDTSTART:19701025T030000\r\n"
    "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10\r\nTZOFFSETFROM:+0200\r\nTZOFFSETTO:+0100\r\n"
    "END:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:19700329T020000\r\n"
    "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3\r\nTZOFFSETFROM:+0100\r\nTZOFFSETTO:+0200\r\n"
    "END:DAYLIGHT\r\nEND:VTIMEZONE\r\nEND:VCALENDAR\r\n").encode()

GOOGLE_UTC = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Google Inc//Google Calendar 70.9054//EN\r\n"
    "BEGIN:VEVENT\r\nDTSTART:20261023T070000Z\r\nDTEND:20261023T073000Z\r\n"
    "RRULE:FREQ=WEEKLY;BYDAY=FR\r\nDTSTAMP:20261001T080000Z\r\nUID:" + UID_Z + "\r\n"
    "SUMMARY:Laufen\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n").encode()


def _off(roh: bytes, uid: str, day: str, off: bool) -> bytes:
    """What the core's own test does to switch one occurrence off/on."""
    kal = Calendar.from_ical(roh)
    ev = next(e for e in kal.walk("VEVENT") if str(e.get("UID")) == uid and "RECURRENCE-ID" not in e)
    start = ev["DTSTART"].dt
    d = abb._datum(day)
    aus = vs.x_aus_lesen(ev.get(abb.X_AUS)) or []
    weg = {abb._lokal(v.dt).date() if isinstance(abb._lokal(v.dt), dt.datetime) else abb._lokal(v.dt)
           for liste in abb._liste(ev.get("EXDATE")) for v in getattr(liste, "dts", [])}
    if off:
        aus = aus + [day] if day not in aus else aus
        weg.add(d)
    else:
        aus = [a for a in aus if a != day]
        weg.discard(d)
    ev.pop("EXDATE", None)
    ev.pop(abb.X_AUS, None)
    if aus:
        ev.add(abb.X_AUS, vs.x_aus_schreiben(aus))
    if weg:
        if isinstance(start, dt.datetime):
            t = abb._lokal(start).time()
            ev.add("EXDATE", [abb._ts(x, t) for x in sorted(weg)])
        else:
            ev.add("EXDATE", sorted(weg))
    return kal.to_ical()


def _edit(roh: bytes, uid: str, **felder) -> bytes:
    """The core's way to change an event: read, change data, write back merged."""
    st = abb.datei_lesen(roh)[0]
    d = dict(st["daten"])
    d.update(felder)
    if st["art"] == "routine":
        kal = abb.routine_kalender(d, uid, jetzt=FIXED)
    else:
        tag = d.pop("tag")
        kal = abb.termin_kalender(tag, d, uid, jetzt=FIXED)
    return abb.zusammenfuehren(roh, kal, uid)


def _fields(d: dict) -> dict:
    return {k: d.get(k) for k in ("label", "tag", "time", "ende", "ort", "aus", "seit") if k in d}


def main():
    x_aus = [[], ["2026-11-10"], ["2026-11-17", "2026-11-10"], ["2026-11-10", "kein Datum"], ["2026-12-24"] * 1]
    cases = []

    def case(name, roh, uid, action, after):
        cases.append({"name": name, "uid": uid, "input": roh.decode(), "action": action,
                      "expect": _fields(_daten(after))})

    r = _routine()
    case("routine off", r, UID_R, {"off": "2026-11-17", "time": "17:00"}, _off(r, UID_R, "2026-11-17", True))
    r2 = _off(r, UID_R, "2026-11-17", True)
    case("routine second off", r2, UID_R, {"off": "2026-11-24", "time": "17:00"},
         _off(r2, UID_R, "2026-11-24", True))
    case("routine back on", r2, UID_R, {"on": "2026-11-17", "time": "17:00"}, _off(r2, UID_R, "2026-11-17", False))
    case("google tz off", GOOGLE_TZ, UID_G, {"off": "2026-11-18", "time": "18:00"},
         _off(GOOGLE_TZ, UID_G, "2026-11-18", True))
    case("google utc off", GOOGLE_UTC, UID_Z, {"off": "2026-11-06", "time": "08:00"},
         _off(GOOGLE_UTC, UID_Z, "2026-11-06", True))
    t = _termin()
    case("termin edit", t, UID_T,
         {"edit": {"title": "Zahnarzt Kontrolle", "place": "Praxis Lenz", "day": "2026-11-20",
                   "start": "09:30", "end": "10:15"}},
         _edit(t, UID_T, label="Zahnarzt Kontrolle", ort="Praxis Lenz", tag="2026-11-20",
               time="09:30", ende="10:15"))
    case("termin clear place", t, UID_T, {"edit": {"place": ""}},
         abb.zusammenfuehren(t, abb.termin_kalender("2026-11-19", {"label": "Zahnarzt", "time": "10:00",
                                                                   "ende": "11:00"}, UID_T, jetzt=FIXED), UID_T))
    case("routine edit time", r, UID_R, {"edit": {"title": "Geige (neu)", "start": "16:30", "end": "17:30"}},
         _edit(r, UID_R, label="Geige (neu)", time="16:30", ende="17:30"))

    out = {
        "x_aus": [{"list": lst, "encoded": vs.x_aus_schreiben(lst)} for lst in x_aus],
        "reasons": sorted(vs.REASONS),
        "cases": cases,
    }
    TARGET.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{TARGET.relative_to(ROOT)}: {len(cases)} cases, {len(out['reasons'])} reasons")


if __name__ == "__main__":
    main()
