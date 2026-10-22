# ui/routen/hub_apps.py
#
# Die Apps des Hubs über HTTP (Hub-Grundlagen, 2026-10-22,
# memory/hub/hub_bauplan.md „Apps starten, stoppen, weiterreichen"):
#
#   GET  /api/apps               installierte Apps aus ihren Manifesten
#   POST /api/apps/<name>/start  Prozess-App starten (läuft sie, nichts)
#   POST /api/apps/<name>/stop   nur, was der Hub selbst gestartet hat
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

import app_verwaltung      # type: ignore  – in core/, durch sys.path.insert auffindbar
import app_weiterleitung   # type: ignore

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
