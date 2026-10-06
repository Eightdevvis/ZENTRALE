"""
Die Abbildung Kalender-Dict <-> iCalendar, Regel für Regel.

Sasha, 2026-10-06: "bisherige daten übertragen ohne verluste". Jede Regel der
Abbildung (memory/werkzeuge/kalender_ics_bauplan.md) wird hier hin UND zurück
geprüft: was geschrieben wird, muss sich exakt so zurücklesen. Dazu die
Testfixtures aus der Kalender-Session (tests/fixtures/kalender/, khal hat sie
so angezeigt, wie LIESMICH.txt es erwartet) — so wird auch das LESEN von
.ics geprüft, die ZENTRALE nicht selbst geschrieben hat.
"""

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest
from icalendar import Calendar

import kalender_ics_abbildung as A

FIX = Path(__file__).parent / "fixtures" / "kalender" / "vdir"


def _lies(datei):
    st = A.datei_lesen((FIX / datei).read_bytes())
    assert len(st) == 1
    return st[0]


# ── Die Fixtures: so wie khal sie zeigt ────────────────────────────────

def test_fixture_ganztags():
    st = _lies("termine/einheit.ics")
    assert st["art"] == "termin" and st["tag"] == "2026-10-03"
    assert st["daten"] == {"label": "Tag der Deutschen Einheit"}


def test_fixture_termin_mit_ort():
    st = _lies("termine/zahnarzt.ics")
    assert st["daten"] == {"label": "Zahnarzt", "ort": "Praxis Dr. Brandt",
                           "time": "14:00", "ende": "15:00"}


def test_fixture_termin_ueber_drei_tage():
    """Berlin: Fr 18:00 -> So 14:00 — EIN Ereignis, Beginn am ersten, Ende am
    letzten Tag (LIESMICH: 18:00-> / <-> / ->14:00)."""
    st = _lies("termine/berlin.ics")
    assert st["tag"] == "2026-10-09"
    assert st["daten"] == {"label": "Wochenende Berlin", "bis": "2026-10-11",
                           "times": {"2026-10-09": "18:00"},
                           "enden": {"2026-10-11": "14:00"}}


def test_fixture_spanne_mit_zeit_pro_tag():
    """Messe: DAILY;COUNT=3 plus zwei Abweichungen in DERSELBEN Datei.
    LIESMICH: 07. 10-18, 08. 09-17, 09. 10-14 (calcurse verlor die
    Abweichungen — wir nicht)."""
    st = _lies("termine/messe.ics")
    assert st["tag"] == "2026-10-07"
    d = st["daten"]
    assert d["bis"] == "2026-10-09"
    assert d["times"] == {"2026-10-07": "10:00", "2026-10-08": "09:00",
                          "2026-10-09": "10:00"}
    assert d["enden"] == {"2026-10-07": "18:00", "2026-10-08": "17:00",
                          "2026-10-09": "14:00"}


def test_fixture_routinen_haben_einen_anfang():
    """Von außen angelegte Routinen beginnen an ihrem DTSTART."""
    g = _lies("routinen/geige.ics")
    assert g["art"] == "routine"
    assert g["daten"] == {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU,TH",
                          "time": "10:00", "ende": "11:00", "seit": "2026-09-01"}
    p = _lies("routinen/parkour.ics")
    assert p["daten"]["seit"] == "2026-09-05"
    assert p["daten"]["rrule"] == "FREQ=WEEKLY;BYDAY=SA"


# ── Termine hin und zurück ─────────────────────────────────────────────

