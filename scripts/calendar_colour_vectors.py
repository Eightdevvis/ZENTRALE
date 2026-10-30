#!/usr/bin/env python3
"""Test vectors for the phone's calendar colours — computed by the REAL core.

The phone ports key + lookup + precedence of core/calendar_colours.py to Dart
(mobile/lib/kalender/colours.dart). So both never drift apart, this script
writes synthesized events (made up, never Sasha's data) as real .ics text
(written by core/kalender_ics_abbildung.termin_kalender, plus a few
hand-written ones like Google or Thunderbird would send) together with what
the core makes of them: entry fields → key → slot (from a fixed table, or the
crc32 fallback) → resolved role/style → final hex day and night.

    venv/bin/python scripts/calendar_colour_vectors.py      # writes the file
    venv/bin/python scripts/calendar_colour_vectors.py --stdout

Target: contracts/calendar-colours/1/calendar_colour_vectors.json. Then `flutter test`
in mobile/. tests/test_calendar_colours.py fails while the file is stale.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

import calendar_colours as cc  # noqa: E402
import kalender_ics_abbildung as abb  # noqa: E402
import kalender_kategorie  # noqa: E402
import stil  # noqa: E402

TARGET = Path(ROOT) / "contracts" / "calendar-colours" / "1" / "calendar_colour_vectors.json"
FIXED_NOW = dt.datetime(2026, 10, 1, 8, 0, tzinfo=dt.timezone.utc)
LAYER_DEFAULT = "#ff5500"          # what the phone's vdir `color` file says

# The synced table the phone would have read (made up).
TABLE = {"analysis": 0, "experimentalphysik": 3, "theoretische": 1,
         "quelle:l_todo": 11, "gruppe:uni": 2, "gruppe:custom:musik": 8}

# Events written by the core itself: (day, entry).
WRITTEN = [
    ("2026-11-02", {"label": "Analysis I @ HS 1", "time": "10:00", "ende": "12:00"}),
    ("2026-11-02", {"label": "Ana Tutorium Jäger", "time": "14:00", "ende": "15:00"}),
    ("2026-11-03", {"label": "ExPhy Übung", "time": "08:00", "ende": "10:00", "kategorie": "uni"}),
    ("2026-11-03", {"label": "TP Sprechstunde (Mi)", "time": "12:00"}),
    ("2026-11-04", {"label": "Parkour", "time": "18:00", "ende": "19:30"}),
    ("2026-11-04", {"label": "Chor", "time": "19:30", "ende": "21:00",
                    "kategorie": "custom", "kategorie_name": "Musik"}),
    ("2026-11-05", {"label": "todo", "time": "10:00", "ende": "12:00",
                    "quelle": {"art": "liste", "id": "l_todo"}}),
    ("2026-11-05", {"label": "haus", "time": "16:00",
                    "quelle": {"art": "projekt", "id": "l_haus/7"}}),
    ("2026-11-06", {"label": "Zahnarzt", "time": "09:00", "ende": "10:00",
                    "stil": {"background-color": "#ffd700", "border-style": "double"}}),
    ("2026-11-06", {"label": "Analysis Klausur", "time": "13:00", "ende": "15:00",
                    "stil": {"border-color": "#ff0000", "border-style": "dashed"}}),
    ("2026-11-07", {"label": "Kino", "time": "20:00",
                    "stil": {"background-color": "#102030", "color": "#ffeedd"}}),
    ("2026-11-07", {"label": "Lesen", "time": "21:00", "stil": {"color": "#ff8800"}}),
    ("2026-11-09", {"label": "Messe", "bis": "2026-11-11"}),
    ("2026-11-12", {"label": "Omas Geburtstag"}),
]

# Hand-written VEVENTs (other calendars): name → body lines.
HAND = {
    "google_color_only": ["SUMMARY:Teammeeting", "COLOR:tomato"],
    "thunderbird_hex_color": ["SUMMARY:Yoga", "COLOR:#00AA88"],
    "unknown_color_name": ["SUMMARY:Yoga", "COLOR:nocolour"],
    "style_beats_color": ["SUMMARY:Analysis I", "COLOR:red",
                          "X-ZENTRALE-STIL:background-color: #112233"],
    "broken_style_ignores_color": ["SUMMARY:Analysis I", "COLOR:red", "X-ZENTRALE-STIL:kaputt"],
    "style_not_offered": ["SUMMARY:Analysis I", "X-ZENTRALE-STIL:width: 3px"],
    "style_escaped": ["SUMMARY:Analysis I",
                      "X-ZENTRALE-STIL:border-style: none\\; border-color: #ABC"],
    "short_hex_and_old_none": ["SUMMARY:Analysis I",
                               "X-ZENTRALE-STIL:--zentrale-muster: none; color: #FA0"],
    "categories_several": ["SUMMARY:Seminar", "CATEGORIES:arbeit,Outlook-Tag"],
    "categories_custom_case": ["SUMMARY:Chorprobe", "CATEGORIES:  MUSIK "],
    "categories_keine": ["SUMMARY:Seminar", "CATEGORIES:keine"],
    "source_url_only": ["SUMMARY:x", "URL:zentrale://fokus/l_todo"],
    "source_url_project": ["SUMMARY:x", "URL:zentrale://fokus/l_haus/7"],
    "source_bad_art": ["SUMMARY:x", "X-ZENTRALE-QUELLE:zettel:l_todo"],
    "source_beats_url": ["SUMMARY:x", "X-ZENTRALE-QUELLE:liste:l_a", "URL:zentrale://fokus/l_b"],
    "empty_title": ["SUMMARY:"],
    "no_title": [],
    "unicode_course": ["SUMMARY:Äquivalenz-Seminar"],
    "place_in_title": ["SUMMARY:Geigenstunde @ Geigenschule"],
}


def _hand_ics(name, lines):
    body = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//test//EN", "BEGIN:VEVENT",
                        f"UID:{name}@test", "DTSTAMP:20261001T080000Z",
                        "DTSTART;VALUE=DATE:20261110", *lines, "END:VEVENT", "END:VCALENDAR", ""])
    return body


def _case(name, ics_text, layer="termine"):
    stueck = abb.datei_lesen(ics_text.encode("utf-8"))[0]
    d = dict(stueck["daten"])
    span = bool(d.get("bis")) and d.get("bis") != stueck.get("tag")
    entry = {**d, "layer": layer, **({"spanning": True} if span else {})}
    key, group = cc.entry_key(entry), cc.entry_group_key(entry)
    r = cc.resolve(d.get("stil"), key, TABLE, span=span)
    return {
        "name": name, "ics": ics_text, "layer": layer,
        "expect": {
            "label": d.get("label"), "quelle": d.get("quelle"), "kategorie": d.get("kategorie"),
            "kategorie_name": d.get("kategorie_name"), "style": d.get("stil"), "span": span,
            "key": key, "slot": r["slot"], "group_key": group,
            "group_slot": cc.slot_for(group, TABLE), "source": r["source"], "role": r["role"],
            "day": cc.block_colours(r, "day", layer_default=LAYER_DEFAULT),
            "night": cc.block_colours(r, "night", layer_default=LAYER_DEFAULT),
        },
    }


def vectors() -> dict:
    n = iter(range(1, 1000))
    cases = []
    for day, e in WRITTEN:
        uid = f"{next(n):032x}@zentrale"
        ics = abb.termin_kalender(day, e, uid, jetzt=FIXED_NOW).to_ical().decode("utf-8")
        cases.append(_case("written_%s" % cc.course_key(e["label"]) + "_%d" % len(cases), ics))
    cases.append(_case("tentative_layer", abb.termin_kalender(
        "2026-11-13", {"label": "Analysis Nachhilfe?", "time": "10:00"},
        f"{next(n):032x}@zentrale", jetzt=FIXED_NOW).to_ical().decode("utf-8"), layer="uncommitted"))
    for name, lines in HAND.items():
        cases.append(_case(name, _hand_ics(name, lines)))
    keys = ["analysis", "experimentalphysik", "quelle:l_todo", "quelle:l_haus/7", "gruppe:uni",
            "gruppe:custom:musik", "äquivalenz", "geigenstunde", "x", "parkour", "zz", "12"]
    return {
        "description": "Calendar colours, written by scripts/calendar_colour_vectors.py with "
                       "core/calendar_colours.py and core/kalender_ics_abbildung.py. "
                       "All events are made up.",
        "format": cc.FORMAT,
        "slot_count": cc.SLOT_COUNT,
        "short_forms": cc.SHORT_FORMS,
        "group_catalog": kalender_kategorie.KATEGORIEN,
        "layer_default": LAYER_DEFAULT,
        "table": TABLE,
        "table_file": cc.table_text(TABLE),
        "old_flat_table_file": json.dumps({"analysis": 3, "x": 12, "y": True}),
        "parsed_old_flat_table": cc.parse_table(json.dumps({"analysis": 3, "x": 12, "y": True})),
        "fallback_slots": {k: cc.fallback_slot(k) for k in keys},
        "course_keys": {t: cc.course_key(t) for t in (
            "Analysis I @ HS 1", "ExPhy-Übung", "exphy", "Theoretische Physik Ia",
            "Allgemeine Chemie für Nebenfächler (Mo)", "", "  Chor  ", "A/B", "TP Sprechstunde X",
            "Ana Tutorium Y", "Ölkunde: Basics", "Kurs.2 (neu)", "–Gedankenstrich", "Ein Wort")},
        "css3_colours": stil.CSS3_FARBEN,
        "cases": cases,
    }


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = json.dumps(vectors(), ensure_ascii=False, indent=1) + "\n"
    if "--stdout" in argv:
        sys.stdout.write(text)
    else:
        TARGET.write_text(text, encoding="utf-8")
        print(f"{TARGET.relative_to(ROOT)}: written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
