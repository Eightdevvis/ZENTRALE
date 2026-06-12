#!/usr/bin/env python3
# scripts/map_window.py
#
# Natives Karten-Fenster (pygame) — das "Wow"-Render-Ziel ohne Browser-Bloat.
# Kein curses, kein Browser: ein zweites X11-Fenster, das aus der TUI heraus
# aufklappen kann (wie /slide → zathura). Hier gibt es, was im Terminal nicht
# geht: echte antialiased Vektorgrafik, gefüllte Farbflächen, Meer-Verlauf,
# Land-Schlagschatten, Küsten-Glow, Vignette, zoom-adaptive Länder-Labels.
#
# Architektur bleibt das Kassetten-Prinzip: das Fenster ist ein DUMMER Renderer.
# Alle Geo-Mathematik (Mercator-Projektion, vorprojizierte Geometrie + Label-
# Anker) lebt in core/map/ und wird 1:1 wiederverwendet. Dieses File zeichnet
# nur, es rechnet keine Geographie.
#
# Steuerung:
#   Maus ziehen / Pfeiltasten   Pan
#   Mausrad / + -               Zoom (Rad zoomt auf den Cursor)
#   0                           Reset auf Weltansicht
#   g                           Gradnetz an/aus
#   l                           Länder-Labels an/aus
#   t                           Handelsrouten-Overlay an/aus (Chokepoints)
#   ?                           Shortcut-Legende ein/aus
#   Esc / q                     schließen
#
# Start:
#   venv/bin/python scripts/map_window.py
#   venv/bin/python scripts/map_window.py --cx 10 --cy 50 --zoom 3

import os
import sys
import math
import argparse

# core/ auffindbar machen, egal von wo gestartet (wie ui/app.py & der Prototyp).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'core'))

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from pygame import gfxdraw  # noqa: E402

from map.projection import lonlat_to_world, world_to_lonlat  # noqa: E402
from map import basemap  # noqa: E402

# ── Palette ("Control-Room": tiefes Meer, Salbei-Land, leuchtende Küste) ─────
SEA_TOP    = (8, 18, 34)       # Tiefsee oben
SEA_BOTTOM = (14, 36, 60)      # heller unten → subtiler Tiefen-Verlauf
LAND       = (78, 107, 71)     # Salbeigrün (Landfläche)
LAND_EDGE  = (104, 138, 96)    # hellere Landkante (Licht von oben)
SHADOW     = (4, 11, 22)       # Schlagschatten unter Land (dunkler als Meer)
COAST      = (130, 222, 212)   # leuchtendes Mint: Küstenlinie
COAST_GLOW = (40, 96, 104)     # weicher Schimmer unter der Küste
GRAT       = (40, 58, 80)      # Gradnetz, dezent
GRAT_AXIS  = (60, 86, 112)     # Äquator + Nullmeridian etwas heller
LABEL_FG   = (236, 246, 242)   # Länder-Label (Hover), helles Mint-Weiß
HUD_FG     = (150, 182, 176)
HUD_BG     = (10, 20, 34)
TRADE_DOT  = (255, 178, 72)     # Chokepoint-Marker (Bernstein, kontrastiert Mint)
TRADE_RING = (255, 226, 180)    # heller Rand des Markers
TRADE_FG   = (255, 232, 196)    # Chokepoint-Label
LEG_FG     = (196, 214, 210)    # Legenden-Text
LEG_KEY    = (130, 222, 212)    # Legenden-Taste (Mint, wie Küste)
LEG_BG     = (10, 20, 34)       # Legenden-Hintergrund

# Shortcut-Legende (oben rechts, Taste '?' blendet sie um). EINE Quelle der
# Wahrheit fürs Fenster — neue Shortcuts ab jetzt HIER als Zeile ergänzen, dann
# tauchen sie automatisch in der Legende auf.
LEGEND = [
    ("Ziehen / ↑↓←→", "Pan"),
    ("Rad / + −",     "Zoom"),
    ("0",             "Weltansicht"),
    ("g",             "Gradnetz"),
    ("l",             "Länder-Labels"),
    ("t",             "Handelsrouten"),
    ("?",             "Legende ein/aus"),
    ("Esc / q",       "schließen"),
]

