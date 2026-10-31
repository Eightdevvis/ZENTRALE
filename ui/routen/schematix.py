# ui/routen/schematix.py
#
# Schematix, the wiring map (memory/hub/schematix.md; plan
# memory/hub/building_kit_plan.md 6 and 8, steps 13–15). Same naming as
# /api/wires: the hub's own routes stay under /api/, /hub/… is the side
# every app answers itself.
#
#   GET  /api/schematix/map            the map of the account, laid out as a
#                                      cross-section (core/schematix_map.py)
#   GET  /api/pieces                   the `+` picker: everything placeable
#                                      (core/schematix_pieces.py)
#   GET  /api/schematix/palette        colour roles + measured contrast
#   PUT  /api/schematix/palette/<role> one role ({"value": "#rrggbb" | null})
#   GET  /api/schematix/schemes        the schemes (step 14)
#   PUT  /api/schematix/schemes/<name> the board → the .canvas file (core/schematix_scheme.py)
#   PUT/DELETE /api/schematix/things/<id>  document a thing / remove it
#   POST /api/schematix/run            the drawing through the gate (step 15):
#                                      check → diff (→ switch with "apply")
#   PUT  /api/schematix/same-version   this node keeps the same version as …
#
# Routes layer (layer 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify, request

import schematix_map     # type: ignore  – in core/, through sys.path.insert
import schematix_pieces  # type: ignore
import schematix_run     # type: ignore
import schematix_scheme  # type: ignore
import schematix_store   # type: ignore
import schematix_versions  # type: ignore
import wires             # type: ignore
import formats           # type: ignore

bp = Blueprint('schematix', __name__)


def _error(e):
    return jsonify({"error": str(e)}), getattr(e, "code", 400)


def live_map():
    """The map from the truths of right now (this node + the cloud)."""
    node = wires.node_name()
    descriptions, notes = schematix_map.account_descriptions()
    m = schematix_map.build(wires.sketch(node), node, schematix_versions.own(), descriptions, notes)
    return m, descriptions


@bp.route('/api/schematix/map')
def api_schematix_map():
    """The map with a scheme (?scheme=<name>, default "home", created from
    heimnetz.md the first time); ?scheme= (empty) = the live map alone."""
    m, _d = live_map()
    name = request.args.get("scheme", schematix_scheme.STARTER)
    if not name:
        return jsonify(schematix_map.layout(m))
    try:
        return jsonify(schematix_scheme.scheme_map(m, name))
    except schematix_store.StoreError as e:
        return _error(e)


@bp.route('/api/schematix/schemes')
def api_schematix_schemes():
    return jsonify({"schemes": schematix_scheme.names()})


@bp.route('/api/schematix/schemes/<name>', methods=['PUT'])
def api_schematix_scheme_save(name):
    """The board as the TUI holds it: places, planned pieces and wires, `stand`."""
    body = request.get_json(silent=True) or {}
    m, _d = live_map()
    try:
        return jsonify(schematix_scheme.save(name, body, m))
    except schematix_scheme.SchemeConflict as e:
        return jsonify({"error": str(e), "stand": e.stand}), 409
    except schematix_store.StoreError as e:
        return _error(e)


@bp.route('/api/schematix/things/<tid>', methods=['PUT'])
def api_schematix_thing_put(tid):
    """Document a thing (a planned device becomes real: same reference)."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(schematix_store.write_thing(dict(body, id=tid)))
    except schematix_store.StoreError as e:
        return _error(e)
    except formats.NewerFormat as e:
        return jsonify({"error": str(e)}), 409


@bp.route('/api/schematix/things/<tid>', methods=['DELETE'])
def api_schematix_thing_delete(tid):
    try:
        schematix_store.delete_thing(tid)
    except schematix_store.StoreError as e:
        return _error(e)
    return jsonify({"ok": True})


@bp.route('/api/pieces')
def api_pieces():
    node = wires.node_name()
    descriptions, _notes = schematix_map.account_descriptions()
    return jsonify(schematix_pieces.catalog(wires.sketch(node), node, descriptions))


def _palette_body():
    roles = schematix_store.palette()
    return {"roles": roles, "measured": schematix_store.measured(roles),
            "against": {k: schematix_store.against(k, roles) for k in roles if k != "board"},
            "floored": sorted(k for k in roles if k != "board" and schematix_store.floored(k)),
            "defaults": schematix_store.default_palette(), "minimum": 4.5}


@bp.route('/api/schematix/palette')
def api_schematix_palette():
    return jsonify(_palette_body())


@bp.route('/api/schematix/palette/<role>', methods=['PUT'])
def api_schematix_palette_role(role):
    body = request.get_json(silent=True) or {}
    try:
        schematix_store.set_role(role, body.get("value"))
    except schematix_store.StoreError as e:
        return _error(e)
    except formats.NewerFormat as e:
        return jsonify({"error": str(e)}), 409
    return jsonify(_palette_body())


@bp.route('/api/schematix/run', methods=['POST'])
def api_schematix_run():
    """Body: {"changes": [wires], "scheme": "home", "apply": false}. Without
    apply only the diff; refused → 409 with errors pinned to pieces/wires."""
    body = request.get_json(silent=True) or {}
    m, _d = live_map()
    r = schematix_run.run(body.get("changes") or [], body.get("scheme"), m, apply=bool(body.get("apply")))
    return jsonify(r), (200 if r["ok"] else 409)


@bp.route('/api/schematix/same-version', methods=['PUT'])
def api_schematix_same_version():
    """Body: {"nodes": [names]} — the nodes THIS node keeps the same ZENTRALE
    version as (only this node writes its own setting; it goes out with its
    description)."""
    body = request.get_json(silent=True) or {}
    nodes = body.get("nodes")
    if not isinstance(nodes, list) or not all(isinstance(n, str) for n in nodes):
        return jsonify({"error": "nodes: a list of node names"}), 400
    return jsonify({"same_version": schematix_versions.set_same_version(nodes)})
