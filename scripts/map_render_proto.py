#!/usr/bin/env python3
# scripts/map_render_proto.py
#
# Render-Stil-Prototyp für die Maps-TUI: vergleicht, wie eine Terminalkarte
# AUSSEHEN könnte, je nach Rasterisierung. Reines Dev-Werkzeug — kein curses,
# druckt nur nach stdout (Farben optional via ANSI). Damit lässt sich der Look
# durchprobieren, BEVOR wir den echten TUI-Renderer (tui/zentrale_tui.py)
# darauf umstellen. Hintergrund + die drei „Achsen": memory/maps/maps_system.md.
#
# Nutzt die echte Engine-Projektion (core/map/projection.py), damit die Vorschau
# 1:1 dem entspricht, was die TUI später zeichnet. Geometrie kommt aus den
# Natural-Earth-Daten unter core/map/data/.
#
# Stile:
#   baseline   – wie JETZT: dünner Umriss, 1 Glyph/Zelle (▓)        → "Pixelsuppe"
#   halfblock  – gefüllte Kontinente, Halbblöcke ▀▄█ (2× vertikal)  → Flächen, satt
#   braille    – Küsten-Umriss in Braille ⠿ (2×4 = 8× pro Zelle)    → feine Linien
#   braille-fill – gefülltes Land in Braille                        → massiv, körnig
#
# Beispiele:
#   venv/bin/python scripts/map_render_proto.py                 # alle Stile, Welt
#   venv/bin/python scripts/map_render_proto.py --style halfblock --color
#   venv/bin/python scripts/map_render_proto.py --style braille --cx 10 --cy 50 --zoom 3
#   venv/bin/python scripts/map_render_proto.py --cols 80 --rows 40

import os
import sys
import math
import json
import argparse

# core/ auffindbar machen, egal von wo aus gestartet (wie ui/app.py).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'core'))
from map.projection import lonlat_to_world  # noqa: E402

_DATA = os.path.join(_ROOT, 'core', 'map', 'data')

# ── ANSI-Farben (nur wenn --color). Land grün, Meer dunkelblau, Linien cyan. ──
RESET = "\033[0m"
FG_LAND = "\033[38;5;108m"   # Salbeigrün (wie der TUI-Akzent)
FG_LINE = "\033[38;5;45m"    # Cyan für Küsten/Linien
BG_SEA = "\033[48;5;17m"     # dunkles Blau als Meer-Hintergrund


def _iter_rings(geom, want_poly):
    """Geometrie → Punktlisten. want_poly: nur Polygon-Außenringe (Land) statt
    Linien (Küste). Löcher/Innenringe ignorieren wir im Prototyp bewusst."""
    t, c = geom['type'], geom['coordinates']
    if want_poly:
        if t == 'Polygon':
            yield c[0]
        elif t == 'MultiPolygon':
            for poly in c:
                yield poly[0]
    else:
        if t == 'LineString':
            yield c
        elif t == 'MultiLineString':
            for l in c:
                yield l


def _load(filename, want_poly):
    with open(os.path.join(_DATA, filename), 'r', encoding='utf-8') as f:
        d = json.load(f)
    return [r for feat in d['features'] for r in _iter_rings(feat['geometry'], want_poly)]


def _make_project(cx, cy, zoom, subw, subh, aspect):
    """lon/lat → Sub-Pixel-Koordinaten im subw×subh-Gitter (gleiche Mathe wie
    core/map/render.base_features). aspect = Zell-Breite/Höhe der Ziel-Subpixel."""
    span_x = min(1.0, 1.0 / (2.0 ** zoom))
    span_y = min(1.0, span_x * (subh / subw) / aspect)
    wcx, wcy = lonlat_to_world(cx, cy)
    x0, y0 = wcx - span_x / 2, wcy - span_y / 2
    sx, sy = subw / span_x, subh / span_y

    def proj(lon, lat):
        wx, wy = lonlat_to_world(lon, lat)
        return (wx - x0) * sx, (wy - y0) * sy
    return proj


def _bres(grid, W, H, x0, y0, x1, y1):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        if 0 <= x0 < W and 0 <= y0 < H:
            grid[y0][x0] = 1
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy; x0 += sx
        if e2 < dx:
            err += dx; y0 += sy