SHADOW_OFF = (3, 4)            # Schlagschatten-Versatz in Pixeln (SO-Licht)

# Koordinaten vor dem Zeichnen begrenzen: bei starkem Zoom projizieren weit
# entfernte Polygon-Punkte auf riesige Pixelwerte → das kann pygames C-Renderer
# überlaufen. Auf einen großzügigen Rahmen klemmen (außerhalb sieht man eh nix).
_CLAMP = 30000


def _clampf(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class MapView:
    """Hält den Viewport (Mittelpunkt in Welt-Koordinaten + Zoom) und projiziert
    Welt-[0,1]²-Punkte auf Fenster-Pixel. Aspect = 1.0 (quadratische Pixel),
    daher unverzerrt ohne den 2:1-Trick, den die TUI braucht."""

    # Easing-Tempo: kleiner = weicher/träger, größer = knackiger. Gilt für Zoom
    # UND Mittelpunkt, damit sich beides gleich anfühlt.
    EASE_K = 7.0

    def __init__(self, w, h, cx_lon, cy_lat, zoom):
        self.w, self.h = w, h
        wcx, wcy = lonlat_to_world(cx_lon, cy_lat)
        self.cx, self.cy = wcx, wcy          # AKTUELLER Mittelpunkt (animiert)
        self.tcx, self.tcy = wcx, wcy        # ZIEL-Mittelpunkt
        self.zoom = float(zoom)              # aktueller Zoom (animiert)
        self.tzoom = float(zoom)             # Ziel-Zoom

    def resize(self, w, h):
        self.w, self.h = w, h

    def _span(self, zoom):
        sx = min(1.0, 1.0 / (2.0 ** zoom))
        return sx, sx * (self.h / self.w)

    @property
    def span_x(self):
        return self._span(self.zoom)[0]

    @property
    def span_y(self):
        return self._span(self.zoom)[1]

    def _view(self):
        sx, sy = self._span(self.zoom)
        return self.cx - sx / 2.0, self.cy - sy / 2.0, sx, sy

    def to_screen(self, wx, wy):
        x0, y0, sx, sy = self._view()
        px = (wx - x0) / sx * self.w
        py = (wy - y0) / sy * self.h
        return _clampf(px, -_CLAMP, _CLAMP), _clampf(py, -_CLAMP, _CLAMP)

    def screen_to_world(self, px, py):
        x0, y0, sx, sy = self._view()
        return x0 + px / self.w * sx, y0 + py / self.h * sy

    def visible(self, minx, miny, maxx, maxy):
        x0, y0, sx, sy = self._view()
        return not (maxx < x0 or minx > x0 + sx or maxy < y0 or miny > y0 + sy)

    def _clamp_pt(self, cx, cy, zoom):
        """Mittelpunkt so halten, dass die Weltkarte nicht ganz rausläuft."""
        sx, sy = self._span(zoom)
        cx = _clampf(cx, -sx / 2.0, 1.0 + sx / 2.0)
        cy = _clampf(cy, sy / 2.0, 1.0 - sy / 2.0) if sy < 1.0 else 0.5
        return cx, cy

    def pan_pixels(self, dx, dy):
        """Maus-Ziehen: 1:1, OHNE Easing — Ziel = Ist, damit es direkt klebt."""
        self.tcx -= dx / self.w * self.span_x
        self.tcy -= dy / self.h * self.span_y
        self.tcx, self.tcy = self._clamp_pt(self.tcx, self.tcy, self.tzoom)
        self.cx, self.cy = self.tcx, self.tcy

    def pan_target(self, fx, fy):
        """Pfeiltasten: nur das ZIEL verschieben (Bruchteil der sichtbaren
        Spanne) — update() gleitet weich hin. Auto-Repeat akkumuliert → flüssig."""
        sx, sy = self._span(self.tzoom)
        self.tcx, self.tcy = self._clamp_pt(self.tcx + fx * sx,
                                            self.tcy + fy * sy, self.tzoom)

    def zoom_to(self, px, py, dz):
        """Ziel-Zoom + Ziel-Mittelpunkt so setzen, dass der Welt-Punkt unter dem
        Cursor (px,py) am Ende wieder dort liegt (Zoom „auf den Cursor"). Die
        Bewegung selbst easet in update() — weich statt sprunghaft."""
        wx, wy = self.screen_to_world(px, py)
        self.tzoom = _clampf(self.tzoom + dz, 0.0, 12.0)
        sx, sy = self._span(self.tzoom)
        self.tcx = wx - (px / self.w - 0.5) * sx
        self.tcy = wy - (py / self.h - 0.5) * sy
        self.tcx, self.tcy = self._clamp_pt(self.tcx, self.tcy, self.tzoom)

    def update(self, dt):
        """Zoom + Mittelpunkt pro Frame Richtung Ziel easen (zeit-basiert,
        framerate-stabil). Schnappt bei winziger Restdifferenz ein."""
        ease = 1.0 - math.exp(-dt * self.EASE_K)
        self.zoom += (self.tzoom - self.zoom) * ease
        self.cx += (self.tcx - self.cx) * ease
        self.cy += (self.tcy - self.cy) * ease
        if abs(self.tzoom - self.zoom) < 1e-4:
            self.zoom = self.tzoom
        if abs(self.tcx - self.cx) < 1e-6 and abs(self.tcy - self.cy) < 1e-6:
            self.cx, self.cy = self.tcx, self.tcy


def _sea_gradient(w, h):
    """Vertikaler Meer-Verlauf als vorgerenderte Fläche (einmal pro Resize)."""
    col = pygame.Surface((1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        col.set_at((0, y), tuple(int(a + (b - a) * t)
                                 for a, b in zip(SEA_TOP, SEA_BOTTOM)))
    return pygame.transform.scale(col, (w, h))


def _vignette(w, h):
    """Weiche Rand-Abdunklung (Alpha-Fläche). Klein berechnet + glatt skaliert."""
    s = 96
    small = pygame.Surface((s, s), pygame.SRCALPHA)
    cx, cy = (s - 1) / 2.0, (s - 1) / 2.0
    maxd = math.hypot(cx, cy)
    for yy in range(s):
        for xx in range(s):
            d = math.hypot(xx - cx, yy - cy) / maxd
            a = _clampf((d - 0.55) / 0.45, 0.0, 1.0) ** 1.7
            small.set_at((xx, yy), (0, 0, 6, int(a * 165)))
    return pygame.transform.smoothscale(small, (w, h))


def _draw_graticule(screen, view):
    """Längen-/Breitenlinien alle 30°; Äquator + Nullmeridian etwas heller."""
    x0, y0, sx, sy = view._view()
    for lon in range(-150, 181, 30):
        wx, _ = lonlat_to_world(lon, 0)
        px = (wx - x0) / sx * view.w
        if 0 <= px <= view.w:
            pygame.draw.line(screen, GRAT_AXIS if lon == 0 else GRAT,
                             (px, 0), (px, view.h))
    for lat in range(-60, 61, 30):
        _, wy = lonlat_to_world(0, lat)
        py = (wy - y0) / sy * view.h
        if 0 <= py <= view.h:
            pygame.draw.line(screen, GRAT_AXIS if lat == 0 else GRAT,
                             (0, py), (view.w, py))


# Geometrie pro LOD-Stufe als numpy-Arrays (einmalig gebaut, dann gecacht). Die
# basemap (core/, stdlib-only) liefert Punktlisten; hier konvertieren wir sie zu
# Nx2-Float-Arrays, damit die Projektion pro Frame VEKTORISIERT läuft — sonst
# wären 10m-Polygone (>500k Punkte) in reinem Python Sekunden pro Frame.
_GEOM = {}


def _get_geom(level):
    g = _GEOM.get(level)
    if g is not None:
        return g
    countries = []
    for c in basemap.countries(level):
        rings = [np.asarray(pts, dtype=np.float64) for (_, _, _, _, pts) in c['rings']]
        countries.append({'name': c['name'], 'lx': c['lx'], 'ly': c['ly'],
                          'bbox': c['bbox'], 'rings': rings})
    coast = [((mnx, mny, mxx, mxy), np.asarray(pts, dtype=np.float64))
             for (mnx, mny, mxx, mxy, pts) in basemap.coastline(level)]
    g = {'countries': countries, 'coast': coast}
    _GEOM[level] = g
    return g


def _project(view, ring):
    """Nx2-Welt-Array → Bildschirm-Pixel (int), vektorisiert + vereinfacht:
    aufeinanderfolgende Punkte auf derselben Pixel-Zelle fallen weg. Kappt die
    Zeichenlast auf ~Bildschirmauflösung, unabhängig von der Quell-Detailtiefe."""
    x0, y0, sx, sy = view._view()
    px = np.clip((ring[:, 0] - x0) / sx * view.w, -_CLAMP, _CLAMP)
    py = np.clip((ring[:, 1] - y0) / sy * view.h, -_CLAMP, _CLAMP)
    pts = np.empty((len(ring), 2), dtype=np.int32)
    pts[:, 0] = px
    pts[:, 1] = py
    if len(pts) > 1:
        keep = np.empty(len(pts), dtype=bool)
        keep[0] = True
        keep[1:] = np.any(pts[1:] != pts[:-1], axis=1)
        pts = pts[keep]
    return pts


def _ix(a, b, ax, val):
    """Schnittpunkt der Strecke a→b mit der Achsen-parallelen Linie coord[ax]=val."""
    da = b[ax] - a[ax]
    t = 0.0 if da == 0 else (val - a[ax]) / da
    x = val if ax == 0 else int(round(a[0] + (b[0] - a[0]) * t))
    y = val if ax == 1 else int(round(a[1] + (b[1] - a[1]) * t))
    return [x, y]


def _clip_poly(poly, xmin, ymin, xmax, ymax):
    """Sutherland-Hodgman: Polygon auf das Rechteck clippen. ENTSCHEIDEND für
    Performance — sonst rastert filled_polygon eines teils weit off-screen
    liegenden Riesen-Polygons (geklemmte Koordinaten) zehntausende Scanlines.
    Nach dem Clip deckt das Polygon nur noch ~die sichtbaren Zeilen ab."""
    def _clip(poly, inside, inter):
        out = []
        n = len(poly)
        for i in range(n):
            a = poly[i]
            b = poly[(i + 1) % n]
            ia, ib = inside(a), inside(b)
            if ia:
                out.append(a)
                if not ib:
                    out.append(inter(a, b))
            elif ib:
                out.append(inter(a, b))
        return out
    poly = _clip(poly, lambda p: p[0] >= xmin, lambda a, b: _ix(a, b, 0, xmin))
    if poly:
        poly = _clip(poly, lambda p: p[0] <= xmax, lambda a, b: _ix(a, b, 0, xmax))
    if poly:
        poly = _clip(poly, lambda p: p[1] >= ymin, lambda a, b: _ix(a, b, 1, ymin))
    if poly:
        poly = _clip(poly, lambda p: p[1] <= ymax, lambda a, b: _ix(a, b, 1, ymax))
    return poly


def _draw_land(screen, view, countries):
    """Land in drei Schichten: Schlagschatten (versetzt, dunkel), Füllung,
    helle Kante. Gibt das Gefühl, dass die Kontinente über dem Meer schweben.
    Ringe pro Frame: vektorisiert projizieren+vereinfachen (_project), dann aufs
    Sichtfenster clippen (_clip_poly) — sonst werden Riesen-Polygone unbezahlbar."""
    ox, oy = SHADOW_OFF
    w, h = view.w, view.h
    polys = []
    for c in countries:
        if not view.visible(*c['bbox']):
            continue
        for ring in c['rings']:
            pts = _project(view, ring)
            if len(pts) < 3:
                continue
            mn = pts.min(axis=0)
            mx = pts.max(axis=0)
            if mn[0] >= -8 and mn[1] >= -8 and mx[0] <= w + 8 and mx[1] <= h + 8:
                polys.append(pts.tolist())            # ganz sichtbar → kein Clip nötig
            else:
                clipped = _clip_poly(pts.tolist(), -8, -8, w + 8, h + 8)
                if len(clipped) >= 3:
                    polys.append(clipped)
    # 1) Schlagschatten ZUERST (versetzt), damit die Füllung darüber liegt.
    for p in polys:
        gfxdraw.filled_polygon(screen, [(x + ox, y + oy) for (x, y) in p], SHADOW)
    # 2) Füllung + 3) helle Kante.
    for p in polys:
        gfxdraw.filled_polygon(screen, p, LAND)
        gfxdraw.aapolygon(screen, p, LAND_EDGE)


def _draw_coast(screen, view, lines):
    """Küste mit Glow: erst breiter, weicher Schimmer, dann scharfe helle Linie.
    Punkte vektorisiert projiziert+vereinfacht (siehe _project)."""
    for (bbox, ring) in lines:
        if not view.visible(*bbox):
            continue
        pts = _project(view, ring)
        if len(pts) < 2:
            continue
        lst = pts.tolist()
        pygame.draw.lines(screen, COAST_GLOW, False, lst, 4)   # weicher Untergrund
        pygame.draw.aalines(screen, COAST, False, lst)         # scharfe Linie


def _point_in_ring(px, py, ring):
    """Punkt-in-Polygon (Even-Odd-Ray-Cast), vektorisiert. ring: Nx2-Welt-Array."""
    x = ring[:, 0]
    y = ring[:, 1]
    x2 = np.roll(x, -1)
    y2 = np.roll(y, -1)
    cond = (y > py) != (y2 > py)
    denom = np.where(y2 != y, y2 - y, 1.0)
    xint = (x2 - x) * (py - y) / denom + x
    return int(np.count_nonzero(cond & (px < xint))) % 2 == 1


def _draw_hover_label(screen, view, countries, fonts, cache, mouse):
    """Nur den Namen des Landes UNTER dem Mauszeiger zeigen (Hover). Sucht per
    Bounding-Box-Vorfilter + Punkt-in-Polygon, zeichnet einen einzelnen Namen
    ohne Schatten am Label-Anker des Landes (bzw. am Cursor, falls der außerhalb
    liegt)."""
    mx, my = mouse
    wx, wy = view.screen_to_world(mx, my)
    hit = None
    for c in countries:
        minx, miny, maxx, maxy = c['bbox']
        if not (minx <= wx <= maxx and miny <= wy <= maxy):
            continue
        if any(_point_in_ring(wx, wy, ring) for ring in c['rings']):
            hit = c
            break
    if hit is None:
        return

    font = fonts[0]
    surf = cache.get(hit['name'])
    if surf is None:
        surf = font.render(hit['name'], True, LABEL_FG)
        cache[hit['name']] = surf
    px, py = view.to_screen(hit['lx'], hit['ly'])
    if not (0 <= px <= view.w and 0 <= py <= view.h):
        px, py = mx, my - 18                              # Anker raus → am Cursor
    w, h = surf.get_size()
    screen.blit(surf, (int(px - w / 2), int(py - h / 2)))


# ── Handelsrouten-Overlay (Achse 2, Sub-Layer Chokepoints / IMF PortWatch) ───
# Das Fenster liest core/map/layers DIREKT (wie die Basiskarte), nicht über die
# API — Sandkasten-Stil fürs schnelle Look-Iterieren. portwatch.chokepoints()
# liefert aus dem lokalen Cache (offline-zuerst); Provenienz/Stand kommen mit.
_TRADE = None


def _get_trade():
    """Chokepoints einmal laden + cachen (Welt-Koords + heutiger Verkehr).
    Gibt {'items':[...], 'vintage':..., 'source':...} oder leere Items zurück."""
    global _TRADE
    if _TRADE is not None:
        return _TRADE
    items, vintage, source = [], None, None
    try:
        from map.layers import portwatch  # noqa: E402
        data = portwatch.chokepoints()
        if data:
            vintage = data.get('vintage')
            source = (data.get('source') or {}).get('name')
            for it in data.get('items', []):
                items.append({'wx': it['wx'], 'wy': it['wy'],
                              'name': it['name'],
                              'val': (it.get('today') or {}).get('total')})
    except Exception:
        pass
    _TRADE = {'items': items, 'vintage': vintage, 'source': source}
    return _TRADE


def _draw_trade(screen, view, font, mouse):
    """Chokepoints als leuchtende Bernstein-Marker, Radius ~√(Schiffe heute).
    Halo + Kern + heller Ring; der dem Cursor nächste bekommt Name + Wert."""
    td = _get_trade()
    mx, my = mouse
    near, nd = None, 1e18
    for it in td['items']:
        if not view.visible(it['wx'], it['wy'], it['wx'], it['wy']):
            continue
        px, py = int(view.to_screen(it['wx'], it['wy'])[0]), \
            int(view.to_screen(it['wx'], it['wy'])[1])
        val = it['val'] or 0
        r = max(4, min(26, int(4 + math.sqrt(val) * 0.7)))
        gfxdraw.filled_circle(screen, px, py, r + 4, (255, 160, 50, 55))  # Halo
        gfxdraw.filled_circle(screen, px, py, r, TRADE_DOT)
        gfxdraw.aacircle(screen, px, py, r, TRADE_RING)
        d = (px - mx) ** 2 + (py - my) ** 2
        if d < nd:
            nd, near = d, (it, px, py, r)
    if near is not None and nd < 70 ** 2:
        it, px, py, r = near
        label = "%s  %s" % (it['name'], '—' if it['val'] is None else it['val'])
        surf = font.render(label, True, TRADE_FG)
        screen.blit(surf, (px + r + 4, py - surf.get_height() // 2))


def _draw_trade_caption(screen, font, view):
    """Kleine Quellen-/Stand-Zeile oben links — Provenienz sichtbar (seriös)."""
    td = _get_trade()
    if not td['items']:
        txt = "◆ Handelsrouten — keine Daten (PortWatch-Cache leer)"
    else:
        txt = "◆ Chokepoints · %s · Stand %s" % (
            td['source'] or 'IMF PortWatch', td['vintage'] or '?')
    label = font.render(txt, True, TRADE_FG)
    pad = 6
    bg = pygame.Surface((label.get_width() + 2 * pad, label.get_height() + 2 * pad))
    bg.set_alpha(150)
    bg.fill(HUD_BG)
    screen.blit(bg, (10, 10))
    screen.blit(label, (10 + pad, 10 + pad))


def _draw_legend(screen, font, win_w):
    """Kleine Shortcut-Legende oben rechts (zweispaltig: Taste | Bedeutung).
    Quelle ist die LEGEND-Liste — Zeilen dort ergänzen reicht."""
    pad, gap, lh = 8, 14, font.get_height() + 2
    key_w = max(font.size(k)[0] for k, _ in LEGEND)
    lab_w = max(font.size(v)[0] for _, v in LEGEND)
    bw = pad * 2 + key_w + gap + lab_w
    bh = pad * 2 + lh * len(LEGEND)
    x0, y0 = win_w - bw - 10, 10
    bg = pygame.Surface((bw, bh))
    bg.set_alpha(165)
    bg.fill(LEG_BG)
    screen.blit(bg, (x0, y0))
    for i, (k, v) in enumerate(LEGEND):
        y = y0 + pad + i * lh
        screen.blit(font.render(k, True, LEG_KEY), (x0 + pad, y))
        screen.blit(font.render(v, True, LEG_FG), (x0 + pad + key_w + gap, y))


def _draw_hud(screen, font, view, level=''):
    lon, lat = world_to_lonlat(view.cx, view.cy)
    txt = "lon %.2f  lat %.2f   zoom %.1f   lod %s" % (lon, lat, view.zoom, level)
    label = font.render(txt, True, HUD_FG)
    pad = 6
    bg = pygame.Surface((label.get_width() + 2 * pad, label.get_height() + 2 * pad))
    bg.set_alpha(180)
    bg.fill(HUD_BG)
    screen.blit(bg, (10, view.h - bg.get_height() - 10))
    screen.blit(label, (10 + pad, view.h - label.get_height() - 10 - pad))


def main():
    ap = argparse.ArgumentParser(description="Natives Karten-Fenster (pygame).")
    ap.add_argument('--cx', type=float, default=10.0, help="Start-Längengrad")
    ap.add_argument('--cy', type=float, default=30.0, help="Start-Breitengrad")
    ap.add_argument('--zoom', type=float, default=0.0, help="0 = ganze Welt")
    ap.add_argument('--w', type=int, default=1100, help="Fensterbreite")
    ap.add_argument('--h', type=int, default=720, help="Fensterhöhe")
    a = ap.parse_args()

    pygame.init()
    pygame.display.set_caption("ZENTRALE — Karte")
    screen = pygame.display.set_mode((a.w, a.h), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    hud_font = pygame.font.SysFont("monospace", 15)
    legend_font = pygame.font.SysFont("monospace", 13)
    label_fonts = (pygame.font.SysFont("sans", 17, bold=True),
                   pygame.font.SysFont("sans", 13))
    label_cache = {}

    view = MapView(a.w, a.h, a.cx, a.cy, a.zoom)
    sea = _sea_gradient(a.w, a.h)
    vig = _vignette(a.w, a.h)
    show_grat = True
    show_labels = True
    show_trade = False               # Handelsrouten-Overlay (Taste 't')
    show_legend = True               # Shortcut-Legende oben rechts (Taste '?')

    dragging = False
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((ev.w, ev.h), pygame.RESIZABLE)
                view.resize(ev.w, ev.h)
                sea = _sea_gradient(ev.w, ev.h)
                vig = _vignette(ev.w, ev.h)
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.key == pygame.K_0:
                    view.tzoom = 0.0       # weich zurück zur Weltansicht
                    wx, wy = lonlat_to_world(10.0, 30.0)
                    view.tcx, view.tcy = view._clamp_pt(wx, wy, 0.0)
                elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    view.zoom_to(view.w / 2, view.h / 2, +0.6)
                elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    view.zoom_to(view.w / 2, view.h / 2, -0.6)
                elif ev.key == pygame.K_g:
                    show_grat = not show_grat
                elif ev.key == pygame.K_l:
                    show_labels = not show_labels
                elif ev.key == pygame.K_t:
                    show_trade = not show_trade
                elif ev.unicode == '?':
                    show_legend = not show_legend
                elif ev.key == pygame.K_LEFT:
                    view.pan_target(-0.2, 0)
                elif ev.key == pygame.K_RIGHT:
                    view.pan_target(+0.2, 0)
                elif ev.key == pygame.K_UP:
                    view.pan_target(0, -0.2)
                elif ev.key == pygame.K_DOWN:
                    view.pan_target(0, +0.2)
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    dragging = True
                elif ev.button == 4:
                    view.zoom_to(*ev.pos, +0.5)
                elif ev.button == 5:
                    view.zoom_to(*ev.pos, -0.5)
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    dragging = False
            elif ev.type == pygame.MOUSEMOTION and dragging:
                view.pan_pixels(ev.rel[0], ev.rel[1])

        view.update(dt)                      # sanftes Zoom-Easing pro Frame

        # Achse 1 / LOD: Detailstufe nach Zoom wählen. basemap cacht pro Stufe,
        # der Aufruf ist also nach dem Erstladen nur ein Dict-Lookup. (Beim
        # ersten Überschreiten einer Schwelle lädt die feinere Datei einmalig —
        # ein kurzer Frame-Hänger, danach flüssig.)
        level = basemap.lod_for_zoom(view.zoom)
        geom = _get_geom(level)

        screen.blit(sea, (0, 0))
        if show_grat:
            _draw_graticule(screen, view)
        _draw_land(screen, view, geom['countries'])
        _draw_coast(screen, view, geom['coast'])
        screen.blit(vig, (0, 0))
        if show_labels:
            _draw_hover_label(screen, view, geom['countries'], label_fonts,
                              label_cache, pygame.mouse.get_pos())
        if show_trade:
            _draw_trade(screen, view, label_fonts[1], pygame.mouse.get_pos())
            _draw_trade_caption(screen, hud_font, view)
        _draw_hud(screen, hud_font, view, level)
        if show_legend:
            _draw_legend(screen, legend_font, view.w)
        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    main()
