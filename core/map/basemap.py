# core/map/basemap.py
#
# Lädt die statischen Basiskarten-Vektordaten (Natural Earth, gemeinfrei) aus
# core/map/data/ und hält sie als vorprojizierte Polylinien im Speicher.
#
# „Vorprojiziert" heißt: jeder lon/lat-Punkt wird EINMAL beim Laden nach
# Welt-Koordinaten [0,1]² umgerechnet (Mercator). Pro Anfrage muss dann nur
# noch linear auf das Zellraster skaliert werden — kein wiederholtes
# Trigonometrie-Rechnen. Zusätzlich cachen wir pro Linie ihre Bounding-Box,
# damit render.py beim Clipping ganze Linien außerhalb des Sichtfensters
# sofort verwerfen kann.
#
# Achse 1 (Detailtiefe/LOD): aktuell nur die 1:110m-Stufe (grob, ~5k Punkte).
# Feinere Stufen (1:50m / 1:10m, später OSM) kommen als weitere Dateien dazu
# und werden je nach Zoom gewählt — die Lade-/Cache-Mechanik hier bleibt gleich.

import os
import json

from .projection import lonlat_to_world

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# Cache: schlüssel ('coast_50m' etc.) -> Liste von Linien/Ringen. Jeder Eintrag:
#   (minx, miny, maxx, maxy, [(wx, wy), ...])   alles in Welt-Koordinaten.
_CACHE = {}

# Achse 1 (Detailgrad / Level-of-Detail). Drei Natural-Earth-Stufen liegen unter
# data/: 110m (grob), 50m (mittel), 10m (fein). Pro Stufe eine Datei je Thema.
COAST_FILES = {
    '110m': 'ne_110m_coastline.geojson',
    '50m':  'ne_50m_coastline.geojson',
    '10m':  'ne_10m_coastline.geojson',
}
COUNTRY_FILES = {
    '110m': 'ne_110m_admin_0_countries.geojson',
    '50m':  'ne_50m_admin_0_countries.geojson',
    '10m':  'ne_10m_admin_0_countries.geojson',
}

# Welche Stufe bei welchem Zoom. Schwellen bewusst konservativ: erst bei echtem
# Reinzoomen die teureren Daten laden. (zoom 0 = ganze Welt, +1 = halbe Breite.)
def lod_for_zoom(zoom):
    if zoom < 2.0:
        return '110m'
    if zoom < 4.5:
        return '50m'
    return '10m'


def _iter_parts(geom):
    """Geometrie → einzelne Punkt-Listen (Linien/Ringe), egal welcher GeoJSON-Typ.
    So behandeln wir LineString/MultiLineString (Küsten) und – für spätere
    Layer – Polygon/MultiPolygon (Grenzen) mit demselben Code."""
    t = geom.get('type')
    c = geom.get('coordinates') or []
    if t == 'LineString':
        yield c
    elif t == 'MultiLineString':
        yield from c
    elif t == 'Polygon':
        yield from c                      # jeder Ring (außen + Löcher)
    elif t == 'MultiPolygon':
        for poly in c:
            yield from poly


def _load(filename):
    """GeoJSON laden und in vorprojizierte Linien mit Bounding-Box umwandeln."""
    path = os.path.join(_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        gj = json.load(f)
    lines = []
    for feat in gj.get('features', []):
        for part in _iter_parts(feat.get('geometry') or {}):
            pts = [lonlat_to_world(lon, lat) for lon, lat in part]
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            lines.append((min(xs), min(ys), max(xs), max(ys), pts))
    return lines


def coastline(level='110m'):
    """Küstenlinien in der gewählten LOD-Stufe ('110m'|'50m'|'10m'). Lazy +
    gecacht pro Stufe. Default 110m hält den bestehenden TUI-Pfad unverändert."""
    key = 'coast_' + level
    if key not in _CACHE:
        _CACHE[key] = _load(COAST_FILES[level])
    return _CACHE[key]


def _iter_exterior(geom):
    """Nur die AUSSEN-Ringe der Polygone (für gefülltes Land). Löcher
    (Innenringe) lassen wir weg: bei 1:110m sind das praktisch keine Seen,
    und Enklaven sind eh Land — so wird die Füllung einfach die Vereinigung
    aller Landflächen."""
    t = geom.get('type')
    c = geom.get('coordinates') or []
    if t == 'Polygon':
        if c:
            yield c[0]
    elif t == 'MultiPolygon':
        for poly in c:
            if poly:
                yield poly[0]


def _load_polys(filename):
    """Wie _load, aber Polygon-Außenringe (geschlossene Flächen) statt Linien."""
    path = os.path.join(_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        gj = json.load(f)
    polys = []
    for feat in gj.get('features', []):
        for ring in _iter_exterior(feat.get('geometry') or {}):
            pts = [lonlat_to_world(lon, lat) for lon, lat in ring]
            if len(pts) < 3:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            polys.append((min(xs), min(ys), max(xs), max(ys), pts))
    return polys


def land(level='110m'):
    """Landflächen (Polygone, für die gefüllte Karte) in der LOD-Stufe.
    Lazy + gecacht pro Stufe."""
    key = 'land_' + level
    if key not in _CACHE:
        _CACHE[key] = _load_polys(COUNTRY_FILES[level])
    return _CACHE[key]


def _load_countries(filename):
    """Wie _load_polys, aber Ringe PRO LAND gruppiert + Metadaten (Name, Label-
    Anker, Einwohner). So kann eine Front gefüllte Länder zeichnen UND beschriften
    aus derselben Quelle. Name englisch (NAME), Anker aus den von
    Natural Earth mitgelieferten LABEL_X/LABEL_Y (auf Welt-Koordinaten projiziert).
    Jedes Land:
      {name, lx, ly (Welt-Koords des Labels), pop,
       bbox:(minx,miny,maxx,maxy), rings:[(minx,miny,maxx,maxy,pts), ...]}"""
    path = os.path.join(_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        gj = json.load(f)
    out = []
    for feat in gj.get('features', []):
        props = feat.get('properties') or {}
        rings = []
        for ring in _iter_exterior(feat.get('geometry') or {}):
            pts = [lonlat_to_world(lon, lat) for lon, lat in ring]
            if len(pts) < 3:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            rings.append((min(xs), min(ys), max(xs), max(ys), pts))
        if not rings:
            continue
        lon = props.get('LABEL_X')
        lat = props.get('LABEL_Y')
        if lon is None or lat is None:
            continue
        lx, ly = lonlat_to_world(lon, lat)
        out.append({
            'name': props.get('NAME') or props.get('NAME_LONG') or '?',
            'lx': lx, 'ly': ly,
            'pop': props.get('POP_EST') or 0,
            'bbox': (min(r[0] for r in rings), min(r[1] for r in rings),
                     max(r[2] for r in rings), max(r[3] for r in rings)),
            'rings': rings,
        })
    return out


def countries(level='110m'):
    """Länder in der LOD-Stufe: Polygone PRO Land + Name/Label-Anker (für
    Beschriftung). Lazy + gecacht pro Stufe. Siehe _load_countries."""
    key = 'countries_' + level
    if key not in _CACHE:
        _CACHE[key] = _load_countries(COUNTRY_FILES[level])
    return _CACHE[key]
