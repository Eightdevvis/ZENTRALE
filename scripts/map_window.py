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
#   Maus ziehen / Pfeiltasten   Pan (horizontal endlos — Welt als Band)
#   Mausrad / + -               Zoom (Rad zoomt auf den Cursor)
#   0                           Reset auf Weltansicht
#   g                           Gradnetz an/aus
#   l                           Länder-Labels an/aus
#   h                           Handelsrouten-Overlay an/aus (Routen + Chokepoints)
#   d                           Verkehrsdichte-Heatmap an/aus (gemessen, World Bank/IMF)
#   p                           Politik/Konflikt-Overlay an/aus (Kontrolle + Ereignisse + Grenzen)
#   t                           Zeit-Schrittweite zyklieren (Woche→Monat→Jahr→10/50/100 J.)
#   , / .                       Achse 3 — Zeit: einen Schritt zurück / vor (gedrückt halten geht)
#   ;                           Achse 3 — zurück auf „jetzt" (jüngster Stand)
#   ?                           Glossar-Such-Modal (Begriffe nachschlagen)
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

from datetime import date, timedelta  # noqa: E402  (Achse-3-Zeit-Scrubber)

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from pygame import gfxdraw  # noqa: E402

from map.projection import lonlat_to_world, world_to_lonlat  # noqa: E402
from map import basemap  # noqa: E402
import glossary  # noqa: E402  (core/glossary.py — Begriffs-Erklärungen fürs ?-Modal)

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
ROUTE_COL  = (92, 138, 156)     # Schifffahrtsrouten-Linien (gedämpftes Stahlblau)
DENS_FG    = (214, 184, 236)    # Verkehrsdichte-Caption (weiches Violett, wie Ramp)
# Politik/Konflikt-Overlay (Achse 2): Kontroll-Punkte nach Status, Ereignisse,
# umstrittene Grenzen. Farben bewusst außerhalb der Handels-Palette (Mint/Bernstein).
CTRL_UA    = (96, 210, 140)     # Kontrolle Ukraine (Grün)
CTRL_RU    = (232, 96, 168)     # Kontrolle Russland (Magenta)
CTRL_CONT  = (240, 190, 80)     # umstritten/unklar (Bernsteingelb)
EVENT_DOT  = (244, 108, 92)     # Konfliktereignis (UCDP) — warmes Rot
EVENT_RING = (255, 196, 180)    # heller Rand des Ereignis-Markers
BORDER_COL = (200, 120, 150)    # umstrittene Grenzlinie (gedämpftes Rosa)
POL_FG     = (232, 176, 200)    # Politik-Caption
LEG_FG     = (196, 214, 210)    # Legenden-Text
LEG_KEY    = (130, 222, 212)    # Legenden-Taste (Mint, wie Küste)
LEG_BG     = (10, 20, 34)       # Legenden-Hintergrund
GLO_BG     = (12, 22, 38)       # Glossar-Modal-Hintergrund
GLO_BORDER = (60, 86, 112)      # Modal-Rahmen
GLO_TERM   = (130, 222, 212)    # Begriff (Mint)
GLO_TERM_A = (255, 232, 196)    # aktiver Begriff (Bernstein)
GLO_TEXT   = (214, 226, 222)    # Erklärungstext
GLO_DIM    = (120, 140, 150)    # Hinweise/Sekundär

