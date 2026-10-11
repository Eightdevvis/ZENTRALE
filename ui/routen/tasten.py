# ui/routen/tasten.py
#
# Tastentabellen der Apps (core/tastentabelle.py, 2026-10-11): welche Tasten
# eine App in welcher Ansicht nimmt, wie sie es in ihrem app.toml unter
# [tasten] sagt. Eine Oberfläche fragt das einmal, wenn sie eine App
# verkabelt, und zeigt danach in ihrer Leiste nur, was in der offenen Ansicht
# geht. Die eingebauten TUI-Programme tragen ihre Tabelle im Code
# (tui/ansichten/tasten.py) — dasselbe Format. Form: openapi.yaml.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify

import apps            # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import tastentabelle   # type: ignore

bp = Blueprint('tasten', __name__)


@bp.route('/api/tasten', methods=['GET'])
def api_tasten():
    """[{app, tasten}] — nur Apps mit gültiger Tabelle im app.toml."""
    return jsonify(tastentabelle.katalog(apps.installiert()))
