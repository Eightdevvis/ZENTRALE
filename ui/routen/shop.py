# ui/routen/shop.py
#
# Das Schaufenster (core/shop.py): Katalog (schema.org ItemList als JSON-LD),
# ein Stück, Kategorien/Themen, holen, Besitz. Die Werkstatt liest geholte
# Icons über GET /api/shop/besitz?kategorie=icons. Genaue Form: openapi.yaml.
# Doku: memory/hub/shop.md.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).
# 2026-10-10.

from flask import Blueprint, jsonify, request

import shop          # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('shop', __name__)

# JSON-LD ist JSON mit eigenem Medientyp (W3C JSON-LD 1.1). Die Antworten
# sind gewöhnliches JSON — der Typ sagt nur, wie man @context liest.
JSONLD = "application/ld+json"


def _ld(daten, status=200):
    r = jsonify(daten)
    r.status_code = status
    r.mimetype = JSONLD
    return r


def _fehler(e):
    return jsonify({"error": str(e)}), e.code


@bp.route('/api/shop')
def api_shop_katalog():
    """Der Katalog. ?kategorie=icons&thema=pixel filtern."""
    try:
        return _ld(shop.katalog(request.args.get("kategorie") or None,
                                request.args.get("thema") or None))
    except shop.ShopFehler as e:
        return _fehler(e)


@bp.route('/api/shop/kategorien')
def api_shop_kategorien():
    """Alle Kategorien (auch leere) und Themen, je mit Anzahl."""
    try:
        return jsonify(shop.uebersicht())
    except shop.ShopFehler as e:
        return _fehler(e)


@bp.route('/api/shop/<kategorie>/<kennung>')
def api_shop_stueck(kategorie, kennung):
    try:
        return _ld(dict(shop.stueck(kategorie, kennung), **{"@context": shop.KONTEXT}))
    except shop.ShopFehler as e:
        return _fehler(e)


@bp.route('/api/shop/holen', methods=['POST'])
def api_shop_holen():
    """Body: {"adresse": "zentrale://shop/icons/post"}. Idempotent."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(shop.holen(body.get("adresse")))
    except shop.ShopFehler as e:
        return _fehler(e)


@bp.route('/api/shop/besitz')
def api_shop_besitz():
    """Was geholt ist. ?kategorie=icons filtern."""
    try:
        return _ld(shop.besitz(request.args.get("kategorie") or None))
    except shop.ShopFehler as e:
        return _fehler(e)
