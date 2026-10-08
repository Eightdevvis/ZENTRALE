# ui/routen/abgleich.py
#
# Der Abgleich über die Mitte (core/abgleich.py, memory/betrieb/abgleich.md):
# nur der Zustand zum Anschauen — wann zuletzt, Fehler, Hinweise. Abgleichen
# selbst tun der Timer, der Änderungs-Haken und scripts/abgleich.py; eine
# Route, die den Abgleich startet, braucht es (noch) nicht.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md). 2026-10-08.

from flask import Blueprint, jsonify

import abgleich   # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('abgleich', __name__)


@bp.route('/api/abgleich', methods=['GET'])
def api_abgleich():
    """-> {weg, rechner, schluessel_da, letzter_versuch, letzter_erfolg,
    fehler, geholt, gesendet, hinweise: [{am, text}], konflikte_ordner}."""
    return jsonify(abgleich.zustand())
