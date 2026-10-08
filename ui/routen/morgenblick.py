# ui/routen/morgenblick.py
#
# Der Morgenblick (core/morgenblick.py): erstellen und die Knöpfe darin
# einlösen. Die fertige Seite liefert GET /api/ablage/<id>/roh aus
# (ui/routen/ablage.py).
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-08, memory/werkzeuge/morgenblick.md.

import html

from flask import Blueprint, Response, jsonify, request

import morgenblick   # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('morgenblick', __name__)

_LOKAL_ADRESSEN = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
_LOKAL_NAMEN = ("localhost", "127.0.0.1", "[::1]")


@bp.route('/api/morgenblick', methods=['POST'])
def api_morgenblick():
    """Morgenblick erstellen und in die Ablage legen. Body {ki?: bool}.
    -> {id, titel, url, mit_ki, modell}. Dauert mit KI einige Sekunden."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(morgenblick.erstellen(ki=body.get("ki", True) is not False))
    except morgenblick.Fehler as e:
        return jsonify({"error": str(e)}), 500


def lokal() -> bool:
    """Kommt die Anfrage von diesem Rechner — und war sie an localhost
    gerichtet? Der Host-Kopf zählt mit: sonst könnte eine fremde Seite
    über einen umgebogenen Namen (DNS-Rebinding) hier anklopfen."""
    host = (request.host or "").lower()
    host = host[:host.find("]") + 1] if host.startswith("[") else host.split(":")[0]
    return request.remote_addr in _LOKAL_ADRESSEN and host in _LOKAL_NAMEN


def _seite(titel, text, code):
    """Eine kleine Bestätigungsseite im Stil des Morgenblicks."""
    rumpf = (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(titel)}</title><style>'
        'body{margin:0;background:#F9F9F7;color:#2E2C27;'
        'font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}'
        'main{max-width:560px;margin:18vh auto 0;padding:0 16px}'
        'h1{font-size:20px;font-weight:600;margin:0 0 8px}p{margin:0;color:#6B6A63}'
        f'</style></head><body><main><h1>{html.escape(titel)}</h1>'
        f'<p>{html.escape(text)}</p></main></body></html>')
    r = Response(rumpf, status=code, mimetype="text/html")
    r.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    r.headers["Cache-Control"] = "no-store"
    return r


@bp.route('/api/morgenblick/auftrag')
def api_morgenblick_auftrag():
    """Ein Knopf aus dem Morgenblick: legt EIN Gespräch mit dem Auftrag als
    Vorschlag an und setzt es aktiv. Sonst nichts — nichts wird ausgeführt.
    Nur von diesem Rechner, nur mit einem Link, den dieses ZENTRALE heute
    (oder gestern) selbst signiert hat."""
    if not lokal():
        return _seite("Nicht von hier", "Knöpfe aus dem Morgenblick gehen nur auf "
                      "dem Rechner, auf dem ZENTRALE läuft.", 403)
    a = request.args
    try:
        _gid, neu = morgenblick.auftrag_anlegen(a.get("d"), a.get("b"), a.get("a"), a.get("s"))
    except morgenblick.KnopfUngueltig as e:
        return _seite("Nichts angelegt", str(e), 400)
    titel = "Gespräch angelegt" if neu else "Das Gespräch gibt es schon"
    return _seite(titel, f"„{a.get('b')}“ — öffne den Chat in ZENTRALE.", 200)
