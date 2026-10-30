# core/plugs.py
#
# The plug dialog (memory/hub/building_kit_plan.md 1.5 and 5.1 step 4, build
# step 11; memory/hub/port_types.md "Plug dialog") — the rights dialog the
# store was missing. When an app is installed, it lists the sockets the app
# needs, proposes the providers this node has, and the person confirms per
# socket. Every front (CLI `zentrale apps`, the store routes the TUI uses)
# asks through here; the rules live once:
#
#   sockets(app)            the needs to ask: [{need, type, min, max, scope,
#                           title, providers: [{port, piece, title}], wire}]
#                           (old rights words are legacy: granted by the rights
#                           check today, not asked; the `data` → `sync` socket
#                           is asked by the new-app question of the sync choice)
#   confirm(app, choices)   {need id: provider port | None} → ONE run through
#                           the gate (core/generations.run): compile → diff →
#                           switch → apply. None = refused: the wire is kept
#                           `off` ("declared, unplugged"). Errors come back
#                           pinned to their socket (`need`).
#   unmet(app)              required sockets (min ≥ 1) without a live wire in
#                           effect — while there are any, the install does not
#                           count (core/app_installation.plug withdraws it)
#
# Foundation (layer 1): wires, generations, port_types, i18n.

import generations
import port_types
import wires
from i18n import _

ASKED_ELSEWHERE = ("sync",)     # the data socket: abgleich_apps' new-app question


def _app_piece(sketch, app):
    pid = "app:" + app
    return next((p for p in sketch["pieces"] if p["id"] == pid), None)


def known(app, node=None) -> bool:
    """Is `app` a piece on this node (installed, built in, or with data)?"""
    return _app_piece(wires.sketch(node, hardware=False), app) is not None


def _wire_id(app, need, scope, node):
    return f"plug/{node}/{app}/{need}" if scope == "node" else f"plug/{app}/{need}"


def _providers(sketch, piece, need):
    """Offers of the pieces here that fit the need: same type, version in
    range; node-scoped types only from the node the app is on."""
    scope = (port_types.entry(need["type"]) or {}).get("scope")
    out = []
    for p in sketch["pieces"]:
        if p["id"] == piece["id"] or p.get("state") == "planned":
            continue
        if scope == "node" and p["id"] not in (piece.get("on") or []):
            continue
        for o in p.get("offers") or []:
            o = port_types.offer(o)
            if o["type"] == need["type"] and port_types.satisfies(o["version"], need["range"]):
                out.append({"port": wires.port(p["ref"], o["id"]), "piece": p["id"],
                            "title": f"{p.get('title') or p['id']} {o['id']}"})
    return out


def sockets(app, node=None, sketch=None) -> list:
    """The sockets of `app` the dialog asks about, with the providers this
    node offers and the wire already plugged in (if any)."""
    node = node or wires.node_name()
    sketch = sketch or wires.sketch(node)
    piece = _app_piece(sketch, app)
    if piece is None:
        return []
    have = {w["to"]: w for w in sketch["wires"]}
    out = []
    for need in piece["needs"]:
        if need.get("legacy") or port_types.family(need["type"]) in ASKED_ELSEWHERE:
            continue
        scope = (port_types.entry(need["type"]) or {}).get("scope")
        lo, hi = need["occurrences"]
        out.append({"need": need["id"], "type": need["type"], "range": need["range"],
                    "min": lo, "max": hi, "scope": scope,
                    "title": f"{piece.get('title') or app} {need['id']}",
                    "providers": _providers(sketch, piece, need),
                    "wire": have.get(wires.port(piece["ref"], need["id"]))})
    return out


def wire_for(app, socket, provider, node=None) -> dict:
    """The wire one answer stands for. provider None = refused: `off`,
    declared to the first provider (or the one already plugged in)."""
    node = node or wires.node_name()
    old = socket.get("wire")
    src = provider or (old or {}).get("from") or (socket["providers"][0]["port"] if socket["providers"] else None)
    if src is None:
        return None
    scope = socket["scope"]
    return {"id": (old or {}).get("id") or _wire_id(app, socket["need"], scope, node),
            "from": src, "to": wires.port(wires.app_ref(app), socket["need"]),
            "type": socket["type"], "owner": wires.node_id(node) if scope == "node" else "app:" + app,
            "state": "live" if provider else "off"}


def confirm(app, choices: dict, node=None, **run_kw) -> dict:
    """Plug in what the person chose ({need id: provider port | None}) in
    one run through the gate. A socket not named keeps what it has. →
    {ok, errors (each with `need` when it is pinned to a socket), diff,
    generation, rolled_back, problems, unmet}."""
    node = node or wires.node_name()
    sk = wires.sketch(node)
    socks = {s["need"]: s for s in sockets(app, node, sk)}
    changed, by_wire, errors = [], {}, []
    for need, provider in choices.items():
        s = socks.get(need)
        if s is None:
            errors.append({"code": "unknown-port", "need": need, "port": need, "piece": "app:" + app,
                           "text": _("{app} has no socket {need}").format(app=app, need=need)})
            continue
        if provider is not None and provider not in [p["port"] for p in s["providers"]]:
            errors.append({"code": "unknown-port", "need": need, "port": need, "piece": "app:" + app,
                           "text": _("{provider} does not fit {socket}").format(
                               provider=provider, socket=s["title"])})
            continue
        w = wire_for(app, s, provider, node)
        if w is not None:
            changed.append(w)
            by_wire[w["id"]] = need
    if errors:
        return {"ok": False, "errors": errors, "diff": [], "generation": None, "rolled_back": False,
                "problems": [], "unmet": unmet(app, node)}
    r = generations.run(generations.with_wires(sk, changed), node, **run_kw)
    out = dict(r)
    out["errors"] = [_pin(e, app, by_wire) for e in r["errors"]]
    out["unmet"] = unmet(app, node)
    return out


def _pin(e, app, by_wire):
    need = by_wire.get(e.get("wire"))
    if need is None and e.get("piece") == "app:" + app:
        need = e.get("port")
    return dict(e, need=need) if need else dict(e)


def unmet(app, node=None) -> list:
    """Required sockets (min ≥ 1, not legacy) of `app` without a live wire in effect."""
    node = node or wires.node_name()
    sk = wires.sketch(node)
    piece = _app_piece(sk, app)
    if piece is None:
        return []
    live = {w["to"] for w in sk["wires"] if w["state"] == "live"}
    return [n["id"] for n in piece["needs"]
            if n["occurrences"][0] >= 1 and not n.get("legacy")
            and wires.port(piece["ref"], n["id"]) not in live]
