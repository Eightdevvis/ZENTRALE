# core/schematix_kinds.py
#
# Kinds of things without ZENTRALE (router, switch, cable, power bank …) and
# the link ports every node gets on the map — data in
# contracts/schematix/1/kinds.json, read once (memory/hub/schematix.md).
# A thing is a `device` piece (contracts/ports/1, TOSCA node template) with
# the NetBox role of its kind; its ports use the port type registry, so the
# compiler checks network and power wires like any other.
#
#   kinds()                 kind → {title, netbox, needs, offers}
#   device_piece(...)       a thing (documented or planned) as a piece
#   with_links(node_piece)  a node piece plus its network/power sockets
#   picker()                the device entries of the `+` picker
#
# Foundation (layer 1).

import functools
import json
import os

import port_types

_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FILE = os.path.join(_ROOT, "contracts", "schematix", "1", "kinds.json")
THING_PREFIX = "zentrale://schematix/things/"


@functools.lru_cache(maxsize=1)
def _data() -> dict:
    with open(FILE, encoding="utf-8") as f:
        return json.load(f)


def kinds() -> dict:
    return _data()["kinds"]


def thing_ref(tid) -> str:
    return f"{THING_PREFIX}{tid}/"


def thing_id(ref):
    """zentrale://schematix/things/router/ → router (or None)."""
    if isinstance(ref, str) and ref.startswith(THING_PREFIX):
        return ref[len(THING_PREFIX):].strip("/") or None
    return None


def device_piece(tid, kind, title=None, state="documented") -> dict:
    k = kinds().get(kind) or {"title": kind, "netbox": kind, "needs": [], "offers": []}
    return {"id": "device:" + tid, "ref": thing_ref(tid), "kind": "device", "role": k["netbox"],
            "title": title or k["title"], "state": state, "thing_kind": kind,
            "needs": [port_types.need(x) for x in k["needs"]],
            "offers": [port_types.offer(x) for x in k["offers"]], "owns": []}


def with_links(node_piece) -> dict:
    """The node piece with network/power sockets added (ids that are not
    taken already) — what network and power wires plug into."""
    links = _data()["node_links"]
    p = dict(node_piece)
    have_n = {x["id"] for x in p.get("needs") or []}
    have_o = {x["id"] for x in p.get("offers") or []}
    p["needs"] = list(p.get("needs") or []) + [n for n in map(port_types.need, links["needs"])
                                                if n["id"] not in have_n]
    p["offers"] = list(p.get("offers") or []) + [o for o in map(port_types.offer, links["offers"])
                                                  if o["id"] not in have_o]
    return p


def picker() -> list:
    out = []
    for kind, k in sorted(kinds().items()):
        out.append({"id": "kind:" + kind, "kind": "device", "thing_kind": kind, "title": k["title"],
                    "role": k["netbox"], "ref": None, "state": "planned",
                    "needs": [port_types.need(x) for x in k["needs"]],
                    "offers": [port_types.offer(x) for x in k["offers"]]})
    return out
