"""Termintyp deadline über die KI-Werkzeuge (2026-10-20).

Der Kern (core/kalender_deadline.py, tests/test_kalender_deadline.py) kann
Deadlines seit a9432c7; hier, dass die erzeugten Kalender-Werkzeuge typ und
vorwarnung durchreichen: anlegen, ändern, zurück auf normal, Fehlercodes mit
dem nächsten Schritt, read_calendar zeigt sie.
"""
import copy
import re
from datetime import date, timedelta

import pytest

import fehlercodes
import kalender
import ki_kalender
import ki_werkzeuge  # noqa: F401  — meldet die Ausführer an
import werkzeug_befund
import werkzeug_register

pytestmark = pytest.mark.kalender_beide

# Fest in der Zukunft: kein Ergebnis hängt am heutigen Datum (Regel 8).
TAG = (date.today() + timedelta(days=40)).isoformat()


@pytest.fixture(autouse=True)
def gross():
    werkzeug_register.erzeugte_einsetzen(True)
    marke = werkzeug_befund.schiene_setzen("gross")
    yield
    werkzeug_befund.schiene_zuruecksetzen(marke)


def tun(name, **args):
    return ki_werkzeuge._verteilen(name, args)


def kennung(text, art="t"):
    return re.findall(r"#(%s[0-9a-f]+)" % art, text)[0]


def _eintrag(k):
    s, fehler = ki_kalender.finden(k)
    assert s is not None, fehler
    return s.roh


def _stand():
    return copy.deepcopy(kalender._load_raw())


def _deadline(**mehr):
    r = tun("add_calendar_entry", day=TAG, label="Analysis HÜ", time="23:59",
            kategorie="keine", typ="deadline", **mehr)
    assert r.status == "ok", r
    return r


def test_deadline_anlegen():
    r = _deadline(vorwarnung="2d")
    assert "23:59" in r and "(Deadline, Vorwarnung 2d)" in r and "EINGETRAGEN" in r, r
    assert "Kein Ende angegeben" not in r          # eine Deadline hat nie eins
    e = _eintrag(kennung(r))
    assert e["typ"] == "deadline" and e["vorwarnung"] == 2 * 1440 and not e.get("ende")


def test_deadline_ohne_vorwarnung_nimmt_die_vorgabe():
    e = _eintrag(kennung(_deadline()))
    assert e["vorwarnung"] == 3 * 1440


def test_read_calendar_zeigt_die_deadline():
    _deadline()
    text = tun("read_calendar", start_date=TAG, end_date=TAG)
    assert "Analysis HÜ" in text and "deadline · Vorwarnung 3d" in text, text


def test_termin_zur_deadline_machen_nimmt_das_ende_weg():
    r = tun("add_calendar_entry", day=TAG, label="Abgabe", time="10:00", ende="11:00",
            kategorie="keine")
    k = kennung(r)
    r = tun("edit_calendar_entry", kennung=k, typ="deadline", time="12:00", vorwarnung="12h")
    assert r.status == "ok", r
    e = _eintrag(k)
    assert e["typ"] == "deadline" and e["vorwarnung"] == 720
    assert e["time"] == "12:00" and not e.get("ende")


def test_nur_die_vorwarnung_aendern():
    k = kennung(_deadline())
    r = tun("edit_calendar_entry", kennung=k, vorwarnung="1d12h")
    assert r.status == "ok" and "Vorwarnung 1d12h" in r, r
    assert _eintrag(k)["vorwarnung"] == 2160


def test_typ_normal_entfernt_beide_felder():
    k = kennung(_deadline(vorwarnung="5d"))
    r = tun("edit_calendar_entry", kennung=k, typ="normal")
    assert r.status == "ok" and "Deadline" not in r, r
    e = _eintrag(k)
    assert "typ" not in e and "vorwarnung" not in e, e


def test_routine_als_deadline_anlegen_und_zurueck():
    von = date.today() + timedelta(days=30)
    r = tun("add_calendar_routine", label="Übungsblatt", rrule="FREQ=WEEKLY;BYDAY=FR",
            time="12:00", von=von.isoformat(), bis=(von + timedelta(days=60)).isoformat(),
            kategorie="keine", typ="deadline", vorwarnung="1d")
    assert r.status == "ok" and "(Deadline, Vorwarnung 1d)" in r, r
    k = kennung(r, "r")
    assert _eintrag(k)["typ"] == "deadline"
    r = tun("edit_calendar_routine", kennung=k, aktion="aendern", typ="normal")
    assert r.status == "ok", r
    assert not _eintrag(k).get("typ")


def test_routine_typ_nicht_fuer_einzelne_tage():
    von = date.today() + timedelta(days=30)
    r = tun("add_calendar_routine", label="Sport", rrule="FREQ=WEEKLY;BYDAY=MO",
            time="18:00", von=von.isoformat(), bis=(von + timedelta(days=60)).isoformat(),
            kategorie="keine")
    vorher = _stand()
    r = tun("edit_calendar_routine", kennung=kennung(r, "r"), aktion="aendern",
            typ="deadline", nur_am=von.isoformat())
    assert r.code == "K-UNBEKANNTES-FELD", r
    assert _stand() == vorher


@pytest.mark.parametrize("args, code", [
    ({"typ": "deadline"}, "K-DEADLINE-OHNE-ZEIT"),
    ({"typ": "deadline", "time": "10:00", "ende": "11:00"}, "K-DEADLINE-MIT-ENDE"),
    ({"typ": "deadline", "time": "10:00", "vorwarnung": "bald"}, "K-VORWARNUNG-UNGUELTIG"),
    ({"typ": "frist", "time": "10:00"}, "K-TYP-UNBEKANNT"),
])
def test_fehlercodes_kommen_mit_dem_naechsten_schritt(args, code):
    vorher = _stand()
    r = tun("add_calendar_entry", day=TAG, label="Abgabe", kategorie="keine", **args)
    assert r.status == "fehlgeschlagen" and r.code == code, r
    assert "ABGEBROCHEN" in r and _stand() == vorher
    if code != "K-TYP-UNBEKANNT":          # der kommt aus der Schema-Prüfung (enum)
        assert fehlercodes.CODES[code][1] in r, r
    if code == "K-DEADLINE-OHNE-ZEIT":
        assert "23:59" in r


def test_mehrtaegig_kann_keine_deadline_sein():
    bis = (date.fromisoformat(TAG) + timedelta(days=2)).isoformat()
    assert kalender.add_span("termine", TAG, bis, "Reise")
    r = tun("edit_calendar_entry", day=TAG, label="Reise", typ="deadline", time="12:00")
    assert r.code == "K-DEADLINE-SPANNE", r
    assert fehlercodes.CODES["K-DEADLINE-SPANNE"][1] in r
    e = kalender.entries_in_range(date.fromisoformat(TAG), date.fromisoformat(TAG))[TAG][0]
    assert not e.get("typ") and not e.get("time")       # nichts geändert


def test_frage_nennt_die_deadline():
    w = werkzeug_register.eintrag("add_calendar_entry")
    frage = w.frage({"day": TAG, "label": "Abgabe", "time": "23:59", "kategorie": "keine",
                     "typ": "deadline", "vorwarnung": "2d"})
    assert "als Deadline, Vorwarnung 2d" in frage, frage
