"""Wires as a projection and the Run gate (core/wires.py, core/sketch_compiler.py,
core/generations.py; memory/hub/port_types.md, building kit steps 9 and 9b).

  - the projection of abgleich_apps + calendar `quelle`, written back → the
    settings stay byte-identical (no second store);
  - every vector sketch of contracts/ports/1 (broken ones give no output);
  - a good change switches, a refused one writes nothing, a failed health
    check rolls back; the CLI's sync choice goes through the same gate;
  - GET/PUT/DELETE /api/wires.
"""
import io
import json
import os

import pytest

import abgleich_apps
import ai_config
import generations
import kalender_einstellung as ke
import port_types
import sketch_compiler
import wires
from zentrale_cli.ausgabe import Terminal

NODE = "testnode"


@pytest.fixture
def settings(_test_ordner, monkeypatch):
    """A real ai_config.json in the test folder (the store of abgleich_apps)."""
    path = _test_ordner / "ai_config.json"
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(path))
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setenv("ZENTRALE_NODE_NAME", NODE)
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    return path


def _bytes(p):
    return open(p, "rb").read() if os.path.exists(p) else None


def _calendar_file():
    return os.path.join(ke._anschluesse(), ke.HAUPT + ".json")


def _stored(settings, choice):
    abgleich_apps.setzen(choice)
    assert json.loads(settings.read_text())["abgleich_apps"] == choice


# ── Projection ─────────────────────────────────────────────────────────────

def test_projection_round_trip_leaves_settings_byte_identical(settings):
    _stored(settings, {"notizen": False, "fokus": True, "gone_app": True})
    ke.schreiben(ke.HAUPT, "lokal")
    before = (_bytes(settings), _bytes(_calendar_file()))
    projected = wires.all_wires()
    assert {w["id"]: w["state"] for w in projected if w["type"] == "sync"} == {
        f"sync/{NODE}/fokus": "live", f"sync/{NODE}/notizen": "off", f"sync/{NODE}/adapter": "live"}
    cal = [w for w in projected if w["type"] == "calendar-source"]
    assert cal[0]["from"] == f"zentrale://hub/node/{NODE}/port/calendar-local"
    assert wires.write(projected, calendar_writer=lambda *a: pytest.fail("nothing to write")) == []
    assert (_bytes(settings), _bytes(_calendar_file())) == before


def test_never_chosen_projects_everything_live_and_writes_nothing(settings):
    projected = wires.all_wires()
    assert all(w["state"] == "live" for w in projected if w["type"] == "sync")
    assert len([w for w in projected if w["type"] == "sync"]) == len(abgleich_apps.tabelle())
    assert projected[-1]["from"] == wires.SOURCE_PORTS["google"]     # no calendar file = google
    wires.write(projected)
    assert _bytes(settings) is None and _bytes(_calendar_file()) is None


def test_the_projection_compiles_and_validates(settings):
    sk = wires.sketch()
    gen, errors = sketch_compiler.compile_sketch(sk)
    assert errors == [] and gen["hash"].startswith("sha256:")
    assert port_types.check(gen, "generation") == []


def test_unmanaged_node_from_an_old_description():
    old = wires.piece_of_description({"name": "minipc", "programm": "39"})
    new = wires.piece_of_description({"name": "laptop", "types": {"sync": "1.0.0"}, "apply_agent": 1})
    assert old["managed"] is False and old["types"] == {}
    assert new["managed"] is True and port_types.check(old, "piece") == []


# ── The compiler on the contract's vectors ─────────────────────────────────