def _outline_bitmap(rings, W, H, proj):
    g = [[0] * W for _ in range(H)]
    for ring in rings:
        pts = [proj(lo, la) for lo, la in ring]
        for i in range(len(pts) - 1):
            _bres(g, W, H, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
    return g


def _fill_bitmap(rings, W, H, proj):
    """Scanline-Polygonfüllung: pro Zeile die Kanten-Schnittpunkte sammeln,
    sortieren, paarweise füllen. O(Zeilen × Kanten) — für 110m problemlos."""
    g = [[0] * W for _ in range(H)]
    for ring in rings:
        pts = [proj(lo, la) for lo, la in ring]
        n = len(pts)
        ys = [p[1] for p in pts]
        for y in range(max(0, int(min(ys))), min(H - 1, int(max(ys))) + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= yc < y1) or (y1 <= yc < y0):
                    xs.append(x0 + (yc - y0) / (y1 - y0) * (x1 - x0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                for x in range(max(0, int(math.ceil(xs[k] - 0.5))),
                               min(W - 1, int(math.floor(xs[k + 1] - 0.5))) + 1):
                    g[y][x] = 1
    return g


# Braille: 2×4 Punkte pro Zelle. Bit-Maske pro (dy, dx) nach Unicode-Standard.
_BRAILLE = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]


def _braille_from_bitmap(g, cols, rows, color=None):
    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            bits = 0
            for dy in range(4):
                for dx in range(2):
                    if g[r * 4 + dy][c * 2 + dx]:
                        bits |= _BRAILLE[dy][dx]
            line.append(chr(0x2800 + bits))
        row = "".join(line)
        out.append((color + row + RESET) if color else row)
    return "\n".join(out)


def render(style, cx, cy, zoom, cols, rows, color):
    coast = _load('ne_110m_coastline.geojson', False)
    land = _load('ne_110m_admin_0_countries.geojson', True)

    if style == 'baseline':
        g = _outline_bitmap(coast, cols, rows, _make_project(cx, cy, zoom, cols, rows, 0.5))
        lines = []
        for r in range(rows):
            row = "".join('▓' if g[r][c] else ' ' for c in range(cols))
            lines.append((FG_LINE + row + RESET) if color else row)
        return "\n".join(lines)

    if style == 'halfblock':
        W, H = cols, rows * 2
        proj = _make_project(cx, cy, zoom, W, H, 1.0)
        fill = _fill_bitmap(land, W, H, proj)
        if color:
            # DER Ziel-Look: jede Zelle ein '▀' (obere Hälfte = fg, untere = bg),
            # jede Hälfte einzeln eingefärbt → 2 gestapelte Vollfarb-Pixel pro
            # Zelle. Land grün, Meer dunkelblau, Küste hell drüber (eigenes
            # Bitmap in gleicher Auflösung). So sieht es in deinem Terminal aus —
            # die Plaintext-Tool-Ausgabe kann die Farbe nur nicht darstellen.
            coast_bm = _outline_bitmap(coast, W, H, proj)
            LAND_RGB, SEA_RGB, COAST_RGB = (95, 150, 90), (12, 26, 52), (140, 220, 210)

            def px(c, r):
                if coast_bm[r][c]:
                    return COAST_RGB
                return LAND_RGB if fill[r][c] else SEA_RGB

            lines = []
            for r in range(rows):
                cells = []
                for c in range(cols):
                    tr, tg, tb = px(c, 2 * r)
                    br, bg, bb = px(c, 2 * r + 1)
                    cells.append("\033[38;2;%d;%d;%dm\033[48;2;%d;%d;%dm▀"
                                 % (tr, tg, tb, br, bg, bb))
                lines.append("".join(cells) + RESET)
            return "\n".join(lines)
        # Mono-Fallback (ohne --color): ▀▄█ zeigt nur die Form.
        lines = []
        for r in range(rows):
            row = []
            for c in range(cols):
                top, bot = fill[2 * r][c], fill[2 * r + 1][c]
                row.append('█' if top and bot else '▀' if top else '▄' if bot else ' ')
            lines.append("".join(row))
        return "\n".join(lines)

    if style == 'braille':
        W, H = cols * 2, rows * 4
        g = _outline_bitmap(coast, W, H, _make_project(cx, cy, zoom, W, H, 1.0))
        return _braille_from_bitmap(g, cols, rows, FG_LINE if color else None)

    if style == 'braille-fill':
        W, H = cols * 2, rows * 4
        g = _fill_bitmap(land, W, H, _make_project(cx, cy, zoom, W, H, 1.0))
        return _braille_from_bitmap(g, cols, rows, FG_LAND if color else None)

    raise SystemExit("unbekannter stil: " + style)


def main():
    ap = argparse.ArgumentParser(description="Render-Stil-Prototyp für die Maps-TUI.")
    ap.add_argument('--style', default='all',
                    choices=['all', 'baseline', 'halfblock', 'braille', 'braille-fill'])
    ap.add_argument('--cx', type=float, default=0.0, help="Mittelpunkt Längengrad")
    ap.add_argument('--cy', type=float, default=12.0, help="Mittelpunkt Breitengrad")
    ap.add_argument('--zoom', type=float, default=0.0, help="0 = ganze Welt")
    ap.add_argument('--cols', type=int, default=57, help="Zeichenbreite (Default = reale Mid-Box)")
    ap.add_argument('--rows', type=int, default=30, help="Zeichenhöhe")
    ap.add_argument('--color', action='store_true', help="ANSI-Farben (Land grün, Meer blau)")
    a = ap.parse_args()

    styles = ['baseline', 'halfblock', 'braille', 'braille-fill'] if a.style == 'all' else [a.style]
    titles = {
        'baseline': 'A) JETZT: Umriss, 1 Glyph/Zelle (▓)',
        'halfblock': 'B) Halbblock-FÜLLUNG (▀▄█), 2× vertikal',
        'braille': 'C) BRAILLE-Umriss (⠿), 2×4 Subpixel',
        'braille-fill': 'D) BRAILLE-FÜLLUNG (Land massiv)',
    }
    for st in styles:
        print("\n" + "=" * 8 + " " + titles[st] + " " + "=" * 8)
        print(render(st, a.cx, a.cy, a.zoom, a.cols, a.rows, a.color))


if __name__ == '__main__':
    main()
