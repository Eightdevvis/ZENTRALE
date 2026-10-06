# ui/routen/notizen.py
#
# Notizen: die Block-Notizen des TUI-Notiz-Werkzeugs.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from flask import Blueprint, jsonify, request

import notes        # type: ignore  – Notiz-Registry (Text-/Listen-/Float-Blöcke, TUI-Werkzeug)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('notizen', __name__)


# ── Notizen (dynamisch, vom Dashboard angelegt) ────────────────────────
#
# Freie Notizen aus gestapelten Blöcken (text/list/float), Inhalt inline in
# data/notes.json (core/notes.py). Aktuell nur vom TUI-Werkzeug bespielt; die
# Browser-Front kommt später. Dünner Adapter — alle Logik in core/notes.

@bp.route('/api/notes')
def api_notes():
    """Übersicht aller Notizen (ohne Block-Inhalte), neueste zuerst."""
    return jsonify(notes.list_notes())


@bp.route('/api/notes', methods=['POST'])
def api_notes_create():
    """Neue (leere) Notiz anlegen. Body (JSON): {"title": "..."} (optional)."""
    body = request.get_json(silent=True) or {}
    n = notes.create_note(body.get('title', ''))
    state.push_log(f"NOTIZ+: {n['id']}")
    return jsonify(n)


@bp.route('/api/notes/<nid>')
def api_notes_get(nid):
    """Vollständige Notiz mit allen Blöcken."""
    n = notes.get_note(nid)
    if n is None:
        return jsonify({"error": "unbekannte notiz"}), 404
    return jsonify(n)


@bp.route('/api/notes/<nid>', methods=['PUT'])
def api_notes_save(nid):
    """
    Notiz-Inhalt ersetzen. Body (JSON): {"title": "...", "blocks": [...]}.
    Beide Felder optional; nur übergebene werden angefasst. Blöcke werden
    serverseitig normalisiert (siehe core/notes._clean_blocks).
    """
    body = request.get_json(silent=True) or {}
    try:
        n = notes.save_note(nid, title=body.get('title'), blocks=body.get('blocks'))
    except KeyError:
        return jsonify({"error": "unbekannte notiz"}), 404
    return jsonify(n)


@bp.route('/api/notes/<nid>', methods=['DELETE'])
def api_notes_delete(nid):
    """Notiz löschen."""
    notes.delete_note(nid)
    state.push_log(f"NOTIZ-: {nid}")
    return jsonify({"ok": True})
