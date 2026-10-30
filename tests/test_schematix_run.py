"""Schematix step 15 (memory/hub/schematix.md): rewire by drawing, Run from
the board = check → diff → switch through generations.run.

Acceptance: unplug tutor → sync on the map, Run, the diff shows one line;
after the switch `zentrale status` on that node shows "stays on this
device". Planned items are checked but never applied; errors are pinned to
pieces; another node's wire is refused; the red ✕ text comes from the
socket table; "same version" is settable here."""
import io
import re

import pytest

import abgleich_apps
import ai_config
import schematix_map
import schematix_run
import schematix_scheme
import schematix_versions
from zentrale_cli import haupt
from zentrale_cli.ausgabe import Terminal


@pytest.fixture
def client(_test_ordner, monkeypatch):
    path = _test_ordner / "ai_config.json"
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(path))
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setenv("ZENTRALE_NODE_NAME", "laptop")
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "datei")
    abgleich_apps.setzen({"tutor": True, "fokus": True})
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


CORE = ("id", "from", "to", "type", "owner", "state")


def _wire(m, wid):
    return next({k: w[k] for k in CORE} for w in m["wires"] if w["id"] == wid)


def _status_line(app_name):
    term = Terminal(aus=io.StringIO(), ein=io.StringIO(""))
    assert haupt.main(["status"], term=term) == 0
    m = re.search(r"^\s+%s\s{2,}(.+)$" % re.escape(app_name), term.aus.getvalue(), re.M)
    return m.group(1).strip() if m else None


def test_unplug_tutor_run_one_line_then_status_says_it(client):
    m = client.get("/api/schematix/map").json
    off = dict(_wire(m, "sync/laptop/tutor"), state="off")
    plan = client.post("/api/schematix/run", json={"changes": [off], "scheme": "home"})
    assert plan.status_code == 200, plan.json
    assert len(plan.json["diff"]) == 1 and plan.json["diff"][0].startswith("~ ")
    assert abgleich_apps.entscheidungen()["tutor"] is True                 # only planned
    assert _status_line("Tutor") == "synced"
    r = client.post("/api/schematix/run", json={"changes": [off], "scheme": "home", "apply": True})
    assert r.status_code == 200 and r.json["applied"] and not r.json["rolled_back"]
    assert abgleich_apps.entscheidungen()["tutor"] is False
    assert _status_line("Tutor") == "stays on this device"
    m2 = client.get("/api/schematix/map").json
    assert next(p for p in m2["pieces"] if p["id"] == "app:tutor@laptop")["sync"] == "off"


def test_errors_are_pinned_to_the_pieces(client):
    m = client.get("/api/schematix/map").json
    bad = dict(_wire(m, "sync/laptop/adapter"), state="off")             # the adapter must sync
    r = client.post("/api/schematix/run", json={"changes": [bad], "scheme": "home"})
    assert r.status_code == 409
    assert any(e["code"] == "unmet-requirement" and e.get("piece") == "app:adapter" for e in r.json["errors"])
    assert abgleich_apps.entscheidungen() == {"tutor": True, "fokus": True}


def test_planned_items_are_checked_but_never_applied(client):
    client.get("/api/schematix/map")
    canvas, _s = schematix_scheme.load("home")
    canvas["edges"].append({"id": "lan/router/cloud", "fromNode": "device:router", "toNode": "app:cloud",
                            "zentrale": {"wire": "lan/router/cloud", "type": "lan", "state": "planned",
                                         "from": "zentrale://schematix/things/router/port/lan",
                                         "to": "zentrale://cloud/port/lan", "owner": "device:router"}})
    schematix_scheme._write("home", canvas)
    m = client.get("/api/schematix/map").json
    off = dict(_wire(m, "sync/laptop/tutor"), state="off")
    r = client.post("/api/schematix/run", json={"changes": [off], "scheme": "home", "apply": True})
    assert r.status_code == 409                                              # a broken plan is broken
    assert any(e.get("wire") == "lan/router/cloud" for e in r.json["errors"])
    assert abgleich_apps.entscheidungen()["tutor"] is True                 # nothing switched
    # Without the broken one: the planned LAN wires pass the check and stay planned.
    canvas["edges"] = [e for e in canvas["edges"] if e["id"] != "lan/router/cloud"]
    schematix_scheme._write("home", canvas)
    r = client.post("/api/schematix/run", json={"changes": [off], "scheme": "home", "apply": True})
    assert r.status_code == 200 and len(r.json["diff"]) == 1, r.json        # planned: not in the diff


def test_another_nodes_wire_is_refused_here(client):
    w = {"id": "sync/minipc/tutor", "from": "zentrale://cloud/port/sync", "to": "zentrale://tutor/port/data",
         "type": "sync", "owner": "node:minipc", "state": "off"}
    r = client.post("/api/schematix/run", json={"changes": [w], "scheme": "home"})
    assert r.status_code == 409 and "run Schematix there" in r.json["errors"][0]["text"]


def test_the_socket_table_says_why_it_does_not_fit():
    pdf = {"id": "app:pdf", "title": "PDF viewer", "needs": [{"id": "files", "type": "files"}], "offers": []}
    cloud = {"id": "app:cloud", "title": "Cloud", "needs": [], "offers": [{"id": "sync", "type": "sync"}]}
    assert schematix_run.fits(pdf, cloud) == []
    assert schematix_run.misfit_text(cloud, pdf) == "PDF viewer needs `files`, Cloud offers `sync`"
    folder = {"id": "app:cloud_folder", "title": "Cloud folder", "needs": [],
              "offers": [{"id": "files", "type": "files"}]}
    assert [(o["type"], n["type"]) for _p, _c, o, n in schematix_run.fits(pdf, folder)] == [("files", "files")]


def test_same_version_is_set_here_and_drawn(client, monkeypatch):
    r = client.put("/api/schematix/same-version", json={"nodes": ["minipc"]})
    assert r.status_code == 200 and r.json["same_version"] == ["minipc"]
    assert schematix_versions.same_version() == ["minipc"]
    mini = {"name": "minipc", "programm": "44", "types": {"sync": "1.0.0"}, "apply_agent": 1}
    monkeypatch.setattr(schematix_map, "account_descriptions", lambda: ([mini], []))
    m = client.get("/api/schematix/map").json
    w = next(w for w in m["wires"] if w["type"] == "same-version")
    assert (w["from_piece"], w["to_piece"]) == ("node:minipc", "node:laptop")
    assert client.put("/api/schematix/same-version", json={"nodes": "x"}).status_code == 400
