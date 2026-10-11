"""
HTTP-Routen per Kennung (Wunsch ASSISTANT, 11.10.2026): fremde Anbindungen
lesen, ändern und löschen per `kennung` statt über Tag+Titel.

  * GET /api/calendar/eintrag?kennung=… liefert das Eintrags-Dict,
  * PUT/DELETE /api/calendar/eintrag und /routine nehmen `kennung` und
    treffen GENAU diesen Eintrag (auch bei zwei gleichnamigen Routinen),
  * ohne `kennung` bleibt der Weg über Tag+Titel wie er war,
  * eine Ablehnung (400 {error, code}) schreibt nichts.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_kennung as kk

pytestmark = pytest.mark.kalender_beide


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return tmp_path


@pytest.fixture
def c(cal):
    from ui.app import app
    app.config["TESTING"] = True
    return app.test_client()


def _stand(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != ".zentrale.lock"}


def _termin(c, **feld):
    body = {"day": "2026-10-20", "label": "Kino", "time": "19:00", "ende": "21:00"}
    body.update(feld)
    r = c.post("/api/calendar/entry", json=body)
    assert r.status_code == 200
    return r.get_json()["kennung"]


def _geige(c, time, ende):
    r = c.post("/api/calendar/routine", json={"label": "Geigenstunde", "byday": "TU",
                                              "time": time, "ende": ende})
    assert r.status_code == 200
    return r.get_json()["kennung"]


def test_lesen_per_kennung(c):
    k = _termin(c)
    r = c.get("/api/calendar/eintrag", query_string={"kennung": k})
    assert r.status_code == 200
    e = r.get_json()
    assert (e["kennung"], e["art"], e["tag"], e["label"]) == (k, "einmal", "2026-10-20", "Kino")
    r = c.get("/api/calendar/eintrag", query_string={"kennung": "gibt-es-nicht"})
    assert r.status_code == 400 and r.get_json()["code"] == "KENNUNG-UNBEKANNT"
    r = c.get("/api/calendar/eintrag")
    assert r.status_code == 400 and r.get_json()["code"] == "KENNUNG-UNBEKANNT"


def test_termin_aendern_und_loeschen_per_kennung(c):
    k = _termin(c)
    _termin(c, time="22:00", ende="23:00")          # gleichnamig, gleicher Tag
    r = c.put("/api/calendar/eintrag", json={"kennung": k, "new": {
        "day": "2026-10-21", "time": "18:00", "ort": "Odeon"}})
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    e = j["eintrag"]
    assert (e["kennung"], e["tag"], e["time"], e["ende"], e["ort"]) == \
        (k, "2026-10-21", "18:00", "21:00", "Odeon")
    # der andere „Kino" blieb, wo er war
    andere = [x for x in kk.alle_eintraege() if x["label"] == "Kino" and x["kennung"] != k]
    assert [(x["tag"], x["time"]) for x in andere] == [("2026-10-20", "22:00")]
    # "" löscht ein Feld
    r = c.put("/api/calendar/eintrag", json={"kennung": k, "new": {"ort": ""}})
    assert "ort" not in r.get_json()["eintrag"]
    r = c.delete("/api/calendar/eintrag", json={"kennung": k})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    assert k not in {x["kennung"] for x in kk.alle_eintraege()}
    assert len(andere) == 1 and kk.eintrag(andere[0]["kennung"])


def test_spanne_per_kennung(c):
    r = c.post("/api/calendar/entry", json={"day": "2026-10-07", "bis": "2026-10-09",
                                            "label": "Messe"})
    k = r.get_json()["kennung"]
    r = c.put("/api/calendar/eintrag", json={"kennung": k, "new": {"von": "2026-10-08"}})
    e = r.get_json()["eintrag"]
    assert (e["art"], e["von"], e["bis"]) == ("spanne", "2026-10-08", "2026-10-10")


def test_gleichnamige_routinen_genau_die_richtige(c):
    frueh = _geige(c, "17:45", "18:30")
    spaet = _geige(c, "18:10", "19:10")
    r = c.put("/api/calendar/routine", json={"kennung": spaet, "new": {
        "time": "18:20", "ende": "19:20", "ort": "Saal 2"}})
    assert r.status_code == 200
    e = r.get_json()["eintrag"]
    assert (e["kennung"], e["time"], e["ende"], e["ort"]) == (spaet, "18:20", "19:20", "Saal 2")
    f = kk.eintrag(frueh)
    assert (f["time"], f["ende"]) == ("17:45", "18:30") and "ort" not in f
    # Wiederholung wie im TUI-Formular → Regel
    r = c.put("/api/calendar/routine", json={"kennung": frueh, "new": {
        "wiederholung": {"freq": "w", "intervall": 2, "wochentage": ["TH"]}}})
    assert r.status_code == 200
    assert "INTERVAL=2" in r.get_json()["eintrag"]["rrule"]
    assert "BYDAY=TH" in r.get_json()["eintrag"]["rrule"]
    assert kk.eintrag(spaet)["rrule"] == "FREQ=WEEKLY;BYDAY=TU"
    r = c.delete("/api/calendar/routine", json={"kennung": spaet})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    rest = [x["kennung"] for x in kk.alle_eintraege() if x["label"] == "Geigenstunde"]
    assert rest == [frueh]


def test_rueckfall_tag_und_titel_unveraendert(c):
    _termin(c)
    r = c.put("/api/calendar/eintrag", json={"day": "2026-10-20", "label": "Kino",
                                             "new": {"time": "20:00"}})
    assert r.get_json() == {"ok": True}
    r = c.delete("/api/calendar/eintrag", json={"day": "2026-10-20", "label": "Kino"})
    assert r.get_json() == {"ok": True}
    _geige(c, "17:45", "18:30")
    r = c.put("/api/calendar/routine", json={"label": "Geigenstunde", "day": "2026-10-13",
                                             "new": {"ort": "Schule"}})
    assert r.get_json() == {"ok": True}
    r = c.delete("/api/calendar/routine", json={"label": "Geigenstunde"})
    assert r.get_json() == {"deleted": 1}


@pytest.mark.parametrize("weg,body,code", [
    ("eintrag", {"new": {"time": "25:00"}}, "ZEIT-UNGUELTIG"),
    ("eintrag", {"new": {"farbe": "rot"}}, "UNBEKANNTES-FELD"),
    ("eintrag", {"new": {"label": ""}}, "TITEL-LEER"),
    ("routine", {"new": {"time": "08:00"}}, "FALSCHE-ART"),
    ("routine-r", {"new": {"rrule": "FREQ=QUATSCH"}}, "RRULE-UNGUELTIG"),
    ("routine-r", {"new": {"wiederholung": {"freq": "x"}}}, "RRULE-UNGUELTIG"),
    ("routine-r", {"new": {"wiederholung": {"freq": "w"}, "bis": "2027-01-01"}},
     "UNBEKANNTES-FELD"),
])
def test_ablehnung_schreibt_nichts(c, cal, weg, body, code):
    k_termin = _termin(c)
    k_routine = _geige(c, "17:45", "18:30")
    k = k_routine if weg == "routine-r" else k_termin
    pfad = "/api/calendar/" + weg.split("-")[0]
    vorher = _stand(cal)
    r = c.put(pfad, json={"kennung": k, **body})
    assert r.status_code == 400 and r.get_json()["code"] == code
    assert _stand(cal) == vorher


def test_loeschen_unbekannte_oder_falsche_kennung_schreibt_nichts(c, cal):
    k = _termin(c)
    vorher = _stand(cal)
    r = c.delete("/api/calendar/routine", json={"kennung": k})
    assert r.status_code == 400 and r.get_json()["code"] == "FALSCHE-ART"
    r = c.delete("/api/calendar/eintrag", json={"kennung": "weg"})
    assert r.status_code == 400 and r.get_json()["code"] == "KENNUNG-UNBEKANNT"
    assert _stand(cal) == vorher
