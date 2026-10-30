# core/plug_store.py
#
# Where the wires live that have no older home (memory/hub/building_kit_plan.md
# 1.4, build step 11; memory/hub/port_types.md "Plug dialog"). `sync` stays in
# `abgleich_apps`, `calendar-source` in the calendar `quelle`; every other
# plug a consumer app gets in the plug dialog (`model`, `files`, `read:…`,
# `mic` …) is stored here, by the scope of its type:
#
#   instance   the consumer app instance owns it and it syncs "without mercy":
#              <adapter folder>/plugs/<app>.json  (data/adapter/plugs/*.json,
#              in the positive list next to the calendar settings)
#   node       the node owns it and it never syncs (the node frame):
#              <installiert_ordner>/plugs-<node>.json  (next to apps-<node>.json)
#
# Form: {"format": "zentrale-plugs/1", "wires": [<wire>, …]} — wires as in
# contracts/ports/1 ($defs/wire). Read rule (core/formats.py): an unknown
# major is read-only and gives no wires; fields this version does not know
# are kept on a write.
#
# Only core/wires.py writes here (the apply agent's hand; guard:
# tests/test_plug_dialog.py). Foundation (layer 1).

import json
import os

import ai_config
import dateien
import formats

PLUGS_FORMAT = "zentrale-plugs/1"
WHAT = "plug-wires"
_PROJECT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def instance_folder(root=None) -> str:
    if root:
        return os.path.join(str(root), "data", "adapter", "plugs")
    return os.path.join(os.path.expanduser(ai_config.setting("adapter_ordner") or
                                           os.path.join(_PROJECT, "data", "adapter")), "plugs")


def node_file(node, root=None) -> str:
    own = None if root else ai_config.setting("installiert_ordner")
    base = (os.path.abspath(os.path.expanduser(str(own))) if own
            else os.path.join(str(root or _PROJECT), "data", "hub"))
    return os.path.join(base, "plugs-%s.json" % dateien.sicherer_name(node))


def instance_file(app, root=None) -> str:
    return os.path.join(instance_folder(root), dateien.sicherer_name(app) + ".json")


def _raw(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def read(path) -> list:
    """The wires in one file; a newer major → [] (read-only, one note)."""
    d = _raw(path)
    if d is None:
        return []
    try:
        formats.check(d, WHAT)
    except formats.NewerFormat:
        return []
    return [w for w in d.get("wires") or [] if isinstance(w, dict) and isinstance(w.get("id"), str)]


def write(path, wires) -> None:
    """Store exactly `wires` in the file; unknown fields stay. A newer major
    raises formats.NewerFormat (nothing written). No wires and no other
    fields → the file goes."""
    old = _raw(path)
    if old is not None:
        formats.check(old, WHAT)
    new = formats.keep_unknown(old, {"format": PLUGS_FORMAT, "wires": sorted(wires, key=lambda w: w["id"])})
    if not wires and set(new) <= {"format", "wires"}:
        if os.path.exists(path):
            os.remove(path)
        return
    if old == new:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dateien.json_schreiben(path, new)


def instance_wires(root=None) -> list:
    folder = instance_folder(root)
    out = []
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if f.endswith(".json"):
            out += read(os.path.join(folder, f))
    return out


def node_wires(node, root=None) -> list:
    return read(node_file(node, root))
