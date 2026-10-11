# ui/routen/werkstatt.py
#
# Die Werkstatt (core/werkstatt.py, 2026-10-10): selbst gebaute Apps aus
# Vorlagen — auflisten, anlegen, Name/Symbol ändern, löschen; dazu was der
# Schmied zur Wahl stellt (Vorlagen, Bilder aus ~/Zentrale/Input).
# Desks umbenennen/löschen stehen bei den Desk-Routen (ui/routen/desk.py).
# Doku: memory/hub/werkstatt.md.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify, request

import werkstatt     # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('werkstatt', __name__)


def _fehler(e):
    return jsonify({"error": str(e)}), e.code


@bp.route('/api/werkstatt/apps')
def api_werkstatt_apps():
    """Selbst gebaute Apps mit Symbol (Raster oder Motiv)."""
    return jsonify({"apps": werkstatt.liste()})


@bp.route('/api/werkstatt/apps', methods=['POST'])
def api_werkstatt_anlegen():
    """Body: {"name": "Geige", "icon": {"bild": "foto.png"} | {"motiv": "post"},
    "vorlage": "desk"} -> 201 die neue App."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(werkstatt.anlegen(body.get("name"), body.get("icon"),
                                         body.get("vorlage") or "desk")), 201
    except werkstatt.WerkstattFehler as e:
        return _fehler(e)


@bp.route('/api/werkstatt/apps/<slug>', methods=['PATCH'])
def api_werkstatt_aendern(slug):
    """Body: {"name"?: "...", "icon"?: {...}}. Der Kurzname bleibt."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(werkstatt.aendern(slug, body.get("name"), body.get("icon")))
    except werkstatt.WerkstattFehler as e:
        return _fehler(e)


@bp.route('/api/werkstatt/apps/<slug>', methods=['DELETE'])
def api_werkstatt_loeschen(slug):
    """?desk=1 löscht ihren Desk mit (Sasha wurde gefragt)."""
    try:
        werkstatt.loeschen(slug, request.args.get("desk") in ("1", "true", "ja"))
    except werkstatt.WerkstattFehler as e:
        return _fehler(e)
    return jsonify({"ok": True})


@bp.route('/api/werkstatt/name', methods=['POST'])
def api_werkstatt_name():
    """Taugt der Name? Der Schmied fragt gleich beim ersten Schritt, nicht
    erst am Ende. Body: {"name": "...", "ausser"?: "<slug>"} -> {name, slug}."""
    body = request.get_json(silent=True) or {}
    try:
        name, slug = werkstatt.namen_pruefen(body.get("name"), body.get("ausser"))
    except werkstatt.WerkstattFehler as e:
        return _fehler(e)
    return jsonify({"name": name, "slug": slug})


@bp.route('/api/werkstatt/vorlagen')
def api_werkstatt_vorlagen():
    return jsonify({"vorlagen": werkstatt.vorlagen()})


@bp.route('/api/werkstatt/bilder')
def api_werkstatt_bilder():
    """Bilder in ~/Zentrale/Input, neueste zuerst — Kandidaten fürs Symbol."""
    return jsonify({"bilder": werkstatt.bilder()})
