# ui/routen/skills.py
#
# Skills der KI (core/skills.py): die Liste zum Anschauen. Nur lesen —
# angelegt und geändert wird über die gegateten Werkzeuge im Chat oder von
# Sasha direkt in der Datei (data/gedaechtnis/skills/).
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-07, Phase 4 des Claude-Web-Plans.

from flask import Blueprint, jsonify

import skills        # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('skills', __name__)


@bp.route('/api/skills')
def api_skills():
    """Alle Skills, nach Name: [{name, beschreibung, status, herkunft,
    erstellt}]. Auch ausgeschaltete und vorgeschlagene — Sasha soll sehen,
    was da ist, nicht nur, was die KI gerade sieht."""
    return jsonify({"skills": skills.alle()})