# Shortcut-Legende (oben rechts, Taste '?' blendet sie um). EINE Quelle der
# Wahrheit fürs Fenster — neue Shortcuts ab jetzt HIER als Zeile ergänzen, dann
# tauchen sie automatisch in der Legende auf.
LEGEND = [
    ("Ziehen / ↑↓←→", "Pan"),
    ("Rad / + −",     "Zoom"),
    ("0",             "Weltansicht"),
    ("g",             "Gradnetz"),
    ("l",             "Länder-Labels"),
    ("h",             "Handelsrouten (Routen+Engstellen)"),
    ("d",             "Verkehrsdichte (Heatmap, gemessen)"),
    ("p",             "Politik/Konflikt (Kontrolle+Ereignisse)"),
    ("t",             "Zeit-Schrittweite (Woche…100 J.)"),
    (", . ;",         "Zeit: Schritt ◂ ▸ (halten) · jetzt"),
    ("?",             "Glossar (Begriffe suchen)"),
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

    def to_screen(self, wx, wy, ox=0.0):
        x0, y0, sx, sy = self._view()
        px = (wx + ox - x0) / sx * self.w
        py = (wy - y0) / sy * self.h
        return _clampf(px, -_CLAMP, _CLAMP), _clampf(py, -_CLAMP, _CLAMP)

    def screen_to_world(self, px, py):
        x0, y0, sx, sy = self._view()
        return x0 + px / self.w * sx, y0 + py / self.h * sy

    def visible(self, minx, miny, maxx, maxy, ox=0.0):
        x0, y0, sx, sy = self._view()
        return not (maxx + ox < x0 or minx + ox > x0 + sx
                    or maxy < y0 or miny > y0 + sy)

    def x_offsets(self):
        """Welt-Wrap: ganzzahlige x-Verschiebungen (in Welt-Breiten = 360°), die
        die [0,1]-Welt ins Sichtfenster bringen. Die Karte ist ein ENDLOS-BAND —
        jede Geometrie wird pro Offset projiziert, damit Routen über den 180°-
        Schnitt nahtlos weiterlaufen (statt am Rand abzuschneiden). Meist 1 Wert,
        am Datums­grenz-Schnitt 2."""
        x0 = self.cx - self.span_x / 2.0
        x1 = x0 + self.span_x
        return list(range(math.floor(x0), math.floor(x1 - 1e-9) + 1))

    def _clamp_pt(self, cx, cy, zoom):
        """Nur VERTIKAL klemmen (oben/unten gibt es keinen Wrap — Mercator endet
        bei ±85°). Horizontal läuft der Mittelpunkt FREI; die Welt wiederholt sich
        als Band (siehe x_offsets), darum kein x-Clamp mehr."""
        sx, sy = self._span(zoom)
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
    for ox in view.x_offsets():
        for lon in range(-150, 181, 30):
            wx, _ = lonlat_to_world(lon, 0)
            px = (wx + ox - x0) / sx * view.w
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


def _project(view, ring, ox=0.0):
    """Nx2-Welt-Array → Bildschirm-Pixel (int), vektorisiert + vereinfacht:
    aufeinanderfolgende Punkte auf derselben Pixel-Zelle fallen weg. Kappt die
    Zeichenlast auf ~Bildschirmauflösung, unabhängig von der Quell-Detailtiefe.
    `ox` verschiebt um eine ganze Welt-Breite (Welt-Wrap-Band, siehe x_offsets)."""
    x0, y0, sx, sy = view._view()
    px = np.clip((ring[:, 0] + ox - x0) / sx * view.w, -_CLAMP, _CLAMP)
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
    for wox in view.x_offsets():
        for c in countries:
            if not view.visible(*c['bbox'], ox=wox):
                continue
            for ring in c['rings']:
                pts = _project(view, ring, wox)
                if len(pts) < 3:
                    continue
                mn = pts.min(axis=0)
                mx = pts.max(axis=0)
                if mn[0] >= -8 and mn[1] >= -8 and mx[0] <= w + 8 and mx[1] <= h + 8:
                    polys.append(pts.tolist())        # ganz sichtbar → kein Clip nötig
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
    for ox in view.x_offsets():
        for (bbox, ring) in lines:
            if not view.visible(*bbox, ox=ox):
                continue
            pts = _project(view, ring, ox)
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
    ox = math.floor(wx)            # welche Welt-Kopie liegt unterm Cursor (Band)
    wxw = wx - ox                  # zugehöriges x in [0,1) für den Polygon-Test
    hit = None
    for c in countries:
        minx, miny, maxx, maxy = c['bbox']
        if not (minx <= wxw <= maxx and miny <= wy <= maxy):
            continue
        if any(_point_in_ring(wxw, wy, ring) for ring in c['rings']):
            hit = c
            break
    if hit is None:
        return

    font = fonts[0]
    surf = cache.get(hit['name'])
    if surf is None:
        surf = font.render(hit['name'], True, LABEL_FG)
        cache[hit['name']] = surf
    px, py = view.to_screen(hit['lx'], hit['ly'], ox=ox)
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


_ROUTES = None


def _get_routes():
    """Schifffahrtsrouten-Segmente einmal laden (Welt-Koords als Nx2-Arrays für
    die vektorisierte Projektion, wie die Küsten). Liste von (bbox, np-array)."""
    global _ROUTES
    if _ROUTES is not None:
        return _ROUTES
    segs = []
    try:
        from map.layers import portwatch  # noqa: E402
        data = portwatch.routes()
        if data:
            for (mnx, mny, mxx, mxy, pts) in data["segments"]:
                segs.append(((mnx, mny, mxx, mxy),
                             np.asarray(pts, dtype=np.float64)))
    except Exception:
        pass
    _ROUTES = segs
    return _ROUTES


def _draw_routes(screen, view):
    """Welt-Schifffahrtsrouten als dezente Linien (unter den Chokepoint-Markern).
    Projektion vektorisiert + vereinfacht (wie die Küste, _project)."""
    for ox in view.x_offsets():
        for (bbox, ring) in _get_routes():
            if not view.visible(*bbox, ox=ox):
                continue
            pts = _project(view, ring, ox)
            if len(pts) < 2:
                continue
            pygame.draw.aalines(screen, ROUTE_COL, False, pts.tolist())


def _draw_trade(screen, view, font, mouse):
    """Chokepoints als leuchtende Bernstein-Marker, Radius ~√(Schiffe heute).
    Halo + Kern + heller Ring; der dem Cursor nächste bekommt Name + Wert."""
    td = _get_trade()
    mx, my = mouse
    near, nd = None, 1e18
    for ox in view.x_offsets():
        for it in td['items']:
            if not view.visible(it['wx'], it['wy'], it['wx'], it['wy'], ox=ox):
                continue
            sxp, syp = view.to_screen(it['wx'], it['wy'], ox=ox)
            px, py = int(sxp), int(syp)
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


def _draw_caption(screen, font, text, y, fg=TRADE_FG):
    """Eine Provenienz-/Stand-Zeile oben links bei Höhe y. Gibt das y für die
    NÄCHSTE Zeile zurück → mehrere Overlays stapeln ihre Captions sauber."""
    label = font.render(text, True, fg)
    pad = 6
    bg = pygame.Surface((label.get_width() + 2 * pad, label.get_height() + 2 * pad))
    bg.set_alpha(150)
    bg.fill(HUD_BG)
    screen.blit(bg, (10, y))
    screen.blit(label, (10 + pad, y + pad))
    return y + bg.get_height() + 4


def _trade_caption_text():
    td = _get_trade()
    if not td['items']:
        return "◆ Handelsrouten — keine Daten (PortWatch-Cache leer)"
    return "◆ Handelsrouten · Routen + Chokepoints · %s · Stand %s" % (
        td['source'] or 'IMF PortWatch', td['vintage'] or '?')


# ── Verkehrsdichte-Overlay (Achse 2, Sub-Layer density / World Bank·IMF) ──────
# Gemessenes AIS-Dichteraster (committet, CC BY 4.0). Wird als weiche Heatmap
# übers Meer gemalt: pro Reduktions-Pixel Welt→lon/lat, Gitter samplen, über eine
# Farb-LUT zu RGBA, dann smoothscale aufs Fenster → nie harte Pixel, nur eine
# Dichtewolke, die tief drin sanft weicher wird. Welt-Wrap kommt gratis, weil x
# pro Pixel mod 1 genommen wird (Endlos-Band, wie der Rest).
_DENS = None
_DENS_LUT = None


def _get_density():
    global _DENS
    if _DENS is not None:
        return _DENS or None
    try:
        from map.layers import density  # noqa: E402
        _DENS = density.load() or False
    except Exception:
        _DENS = False
    return _DENS or None


def _density_lut():
    """256×4-RGBA-Farbverlauf (transparent → Indigo → Magenta → warm). Alpha
    wächst mit der Dichte, leeres Meer bleibt klar."""
    global _DENS_LUT
    if _DENS_LUT is not None:
        return _DENS_LUT
    stops = [(0.00,  10,  16,  40,   0),
             (0.12,  34,  54, 120,  60),
             (0.40, 120,  46, 156, 130),
             (0.72, 242,  96,  74, 184),
             (1.00, 255, 224, 158, 214)]
    ts = np.array([s[0] for s in stops])
    xs = np.linspace(0, 1, 256)
    lut = np.zeros((256, 4), np.uint8)
    for ci in range(4):
        ys = np.array([s[ci + 1] for s in stops], float)
        lut[:, ci] = np.clip(np.interp(xs, ts, ys), 0, 255).astype(np.uint8)
    _DENS_LUT = lut
    return lut


def _draw_density(screen, view):
    """Dichte als weiche Heatmap übers Meer (unter Land/Routen). Reduktions-Raster
    vektorisiert sampeln, dann glatt aufs Fenster skalieren."""
    d = _get_density()
    if d is None:
        return
    grid = d['grid']
    H, W = grid.shape
    lon_min, lon_max = d['lon_min'], d['lon_max']
    lat_min, lat_max = d['lat_min'], d['lat_max']
    w, h = view.w, view.h
    rw = min(600, max(120, w // 2))
    rh = max(1, int(rw * h / w))
    x0, y0, sx, sy = view._view()
    wx = x0 + (np.arange(rw) + 0.5) / rw * sx
    wy = y0 + (np.arange(rh) + 0.5) / rh * sy
    WX = wx[None, :] - np.floor(wx[None, :])          # Welt-Wrap → [0,1)
    WY = wy[:, None]
    lon = WX * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi - 2.0 * np.pi * WY)))  # inverse Mercator
    col = (lon - lon_min) / (lon_max - lon_min) * W
    row = (lat_max - lat) / (lat_max - lat_min) * H
    valid = ((row >= 0) & (row < H) & (col >= 0) & (col < W)
             & (WY >= 0) & (WY <= 1))
    ri = np.clip(row, 0, H - 1).astype(np.int32)
    ci = np.clip(col, 0, W - 1).astype(np.int32)
    rgba = _density_lut()[grid[ri, ci]]               # (rh, rw, 4)
    rgba[~valid] = 0
    surf = pygame.image.frombuffer(np.ascontiguousarray(rgba, np.uint8).tobytes(),
                                   (rw, rh), 'RGBA')
    screen.blit(pygame.transform.smoothscale(surf, (w, h)), (0, 0))