TERMINE = [
    ("ganztags", "2026-06-03", {"label": "TÜV-Frist"}),
    ("mit zeit", "2026-06-03", {"label": "Arzt", "time": "09:30"}),
    ("zeit+ende+ort", "2026-06-03", {"label": "Arzt", "time": "09:30", "ende": "10:15", "ort": "Praxis"}),
    ("bis mitternacht", "2026-06-03", {"label": "Nacht", "time": "23:00", "ende": "24:00"}),
    ("nur stunde", "2026-07-14", {"label": "Fahrt", "time": "10"}),
    ("ohne fuehrende null", "2026-07-04", {"label": "Früh", "time": "9:30"}),
    ("unlesbare zeit", "2026-07-04", {"label": "Irgendwann", "time": "abends"}),
    ("ende vor beginn", "2026-06-03", {"label": "Krumm", "time": "18:00", "ende": "08:00"}),
    ("ende ohne beginn", "2026-06-03", {"label": "Nur Ende", "ende": "12:00"}),
    ("extras", "2026-06-03", {"label": "X", "tags": ["a", 1], "nix": None, "tief": {"a": {"b": [1, 2]}}}),
    ("absage am termin", "2026-06-03", {"label": "Kurs", "time": "10:00", "absage_noetig": True}),
    ("absage falsch typisiert", "2026-06-03", {"label": "Kurs", "absage_noetig": "ja"}),
    ("sonderzeichen", "2026-06-03", {"label": "Komma, Semi; Back\\slash\nZeile ÄÖÜ ß 漢字 " + "x" * 120, "ort": "a;b,c"}),
    ("leerer titel", "2026-06-03", {"label": ""}),
    ("ohne titel", "2026-06-03", {"time": "10:00"}),
    ("leerer ort", "2026-06-03", {"label": "A", "ort": ""}),
    ("label kein text", "2026-06-03", {"label": 42}),
    ("spanne ganztags", "2026-06-08", {"label": "Ungarn-Reise", "bis": "2026-06-12", "ort": "Ungarn"}),
    ("spanne ein tag", "2026-06-08", {"label": "Eintag", "bis": "2026-06-08"}),
    ("spanne zeit am ersten", "2026-06-08", {"label": "Ab", "bis": "2026-06-10", "times": {"2026-06-08": "18:00"}}),
    ("spanne erste+letzte", "2026-06-08", {"label": "B", "bis": "2026-06-10", "times": {"2026-06-08": "18:00"}, "enden": {"2026-06-10": "14:00"}}),
    ("spanne zeit mitte", "2026-07-13", {"label": "Basel", "bis": "2026-07-17", "times": {"2026-07-14": "10"}}),
    ("spanne mehrere zeiten", "2026-10-07", {"label": "Messe", "bis": "2026-10-09",
                                             "times": {"2026-10-07": "10:00", "2026-10-08": "09:00"},
                                             "enden": {"2026-10-07": "18:00", "2026-10-08": "17:00"}}),
    ("spanne zeit ausserhalb", "2026-06-08", {"label": "C", "bis": "2026-06-10", "times": {"2026-06-01": "10:00", "murks": "11:00"}}),
    ("spanne leere times", "2026-06-08", {"label": "D", "bis": "2026-06-10", "times": {}}),
    ("spanne ende ohne zeit", "2026-06-08", {"label": "E", "bis": "2026-06-10", "enden": {"2026-06-09": "12:00"}}),
    ("spanne mit ende-feld", "2026-06-08", {"label": "F", "bis": "2026-06-10", "ende": "18:00", "time": "09:00"}),
]


@pytest.mark.parametrize("name,tag,e", TERMINE, ids=[t[0] for t in TERMINE])
def test_termin_rundreise(name, tag, e):
    kal = A.termin_kalender(tag, e, "uid-1", pos=4)
    zurueck = A.lesen(Calendar.from_ical(kal.to_ical()))
    assert len(zurueck) == 1
    assert zurueck[0]["art"] == "termin"
    assert zurueck[0]["tag"] == tag
    assert zurueck[0]["daten"] == e
    assert zurueck[0]["pos"] == 4


def test_spanne_ueber_tage_ist_ein_vevent():
    kal = A.termin_kalender("2026-06-08", {"label": "Urlaub", "bis": "2026-06-12"}, "u")
    evs = kal.walk("VEVENT")
    assert len(evs) == 1
    assert evs[0].get("RRULE") is None
    assert evs[0]["DTSTART"].dt == date(2026, 6, 8)
    assert evs[0]["DTEND"].dt == date(2026, 6, 13)        # exklusiv: bis + 1


