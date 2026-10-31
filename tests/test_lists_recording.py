"""Lists step 3 (memory/hub/list_extraction_plan.md): the answers of the
EXISTING list routes stay byte-identical while the lists are made ready to
move. A fixed test set (no timestamps from the clock) is written straight into
the test's list folder, every route is asked, and the bodies are compared
with the recording taken before step 3 (tests/daten/lists_recording.json).

The same recording is the proof for step 5 (the move): through the hub's
forwarding the bodies must still be the same bytes.

Re-record only on purpose: ZENTRALE_RECORD_LISTS=1 pytest tests/test_lists_recording.py
"""

import json
import os

import pytest

import kalender_quelle
import lists

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDING = os.path.join(HERE, "daten", "lists_recording.json")

FIXED_LISTS = [
    {"id": "l_einkauf", "name": "Einkauf", "created": "2026-10-01T09:00:00",
     "next_item": 9, "project": False, "items": [
         {"id": 1, "text": "Milch", "done": False},
         {"id": 2, "text": "Brot", "done": True},
         {"id": 3, "text": "Eier", "done": False},
         {"id": 4, "text": "Baumarkt", "done": False, "project": True, "items": [
             {"id": 5, "text": "Schrauben", "done": True},
             {"id": 6, "text": "Dübel", "done": False},
             {"id": 7, "text": "Farbe", "done": False, "items": [
                 {"id": 8, "text": "weiß", "done": False}]}]}]},
    {"id": "l_umzug", "name": "Umzug", "created": "2026-10-02T09:00:00",
     "next_item": 6, "project": True, "items": [
         {"id": 1, "text": "Kartons", "done": True},
         {"id": 2, "text": "Küche", "done": False, "focus": True, "items": [
             {"id": 3, "text": "Teller", "done": False},
             {"id": 4, "text": "Töpfe", "done": True}]},
         {"id": 5, "text": "Strom ummelden", "done": False}]},
    {"id": "l_leer", "name": "Leer", "created": "2026-10-03T09:00:00",
     "next_item": 1, "project": False, "items": []},
    {"id": "l_fertig", "name": "Fertig", "created": "2026-10-04T09:00:00",
     "next_item": 3, "project": False, "items": [
         {"id": 1, "text": "eins", "done": True},
         {"id": 2, "text": "zwei", "done": True}]},
]

GETS = ["/api/lists", "/api/projects", "/api/projects/focused", "/api/projects/focus",
        "/api/kacheln", "/api/calendar/quellen",
        "/api/calendar/quelle?art=liste&id=l_einkauf&n=5",
        "/api/calendar/quelle?art=projekt&id=l_einkauf/4",
        "/api/calendar/quelle?art=liste&id=l_fertig",
        "/api/calendar/quelle?art=liste&id=l_weg"]

TILES = [
    {"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_einkauf", "w": 36, "h": 12},
    {"adresse": "zentrale://fokus/liste?erledigte=true&liste=l_einkauf", "w": 30, "h": 9},
    {"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_umzug", "w": 24, "h": 7,
     "oben": 1},
    {"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_leer", "w": 20, "h": 8},
    {"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_weg", "w": 20, "h": 8},
]

SOURCES = [{"art": "liste", "id": "l_einkauf"}, {"art": "projekt", "id": "l_einkauf/4"},
           {"art": "projekt", "id": "l_umzug"}, {"art": "liste", "id": "l_fertig"},
           {"art": "liste", "id": "l_leer"}, {"art": "projekt", "id": "l_einkauf/6"},
           {"art": "liste", "id": "l_weg"}, {"art": "kaputt"}]


@pytest.fixture
def fixed_lists():
    with open(lists._REGISTRY, "w", encoding="utf-8") as f:
        json.dump(FIXED_LISTS, f, ensure_ascii=False)


def _answers():
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    out = {}
    for path in GETS:
        r = c.get(path)
        out["GET " + path] = [r.status_code, r.get_data(as_text=True)]
    for tile in TILES:
        r = c.post("/api/kachel", json=tile)
        out["POST /api/kachel " + json.dumps(tile, sort_keys=True)] = [
            r.status_code, r.get_data(as_text=True)]
    for q in SOURCES:
        key = json.dumps(q, sort_keys=True)
        out["aufloesen " + key] = json.dumps(
            kalender_quelle.aufloesen(q, "Rückfall"), ensure_ascii=False, sort_keys=True)
        try:
            out["vorschau " + key] = json.dumps(
                kalender_quelle.vorschau(q, 3), ensure_ascii=False, sort_keys=True)
        except Exception as e:                        # noqa: BLE001 — the error is the answer
            out["vorschau " + key] = "error: %s %s" % (type(e).__name__, e)
    out["auswahl"] = json.dumps(kalender_quelle.auswahl(), ensure_ascii=False, sort_keys=True)
    return out


def test_existing_list_answers_stay_byte_identical(fixed_lists):
    now = _answers()
    if os.environ.get("ZENTRALE_RECORD_LISTS") == "1":
        with open(RECORDING, "w", encoding="utf-8") as f:
            json.dump(now, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        pytest.skip("recorded")
    with open(RECORDING, encoding="utf-8") as f:
        before = json.load(f)
    assert sorted(now) == sorted(before)
    changed = sorted(k for k in now if now[k] != before[k])
    assert not changed, "these answers changed: %s" % changed


def test_recording_does_not_touch_the_lists(fixed_lists):
    """Asking is reading: the fixed set is the same bytes afterwards."""
    with open(lists._REGISTRY, "rb") as f:
        before = f.read()
    _answers()
    with open(lists._REGISTRY, "rb") as f:
        assert f.read() == before
