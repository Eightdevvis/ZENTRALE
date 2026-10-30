# ui/routen/hub_wires.py
#
# The wires of this node over HTTP (memory/hub/building_kit_plan.md 1.4,
# build steps 9 and 9b):
#
#   GET    /api/wires          the projection: pieces and wires of this node
#                              (core/wires.py — no store of its own)
#   PUT    /api/wires/<id>     plug or re-plug one wire
#   DELETE /api/wires/<id>     unplug it (state off: "stays on this device")
#
# PUT and DELETE go through the one gate (core/generations.run): compile →
# diff → switch → apply. A refused change answers 409 with the errors pinned
# to pieces and wires; nothing is written. `?plan=1` only plans: the diff
# without switching. Form: openapi.yaml. (The plan said /hub/wires; /hub/… is
# the side every app answers itself — /hub/gesund, /hub/ereignis — so the
# hub's own routes stay under /api/ like /api/apps.)
#
# Routes layer (layer 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify, request

import generations   # type: ignore  – in core/, durch sys.path.insert auffindbar
import wires         # type: ignore
from i18n import _   # type: ignore

bp = Blueprint('hub_wires', __name__)


@bp.route('/api/wires', methods=['GET'])
def hub_wires():
    s = wires.sketch()
    return jsonify({"node": wires.node_name(), "pieces": s["pieces"], "wires": s["wires"]})


def _answer(r):
    body = {"ok": r.ok, "diff": r["diff"], "errors": r["errors"], "generation": r["generation"],
            "rolled_back": r["rolled_back"], "problems": r["problems"]}
    return jsonify(body), (200 if r.ok else 409)


def _plan_only():
    return request.args.get("plan") in ("1", "true", "yes")


@bp.route('/api/wires/<path:wid>', methods=['PUT'])
def hub_wire_put(wid):
    w = request.get_json(silent=True)
    if not isinstance(w, dict) or w.get("id", wid) != wid:
        return jsonify({"ok": False, "errors": [{"code": "schema", "wire": wid,
                                                 "text": _("the body must be the wire with this id")}]}), 400
    w = dict(w, id=wid)
    s = generations.with_wires(wires.sketch(), changed=[w])
    return _answer(generations.run(s, apply=not _plan_only()))


@bp.route('/api/wires/<path:wid>', methods=['DELETE'])
def hub_wire_delete(wid):
    s = wires.sketch()
    old = next((w for w in s["wires"] if w["id"] == wid), None)
    if old is None:
        return jsonify({"ok": False, "errors": [{"code": "unknown-wire", "wire": wid,
                                                 "text": _("there is no such wire")}]}), 404
    s = generations.with_wires(s, changed=[dict(old, state="off")])
    return _answer(generations.run(s, apply=not _plan_only()))
