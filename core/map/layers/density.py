# core/map/layers/density.py
#
# Sub-Layer „Verkehrsdichte" (gemessen) des Handelsrouten-Overlays.
# Quelle: World Bank Data Catalog „Global Shipping Traffic Density" (Dataset
# 0037580) — entstanden aus IMFs eigener AIS-Analyse (Cerdeiro, Komaromi, Liu,
# Saeed 2020). Also dieselbe institutionelle Linie wie die Chokepoints, nur das
# GEMESSENE Produkt: ein Dichte-Raster aus stündlichen AIS-Positionen 2015–2021.
#
# WICHTIG — anders als PortWatch ist DAS hier CC BY 4.0 (commit_ok = True):
#   • Die Originaldatei ist ein globaler 0,005°-GeoTIFF (~10 GB entpackt) → viel
#     zu groß fürs Repo. Darum macht scripts/ingest_shipdensity.py EINMAL auf
#     dem PC einen kleinen abgeleiteten Auszug: heruntergerechnet auf ein grobes
#     Gitter, log-skaliert auf uint8, als .npz abgelegt — wenige MB.
#   • Dieses kleine .npz liegt COMMITTET in core/map/data/ (mit Namensnennung),
#     nicht im gitignore'ten cache/. Es ist statisch (Aggregat 2015–2021), muss
#     also nie „frisch gehalten" werden — Tagesaktualität sitzt in den
#     Chokepoints (siehe portwatch.py / maps_quellen.md, A/B-Trennung).
#   • Das Raster bleibt in seiner NATIVEN Projektion (Plattkarte, lat/lon
#     linear). Die Mercator-Umrechnung passiert erst beim Zeichnen — so geht
#     keine Auflösung durch doppeltes Resampling verloren.

import os
import numpy as np

# Provenienz — hängt an jeder Antwort.
SOURCE = {
    "name": "World Bank / IMF — Global Shipping Traffic Density",
    "url": "https://datacatalog.worldbank.org/search/dataset/0037580",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "attribution": "World Bank / IMF (Cerdeiro, Komaromi, Liu, Saeed 2020)",
    "commit_ok": True,        # CC BY 4.0 → darf (mit Namensnennung) ins Repo
}

# Datenstand der Messung — statisches Aggregat, kein Tagesbezug.
VINTAGE = "2015–2021"

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
# Default- Name; scripts/ingest_shipdensity.py schreibt genau hierhin.
_FILE = os.path.join(_DATA_DIR, "shipdensity_density_0p05.npz")

META = {"id": "density", "name": "Verkehrsdichte (gemessen)", "kind": "raster",
        "time": False, "source": SOURCE}

_CACHE = None


def load():
    """Committetes Dichteraster laden (einmal, dann gecacht).

    Rückgabe-dict:
      grid     : uint8 (H, W) — log-skalierte Dichte, Plattkarte (lat/lon linear)
      lon_min/lon_max/lat_min/lat_max : geografische Ausdehnung des Rasters
      vlog_min/vlog_max : log-Grenzen, mit denen uint8 ↔ ~Roh-Dichte rückrechenbar
      vintage, source   : Provenienz
    Oder None, wenn das .npz fehlt (Ingest noch nicht gelaufen →
    `python scripts/ingest_shipdensity.py`)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE or None
    if not os.path.exists(_FILE):
        _CACHE = False
        return None
    z = np.load(_FILE)
    _CACHE = {
        "grid": z["grid"],
        "lon_min": float(z["lon_min"]), "lon_max": float(z["lon_max"]),
        "lat_min": float(z["lat_min"]), "lat_max": float(z["lat_max"]),
        "vlog_min": float(z["vlog_min"]), "vlog_max": float(z["vlog_max"]),
        "vintage": VINTAGE, "source": SOURCE,
    }
    return _CACHE
