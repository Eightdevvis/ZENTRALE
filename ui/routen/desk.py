# ui/routen/desk.py
#
# Desk View (core/desk.py): Desks auflisten, anlegen, laden, ganz speichern;
# Bilder (core/desk_bild.py): übernehmen, Vorschau, öffnen.
# Die TUI schickt nach jeder Änderung den ganzen Desk (Elemente in Zellen +
# Verbindungen) mit dem `stand` vom Laden; hat sich die Datei inzwischen
# woanders geändert, kommt 409 mit dem neuen Stand und es wird nichts
# geschrieben. Doku: memory/system/desk_view.md.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-09.

import os

from flask import Blueprint, jsonify, request, send_file

import desk          # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import desk_bild     # type: ignore

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


# ── Bilder auf dem Desk (core/desk_bild.py, 2026-10-10) ───────────────
# Bilder gehören dem Desk-Ordner (bilder/), nicht einem Desk — darum ein
# eigener Pfad ohne Desk-Namen.


@bp.route('/api/desk-bild/quellen')
def api_desk_bild_quellen():
    """Bilder in ~/Zentrale/Input, neueste zuerst."""
    return jsonify({"quellen": desk_bild.quellen()})


@bp.route('/api/desk-bild', methods=['POST'])
def api_desk_bild_uebernehmen():
    """Ein Bild nach <desk_ordner>/bilder/ kopieren. Body: {"quelle": "foto.jpg"}
    (Name in Input/ oder ein Pfad). -> {datei, titel, w, h}."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(desk_bild.uebernehmen(body.get("quelle"))), 201
    except desk.DeskFehler as e:
        return _fehler(e)


@bp.route('/api/desk-bild/vorschau', methods=['POST'])
def api_desk_bild_vorschau():
    """Body: {"datei": "bilder/x.png", "w": 32, "h": 10, "modus": "mono"|"farbe",
    "invert": false} -> {status, zeilen?: [[[zeichen, "#rrggbb"|null], …], …], text?}."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(desk_bild.vorschau(body.get("datei"), body.get("w"), body.get("h"),
                                          body.get("modus") or "mono", bool(body.get("invert"))))
    except desk.DeskFehler as e:
        return _fehler(e)


@bp.route('/api/desk-bild/oeffnen', methods=['POST'])
def api_desk_bild_oeffnen():
    """Body: {"datei": "bilder/x.png"} -> {pfad, da, betrachter}. Öffnen tut
    die TUI auf ihrem Rechner (Bildbetrachter, Einstellung bild_betrachter)."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(desk_bild.oeffnen_info(body.get("datei")))
    except desk.DeskFehler as e:
        return _fehler(e)


@bp.route('/api/desk-bild/datei')
def api_desk_bild_datei():
    """Das Bild selbst (?datei=bilder/x.png) — für eine TUI auf einem anderen
    Rechner als das Backend, die es zum Öffnen erst holen muss."""
    try:
        p = desk_bild.pfad(request.args.get("datei"))
    except desk.DeskFehler as e:
        return _fehler(e)
    if not os.path.isfile(p):
        return jsonify({"error": "bild fehlt"}), 404
    return send_file(p)
