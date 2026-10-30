# core/schematix_map.py
#
# The map of an account for Schematix (memory/hub/building_kit_plan.md 6,
# build step 13; app: memory/hub/schematix.md). Nothing is stored here: the
# map is laid fresh from the truths every time —
#
#   this node      its projection (core/wires.py: pieces with ports, wires)
#                  and its versions (core/schematix_versions.py)
#   other nodes    their descriptions in the cloud (GET /v1/knoten): node
#                  piece (wires.piece_of_description), their own wires
#                  (wires.wires_of_description), their versions section
#
# One piece per app ON a node ("app:tutor@minipc"), because sync is decided
# per node; the cloud is one piece for the account. A wire's ends are map
# pieces; its layer comes from the type registry. The sync state of every
# app on every node is what `zentrale status` on that node says:
#   live wire → synced · off wire → stays on this device · no wire → not
#   decided yet · required (adapter) → always synced.
#
#   build(...)      → {"format", node, pieces, wires, layers, notes}
#   layout(map)     cells (x, y, w, h) per piece, as a cross-section: cloud on
#                   top, apps per node in columns, nodes below, things at the
#                   bottom; a scheme's positions win (step 14)
#
# Service (layer 2).

import abgleich_apps
import port_types
import schematix_kinds
import schematix_versions as versions
import wires
from i18n import _

MAP = "zentrale-schematix-map/1"
LAYERS = ("data", "services", "hardware", "network", "power")
BANDS = ("cloud", "software", "nodes", "things")
CLOUD_ID = "app:cloud"
SYNC_STATES = {"live": "synced", "off": "off"}

# Cells (Desk canvas: 1 column = 10 px, 1 row = 20 px in the file).
APP_W, APP_H = 24, 4
NODE_W, NODE_H = 42, 5
THING_W, THING_H = 24, 4
GAP_X, GAP_Y = 3, 1
BAND_GAP = 4


def map_id(piece_id, node):
    """app:tutor on minipc → app:tutor@minipc; nodes and devices stay."""
    if piece_id.startswith("app:") and piece_id != CLOUD_ID and node:
        return f"{piece_id}@{node}"
    return piece_id


def layer_of(port_type):
    return (port_types.entry(port_type) or {}).get("layer")


def _sync_of(name, node_wires, table, node):
    if (table.get(name) or {}).get("pflicht"):
        return "always"
    w = next((w for w in node_wires if w.get("type") == "sync"
              and w.get("id") == f"sync/{node}/{name}"), None)
    if w is None:
        return "open"
    return SYNC_STATES.get(w.get("state"), w.get("state"))


def _node_piece(base, node, this, desc=None, own_versions=None):
    p = dict(schematix_kinds.with_links(base), band="nodes", node=node, this=this)
    if this:
        p["versions"] = own_versions
        p["cannot_yet"] = []
    else:
        p["versions"] = versions.of_description(desc)
        p["cannot_yet"] = versions.cannot_yet(desc)
        p["seen"] = (desc or {}).get("zuletzt_gesehen")
        p["kind_of_node"] = (desc or {}).get("sorte")
    return p


def _app_piece(base, node, table, node_wires):
    name = base["ref"][len("zentrale://"):].split("/", 1)[0]
    p = dict(base, id=map_id(base["id"], node), piece=base["id"], node=node, band="software",
             name=name)
    if base["id"] == f"app:{name}" and name in table:
        p["sync"] = _sync_of(name, node_wires, table, node)
    return p


def _resolve(address, node, refs):
    """A port address → the map piece it belongs to on `node`."""
    ref, pid = wires.split_port(address)
    if ref == wires.CLOUD:
        return CLOUD_ID, pid
    if ref == wires.node_ref(node):
        return wires.node_id(node), pid
    pid_piece = refs.get(ref)
    return (map_id(pid_piece, node) if pid_piece else None), pid


def _map_wire(w, node, refs):
    a, from_port = _resolve(w.get("from"), node, refs)
    b, to_port = _resolve(w.get("to"), node, refs)
    if a is None or b is None:
        return None
    return dict(w, node=node, layer=layer_of(w.get("type")), from_piece=a, to_piece=b,
                from_port=from_port, to_port=to_port)


def _cloud_piece():
    return {"id": CLOUD_ID, "ref": wires.CLOUD, "kind": "app", "title": "Cloud", "name": "cloud",
            "state": "live", "band": "cloud", "needs": [], "offers": [port_types.offer("sync")]}


