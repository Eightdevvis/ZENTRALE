# ui/routen/ablage.py
#
# Die Ablage (core/ablage.py): Liste, ein Dokument lesen, archivieren — und
# Anhänge annehmen (core/anhang.py), die Sasha im Chat mit `/anhang <pfad>`
# hineingibt. Gelöscht wird nie (der Sync ist additiv), nur archiviert.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-07, Phase 5 des Claude-Web-Plans (memory/ki/ablage.md).

import base64
import binascii

from flask import Blueprint, jsonify, request

import ablage        # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import ai_backends   # type: ignore
import anhang        # type: ignore
import gespraeche    # type: ignore

bp = Blueprint('ablage', __name__)


def _mit_gespraech(k: dict) -> dict:
    """Kopf + Titel des Gesprächs, aus dem das Dokument kam (für die Liste)."""
    k = dict(k)
    gid = k.get("gespraech")
    if gid and gespraeche.gibt_es(gid):
        k["gespraech_titel"] = gespraeche.kopf(gid).get("titel") or ""
    return k


@bp.route('/api/ablage')
def api_ablage_liste():
    """Alle Dokumente, neueste Änderung zuerst. ?archiv=1: die archivierten."""
    archiv = request.args.get('archiv') in ('1', 'true', 'ja')
    return jsonify({"dokumente": [_mit_gespraech(k) for k in ablage.liste(archiv)]})


@bp.route('/api/ablage/<doc_id>')
def api_ablage_lesen(doc_id):
    """Ein Dokument: {kopf, fassung, inhalt (Text) | null (Bild), bytes,
    mime?, pfad}. ?fassung=n für eine ältere Fassung."""
    try:
        d = ablage.lesen(doc_id, request.args.get('fassung'))
        d["pfad"] = ablage.pfad(doc_id, request.args.get('fassung'))
    except ablage.Unbekannt:
        return jsonify({"error": "Dieses Dokument gibt es nicht."}), 404
    d["kopf"] = _mit_gespraech(d["kopf"])
    return jsonify(d)


@bp.route('/api/ablage/<doc_id>/archiv', methods=['POST'])
def api_ablage_archiv(doc_id):
    """Body {an: bool} — archivieren oder zurückholen."""
    an = bool((request.get_json(silent=True) or {}).get('an', True))
    try:
        return jsonify(ablage.archivieren(doc_id, an))
    except ablage.Unbekannt:
        return jsonify({"error": "Dieses Dokument gibt es nicht."}), 404


@bp.route('/api/anhang', methods=['POST'])
def api_anhang():
    """Eine Datei als Anhang annehmen. Body {pfad, daten (base64), gespraech?}.

    Die TUI liest die Datei auf ihrem Rechner und schickt die Bytes mit —
    das Backend öffnet den Pfad nie (er kann auf einem anderen Rechner
    liegen), prüft ihn aber gegen die Sperrliste. Antwort {id, titel, art,
    zeichen, gekappt, hinweis}; abgelehnt → 400 mit Klartext."""
    body = request.get_json(silent=True) or {}
    pfad = str(body.get('pfad') or '').strip()
    try:
        daten = base64.b64decode(str(body.get('daten') or ''), validate=True)
    except (binascii.Error, ValueError):
        return jsonify({"error": "Die Datei kam kaputt an."}), 400
    gid = body.get('gespraech')
    gid = str(gid) if gid and gespraeche.gibt_es(str(gid)) else None
    cloud = ai_backends.chat_available() == ai_backends.CLOUD
    try:
        return jsonify(anhang.annehmen(pfad, daten, gespraech=gid, cloud=cloud))
    except anhang.Abgelehnt as e:
        return jsonify({"error": str(e)}), 400
