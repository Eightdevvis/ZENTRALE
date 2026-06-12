# core/map/render.py
#
# Der /api/map/base-Kern: nimmt den Viewport, den eine Front beschreibt
# (Mittelpunkt lon/lat, Zoom, Zielraster cols×rows, Zell-Seitenverhältnis),
# und liefert die Basiskarten-Linien fertig auf dieses Raster projiziert
# zurück. Die Front (TUI/SVG) zeichnet die Zellkoordinaten nur noch — alle
# Geo-Mathematik (Mercator, Clipping, Skalierung) passiert hier, EINMAL.
#
# Warum das Raster vom Client kommt: ein TUI-Zeichen ist ~doppelt so hoch wie
# breit (aspect ≈ 0.5), ein SVG-Pixel quadratisch (aspect = 1.0). Indem die
# Front ihr cols/rows/aspect mitschickt, bleibt diese Engine front-agnostisch
# und liefert jeder Front ein unverzerrtes Bild.

import math

from .projection import lonlat_to_world, world_to_lonlat
from . import basemap


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def viewport(cx, cy, zoom, cols, rows, aspect=0.5):
    """Sicht-Geometrie für einen Viewport — EINMAL berechnet, von Basiskarte
    UND Overlay-Layern geteilt. So projizieren Grundkarte und thematische Layer
    garantiert aufs identische Zellraster (sonst „schwimmen" Overlays).

    Liefert ein dict mit:
      cx,cy,zoom,cols,rows         — normalisierte Eingaben
      x0,y0,x1,y1                  — sichtbarer Welt-Ausschnitt [0,1]²
      sx,sy                        — Welt→Zelle-Skalierung
      west,south,east,north        — Sicht-Bounds in lon/lat (für Pan der Front)
    """
    cols = max(8, int(cols))
    rows = max(4, int(rows))
    aspect = float(aspect) or 0.5
    zoom = max(0.0, float(zoom))
    cx = _clamp(float(cx), -180.0, 180.0)
    cy = _clamp(float(cy), -85.05, 85.05)

    span_x = min(1.0, 1.0 / (2.0 ** zoom))
    span_y = min(1.0, span_x * (rows / cols) / aspect)

    wcx, wcy = lonlat_to_world(cx, cy)
    x0, x1 = wcx - span_x / 2.0, wcx + span_x / 2.0
    y0, y1 = wcy - span_y / 2.0, wcy + span_y / 2.0
    west, north = world_to_lonlat(x0, y0)
    east, south = world_to_lonlat(x1, y1)

    return {
        "cx": cx, "cy": cy, "zoom": zoom, "cols": cols, "rows": rows,
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "sx": cols / span_x, "sy": rows / span_y,
        "west": west, "south": south, "east": east, "north": north,
    }


def base_features(cx, cy, zoom, cols, rows, aspect=0.5):
    """
    Basiskarten-Linien für einen Viewport, projiziert aufs Zellraster.

    Eingabe:
      cx, cy : Mittelpunkt in lon/lat (Grad)
      zoom   : ≥0; je +1 halbiert sich die sichtbare Weltbreite (slippy-Semantik)
      cols,rows : Zielraster der Front (Zeichen-/Pixel-Gitter)
      aspect : Zell-Breite/Höhe (TUI ≈ 0.5, SVG = 1.0) — gegen Verzerrung

    Ausgabe (JSON-fähig):
      {
        "center": [cx, cy], "zoom": z,
        "bounds": [west, south, east, north],   # für Pan-Schrittweite der Front
        "cols": cols, "rows": rows,
        "lines": [ [[col,row], [col,row], ...], ... ]   # Zellkoordinaten (float)
      }
    """
    cols = max(8, int(cols))
    rows = max(4, int(rows))
    aspect = float(aspect) or 0.5
    zoom = max(0.0, float(zoom))
    cx = _clamp(float(cx), -180.0, 180.0)
    cy = _clamp(float(cy), -85.05, 85.05)

    # Sichtbarer Welt-Ausschnitt. span_x = Bruchteil der Weltbreite (slippy:
    # 1/2^zoom). span_y so wählen, dass Geographie unverzerrt erscheint —
    # weil Zellen nicht quadratisch sind, geht das Seitenverhältnis ein:
    #   span_y = span_x · (rows/cols) / aspect
    span_x = min(1.0, 1.0 / (2.0 ** zoom))
    span_y = min(1.0, span_x * (rows / cols) / aspect)

    wcx, wcy = lonlat_to_world(cx, cy)
    x0, x1 = wcx - span_x / 2.0, wcx + span_x / 2.0
    y0, y1 = wcy - span_y / 2.0, wcy + span_y / 2.0

    # Sicht-Bounds in lon/lat zurückgeben: die Front rechnet daraus ihre
    # Pan-Schrittweite (sie selbst macht KEINE Projektion). y0=oben=Norden.
    west, north = world_to_lonlat(x0, y0)
    east, south = world_to_lonlat(x1, y1)

    sx = cols / span_x          # Welt→Zelle, Skalierungsfaktoren
    sy = rows / span_y

    lines = []
    for (minx, miny, maxx, maxy, pts) in basemap.coastline():
        # Ganze Linie verwerfen, wenn ihre Bounding-Box den Viewport nicht
        # berührt (billiges Vor-Clipping; Restüberhang clippt der Renderer).
        if maxx < x0 or minx > x1 or maxy < y0 or miny > y1:
            continue
        out = []
        last_cell = None
        for (wx, wy) in pts:
            col = (wx - x0) * sx
            row = (wy - y0) * sy
            # Punkte vereinfachen: aufeinanderfolgende, die auf dieselbe Zelle
            # fallen, zusammenfassen (kürzt Payload + Zeichenarbeit deutlich,
            # gerade bei kleinem Zoom). Endpunkte bleiben erhalten.
            cell = (int(col), int(row))
            if cell == last_cell:
                continue
            last_cell = cell
            out.append([round(col, 2), round(row, 2)])
        if len(out) >= 2:
            lines.append(out)

    return {
        "center": [cx, cy],
        "zoom": zoom,
        "bounds": [west, south, east, north],
        "cols": cols,
        "rows": rows,
        "lines": lines,
    }


