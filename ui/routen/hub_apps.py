# ui/routen/hub_apps.py
#
# Die Apps des Hubs über HTTP (Hub-Grundlagen, 2026-10-22,
# memory/hub/hub_bauplan.md „Apps starten, stoppen, weiterreichen"):
#
#   GET  /api/apps               installierte Apps aus ihren Manifesten
#   POST /api/apps/<name>/start  Prozess-App starten (läuft sie, nichts)
#   POST /api/apps/<name>/stop   nur, was der Hub selbst gestartet hat
#   POST /api/apps/laden         App aus dem Schaufenster holen, Ansichten zeigen
#   POST /api/apps/installieren  mit den gewählten Ansichten einrichten
#                                (core/app_installation.py, seit 2026-10-25)
#   POST /api/apps/remove        remove from this node (built-in apps, step 10)
#   GET  /api/apps/installed     shop addresses installed on this node (+ holds)
#   POST /api/apps/hold          hold an extracted app at its version (step 12)
#   GET/POST /api/apps/<name>/plugs   the plug dialog (building kit step 11)
#
# Und die Weiterleitung: gehört der Pfad einer Anfrage laut `routen` im
# app.toml einer App, reicht der Hub sie unverändert an die App
# (core/app_weiterleitung.py). Das läuft vor dem Routing von Flask, aber
# NACH der Tür (zugang steht in BEREICHE vorn und hängt seine Prüfung zuerst
# ein) — eine App hinter dem Hub ist so geschützt wie der Hub selbst.
# Form aller Antworten: openapi.yaml.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).

from flask import Blueprint, Response, jsonify, request

import app_installation   # type: ignore  – in core/, durch sys.path.insert auffindbar
import app_verwaltung      # type: ignore  – in core/, durch sys.path.insert auffindbar
import app_weiterleitung   # type: ignore
import plugs               # type: ignore

bp = Blueprint('hub_apps', __name__)


@bp.before_app_request
def _weiterleiten():
    m = app_weiterleitung.besitzer(request.path)
    if m is None:
        return None
    status, koepfe, daten = app_weiterleitung.weiterleiten(
        m, request.method, request.path, request.query_string,
        request.get_data(cache=False), request.headers.items())
    antwort = Response(daten, status=status)
    antwort.headers.pop("Content-Type", None)     # nur, was die App sagt
    for k, v in koepfe:
        antwort.headers.add(k, v)
    return antwort


@bp.route('/api/apps', methods=['GET'])
def api_apps():
    return jsonify(app_verwaltung.liste())


@bp.route('/api/apps/<name>/start', methods=['POST'])
def api_app_start(name):
    try:
        return jsonify(app_verwaltung.starten(name))
    except app_verwaltung.AppFehler as e:
        return jsonify(e.antwort), e.status


@bp.route('/api/apps/<name>/stop', methods=['POST'])
def api_app_stop(name):
    try:
        return jsonify(app_verwaltung.stoppen(name))
    except app_verwaltung.AppFehler as e:
        return jsonify(e.antwort), e.status


@bp.route('/api/apps/laden', methods=['POST'])
def api_app_laden():
    """Body {"adresse": "zentrale://shop/apps/<id>"} → Ansichten zur Wahl."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(app_installation.laden(body.get("adresse")))
    except app_installation.InstallFehler as e:
        return jsonify({"error": str(e)}), e.code


@bp.route('/api/apps/installieren', methods=['POST'])
def api_app_installieren():
    """Body {"adresse", "ansichten": ["browser", …]} (mindestens eine)."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(app_installation.installieren(body.get("adresse"), body.get("ansichten")))
    except app_installation.InstallFehler as e:
        return jsonify({"error": str(e)}), e.code


@bp.route('/api/apps/remove', methods=['POST'])
def api_app_remove():
    """Body {"adresse": "zentrale://shop/apps/<id>"}: off on this node, nothing deleted."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(app_installation.entfernen(body.get("adresse")))
    except app_installation.InstallFehler as e:
        return jsonify({"error": str(e)}), e.code


@bp.route('/api/apps/installed', methods=['GET'])
def api_apps_installed():
    return jsonify({"adressen": app_installation.installed_addresses(),
                    "held": app_installation.held_addresses()})


@bp.route('/api/apps/hold', methods=['POST'])
def api_app_hold():
    """Body {"adresse", "hold": true|false}."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(app_installation.hold(body.get("adresse"), body.get("hold") is True))
    except app_installation.InstallFehler as e:
        return jsonify({"error": str(e)}), e.code


# ── Plug dialog (building kit step 11, core/plugs.py) ─────────────────
#
#   GET  /api/apps/<name>/plugs   the sockets to ask, with the providers here
#   POST /api/apps/<name>/plugs   {"choices": {socket: provider port | null}}
#                                 → one run through the gate; a required
#                                 socket left unplugged withdraws the install

@bp.route('/api/apps/<name>/plugs', methods=['GET'])
def api_app_plugs(name):
    if not plugs.known(name):
        return jsonify({"error": "unknown app"}), 404
    return jsonify({"name": name, "sockets": plugs.sockets(name)})


@bp.route('/api/apps/<name>/plugs', methods=['POST'])
def api_app_plugs_confirm(name):
    body = request.get_json(silent=True) or {}
    choices = body.get("choices")
    if not isinstance(choices, dict) or not all(v is None or isinstance(v, str) for v in choices.values()):
        return jsonify({"error": "choices: {socket: provider port or null}"}), 400
    try:
        r = app_installation.plug(name, choices)
    except app_installation.InstallFehler as e:
        return jsonify({"error": str(e)}), e.code
    return jsonify(r), (200 if r["ok"] and not r["withdrawn"] else 409)
