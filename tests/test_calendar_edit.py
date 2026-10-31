"""PUT /api/calendar/edit — one user edit = one call = one save, all or
nothing (A1, 2026-10-31; core/kalender_bearbeiten.edit, kalender.one_write).

  * success: main change + group + style + deadline + layer, ONE real save,
    the answer is the entry re-read by kennung,
  * a rejection (also one that only shows up halfway) writes nothing,
  * "once → series/span" is create + delete in the same save; a failure in
    the second half (the delete) leaves the store exactly as before,
  * extras that equal the stored value are not touched.
Throwaway calendar in tmp_path; runs against both stores.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_bearbeiten as kb
import kalender_kennung as kk
from kalender_ics import IcsSpeicher
from kalender_json import JsonSpeicher

pytestmark = pytest.mark.kalender_beide

DAY = "2026-10-20"       # fixed calendar day of the entries, not "today"


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return tmp_path


@pytest.fixture
def c(cal):
    from ui.app import app
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def saves(monkeypatch):
    """How often the real store was written."""
    n = []
    for cls in (JsonSpeicher, IcsSpeicher):
        orig = cls.speichern

        def counted(self, *a, _orig=orig, **k):
            n.append(1)
            return _orig(self, *a, **k)
        monkeypatch.setattr(cls, "speichern", counted)
    return n


def _state(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != ".zentrale.lock"
            and "kalender_verlauf" not in p.parts and "kalender_snapshots" not in p.parts}


def _entry(c, **fields):
    body = {"day": DAY, "label": "Kino", "time": "19:00", "ende": "21:00"}
    body.update(fields)
    r = c.post("/api/calendar/entry", json=body)
    assert r.status_code == 200
    return r.get_json()["kennung"]


def _edit(c, body):
    return c.put("/api/calendar/edit", json=body)


def test_edit_everything_in_one_save(c, saves):
    k = _entry(c)
    del saves[:]
    r = _edit(c, {"kennung": k, "new": {
        "day": "2026-10-21", "time": "20:00", "ende": "22:00", "ort": "Kino 3",
        "kategorie": "custom", "kategorie_name": "Freizeit", "stil": {"color": "#00ff00"},
        "layer": "uncommitted"}})
    assert r.status_code == 200, r.get_json()
    e = r.get_json()["eintrag"]
    assert (e["kennung"], e["tag"], e["time"], e["ende"], e["ort"]) == \
        (k, "2026-10-21", "20:00", "22:00", "Kino 3")
    assert (e["kategorie"], e["kategorie_name"], e["stil"], e["layer"]) == \
        ("custom", "Freizeit", {"color": "#00ff00"}, "uncommitted")
    assert len(saves) == 1, "one edit = one save"
    assert kk.eintrag(k) == e                                   # proof: re-read


def test_unchanged_extras_are_not_touched(c, saves):
    k = _entry(c, kategorie="uni", stil={"color": "#ff0000"})
    del saves[:]
    r = _edit(c, {"kennung": k, "new": {"kategorie": "uni", "stil": {"color": "#ff0000"},
                                        "typ": "normal", "layer": "termine"}})
    assert r.status_code == 200
    assert len(saves) == 0, "nothing differs → nothing written"


def test_rejection_writes_nothing(c, cal):
    k = _entry(c)
    before = _state(cal)
    # invalid right away
    r = _edit(c, {"kennung": k, "new": {"time": "25:99"}})
    assert r.status_code == 400
    assert r.get_json()["code"] == "AENDERUNG-ABGELEHNT" and r.get_json()["next"]
    # unknown field
    r = _edit(c, {"kennung": k, "new": {"farbe": "rot"}})
    assert r.status_code == 400 and r.get_json()["code"] == "UNBEKANNTES-FELD"
    # only found halfway: the time change is fine, the style is not
    r = _edit(c, {"kennung": k, "new": {"time": "08:00", "ende": "09:00",
                                        "stil": {"color": "nonsense"}}})
    assert r.status_code == 400 and r.get_json()["code"] == "STIL-UNGUELTIG"
    assert _state(cal) == before
    assert kk.eintrag(k)["time"] == "19:00"


def test_deadline_back_to_normal_with_new_end_in_one_call(c):
    k = _entry(c, ende="", typ="deadline", vorwarnung="3d", label="Abgabe")
    r = _edit(c, {"kennung": k, "new": {"typ": "normal", "time": "19:00", "ende": "20:00"}})
    assert r.status_code == 200, r.get_json()
    e = r.get_json()["eintrag"]
    assert e.get("typ") is None and e["ende"] == "20:00"
    # and back: the end goes in the same call as the deadline
    r = _edit(c, {"kennung": k, "new": {"ende": "", "typ": "deadline", "vorwarnung": 60}})
    assert r.status_code == 200, r.get_json()
    e = r.get_json()["eintrag"]
    assert (e["typ"], e["vorwarnung"], e.get("ende")) == ("deadline", 60, None)


def test_once_becomes_series_create_and_delete_in_one_save(c, saves):
    k = _entry(c)
    del saves[:]
    r = _edit(c, {"kennung": k, "replace": {
        "kind": "routine", "layer": "termine", "label": "Kino", "seit": DAY, "freq": "w",
        "intervall": 1, "time": "19:00", "ende": "21:00", "kategorie": "uni"}})
    assert r.status_code == 200, r.get_json()
    e = r.get_json()["eintrag"]
    assert e["art"] == "routine" and e["kennung"] != k and e["kategorie"] == "uni"
    assert len(saves) == 1
    with pytest.raises(kk.KalenderAbgelehnt):
        kk.eintrag(k)


def test_failure_in_the_second_half_of_a_conversion_rolls_back(c, cal, monkeypatch):
    k = _entry(c)
    before = _state(cal)

    def broken(_k):
        raise RuntimeError("disk gone")
    with monkeypatch.context() as m:
        m.setattr(kk, "eintrag_loeschen", broken)
        with pytest.raises(RuntimeError):
            kb.edit(k, replace={"kind": "spanne", "layer": "termine", "von": DAY,
                                "bis": "2026-10-22", "label": "Kino"})
    assert _state(cal) == before
    assert [e["kennung"] for e in kk.alle_eintraege()] == [k]
    # a rejected new half writes nothing either
    r = _edit(c, {"kennung": k, "replace": {"kind": "spanne", "von": DAY,
                                            "bis": "2026-10-01", "label": "Kino"}})
    assert r.status_code == 400 and r.get_json()["code"] == "AENDERUNG-ABGELEHNT"
    assert _state(cal) == before


def test_whole_series_and_whole_span(c):
    r = c.post("/api/calendar/routine", json={"label": "Geige", "seit": DAY, "freq": "w",
                                              "time": "18:00", "ende": "19:00"})
    k = r.get_json()["kennung"]
    r = _edit(c, {"kennung": k, "day": DAY, "new": {
        "label": "Violine", "wiederholung": {"freq": "w", "intervall": 2},
        "kategorie": "uni"}})
    assert r.status_code == 200, r.get_json()
    e = r.get_json()["eintrag"]
    assert (e["label"], e["kategorie"]) == ("Violine", "uni") and "INTERVAL=2" in e["rrule"]
    r = c.post("/api/calendar/spanne", json={"von": DAY, "bis": "2026-10-22", "label": "Messe"})
    assert r.status_code == 200
    sk = next(x["kennung"] for x in kk.alle_eintraege() if x["label"] == "Messe")
    r = _edit(c, {"kennung": sk, "new": {"verschieben": 7, "stil": {"color": "#0000ff"}}})
    assert r.status_code == 200, r.get_json()
    e = r.get_json()["eintrag"]
    assert (e["von"], e["bis"], e["stil"]) == ("2026-10-27", "2026-10-29", {"color": "#0000ff"})


def test_locate_without_kennung(c):
    _entry(c, label="Zahnarzt", time="14:00", ende="15:00")
    r = _edit(c, {"locate": {"layer": "termine", "day": DAY, "label": "Zahnarzt",
                             "time": "14:00"}, "new": {"time": "14:30"}})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["eintrag"]["time"] == "14:30"
    r = _edit(c, {"locate": {"day": DAY, "label": "Gibtsnicht"}, "new": {"time": "14:30"}})
    assert r.status_code == 400 and r.get_json()["code"] == "KEIN-TREFFER"


def test_one_write_is_one_save_and_nothing_on_error(cal, saves):
    with kalender.one_write():
        kalender.add_entry("termine", DAY, "A")
        kalender.add_entry("termine", DAY, "B")
    assert len(saves) == 1
    with pytest.raises(RuntimeError):
        with kalender.one_write():
            kalender.add_entry("termine", DAY, "C")
            raise RuntimeError("halfway")
    assert sorted(e["label"] for e in kk.alle_eintraege()) == ["A", "B"]


def _shown(c, label):
    days = c.get("/api/calendar", query_string={"ref": DAY}).get_json()["days"]
    return next(e for e in days[DAY] if e["label"] == label)


def _send(c, plan):
    (method, path, body), = plan["aufrufe"]
    return c.open(path, method=method, json=body)


def test_the_tui_plan_is_what_the_core_takes(c):
    """End to end: the body the TUI form builds goes through the route."""
    from datetime import date
    from tui.ansichten import kalender_werkzeuge as kw
    tag = date.fromisoformat(DAY)
    k = _entry(c, label="Zahnarzt", time="14:00", ende="15:00")
    f = kw.formular_bearbeiten(_shown(c, "Zahnarzt"), tag, tag)
    next(x for x in f.felder if x.name == "von").text = "15:00"
    next(x for x in f.felder if x.name == "bis").text = "16:00"
    gruppe = next(x for x in f.felder if x.name == "gruppe")
    gruppe.wahl = gruppe.optionen.index("Uni")
    assert f.taste(19) == "fertig", f.fehler
    r = _send(c, f.plan())
    assert r.status_code == 200, r.get_json()
    e = kk.eintrag(k)
    assert (e["time"], e["ende"], e["kategorie"]) == ("15:00", "16:00", "uni")
    # once → weekly series, through the form
    f = kw.formular_wiederholen(_shown(c, "Zahnarzt"), tag, tag)
    wied = next(x for x in f.felder if x.name == "wied")
    wied.wahl = wied.optionen.index("wöchentlich")
    assert f.taste(19) == "fertig", f.fehler
    r = _send(c, f.plan())
    assert r.status_code == 200, r.get_json()
    neu = r.get_json()["eintrag"]
    assert neu["art"] == "routine" and neu["kategorie"] == "uni"
    assert [x["kennung"] for x in kk.alle_eintraege()] == [neu["kennung"]]
