# ui/routen/karte.py
#
# Weltkarte: Basiskarte, Braille-Füllung, Länder, Overlay-Layer (core/map/).
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from flask import Blueprint, jsonify, request

from map import base_braille as map_base_braille  # type: ignore  – Maps-System (Braille-Füllung)
from map import base_features as map_base_features  # type: ignore  – Maps-System (core/map/)
from map import country_outlines as map_country_outlines  # type: ignore  – Länder-Auswahl (TUI)
from map import layers as map_layers  # type: ignore  – Overlay-Layer (Achse 2, Handelsrouten)

bp = Blueprint('karte', __name__)


@bp.route('/api/map/base')
def api_map_base():
    """
    Basiskarte (Küstenlinien 1:110m) für den Viewport der anfragenden Front,
    fertig auf deren Zellraster projiziert. Front-agnostisch: TUI und Browser
    rufen denselben Endpoint, schicken nur ihr eigenes cols/rows/aspect mit.
    Alle Geo-Mathematik steckt in core/map/ (siehe memory/maps/maps_system.md).

    Query: cx,cy (lon/lat Mittelpunkt), zoom (≥0), cols,rows (Zielraster),
           aspect (Zellbreite/Höhe; TUI ≈ 0.5, SVG = 1.0).
    NICHT KI-gegatet — die Karte gibt es ÜBERALL.
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 120))
        rows = int(a.get('rows', 40))
        aspect = float(a.get('aspect', 0.5))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    return jsonify(map_base_features(cx, cy, zoom, cols, rows, aspect))


@bp.route('/api/map/braille')
def api_map_braille():
    """
    Basiskarte als GEFÜLLTES Land in Braille („kleine Punkte als Füllung") —
    fertige Braille-Zeilen für eine Terminal-Front, die sie nur druckt. 2×4
    Subpixel pro Zelle. Geo-/Rasterlogik komplett in core/map/render.py.

    Query: cx,cy (lon/lat), zoom (≥0), cols,rows (Zeichenraster der TUI-Box).
    NICHT KI-gegatet (Karte gibt es überall).
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 80))
        rows = int(a.get('rows', 30))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    return jsonify(map_base_braille(cx, cy, zoom, cols, rows))


@bp.route('/api/map/countries')
def api_map_countries():
    """
    Länder für die Auswahl/Fokussierung in einer Front: alle Länder-Mittelpunkte
    (für die Richtungs-Navigation) + der projizierte Umriss des fokussierten
    Landes (Border zum Zeichnen). Geo-Logik in core/map/render.country_outlines.

    Query: cx,cy,zoom,cols,rows,aspect wie /api/map/base; zusätzlich
           focus = Name des fokussierten Landes (für dessen Umriss).
    NICHT KI-gegatet (Karte gibt es überall).
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 80))
        rows = int(a.get('rows', 30))
        aspect = float(a.get('aspect', 0.5))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    return jsonify(map_country_outlines(cx, cy, zoom, cols, rows, aspect,
                                        a.get('focus') or None))


@bp.route('/api/map/layers')
def api_map_layers():
    """
    Registry der thematischen Overlay-Layer (Achse 2): welche Layer es gibt,
    je mit ihren Sub-Layern, Quelle (Provenienz) und ob sie eine Zeitachse
    haben (Achse 3). Die Front baut daraus ihr Layer-Menü.
    NICHT KI-gegatet (Karte gibt es überall).
    """
    return jsonify({"layers": map_layers.registry()})


@bp.route('/api/map/layer/<layer_id>')
def api_map_layer(layer_id):
    """
    Features EINES Overlay-Layers für den Viewport der Front, fertig aufs
    Zellraster projiziert (gleiche viewport()-Mathematik wie /api/map/base, damit
    Overlay und Grundkarte passgenau sitzen). Trägt die Provenienz mit
    (source/vintage/retrieved_at) — für ein seriöses „wer sagt das, wann".

    Query: cx,cy,zoom,cols,rows,aspect wie /api/map/base; zusätzlich
           sub  = Sub-Layer (z.B. 'chokepoints'),
           at   = Zeitpunkt (Achse 3; Layer ohne Zeitachse ignorieren ihn).
    404 bei unbekanntem Layer. NICHT KI-gegatet.
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 120))
        rows = int(a.get('rows', 40))
        aspect = float(a.get('aspect', 0.5))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    sub = a.get('sub') or None
    at = a.get('at') or None
    out = map_layers.layer_features(layer_id, cx, cy, zoom, cols, rows,
                                    aspect=aspect, sub=sub, at=at)
    if out is None:
        return jsonify({"error": "unbekannter layer/sub-layer"}), 404
    return jsonify(out)
