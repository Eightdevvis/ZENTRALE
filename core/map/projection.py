# core/map/projection.py
#
# Web-Mercator-Projektion (EPSG:3857), normalisiert auf den Einheitsraum
# [0,1]×[0,1]. Das ist DASSELBE Schema, das Google Maps / OpenStreetMap nutzen
# (slippy z/x/y), nur ohne die Kachel-Multiplikation — wir halten die Welt als
# Quadrat [0,1]² und skalieren später linear auf das jeweilige Front-Raster.
#
#   x = 0   → 180° West,  x = 1   → 180° Ost
#   y = 0   → Nordrand (+85.05°),  y = 1 → Südrand (−85.05°)
#
# Warum normalisiert statt Pixel: die Mercator-Mathematik (der nicht-lineare
# Breitengrad-Teil) lebt damit EINMAL hier; die Fronten machen nur noch eine
# triviale lineare Abbildung Welt→Zelle. So bleibt der Renderer dumm.
#
# Die Pol-Kappen jenseits ±85.05° fallen weg — das ist die Standard-Mercator-
# Grenze (sonst liefe y gegen ±∞).

import math

# Grenz-Breitengrad, bei dem die Mercator-Welt quadratisch wird (±85.0511°).
MAX_LAT = 85.05112878


def lonlat_to_world(lon, lat):
    """(lon, lat) in Grad → (x, y) im normalisierten Mercator-Raum [0,1]²."""
    x = (lon + 180.0) / 360.0
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    s = math.sin(math.radians(lat))
    # y wächst nach SÜDEN (Bildschirm-Konvention: oben = Norden = y klein).
    y = 0.5 - math.log((1.0 + s) / (1.0 - s)) / (4.0 * math.pi)
    return x, y


def world_to_lonlat(x, y):
    """(x, y) im normalisierten Mercator-Raum [0,1]² → (lon, lat) in Grad."""
    lon = x * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y
    lat = math.degrees(math.atan(math.sinh(n)))
    return lon, lat
