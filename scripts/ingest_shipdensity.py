#!/usr/bin/env python3
# scripts/ingest_shipdensity.py
#
# EINMALIGER Ingest des World-Bank/IMF-Dichterasters „Global Shipping Traffic
# Density" → kleines, committbares .npz für core/map/layers/density.py.
#
# WARUM separat / einmalig:
#   • Die Quelle ist ein globaler 0,005°-GeoTIFF (~534 MB gezippt, ~10 GB
#     entpackt im RAM) — viel zu groß fürs Repo und für die Laufzeit.
#   • CC BY 4.0 → das ABGELEITETE kleine Raster darf (mit Namensnennung) ins Git.
#   • Läuft auf dem PC (braucht Netz + RAM), NICHT in der abgeschotteten
#     Build-Umgebung. Danach liegt ein paar-MB-.npz committet vor und jede
#     Maschine (auch der Pi) hat die Dichte offline.
#
# Abhängigkeit NUR hier (nicht zur Laufzeit):  pip install tifffile
#   (optional schneller bei COG-Overviews; sonst wird die Vollauflösung gelesen)
#
# Aufruf:
#   # a) Datei schon lokal (zip von Zenodo entpackt):
#   python scripts/ingest_shipdensity.py --tif /pfad/shipdensity_global.tif
#   # b) automatisch von Zenodo holen + entpacken + ingestieren:
#   python scripts/ingest_shipdensity.py --download
#   # feiner/gröber:
#   python scripts/ingest_shipdensity.py --tif ... --res 0.05
#
# Ergebnis:  core/map/data/shipdensity_density_0p05.npz   (committen!)

import os
import sys
import argparse
import tempfile
import zipfile
import urllib.request

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT_DIR = os.path.join(_ROOT, "core", "map", "data")

_ZENODO = "https://zenodo.org/records/16894236/files/shipdensity_global.zip?download=1"


def _download(dest_dir):
    """Zenodo-Zip holen + den GeoTIFF entpacken. Gibt den .tif-Pfad zurück."""
    zip_path = os.path.join(dest_dir, "shipdensity_global.zip")
    print("Lade %s …" % _ZENODO)
    req = urllib.request.Request(_ZENODO, headers={"User-Agent": "ZENTRALE-maps/1"})
    with urllib.request.urlopen(req) as r, open(zip_path, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total:
                print("\r  %5.1f %%" % (100 * got / total), end="", flush=True)
        print()
    print("Entpacke …")
    with zipfile.ZipFile(zip_path) as z:
        tifs = [n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))]
        if not tifs:
            sys.exit("Kein .tif im Zip gefunden: %s" % z.namelist())
        z.extract(tifs[0], dest_dir)
        return os.path.join(dest_dir, tifs[0])


def _geo_extent(page, shape):
    """Geografische Ausdehnung (lon_min..lon_max, lat_min..lat_max) aus den
    GeoTIFF-Tags lesen (ModelPixelScale 33550 + ModelTiepoint 33922). Fällt auf
    die bekannte World-Bank-Ausdehnung -180..180 / -85..85 zurück, falls Tags
    fehlen — dann eine WARNUNG, damit man es prüft."""
    h, w = shape[:2]
    tags = {t.code: t.value for t in page.tags}
    scale = tags.get(33550)         # (sx, sy, sz) Grad/Pixel
    tie = tags.get(33922)           # (i, j, k, X, Y, Z) Pixel(0,0) → Welt
    if scale and tie:
        sx, sy = float(scale[0]), float(scale[1])
        x0, y0 = float(tie[3]), float(tie[4])     # obere-linke Ecke (lon, lat)
        lon_min, lon_max = x0, x0 + sx * w
        lat_max, lat_min = y0, y0 - sy * h        # y wächst nach unten
        return lon_min, lon_max, lat_min, lat_max
    print("  WARNUNG: keine GeoTIFF-Georeferenz-Tags — nehme -180..180 / "
          "-85..85 an. BITTE PRÜFEN, ob das Bild wirklich so ausgedehnt ist.")
    return -180.0, 180.0, -85.0, 85.0


