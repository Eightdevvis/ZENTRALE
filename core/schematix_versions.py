# core/schematix_versions.py
#
# The versions panel of Schematix (memory/hub/building_kit_plan.md 6.2,
# build step 13; app: memory/hub/schematix.md). What a node runs and speaks,
# for its description in the cloud (only this node writes its own) and for
# the panel that folds open on every node piece:
#
#   own(root)              this node: ZENTRALE version, store app versions,
#                          contract majors, auto_update, "same version",
#                          whether it syncs over the cloud
#   of_description(d)      another node's section, read rule of step 5 (an
#                          unknown major gives None and one note)
#   cannot_yet(d)          what a node cannot do yet, read from what its
#                          description lacks ("no Run from the map: needs …")
#   same_version()/set_same_version(nodes)
#                          the node setting "same version": the nodes this
#                          one keeps the same ZENTRALE version as (Sasha
#                          30.10., plan 2.2 rule 5) — set from Schematix
#
# Foundation (layer 1).

import os

import ai_config
import apps
import formats
import knoten
import port_types
from i18n import _

VERSIONS_FORMAT = "zentrale-node-versions/1"     # the `versions` field of a node description
SAME_SETTING = "same_version"                   # node setting (data/ai_config.json, never synced)
AUTO_SETTING = "auto_update"                    # zentrale_cli/aktualisieren.py owns its writing
_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def contracts(root=None) -> dict:
    """{contract: [majors]} this code speaks: the port types (registry
    major), the cloud API, and every versioned file format it reads and
    writes (core/formats.py). From the code, not from files on disk — an
    installed package does not carry every vector folder."""
    out = {"ports": [int(port_types.SCHEMA_ID.rsplit(":", 1)[1])], "cloud-api": [1]}
    for key, (major, _label) in formats.FORMATS.items():
        out[key] = [major]
    return dict(sorted(out.items()))


def _app_versions() -> dict:
    out = {}
    for m in apps.installiert():
        name = str(m.get("_slug") or m.get("name") or "")
        v = m.get("version") or m.get("fassung")
        if name and v:
            out[name] = str(v)
    return dict(sorted(out.items()))


def same_version() -> list:
    v = ai_config.setting(SAME_SETTING)
    if isinstance(v, str):
        v = [v] if v else []
    return sorted({str(x) for x in v or [] if str(x)})


def set_same_version(nodes) -> list:
    """Store the nodes this node keeps the same version as (empty = none)."""
    clean = sorted({str(n) for n in nodes or [] if str(n)})
    ai_config.set_override(SAME_SETTING, clean, persist=True)
    return clean


def own(root=None, cloud=None) -> dict:
    """This node's section for its description."""
    if cloud is None:
        import abgleich
        cloud = abgleich.cloud_an()
    return {"format": VERSIONS_FORMAT, "zentrale": knoten.fassung(root or _ROOT),
            "apps": _app_versions(), "contracts": contracts(root),
            "auto_update": ai_config.setting(AUTO_SETTING) is not False,
            "same_version": same_version(), "cloud": bool(cloud)}


def of_description(d):
    """The `versions` section of another node's description, or None (old
    node without it, malformed, or a newer major: read-only, one note)."""
    sec = d.get("versions") if isinstance(d, dict) else None
    if not isinstance(sec, dict) or not str(sec.get("format", "")).startswith("zentrale-node-versions/"):
        return None
    try:
        formats.check(sec, "node-versions")
    except formats.NewerFormat:
        return None
    return sec


def cannot_yet(d) -> list:
    """What a node cannot do yet, from what its description lacks. Each line
    names the feature and what it needs (the panel shows them as they are)."""
    out = []
    if not isinstance(d, dict):
        return out
    if not d.get("apply_agent"):
        out.append(_("no Run from the map: needs the apply agent (building kit step 9b)"))
    if not isinstance(d.get("wires"), dict):
        out.append(_("its wiring is unknown here: needs node wires in its description (step 11)"))
    if not isinstance(d.get("versions"), dict):
        out.append(_("no versions panel: needs Schematix (step 13)"))
    have = d.get("types") if isinstance(d.get("types"), dict) else {}
    mine = port_types.supported()
    missing = sorted(t for t in mine if t not in have)
    if have and missing:
        out.append(_("does not speak {types} yet: needs a newer ZENTRALE").format(types=", ".join(missing)))
    return out
