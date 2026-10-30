# core/sketch_compiler.py
#
# The hard gate of Run (memory/hub/building_kit_plan.md 6.7, build step 9b;
# rules and reasoning: memory/hub/port_types.md). Sasha: "niemand darf je
# einen kaputten Sketch kompilieren und sein Netzwerk verbuggen."
#
#   compile_sketch(sketch, current=None) → (generation, []) or (None, errors)
#
# Stage 2, item check: the sketch and each piece and wire against
# contracts/ports/1/ports.schema.json. Any fault → stop here.
# Stage 3, graph rules no schema can express:
#   - every port type is registered; a wire joins an offer and a need of its type
#   - the offer's version is inside the need's range
#   - every non-planned need is fulfilled within its occurrences — a socket
#     holds at most `max` plugs, a required one (min ≥ 1) needs live wires;
#     node-scoped types (sync, hardware) are counted per node
#   - no cycle over types whose registry entry forbids cycles
#   - one owner per resource (`owns`); a wire's owner is the one its scope says
#   - nothing live hangs on a planned piece
#   - the node a wire runs on speaks the needed type version (node `types`),
#     unless the wire is planned
#   - unmanaged nodes (no apply agent) are read-only: their wires stay as
#     they are in `current`
# Any error → no generation. Each error names the piece / wire / port it is
# pinned to, so the map can show it there. Same input → same output (the
# vectors in contracts/ports/1/sketch_vectors.json pin it).
#
# Foundation (layer 1): imports only port_types and i18n.

import hashlib
import json

import port_types
from i18n import _

GENERATION = "zentrale-generation/1"

# error code → English msgid (German in core/locale/de/…/zentrale.po)
TEXTS = {
    "schema": "{where} does not fit its schema: {detail}",
    "duplicate-id": "the id {id} is used twice",
    "unknown-type": "{where}: the port type {type} is not known",
    "unknown-piece": "{where}: there is no piece {ref}",
    "unknown-port": "{where}: {ref} has no socket {port} that {direction}",
    "type-mismatch": "{wire}: {need} needs {need_type}, {offer} offers {offer_type}",
    "version-mismatch": "{wire}: {need} needs {type} {range}, {offer} offers {version}",
    "unmet-requirement": "{where} needs {type} on its socket {port} — nothing is plugged in",
    "too-many": "{piece}: the socket {port} takes at most {max}, {count} are plugged in",
    "cycle": "a loop over {type}: {path}",
    "double-owner": "{resource} has more than one owner: {owners}",
    "wrong-owner": "{wire}: owned by {owner}, but {type} wires belong to {expected}",
    "live-on-planned": "{where} is live but {planned} is only planned (not yet)",
    "wire-broken": "{wire} is broken — its provider is gone or speaks a newer version",
    "type-too-new": "{wire} needs {type} {range}, but {node} speaks {have} — not yet: needs an update on {node}",
    "no-version": "no version of it",
    "node-unmanaged": "{wire}: {node} has no apply agent — it can only be read, not changed",
}


def _err(code, **kw):
    pinned = {k: kw[k] for k in ("piece", "wire", "port") if kw.get(k)}
    values = {k: ("—" if v is None else v) for k, v in kw.items()}
    return dict(pinned, code=code, text=_(TEXTS[code]).format(**values))