def _density_caption_text():
    d = _get_density()
    if d is None:
        return "▦ Verkehrsdichte — keine Daten (Ingest fehlt: ingest_shipdensity.py)"
    return "▦ Verkehrsdichte (gemessen) · World Bank/IMF · Stand %s · CC BY 4.0" \
        % d['vintage']


def _draw_density_legend(screen, font, view, bottom):
    """Farbskala-Legende (Heatmap = wenig→viel Verkehr) unten rechts, mit der
    Unterkante bei `bottom`. Gibt die Oberkante zurück (zum Stapeln)."""
    pad = 8
    barw, barh = 130, 10
    title = "Verkehrsdichte (2015–2021)"
    tw = font.size(title)[0]
    lo, hi = font.size("wenig")[0], font.size("viel")[0]
    bw = pad * 2 + max(barw, tw)
    bh = pad * 2 + font.get_height() + 4 + barh + 2 + font.get_height()
    x0 = view.w - bw - 10
    y0 = bottom - bh
    bg = pygame.Surface((bw, bh))
    bg.set_alpha(175)
    bg.fill(LEG_BG)
    screen.blit(bg, (x0, y0))
    screen.blit(font.render(title, True, LEG_FG), (x0 + pad, y0 + pad))
    by = y0 + pad + font.get_height() + 4
    lut = _density_lut()
    for i in range(barw):                              # Farbverlauf-Balken
        c = lut[int(i / barw * 255)]
        pygame.draw.line(screen, (int(c[0]), int(c[1]), int(c[2])),
                         (x0 + pad + i, by), (x0 + pad + i, by + barh))
    ty = by + barh + 2
    screen.blit(font.render("wenig", True, LEG_FG), (x0 + pad, ty))
    screen.blit(font.render("viel", True, LEG_FG), (x0 + pad + barw - hi, ty))
    return y0


# ── Politik/Konflikt-Overlay (Achse 2: control-ua + events-ucdp + borders) ────
# Wie der Handels-Overlay liest das Fenster die Sub-Layer DIREKT aus core/map/
# layers (offline-zuerst, Provenienz kommt mit). Drei Bausteine:
#   • Gebietskontrolle (VIINA) — je Ort ein Punkt, Farbe nach Konsens-Status.
#     ZEITREISEFÄHIG (Achse 3): control(at) löst den Stand an einem Tag auf.
#   • Konfliktereignisse (UCDP GED) — Punkte, Radius ~√(Todesopfer).
#   • Umstrittene Grenzen (Natural Earth) — Linien.
_POL_CONTROL = {}      # at-Schlüssel ('_now' | 'YYYY-MM-DD') → vorbereitete Arrays
_POL_EVENTS = None
_POL_BORDERS = None
_POL_RANGE = "_unset"  # (date_min, date_max) der VIINA-Zeitreihe oder None