def build(own_sketch, this_node, own_versions, descriptions=(), notes=()) -> dict:
    """The map from this node's projection and the other nodes' descriptions."""
    table = abgleich_apps.tabelle()
    pieces = {CLOUD_ID: _cloud_piece()}
    out_wires = []
    # This node: its projection is the truth.
    refs = {p["ref"]: p["id"] for p in own_sketch["pieces"]}
    own_wires = own_sketch["wires"]
    for p in own_sketch["pieces"]:
        if p["kind"] == "node":
            mp = _node_piece(p, this_node, True, own_versions=own_versions)
        elif p["id"] == CLOUD_ID:
            continue
        else:
            mp = _app_piece(p, this_node, table, own_wires)
        pieces[mp["id"]] = mp
    for w in own_wires:
        mw = _map_wire(w, this_node, refs)
        if mw:
            out_wires.append(mw)
    # Other nodes: what they published about themselves.
    for d in sorted(descriptions or [], key=lambda d: str(d.get("name"))):
        name = str(d.get("name") or "")
        if not name or name == this_node or d.get("removed"):
            continue
        base = wires.piece_of_description(d)
        pieces[base["id"]] = _node_piece(base, name, False, desc=d)
        theirs = wires.wires_of_description(d)
        names = list(table)
        for w in theirs:
            if w.get("type") == "sync":
                app = wires._app_of(w)
                if app not in names:
                    names.append(app)
        app_refs = {}
        for app in names:
            base_app = {"id": f"app:{app}", "ref": wires.app_ref(app), "kind": "app",
                        "title": (table.get(app) or {}).get("titel") or app, "state": "live",
                        "on": [wires.node_id(name)], "needs": [port_types.need("sync")],
                        "offers": [], "owns": []}
            mp = _app_piece(base_app, name, table, theirs)
            pieces[mp["id"]] = mp
            app_refs[base_app["ref"]] = base_app["id"]
        for w in theirs:
            mw = _map_wire(w, name, app_refs)
            if mw:
                out_wires.append(mw)
    out_wires += _same_version_wires(pieces.values())
    return {"format": MAP, "node": this_node, "pieces": list(pieces.values()),
            "wires": sorted(out_wires, key=lambda w: w["id"]),
            "layers": [{"id": layer} for layer in LAYERS], "notes": list(notes),
            # the socket table for the board (plan 6.7 stage 1): same type = fits;
            # scope says where a drawn wire lives (link → the scheme)
            "types": {n: {"layer": e["layer"], "scope": e["scope"]} for n, e in port_types.types().items()}}


SAME_VERSION = "same-version"


def _same_version_wires(pieces):
    """"Same version" between nodes (Sasha 30.10., plan 2.2 rule 5): drawn
    from the node that is followed to the node that follows. A setting of
    the following node (core/schematix_versions.py), not a port — never
    compiled, set with `s` in Schematix."""
    nodes = {p.get("node"): p for p in pieces if p.get("kind") == "node"}
    out = []
    for name, p in nodes.items():
        for other in (p.get("versions") or {}).get("same_version") or []:
            if other in nodes and other != name:
                out.append({"id": f"{SAME_VERSION}/{other}/{name}", "type": SAME_VERSION, "layer": "services",
                            "from": wires.port(wires.node_ref(other), "version"),
                            "to": wires.port(wires.node_ref(name), "version"),
                            "state": "live", "owner": wires.node_id(name), "node": name,
                            "from_piece": wires.node_id(other), "to_piece": wires.node_id(name)})
    return out


# ── Layout: a cross-section ─────────────────────────────────────────────

def _node_order(m):
    nodes = [p for p in m["pieces"] if p["kind"] == "node"]
    nodes.sort(key=lambda p: (not p.get("this"), p.get("state") == "planned", str(p.get("node") or p["id"])))
    return [p.get("node") or p["id"].split(":", 1)[1] for p in nodes]


def layout(m, positions=None) -> dict:
    """Give every piece x, y, w, h in cells. `positions` ({id: {x, y, w, h}})
    — from a scheme — win over the automatic place."""
    positions = positions or {}
    order = _node_order(m)
    col_w = 2 * APP_W + GAP_X
    col_x = {n: i * (col_w + 2 * GAP_X) for i, n in enumerate(order)}
    by_node = {}
    for p in m["pieces"]:
        if p.get("band") == "software":
            by_node.setdefault(p.get("node"), []).append(p)
    tallest = max([len(v) for v in by_node.values()] + [1])
    rows = (tallest + 1) // 2
    soft_y = APP_H + BAND_GAP
    node_y = soft_y + rows * (APP_H + GAP_Y) + BAND_GAP
    thing_y = node_y + NODE_H + BAND_GAP
    width = max(col_w, len(order) * (col_w + 2 * GAP_X) - 2 * GAP_X)
    things = 0
    for p in m["pieces"]:
        band = p.get("band")
        if band == "cloud":
            p.update(x=width // 2 - APP_W // 2, y=0, w=APP_W + 4, h=APP_H)
        elif band == "nodes":
            n = p.get("node") or p["id"].split(":", 1)[1]
            p.update(x=col_x.get(n, 0), y=node_y, w=NODE_W, h=NODE_H)
        elif band == "software":
            n = p.get("node")
            i = sorted(by_node.get(n, []), key=lambda q: str(q["id"])).index(p)
            p.update(x=col_x.get(n, 0) + (i % 2) * (APP_W + GAP_X), y=soft_y + (i // 2) * (APP_H + GAP_Y),
                     w=APP_W, h=APP_H)
        else:
            p.update(x=things * (THING_W + GAP_X), y=thing_y, w=THING_W, h=THING_H)
            things += 1
        pos = positions.get(p["id"])
        if isinstance(pos, dict):
            p.update({k: int(pos[k]) for k in ("x", "y", "w", "h") if isinstance(pos.get(k), int)})
    m["bands"] = [{"id": "cloud", "y": 0}, {"id": "software", "y": soft_y},
                  {"id": "nodes", "y": node_y}, {"id": "things", "y": thing_y}]
    return m


def account_descriptions():
    """The account's node descriptions (GET /v1/knoten) → (list, notes).
    Logged out or offline → none, with one note; the map then shows this
    node only."""
    import abgleich
    import konto
    if not abgleich.cloud_an():
        return [], [local_note()]
    try:
        a = konto.client().get("/v1/knoten")
    except Exception:                     # offline, server error: this node only
        return [], [offline_note()]
    liste = a.get("knoten", []) if isinstance(a, dict) else a
    return [d for d in liste or [] if isinstance(d, dict)], []


def offline_note():
    return _("other devices: the cloud is not reachable — only this device is shown")


def local_note():
    return _("not logged in — only this device is shown")
