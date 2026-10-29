"""Three-way merge inside one VEVENT, per group of fields (core/vevent_merge,
core/abgleich_vorschlaege.merge_event; memory/betrieb/abgleich_fremde_knoten.md
"Termine vom Handy"). The phone edits line for line like
mobile/lib/kalender/event_edit.dart; here the same by text replacement.
Fixed dates and stamps, never "today" (memory/betrieb/tests.md rule 8)."""
import datetime as dt
import hashlib

from icalendar import Calendar

import abgleich_vorschlaege as vs
import kalender_ics_abbildung as abb
import vevent_merge as vm
from test_abgleich import Welt  # noqa: F401
from test_abgleich_handy import Handy, kalender_welt, welt  # noqa: F401
from test_i18n import _po_entries

FIXED = dt.datetime(2026, 10, 1, 8, 0, tzinfo=dt.timezone.utc)
UID_R = "r" * 32 + "@zentrale"
UID_D = "d" * 32 + "@zentrale"
UID = "a" * 32 + "@zentrale"
REL = f"data/kalender/termine/{UID}.ics"
FOREIGN_ALARM = ("BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:gleich\r\n"
                 "TRIGGER:-PT15M\r\nEND:VALARM\r\n")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _sub(roh: bytes, old: str, new: str) -> bytes:
    assert old.encode() in roh, old
    return roh.replace(old.encode(), new.encode(), 1)


def _phone_stamp(roh: bytes, stamp="20261029T120000Z") -> bytes:
    """What the phone's _touch does: DTSTAMP and LAST-MODIFIED fresh."""
    roh = _sub(roh, "DTSTAMP:20261001T080000Z", f"DTSTAMP:{stamp}")
    return _sub(roh, "LAST-MODIFIED:20261001T080000Z", f"LAST-MODIFIED:{stamp}")


def _routine(aus=()):
    kal = abb.routine_kalender({"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:00",
                                "ende": "18:00", "seit": "2026-11-03", "aus": list(aus)},
                               UID_R, jetzt=FIXED)
    return abb.zusammenfuehren(None, kal, UID_R)


def _deadline():
    kal = abb.termin_kalender("2026-11-19", {"label": "Abgabe", "time": "10:00", "typ": "deadline",
                                             "vorwarnung": 60, "ort": "Uni"}, UID_D, jetzt=FIXED)
    return abb.zusammenfuehren(None, kal, UID_D)


def _move_time(roh: bytes) -> bytes:
    roh = _sub(roh, "DTSTART;TZID=Europe/Berlin:20261103T170000", "DTSTART;TZID=Europe/Berlin:20261103T163000")
    return _sub(roh, "DTEND;TZID=Europe/Berlin:20261103T180000", "DTEND;TZID=Europe/Berlin:20261103T173000")


def _data(roh: bytes) -> dict:
    return abb.datei_lesen(roh)[0]["daten"]


def _merge(b, p, m):
    neu, conflicts = vs.dreiweg(b, p, m)
    if neu is not None:
        Calendar.from_ical(neu)              # always a readable calendar
    return neu, conflicts


# ── The mapping and the merge agree ────────────────────────────────────

def test_copied_constants_stay_equal_to_the_mapping():
    assert vm.X_WARNING == abb.X_VORWARNUNG
    assert vm.WARNING_TEXT == abb.ALARM_TEXT


def test_every_zentrale_property_has_a_group():
    """A new X-ZENTRALE-* field must be grouped on purpose (or else it would
    be merged alone, split from what it belongs to)."""
    grouped = {n for names in vm.GROUPS.values() for n in names}
    for name, value in vars(abb).items():
        if name.startswith("X_") and isinstance(value, str) and value.startswith("X-ZENTRALE-"):
            if value == abb.X_VORWARNUNG:        # lives inside OUR VALARM (deadline group)
                continue
            assert value in grouped, f"{value} ({name}) has no group in core/vevent_merge.GROUPS"
    managed = set(abb.VERWALTET_ABWEICHUNG) - vm.TECHNICAL - vm.KEY
    assert managed <= grouped


