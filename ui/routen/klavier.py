# ui/routen/klavier.py
#
# Klavier-Werkzeug: die Melodien-Registry.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from flask import Blueprint, jsonify, request

import melodies     # type: ignore  – Melodie-Registry (Klavier-Werkzeug, data/melodies.json)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('klavier', __name__)


# ── Melodien (Klavier-Werkzeug, Canvas-Exhibit „Klavier") ──────────────
#
# Auf der Computertastatur gespielte und aufgezeichnete Melodien. Wie die
# Listen liegen Definition UND Inhalt inline in data/melodies.json
# (core/melodies.py). Direkte Nutzeraktion, also NICHT KI-gegatet — die
# Routen stehen überall offen.

@bp.route('/api/melodies')
def api_melodies():
    """Alle aufgezeichneten Melodien inkl. ihrer Noten."""
    return jsonify(melodies.list_melodies())


@bp.route('/api/melodies', methods=['POST'])
def api_melodies_create():
    """
    Aufnahme ablegen.
    Body (JSON): {"name": "Regen", "notes": [{"n": 60, "t": 0, "d": 320}, …]}
    n = MIDI-Note, t = Startzeit ab Aufnahmebeginn (ms), d = Klingdauer (ms).
    """
    body = request.get_json(silent=True) or {}
    try:
        m = melodies.create_melody(body.get('name'), body.get('notes'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    state.push_log(f"MELODIE+: {m['id']} ({len(m['notes'])} noten)")
    return jsonify(m)


@bp.route('/api/melodies/<mid>/rename', methods=['POST'])
def api_melodies_rename(mid):
    """Melodie umbenennen. Body (JSON): {"name": "…"}"""
    body = request.get_json(silent=True) or {}
    try:
        m = melodies.rename_melody(mid, body.get('name'))
    except KeyError:
        return jsonify({"error": "unbekannte melodie"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(m)


@bp.route('/api/melodies/<mid>', methods=['DELETE'])
def api_melodies_delete(mid):
    """Melodie löschen."""
    melodies.delete_melody(mid)
    state.push_log(f"MELODIE-: {mid}")
    return jsonify({"ok": True})