def _pol_range():
    """Zeitreise-Grenzen der Kontrolle einmal lesen (für den Scrubber)."""
    global _POL_RANGE
    if _POL_RANGE == "_unset":
        try:
            from map.layers import viina  # noqa: E402
            _POL_RANGE = viina.date_range()
        except Exception:
            _POL_RANGE = None
    return _POL_RANGE


# Konsens-Status → (Farbe, Status-Code für die vektorisierte Gruppierung).
_CTRL_COL = {"UA": (CTRL_UA, 0), "RU": (CTRL_RU, 1)}   # sonst → CONTESTED (2)


def _get_control(at):
    """VIINA-Kontrolle für Zeitpunkt `at` (None=jetzt) laden + je at cachen. Gibt
    {wx, wy, code (Nx1 int), vintage, source, n} mit Welt-Koord-Arrays zurück."""
    key = at or "_now"
    c = _POL_CONTROL.get(key)
    if c is not None:
        return c
    wx, wy, code = [], [], []
    vintage, source, n = None, None, 0
    try:
        from map.layers import viina  # noqa: E402
        data = viina.control(at)
        if data:
            vintage = data.get("vintage")
            source = (data.get("source") or {}).get("name")
            for it in data.get("items", []):
                wx.append(it["wx"])
                wy.append(it["wy"])
                code.append(_CTRL_COL.get(it.get("status"), (None, 2))[1])
            n = len(wx)
    except Exception:
        pass
    c = {"wx": np.asarray(wx, dtype=np.float64),
         "wy": np.asarray(wy, dtype=np.float64),
         "code": np.asarray(code, dtype=np.int32),
         "vintage": vintage, "source": source, "n": n}
    _POL_CONTROL[key] = c
    return c


def _get_events():
    """UCDP-Ereignisse einmal laden + cachen (Welt-Koords + Todesopfer). Leer,
    solange kein Cache da ist (Token-gesperrt) — dann rendert der Sub-Layer nix."""
    global _POL_EVENTS
    if _POL_EVENTS is not None:
        return _POL_EVENTS
    items, vintage, source = [], None, None
    try:
        from map.layers import ucdp  # noqa: E402
        data = ucdp.events()
        if data:
            vintage = data.get("vintage")
            source = (data.get("source") or {}).get("name")
            for it in data.get("items", []):
                items.append({"wx": it["wx"], "wy": it["wy"],
                              "name": it.get("conflict") or "Ereignis",
                              "val": it.get("best"), "date": it.get("date")})
    except Exception:
        pass
    _POL_EVENTS = {"items": items, "vintage": vintage, "source": source}
    return _POL_EVENTS


def _get_pol_borders():
    """Umstrittene-Gebiete-Ringe einmal laden (Welt-Koords als Nx2-Arrays, wie die
    Küste). Liste von (bbox, np-array)."""
    global _POL_BORDERS
    if _POL_BORDERS is not None:
        return _POL_BORDERS
    segs = []
    try:
        from map.layers import borders  # noqa: E402
        data = borders.load()
        if data:
            for (mnx, mny, mxx, mxy, pts, _name, _cla) in data["rings"]:
                segs.append(((mnx, mny, mxx, mxy),
                             np.asarray(pts, dtype=np.float64)))
    except Exception:
        pass
    _POL_BORDERS = segs
    return _POL_BORDERS


def _draw_pol_borders(screen, view):
    """Umstrittene Grenzen als dezente rosa Linien (unter den Kontroll-Punkten)."""
    for ox in view.x_offsets():
        for (bbox, ring) in _get_pol_borders():
            if not view.visible(*bbox, ox=ox):
                continue
            pts = _project(view, ring, ox)
            if len(pts) < 2:
                continue
            pygame.draw.aalines(screen, BORDER_COL, False, pts.tolist())


# Kontroll-Fläche wird zwischengespeichert und NUR neu gerechnet, wenn sich der
# Blick (Mittelpunkt/Zoom), die Fenstergröße oder der Zeitpunkt ändern. Im
# Ruhezustand (Lesen, kein Pan/Zoom/Scrub) kostet der Layer dann nur EINEN Blit
# statt einer Vollbild-Neuberechnung je Frame — das war die Hauptlast.
_CTRL_SURF = {"sig": None, "surf": None, "buf": None}


def _control_surface(view, at):
    """RGBA-Fläche mit den Kontroll-Punkten (2×2 je Ort, nach Status gefärbt),
    signatur-gecacht. Baut nur bei Änderung neu: alle Orte vektorisiert
    projizieren (numpy), sichtbare maskieren, in einen WIEDERVERWENDETEN Puffer
    stempeln. Gibt die Surface (oder None, wenn nichts sichtbar) zurück."""
    w, h = view.w, view.h
    # Blick grob quantisieren → Mikro-Jitter am Ende des Easings baut nicht neu.
    sig = (round(view.cx, 4), round(view.cy, 4), round(view.zoom, 3), w, h, at)
    if _CTRL_SURF["sig"] == sig:
        return _CTRL_SURF["surf"]
    c = _get_control(at)
    if not c["n"]:
        _CTRL_SURF.update(sig=sig, surf=None)
        return None
    buf = _CTRL_SURF["buf"]
    if buf is None or buf.shape[0] != h or buf.shape[1] != w:
        buf = np.zeros((h, w, 4), dtype=np.uint8)
        _CTRL_SURF["buf"] = buf
    else:
        buf[:] = 0                               # Puffer nullen statt neu allozieren
    x0, y0, sx, sy = view._view()
    hit = False
    for ox in view.x_offsets():
        px = (c["wx"] + ox - x0) / sx * w
        py = (c["wy"] - y0) / sy * h
        vis = (px >= 0) & (px < w) & (py >= 0) & (py < h)
        if not np.any(vis):
            continue
        pxi = px[vis].astype(np.int32)
        pyi = py[vis].astype(np.int32)
        codev = c["code"][vis]
        for col, cc in ((CTRL_UA, 0), (CTRL_RU, 1), (CTRL_CONT, 2)):
            m = codev == cc
            if not np.any(m):
                continue
            xs, ys = pxi[m], pyi[m]
            for ddx in (0, 1):                   # 2×2-Block → sichtbarer, günstiger Punkt
                xx = np.clip(xs + ddx, 0, w - 1)
                for ddy in (0, 1):
                    yy = np.clip(ys + ddy, 0, h - 1)
                    buf[yy, xx, 0] = col[0]
                    buf[yy, xx, 1] = col[1]
                    buf[yy, xx, 2] = col[2]
                    buf[yy, xx, 3] = 255
            hit = True
    surf = pygame.image.frombuffer(np.ascontiguousarray(buf).tobytes(),
                                   (w, h), 'RGBA') if hit else None
    _CTRL_SURF.update(sig=sig, surf=surf)
    return surf


