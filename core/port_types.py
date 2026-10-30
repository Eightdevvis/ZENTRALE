# core/port_types.py
#
# The type registry of the building kit (memory/hub/building_kit_plan.md 1.3
# and 6.7, build step 9; reasoning in memory/hub/port_types.md). The registry
# and every item schema live once in contracts/ports/1/ (JSON Schema
# 2020-12), read by the core here and by the phone's tests — no copies.
#
#   types()            name → registry entry (version, layer, scope, …)
#   check(item, kind)  item check against the schema → list of messages
#   need(x) / offer(x) a port in short ("sync@^1") or long form → a dict with
#                      every default filled in from the registry
#   satisfies(v, r)    SemVer: does version v fall in range r (^1, ~1.2, 1.2.3, *)
#   supported()        the type versions this code speaks (for the node description)
#
# Foundation (layer 1): stdlib + jsonschema, no other ZENTRALE module.

import functools
import json
import os
import re

_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FOLDER = os.path.join(_ROOT, "contracts", "ports", "1")
SCHEMA = os.path.join(FOLDER, "ports.schema.json")
REGISTRY = os.path.join(FOLDER, "types.json")
SCHEMA_ID = "urn:zentrale:ports:1"
UNBOUNDED = "UNBOUNDED"
APPLY_AGENT = 1           # version of the apply agent this code carries (core/generations.py)

_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_RANGE = re.compile(r"^(\*|([\^~]?)(\d+)(?:\.(\d+))?(?:\.(\d+))?)$")


@functools.lru_cache(maxsize=1)
def schema() -> dict:
    with open(SCHEMA, encoding="utf-8") as f:
        return json.load(f)


@functools.lru_cache(maxsize=1)
def _registry() -> dict:
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def types() -> dict:
    return _registry()["types"]


def family(port_type: str) -> str:
    """event:presence → event."""
    return str(port_type).split(":", 1)[0]


def entry(port_type: str):
    """Registry entry of a port type (or None when unknown). A qualifier is
    only allowed on families that take one."""
    fam, _, qual = str(port_type).partition(":")
    e = types().get(fam)
    if e is None:
        return None
    if bool(qual) != (e.get("qualifier", "none") == "name"):
        return None
    return e


def supported() -> dict:
    """The type versions this code speaks → the node description's `types`."""
    return {n: e["version"] for n, e in sorted(types().items())}


# ── Item check (stage 2) ─────────────────────────────────────────────────

@functools.lru_cache(maxsize=None)
def _validator(kind):
    import jsonschema
    s = dict(schema())
    s.pop("$id", None)
    s["$ref"] = "#/$defs/" + kind
    return jsonschema.Draft202012Validator(s)


def check(item, kind) -> list:
    """Item check of one piece/wire/manifestPorts/registry/sketch/generation
    → messages (empty = valid), each with the JSON path of the fault."""
    out = []
    for e in sorted(_validator(kind).iter_errors(item), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path)
        out.append(f"{where}: {e.message}" if where else e.message)
    return out


# ── SemVer ────────────────────────────────────────────────────────────────

def parse_version(v):
    m = _VERSION.match(str(v))
    return tuple(int(x) for x in m.groups()) if m else None


def satisfies(version, rng) -> bool:
    """npm-style subset: ^1 / ^1.2 / ^1.2.3 (same major; for major 0 the same
    minor), ~1.2 (same minor), 1.2.3 exact, 1 / 1.2 (prefix), * (any)."""
    v = parse_version(version)
    m = _RANGE.match(str(rng))
    if v is None or m is None:
        return False
    if m.group(1) == "*":
        return True
    op = m.group(2)
    parts = [int(x) for x in m.group(3, 4, 5) if x is not None]
    low = tuple(parts + [0] * (3 - len(parts)))
    if v < low:
        return False
    if op == "^":
        if low[0] > 0 or len(parts) == 1:
            return v[0] == low[0]
        if low[1] > 0 or len(parts) == 2:
            return v[:2] == low[:2]
        return v == low
    if op == "~":
        return v[:2] == low[:2] if len(parts) >= 2 else v[0] == low[0]
    return v[:len(parts)] == tuple(parts)


def default_range(port_type) -> str:
    e = entry(port_type)
    return "^" + str(parse_version(e["version"])[0]) if e else "*"


# ── Ports in short or long form ──────────────────────────────────────────

def need(x) -> dict:
    """A need with every default: {id, type, range, occurrences, access?, legacy?}."""
    if isinstance(x, str):
        t, _, r = x.partition("@")
        x = {"type": t, **({"range": r} if r else {})}
    d = dict(x)
    e = entry(d["type"]) or {}
    d.setdefault("id", d["type"].replace(":", "."))
    d.setdefault("range", default_range(d["type"]))
    d.setdefault("occurrences", list(e.get("occurrences") or [0, 1]))
    return d


def offer(x) -> dict:
    """An offer with every default: {id, type, version, legacy?}."""
    if isinstance(x, str):
        t, _, v = x.partition("@")
        x = {"type": t, **({"version": v} if v else {})}
    d = dict(x)
    e = entry(d["type"]) or {}
    d.setdefault("id", d["type"].replace(":", "."))
    d.setdefault("version", e.get("version", "1.0.0"))
    return d


def at_most(occ, n) -> bool:
    return occ[1] == UNBOUNDED or n <= occ[1]
