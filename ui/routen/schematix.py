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
#
# Routes layer (layer 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify, request

import schematix_map     # type: ignore  – in core/, through sys.path.insert
import schematix_pieces  # type: ignore
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
    m, _d = live_map()
    return jsonify(schematix_map.layout(m))


@bp.route('/api/pieces')
def api_pieces():
    node = wires.node_name()
    descriptions, _notes = schematix_map.account_descriptions()
    return jsonify(schematix_pieces.catalog(wires.sketch(node), node, descriptions))


def _palette_body():
    roles = schematix_store.palette()
    return {"roles": roles, "measured": schematix_store.measured(roles),
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
