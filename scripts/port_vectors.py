#!/usr/bin/env python3
"""Test vectors of the building kit's type system — sketches and items,
checked by the REAL core (core/sketch_compiler.py, core/port_types.py).

Every case is a whole, self-contained sketch (made-up nodes and apps, never
Sasha's), written down with the outcome it must have: `ok` with the
generation hash, or the error codes and the piece/wire they are pinned to.
The expected codes are written here BY HAND; the script refuses to write the
file when the compiler disagrees. Item vectors (one piece/wire/manifest and
valid or not) and the built-in apps' port declarations let the phone run the
same schemas (mobile/test/ports_test.dart).

    venv/bin/python scripts/port_vectors.py            # writes the file
    venv/bin/python scripts/port_vectors.py --stdout

Target: contracts/ports/1/port_vectors.json. tests/test_port_types.py fails
while the file is stale.
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

import eingebaute_apps  # noqa: E402
import port_types  # noqa: E402
import sketch_compiler  # noqa: E402

TARGET = os.path.join(ROOT, "contracts", "ports", "1", "port_vectors.json")
ALL = port_types.supported()
OLD = {"sync": "1.0.0", "calendar-source": "1.0.0", "data": "1.0.0", "lan": "1.0.0"}
SYNC = {"id": "data", "type": "sync", "occurrences": [0, 1]}


def _node(name, types, managed=True, needs=()):
    return {"id": f"node:{name}", "ref": f"zentrale://hub/node/{name}/", "kind": "node", "title": name,
            "managed": managed, "types": types, "needs": list(needs),
            "offers": [{"id": "calendar-local", "type": "calendar-source"},
                       {"id": "mic", "type": "mic"}]}


def _app(name, on, needs=(), offers=(), owns=(), state="live"):
    return {"id": f"app:{name}", "ref": f"zentrale://{name}/", "kind": "app", "title": name,
            "state": state, "on": list(on), "needs": list(needs), "offers": list(offers),
            "owns": list(owns)}


def _wire(wid, frm, to, typ, owner, state="live"):
    return {"id": wid, "from": frm, "to": to, "type": typ, "owner": owner, "state": state}


def _sync(node, app, state="live"):
    return _wire(f"sync/{node}/{app}", "zentrale://cloud/port/sync", f"zentrale://{app}/port/data",
                 "sync", f"node:{node}", state)


BOTH = ["node:laptop", "node:minipc"]


def base():
    """Laptop (new), mini-PC (older: knows fewer types), Pi (no apply agent),
    a planned router. Tutor syncs on the laptop, stays local on the mini."""
    pieces = [
        _node("laptop", ALL),
        _node("minipc", OLD, needs=[{"id": "lan", "type": "lan", "occurrences": [0, "UNBOUNDED"]}]),
        _node("pi", OLD, managed=False),
        _app("cloud", BOTH, offers=[{"id": "sync", "type": "sync"},
                                    {"id": "calendar", "type": "calendar-source"}]),
        _app("adapter", BOTH, needs=[dict(SYNC, occurrences=[1, 1])],
             offers=[{"id": "google", "type": "calendar-source"}, {"id": "model", "type": "model"}],
             owns=["file:data/adapter/anschluesse/*.json"]),
        _app("tutor", BOTH + ["node:pi"], needs=[SYNC, "mic@^1"], owns=["file:tutor/data/staende/**"]),
        _app("fokus", ["node:laptop"], needs=[SYNC], owns=["file:data/lists.json"]),
        _app("cloud_folder", ["node:laptop"], needs=[SYNC], offers=["files@1.0.0"],
             owns=["file:data/cloud/**"]),
        _app("pdf", ["node:laptop"], needs=[{"id": "files", "type": "files", "occurrences": [1, 1],
                                             "access": "read"}]),
        {**_app("kalender/kalender-haupt", BOTH, needs=[{"id": "source", "type": "calendar-source"}],
                owns=["setting:kalender-haupt#quelle"]), "ref": "zentrale://kalender/kalender-haupt/"},
        {"id": "device:router", "ref": "zentrale://schematix/thing/router/", "kind": "device",
         "title": "Router", "state": "planned", "role": "router", "offers": ["lan"]},
    ]
    wires = [
        _sync("laptop", "adapter"), _sync("minipc", "adapter"),
        _sync("laptop", "tutor"), _sync("minipc", "tutor", "off"),
        _sync("laptop", "fokus"), _sync("laptop", "cloud_folder"),
        _wire("calendar-source/kalender-haupt", "zentrale://adapter/port/google",
              "zentrale://kalender/kalender-haupt/port/source", "calendar-source",
              "app:kalender/kalender-haupt"),
        _wire("files/pdf", "zentrale://cloud_folder/port/files", "zentrale://pdf/port/files",
              "files", "app:pdf"),
        _wire("lan/minipc/router", "zentrale://schematix/thing/router/port/lan",
              "zentrale://hub/node/minipc/port/lan", "lan", "node:minipc", "planned"),
        _wire("mic/laptop/tutor", "zentrale://hub/node/laptop/port/mic", "zentrale://tutor/port/mic",
              "mic", "node:laptop"),
    ]
    return {"format": "zentrale-sketch/1", "pieces": pieces, "wires": wires}


def _piece(s, pid):
    return next(p for p in s["pieces"] if p["id"] == pid)


def _w(s, wid):
    return next(w for w in s["wires"] if w["id"] == wid)


def _drop(s, wid):
    s["wires"] = [w for w in s["wires"] if w["id"] != wid]


def cases():
    out = []

    def case(name, why, fn, expect, current=None):
        s = base()
        fn(s)
        out.append({"name": name, "why": why, "sketch": s, "expect": expect,
                    **({"current": current} if current is not None else {})})

    case("good", "the base sketch compiles", lambda s: None, {"ok": True})
    case("good-planned-new-type", "a too-new type on an old node is fine while planned",
         lambda s: s["wires"].append(_wire("mic/minipc/tutor", "zentrale://hub/node/minipc/port/mic",
                                           "zentrale://tutor/port/mic", "mic", "node:minipc", "planned")),
         {"ok": True})
    case("double-owner", "two pieces own the same file",
         lambda s: _piece(s, "app:tutor")["owns"].append("file:data/lists.json"),
         {"ok": False, "errors": [{"code": "double-owner", "piece": "app:fokus"},
                                  {"code": "double-owner", "piece": "app:tutor"}]})
    case("unmet-requirement", "the PDF viewer needs exactly one files wire",
         lambda s: _drop(s, "files/pdf"),
         {"ok": False, "errors": [{"code": "unmet-requirement", "piece": "app:pdf", "port": "files"}]})
    case("unmet-required-sync", "the adapter must sync on every node it is on",
         lambda s: _w(s, "sync/minipc/adapter").update(state="off"),
         {"ok": False, "errors": [{"code": "unmet-requirement", "piece": "app:adapter", "port": "data"}]})
    case("live-on-planned", "the mini's LAN wire cannot be live while the router is not yet",
         lambda s: _w(s, "lan/minipc/router").update(state="live"),
         {"ok": False, "errors": [{"code": "live-on-planned", "wire": "lan/minipc/router",
                                   "piece": "device:router"}]})
    case("type-too-new", "the mini does not speak mic yet",
         lambda s: s["wires"].append(_wire("mic/minipc/tutor", "zentrale://hub/node/minipc/port/mic",
                                           "zentrale://tutor/port/mic", "mic", "node:minipc")),
         {"ok": False, "errors": [{"code": "type-too-new", "wire": "mic/minipc/tutor",
                                   "piece": "node:minipc"}]})
    case("schema-invalid", "a wire with an unknown state",
         lambda s: _w(s, "sync/laptop/fokus").update(state="maybe"),
         {"ok": False, "errors": [{"code": "schema", "wire": "sync/laptop/fokus"}]})
    case("schema-invalid-piece", "a piece without a ref",
         lambda s: _piece(s, "app:fokus").pop("ref"),
         {"ok": False, "errors": [{"code": "schema", "piece": "app:fokus"}]})
    case("unknown-type", "a port type nobody registered",
         lambda s: _piece(s, "app:fokus")["needs"].append("teleport@^1"),
         {"ok": False, "errors": [{"code": "unknown-type", "piece": "app:fokus", "port": "teleport"}]})
    case("type-mismatch", "a calendar cannot take the sync port",
         lambda s: _w(s, "calendar-source/kalender-haupt").update({"from": "zentrale://cloud/port/sync"}),
         {"ok": False, "errors": [{"code": "type-mismatch", "wire": "calendar-source/kalender-haupt"},
                                  {"code": "unmet-requirement", "piece": "app:kalender/kalender-haupt",
                                   "port": "source"}]})
    case("version-mismatch", "the tutor wants sync 2, the cloud speaks 1",
         lambda s: _piece(s, "app:tutor")["needs"].__setitem__(0, dict(SYNC, range="^2")),
         {"ok": False, "errors": [{"code": "version-mismatch", "wire": "sync/laptop/tutor"},
                                  {"code": "type-too-new", "wire": "sync/laptop/tutor", "piece": "node:laptop"},
                                  {"code": "version-mismatch", "wire": "sync/minipc/tutor"},
                                  {"code": "type-too-new", "wire": "sync/minipc/tutor", "piece": "node:minipc"}]})
    case("too-many", "a calendar takes exactly one source",
         lambda s: s["wires"].append(_wire("calendar-source/kalender-haupt-2", "zentrale://cloud/port/calendar",
                                           "zentrale://kalender/kalender-haupt/port/source",
                                           "calendar-source", "app:kalender/kalender-haupt")),
         {"ok": False, "errors": [{"code": "too-many", "piece": "app:kalender/kalender-haupt",
                                   "port": "source"}]})
    case("cycle", "the cloud would need a model from the adapter that syncs over the cloud",
         lambda s: (_piece(s, "app:cloud")["needs"].append("model@^1"),
                    s["wires"].append(_wire("model/cloud", "zentrale://adapter/port/model",
                                            "zentrale://cloud/port/model", "model", "app:cloud"))),
         {"ok": False, "errors": [{"code": "cycle", "wire": "sync/laptop/adapter"},
                                  {"code": "cycle", "wire": "sync/minipc/adapter"},
                                  {"code": "cycle", "wire": "model/cloud"},
                                  # the mini does not speak `model` either
                                  {"code": "type-too-new", "wire": "model/cloud", "piece": "node:minipc"}]})
    case("wrong-owner", "a node owns the sync wire of a node the app is not on",
         lambda s: _w(s, "sync/laptop/fokus").update(owner="node:minipc"),
         {"ok": False, "errors": [{"code": "wrong-owner", "wire": "sync/laptop/fokus"}]})
    case("node-unmanaged", "the Pi has no apply agent: its wires cannot be changed",
         lambda s: s["wires"].append(_sync("pi", "tutor")),
         {"ok": False, "errors": [{"code": "node-unmanaged", "wire": "sync/pi/tutor"}]},
         current={})
    case("unmanaged-unchanged", "the Pi's wire as it is passes",
         lambda s: s["wires"].append(_sync("pi", "tutor")),
         {"ok": True}, current={"sync/pi/tutor": _sync("pi", "tutor")})
    return out


def _pinned(errors):
    """The errors without their text, in a fixed order (the order of errors
    is not part of the contract)."""
    out = [{k: e[k] for k in ("code", "piece", "wire", "port") if k in e} for e in errors]
    return sorted(out, key=lambda e: json.dumps(e, sort_keys=True))


def items():
    good_wire = _sync("laptop", "tutor")
    return [
        {"kind": "wire", "valid": True, "item": good_wire},
        {"kind": "wire", "valid": False, "item": dict(good_wire, state="maybe")},
        {"kind": "wire", "valid": False, "item": {k: v for k, v in good_wire.items() if k != "owner"}},
        {"kind": "wire", "valid": False, "item": dict(good_wire, to="zentrale://tutor/data")},
        {"kind": "piece", "valid": True, "item": _app("tutor", ["node:laptop"], needs=["sync@^1"])},
        {"kind": "piece", "valid": False, "item": dict(_app("tutor", []), kind="robot")},
        {"kind": "piece", "valid": False, "item": dict(_app("tutor", []), id="node:tutor")},
        {"kind": "manifestPorts", "valid": True,
         "item": {"needs": ["model", "files@^1", {"type": "event:presence", "occurrences": [0, "UNBOUNDED"]}],
                  "offers": ["tile:list@1.0.0"]}},
        {"kind": "manifestPorts", "valid": False, "item": {"needs": ["Model"]}},
        {"kind": "manifestPorts", "valid": False, "item": {"needs": ["sync@>=1"]}},
        {"kind": "manifestPorts", "valid": False, "item": {"needs": [{"type": "sync", "occurrences": [0, 0]}]}},
    ]


def build():
    out_cases = []
    for c in cases():
        gen, errors = sketch_compiler.compile_sketch(copy.deepcopy(c["sketch"]), c.get("current"))
        got = {"ok": True} if gen else {"ok": False, "errors": _pinned(errors)}
        if not c["expect"]["ok"]:
            c["expect"]["errors"] = _pinned(c["expect"]["errors"])
        if got != c["expect"]:
            raise SystemExit(f"case {c['name']}: expected {c['expect']}, the compiler says {got}")
        if gen:
            c["expect"] = {"ok": True, "hash": gen["hash"]}
        out_cases.append(c)
    for i in items():
        if (port_types.check(i["item"], i["kind"]) == []) != i["valid"]:
            raise SystemExit(f"item vector disagrees: {i}")
    return {"about": "Building kit type system vectors (contracts/ports/1). Generated by "
                     "scripts/port_vectors.py — do not edit by hand.",
            "manifests": {n: eingebaute_apps.PORTS[n] for n in sorted(eingebaute_apps.PORTS)},
            "items": items(), "cases": out_cases}


def text():
    data = build()

    def one(x):
        return json.dumps(x, ensure_ascii=False)

    # One line per case and item: readable diffs, a small file.
    parts = [f'"about": {one(data["about"])}',
             f'"manifests": {one(data["manifests"])}',
             '"items": [\n  ' + ",\n  ".join(one(i) for i in data["items"]) + "\n ]",
             '"cases": [\n  ' + ",\n  ".join(one(c) for c in data["cases"]) + "\n ]"]
    return "{\n " + ",\n ".join(parts) + "\n}\n"


if __name__ == "__main__":
    t = text()
    if "--stdout" in sys.argv:
        sys.stdout.write(t)
    else:
        with open(TARGET, "w", encoding="utf-8") as f:
            f.write(t)
        print(f"written: {TARGET}")