def _block_mean(a, fy, fx):
    """Ganzzahlig blockweise mitteln (fy×fx Zellen → 1). Rand wird abgeschnitten."""
    h, w = a.shape
    h2, w2 = (h // fy) * fy, (w // fx) * fx
    a = a[:h2, :w2].reshape(h2 // fy, fy, w2 // fx, fx)
    return a.mean(axis=(1, 3))


def _stream_block_mean(src, full_h, full_w, fy, fx, strip_src_rows=400):
    """Wie _block_mean, aber OHNE das Vollraster je komplett in den RAM zu ziehen.

    `src` ist ein lazy indexierbares 2D-Array (zarr-View über den GeoTIFF oder
    numpy-memmap): `src[y0:y1, :]` liest NUR diese Zeilen von der Platte. Wir
    gehen in horizontalen Streifen durch, rechnen jeden Streifen sofort auf
    fy×fx herunter und sammeln nur das kleine Ergebnis. Peak-RAM = ein Streifen
    (~strip_src_rows·full_w·4 B) + das Ergebnisgitter — statt der vollen ~20 GB.
    """
    out_h, out_w = full_h // fy, full_w // fx
    acc = np.zeros((out_h, out_w), dtype=np.float32)
    strip = max(fy, (strip_src_rows // fy) * fy)   # Streifenhöhe = Vielfaches von fy
    oy = 0
    last = -1
    for y0 in range(0, out_h * fy, strip):
        y1 = min(y0 + strip, out_h * fy)
        blk = np.asarray(src[y0:y1, :out_w * fx], dtype=np.float32)
        blk = np.where(blk < 0, 0.0, blk)          # Nodata/Negative → 0
        bh = (y1 - y0) // fy
        blk = blk.reshape(bh, fy, out_w, fx).mean(axis=(1, 3))
        acc[oy:oy + bh] = blk
        oy += bh
        pct = 100 * y1 // (out_h * fy)
        if pct != last:                            # schlichter Fortschritt
            print("\r  streame … %3d %%" % pct, end="", flush=True)
            last = pct
    print()
    return acc


def main():
    ap = argparse.ArgumentParser(description="World-Bank-Dichteraster → kleines .npz")
    ap.add_argument("--tif", help="Pfad zum entpackten shipdensity_global.tif")
    ap.add_argument("--download", action="store_true",
                    help="Zenodo-Zip selbst holen + entpacken")
    ap.add_argument("--res", type=float, default=0.05,
                    help="Ziel-Zellgröße in Grad (Default 0.05°)")
    ap.add_argument("--out", default=None, help="Ausgabe-.npz (Default automatisch)")
    a = ap.parse_args()

    try:
        import tifffile
    except ImportError:
        sys.exit("Bitte einmalig:  pip install tifffile")

    tmp = tempfile.mkdtemp(prefix="shipdensity_")
    tif = a.tif or (_download(tmp) if a.download else None)
    if not tif:
        sys.exit("Entweder --tif PFAD oder --download angeben.")

    # RAM-Deckel: oberhalb davon NICHT das Vollraster laden, sondern streamen.
    # Das Vollbild (72000×36000) wäre als float64 ~21 GB — das sprengt selbst
    # einen 16-GB-PC. Unterhalb des Deckels ist Direktladen schneller/einfacher.
    DIRECT_LOAD_MAX_BYTES = 1_200_000_000   # ~1,2 GB float64-Vollladung

    print("Lese %s …" % tif)
    with tifffile.TiffFile(tif) as t:
        series = t.series[0]
        page = series.pages[0]
        full_h, full_w = series.shape[:2]
        src_res = 360.0 / full_w
        print("  Vollauflösung: %d×%d  (~%.4f°/Zelle)" % (full_w, full_h, src_res))

        # COG-Overviews nutzen: kleinste Ebene wählen, die noch feiner als das
        # Ziel ist → spart RAM massiv, ohne unter die Zielauflösung zu fallen.
        target_w = int(round(360.0 / a.res))
        chosen = series
        levels = getattr(series, "levels", None) or [series]
        for lvl in levels:
            lw = lvl.shape[1]
            if lw >= target_w and lw < chosen.shape[1]:
                chosen = lvl
        if chosen is not series:
            print("  nutze Overview-Ebene %d×%d (statt Vollbild)"
                  % (chosen.shape[1], chosen.shape[0]))

        ch_h, ch_w = chosen.shape[:2]
        fx = max(1, int(round((target_w and ch_w / target_w) or 1)))
        fy = fx
        lon_min, lon_max, lat_min, lat_max = _geo_extent(page, (full_h, full_w))

        est = ch_h * ch_w * 8
        if est <= DIRECT_LOAD_MAX_BYTES:
            # Klein genug (z.B. Overview-Ebene) → in einem Rutsch laden.
            arr = np.asarray(chosen.asarray(), dtype=np.float64)
            arr = np.where(arr < 0, 0.0, arr)
            grid = _block_mean(arr, fy, fx) if fx > 1 else arr
            del arr
        else:
            # Zu groß fürs RAM → streifenweise von der Platte lesen.
            print("  Vollladung wäre ~%.1f GB → streame stattdessen "
                  "(Peak ein paar 100 MB)." % (est / 1e9))
            try:
                import zarr  # noqa: F401
                store = chosen.aszarr()
                src = zarr.open(store, mode="r")
            except ImportError:
                sys.exit("Für das Streaming des Vollrasters einmalig:  "
                         "%s -m pip install zarr" % os.path.basename(sys.executable))
            grid = _stream_block_mean(src, ch_h, ch_w, fy, fx)
    print("  heruntergerechnet auf %d×%d" % (grid.shape[1], grid.shape[0]))

    # Log-Skala (Dichte ist extrem schief: 1 … zig Millionen), dann auf uint8.
    g = np.log1p(grid)
    vlog_min, vlog_max = float(g.min()), float(g.max())
    if vlog_max <= vlog_min:
        vlog_max = vlog_min + 1.0
    u8 = np.clip((g - vlog_min) / (vlog_max - vlog_min) * 255.0, 0, 255).astype(np.uint8)

    out = a.out or os.path.join(_OUT_DIR, "shipdensity_density_0p05.npz")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    np.savez_compressed(out, grid=u8,
                        lon_min=lon_min, lon_max=lon_max,
                        lat_min=lat_min, lat_max=lat_max,
                        vlog_min=vlog_min, vlog_max=vlog_max)
    mb = os.path.getsize(out) / 1e6
    print("Geschrieben: %s  (%d×%d uint8, %.1f MB komprimiert)"
          % (out, u8.shape[1], u8.shape[0], mb))
    print("Ausdehnung: lon %.2f..%.2f  lat %.2f..%.2f" % (lon_min, lon_max, lat_min, lat_max))
    print("→ committen (CC BY 4.0, Namensnennung World Bank/IMF).")


if __name__ == "__main__":
    main()
