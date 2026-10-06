# ui/routen/erfassung.py
#
# Erfassen und Messen: Data-Collection-Kategorien und -Einträge (/api/log),
# Lifestyle-Graphen (Messreihen) und die Zyklus-Vorhersage daraus.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

import json
import os
from datetime import datetime
from flask import Blueprint, jsonify, request

import categories   # type: ignore
import cycle        # type: ignore  – Zyklus/PMS-Vorhersage aus dem »periode«-Graphen
import graphs       # type: ignore  – dynamische Lifestyle-Graph-Registry
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

from ui.routen.gemeinsam import _DATA_DIR

bp = Blueprint('erfassung', __name__)


# ── Data Collection ────────────────────────────────────────────────────

@bp.route('/api/categories')
def api_categories():
    """Gibt alle verfügbaren Data-Collection-Kategorien zurück (aus categories.py)."""
    return jsonify(categories.CATEGORIES)


@bp.route('/api/data/<category_id>')
def api_data(category_id):
    """
    Gibt alle gespeicherten Einträge einer Kategorie zurück.
    Die Daten liegen in data/<category_id>.json auf Disk.
    Leere Liste wenn noch keine Einträge existieren.
    """
    log_file = os.path.join(_DATA_DIR, f'{category_id}.json')
    if not os.path.exists(log_file):
        return jsonify([])
    with open(log_file, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))


# ── Lifestyle-Graphen (dynamisch, vom Dashboard angelegt) ──────────────
#
# Definitionen liegen in data/graphs.json (core/graphs.py). Die Messwerte
# selbst teilen sich die Data-Collection-Infrastruktur: /api/log schreibt
# nach data/<graph_id>.json, /api/data/<graph_id> liest sie zurück. Hier
# gibt es nur die Verwaltung der Definitionen (Liste / anlegen / löschen).

@bp.route('/api/graphs')
def api_graphs():
    """Alle Graph-Definitionen (für das Graph-Werkzeug und die lifestyle-Box)."""
    return jsonify(graphs.list_graphs())


@bp.route('/api/graphs', methods=['POST'])
def api_graphs_create():
    """
    Neuen Graphen anlegen.
    Body (JSON): {"name": "Gewicht", "type": "number"|"scale", "unit": "kg",
                  "remind": true|false, "remind_at": "HH:MM"}
    remind/remind_at optional → Tages-Reminder gleich beim Anlegen mitgeben.
    """
    body = request.get_json(silent=True) or {}
    try:
        g = graphs.create_graph(body.get('name'), body.get('type', 'number'), body.get('unit', ''),
                                remind=bool(body.get('remind')), remind_at=body.get('remind_at', ''))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    state.push_log(f"GRAPH+: {g['id']} ({g['type']})")
    return jsonify(g)


@bp.route('/api/graphs/<gid>', methods=['DELETE'])
def api_graphs_delete(gid):
    """Graph-Definition und seine Messwerte-Datei löschen."""
    graphs.delete_graph(gid)
    state.push_log(f"GRAPH-: {gid}")
    return jsonify({"ok": True})


@bp.route('/api/graphs/<gid>/predict', methods=['POST'])
def api_graphs_set_predict(gid):
    """
    Vorhersage-Flag eines Graphen setzen/löschen — steuert, ob die lifestyle-Box
    fehlende Tage aus dem Schnitt schätzt (blass/schraffiert). Default aus.
    Body (JSON): {"predict": true|false}
    """
    body = request.get_json(silent=True) or {}
    try:
        g = graphs.set_predict(gid, bool(body.get('predict')))
    except KeyError:
        return jsonify({"error": "unbekannter graph"}), 404
    state.push_log(f"GRAPH~predict {'an' if g.get('predict') else 'aus'}: {gid}")
    return jsonify(g)


@bp.route('/api/graphs/<gid>/remind', methods=['POST'])
def api_graphs_set_remind(gid):
    """
    Tages-Reminder eines Graphen setzen/löschen. Ab `at` erinnern die Fronten
    täglich ans Eintragen, bis für den Tag ein Wert da ist. Default aus.
    Body (JSON): {"remind": true|false, "at": "HH:MM"} (at optional → unverändert)
    """
    body = request.get_json(silent=True) or {}
    try:
        g = graphs.set_remind(gid, bool(body.get('remind')), body.get('at'))
    except KeyError:
        return jsonify({"error": "unbekannter graph"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    state.push_log(f"GRAPH~remind {('an ' + g.get('remind_at', '')) if g.get('remind') else 'aus'}: {gid}")
    return jsonify(g)


@bp.route('/api/graphs/reminders')
def api_graphs_reminders():
    """
    Graphen mit JETZT fälligem Tages-Reminder (remind an, Uhrzeit erreicht, heute
    noch nicht geloggt). Geteilte Quelle: monolith/laptop ziehen daraus das
    »bitte eintragen«-Modal, die TUI ihren Nag. Liefert [{id, name, remind_at}].
    """
    return jsonify(graphs.due_reminders())


@bp.route('/api/cycle')
def api_cycle():
    """
    Zyklus-Vorhersage aus dem »periode«-Graphen (core/cycle.py): wann die
    nächste Periode fällig ist und welche Woche davor als PMS gilt. Reine
    Ableitung aus den Graph-Werten, kein eigener Speicher.

    Liefert die predict()-Form (+ `summary`, der fertige Einzeiler) oder
    {} wenn es keinen »periode«-Graphen bzw. noch keine Werte gibt — die
    Fronten zeichnen dann einfach nichts. NICHT KI-gegatet: reine Anzeige,
    also überall offen.
    """
    p = cycle.predict()
    if not p:
        return jsonify({})
    p['summary'] = cycle.summary(p)
    return jsonify(p)


@bp.route('/api/log', methods=['POST'])
def api_log():
    """
    Speichert einen neuen Data-Collection-Eintrag auf Disk.

    Erwartet JSON: {"category": "sleep_quality", "data": {"date": "...", "quality": 3}}
    Anhängt den Eintrag an data/<category>.json (erstellt die Datei wenn nötig).
    """
    entry       = request.get_json()
    category_id = entry.get('category')
    data        = entry.get('data', {})
    upsert      = bool(entry.get('upsert'))   # True → Eintrag mit gleichem Datum ersetzen

    os.makedirs(_DATA_DIR, exist_ok=True)  # data/ erstellen falls noch nicht vorhanden
    log_file = os.path.join(_DATA_DIR, f'{category_id}.json')

    # Bestehende Einträge laden (oder leere Liste starten)
    logs = []
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)

    # upsert: vorhandene Einträge desselben Datums entfernen (Nachtragen/Ändern
    # im Graph-Werkzeug soll genau EINEN Eintrag pro Tag halten, kein Duplikat).
    if upsert and data.get('date') is not None:
        logs = [e for e in logs if not (isinstance(e, dict) and e.get('date') == data['date'])]

    # Neuen Eintrag mit Zeitstempel anhängen und zurückschreiben
    logs.append({**data, 'logged_at': datetime.now().isoformat()})
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

    state.push_log(f"LOGGED: {category_id} → {data}")
    return jsonify({"ok": True})