def test_spanne_mit_zeiten_ist_serie_mit_abweichungen_in_einer_datei():
    """Sashas Entscheidung: NICHT in Einzeltermine zerlegen, und die
    Abweichungen tragen dieselbe UID — sonst bricht vdirsyncer."""
    e = {"label": "Messe", "bis": "2026-10-09",
         "times": {"2026-10-07": "10:00", "2026-10-09": "11:00"}}
    kal = A.termin_kalender("2026-10-07", e, "messe-uid")
    evs = kal.walk("VEVENT")
    master = [x for x in evs if x.get("RECURRENCE-ID") is None]
    abw = [x for x in evs if x.get("RECURRENCE-ID") is not None]
    assert len(master) == 1 and len(abw) == 2
    assert master[0]["RRULE"].to_ical() == b"FREQ=DAILY;COUNT=3"
    assert {str(x["UID"]) for x in evs} == {"messe-uid"}
    assert all(str(x["SUMMARY"]) == "Messe" for x in abw)   # Google zeigt sie einzeln


def test_zeiten_tragen_die_zone_berlin():
    kal = A.termin_kalender("2026-06-03", {"label": "A", "time": "09:30"}, "u")
    text = kal.to_ical().decode()
    assert "DTSTART;TZID=Europe/Berlin:20260603T093000" in text
    assert "BEGIN:VTIMEZONE" in text and "TZID:Europe/Berlin" in text


def test_stunde_ohne_minuten_zeigt_google_die_richtige_zeit():
    """Sashas echte Daten haben "10", "18", "8". Google soll 10:00 zeigen,
    ZENTRALE weiter "10" — beides ohne Verlust."""
    kal = A.termin_kalender("2026-07-14", {"label": "Fahrt", "time": "10"}, "u")
    assert "DTSTART;TZID=Europe/Berlin:20260714T100000" in kal.to_ical().decode()


def test_utc_wird_in_ortszeit_gelesen():
    roh = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\nBEGIN:VEVENT\r\nUID:z\r\n"
           b"DTSTAMP:20261001T000000Z\r\nSUMMARY:Call\r\nDTSTART:20260715T160000Z\r\n"
           b"DTEND:20260715T170000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    st = A.datei_lesen(roh)[0]
    assert st["daten"] == {"label": "Call", "time": "18:00", "ende": "19:00"}   # Sommerzeit


def test_floating_time_bleibt_wie_sie_ist():
    st = _lies("termine/kino.ics")
    assert st["daten"]["time"] == "19:00"


def test_winterzeit():
    kal = A.termin_kalender("2026-12-01", {"label": "W", "time": "08:00", "ende": "09:00"}, "u")
    ev = kal.walk("VEVENT")[0]
    assert ev["DTSTART"].dt.utcoffset().total_seconds() == 3600


@pytest.mark.parametrize("tag,e", [
    ("2026-07-07", {"label": "Verdreht", "bis": "2026-07-01"}),
    ("2026-07-07", {"label": "Kaputt", "bis": "nie"}),
    ("2026-07-07", {"label": "T", "bis": "2026-07-08", "times": ["10:00"]}),
    ("2026-13-01", {"label": "Kein Datum"}),
    ("gestern", {"label": "Kein Datum"}),
])
def test_nicht_abbildbares_wird_gemeldet(tag, e):
    with pytest.raises(A.NichtAbbildbar):
        A.termin_kalender(tag, e, "u")


# ── Routinen hin und zurück ────────────────────────────────────────────

PAUSEN = [(0, {"label": "Geigenstunde", "von": "2026-06-29", "bis": "2026-08-07", "grund": "Sommerferien"}),
          (3, {"label": "Geigenstunde", "von": "2026-10-05", "bis": "kaputt"})]