def _draw_control(screen, view, at):
    """Kontroll-Punkte zeichnen: die (gecachte) Fläche holen und blitten."""
    surf = _control_surface(view, at)
    if surf is not None:
        screen.blit(surf, (0, 0))


_POL_EVENT_CAP = 4000    # ehrliche Obergrenze gezeichneter Ereignisse pro Frame


def _draw_events(screen, view, font, mouse):
    """UCDP-Ereignisse als warme Punkte (Radius ~√Todesopfer), dem Cursor
    nächstes bekommt Name + Opferzahl + Datum. Bei sehr vielen sichtbaren
    Ereignissen greift ein Deckel (stärkste zuerst) — ehrlich, keine stille
    Kürzung."""
    ev = _get_events()
    items = ev["items"]
    if not items:
        return
    mx, my = mouse
    drawn = []
    for ox in view.x_offsets():
        for it in items:
            if not view.visible(it["wx"], it["wy"], it["wx"], it["wy"], ox=ox):
                continue
            sxp, syp = view.to_screen(it["wx"], it["wy"], ox=ox)
            drawn.append((int(sxp), int(syp), it))
    if len(drawn) > _POL_EVENT_CAP:
        drawn.sort(key=lambda d: (d[2]["val"] or 0), reverse=True)
        drawn = drawn[:_POL_EVENT_CAP]
    near, nd = None, 1e18
    for px, py, it in drawn:
        val = it["val"] or 0
        r = max(3, min(20, int(3 + math.sqrt(val) * 0.6)))
        gfxdraw.filled_circle(screen, px, py, r + 3, (244, 108, 92, 50))   # Halo
        gfxdraw.filled_circle(screen, px, py, r, EVENT_DOT)
        gfxdraw.aacircle(screen, px, py, r, EVENT_RING)
        d = (px - mx) ** 2 + (py - my) ** 2
        if d < nd:
            nd, near = d, (px, py, r, it)
    if near is not None and nd < 70 ** 2:
        px, py, r, it = near
        val = '—' if it["val"] is None else it["val"]
        label = "%s  ✝%s  %s" % (it["name"], val, it.get("date") or "")
        surf = font.render(label.strip(), True, EVENT_RING)
        screen.blit(surf, (px + r + 4, py - surf.get_height() // 2))


# Zeit-Schrittweite (Taste t zykliert): Label + Tage je ,/.-Schritt. Für heutige
# VIINA-Daten (~7 Monate) sind die großen Sprünge meist auf die Grenzen geklemmt,
# aber der Mechanismus ist generisch (künftige historische Layer spannen weiter).
_TIME_GRAN = [("Woche", 7), ("Monat", 30), ("Jahr", 365),
              ("10 Jahre", 3650), ("50 Jahre", 18250), ("100 Jahre", 36500)]


def _pol_step(at, days):
    """Achse-3-Zeit-Scrubber: `at` um `days` verschieben, in [date_min, date_max]
    geklemmt. Über das Maximum hinaus → None (=jüngster Stand, „jetzt")."""
    rng = _pol_range()
    if not rng:
        return at
    dmin, dmax = rng
    base = date.fromisoformat(at) if at else date.fromisoformat(dmax)
    lo, hi = date.fromisoformat(dmin), date.fromisoformat(dmax)
    nd = base + timedelta(days=days)
    if nd >= hi:
        return None                 # am jüngsten Rand → zurück auf „jetzt"
    if nd <= lo:
        return dmin
    return nd.isoformat()


def _pol_caption_text(at, gran_label):
    """Provenienz-/Stand-Zeile fürs Politik-Overlay (oben links), inkl. der
    aktuellen Zeit-Schrittweite (was ,/. springen)."""
    c = _get_control(at)
    ev = _get_events()
    if not c["n"] and not ev["items"] and not _get_pol_borders():
        return "◈ Politik/Konflikt — keine Daten (Cache leer)"
    when = at or "jetzt"
    parts = ["◈ Politik/Konflikt"]
    if c["n"]:
        parts.append("Kontrolle %d Orte · Stand %s" % (c["n"], c["vintage"] or when))
    if ev["items"]:
        parts.append("Ereignisse %d (UCDP)" % len(ev["items"]))
    else:
        parts.append("Ereignisse: kein UCDP-Cache")
    parts.append("Schritt: %s (,/.)" % gran_label)
    return " · ".join(parts)


# Symbol-/Farb-Erklärung fürs Politik-Overlay (nur sichtbar, wenn 'p' an ist).
_POL_LEGEND = [
    ("dot", CTRL_UA,   "Kontrolle Ukraine"),
    ("dot", CTRL_RU,   "Kontrolle Russland"),
    ("dot", CTRL_CONT, "umstritten / unklar"),
    ("dot", EVENT_DOT, "Konfliktereignis (UCDP)"),
    ("line", BORDER_COL, "umstrittene Grenze"),
]


def _draw_pol_legend(screen, font, view, bottom):
    """Mini-Legende unten rechts, die die Politik-Farben beschriftet. Unterkante
    bei `bottom`, gibt die Oberkante zurück (zum Stapeln)."""
    pad, sw, gap = 8, 24, 8
    lh = font.get_height() + 6
    lab_w = max(font.size(t)[0] for _, _, t in _POL_LEGEND)
    bw = pad * 2 + sw + gap + lab_w
    bh = pad * 2 + lh * len(_POL_LEGEND)
    x0 = view.w - bw - 10
    y0 = bottom - bh
    bg = pygame.Surface((bw, bh))
    bg.set_alpha(175)
    bg.fill(LEG_BG)
    screen.blit(bg, (x0, y0))
    for i, (kind, col, text) in enumerate(_POL_LEGEND):
        ty = y0 + pad + i * lh
        cyc = ty + font.get_height() // 2
        sxc = x0 + pad
        if kind == "line":
            pygame.draw.line(screen, col, (sxc, cyc), (sxc + sw, cyc), 2)
        else:
            gfxdraw.filled_circle(screen, sxc + sw // 2, cyc, 5, col)
            gfxdraw.aacircle(screen, sxc + sw // 2, cyc, 5, EVENT_RING)
        screen.blit(font.render(text, True, LEG_FG), (x0 + pad + sw + gap, ty))
    return y0


# Symbol-Erklärung für das Trade-Overlay (nur sichtbar, wenn 't' an ist). Sagt,
# was Linie / Marker / Zahl bedeuten — eine EIGENE Legende, getrennt von der
# Shortcut-Legende oben rechts. Unten rechts (über nichts anderem).
_TRADE_LEGEND = [
    ("line", ROUTE_COL, "Schifffahrtsroute"),
    ("dot",  TRADE_DOT, "Chokepoint (Engstelle)"),
    ("num",  TRADE_FG,  "Zahl = Schiffe / Tag"),
]


def _draw_trade_legend(screen, font, view, bottom):
    """Mini-Legende unten rechts, die die Trade-Symbole beschriftet: was ist die
    Linie, was der Marker, was die Zahl. Unterkante bei `bottom`, gibt die
    Oberkante zurück (zum Stapeln mit anderen Overlay-Legenden)."""
    pad, sw, gap = 8, 24, 8                       # swatch-Breite, Abstand
    lh = font.get_height() + 6
    lab_w = max(font.size(t)[0] for _, _, t in _TRADE_LEGEND)
    bw = pad * 2 + sw + gap + lab_w
    bh = pad * 2 + lh * len(_TRADE_LEGEND)
    x0 = view.w - bw - 10
    y0 = bottom - bh
    bg = pygame.Surface((bw, bh))
    bg.set_alpha(175)
    bg.fill(LEG_BG)
    screen.blit(bg, (x0, y0))
    for i, (kind, col, text) in enumerate(_TRADE_LEGEND):
        ty = y0 + pad + i * lh
        cyc = ty + font.get_height() // 2
        sxc = x0 + pad
        if kind == "line":
            pygame.draw.line(screen, col, (sxc, cyc), (sxc + sw, cyc), 2)
        elif kind == "dot":
            gfxdraw.filled_circle(screen, sxc + sw // 2, cyc, 5, col)
            gfxdraw.aacircle(screen, sxc + sw // 2, cyc, 5, TRADE_RING)
        else:  # num — Beispielzahl als Probe
            ns = font.render("17", True, col)
            screen.blit(ns, (sxc + sw // 2 - ns.get_width() // 2,
                             cyc - ns.get_height() // 2))
        screen.blit(font.render(text, True, LEG_FG), (x0 + pad + sw + gap, ty))
    return y0


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


def _wrap(font, text, max_w):
    """Text auf max_w Pixel umbrechen (wortweise). Liste von Zeilen-Strings."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if font.size(trial)[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_glossary(screen, fonts, win_w, win_h, query, results, sel):
    """Such-Modal (Taste '?'): Eingabezeile + Trefferliste links, Erklärung des
    gewählten Begriffs rechts. Inhalte aus core/glossary.py. Reiner Renderer."""
    title_f, term_f, text_f = fonts          # (bold 17, bold 15, normal 14)
    # Karte abdunkeln (Fokus aufs Modal).
    dim = pygame.Surface((win_w, win_h), pygame.SRCALPHA)
    dim.fill((4, 8, 16, 170))
    screen.blit(dim, (0, 0))

    pw = min(820, win_w - 60)
    ph = min(520, win_h - 60)
    x0 = (win_w - pw) // 2
    y0 = (win_h - ph) // 2
    panel = pygame.Surface((pw, ph))
    panel.fill(GLO_BG)
    screen.blit(panel, (x0, y0))
    pygame.draw.rect(screen, GLO_BORDER, (x0, y0, pw, ph), 1)

    pad = 18
    cx = x0 + pad
    cy = y0 + pad
    # Kopf + Eingabezeile (mit blinkfreiem Cursor-Balken).
    screen.blit(title_f.render("Glossar", True, GLO_TERM), (cx, cy))
    hint = "tippen zum Suchen · ↑↓ wählen · Esc schließt"
    hs = text_f.render(hint, True, GLO_DIM)
    screen.blit(hs, (x0 + pw - pad - hs.get_width(), cy + 3))
    cy += title_f.get_height() + 8
    qs = term_f.render("Suche: " + query + "▌", True, GLO_TERM_A)
    screen.blit(qs, (cx, cy))
    cy += term_f.get_height() + 8
    pygame.draw.line(screen, GLO_BORDER, (cx, cy), (x0 + pw - pad, cy))
    cy += 10

    if not results:
        screen.blit(text_f.render("keine Treffer für „%s“" % query, True,
                                  GLO_DIM), (cx, cy))
        return

    # Linke Spalte: Treffer-Begriffe (gewählter hervorgehoben).
    list_w = 250
    lh = term_f.get_height() + 6
    max_rows = (y0 + ph - pad - cy) // lh
    sel = max(0, min(sel, len(results) - 1))
    start = max(0, min(sel - max_rows + 1, len(results) - max_rows)) \
        if len(results) > max_rows else 0
    for i in range(start, min(len(results), start + max_rows)):
        e = results[i]
        active = (i == sel)
        col = GLO_TERM_A if active else GLO_TERM
        prefix = "▸ " if active else "  "
        screen.blit(term_f.render(prefix + e["term"], True, col),
                    (cx, cy + (i - start) * lh))

    # Rechte Spalte: Erklärung des gewählten Begriffs (umbrochen).
    rx = cx + list_w + 16
    rw = x0 + pw - pad - rx
    pygame.draw.line(screen, GLO_BORDER, (rx - 8, cy),
                     (rx - 8, y0 + ph - pad))
    e = results[sel]
    ty = cy
    screen.blit(term_f.render(e["term"], True, GLO_TERM_A), (rx, ty))
    ty += term_f.get_height() + 6
    for line in _wrap(text_f, e["text"], rw):
        screen.blit(text_f.render(line, True, GLO_TEXT), (rx, ty))
        ty += text_f.get_height() + 3


def _draw_hud(screen, font, view, level=''):
    lon, lat = world_to_lonlat(view.cx - math.floor(view.cx), view.cy)
    txt = "lon %.2f  lat %.2f   zoom %.1f   lod %s" % (lon, lat, view.zoom, level)
    label = font.render(txt, True, HUD_FG)
    pad = 6
    bg = pygame.Surface((label.get_width() + 2 * pad, label.get_height() + 2 * pad))
    bg.set_alpha(180)
    bg.fill(HUD_BG)
    screen.blit(bg, (10, view.h - bg.get_height() - 10))
    screen.blit(label, (10 + pad, view.h - label.get_height() - 10 - pad))


def _make_icon(size=64):
    """Fenster-Icon (favicon) programmatisch malen — ein kleiner „Control-Room"-
    Globus in der Fensterpalette: Tiefsee-Scheibe, zwei Salbei-Landflecken,
    Mint-Küstenring + Gradnetz-Kreuz und ein Bernstein-Marker. Kein externes
    Asset nötig, skaliert scharf über gfxdraw-Antialiasing."""
    s = size
    icon = pygame.Surface((s, s), pygame.SRCALPHA)
    c = s // 2
    r = s // 2 - 2
    gfxdraw.filled_circle(icon, c, c, r, SEA_BOTTOM)         # Meer-Scheibe
    gfxdraw.filled_circle(icon, int(s * 0.40), int(s * 0.44), int(s * 0.20), LAND)
    gfxdraw.filled_circle(icon, int(s * 0.63), int(s * 0.62), int(s * 0.14), LAND)
    gfxdraw.aacircle(icon, c, c, r, COAST)                   # Küstenring
    gfxdraw.aacircle(icon, c, c, r - 1, COAST)
    pygame.draw.line(icon, GRAT_AXIS, (c, 3), (c, s - 3))    # Gradnetz-Kreuz
    pygame.draw.line(icon, GRAT_AXIS, (3, c), (s - 3, c))
    gfxdraw.filled_circle(icon, int(s * 0.66), int(s * 0.34), 4, TRADE_DOT)   # Marker
    gfxdraw.aacircle(icon, int(s * 0.66), int(s * 0.34), 4, TRADE_RING)
    return icon


def main():
    ap = argparse.ArgumentParser(description="Natives Karten-Fenster (pygame).")
    ap.add_argument('--cx', type=float, default=10.0, help="Start-Längengrad")
    ap.add_argument('--cy', type=float, default=30.0, help="Start-Breitengrad")
    ap.add_argument('--zoom', type=float, default=0.0, help="0 = ganze Welt")
    ap.add_argument('--w', type=int, default=1100, help="Fensterbreite")
    ap.add_argument('--h', type=int, default=720, help="Fensterhöhe")
    a = ap.parse_args()

    pygame.init()
    pygame.display.set_icon(_make_icon())     # Fenster-Icon (favicon) VOR set_mode
    pygame.display.set_caption("ZENTRALE — Karte")
    screen = pygame.display.set_mode((a.w, a.h), pygame.RESIZABLE)
    # Tasten-Wiederholung bei Halten: 300 ms Anlauf, dann alle 55 ms. Damit lässt
    # sich die Zeit (,/.) UND Pan/Zoom durch Gedrückthalten flüssig durchfahren.
    pygame.key.set_repeat(300, 55)
    clock = pygame.time.Clock()
    hud_font = pygame.font.SysFont("monospace", 15)
    legend_font = pygame.font.SysFont("monospace", 13)
    label_fonts = (pygame.font.SysFont("sans", 17, bold=True),
                   pygame.font.SysFont("sans", 13))
    glossary_fonts = (pygame.font.SysFont("sans", 17, bold=True),
                      pygame.font.SysFont("sans", 15, bold=True),
                      pygame.font.SysFont("sans", 14))
    label_cache = {}

    view = MapView(a.w, a.h, a.cx, a.cy, a.zoom)
    sea = _sea_gradient(a.w, a.h)
    vig = _vignette(a.w, a.h)
    show_grat = True
    show_labels = True
    show_trade = False               # Routen + Chokepoints (Taste 't')
    show_density = False             # Verkehrsdichte-Heatmap (Taste 'd')
    show_political = False           # Kontrolle + Ereignisse + Grenzen (Taste 'p')
    pol_at = None                    # Achse 3: Zeitpunkt 'YYYY-MM-DD' oder None=jetzt
    time_gran_idx = 0                # Zeit-Schrittweite (Index in _TIME_GRAN, Taste 't')
    show_legend = True               # Shortcut-Legende oben rechts (immer an)
    glossary_open = False            # '?'-Such-Modal (Begriffs-Erklärungen)
    g_query, g_sel = "", 0

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
                if glossary_open:
                    # Modal frisst alle Tasten — keine Karten-Steuerung dahinter.
                    if ev.key == pygame.K_ESCAPE:
                        glossary_open = False
                    elif ev.key == pygame.K_BACKSPACE:
                        g_query, g_sel = g_query[:-1], 0
                    elif ev.key == pygame.K_UP:
                        g_sel = max(0, g_sel - 1)
                    elif ev.key == pygame.K_DOWN:
                        g_sel += 1            # beim Zeichnen geclamped
                    elif ev.unicode and ev.unicode.isprintable():
                        g_query, g_sel = g_query + ev.unicode, 0
                    continue
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.unicode == '?':
                    glossary_open, g_query, g_sel = True, "", 0
                elif ev.key == pygame.K_0:
                    view.tzoom = 0.0       # weich zurück zur Weltansicht
                    wx, wy = lonlat_to_world(10.0, 30.0)
                    wx += round(view.cx - wx)   # nächste Welt-Kopie → kurzer Pan
                    view.tcx, view.tcy = view._clamp_pt(wx, wy, 0.0)
                elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    view.zoom_to(view.w / 2, view.h / 2, +0.6)
                elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    view.zoom_to(view.w / 2, view.h / 2, -0.6)
                elif ev.key == pygame.K_g:
                    show_grat = not show_grat
                elif ev.key == pygame.K_l:
                    show_labels = not show_labels
                elif ev.key == pygame.K_h:
                    show_trade = not show_trade
                elif ev.key == pygame.K_d:
                    show_density = not show_density
                elif ev.key == pygame.K_p:
                    show_political = not show_political
                    if show_political:
                        pol_at = None            # beim Einschalten auf „jetzt"
                elif ev.key == pygame.K_t:       # Zeit-Schrittweite zyklieren
                    time_gran_idx = (time_gran_idx + 1) % len(_TIME_GRAN)
                # Zeit-Scrubber über ev.unicode (layout-sicher, auch für ';' das auf
                # dt. Layout Shift+, ist) — und über set_repeat gedrückt-haltbar.
                elif ev.unicode == ',':          # Achse 3: einen Schritt zurück
                    pol_at = _pol_step(pol_at, -_TIME_GRAN[time_gran_idx][1])
                elif ev.unicode == '.':          # Achse 3: einen Schritt vor
                    pol_at = _pol_step(pol_at, +_TIME_GRAN[time_gran_idx][1])
                elif ev.unicode == ';':          # Achse 3: zurück auf „jetzt"
                    pol_at = None
                elif ev.key == pygame.K_LEFT:
                    view.pan_target(-0.2, 0)
                elif ev.key == pygame.K_RIGHT:
                    view.pan_target(+0.2, 0)
                elif ev.key == pygame.K_UP:
                    view.pan_target(0, -0.2)
                elif ev.key == pygame.K_DOWN:
                    view.pan_target(0, +0.2)
            elif ev.type == pygame.MOUSEBUTTONDOWN and not glossary_open:
                if ev.button == 1:
                    dragging = True
                elif ev.button == 4:
                    view.zoom_to(*ev.pos, +0.5)
                elif ev.button == 5:
                    view.zoom_to(*ev.pos, -0.5)
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    dragging = False
            elif ev.type == pygame.MOUSEMOTION and dragging and not glossary_open:
                view.pan_pixels(ev.rel[0], ev.rel[1])

        view.update(dt)                      # sanftes Zoom-Easing pro Frame

        # Achse 1 / LOD: Detailstufe nach Zoom wählen. basemap cacht pro Stufe,
        # der Aufruf ist also nach dem Erstladen nur ein Dict-Lookup. (Beim
        # ersten Überschreiten einer Schwelle lädt die feinere Datei einmalig —
        # ein kurzer Frame-Hänger, danach flüssig.)
        level = basemap.lod_for_zoom(view.zoom)
        geom = _get_geom(level)

        screen.blit(sea, (0, 0))
        if show_density:
            _draw_density(screen, view)      # Meer-Heatmap unter Gradnetz/Land
        if show_grat:
            _draw_graticule(screen, view)
        _draw_land(screen, view, geom['countries'])
        _draw_coast(screen, view, geom['coast'])
        screen.blit(vig, (0, 0))
        if show_labels:
            _draw_hover_label(screen, view, geom['countries'], label_fonts,
                              label_cache, pygame.mouse.get_pos())
        if show_trade:
            _draw_routes(screen, view)       # Routen zuerst (unter den Markern)
            _draw_trade(screen, view, label_fonts[1], pygame.mouse.get_pos())
        if show_political:
            _draw_pol_borders(screen, view)  # Grenzen unter den Punkten
            _draw_control(screen, view, pol_at)
            _draw_events(screen, view, label_fonts[1], pygame.mouse.get_pos())
        # Provenienz-Captions oben links stapeln (jedes aktive Overlay eine Zeile).
        cap_y = 10
        if show_density:
            cap_y = _draw_caption(screen, hud_font, _density_caption_text(),
                                  cap_y, DENS_FG)
        if show_trade:
            cap_y = _draw_caption(screen, hud_font, _trade_caption_text(), cap_y)
        if show_political:
            cap_y = _draw_caption(
                screen, hud_font,
                _pol_caption_text(pol_at, _TIME_GRAN[time_gran_idx][0]),
                cap_y, POL_FG)
        # Overlay-Legenden unten rechts stapeln (Dichte unten, dann Trade, dann Politik).
        leg_bottom = view.h - 10
        if show_density:
            leg_bottom = _draw_density_legend(screen, legend_font, view,
                                              leg_bottom) - 8
        if show_trade:
            leg_bottom = _draw_trade_legend(screen, legend_font, view,
                                            leg_bottom) - 8
        if show_political:
            _draw_pol_legend(screen, legend_font, view, leg_bottom)
        _draw_hud(screen, hud_font, view, level)
        if show_legend:
            _draw_legend(screen, legend_font, view.w)
        if glossary_open:
            _draw_glossary(screen, glossary_fonts, view.w, view.h,
                           g_query, glossary.search(g_query), g_sel)
        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    main()