def canonical(obj) -> bytes:
    """JCS (RFC 8785) for the documents here: sorted keys, no spaces, UTF-8
    (they hold no floats)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def generation_hash(gen) -> str:
    body = {k: gen[k] for k in ("format", "pieces", "wires")}
    return "sha256:" + hashlib.sha256(canonical(body)).hexdigest()


# ── Stage 2 ────────────────────────────────────────────────────────────────

def item_check(sketch) -> list:
    errors = [_err("schema", where="sketch", detail=m) for m in port_types.check(sketch, "sketch")]
    if errors:
        return errors
    for p in sketch["pieces"]:
        pid = p.get("id") if isinstance(p, dict) and isinstance(p.get("id"), str) else "?"
        errors += [_err("schema", piece=pid, where=pid, detail=m) for m in port_types.check(p, "piece")]
    for w in sketch["wires"]:
        wid = w.get("id") if isinstance(w, dict) and isinstance(w.get("id"), str) else "?"
        errors += [_err("schema", wire=wid, where=wid, detail=m) for m in port_types.check(w, "wire")]
    return errors


# ── Stage 3 ────────────────────────────────────────────────────────────────

def _normal_piece(p) -> dict:
    d = dict(p)
    d.setdefault("state", "live")
    d["needs"] = [port_types.need(x) for x in p.get("needs") or []]
    d["offers"] = [port_types.offer(x) for x in p.get("offers") or []]
    return d


def _planned(p) -> bool:
    return p is not None and p.get("state") == "planned"


def _sockets(pieces, errors):
    """(ref, port id) → (piece, "need"|"offer", port)."""
    out = {}
    for p in pieces:
        for direction, key in (("need", "needs"), ("offer", "offers")):
            for port in p[key]:
                if port_types.entry(port["type"]) is None:
                    errors.append(_err("unknown-type", piece=p["id"], port=port["id"],
                                       where=f"{p['id']} {port['id']}", type=port["type"]))
                k = (p["ref"], port["id"])
                if k in out:
                    errors.append(_err("duplicate-id", piece=p["id"], port=port["id"], id=port["id"]))
                out[k] = (p, direction, port)
    return out


def _split(address):
    ref, sep, pid = str(address).rpartition("port/")
    return (ref, pid) if sep else (address, "")


def _check_wire(w, sockets, by_id, errors, current):
    """→ (provider piece, consumer piece, need) or None when the wire cannot be placed."""
    wid = w["id"]
    entry = port_types.entry(w["type"])
    if entry is None:
        errors.append(_err("unknown-type", wire=wid, where=wid, type=w["type"]))
        return None
    ends = []
    for key, direction, verb in (("from", "offer", "offers"), ("to", "need", "needs")):
        ref, pid = _split(w[key])
        s = sockets.get((ref, pid))
        if s is None or s[1] != direction:
            errors.append(_err("unknown-port", wire=wid, where=wid, ref=ref, port=pid,
                               direction=_(verb)))
            return None
        ends.append(s)
    (prov, _d1, offer), (cons, _d2, need) = ends
    if not (offer["type"] == need["type"] == w["type"]):
        errors.append(_err("type-mismatch", wire=wid, need=cons["id"], need_type=need["type"],
                           offer=prov["id"], offer_type=offer["type"]))
        return None
    if not port_types.satisfies(offer["version"], need["range"]):
        errors.append(_err("version-mismatch", wire=wid, need=cons["id"], type=w["type"],
                           range=need["range"], offer=prov["id"], version=offer["version"]))
    planned = w["state"] == "planned"
    owner = by_id.get(w["owner"])
    if owner is None:
        errors.append(_err("unknown-piece", wire=wid, where=wid, ref=w["owner"]))
        return None
    scope = entry["scope"]
    if scope == "node":
        expected = cons.get("on") or []
        ok = w["owner"] in expected
    elif scope == "instance":
        expected = [cons["id"]]
        ok = w["owner"] == cons["id"]
    else:
        expected = [prov["id"], cons["id"]]
        ok = True
    if not ok:
        errors.append(_err("wrong-owner", wire=wid, owner=w["owner"], type=w["type"],
                           expected=", ".join(expected) or "—"))
    if not planned:
        for p in (prov, cons, owner):
            if _planned(p):
                errors.append(_err("live-on-planned", wire=wid, piece=p["id"], where=wid, planned=p["id"]))
                break
        if w["state"] == "broken":
            errors.append(_err("wire-broken", wire=wid))
    # The nodes the wire runs on.
    if scope == "node":
        targets = [w["owner"]]
    elif scope == "instance":
        targets = list(cons.get("on") or [])
    else:
        targets = [p["id"] for p in (prov, cons) if p["kind"] == "node"]
    if owner["kind"] == "node" and owner.get("managed") is False:
        old = (current or {}).get(wid)
        if old is None or any(old.get(k) != w.get(k) for k in ("from", "to", "type", "owner", "state")):
            errors.append(_err("node-unmanaged", wire=wid, node=owner["id"]))
    if not planned:
        for nid in targets:
            node = by_id.get(nid)
            if node is None or node["kind"] != "node" or node.get("managed") is False:
                continue
            have = (node.get("types") or {}).get(port_types.family(w["type"]))
            if have is None or not port_types.satisfies(have, need["range"]):
                errors.append(_err("type-too-new", wire=wid, piece=nid, type=w["type"],
                                   range=need["range"], node=nid, have=have or _(TEXTS["no-version"])))
    return prov, cons, need


def _requirements(pieces, wires_at, errors):
    for p in pieces:
        if _planned(p):
            continue
        for need in p["needs"]:
            entry = port_types.entry(need["type"])
            if entry is None:
                continue
            groups = {}
            for w in wires_at.get((p["ref"], need["id"]), []):
                key = w["owner"] if entry["scope"] == "node" else None
                groups.setdefault(key, []).append(w)
            if entry["scope"] == "node":
                for nid in p.get("on") or []:
                    groups.setdefault(nid, [])
            elif not groups:
                groups[None] = []
            lo, hi = need["occurrences"]
            for key, ws in sorted(groups.items(), key=lambda kv: str(kv[0])):
                where = f"{p['id']} on {key}" if key else p["id"]
                live = [w for w in ws if w["state"] == "live"]
                if not port_types.at_most(need["occurrences"], len(ws)):
                    errors.append(_err("too-many", piece=p["id"], port=need["id"], max=hi,
                                       count=len(ws)))
                elif len(live) < lo and not need.get("legacy"):
                    errors.append(_err("unmet-requirement", piece=p["id"], port=need["id"],
                                       where=where, type=f"{need['type']}@{need['range']}"))


def _owners(pieces, errors):
    owners = {}
    for p in pieces:
        for r in p.get("owns") or []:
            owners.setdefault(r, []).append(p["id"])
    for r, ids in sorted(owners.items()):
        if len(ids) > 1:
            for pid in ids:
                errors.append(_err("double-owner", piece=pid, resource=r, owners=", ".join(ids)))


def _cycles(edges, errors):
    """edges: consumer id → [(provider id, wire)] over cycle-forbidding wires.
    A wire lies on a loop when its consumer can be reached again from its
    provider; every such wire is named (the map marks the whole loop)."""
    def reaches(start, goal):
        seen, todo = {start}, [start]
        while todo:
            n = todo.pop()
            if n == goal:
                return True
            for nxt, _w in edges.get(n, []):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return False

    loop = [(w, cons) for cons in sorted(edges) for prov, w in edges[cons] if reaches(prov, cons)]
    path = " → ".join(sorted(w["id"] for w, _c in loop))
    for w, _c in loop:
        errors.append(_err("cycle", wire=w["id"], type=w["type"], path=path))


def compile_sketch(sketch, current=None):
    """→ (generation, []) or (None, [errors]). `current`: the wires as they
    are now ({id: wire}) — what unmanaged nodes keep."""
    errors = item_check(sketch)
    if errors:
        return None, errors
    pieces = [_normal_piece(p) for p in sketch["pieces"]]
    wires = [dict(w) for w in sketch["wires"]]
    by_id, refs = {}, set()
    for p in pieces:
        if p["id"] in by_id or p["ref"] in refs:
            errors.append(_err("duplicate-id", piece=p["id"], id=p["id"]))
        by_id[p["id"]] = p
        refs.add(p["ref"])
    seen = set()
    for w in wires:
        if w["id"] in seen:
            errors.append(_err("duplicate-id", wire=w["id"], id=w["id"]))
        seen.add(w["id"])
    for p in pieces:
        for nid in p.get("on") or []:
            node = by_id.get(nid)
            if node is None or node["kind"] != "node":
                errors.append(_err("unknown-piece", piece=p["id"], where=p["id"], ref=nid))
            elif _planned(node) and not _planned(p):
                errors.append(_err("live-on-planned", piece=p["id"], where=p["id"], planned=nid))
    sockets = _sockets(pieces, errors)
    wires_at, edges = {}, {}
    for w in wires:
        placed = _check_wire(w, sockets, by_id, errors, current)
        if placed is None or w["state"] == "planned":
            continue
        prov, cons, need = placed
        wires_at.setdefault((cons["ref"], need["id"]), []).append(w)
        entry = port_types.entry(w["type"])
        if w["state"] == "live" and entry["cycles"] == "forbidden":
            edges.setdefault(cons["id"], []).append((prov["id"], w))
    _requirements(pieces, wires_at, errors)
    _owners(pieces, errors)
    _cycles(edges, errors)
    if errors:
        return None, _unique(errors)
    gen = {"format": GENERATION,
           "pieces": sorted(pieces, key=lambda p: p["id"]),
           "wires": sorted(wires, key=lambda w: w["id"])}
    gen["hash"] = generation_hash(gen)
    return gen, []


def _unique(errors):
    out, seen = [], set()
    for e in errors:
        k = canonical(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out
