# core/schematix_scheme.py
#
# A scheme of Schematix (memory/hub/schematix.md, building kit step 14): one
# JSON Canvas 1.0 file (https://jsoncanvas.org/spec/1.0/) per scheme in
# data/schematix/schemes/<name>.canvas — synced, Obsidian opens it. Standard
# fields only; the typed data sits under ONE namespaced key `zentrale` per
# node and edge (plan 6.4). Fields nobody here knows (Obsidian's `color`, a
# newer ZENTRALE's keys) are written back unchanged.
#
# What lives where (plan 6.3) — the scheme never copies a truth:
#   live        this node's projection + the other nodes' descriptions
#               (core/schematix_map.py); the scheme only keeps their place
#   documented  a thing in data/schematix/things/<id>.json (core/schematix_store.py)
#               with its links; the scheme keeps its place
#   planned     only here ("state": "planned" under `zentrale`)
#
# A planned piece carries the address it WILL have (node name, app, thing
# id). When that object appears (a node joins, an app is installed, a thing
# is documented), the piece is live by itself: same id, same reference,
# nothing redrawn. Live wires are written into the file only as a display
# fallback for Obsidian, rewritten from the truth on every save.
#
#   starter()            the scheme "home" from memory/system/heimnetz.md
#   apply(map, canvas)   the map with the scheme's places, planned pieces and
#                        wires and the documented things
#   save(name, body, m)  the board as the TUI sends it → the file
#
# Service (layer 2).

import hashlib
import json
import os
import re

import datasync
import dateien
import desk
import eingebaute_apps
import port_types
import schematix_kinds as kinds
import schematix_map
import schematix_store as store
import wires

KEY = "zentrale"
STARTER = "home"
END = ".canvas"
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
PX_X, PX_Y = desk.PX_SPALTE, desk.PX_ZEILE      # one cell = 10 × 20 px, like the Desk


class SchemeConflict(store.StoreError):
    """The file changed elsewhere since it was loaded; nothing written."""

    def __init__(self, stand):
        super().__init__("the scheme was changed elsewhere", 409)
        self.stand = stand


def folder():
    return os.path.join(store.folder(), "schemes")


def _path(name):
    if not isinstance(name, str) or not _NAME.match(name):
        raise store.StoreError("a scheme name is lowercase letters, digits, - and _")
    return os.path.join(folder(), name + END)


def names() -> list:
    try:
        return sorted(f[:-len(END)] for f in os.listdir(folder()) if f.endswith(END) and not f.startswith("."))
    except FileNotFoundError:
        return []


