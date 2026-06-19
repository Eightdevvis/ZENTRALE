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


def project_polyline(vp, pts):
    """Eine Polylinie (Welt-Koords [(wx,wy),…]) aufs Zellraster eines viewport()
    projizieren + vereinfachen (aufeinanderfolgende Punkte derselben Zelle
    zusammenfassen). Für Overlay-Linien (z.B. Schifffahrtsrouten). Gibt
    [[col,row],…] zurück; Clipping macht der Renderer beim Zeichnen."""
    out = []
    last = None
    for wx, wy in pts:
        col = (wx - vp["x0"]) * vp["sx"]
        row = (wy - vp["y0"]) * vp["sy"]
        cell = (int(col), int(row))
        if cell == last:
            continue
        last = cell
        out.append([round(col, 2), round(row, 2)])
    return out


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


def country_outlines(cx, cy, zoom, cols, rows, aspect=0.5, focus=None):
    """Länder-Daten für die Auswahl in einer Front (front-agnostisch):

      • `countries`: ALLE Länder mit Mittelpunkt in Welt-Koords [0,1]²
        (`wx,wy`) + lon/lat + Name — die Front navigiert damit richtungsbasiert
        (Alt+Pfeile → räumlich nächstes Land), unabhängig vom Viewport.
      • `focus`: das fokussierte Land, dessen Umriss als DÜNNE Braille-Linie ins
        aktuelle Zellraster rasterisiert ist (`braille` = [[col,row,char],…], nur
        Rand-Zellen — deckungsgleich mit der Braille-Füllung) plus Label-Zelle —
        die Front malt die Rand-Zeichen nur eingefärbt (z.B. weiß) + den Namen.

    LOD wie die Braille-Basis (lod_for_zoom), damit der Umriss zum gefüllten
    Land passt. Die Geo-Mathematik bleibt hier; die Front zeichnet/navigiert nur.
    """
    vp = viewport(cx, cy, zoom, cols, rows, aspect)
    cs = basemap.countries(basemap.lod_for_zoom(vp["zoom"]))
    centers = []
    for c in cs:
        lon, lat = world_to_lonlat(c["lx"], c["ly"])
        # wx/wy: visuelle Richtungswahl (Bildschirm-oben = kleineres wy);
        # lon/lat: Kamera-Ziel der Front (die macht KEINE Projektion selbst).
        centers.append({"name": c["name"], "wx": round(c["lx"], 6),
                        "wy": round(c["ly"], 6), "lon": round(lon, 4),
                        "lat": round(lat, 4)})
    foc = None
    if focus:
        m = next((c for c in cs if c["name"] == focus), None)
        if m is not None:
            # Umriss als BRAILLE-Subpixel rasterisieren (2×4 Punkte/Zelle, gleiche
            # Viewport-Mathematik wie die Braille-Füllung → deckungsgleich), damit
            # die Front eine dünne Linie aus Braille-Punkten zeichnen kann statt
            # fetter Vollzeichen. Rückgabe: [[col,row,char], …] (nur Rand-Zellen).
            braille = _braille_outline(vp, [pts for (_, _, _, _, pts) in m["rings"]],
                                       cols, rows)
            lc = [round((m["lx"] - vp["x0"]) * vp["sx"], 2),
                  round((m["ly"] - vp["y0"]) * vp["sy"], 2)]
            foc = {"name": m["name"], "braille": braille, "label": lc,
                   "onscreen": 0 <= lc[0] <= cols and 0 <= lc[1] <= rows}
    return {
        "center": [vp["cx"], vp["cy"]], "zoom": vp["zoom"],
        "cols": cols, "rows": rows,
        "countries": centers, "focus": foc,
    }


# Braille-Punktmuster: 2×4 Punkte pro Zelle, Bit-Maske nach Unicode-Standard.
_BRAILLE = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]


def _braille_outline(vp, rings_world, cols, rows):
    """Polylinien (Welt-Koords) als DÜNNE Braille-Linie in ein cols*2 × rows*4
    Subpixel-Raster zeichnen (Bresenham), pro Zelle zum Braille-Zeichen packen.
    Subpixel-x = Zell-x·2, Subpixel-y = Zell-y·4 (gleiche viewport()-Skalen wie
    die Füllung → deckungsgleich). Rückgabe: [[col,row,char], …], nur Rand-Zellen.
    """
    W, H = cols * 2, rows * 4
    sx2, sy4 = vp["sx"] * 2.0, vp["sy"] * 4.0
    cells = {}

    def setpix(px, py):
        if 0 <= px < W and 0 <= py < H:
            cells[(px // 2, py // 4)] = (cells.get((px // 2, py // 4), 0)
                                         | _BRAILLE[py % 4][px % 2])

    def _clampi(v, lo, hi):
        return lo if v < lo else hi if v > hi else v

    for pts in rings_world:
        prev = None
        for (wx, wy) in pts:
            # Auf einen großzügigen Rand clampen: hält Bresenham-Läufe bounded,
            # ohne den sichtbaren Linienverlauf (0..W/0..H) zu verändern.
            px = _clampi(int((wx - vp["x0"]) * sx2), -W, 2 * W)
            py = _clampi(int((wy - vp["y0"]) * sy4), -H, 2 * H)
            if prev is not None:
                ax, ay = prev
                ddx, ddy = abs(px - ax), abs(py - ay)
                stepx = 1 if ax < px else -1
                stepy = 1 if ay < py else -1
                err = ddx - ddy
                # Frühes Cullen, wenn die ganze Strecke weit außerhalb liegt
                # (sonst läuft Bresenham bei starkem Zoom über riesige Distanzen).
                if not (max(ax, px) < 0 or min(ax, px) > W
                        or max(ay, py) < 0 or min(ay, py) > H):
                    while True:
                        setpix(ax, ay)
                        if ax == px and ay == py:
                            break
                        e2 = 2 * err
                        if e2 > -ddy:
                            err -= ddy; ax += stepx
                        if e2 < ddx:
                            err += ddx; ay += stepy
            prev = (px, py)
    return [[c, r, chr(0x2800 + mask)] for (c, r), mask in cells.items()]


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