# Braille-Punktmuster: 2×4 Punkte pro Zelle, Bit-Maske nach Unicode-Standard.
_BRAILLE = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]


def base_braille(cx, cy, zoom, cols, rows):
    """Basiskarte als GEFÜLLTES Land in Braille (Stil „kleine Punkte als
    Füllung"). Liefert fertige Braille-Zeilen, die eine Terminal-Front nur noch
    druckt — die Front bleibt dumm. Auflösung: 2×4 Subpixel pro Zelle, also ein
    cols*2 × rows*4 Bitmap, in das die Landpolygone per Scanline gefüllt werden.
    Subpixel sind ~quadratisch (Zelle ist ~2:1), daher aspect=1.0.

    Rückgabe: wie base_features, aber "braille": [zeilen-string, ...] statt lines."""
    cols = max(8, int(cols))
    rows = max(4, int(rows))
    zoom = max(0.0, float(zoom))
    cx = _clamp(float(cx), -180.0, 180.0)
    cy = _clamp(float(cy), -85.05, 85.05)

    W, H = cols * 2, rows * 4
    span_x = min(1.0, 1.0 / (2.0 ** zoom))
    span_y = min(1.0, span_x * (H / W))      # aspect 1.0 (Subpixel quadratisch)

    wcx, wcy = lonlat_to_world(cx, cy)
    x0, y0 = wcx - span_x / 2.0, wcy - span_y / 2.0
    x1, y1 = x0 + span_x, y0 + span_y
    west, north = world_to_lonlat(x0, y0)
    east, south = world_to_lonlat(x1, y1)
    sx, sy = W / span_x, H / span_y

    grid = [bytearray(W) for _ in range(H)]
    for (minx, miny, maxx, maxy, pts) in basemap.land():
        if maxx < x0 or minx > x1 or maxy < y0 or miny > y1:
            continue
        scr = [((wx - x0) * sx, (wy - y0) * sy) for (wx, wy) in pts]
        n = len(scr)
        ys = [p[1] for p in scr]
        for y in range(max(0, int(min(ys))), min(H - 1, int(max(ys))) + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                ax, ay = scr[i]
                bx, by = scr[(i + 1) % n]
                if (ay <= yc < by) or (by <= yc < ay):
                    xs.append(ax + (yc - ay) / (by - ay) * (bx - ax))
            xs.sort()
            row = grid[y]
            for k in range(0, len(xs) - 1, 2):
                xa = max(0, int(math.ceil(xs[k] - 0.5)))
                xb = min(W - 1, int(math.floor(xs[k + 1] - 0.5)))
                for x in range(xa, xb + 1):
                    row[x] = 1

    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            bits = 0
            base = c * 2
            for dy in range(4):
                gr = grid[r * 4 + dy]
                if gr[base]:
                    bits |= _BRAILLE[dy][0]
                if gr[base + 1]:
                    bits |= _BRAILLE[dy][1]
            line.append(chr(0x2800 + bits))
        out.append("".join(line))

    return {
        "center": [cx, cy],
        "zoom": zoom,
        "bounds": [west, south, east, north],
        "cols": cols,
        "rows": rows,
        "braille": out,
    }
