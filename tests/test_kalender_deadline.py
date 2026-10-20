"""
Termintyp „deadline" im Kern (core/kalender_deadline.py, 20.10.2026).

Sasha: „ne deadline is ja ne ganz andere art von termin … rot leuchten in
einem zeitfenster was man selbst vorher einstellen kann". Geprüft:
  * .ics hin und zurück verlustfrei: X-ZENTRALE-TYP, DTEND = DTSTART, die
    Vorwarnung als Standard-VALARM (TRIGGER:-P3D) — auch nach einem Server,
    der ein Ende dazugibt oder die Marke am Alarm verwirft;
  * fremde Alarme bleiben, unsere werden ersetzt und nie vermehrt;
  * Ablehnungen (ohne Uhrzeit, mit Ende, mehrtägig) schreiben nichts;
  * eine Deadline kollidiert nie; im Vorwarn-Fenster EIN Alarm, außerhalb
    keiner (Uhr über core/uhr.py gestellt, datumsunabhängig);
  * Imprint/KI-Lesen: „[deadline] 23:59 Analysis HÜ (in 2 Tagen)";
  * /api/calendar liefert typ/vorwarnung, POST /api/calendar/typ schaltet.
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest
from icalendar import Calendar

import kalender
import kalender_deadline as kd
import kalender_ics_abbildung as abb
import kalender_kennung as kk
import uhr
from kalender_fehler import KalenderAbgelehnt

# Fester Tag, damit nichts vom heutigen Datum abhängt (tests.md Regel 8).
TAG = date(2026, 10, 23)                 # ein Freitag
JETZT = datetime(2026, 10, 21, 12, 0)    # zwei Tage und knapp 12 h davor


# ── reine Rechnung ─────────────────────────────────────────────────────
def test_dauer_lesen_und_schreiben():
    assert kd.dauer_lesen("3d") == 3 * 1440
    assert kd.dauer_lesen("12h") == 720
    assert kd.dauer_lesen("1d12h") == 2160
    assert kd.dauer_lesen("90m") == 90 and kd.dauer_lesen("90") == 90
    assert kd.dauer_lesen("2 tage") == 2880
    assert kd.dauer_lesen("bald") is None and kd.dauer_lesen("") is None
    for m in (0, 45, 90, 720, 2160, 4320):
        assert kd.dauer_lesen(kd.dauer_text(m)) == m
    with pytest.raises(KalenderAbgelehnt) as e:
        kd.vorwarnung_pruefen("400d")
    assert e.value.code == "VORWARNUNG-UNGUELTIG"


def test_rest_text_auf_den_tag_genau():
    e = {"label": "Analysis HÜ", "time": "23:59", "typ": "deadline", "vorwarnung": 4320}
    assert kd.rest_text(e, TAG, JETZT) == "in 2 Tagen"
    assert kd.rest_text(e, TAG, JETZT + timedelta(days=1)) == "morgen"
    assert kd.rest_text(e, TAG, datetime(2026, 10, 23, 21, 0)) == "heute, in 2 h"
    assert kd.rest_text(e, TAG, datetime(2026, 10, 23, 23, 30)) == "heute, in 29 min"
    assert kd.rest_text(e, TAG, datetime(2026, 10, 24, 0, 1)) == "überschritten"
    assert kd.im_fenster(e, TAG, JETZT)
    assert not kd.im_fenster(e, TAG, JETZT - timedelta(days=2))
    assert not kd.im_fenster(e, TAG, datetime(2026, 10, 24, 0, 1))


# ── .ics hin und zurück ────────────────────────────────────────────────
def _termin(**mehr):
    return {"label": "Analysis HÜ", "time": "23:59", "typ": "deadline",
            "vorwarnung": 4320, **mehr}


def test_ics_termin_hin_und_zurueck_mit_valarm():
    kal = abb.termin_kalender(TAG.isoformat(), _termin(), "u1@zentrale")
    roh = kal.to_ical().decode()
    assert "X-ZENTRALE-TYP:DEADLINE" in roh
    assert "BEGIN:VALARM" in roh and "TRIGGER:-P3D" in roh and "ACTION:DISPLAY" in roh
    ev = kal.walk("VEVENT")[0]
    assert ev["DTEND"].dt == ev["DTSTART"].dt          # Zeitpunkt, Dauer 0
    gelesen = abb.lesen(Calendar.from_ical(kal.to_ical()))
    assert gelesen[0]["daten"] == _termin()


def test_ics_routine_und_vorwarnung_null():
    r = {"label": "Abgabe Blatt", "rrule": "FREQ=WEEKLY;BYDAY=FR", "time": "12:00",
         "seit": TAG.isoformat(), "typ": "deadline", "vorwarnung": 0}
    kal = abb.routine_kalender(r, "u2@zentrale")
    assert "TRIGGER:P0D" in kal.to_ical().decode() or "TRIGGER:PT0S" in kal.to_ical().decode()
    assert abb.lesen(Calendar.from_ical(kal.to_ical()))[0]["daten"] == r


def test_ics_server_gibt_ende_dazu_und_verwirft_die_marke():
    """Google gibt Terminen gern eine Stunde und kennt unsere Marke am
    VALARM vielleicht nicht — Deadline und Vorwarnung bleiben trotzdem."""
    roh = abb.termin_kalender(TAG.isoformat(), _termin(), "u3@zentrale").to_ical().decode()
    fremd = (roh.replace("X-ZENTRALE-VORWARNUNG:TRUE\r\n", "")
             .replace("DTEND;TZID=Europe/Berlin:20261023T235900",
                      "DTEND;TZID=Europe/Berlin:20261024T005900"))
    assert fremd != roh
    daten = abb.lesen(Calendar.from_ical(fremd.encode()))[0]["daten"]
    assert daten == _termin()


def test_ics_zusammenfuehren_behaelt_fremde_alarme_und_vermehrt_unsere_nicht():
    alt = abb.termin_kalender(TAG.isoformat(), _termin(), "u4@zentrale").to_ical().decode()
    handy = ("BEGIN:VALARM\r\nACTION:AUDIO\r\nTRIGGER:-PT30M\r\nEND:VALARM\r\n"
             # unsere, nach einem Server ohne Marke und mit anderem Text
             "BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:This is an event reminder\r\n"
             "TRIGGER:-P3D\r\nEND:VALARM\r\n")
    alt = alt.replace("BEGIN:VALARM", handy + "BEGIN:VALARM", 1)
    for _ in range(3):                                  # mehrmals schreiben
        neu = abb.termin_kalender(TAG.isoformat(), _termin(vorwarnung=720), "u4@zentrale")
        alt = abb.zusammenfuehren(alt.encode(), neu, "u4@zentrale").decode()
    ev = Calendar.from_ical(alt.encode()).walk("VEVENT")[0]
    trigger = sorted(str(a.get("TRIGGER").to_ical().decode()) for a in ev.subcomponents)
    assert trigger == ["-PT12H", "-PT30M"]               # Handy-Alarm bleibt, unserer neu
    # zurück zum normalen Termin: unser Alarm geht, der fremde bleibt
    normal = abb.termin_kalender(TAG.isoformat(), {"label": "Analysis HÜ", "time": "23:59"},
                                 "u4@zentrale")
    ev = Calendar.from_ical(abb.zusammenfuehren(alt.encode(), normal, "u4@zentrale")
                            ).walk("VEVENT")[0]
    assert [str(a.get("TRIGGER").to_ical().decode()) for a in ev.subcomponents] == ["-PT30M"]


# ── Kern mit Speicher ──────────────────────────────────────────────────
@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return tmp_path


def _stand(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != ".zentrale.lock"}


def _tag(iso):
    d = date.fromisoformat(iso)
    return kalender.entries_in_range(d, d).get(iso, [])


@pytest.mark.kalender_beide
def test_anlegen_mit_vorgabe_und_ablehnungen_schreiben_nichts(cal):
    assert kalender.add_entry("termine", TAG.isoformat(), "Analysis HÜ", time="23:59",
                              typ="deadline")
    e = _tag(TAG.isoformat())[0]
    assert (e["typ"], e["vorwarnung"]) == ("deadline", kd.VORWARNUNG_STANDARD)
    vorher = _stand(cal)
    for kwargs, code in ((dict(time=None), "DEADLINE-OHNE-ZEIT"),
                         (dict(time="10:00", ende="11:00"), "DEADLINE-MIT-ENDE"),
                         (dict(time="10:00", vorwarnung="bald"), "VORWARNUNG-UNGUELTIG"),
                         (dict(time="10:00", typ="frist"), "TYP-UNBEKANNT")):
        kw = {"typ": "deadline", **kwargs}
        with pytest.raises(KalenderAbgelehnt) as ex:
            kalender.add_entry("termine", TAG.isoformat(), "X", **kw)
        assert ex.value.code == code, kwargs
    with pytest.raises(KalenderAbgelehnt) as ex:
        kalender.add_span("termine", "2026-10-20", "2026-10-22", "Woche", typ="deadline")
    assert ex.value.code == "DEADLINE-SPANNE"
    assert _stand(cal) == vorher


@pytest.mark.kalender_beide
def test_typ_umschalten_per_kennung(cal):
    kalender.add_entry("termine", TAG.isoformat(), "Kino", time="19:00", ende="21:00")
    k = kk.alle_eintraege()[0]["kennung"]
    vorher = _stand(cal)
    with pytest.raises(KalenderAbgelehnt) as ex:
        kk.typ_setzen(k, "deadline")
    assert ex.value.code == "DEADLINE-MIT-ENDE" and _stand(cal) == vorher
    e = kk.eintrag_aendern(k, ende="", typ="deadline", vorwarnung="1d12h")
    assert (e["typ"], e["vorwarnung"], e.get("ende")) == ("deadline", 2160, None)
    assert kk.typ_setzen(k, "deadline", vorwarnung=60)["vorwarnung"] == 60
    with pytest.raises(KalenderAbgelehnt) as ex:
        kk.eintrag_aendern(k, ende="23:00")
    assert ex.value.code == "DEADLINE-MIT-ENDE"
    e = kk.typ_setzen(k, "normal")
    assert "typ" not in e and "vorwarnung" not in e
    with pytest.raises(KalenderAbgelehnt) as ex:
        kk.typ_setzen(k, None)
    assert ex.value.code == "TYP-UNBEKANNT"


@pytest.mark.kalender_beide
def test_routine_als_deadline_jede_woche(cal):
    import kalender_bearbeiten as kb
    assert kb.routine_neu("termine", "Abgabe Blatt", TAG.isoformat(), "w", time="12:00",
                          typ="deadline", vorwarnung="2d")
    tage = kalender.entries_in_range(TAG, TAG + timedelta(days=7))
    occ = [e for es in tage.values() for e in es]
    assert len(occ) == 2 and all(e["typ"] == "deadline" and e["vorwarnung"] == 2880
                                 for e in occ)


@pytest.mark.kalender_beide
def test_keine_kollision_und_alarm_nur_im_fenster(cal):
    iso = TAG.isoformat()
    kalender.add_entry("termine", iso, "Vorlesung", time="23:00", ende="23:59")
    kalender.add_entry("termine", iso, "Analysis HÜ", time="23:30", typ="deadline",
                       vorwarnung=3 * 1440)
    assert kalender.find_collisions(_tag(iso)) == []
    assert kalender.conflicts_for_proposed("termine", iso, "Neu", "23:15", "23:45") \
        and all("Analysis" not in z for z in
                kalender.conflicts_for_proposed("termine", iso, "Neu", "23:15", "23:45"))
    with uhr.gestellt(datetime(2026, 10, 19, 12, 0)):          # 4 Tage davor
        assert not [a for a in kalender.open_alarms() if a["kind"] == "Deadline"]
    with uhr.gestellt(JETZT):
        dl = [a for a in kalender.open_alarms() if a["kind"] == "Deadline"]
        assert [a["text"] for a in dl] == ["Deadline Analysis HÜ in 2 Tagen (Fr 23.10. 23:30)"]
        id_1 = dl[0]["id"]
        uhr.vorstellen(hours=3)                                 # gleicher Tag → gleiche id
        assert [a["id"] for a in kalender.open_alarms() if a["kind"] == "Deadline"] == [id_1]
        uhr.vorstellen(days=1)
        assert [a["text"] for a in kalender.open_alarms() if a["kind"] == "Deadline"] == [
            "Deadline Analysis HÜ morgen (Fr 23.10. 23:30)"]
        uhr.vorstellen(days=2)                                  # vorbei: kein Alarm mehr
        assert not [a for a in kalender.open_alarms() if a["kind"] == "Deadline"]


@pytest.mark.kalender_beide
def test_imprint_und_ki_lesen(cal):
    kalender.add_entry("termine", TAG.isoformat(), "Analysis HÜ", time="23:59",
                       typ="deadline")
    with uhr.gestellt(JETZT):
        text = kalender.render_range_for_tool(TAG, TAG)
        assert "[deadline] 23:59 Analysis HÜ (in 2 Tagen)" in text
        imp = kalender.imprint_for_prompt(tage=2)
        assert "[deadline] 23:59 Analysis HÜ (in 2 Tagen)" in imp
        assert "Zeitpunkt" in imp
        import ki_kalender
        zeile = ki_kalender._vorkommen_zeile(_tag(TAG.isoformat())[0], None, TAG.isoformat())
        assert "deadline · Vorwarnung 3d" in zeile and zeile.endswith("(in 2 Tagen)")
    with uhr.gestellt(datetime(2026, 10, 23, 20, 0)):
        # am Tag selbst: Werkzeug mit Stunden, Imprint ohne (Prompt-Kopf ändert sich 1×/Tag)
        assert "(heute, in 3 h)" in kalender.render_range_for_tool(TAG, TAG)
        assert "Analysis HÜ (heute)" in kalender.imprint_for_prompt(tage=0)
    with uhr.gestellt(JETZT):
        ohne = kalender.imprint_for_prompt(tage=0)        # heute: keine Deadline
        assert "Zeitpunkt (Abgabe" not in ohne


@pytest.mark.kalender_beide
def test_routen_liefern_und_schalten(cal):
    from ui.app import app
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.post("/api/calendar/entry", json={"day": TAG.isoformat(), "label": "Analysis HÜ",
                                            "time": "23:59", "typ": "deadline",
                                            "vorwarnung": "12h"})
    assert r.status_code == 200, r.get_json()
    k = r.get_json()["kennung"]
    d = c.get("/api/calendar?view=week&ref=" + TAG.isoformat()).get_json()
    e = d["days"][TAG.isoformat()][0]
    assert (e["typ"], e["vorwarnung"], e["kennung"]) == ("deadline", 720, k)
    r = c.post("/api/calendar/entry", json={"day": TAG.isoformat(), "label": "X",
                                            "typ": "deadline"})
    assert r.status_code == 400 and r.get_json()["code"] == "DEADLINE-OHNE-ZEIT"
    r = c.post("/api/calendar/typ", json={"kennung": k, "typ": "normal"})
    assert r.status_code == 200 and "typ" not in r.get_json()
    r = c.put("/api/calendar/eintrag", json={"kennung": k, "new": {"typ": "deadline",
                                                                   "vorwarnung": 30}})
    assert r.get_json()["eintrag"]["vorwarnung"] == 30
    r = c.post("/api/calendar/routine", json={"label": "Abgabe", "freq": "w",
                                              "seit": TAG.isoformat(), "time": "12:00",
                                              "typ": "deadline"})
    assert r.status_code == 200 and kk.eintrag(r.get_json()["kennung"])["typ"] == "deadline"