def test_every_vector_sketch():
    with open(os.path.join(port_types.FOLDER, "port_vectors.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    names = {c["name"] for c in cases}
    assert {"double-owner", "unmet-requirement", "live-on-planned", "type-too-new",
            "schema-invalid"} <= names
    for c in cases:
        gen, errors = sketch_compiler.compile_sketch(c["sketch"], c.get("current"))
        if c["expect"]["ok"]:
            assert errors == [] and gen["hash"] == c["expect"]["hash"], c["name"]
        else:
            assert gen is None, c["name"]                # any error → no output
            got = sorted((json.dumps({k: e[k] for k in ("code", "piece", "wire", "port") if k in e},
                                     sort_keys=True) for e in errors))
            assert got == [json.dumps(e, sort_keys=True) for e in c["expect"]["errors"]], c["name"]
            assert all(e["text"] for e in errors)


# ── Run ────────────────────────────────────────────────────────────────────

def test_a_good_change_switches(settings):
    _stored(settings, {"fokus": True, "notizen": True})
    store = generations.Store()
    r = generations.choose_sync({"fokus": False}, store=store)
    assert r.ok and not r["rolled_back"]
    assert r["diff"] == [f"~ Listen data → Cloud sync on {NODE}: live → off"]
    assert abgleich_apps.entscheidungen() == {"fokus": False, "notizen": True}
    assert store.current_hash(NODE) == r["generation"]
    assert os.path.islink(os.path.join(store._node(NODE), "current"))
    assert [h["hash"] for h in store.history(NODE)] == [r["previous"], r["generation"]]
    assert store.current(NODE)["hash"] == r["generation"]           # self-contained, hash checks


def test_a_refused_change_writes_nothing(settings):
    _stored(settings, {"fokus": True})
    before = _bytes(settings)
    store = generations.Store()
    r = generations.choose_sync({"adapter": False}, store=store)    # the adapter must sync
    assert not r.ok and r["generation"] is None and r["diff"] == []
    assert [e["code"] for e in r["errors"]] == ["unmet-requirement"]
    assert r["errors"][0]["piece"] == "app:adapter"
    assert _bytes(settings) == before and store.current_hash(NODE) is None


def test_a_failed_health_check_rolls_back(settings):
    _stored(settings, {"fokus": True, "notizen": True})
    before = _bytes(settings)
    store = generations.Store()
    new = {}

    def health(gen, node, done):
        return ["tutor did not come up"] if gen["hash"] == new.get("hash") else []

    plan = generations.choose_sync({"notizen": False}, store=store, apply=False)
    new["hash"] = plan["generation"]
    r = generations.choose_sync({"notizen": False}, store=store, health=health)
    assert r["rolled_back"] and not r.ok and r["problems"] == ["tutor did not come up"]
    assert abgleich_apps.entscheidungen() == {"fokus": True, "notizen": True}
    assert json.loads(_bytes(settings)) == json.loads(before)
    assert store.current_hash(NODE) == r["previous"]
    assert store.history(NODE)[-1]["note"].startswith("rolled back")


def test_a_calendar_source_change_goes_to_its_one_writer(settings):
    calls = []
    sk = wires.sketch()
    w = dict(wires.calendar_wire(ke.HAUPT, "zencloud"))
    r = generations.run(generations.with_wires(sk, [w]), writer=lambda *a: calls.append(a[:2]),
                        health=lambda *a: [])
    assert r.ok and calls == [(ke.HAUPT, "zencloud")]


def test_store_keeps_the_last_n(settings, _test_ordner):
    store = generations.Store(str(_test_ordner / "g"), keep=3)
    base = wires.sketch(hardware=False)
    hashes = []
    for i in range(5):
        sk = generations.with_wires(base, [wires.sync_wire("fokus", "live" if i % 2 else "off")])
        sk["pieces"][0]["title"] = f"n{i}"             # a different generation each time
        gen, errors = sketch_compiler.compile_sketch(sk)
        assert not errors
        store.save(gen)
        store.switch(NODE, gen["hash"])
        hashes.append(gen["hash"])
    assert [h["hash"] for h in store.history(NODE)] == hashes[-3:]
    assert len(os.listdir(os.path.join(store.root, "gen"))) == 3
    assert store.previous(NODE)["hash"] == hashes[-2]


# ── The CLI's sync choice ────────────────────────────────────────────────

class Spiel(Terminal):
    def __init__(self):
        super().__init__(aus=io.StringIO(), ein=io.StringIO(""))

    @property
    def text(self):
        return self.aus.getvalue()


def test_cli_choice_goes_through_the_gate(settings):
    from zentrale_cli import befehle
    _stored(settings, {"fokus": True})
    term = Spiel()
    assert befehle.choose_sync(term, {"notizen": True}) is True
    assert "+ " in term.text and abgleich_apps.entscheidungen() == {"fokus": True, "notizen": True}
    term = Spiel()
    assert befehle.choose_sync(term, {"adapter": False}) is False
    assert "Not changed" in term.text and "app:adapter" in term.text
    assert abgleich_apps.entscheidungen() == {"fokus": True, "notizen": True}


# ── Routes ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client(settings):
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def test_routes(client, settings):
    _stored(settings, {"fokus": True})
    r = client.get("/api/wires")
    assert r.status_code == 200 and r.json["node"] == NODE
    wid = f"sync/{NODE}/fokus"
    assert any(w["id"] == wid for w in r.json["wires"])
    planned = client.delete(f"/api/wires/{wid}?plan=1")
    assert planned.status_code == 200 and len(planned.json["diff"]) == 1
    assert abgleich_apps.entscheidungen() == {"fokus": True}         # only planned
    assert client.delete(f"/api/wires/{wid}").status_code == 200
    assert abgleich_apps.entscheidungen() == {"fokus": False}
    bad = dict(wires.sync_wire("adapter", "off"))
    r = client.put(f"/api/wires/{bad['id']}", json=bad)
    assert r.status_code == 409 and r.json["errors"][0]["code"] == "unmet-requirement"
    assert client.put(f"/api/wires/{wid}", json=dict(bad, id="other")).status_code == 400
    assert client.delete("/api/wires/nope").status_code == 404