def test_every_group_label_has_german_text():
    po = _po_entries()
    for group, msgid in vm.LABELS.items():
        assert msgid in po, f"no German text for group {group}"
    assert vm.OTHER_LABEL in po


# ── Different groups: both sides come in ───────────────────────────────

def test_cloud_adds_note_phone_moves_time_both_visible():
    b = _routine()
    m = _sub(b, "END:VEVENT", "DESCRIPTION:Noten mitbringen\r\nEND:VEVENT")
    p = _phone_stamp(_move_time(b))
    neu, conflicts = _merge(b, p, m)
    assert not conflicts
    assert b"Noten mitbringen" in neu and b"T163000" in neu and b"T170000\r\n" not in neu
    d = _data(neu)
    assert d["time"] == "16:30" and d["ende"] == "17:30"
    assert b"LAST-MODIFIED:20261029T120000Z" in neu          # the later stamp
    assert b"SEQUENCE:1" in neu                              # time changed (RFC 5545)


def test_cloud_foreign_alarm_phone_moves_time_alarm_stays():
    b = _routine()
    m = _sub(b, "END:VEVENT", FOREIGN_ALARM + "END:VEVENT")
    p = _phone_stamp(_move_time(b))
    neu, conflicts = _merge(b, p, m)
    assert not conflicts
    assert neu.count(b"BEGIN:VALARM") == 1 and b"TRIGGER:-PT15M" in neu and b"T163000" in neu


def test_phone_omits_note_and_alarms_while_cloud_unchanged_nothing_lost():
    b = _sub(_routine(), "END:VEVENT", "DESCRIPTION:Notiz\r\n" + FOREIGN_ALARM + "END:VEVENT")
    p = _sub(_sub(b, "DESCRIPTION:Notiz\r\n", ""), FOREIGN_ALARM, "")
    p = _sub(p, "SUMMARY:Geige", "SUMMARY:Geige neu")
    neu, conflicts = _merge(b, p, b)
    assert not conflicts
    assert b"SUMMARY:Geige neu" in neu and b"DESCRIPTION:Notiz" in neu and b"TRIGGER:-PT15M" in neu


def test_phone_clears_place_managed_field_counts_as_change():
    b = _deadline()
    p = _sub(b, "LOCATION:Uni\r\n", "")
    m = _sub(b, "END:VEVENT", "DESCRIPTION:Hinweis\r\nEND:VEVENT")
    neu, conflicts = _merge(b, p, m)
    assert not conflicts
    assert b"LOCATION" not in neu and b"DESCRIPTION:Hinweis" in neu


def test_our_deadline_warning_and_foreign_alarms_are_separate_groups():
    b = _sub(_deadline(), "END:VEVENT", FOREIGN_ALARM + "END:VEVENT")
    p = _sub(b, "TRIGGER:-PT1H", "TRIGGER:-PT2H")                 # phone: our warning
    m = _sub(b, "TRIGGER:-PT15M", "TRIGGER:-PT5M")                # cloud: the foreign one
    neu, conflicts = _merge(b, p, m)
    assert not conflicts
    assert b"TRIGGER:-PT2H" in neu and b"TRIGGER:-PT5M" in neu and neu.count(b"BEGIN:VALARM") == 2


def test_same_change_on_both_sides_is_fine():
    b = _routine()
    p = _phone_stamp(_sub(b, "SUMMARY:Geige", "SUMMARY:Cello"))
    m = _sub(_sub(b, "SUMMARY:Geige", "SUMMARY:Cello"), "END:VEVENT", "DESCRIPTION:x\r\nEND:VEVENT")
    neu, conflicts = _merge(b, p, m)
    assert not conflicts and b"SUMMARY:Cello" in neu and b"DESCRIPTION:x" in neu


def test_untouched_lines_keep_their_bytes():
    b = _routine()
    m = _sub(b, "END:VEVENT", "DESCRIPTION:Noten\r\nEND:VEVENT")
    p = _sub(b, "SUMMARY:Geige", "SUMMARY:Cello")
    neu, _c = _merge(b, p, m)
    assert neu == _sub(m, "SUMMARY:Geige", "SUMMARY:Cello")