ROUTINEN = [
    ("woechentlich", {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45"}, []),
    ("mit ende ort absage", {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45",
                             "ende": "18:30", "ort": "Geigenschule", "absage_noetig": True}, PAUSEN),
    ("mehrere tage + aus", {"label": "Fahrschule", "rrule": "FREQ=WEEKLY;BYDAY=TU,TH", "time": "19:00",
                            "ende": "20:00", "aus": ["2026-06-30", "2026-07-14", "kein-datum", "2026-07-14"]}, []),
    ("leeres aus", {"label": "P", "rrule": "FREQ=WEEKLY;BYDAY=WE", "aus": []}, []),
    ("monatlich", {"label": "Miete", "rrule": "FREQ=MONTHLY;BYMONTHDAY=1"}, []),
    ("zweiter dienstag", {"label": "Treffen", "rrule": "FREQ=MONTHLY;BYDAY=2TU", "time": "19:30"}, []),
    ("umgeordnete regel", {"label": "Weihnachten", "rrule": "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25"}, []),
    ("until", {"label": "Kurs", "rrule": "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261231", "time": "08:00"}, []),
    ("until ganztags", {"label": "Kurs", "rrule": "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261231T000000"}, []),
    ("count", {"label": "Reha", "rrule": "FREQ=WEEKLY;COUNT=6;BYDAY=MO,FR", "time": "07:00"}, []),
    ("mit seit", {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU,TH", "time": "10:00", "ende": "11:00",
                  "seit": "2026-09-01"}, []),
    ("ende 24", {"label": "Nachtschicht", "rrule": "FREQ=WEEKLY;BYDAY=FR", "time": "22:00", "ende": "24:00"}, []),
    ("nur stunde", {"label": "Lauf", "rrule": "FREQ=WEEKLY;BYDAY=SA", "time": "8"}, []),
    ("extras", {"label": "X", "rrule": "FREQ=DAILY", "notiz": "Dauerauftrag", "absage_noetig": False}, []),
    ("abweichungen", {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45", "ende": "18:30",
                      "abweichungen": {"2026-10-13": {"tag": "2026-10-14", "time": "16:00", "ende": "17:00"},
                                       "2026-10-20": {"entfaellt": True},
                                       "2026-10-27": {"tag": "2026-10-27", "time": "18:00", "ort": "Anderswo"}}}, []),
    ("abweichung murks", {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU",
                          "abweichungen": {"kein": {"tag": "x"}}}, []),
]


@pytest.mark.parametrize("name,r,pausen", ROUTINEN, ids=[t[0] for t in ROUTINEN])
def test_routine_rundreise(name, r, pausen):
    kal = A.routine_kalender(r, "uid-r", pos=9, pausen=pausen, anker=date(2026, 6, 3))
    zurueck = A.lesen(Calendar.from_ical(kal.to_ical()))
    assert len(zurueck) == 1
    st = zurueck[0]
    assert st["art"] == "routine"
    assert st["daten"] == r
    assert st["pos"] == 9
    assert sorted(st["pausen"], key=lambda p: p[0]) == sorted(pausen, key=lambda p: p[0])


def test_routine_ohne_anfang_bekommt_ausgerichteten_anker():
    """DTSTART ist nach RFC 5545 immer ein Vorkommen — also auf den ersten
    echten Dienstag ab dem Anker, nicht auf den Anker selbst (Mittwoch)."""
    kal = A.routine_kalender({"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45"},
                             "u", anker=date(2026, 6, 3))
    ev = kal.walk("VEVENT")[0]
    assert ev["DTSTART"].dt.date() == date(2026, 6, 9)
    assert str(ev[A.X_OHNE_ANFANG]) == "TRUE"


def test_aus_und_pausen_werden_exdates():
    r = {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45",
         "aus": ["2026-09-01"]}
    kal = A.routine_kalender(r, "u", pausen=PAUSEN[:1], anker=date(2026, 6, 3))
    ev = kal.walk("VEVENT")[0]
    tage = sorted(v.dt.date() for liste in A._liste(ev.get("EXDATE")) for v in liste.dts)
    # 6 Dienstage in den Sommerferien + der eine deaktivierte
    assert tage == [date(2026, 6, 30), date(2026, 7, 7), date(2026, 7, 14), date(2026, 7, 21),
                    date(2026, 7, 28), date(2026, 8, 4), date(2026, 9, 1)]
    # mit derselben Uhrzeit und Zone wie DTSTART (sonst trifft Google nichts)
    v = A._liste(ev.get("EXDATE"))[0].dts[0].dt
    assert (v.hour, v.minute, str(v.tzinfo)) == (17, 45, "Europe/Berlin")


def test_absage_noetig_als_x_property():
    kal = A.routine_kalender({"label": "G", "rrule": "FREQ=WEEKLY;BYDAY=TU", "absage_noetig": True}, "u")
    assert "X-ZENTRALE-ABSAGE-NOETIG:TRUE" in kal.to_ical().decode()


def test_kaputte_regel_ist_nicht_abbildbar():
    with pytest.raises(A.NichtAbbildbar):
        A.routine_kalender({"label": "X", "rrule": "FREQ=BLOEDSINN"}, "u")


# ── Was von außen kommt, gewinnt ───────────────────────────────────────

def _bearbeiten(kal, **neu):
    ev = kal.walk("VEVENT")[0]
    for k, v in neu.items():
        k = k.upper()
        if k in ev:
            del ev[k]
        ev.add(k, v)
    return A.lesen(Calendar.from_ical(kal.to_ical()))[0]["daten"]


def test_am_handy_verschobene_zeit_schlaegt_den_rohtext():
    """"10" steht als Rohtext dabei — verschiebt Sasha den Termin am Handy
    auf 11:00, gilt 11:00, nicht der alte Rohtext."""
    kal = A.termin_kalender("2026-07-14", {"label": "Fahrt", "time": "10"}, "u")
    from zoneinfo import ZoneInfo
    d = _bearbeiten(kal, dtstart=datetime(2026, 7, 14, 11, 0, tzinfo=ZoneInfo("Europe/Berlin")))
    assert d["time"] == "11:00"


def test_am_handy_umbenannt_schlaegt_extras_nicht():
    """Extras füllen nur Lücken — ein neuer Titel bleibt der neue Titel."""
    kal = A.termin_kalender("2026-06-03", {"label": "Alt", "tags": ["x"]}, "u")
    d = _bearbeiten(kal, summary="Neu")
    assert d == {"label": "Neu", "tags": ["x"]}


def test_umgeordnete_regel_gilt_nur_solange_unveraendert():
    kal = A.routine_kalender({"label": "W", "rrule": "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25"}, "u")
    d = _bearbeiten(kal, rrule={"FREQ": "YEARLY", "BYMONTH": 12, "BYMONTHDAY": 24})
    assert d["rrule"] == "FREQ=YEARLY;BYMONTHDAY=24;BYMONTH=12"


def test_am_handy_geloeschter_einzeltermin_gilt_als_deaktiviert():
    """EXDATE ohne Eintrag in X-ZENTRALE-AUS: jemand hat am Handy "nur diesen
    Termin löschen" gedrückt. In ZENTRALE ist das 'aus'."""
    from zoneinfo import ZoneInfo
    kal = A.routine_kalender({"label": "G", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45"},
                             "u", anker=date(2026, 6, 3))
    ev = kal.walk("VEVENT")[0]
    ev.add("EXDATE", [datetime(2026, 9, 8, 17, 45, tzinfo=ZoneInfo("Europe/Berlin"))])
    d = A.lesen(Calendar.from_ical(kal.to_ical()))[0]["daten"]
    assert d["aus"] == ["2026-09-08"]


def test_x_properties_weg_verlieren_den_termin_nicht():
    """Ungetestet ist, ob Google X-ZENTRALE-* behält. Wirft es sie weg, bleibt
    der Termin trotzdem vollständig lesbar — nur ohne die Zusatzbedeutung."""
    kal = A.routine_kalender({"label": "G", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45",
                              "absage_noetig": True, "aus": ["2026-09-08"]},
                             "u", pausen=PAUSEN[:1], anker=date(2026, 6, 3))
    ev = kal.walk("VEVENT")[0]
    for k in [k for k in ev if k.startswith("X-ZENTRALE-")]:
        del ev[k]
    st = A.lesen(Calendar.from_ical(kal.to_ical()))[0]
    d = st["daten"]
    assert d["label"] == "G" and d["time"] == "17:45" and d["rrule"] == "FREQ=WEEKLY;BYDAY=TU"
    assert "2026-09-08" in d["aus"]                # EXDATE bleibt -> deaktiviert
    assert "2026-07-07" in d["aus"]                # auch die Ferien-Dienstage


def test_google_ergaenzt_ein_ende():
    """Bekannte, dokumentierte Folge: setzt der Server bei einem Termin ohne
    Ende eins (z. B. +1 h), hat ZENTRALE danach ein Ende."""
    kal = A.termin_kalender("2026-06-03", {"label": "A", "time": "09:00"}, "u")
    from zoneinfo import ZoneInfo
    d = _bearbeiten(kal, dtend=datetime(2026, 6, 3, 10, 0, tzinfo=ZoneInfo("Europe/Berlin")))
    assert d == {"label": "A", "time": "09:00", "ende": "10:00"}


# ── Zusammenführen: fremde Inhalte überleben ein Zurückschreiben ───────

ALT = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Google Inc//Google Calendar//EN\r\n"
       b"X-WR-CALNAME:Termine\r\n"
       b"BEGIN:VEVENT\r\nUID:u1\r\nDTSTAMP:20261001T000000Z\r\nSUMMARY:Alt\r\n"
       b"DTSTART;VALUE=DATE:20261010\r\nDESCRIPTION:Notiz vom Handy\r\n"
       b"ATTENDEE:mailto:a@example.org\r\nATTENDEE:mailto:b@example.org\r\n"
       b"X-GOOGLE-ETWAS:bleibt\r\n"
       b"BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:Erinnerung\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\n"
       b"END:VEVENT\r\n"
       b"BEGIN:VEVENT\r\nUID:fremd\r\nDTSTAMP:20261001T000000Z\r\nSUMMARY:Anderer\r\n"
       b"DTSTART;VALUE=DATE:20261011\r\nEND:VEVENT\r\n"
       b"END:VCALENDAR\r\n")


def test_zusammenfuehren_behaelt_fremdes():
    neu = A.termin_kalender("2026-10-12", {"label": "Neu", "time": "09:00"}, "u1")
    text = A.zusammenfuehren(ALT, neu, "u1").decode()
    kal = Calendar.from_ical(text)
    u1 = [e for e in kal.walk("VEVENT") if str(e["UID"]) == "u1"][0]
    assert str(u1["SUMMARY"]) == "Neu"                         # verwaltet: neu
    assert u1["DTSTART"].dt.date() == date(2026, 10, 12)
    assert str(u1["DESCRIPTION"]) == "Notiz vom Handy"         # fremd: bleibt
    assert len(u1["ATTENDEE"]) == 2                            # alle Vorkommen
    assert str(u1["X-GOOGLE-ETWAS"]) == "bleibt"
    assert u1.subcomponents and u1.subcomponents[0].name == "VALARM"
    assert any(str(e["UID"]) == "fremd" for e in kal.walk("VEVENT"))
    assert "X-WR-CALNAME:Termine" in text
    # und ZENTRALE liest den eigenen Teil weiter exakt
    st = [s for s in A.lesen(kal) if s["uid"] == "u1"][0]
    assert st["daten"] == {"label": "Neu", "time": "09:00"}


def test_zusammenfuehren_mit_kaputter_alter_datei():
    neu = A.termin_kalender("2026-10-12", {"label": "Neu"}, "u1")
    assert A.zusammenfuehren(b"das ist kein icalendar", neu, "u1") == neu.to_ical()


def test_geaendert_um_ist_utc():
    kal = A.termin_kalender("2026-06-03", {"label": "A"}, "u",
                            jetzt=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc))
    assert A.geaendert_um(kal.walk("VEVENT")[0]) == datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
