# core/map/layers/borders.py
#
# Quelle für den Sub-Layer „borders" des politischen Overlays (Achse 2):
# umstrittene / abtrünnige Gebiete („die Claims" — Kaschmir, Aksai Chin,
# Westjordanland, Krim, Westsahara …). Das ist der politische Mehrwert über die
# reine Basiskarte hinaus: die Basiskarte (basemap.py) zeichnet die anerkannten
# Ländergrenzen; DIESER Layer zeichnet, was umstritten ist.
#
# Institution: Natural Earth (https://www.naturalearthdata.com), Datei
# `ne_10m_admin_0_disputed_areas` — gemeinfrei (Public Domain), wie die übrigen
# Natural-Earth-Basisdaten. `commit_ok = True` → die GeoJSON liegt COMMITTET in
# core/map/data/ (statisch, kein Live-Fetch, kein Cache nötig).
#
# Bewusst nur numpy-frei/stdlib (json + Projektion) — passt zur Offline-/Lean-
# Philosophie und lädt genauso wie basemap.py (vorprojiziert + Bounding-Box).

import os
import json

from ..projection import lonlat_to_world

# Provenienz — hängt an jeder Antwort.
SOURCE = {
    "name": "Natural Earth — Disputed Areas (1:10m)",
    "url": "https://www.naturalearthdata.com",
    "license": "Public Domain",
    "license_url": "https://www.naturalearthdata.com/about/terms-of-use/",
    "attribution": "Made with Natural Earth",
    "commit_ok": True,       # gemeinfrei → committet in core/map/data/
}

# Datenstand: Natural-Earth-Release (statisch), kein Tagesbezug.
VINTAGE = "Natural Earth 1:10m"

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_FILE = os.path.join(_DATA_DIR, "ne_10m_admin_0_disputed_areas.geojson")

_CACHE = None


def _iter_rings(geom):
    """Geometrie → einzelne Ring-Punktlisten (wie basemap._iter_parts, aber nur
    Polygon/MultiPolygon — disputed areas sind Flächen)."""
    t = geom.get("type")
    c = geom.get("coordinates") or []
    if t == "Polygon":
        yield from c
    elif t == "MultiPolygon":
        for poly in c:
            yield from poly


def load():
    """Umstrittene Gebiete als vorprojizierte Ringe (einmal geladen, dann gecacht).

    Rückgabe-dict:
      rings : Liste von (minx, miny, maxx, maxy, [(wx,wy),…], name, cla)
              — Welt-Koordinaten + Bounding-Box (fürs Clipping) + Beschriftung.
      source, vintage : Provenienz.
    Oder None, wenn die GeoJSON fehlt (graceful — Layer liefert dann „keine
    Daten", analog density ohne Ingest)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE or None
    if not os.path.exists(_FILE):
        _CACHE = False
        return None
    with open(_FILE, "r", encoding="utf-8") as f:
        gj = json.load(f)

    rings = []
    for feat in gj.get("features", []):
        props = feat.get("properties") or {}
        name = props.get("BRK_NAME") or props.get("NAME") or props.get("NAME_LONG")
        cla = props.get("featurecla")
        for part in _iter_rings(feat.get("geometry") or {}):
            pts = [lonlat_to_world(lon, lat) for lon, lat in part]
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            rings.append((min(xs), min(ys), max(xs), max(ys), pts, name, cla))

    _CACHE = {"rings": rings, "source": SOURCE, "vintage": VINTAGE}
    return _CACHE
