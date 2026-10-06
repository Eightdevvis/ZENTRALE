# ui/routen/zustand.py
#
# System-Zustand: State-Polling der TUI, Sensor-Webhook, Telemetrie (PC + Pi),
# Paket-Versorgung der Aussenposten.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from datetime import datetime
from flask import Blueprint, Response, jsonify, request

import aussenposten # type: ignore  – Paket-Schnuerer für Knoten ohne Backend
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import telemetry    # type: ignore  – PC-Host-Telemetrie (CPU/GPU/VRAM/Temp/RAM)

bp = Blueprint('zustand', __name__)


# ── State-Polling ──────────────────────────────────────────────────────

@bp.route('/api/state')
def api_state():
    """
    Liefert den aktuellen System-State als JSON.
    Wird vom Browser jede Sekunde abgefragt (Polling-Loop in index.html).
    """
    snapshot = state.get_snapshot()
    # Datum wird hier im Backend formatiert statt im Frontend,
    # damit alle Clients (auch zukünftige) dasselbe Format bekommen.
    snapshot['time'] = datetime.now().strftime("%d. %B %Y")
    return jsonify(snapshot)


# ── Sensor-Webhook ─────────────────────────────────────────────────────
#
# POST /api/sensor/<name> – Eingangskanal fuer externe Sensor-Trigger.
#
# Seit der PC↔Pi-Topologie-Migration laeuft das Backend auf dem PC. Echte
# Sensoren (Pi-PIR, Tuersensor, Mikrocontroller) haengen aber physisch
# am Pi (oder spaeter direkt am LAN). Damit sie Events ins System bringen
# koennen, ohne dass main.py auf jedem Knoten laufen muss, schicken sie
# einen HTTP-POST an diesen Endpoint. Der Sensor-Name wird gequeued, der
# Event-Loop in main.py mapped ihn auf den jeweiligen Event.
#
# Whitelist gegen Tippfehler und gegen Querschuss aus dem LAN (Hotspot
# ist nicht streng abgeschottet). Bewusst nicht aus events.py generiert –
# Sensor-Namen sind die "physischen" Eingangskanaele, Events sind die
# internen logischen Ereignisse. Beide Welten getrennt halten.

_ALLOWED_SENSORS = {"button", "light", "motion", "door"}


# ── Telemetrie ─────────────────────────────────────────────────────────
#
# Zwei Maschinen, zwei Wege:
#   PC : lokal aus /proc + /sys + nvidia-smi (core/telemetry.pc_snapshot)
#   Pi : der Pi POSTet seine Werte an /api/telemetry/pi (FS read-only, kann
#        nicht selbst anzeigen) → wir halten den letzten Stand in state.py.
# GET /api/telemetry liefert beides kombiniert ans Dashboard.

# Welche Top-Level-Keys wir vom Pi akzeptieren (gegen Muell/Querschuss aus
# dem LAN). Werte werden nicht weiter geparst - der Pi baut die Shape selbst
# (scripts/pi_sensor_bridge.py), wir nehmen nur bekannte Schluessel.
_ALLOWED_PI_METRICS = {"cpu", "temp", "ram", "disk"}


@bp.route('/api/telemetry')
def api_telemetry():
    """PC- und Pi-Telemetrie kombiniert. Wird vom Dashboard alle ~2s gepollt."""
    return jsonify({
        "pc": telemetry.pc_snapshot(),
        "pi": state.get_pi_telemetry(),   # {} solange der Pi noch nichts gesendet hat
    })


@bp.route('/api/telemetry/pi', methods=['POST'])
def api_telemetry_pi():
    """
    Telemetrie-Push vom Pi entgegennehmen. Body (JSON) hat die gleiche
    Shape wie ein Meter-Block im Frontend, z.B.:
      {"cpu": {"v": 12.3}, "temp": {"v": 51.0},
       "ram": {"v": 38, "used": 0.6, "total": 1.0},
       "disk": {"v": 47, "used": 14.1, "total": 30.0}}
    Nur bekannte Schluessel werden uebernommen.
    """
    body = request.get_json(silent=True) or {}
    clean = {k: v for k, v in body.items() if k in _ALLOWED_PI_METRICS}
    state.set_pi_telemetry(clean)
    return jsonify({"ok": True})


@bp.route('/api/sensor/<name>', methods=['POST'])
def api_sensor_trigger(name):
    """
    Externes Sensor-Signal entgegennehmen und in die Verarbeitungs-
    Queue stellen. Antwortet sofort – die eigentliche Verarbeitung
    macht der Event-Loop asynchron.

    Body wird aktuell ignoriert (reines Trigger-Signal reicht). Spaeter
    kann hier z.B. ein Wert (Helligkeit, Tueroffen-Dauer) mitgegeben
    werden – dann erweitern wir queue_sensor() um ein meta-Dict.
    """
    if name not in _ALLOWED_SENSORS:
        return jsonify({"error": f"unbekannter Sensor: {name}"}), 400
    state.queue_sensor(name)
    state.push_log(f"WEBHOOK: sensor/{name} von {request.remote_addr}")
    return jsonify({"ok": True})


# ── Aussenposten-Versorgung ────────────────────────────────────────────
#
# Ein Aussenposten (Pi an der Wand, spaeter einer pro Raum) hostet kein
# Backend und hat keinen Git-Clone. Er holt sich hier sein zugeschnittenes
# Paket ab: Manifest fragen, Version vergleichen, bei Abweichung das tar.gz
# ziehen. Was drin ist, sagt deploy/aussenposten.txt; geschnuert wird in
# core/aussenposten.py. Gegenstueck auf dem Knoten:
# scripts/aussenposten_update.py (stdlib-only, laeuft ohne venv).
#
# Absichtlich OHNE KI-Gate: ein Knoten muss sich auch dann
# aktualisieren koennen, wenn die KI gedrosselt ist — sonst friert genau die
# Maschine ein, die man gerade reparieren will.


@bp.route('/api/aussenposten/manifest')
def api_aussenposten_manifest():
    """Was gerade zu holen waere: Version (Inhalts-Hash), Dateizahl, Groesse.

    Billig genug fuer einen Poll alle paar Minuten — es wird nur gehasht,
    nicht gepackt.
    """
    try:
        return jsonify(aussenposten.manifest())
    except Exception as exc:
        return jsonify({"error": "Paket-Manifest fehlgeschlagen: %s" % exc}), 500


@bp.route('/api/aussenposten/paket')
def api_aussenposten_paket():
    """Das Paket selbst als tar.gz.

    Deterministisch gepackt (sortiert, mtime=0) — gleicher Inhalt, gleiche
    Bytes. Die Version steht im Header X-Paket-Version, damit der Knoten
    nach dem Download noch einmal abgleichen kann, ob sich zwischen Manifest
    und Abruf etwas geaendert hat.
    """
    try:
        daten = aussenposten.paket()
        version = aussenposten.manifest()["version"]
    except Exception as exc:
        return jsonify({"error": "Paket-Bau fehlgeschlagen: %s" % exc}), 500
    return Response(daten, content_type='application/gzip', headers={
        'X-Paket-Version': version,
        'Content-Disposition': 'attachment; filename="aussenposten.tar.gz"',
    })
