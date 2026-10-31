"""Lists step 3 (memory/hub/list_extraction_plan.md): the read-only list
routes that let the TUI and the calendar stop computing list logic in their
own process —

  GET  /api/lists?view=1        counts, effective done, display order (A8)
  GET  /api/lists/targets       "einordnen" targets (A8)
  GET  /api/lists/<lid>/bild    the picture of one level (A9)
  POST /api/lists/aufloesen     what is on top now (calendar)

Each answer is checked against its schema in openapi.yaml, and the picture is
the SAME as the tile's (one picture, memory/hub/listen_app.md).
"""
import json
import os

import pytest
import yaml
from jsonschema import Draft202012Validator

import kacheln
import listen_bild
import lists

from test_lists_recording import FIXED_LISTS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def spec():
    with open(os.path.join(ROOT, "openapi.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def c():
    with open(lists._REGISTRY, "w", encoding="utf-8") as f:
        json.dump(FIXED_LISTS, f, ensure_ascii=False)
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def fits(spec, name, value):
    schema = {"components": spec["components"], "$ref": "#/components/schemas/%s" % name}
    errors = [e.message for e in Draft202012Validator(schema).iter_errors(value)]
    assert not errors, (name, errors)


# ── A8: GET /api/lists?view=1 ─────────────────────────────────────────

def test_view_carries_counts_and_display_order(c, spec):
    plain = c.get("/api/lists").get_json()
    viewed = c.get("/api/lists?view=1").get_json()
    for node in viewed:
        fits(spec, "ListNode", node)
    einkauf = viewed[0]
    assert einkauf["view"] == {"done": 2, "total": 6, "complete": False,
                               "order": [1, 3, 4], "finished": [2]}
    baumarkt = einkauf["items"][3]
    assert baumarkt["view"]["order"] == [6, 7] and baumarkt["view"]["finished"] == [5]
    assert einkauf["items"][1]["view"] == {"done": 1, "total": 1, "complete": True}
    umzug = viewed[1]
    assert umzug["view"]["order"][0] == 2                 # the focus sticks on top
    assert viewed[2]["view"] == {"done": 0, "total": 0, "complete": False,
                                 "order": [], "finished": []}
    assert viewed[3]["view"]["complete"] is True

    def strip(nodes):
        return [{k: (strip(v) if k == "items" else v) for k, v in n.items() if k != "view"}
                for n in nodes]
    assert strip(viewed) == plain                        # only `view` is added


def test_view_box_carries_the_root_boxes(c, spec):
    """&box=W (Sasha 2026-10-31, option 2): every list and every project item
    carries its box for the root of the list view — the same box listen_bild
    draws, without the ★; other items carry none, the rest of `view` is the
    same as without box."""
    viewed = c.get("/api/lists?view=1").get_json()
    boxed = c.get("/api/lists?view=1&box=30").get_json()
    for node in boxed:
        fits(spec, "ListNode", node)
    einkauf, umzug = boxed[0], boxed[1]
    baumarkt = einkauf["items"][3]                     # a project item in a plain list
    expected = listen_bild.eintrag(FIXED_LISTS[0]["items"][3], projekt_marke=False)
    assert baumarkt["view"]["box"] == {"plain": listen_bild.kasten(expected, 30),
                                       "selected": listen_bild.kasten(expected, 30, gewaehlt=True)}
    assert "★" not in json.dumps(umzug["view"]["box"], ensure_ascii=False)
    assert "box" in boxed[2]["view"] and "box" in boxed[3]["view"]
    assert "box" not in einkauf["items"][0]["view"]  # a plain item: no box

    def strip(nodes):
        return [{k: (strip(v) if k == "items" else
                     ({a: b for a, b in v.items() if a != "box"} if k == "view" else v))
                 for k, v in n.items()} for n in nodes]
    assert strip(boxed) == viewed


def test_view_box_rejects_a_wrong_width(c):
    assert c.get("/api/lists?view=1&box=0").status_code == 400
    assert c.get("/api/lists?view=1&box=x").status_code == 400


def test_view_does_not_write(c):
    before = open(lists._REGISTRY, "rb").read()
    c.get("/api/lists?view=1")
    assert open(lists._REGISTRY, "rb").read() == before


# ── A8: GET /api/lists/targets ────────────────────────────────────────

def test_targets_for_an_item_leave_out_its_own_subtree(c, spec):
    r = c.get("/api/lists/targets?kind=item&lid=l_einkauf&iid=4")
    assert r.status_code == 200
    got = r.get_json()
    for t in got:
        fits(spec, "FilingTarget", t)
    mine = [(t["iid"], t["tiefe"]) for t in got if t["lid"] == "l_einkauf"]
    assert mine == [(None, 0), (1, 1), (2, 1), (3, 1)]   # 4 and below are gone
    assert {"lid": "l_umzug", "iid": 3, "text": "Teller", "tiefe": 2} in got


def test_targets_for_a_list_leave_out_the_list(c):
    got = c.get("/api/lists/targets?kind=list&lid=l_umzug").get_json()
    assert "l_umzug" not in {t["lid"] for t in got}
    assert got[0] == {"lid": "l_einkauf", "iid": None, "text": "Einkauf", "tiefe": 0}


@pytest.mark.parametrize("query", ["kind=etwas&lid=l_umzug", "kind=item&lid=l_umzug&iid=x"])
def test_targets_reject_wrong_questions(c, query):
    assert c.get("/api/lists/targets?" + query).status_code == 400


# ── A9: GET /api/lists/<lid>/bild ─────────────────────────────────────

def test_top_level_picture_is_the_tiles_picture(c, spec):
    pic = c.get("/api/lists/l_einkauf/bild?w=36&h=12").get_json()
    fits(spec, "ListPicture", pic)
    status, tile = kacheln.holen({"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_einkauf",
                                  "w": 36, "h": 12})
    assert status == 200 and pic["zeilen"] == tile["zeilen"]
    assert pic["pfad"] == [] and pic["namen"] == ["Einkauf"]


def test_deeper_level_selection_and_finished(c, spec):
    pic = c.get("/api/lists/l_einkauf/bild?w=30&h=14&pfad=4&auswahl=1").get_json()
    fits(spec, "ListPicture", pic)
    assert pic["pfad"] == [4] and pic["namen"] == ["Einkauf", "Baumarkt"]
    items = FIXED_LISTS[0]["items"][3]["items"]
    expected = listen_bild.ebene(items, 30, 14, ["Einkauf", "Baumarkt"], auswahl=1)
    assert pic["zeilen"] == json.loads(json.dumps(expected["zeilen"]))
    assert pic["bernstein"]["done"] == 1 and pic["bernstein"]["total"] == 3
    assert len(pic["bernstein"]["steine"]) == pic["bernstein"]["breite"] - 2
    done = c.get("/api/lists/l_einkauf/bild?w=30&h=14&pfad=4&erledigte=1").get_json()
    assert "abgeschl" in done["zeilen"][0][0][0]


def test_broken_path_is_cut(c):
    pic = c.get("/api/lists/l_einkauf/bild?w=30&h=14&pfad=4,99,7").get_json()
    assert pic["pfad"] == [4] and pic["namen"] == ["Einkauf", "Baumarkt"]


@pytest.mark.parametrize("query,status", [("w=30", 400), ("w=30&h=0", 400),
                                          ("w=30&h=9&pfad=a", 400)])
def test_picture_rejects_wrong_numbers(c, query, status):
    assert c.get("/api/lists/l_einkauf/bild?" + query).status_code == status


def test_picture_of_a_gone_list(c):
    assert c.get("/api/lists/l_weg/bild?w=30&h=9").status_code == 404


# ── POST /api/lists/aufloesen ─────────────────────────────────────────

def test_resolve_answers_each_source_in_order(c, spec):
    r = c.post("/api/lists/aufloesen", json={
        "quellen": ["l_einkauf", {"art": "projekt", "id": "l_einkauf/4"}, "l_fertig",
                    "l_einkauf/6", "l_weg", "l_einkauf/x", 7], "offene": 3})
    assert r.status_code == 200
    got = r.get_json()["ergebnisse"]
    for e in got:
        fits(spec, "ListResolution", e)
    assert [e["zustand"] for e in got] == ["ok", "ok", "leer", "ok", "fehlt", "fehlt", "fehlt"]
    assert got[0]["titel"] == "Milch" and got[0]["offene"] == ["Milch", "Eier", "Dübel"]
    assert got[1] == {"zustand": "ok", "titel": "Dübel", "name": "Baumarkt", "projekt": True,
                      "eintrag": {"liste": "l_einkauf", "id": 6}, "offene": ["Dübel", "weiß"]}
    assert got[2]["titel"] == "Fertig — alles erledigt"
    assert got[3]["titel"] == "Dübel" and got[3]["offene"] == []   # a point is its own step


def test_resolve_rejects_no_list(c):
    assert c.post("/api/lists/aufloesen", json={"quellen": "l_einkauf"}).status_code == 400


def test_calendar_no_longer_computes_list_logic():
    """The calendar asks the lists (lists.resolve); it does not import the
    list helpers any more (memory/hub/list_extraction_plan.md step 3)."""
    import ast
    with open(os.path.join(ROOT, "core", "kalender_quelle.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"listen_baum", "listen_bild"}
