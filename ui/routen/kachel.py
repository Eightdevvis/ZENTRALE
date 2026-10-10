# ui/routen/kachel.py
#
# Kacheln (core/kacheln.py): eine Oberfläche fragt den Katalog (was jede
# App liefern kann), den Inhalt einer Kachel (Verweis = Adresse
# zentrale://<app>/<art>?…, in w×h Zellen) und reicht Aktionen weiter
# („oeffnen" → eine Adresse). Immer über den Hub, nie direkt an die App
# (memory/system/hub_bauplan.md „Kacheln"). Doku: api_endpoints.md.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-10.

from flask import Blueprint, jsonify, request

import kacheln       # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('kachel', __name__)


@bp.route('/api/kacheln', methods=['GET'])
def api_kacheln():
    """Katalog: [{app, art, titel, min, bevorzugt, max?, ttl, felder,
    aktionen, formen}] — nur Apps mit `<app>:lesen` (2026-10-10)."""
    return jsonify(kacheln.katalog())


@bp.route('/api/kachel', methods=['POST'])
def api_kachel():
    """Body {adresse, w, h, oben?, stand?} → Zeilen mit Farbrollen."""
    status, antwort = kacheln.holen(request.get_json(silent=True))
    return jsonify(antwort), status


@bp.route('/api/kachel/aktion', methods=['POST'])
def api_kachel_aktion():
    """Body {adresse, aktion} → {"zeige": {"adresse"}}."""
    status, antwort = kacheln.aktion(request.get_json(silent=True))
    return jsonify(antwort), status
