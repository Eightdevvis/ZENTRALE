"""Schematix step 14 (memory/hub/schematix.md): schemes as JSON Canvas 1.0
with the `zentrale` key, planned and documented pieces, the things store,
the starter scheme from memory/system/heimnetz.md.

Acceptance: the planned router is drawn as "not yet"; a joining node turns
its planned piece live (same piece, same place); the file stays what
Obsidian opens, and a load → save round trip keeps every key."""
import pytest

import ai_config
import schematix_map
import schematix_scheme


@pytest.fixture
def client(_test_ordner, monkeypatch):
    path = _test_ordner / "ai_config.json"
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(path))
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setenv("ZENTRALE_NODE_NAME", "laptop")
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "datei")
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def by_id(m):
    return {p["id"]: p for p in m["pieces"]}


def board_body(m):
    """What the TUI sends after a change: every place, the planned pieces
    and the planned wires (tui/ansichten/schematix.py `koerper`)."""
    planned = set(m["scheme"]["planned"])
    pieces = []
    for p in m["pieces"]:
        d = {k: p[k] for k in ("id", "x", "y", "w", "h")}
        if p["id"] in planned:
            d["planned"] = {k: p.get(k) for k in ("kind", "ref", "title", "node", "thing_kind", "address")}
        pieces.append(d)
    wires = [{k: w.get(k) for k in ("id", "from_piece", "to_piece", "type", "from", "to", "owner")}
             for w in m["wires"] if w["state"] == "planned"]
    return {"stand": m["scheme"]["stand"], "pieces": pieces, "wires": wires}


def test_starter_scheme_from_heimnetz(client):
    m = client.get("/api/schematix/map").json
    p = by_id(m)
    assert m["scheme"]["name"] == "home" and schematix_scheme.names() == ["home"]
    assert p["device:router"]["state"] == "planned" and p["device:router"]["address"] == "192.168.50.254"
    assert p["node:pc"]["state"] == "planned" and p["node:laptop"]["state"] == "live"   # this node reports
    assert p["device:tablet"]["state"] == "documented"
    w = {x["id"]: x for x in m["wires"]}
    assert w["lan/router/pc"]["state"] == "planned" and w["lan/router/pc"]["layer"] == "network"
    assert w["tailscale/minipc/tablet"]["state"] == "live"                  # live today
    assert w["power/power-bank/minipc"]["layer"] == "power"
    assert p["device:router"]["y"] > p["node:laptop"]["y"]                  # things below the nodes


def test_a_joining_node_turns_its_planned_piece_live(client, monkeypatch):
    before = by_id(client.get("/api/schematix/map").json)["node:pc"]
    pc = {"name": "pc", "programm": "44", "types": {"sync": "1.0.0"}, "apply_agent": 1,
          "wires": {"format": "zentrale-node-wires/1", "wires": []}}
    monkeypatch.setattr(schematix_map, "account_descriptions", lambda: ([pc], []))
    after = by_id(client.get("/api/schematix/map").json)["node:pc"]
    assert before["state"] == "planned" and after["state"] == "live"
    assert (after["x"], after["y"]) == (before["x"], before["y"])            # same piece, same place
    canvas, _s = schematix_scheme.load("home")
    assert any(n["id"] == "node:pc" for n in canvas["nodes"])               # nothing redrawn


def canvas_ok(c):
    """JSON Canvas 1.0 (jsoncanvas.org/spec/1.0): what Obsidian needs to open it."""
    ids = set()
    for n in c["nodes"]:
        assert isinstance(n["id"], str) and n["type"] in ("text", "file", "link", "group")
        assert all(isinstance(n[k], int) for k in ("x", "y", "width", "height")), n
        ids.add(n["id"])
    for e in c["edges"]:
        assert isinstance(e["id"], str) and e["fromNode"] in ids and e["toNode"] in ids, e


def test_load_save_round_trip_keeps_every_key(client):
    client.get("/api/schematix/map")
    canvas, _s = schematix_scheme.load("home")
    canvas_ok(canvas)
    router = next(n for n in canvas["nodes"] if n["id"] == "device:router")
    router["color"] = "4"
    router["zentrale"]["future"] = {"a": 1}
    canvas["nodes"].append({"id": "note1", "type": "text", "text": "buy cables", "x": 0, "y": -400,
                            "width": 200, "height": 60})
    canvas["edges"][0]["color"] = "2"
    canvas["edges"].append({"id": "arrow1", "fromNode": "note1", "toNode": "device:router"})
    schematix_scheme._write("home", canvas)
    m = client.get("/api/schematix/map").json
    body = board_body(m)
    r = client.put("/api/schematix/schemes/home", json=body)
    assert r.status_code == 200, r.json
    again, _s = schematix_scheme.load("home")
    canvas_ok(again)
    r2 = next(n for n in again["nodes"] if n["id"] == "device:router")
    assert r2["color"] == "4" and r2["zentrale"]["future"] == {"a": 1} and r2["zentrale"]["state"] == "planned"
    assert any(n["id"] == "note1" for n in again["nodes"])                  # Obsidian's own note
    assert any(e["id"] == "arrow1" for e in again["edges"])
    first = next(e for e in again["edges"] if e["id"] == canvas["edges"][0]["id"])
    assert first["color"] == "2" and first["zentrale"]["wire"] == first["id"]
    places = {n["id"]: (n["x"], n["y"]) for n in canvas["nodes"]}
    assert {n["id"]: (n["x"], n["y"]) for n in again["nodes"]} == places    # nothing moved
    # A stale stand is refused: nothing written.
    assert client.put("/api/schematix/schemes/home", json=body).status_code == 409


def test_moving_a_piece_is_stored_and_a_planned_piece_can_go(client):
    m = client.get("/api/schematix/map").json
    body = board_body(m)
    for d in body["pieces"]:
        if d["id"] == "device:switch":
            d["x"] += 7
    body["pieces"] = [d for d in body["pieces"] if d["id"] != "device:power-bank"]
    body["wires"] = [w for w in body["wires"] if "power-bank" not in w["id"]]
    m2 = client.put("/api/schematix/schemes/home", json=body).json
    p = by_id(m2)
    assert p["device:switch"]["x"] == by_id(m)["device:switch"]["x"] + 7
    assert "device:power-bank" not in p and "power/power-bank/minipc" not in {w["id"] for w in m2["wires"]}


def test_documenting_a_planned_thing_keeps_its_reference(client):
    client.get("/api/schematix/map")
    r = client.put("/api/schematix/things/router", json={"kind": "router", "title": "Router (Flint 2)",
                                                         "address": "192.168.50.254"})
    assert r.status_code == 200 and r.json["format"] == "zentrale-thing/1"
    p = by_id(client.get("/api/schematix/map").json)
    assert p["device:router"]["state"] == "documented"
    assert p["device:router"]["ref"] == "zentrale://schematix/things/router/"
    assert client.put("/api/schematix/things/x", json={"kind": 3}).status_code == 400
