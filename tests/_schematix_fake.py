"""A small, laid-out Schematix map for the TUI tests without a backend
(tests/test_fussleiste.py `antwort`, tests/tasten_zustaende/schematix.py,
tests/test_schematix_tui.py). The node `minipc` sits in the middle: a piece
in every direction, so every arrow does something from there."""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _palette():
    with open(os.path.join(ROOT, "contracts", "schematix", "1", "palette.json"), encoding="utf-8") as f:
        roles = json.load(f)["roles"]
    return {"roles": roles, "measured": {k: 7.0 for k in roles if k != "board"},
            "defaults": dict(roles), "minimum": 4.5}


def _node(name, x, this=False, state="live"):
    return {"id": "node:" + name, "ref": "zentrale://hub/node/%s/" % name, "kind": "node", "title": name,
            "state": state, "band": "nodes", "node": name, "this": this, "managed": True,
            "versions": {"format": "zentrale-node-versions/1", "zentrale": "44", "apps": {},
                         "contracts": {"ports": [1]}, "auto_update": True, "same_version": [],
                         "cloud": True},
            "cannot_yet": [], "needs": [{"id": "lan", "type": "lan"}, {"id": "power", "type": "power"}],
            "offers": [{"id": "tailscale", "type": "tailscale"}],
            "x": x, "y": 20, "w": 42, "h": 5}


def _app(name, node, x, sync="synced"):
    return {"id": "app:%s@%s" % (name, node), "piece": "app:" + name, "ref": "zentrale://%s/" % name,
            "kind": "app", "title": name.title(), "name": name, "state": "live", "band": "software",
            "node": node, "sync": sync, "needs": [{"id": "data", "type": "sync"}], "offers": [],
            "x": x, "y": 8, "w": 24, "h": 4}


def _wire(app, node, state="live"):
    return {"id": "sync/%s/%s" % (node, app), "from": "zentrale://cloud/port/sync",
            "to": "zentrale://%s/port/data" % app, "type": "sync", "owner": "node:" + node,
            "state": state, "layer": "data", "node": node, "from_piece": "app:cloud",
            "to_piece": "app:%s@%s" % (app, node), "from_port": "sync", "to_port": "data"}


MAP = {
    "format": "zentrale-schematix-map/1", "node": "laptop", "notes": [],
    "scheme": {"name": "home", "stand": "s1", "planned": ["node:pc", "device:router"]},
    "layers": [{"id": x} for x in ("data", "services", "hardware", "network", "power")],
    "bands": [{"id": "cloud", "y": 0}, {"id": "software", "y": 8}, {"id": "nodes", "y": 20},
              {"id": "things", "y": 32}],
    "pieces": [
        {"id": "app:cloud", "ref": "zentrale://cloud/", "kind": "app", "title": "Cloud", "name": "cloud",
         "state": "live", "band": "cloud", "needs": [], "offers": [{"id": "sync", "type": "sync"}],
         "x": 40, "y": 0, "w": 24, "h": 4},
        _app("fokus", "laptop", 0), _app("tutor", "minipc", 55, "off"),
        _node("laptop", 0, this=True), _node("minipc", 50), _node("pc", 100, state="planned"),
        {"id": "device:router", "ref": "zentrale://schematix/things/router/", "kind": "device",
         "title": "Router", "role": "router", "state": "planned", "band": "things",
         "needs": [{"id": "power", "type": "power"}], "offers": [{"id": "lan", "type": "lan"}],
         "x": 60, "y": 32, "w": 24, "h": 4},
    ],
    "wires": [_wire("fokus", "laptop"), _wire("tutor", "minipc", "off")],
}


PIECES = [
    {"group": "node", "id": "node:minipc", "ref": "zentrale://hub/node/minipc/", "kind": "node",
     "title": "minipc", "needs": [], "offers": [], "state": "live"},
    {"group": "store", "id": "app:budget", "ref": "zentrale://budget/", "kind": "app", "title": "Budget",
     "needs": [], "offers": [], "state": "planned"},
    {"group": "device", "id": "kind:switch", "kind": "device", "thing_kind": "switch", "title": "Switch",
     "role": "switch", "ref": None, "state": "planned", "needs": [{"id": "uplink", "type": "lan"}],
     "offers": [{"id": "lan", "type": "lan"}]},
]


def answer(path, method):
    p = path.split("?")[0]
    if p == "/api/schematix/map":
        return copy.deepcopy(MAP)
    if p.startswith("/api/schematix/palette"):
        return _palette()
    if p == "/api/pieces":
        return {"pieces": copy.deepcopy(PIECES)}
    if p.startswith("/api/schematix/schemes/"):
        return copy.deepcopy(MAP)
    return {"ok": True}