# ── Same group, different: conflict, nothing written ───────────────────

def test_both_change_title_differently_conflict():
    b = _routine()
    neu, conflicts = _merge(b, _sub(b, "SUMMARY:Geige", "SUMMARY:Am Handy"),
                            _sub(b, "SUMMARY:Geige", "SUMMARY:Am Laptop"))
    assert neu is None and len(conflicts) == 1 and "(Titel)" in conflicts[0]


def test_both_change_time_differently_conflict():
    b = _routine()
    m = _sub(b, "DTEND;TZID=Europe/Berlin:20261103T180000", "DTEND;TZID=Europe/Berlin:20261103T190000")
    neu, conflicts = _merge(b, _move_time(b), m)
    assert neu is None and "(Zeit)" in conflicts[0]


def test_exdate_and_switched_off_list_are_one_unit():
    """Cloud switches 10 Nov off, phone 17 Nov: both touch the time group →
    conflict (never EXDATE from one side, X-ZENTRALE-AUS from the other)."""
    b = _routine()
    m = _routine(aus=["2026-11-10"])
    p = _routine(aus=["2026-11-17"])
    neu, conflicts = _merge(b, p, m)
    assert neu is None and "(Zeit)" in conflicts[0]


def test_switched_off_list_follows_exdate_when_the_time_comes_from_the_phone():
    """Phone switches 10 Nov back on, forgets X-ZENTRALE-AUS; the cloud only
    added a note → accepted, the list aligned to EXDATE, note kept."""
    b = _routine(aus=["2026-11-10", "2026-11-17"])
    kal = Calendar.from_ical(b)
    ev = kal.walk("VEVENT")[0]
    ev.pop("EXDATE")
    ev.add("EXDATE", abb._ts(abb._datum("2026-11-17"), abb._hhmm("17:00")))
    p = kal.to_ical()
    m = _sub(b, "END:VEVENT", "DESCRIPTION:Noten\r\nEND:VEVENT")
    neu, conflicts = _merge(b, p, m)
    assert not conflicts
    assert _data(neu)["aus"] == ["2026-11-17"] and b"DESCRIPTION:Noten" in neu
    assert vs.x_aus_lesen(Calendar.from_ical(neu).walk("VEVENT")[0].get(abb.X_AUS)) == ["2026-11-17"]


def test_only_technical_fields_differ_nothing_to_do():
    b = _routine()
    m = _sub(b, "END:VEVENT", "DESCRIPTION:Noten\r\nEND:VEVENT")
    neu, conflicts = _merge(b, _phone_stamp(b), m)
    assert not conflicts and neu == m


# ── The whole way: phone → inbox → computer → cloud ────────────────────

def test_phone_moves_time_while_cloud_got_a_note_accepted(kalender_welt):  # noqa: F811
    welt = kalender_welt
    laptop = welt.rechner("laptop")
    h = Handy(welt)
    basis = h.lesen(REL)
    roh = laptop.pfad(f"kalender/termine/{UID}.ics").read_bytes()
    laptop.pfad(f"kalender/termine/{UID}.ics").write_bytes(
        _sub(roh, "END:VEVENT", "DESCRIPTION:Unterlagen mitnehmen\r\nEND:VEVENT"))
    laptop.abgleichen()
    zeile = next(z for z in basis.decode().splitlines() if z.startswith("DTSTART;TZID"))
    neu = _sub(basis, zeile, zeile.replace("T100000", "T093000"))
    h.schreiben(REL, neu, basis_sha=_sha(basis), basis=basis)
    b = laptop.abgleichen()
    assert not b.hinweise
    jetzt = laptop.lesen(f"kalender/termine/{UID}.ics")
    assert "Unterlagen mitnehmen" in jetzt and "T093000" in jetzt
    assert h.quittung(REL)["ergebnis"] == "angenommen"