def load(name):
    """→ (canvas, stand). Missing → 404; broken → 422 (never overwritten)."""
    try:
        with open(_path(name), "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        raise store.StoreError("there is no such scheme", 404)
    try:
        c = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (ValueError, UnicodeDecodeError):
        raise store.StoreError("the scheme file is not valid JSON — look at it by hand", 422)
    if not isinstance(c, dict) or not all(isinstance(c.get(k, []), list) for k in ("nodes", "edges")):
        raise store.StoreError("the scheme file is not JSON Canvas", 422)
    return c, hashlib.sha256(raw).hexdigest()[:16]


def _write(name, canvas):
    path = _path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dateien.json_schreiben(path, canvas)
    datasync.notify_change(path)


# ── Pieces from the file ──────────────────────────────────────────────────

def _cells(n):
    return {"x": round(_num(n.get("x")) / PX_X), "y": round(_num(n.get("y")) / PX_Y),
            "w": max(3, round(_num(n.get("width"), 200) / PX_X)),
            "h": max(3, round(_num(n.get("height"), 80) / PX_Y))}


def _num(x, default=0):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else default


def _title(n, fallback):
    text = str(n.get("text") or n.get("label") or "").strip()
    return text.splitlines()[0].lstrip("# ").strip() if text else fallback


def planned_piece(pid, z, title=None) -> dict | None:
    """A piece that exists only in the scheme, from its `zentrale` key."""
    kind = z.get("kind")
    if kind == "device":
        tid = kinds.thing_id(z.get("ref")) or pid.split(":", 1)[-1]
        p = dict(kinds.device_piece(tid, z.get("thing_kind") or "router", title, state="planned"),
                 band="things")
    elif kind == "node":
        name = pid.split(":", 1)[-1]
        base = {"id": wires.node_id(name), "ref": wires.node_ref(name), "kind": "node",
                "title": title or name, "state": "planned", "managed": True, "types": {},
                "needs": [], "offers": [port_types.offer(x) for x in eingebaute_apps.NODE_PORTS["offers"]],
                "owns": []}
        p = dict(kinds.with_links(base), band="nodes", node=name, this=False, versions=None,
                 cannot_yet=[], address=z.get("address"))
    elif kind == "app":
        ref = str(z.get("ref") or "")
        name = ref[len("zentrale://"):].split("/", 1)[0] if ref.startswith("zentrale://") else pid
        node = z.get("node")
        p = {"id": pid, "piece": "app:" + name, "ref": wires.app_ref(name), "kind": "app", "title": title or name,
             "name": name, "state": "planned", "band": "software", "node": node,
             "on": [wires.node_id(node)] if node else [], "needs": [port_types.need("sync")], "offers": [],
             "owns": [], "store": z.get("store")}
    else:
        return None
    if z.get("address"):
        p["address"] = z["address"]
    return p


def _thing_piece(t):
    p = kinds.device_piece(t["id"], t["kind"], t.get("title"), state="documented")
    return dict(p, band="things", address=t.get("address"), notes=t.get("notes"))


def _index(pieces):
    """ref → piece id for nodes and things (link ends)."""
    return {p["ref"]: p["id"] for p in pieces if p.get("kind") in ("node", "device")}


def _link_wire(link, owner, refs):
    a = refs.get(wires.split_port(link["from"])[0])
    b = refs.get(wires.split_port(link["to"])[0])
    if a is None or b is None:
        return None
    return {"id": link["id"], "from": link["from"], "to": link["to"], "type": link["type"],
            "owner": owner, "state": link.get("state", "live"), "documented": True,
            "layer": schematix_map.layer_of(link["type"]), "from_piece": a, "to_piece": b,
            "from_port": wires.split_port(link["from"])[1], "to_port": wires.split_port(link["to"])[1]}


def apply(m, canvas, things=None, name=STARTER, stand=None) -> dict:
    """The live map `m` with the scheme: documented things, planned pieces
    and wires, places. A planned piece whose object is there is live."""
    things = store.things() if things is None else things
    pieces = {p["id"]: p for p in m["pieces"]}
    for t in things:
        tp = _thing_piece(t)
        pieces.setdefault(tp["id"], tp)
    positions, planned_ids = {}, []
    for n in canvas.get("nodes") or []:
        z = n.get(KEY) if isinstance(n, dict) else None
        if not isinstance(z, dict) or not isinstance(n.get("id"), str):
            continue
        pid = z.get("piece") or n["id"]
        if all(k in n for k in ("x", "y")):      # a new planned node has no place yet
            positions[pid] = _cells(n)
        if pid in pieces:
            continue                              # live (or documented) wins: same reference
        if z.get("state") == "planned":
            p = planned_piece(pid, z, _title(n, None))
            if p:
                pieces[pid] = p
                planned_ids.append(pid)
    out_wires = {w["id"]: w for w in m["wires"]}
    refs = _index(pieces.values())
    for t in things:
        for link in t.get("links") or []:
            w = _link_wire(link, "device:" + t["id"], refs)
            if w:
                out_wires.setdefault(w["id"], w)
    for e in canvas.get("edges") or []:
        z = e.get(KEY) if isinstance(e, dict) else None
        if not isinstance(z, dict) or z.get("state") != "planned":
            continue
        wid = z.get("wire") or e.get("id")
        if wid in out_wires or e.get("fromNode") not in pieces or e.get("toNode") not in pieces:
            continue
        out_wires[wid] = {"id": wid, "from": z.get("from"), "to": z.get("to"), "type": z.get("type"),
                          "owner": z.get("owner") or e["fromNode"], "state": "planned",
                          "layer": schematix_map.layer_of(z.get("type")), "from_piece": e["fromNode"],
                          "to_piece": e["toNode"], "from_port": wires.split_port(z.get("from"))[1],
                          "to_port": wires.split_port(z.get("to"))[1]}
    out = dict(m, pieces=list(pieces.values()), wires=sorted(out_wires.values(), key=lambda w: w["id"]),
               scheme={"name": name, "stand": stand, "planned": planned_ids})
    return schematix_map.layout(out, positions)


# ── The starter scheme from memory/system/heimnetz.md ──────────────────────

# Adressplan of heimnetz.md (target picture): the router takes .254, the PC
# .1, the Pi .10, Pi 2 .11, laptop .20, mini .21; the fibre modem in front of
# the router; WireGuard for the laptop and the mini on the road. Plus the
# power bank of the mini (plan 6.6) and the tablet with Tailscale to the
# mini, which is live today (Sasha 30.10.).
HOME_NODES = (("pc", "PC", "192.168.50.1"), ("pi", "Pi", "192.168.50.10"),
              ("pi2", "Pi 2 (media)", "192.168.50.11"), ("laptop", "Laptop", "192.168.50.20"),
              ("minipc", "Mini-PC", "192.168.50.21"))
HOME_THINGS = (("router", "router", "Router (Flint 2)", "192.168.50.254"),
               ("modem", "modem", "Fibre modem (ONT)", None),
               ("switch", "switch", "Switch", None),
               ("power-bank", "power-bank", "Power bank", None))
TABLET = {"id": "tablet", "kind": "tablet", "title": "Tablet",
          "notes": "Tailscale to the Mini-PC — live today (Sasha 30.10.).",
          "links": [{"id": "tailscale/minipc/tablet", "type": "tailscale", "state": "live",
                     "from": "zentrale://hub/node/minipc/port/tailscale-out",
                     "to": kinds.thing_ref("tablet") + "port/tailscale"}]}


def _p(ref, pid):
    return ref + "port/" + pid


def _starter_wires():
    router = kinds.thing_ref("router")
    out = [("cable/modem/router", "cable", _p(kinds.thing_ref("modem"), "wan"), _p(router, "wan"),
            "device:modem", "device:router")]
    for name, _t, _a in HOME_NODES:
        out.append((f"lan/router/{name}", "lan", _p(router, "lan"), _p(wires.node_ref(name), "lan"),
                    "device:router", wires.node_id(name)))
    for name in ("laptop", "minipc"):
        out.append((f"wireguard/router/{name}", "wireguard", _p(router, "wireguard"),
                    _p(wires.node_ref(name), "wireguard"), "device:router", wires.node_id(name)))
    out.append(("power/power-bank/minipc", "power", _p(kinds.thing_ref("power-bank"), "power"),
                _p(wires.node_ref("minipc"), "power"), "device:power-bank", wires.node_id("minipc")))
    return out


def starter(m, things=None) -> dict:
    """The canvas of the scheme "home": every heimnetz.md piece planned
    except the nodes that already report (they are in the map, live).
    Positions from the cross-section layout."""
    nodes = []
    for name, title, addr in HOME_NODES:
        nodes.append({"id": wires.node_id(name), "type": "text", "text": title,
                      KEY: {"piece": wires.node_id(name), "kind": "node", "ref": wires.node_ref(name),
                            "state": "planned", "address": addr}})
    for tid, kind, title, addr in HOME_THINGS:
        nodes.append({"id": "device:" + tid, "type": "text", "text": title,
                      KEY: {"piece": "device:" + tid, "kind": "device", "ref": kinds.thing_ref(tid),
                            "thing_kind": kind, "state": "planned",
                            **({"address": addr} if addr else {})}})
    edges = []
    for wid, typ, frm, to, a, b in _starter_wires():
        edges.append({"id": wid, "fromNode": a, "toNode": b, "label": typ,
                      KEY: {"wire": wid, "type": typ, "from": frm, "to": to, "owner": a,
                            "state": "planned", "layer": schematix_map.layer_of(typ)}})
    canvas = {"nodes": nodes, "edges": edges}
    laid = apply(m, canvas, things)
    return to_canvas(laid, {"nodes": [], "edges": []}, home_group=True)


def ensure_starter(m):
    """Create the scheme "home" (and the tablet, a documented thing with its
    live Tailscale link) when there is no scheme yet."""
    if names():
        return
    things = store.things()
    if not any(t["id"] == TABLET["id"] for t in things):
        things.append(store.write_thing(dict(TABLET)))
    _write(STARTER, starter(m, things))


# ── Writing the file ──────────────────────────────────────────────────────

def _z_of(p):
    z = {"piece": p["id"], "kind": p["kind"], "ref": p["ref"], "state": p.get("state", "live")}
    for k in ("node", "thing_kind", "address", "store"):
        if p.get(k):
            z[k] = p[k]
    return z


def to_canvas(m, old, home_group=False) -> dict:
    """The laid-out map (pieces with cells, wires) → JSON Canvas, on top of
    the old file: every node and edge keeps the fields this code does not
    write; nodes/edges without `zentrale` (Obsidian's own) stay as they are.
    A position is only rewritten when it changed in cells (pixel-exact
    Obsidian positions stay)."""
    old_nodes = {n.get("id"): n for n in old.get("nodes") or [] if isinstance(n, dict)}
    old_edges = {e.get("id"): e for e in old.get("edges") or [] if isinstance(e, dict)}
    nodes, edges, ids = [], [], set()
    for p in m["pieces"]:
        prev = old_nodes.get(p["id"])
        n = dict(prev) if prev else {"id": p["id"], "type": "text"}
        cells = {k: p[k] for k in ("x", "y", "w", "h")}
        was = _cells(prev) if prev else {}
        if (cells["x"], cells["y"]) != (was.get("x"), was.get("y")):
            n.update(x=cells["x"] * PX_X, y=cells["y"] * PX_Y)
        if (cells["w"], cells["h"]) != (was.get("w"), was.get("h")):
            n.update(width=cells["w"] * PX_X, height=cells["h"] * PX_Y)
        if n.get("type") == "text":
            n["text"] = str(p.get("title") or p["id"])
        z = prev.get(KEY) if prev and isinstance(prev.get(KEY), dict) else {}
        n[KEY] = dict(z, **_z_of(p))
        nodes.append(n)
        ids.add(p["id"])
    for nid, n in old_nodes.items():
        if nid not in ids and not isinstance(n.get(KEY), dict):
            nodes.append(n)                        # Obsidian's own node (a note, a group)
    if home_group and nodes:
        x0 = min(n["x"] for n in nodes) - 40
        y0 = min(n["y"] for n in nodes) - 60
        x1 = max(n["x"] + n["width"] for n in nodes) + 40
        y1 = max(n["y"] + n["height"] for n in nodes) + 40
        nodes.insert(0, {"id": "g-home", "type": "group", "label": "Home", "x": x0, "y": y0,
                         "width": x1 - x0, "height": y1 - y0})
    for w in m["wires"]:
        if w["from_piece"] not in ids or w["to_piece"] not in ids:
            continue
        prev = old_edges.get(w["id"])
        e = dict(prev) if prev else {"id": w["id"]}
        e.update(fromNode=w["from_piece"], toNode=w["to_piece"])
        e.setdefault("label", w["type"])
        z = prev.get(KEY) if prev and isinstance(prev.get(KEY), dict) else {}
        e[KEY] = dict(z, wire=w["id"], type=w["type"], layer=w.get("layer"), state=w["state"],
                      **{k: w[k] for k in ("from", "to", "owner") if w.get(k)})
        edges.append(e)
    known = {e["id"] for e in edges}
    for eid, e in old_edges.items():
        if eid not in known and not isinstance(e.get(KEY), dict) and e.get("fromNode") in ids | set(old_nodes) \
                and e.get("toNode") in ids | set(old_nodes):
            edges.append(e)                        # an Obsidian arrow between notes
    return dict(old, nodes=nodes, edges=edges)


def _cells_of(d):
    out = {}
    for k in ("x", "y", "w", "h"):
        v = d.get(k)
        if isinstance(v, bool) or not isinstance(v, int) or abs(v) > desk.KOORD_GRENZE:
            raise store.StoreError("a place is whole cells")
        out[k] = v
    if not (3 <= out["w"] <= 2000 and 3 <= out["h"] <= 2000):
        raise store.StoreError("a piece is 3 to 2000 cells")
    return out


def save(name, body, live_map) -> dict:
    """The board from the TUI → the file. body = {stand, pieces: [{id, x, y,
    w, h, planned?: {kind, ref, title, node, thing_kind, address, store}}],
    wires: [planned wires {id, from_piece, to_piece, type, from, to, owner}]}.
    The scheme's own content (planned pieces and wires) is exactly what is
    sent; live pieces keep coming from the truth. → the map with the scheme."""
    try:
        canvas, now = load(name)
    except store.StoreError as e:
        if e.code != 404:
            raise
        canvas, now = {"nodes": [], "edges": []}, None
    if body.get("stand") is not None and body.get("stand") != now:
        raise SchemeConflict(now)
    pieces = body.get("pieces")
    if not isinstance(pieces, list):
        raise store.StoreError("pieces missing")
    places, planned_nodes = {}, []
    for d in pieces:
        if not isinstance(d, dict) or not isinstance(d.get("id"), str):
            raise store.StoreError("a piece without id")
        places[d["id"]] = _cells_of(d)
        pl = d.get("planned")
        if isinstance(pl, dict):
            z = {k: pl[k] for k in ("kind", "ref", "node", "thing_kind", "address", "store") if pl.get(k)}
            if planned_piece(d["id"], z) is None:
                raise store.StoreError("a planned piece needs its kind and address")
            planned_nodes.append({"id": d["id"], "type": "text", "text": str(pl.get("title") or d["id"]),
                                  KEY: dict(z, piece=d["id"], state="planned")})
    planned_edges = []
    for w in body.get("wires") or []:
        if not isinstance(w, dict) or not all(isinstance(w.get(k), str) for k in ("id", "from_piece", "to_piece", "type")):
            raise store.StoreError("a planned wire needs id, ends and type")
        planned_edges.append({"id": w["id"], "fromNode": w["from_piece"], "toNode": w["to_piece"],
                              KEY: {"wire": w["id"], "type": w["type"], "state": "planned",
                                    **{k: w[k] for k in ("from", "to", "owner") if isinstance(w.get(k), str)}}})
    # The scheme as it will be: old fields kept, planned content replaced.
    kept_nodes = [n for n in canvas.get("nodes") or [] if not (isinstance(n.get(KEY), dict)
                                                              and n[KEY].get("state") == "planned")]
    kept_edges = [e for e in canvas.get("edges") or [] if not (isinstance(e.get(KEY), dict)
                                                              and e[KEY].get("state") == "planned")]
    old_by_id = {n.get("id"): n for n in canvas.get("nodes") or []}
    for n in planned_nodes:
        prev = old_by_id.get(n["id"])
        if isinstance(prev, dict):                 # keep its unknown fields
            n = dict(prev, **{k: v for k, v in n.items() if k != KEY},
                     **{KEY: dict(prev.get(KEY) or {}, **n[KEY])})
        kept_nodes.append(n)
    old_edges = {e.get("id"): e for e in canvas.get("edges") or []}
    for i, e in enumerate(planned_edges):
        prev = old_edges.get(e["id"])
        if isinstance(prev, dict):                 # keep its unknown fields
            planned_edges[i] = dict(prev, **{k: v for k, v in e.items() if k != KEY},
                                    **{KEY: dict(prev.get(KEY) or {}, **e[KEY])})
    draft = dict(canvas, nodes=kept_nodes, edges=kept_edges + planned_edges)
    merged = apply(live_map, draft, name=name)
    for p in merged["pieces"]:
        if p["id"] in places:
            p.update(places[p["id"]])
    new = to_canvas(merged, draft)
    _write(name, new)
    return scheme_map(live_map, name)


def scheme_map(live_map, name=STARTER) -> dict:
    """The map with scheme `name` (created from heimnetz.md the first time)."""
    if name == STARTER:
        ensure_starter(live_map)
    canvas, stand = load(name)
    return apply(live_map, canvas, name=name, stand=stand)
