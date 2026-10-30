# core/schematix_run.py
#
# Run from the drawing (memory/hub/building_kit_plan.md 6.7, build step 15;
# app: memory/hub/schematix.md). The board sends the wires it changed (a
# plug drawn, a wire unplugged); this is the same gate as every other change:
#
#   1. this node's projection + the changes = the sketch of this node
#      (only wires this node may write — another node's wire is refused:
#      "run Schematix there", its owner store lives on that node)
#   2. the whole scheme is checked with it: planned pieces and wires,
#      documented things and their links, the other nodes — stages 2–3 of
#      the compiler, errors pinned to pieces and wires. Planned items are
#      checked, never applied.
#   3. generations.run on the sketch of this node: diff, switch, apply,
#      health check, roll-back (apply=False: the diff only)
#
#   run(changes, scheme, live_map, apply)  → RunResult-like dict
#   fits(a, b)                            the socket table for the red ✕
#
# Service (layer 2).

import generations
import schematix_kinds as kinds
import schematix_scheme
import schematix_store as store
import sketch_compiler
import wires
from i18n import _


def _types(ports):
    return sorted({p["type"] for p in ports or []})


def fits(a, b) -> list:
    """(provider, consumer, offer, need) for every offer of one piece that a
    need of the other takes: same type — the socket table of plan 6.7."""
    out = []
    for prov, cons in ((a, b), (b, a)):
        for o in prov.get("offers") or []:
            for n in cons.get("needs") or []:
                if o.get("type") == n.get("type"):
                    out.append((prov, cons, o, n))
    return out


def misfit_text(a, b) -> str:
    """'PDF viewer needs `files`, Cloud offers `sync`' (plan 6.7 stage 1)."""
    def t(p):
        return p.get("title") or p.get("id")
    cons, prov = (a, b) if a.get("needs") and not a.get("offers") else (b, a)
    needs = ", ".join("`%s`" % x for x in _types(cons.get("needs"))) or _("nothing")
    offers = ", ".join("`%s`" % x for x in _types(prov.get("offers"))) or _("nothing")
    return _("{a} needs {needs}, {b} offers {offers}").format(a=t(cons), needs=needs, b=t(prov), offers=offers)


def _mine(w, node):
    return wires._writable(w, node) or w.get("state") == "planned"


def _scheme_items(m, sketch, node):
    """The scheme's own items for the check: planned pieces (not already a
    piece of the sketch by reference), documented things, the other nodes,
    planned wires and documented links. Node pieces get their link sockets."""
    refs = {p["ref"] for p in sketch["pieces"]}
    ids = {p["id"] for p in sketch["pieces"]}
    pieces, extra_wires = [], []
    for p in m["pieces"]:
        base = {k: p[k] for k in ("id", "ref", "kind", "title", "state", "needs", "offers", "owns",
                                  "on", "managed", "types", "role") if k in p}
        if p.get("kind") == "node" and p["id"] not in ids:
            pieces.append(kinds.with_links(dict(base, needs=base.get("needs") or [],
                                                offers=base.get("offers") or [])))
        elif p.get("kind") == "device" or (p.get("state") == "planned" and p["ref"] not in refs):
            if p.get("kind") == "app":
                base["id"] = "app:" + p["id"].split(":", 1)[1].replace("@", "-at-")
            pieces.append(base)
    present = {p["id"]: p for p in pieces} | {p["id"]: p for p in sketch["pieces"]}
    for w in m["wires"]:
        if w.get("state") != "planned" and not w.get("documented"):
            continue
        a, b = w.get("from_piece"), w.get("to_piece")
        if a not in present or b not in present:
            continue
        core = {k: w[k] for k in ("id", "from", "to", "type", "owner", "state")}
        # Real, but outside software, and touching something that is only
        # planned: it cannot be live in ZENTRALE's eyes yet (plan 6.7).
        if any(present[x].get("state") == "planned" for x in (a, b)) and core["state"] == "live":
            core["state"] = "planned"
        extra_wires.append(core)
    return pieces, extra_wires


def run(changes, scheme, live_map, apply=False) -> dict:
    """Run the drawing: check everything, apply this node's part."""
    node = wires.node_name()
    sk = wires.sketch(node)
    sk = dict(sk, pieces=[kinds.with_links(p) if p["kind"] == "node" else p for p in sk["pieces"]])
    errors, mine = [], []
    for w in changes or []:
        if not isinstance(w, dict) or not isinstance(w.get("id"), str):
            errors.append({"code": "schema", "text": _("a change without a wire id")})
            continue
        core = {k: w.get(k) for k in ("id", "from", "to", "type", "owner", "state")}
        if not _mine(core, node):
            owner = str(core.get("owner") or "").split(":", 1)[-1]
            errors.append({"code": "elsewhere", "wire": core["id"],
                           "text": _("{wire} belongs to {owner} — run Schematix there").format(
                               wire=core["id"], owner=owner)})
            continue
        mine.append(core)
    if errors:
        return {"ok": False, "errors": errors, "diff": [], "generation": None, "rolled_back": False,
                "problems": []}
    try:
        m = schematix_scheme.scheme_map(live_map, scheme) if scheme else live_map
    except store.StoreError:
        m = live_map
    live_sketch = generations.with_wires(sk, changed=[w for w in mine if w["state"] != "planned"])
    pieces, extra = _scheme_items(m, live_sketch, node)
    full = dict(live_sketch, pieces=live_sketch["pieces"] + pieces,
                wires=live_sketch["wires"] + [w for w in extra if w["id"] not in
                                              {x["id"] for x in live_sketch["wires"]}])
    current = {w["id"]: w for w in sk["wires"]}
    _gen, errors = sketch_compiler.compile_sketch(full, current=current)
    if errors:
        return {"ok": False, "errors": errors, "diff": [], "generation": None, "rolled_back": False,
                "problems": []}
    r = generations.run(live_sketch, node, apply=apply)
    return {"ok": r.ok, "errors": r["errors"], "diff": r["diff"], "generation": r["generation"],
            "rolled_back": r["rolled_back"], "problems": r["problems"], "applied": bool(apply and r.ok)}

