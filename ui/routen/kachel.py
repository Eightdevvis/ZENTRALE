# ui/routen/kachel.py
#
# Kacheln (core/kacheln.py): eine Front fragt den Inhalt einer Kachel an
# (Verweis app + art + ref, in w×h Zellen) und reicht Aktionen weiter
# („oeffnen" → wohin springen). Immer über den Hub, nie direkt an die App
# (memory/system/hub_bauplan.md „Kacheln"). Doku: api_endpoints.md.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-10.

from flask import Blueprint, jsonify, request

import kacheln       # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('kachel', __name__)


@bp.route('/api/kachel', methods=['POST'])
def api_kachel():
    """Body {app, art, ref, w, h, oben?, stand?} → Zeilen mit Farbrollen."""
    status, antwort = kacheln.holen(request.get_json(silent=True))
    return jsonify(antwort), status


@bp.route('/api/kachel/aktion', methods=['POST'])
def api_kachel_aktion():
    """Body {app, art, ref, aktion} → {"zeige": {ansicht, ziel}}."""
    status, antwort = kacheln.aktion(request.get_json(silent=True))
    return jsonify(antwort), status
