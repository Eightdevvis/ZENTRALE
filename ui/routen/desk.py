# ui/routen/desk.py
#
# Desk View (core/desk.py): Desks auflisten, anlegen, laden, ganz speichern.
# Die TUI schickt nach jeder Änderung den ganzen Desk (Elemente in Zellen +
# Verbindungen) mit dem `stand` vom Laden; hat sich die Datei inzwischen
# woanders geändert, kommt 409 mit dem neuen Stand und es wird nichts
# geschrieben. Doku: memory/system/desk_view.md.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-09.

from flask import Blueprint, jsonify, request

import desk          # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('desk', __name__)


def _fehler(e):
    body = {"error": str(e)}
    if isinstance(e, desk.DeskKonflikt):
        body["stand"] = e.stand
    return jsonify(body), e.code


@bp.route('/api/desk')
def api_desk_liste():
    """Alle Desks, zuletzt geändert zuerst."""
    return jsonify({"desks": desk.liste()})


@bp.route('/api/desk', methods=['POST'])
def api_desk_anlegen():
    """Leeren Desk anlegen. Body: {"name": "Elektronik"}."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(desk.anlegen(body.get("name"))), 201
    except desk.DeskFehler as e:
        return _fehler(e)


@bp.route('/api/desk/<name>')
def api_desk_laden(name):
    try:
        return jsonify(desk.laden(name))
    except desk.DeskFehler as e:
        return _fehler(e)


@bp.route('/api/desk/<name>', methods=['PUT'])
def api_desk_speichern(name):
    """Body: {"elemente": [...], "verbindungen": [...], "stand": "..."}."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(desk.speichern(name, body.get("elemente"),
                                      body.get("verbindungen"), body.get("stand")))
    except desk.DeskFehler as e:
        return _fehler(e)
