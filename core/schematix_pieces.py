# core/schematix_pieces.py
#
# Everything that can be placed on a scheme — the `+` picker of Schematix
# (memory/hub/building_kit_plan.md 6.5, build step 13). Fresh on every call,
# like the Desk's tile catalog: a newly installed app shows up by itself.
#
#   installed   app pieces of this node with their ports (core/wires.py)
#   provider    pieces that offer something to others (cloud, adapter …)
#   node        the account's nodes (this one and GET /v1/knoten)
#   store       store apps not installed here — placed as planned; the
#               action "install" is the store's normal install + plug dialog
#   device      kinds of things without ZENTRALE (router, switch, cable,
#               power bank …) — documented or planned (step 14)
#
# Service (layer 2).

import app_register
import schematix_kinds
import shop
import wires


def _entry(p, group, **more):
    return dict({"group": group, "id": p["id"], "ref": p["ref"], "kind": p["kind"],
                 "title": p.get("title") or p["id"], "needs": p.get("needs") or [],
                 "offers": p.get("offers") or [], "state": p.get("state", "live")}, **more)


def _store_apps():
    installed = set(app_register.namen())
    out = []
    try:
        items = shop.katalog("apps").get("itemListElement") or []
    except Exception:                      # a broken catalog never breaks the picker
        return out
    for it in items:
        s = it.get("item") or {}
        name = app_register.app_name(s)
        if not name or name in installed or app_register.built_in(s):
            continue
        out.append({"group": "store", "id": "app:" + name, "ref": wires.app_ref(name), "kind": "app",
                    "title": s.get("name") or name, "needs": [], "offers": [], "state": "planned",
                    "store": s.get("@id")})
    return out


def catalog(own_sketch, this_node, descriptions=()) -> dict:
    out = []
    for p in own_sketch["pieces"]:
        if p["kind"] == "node":
            continue
        group = "provider" if p.get("offers") else "installed"
        out.append(_entry(p, group, node=this_node))
    nodes = {this_node} | {str(d.get("name")) for d in descriptions or []
                           if d.get("name") and not d.get("removed")}
    for n in sorted(nodes):
        out.append({"group": "node", "id": wires.node_id(n), "ref": wires.node_ref(n), "kind": "node",
                    "title": n, "needs": [], "offers": [], "state": "live", "this": n == this_node})
    out += _store_apps()
    out += [dict(k, group="device") for k in schematix_kinds.picker()]
    return {"pieces": out}
