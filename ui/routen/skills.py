# ui/routen/skills.py
#
# Gedächtnis und Skills der KI für Sasha: ansehen und von Hand ändern.
#
#   GET  /api/skills                  die Skill-Liste (Phase 4)
#   POST /api/skills/<name>/status    Skill an/aus (Phase 3)
#   GET  /api/gedaechtnis             Kernakten, Bereiche (Titel), Skills
#   PUT  /api/gedaechtnis/<akte>      eine der drei Kernakten ersetzen
#
# Geschrieben wird hier NUR, was Sasha selbst in der TUI tut (Gedächtnis-
# Ansicht, tui/ansichten/gedaechtnis.py): die drei Kernakten und der
# Skill-Status. Alles andere schreibt die KI über ihre gegateten Werkzeuge.
#
# Warum Gedächtnis-Routen in DIESER Datei (2026-10-07): beides ist „was die
# KI über Sasha weiß und wie sie arbeitet", und eine neue Routen-Datei
# hätte ui/routen/__init__.py angefasst, an dem gerade ein zweiter Umbau
# (Phase 5) hängt.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify, request

import gedaechtnis   # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import skills        # type: ignore

bp = Blueprint('skills', __name__)


@bp.route('/api/skills')
def api_skills():
    """Alle Skills, nach Name: [{name, beschreibung, status, herkunft,
    erstellt}]. Auch ausgeschaltete und vorgeschlagene — Sasha soll sehen,
    was da ist, nicht nur, was die KI gerade sieht. Dazu `skill_liste`:
    wie lang die Liste der aktiven im Prompt wäre und ob sie über die
    Grenze geht ({laenge, grenze, zu_lang, gekuerzt, nur_name}, 2026-10-08)."""
    return jsonify({"skills": skills.alle(), "skill_liste": skills.liste_lage()})


@bp.route('/api/skills/<name>/status', methods=['POST'])
def api_skill_status(name):
    """Body {status: aktiv|aus|vorgeschlagen}. 404 unbekannter Skill, 400
    unbekannter Status. → {skill, skill_liste}"""
    status = (request.get_json(silent=True) or {}).get("status")
    try:
        skill = skills.status_setzen(name, str(status or ""))
    except KeyError:
        return jsonify({"error": f"Den Skill „{name}“ gibt es nicht."}), 404
    except ValueError:
        return jsonify({"error": "Status muss aktiv, aus oder vorgeschlagen sein."}), 400
    return jsonify({"skill": skill, "skill_liste": skills.liste_lage()})


def _kernakte(akte):
    text = gedaechtnis.kernakte_lesen(akte)
    return {"akte": akte, "text": text, "stand": gedaechtnis.kernakte_stand(text)}


@bp.route('/api/gedaechtnis')
def api_gedaechtnis():
    """Alles auf einen Blick: {kernakten: [{akte, text, stand}],
    bereiche: [{bereich, titel: [...]}], skills: [...], skill_liste}. Kernakten in der
    festen Reihenfolge Hausregeln, Steckbrief, Ziele."""
    return jsonify({
        "kernakten": [_kernakte(a) for a in gedaechtnis.KERNAKTEN],
        "bereiche": [{"bereich": b, "titel": gedaechtnis.liste(b)}
                     for b in gedaechtnis.BEREICHE],
        "skills": skills.alle(),
        "skill_liste": skills.liste_lage(),
    })


@bp.route('/api/gedaechtnis/<akte>', methods=['PUT'])
def api_gedaechtnis_schreiben(akte):
    """Body {text, stand?}. Nur hausregeln, steckbrief, ziele (sonst 404).
    `stand` aus dem GET: weicht die Datei inzwischen ab (die KI hat
    geschrieben), 409 statt Überschreiben. → {akte, text, stand}"""
    if akte not in gedaechtnis.KERNAKTEN:
        return jsonify({"error": "Ändern lassen sich hier nur Hausregeln, "
                                 "Steckbrief und Ziele."}), 404
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    if not isinstance(text, str):
        return jsonify({"error": "Es fehlt der Text."}), 400
    stand = body.get("stand")
    if stand and stand != gedaechtnis.kernakte_stand(gedaechtnis.kernakte_lesen(akte)):
        return jsonify({"error": "Die Akte wurde inzwischen geändert — "
                                 "neu laden und noch einmal."}), 409
    try:
        gedaechtnis.kernakte_schreiben(akte, text)
    except ValueError:
        return jsonify({"error": f"Zu lang — höchstens "
                                 f"{gedaechtnis.MAX_KERNAKTE} Zeichen."}), 400
    return jsonify(_kernakte(akte))
