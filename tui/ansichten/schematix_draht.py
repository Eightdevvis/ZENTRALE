# tui/ansichten/schematix_draht.py
#
# Rewiring by drawing in Schematix (memory/hub/schematix.md, building kit
# step 15) — pure helpers, no curses, no backend:
#
#   fits(a, b)          the socket table (plan 6.7 stage 1): an offer of one
#                       piece that a need of the other takes — same type. The
#                       same rule as core/schematix_run.fits; every surface
#                       draws the red ✕ itself, the gate stays in the core.
#   misfit(a, b)        the short error at the socket ("PDF viewer needs
#                       `files`, Cloud offers `sync`")
#   wire_for(...)       a drawn connection → the wire it stands for: a link
#                       (network, power) is planned in the scheme; everything
#                       else is a change for Run (the gate decides)
#   toggled(w, node)    what `x` in the plugs panel does to a wire
#
# Convenience only — the guarantee is the compiler behind Run.

from .translate import _


def _types(ports):
    return sorted({p.get("type") for p in ports or [] if p.get("type")})


def fits(a, b):
    out = []
    for prov, cons in ((a, b), (b, a)):
        for o in prov.get("offers") or []:
            for n in cons.get("needs") or []:
                if o.get("type") == n.get("type"):
                    out.append((prov, cons, o, n))
    return out


def misfit(a, b):
    """None when something fits, else the short reason."""
    if not a or not b or fits(a, b):
        return None

    def t(p):
        return p.get("title") or p.get("id")
    cons, prov = (a, b) if a.get("needs") and not a.get("offers") else (b, a)
    needs = ", ".join("`%s`" % x for x in _types(cons.get("needs"))) or _("nothing")
    offers = ", ".join("`%s`" % x for x in _types(prov.get("offers"))) or _("nothing")
    return _("{a} needs {needs}, {b} offers {offers}").format(a=t(cons), needs=needs, b=t(prov), offers=offers)


def _short(p):
    return str(p.get("id")).split(":", 1)[-1].split("@", 1)[0]


def _app(p):
    return p.get("name") or _short(p)


def wire_for(a, b, types):
    """The wire a drawn connection a → b stands for (the first fitting
    pair), with its map ends. `types` = the map's socket table {type: {layer,
    scope}}. → (wire, "planned" | "run") or (None, None)."""
    pairs = fits(a, b)
    if not pairs:
        return None, None
    prov, cons, o, n = pairs[0]
    typ = o["type"]
    fam = typ.split(":", 1)[0]
    info = types.get(fam) or {}
    w = {"type": typ, "from": prov["ref"] + "port/" + o["id"], "to": cons["ref"] + "port/" + n["id"],
         "from_piece": prov["id"], "to_piece": cons["id"], "layer": info.get("layer") or "data",
         "from_port": o["id"], "to_port": n["id"]}
    if info.get("scope") == "link":
        owner = prov["id"] if prov.get("kind") != "app" else "app:" + _app(prov)
        return dict(w, id="%s/%s/%s" % (fam, _short(prov), _short(cons)), owner=owner,
                    state="planned"), "planned"
    node = cons.get("node")
    if typ == "sync":
        wid, owner = "sync/%s/%s" % (node, _app(cons)), "node:%s" % node
    elif info.get("scope") == "node":
        wid, owner = "plug/%s/%s/%s" % (node, _app(cons), n["id"]), "node:%s" % node
    else:
        wid, owner = "plug/%s/%s" % (_app(cons), n["id"]), "app:" + _app(cons)
    return dict(w, id=wid, owner=owner, state="live"), "run"


CORE = ("id", "from", "to", "type", "owner", "state")


def core(w):
    return {k: w.get(k) for k in CORE}


def toggled(w, node):
    """`x` on a wire in the plugs panel → (what, wire | None, message):
    "revert" a pending change, "drop" a planned wire, "run" a change for
    Run (live ↔ off), or "no" with the reason."""
    if w.get("pending"):
        return "revert", None, ""
    if w.get("state") == "planned":
        return "drop", None, ""
    if w.get("type") == "same-version":
        return "no", None, _("same version is set with s on the node")
    if w.get("documented"):
        return "no", None, _("a documented link — change it in its thing")
    owner = str(w.get("owner") or "")
    if owner.startswith("node:") and owner != "node:" + node:
        return "no", None, _("{wire} belongs to {owner} — run Schematix there").format(
            wire=w["id"], owner=owner[5:])
    return "run", dict(w, state="off" if w.get("state") == "live" else "live", pending=True), ""
