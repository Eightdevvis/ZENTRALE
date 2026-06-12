# core/map/layers/ — thematische Overlay-Layer (Achse 2)
#
# Registry analog zu core/graphs.py: jeder Overlay ist ein reiner Daten-Provider
# auf demselben Geo-Substrat (Projektion/Viewport aus core/map/). Die Fronten
# holen Features über /api/map/layer/<id> und zeichnen nur (Kassetten-Prinzip).
#
# Architektur-Detail (siehe memory/maps_system.md, memory/maps_quellen.md):
# ein Overlay kann ein KOMPOSIT aus mehreren Sub-Layern sein, jeder Sub-Layer
# mit EINER offiziellen Quelle + mitgeführter Provenienz.

from . import trade

# id -> Layer-Modul (jedes hat META + features()).
_LAYERS = {
    "trade": trade,
}


def registry():
    """Liste aller Overlay-Layer mit Meta (für /api/map/layers): welche Layer,
    je mit Sub-Layern, Quelle und ob zeitfähig (Achse 3)."""
    return [m.META for m in _LAYERS.values()]


def layer_features(layer_id, cx, cy, zoom, cols, rows, aspect=0.5,
                   sub=None, at=None):
    """Features eines Overlays (projiziert aufs Zellraster) oder None bei
    unbekanntem Layer. Dispatch an das jeweilige Layer-Modul."""
    m = _LAYERS.get(layer_id)
    if m is None:
        return None
    return m.features(cx, cy, zoom, cols, rows, aspect=aspect, sub=sub, at=at)
