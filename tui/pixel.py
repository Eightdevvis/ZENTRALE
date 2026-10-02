"""Pixel-Baustein der TUI: kleine Pixelbilder als Terminal-Zeichen malen.

Ein Terminal kann pro Zeichenfeld genau zwei Farben (Vorder- + Hintergrund).
Gemalt wird deshalb fein — 2×6 Pixel je Zeichenfeld — und für jedes Feld
das Zeichen gewählt, das die Pixel am treuesten trifft ("Mix"): Halbblock
(1×2, ▀) bei Farbflächen, Viertel (2×2, ▚) oder Sextant (2×3, 🬗) bei feinen
Kanten. VTE zeichnet alle drei selbst und pixelgenau (Sextanten seit ~0.62).
Modus "half" nimmt nur Halbblöcke — für Terminals ohne Sextanten (E-Ink-App,
Linux-Konsole), per ZENTRALE_PIXEL=half.

Curses-frei: liefert Zellen (zeichen, fg_rgb, bg_rgb); welche curses-Farbe
daraus wird (24 Bit oder nächste der 256), entscheidet die TUI.

Erstes Motiv: Sashas Bernstein im Treppenschliff (Vorlage: ein 16×16-PNG,
nachgezeichnet als Bauregel `gem`, damit er in jeder Größe sauber wird).
"""
import math
from functools import lru_cache

FX, FY = 2, 6                       # Feinpixel je Zeichenfeld (Spalten, Zeilen)
AY = (18 / FY) / (9 / FX)           # Pixelhöhe/-breite bei 9×18-Zellen ≈ 0,67


def _hex(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


GEM = {
    "out": _hex("#4a1c10"), "top": _hex("#ffd866"), "left": _hex("#ffb53a"),
    "right": _hex("#d8580c"), "bottom": _hex("#e8741a"), "edge": _hex("#fff1c2"),
    "tabL": _hex("#ffb21f"), "tabD": _hex("#e05a0a"), "tabHi": _hex("#ffe9a0"),
    "spark": _hex("#fffbe8"),
}
EMBER = _hex("#ff5a1f")             # Nachglimmen des zuletzt abgehakten Steins


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


# ── xterm-256 ↔ RGB ─────────────────────────────────────────────────────────
_CUBE = (0, 95, 135, 175, 215, 255)
_BASE16 = ("#000000", "#800000", "#008000", "#808000", "#000080", "#800080",
           "#008080", "#c0c0c0", "#808080", "#ff0000", "#00ff00", "#ffff00",
           "#0000ff", "#ff00ff", "#00ffff", "#ffffff")


def xterm_rgb(n):
    """RGB einer xterm-256-Farbnummer."""
    n = int(n)
    if n < 16:
        return _hex(_BASE16[max(0, n)])
    if n >= 232:
        v = 8 + (n - 232) * 10
        return (v, v, v)
    i = n - 16
    return (_CUBE[i // 36], _CUBE[(i // 6) % 6], _CUBE[i % 6])


def rgb_256(c):
    """Nächste xterm-256-Farbe (Würfel oder Graurampe) zu RGB."""
    def q(v):
        return min(range(6), key=lambda i: abs(_CUBE[i] - v))
    qi = [q(v) for v in c]
    cube = tuple(_CUBE[i] for i in qi)
    gi = max(0, min(23, round((sum(c) / 3 - 8) / 10)))
    grey = (8 + gi * 10,) * 3
    if _d2(c, cube) <= _d2(c, grey):
        return 16 + 36 * qi[0] + 6 * qi[1] + qi[2]
    return 232 + gi


# ── Bauregel: Bernstein im Treppenschliff ───────────────────────────────────
def gem(w, h, ay=1.0):
    """Den Stein als Pixelraster [zeile][spalte] = RGB | None malen.
    ay = Pixelhöhe/Pixelbreite, damit er bei flachen Pixeln nicht staucht.
    Groß (≥12): Rahmen 3, cremefarbene Tafelkante, Funkelkreuze; klein:
    Rand, 1er-Rahmen, geteilte Tafel, ein Glanzpixel."""
    g = [[None] * w for _ in range(h)]
    big = w >= 12 and h * ay >= 12
    fr = 3 if big else (1 if w >= 6 and h * ay >= 5 else 0)
    t0x, t0y = fr + 1, int((fr + .34) / ay) + 1
    tw, th = w - 2 * t0x, h - 2 * t0y
    for y in range(h):
        for x in range(w):
            cx, cy = min(x, w - 1 - x), min(y, h - 1 - y) * ay
            if cx + cy < (2 if big else 1):                      # runde Ecken
                continue
            if cx == 0 or cy < .7 or (big and cx + cy < 2 + max(1, ay)):
                g[y][x] = GEM["out"]
                continue
            if cx <= fr or cy <= fr + .34:                       # abgeschrägter Rahmen
                if abs(cx - cy) < .5:
                    g[y][x] = GEM["edge"]                        # Kante von der Ecke
                elif cy < cx:
                    g[y][x] = GEM["top"] if y < h / 2 else GEM["bottom"]
                else:
                    g[y][x] = GEM["left"] if x < w / 2 else GEM["right"]
                continue
            tx, ty = x - t0x, y - t0y                            # Tafel
            if big and (tx == 0 or ty == 0 or tx == tw - 1 or ty == th - 1):
                g[y][x] = GEM["edge"]
                continue
            u = (tx + .5) / tw + (ty + .5) / th
            g[y][x] = (GEM["tabHi"] if big and abs(u - 1) < .1
                       else GEM["tabL"] if u < 1 else GEM["tabD"])
    if big:                                                      # Funkelkreuze
        for x, y in ((t0x, t0y), (w - 1 - t0x, t0y), (t0x, h - 1 - t0y),
                     (w - 1 - t0x, h - 1 - t0y)):
            g[y][x] = GEM["spark"]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= y + dy < h and 0 <= x + dx < w and g[y + dy][x + dx]:
                    g[y + dy][x + dx] = GEM["edge"]
    elif tw > 0 and th > 0:
        g[t0y][t0x] = GEM["spark"]                               # Glanzpixel
    return g


# ── Zelle → Zeichen ─────────────────────────────────────────────────────────
_QUAD = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"          # Bits: oben-l 1, oben-r 2, unten-l 4, unten-r 8


def sextant(bits):
    """Sextanten-Zeichen zu 6 Bits (oben-l 1, oben-r 2, mitte-l 4, mitte-r 8,
    unten-l 16, unten-r 32). Die vier Muster, die es schon gibt (leer, linke
    und rechte Spalte, voll), stehen nicht im Block U+1FB00–1FB3B."""
    bits &= 63
    special = {0: " ", 21: "▌", 42: "▐", 63: "█"}
    if bits in special:
        return special[bits]
    return chr(0x1FB00 + bits - 1 - (bits > 21) - (bits > 42))


def _zwei_farben(cols):
    """Die zwei Farben, die die Liste am besten treffen + Zuordnung je Eintrag."""
    uniq = []
    for c in cols:
        if c not in uniq:
            uniq.append(c)
    if len(uniq) == 1:
        return uniq[0], uniq[0], [False] * len(cols), 0
    best = None
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = uniq[i], uniq[j]
            on, err = [], 0
            for c in cols:
                da, db = _d2(c, a), _d2(c, b)
                on.append(da < db)
                err += min(da, db)
            if best is None or err < best[3]:
                best = (a, b, on, err)
    a, b, on, _ = best

    def avg(sel):
        g = [c for c, o in zip(cols, on) if o == sel]
        return tuple(round(sum(v[k] for v in g) / len(g)) for k in range(3)) if g else None
    return avg(True) or a, avg(False) or b, on, best[3]


def zelle(fine, modus="mix"):
    """2×6 Feinpixel (zeilenweise, RGB) → (zeichen, fg, bg).
    Probiert Halbblock, Viertel und Sextant; Gleichstand → Halbblock."""
    layouts = ((1, 2, 0),) if modus == "half" else ((1, 2, 0), (2, 2, 1), (2, 3, 1))
    best = None
    for gx, gy, malus in layouts:
        bw, bh = FX // gx, FY // gy
        sub = []
        for j in range(gy):
            for i in range(gx):
                px = [fine[y * FX + x] for y in range(j * bh, (j + 1) * bh)
                      for x in range(i * bw, (i + 1) * bw)]
                sub.append(tuple(round(sum(p[k] for p in px) / len(px)) for k in range(3)))
        fg, bg, on, _ = _zwei_farben(sub)
        err = 0
        for y in range(FY):
            for x in range(FX):
                k = (y // bh) * gx + x // bw
                err += _d2(fine[y * FX + x], fg if on[k] else bg)
        err *= 1 + malus * .04
        if best is None or err < best[0]:
            best = (err, gx, gy, fg, bg, on)
    _, gx, gy, fg, bg, on = best
    bits = sum(1 << k for k, o in enumerate(on) if o)
    if not any(on):
        return " ", bg, bg
    if gx == 1:
        ch = "█" if bits == 3 else ("▀" if bits == 1 else "▄")
    elif gy == 2:
        ch = _QUAD[bits]
    else:
        ch = sextant(bits)
    return ch, fg, bg


def zellen(px, bg, modus="mix"):
    """Feinpixel-Raster (Höhe Vielfaches von 6, Breite von 2) → Zeilen von
    Zellen (zeichen, fg, bg). None-Pixel nehmen die Hintergrundfarbe an."""
    rows = len(px) // FY
    cols = len(px[0]) // FX if px else 0
    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            fine = [px[r * FY + y][c * FX + x] or bg for y in range(FY) for x in range(FX)]
            line.append(zelle(fine, modus))
        out.append(line)
    return out


# ── Bernsteinleiste ─────────────────────────────────────────────────────────
def _leer(c, bg):
    """Noch nicht abgehakt: derselbe Stein, fast durchsichtig (Rand etwas mehr)."""
    return mix(c, bg, .55 if c == GEM["out"] else .86)


@lru_cache(maxsize=64)
def bernstein_zellen(done, total, breite, bg, glimm=0, modus="mix"):
    """Die Bernsteinleiste als 2 Zeilen × `breite` Zellen (zeichen, fg, bg).

    Ein Stein je Punkt, die abgehakten leuchten; Steinbreite 4, 3 oder 2
    Zeichen (mit Fuge, wenn Platz ist) — passt nicht mal das, wird es eine
    durchgehende Bernsteinfüllung. glimm (0..7) lässt den zuletzt abgehakten
    Stein nachglimmen (die TUI zählt das im Takt hoch)."""
    try:
        done, total, breite = int(done), int(total), int(breite)
    except (TypeError, ValueError):
        return []
    if total <= 0 or breite <= 0:
        return []
    done = max(0, min(done, total))
    H, W = 2 * FY, breite * FX
    px = [[None] * W for _ in range(H)]
    glut = (math.sin(glimm / 8 * 2 * math.pi) + 1) / 2 * .4
    k = gap = 0
    for kk, gg in ((4, 1), (4, 0), (3, 1), (3, 0), (2, 1), (2, 0)):
        if total * (kk + gg) - gg <= breite:
            k, gap = kk, gg
            break
    if k:
        sp = gem(k * FX, H, AY)
        for i in range(total):
            x0 = i * (k + gap) * FX
            for y in range(H):
                for x in range(k * FX):
                    c = sp[y][x]
                    if c is None:
                        continue
                    if i >= done:
                        c = _leer(c, bg)
                    elif i == done - 1 and c != GEM["out"] and glut:
                        c = mix(c, EMBER, glut)
                    px[y][x0 + x] = c
    else:                                   # zu viele Punkte → durchgehende Füllung
        spalte = (GEM["out"], GEM["out"], GEM["top"], GEM["top"], GEM["tabL"], GEM["tabL"],
                  GEM["tabL"], GEM["tabD"], GEM["tabD"], GEM["bottom"], GEM["out"], GEM["out"])
        lit = done * W // total
        for x in range(W):
            for y in range(H):
                px[y][x] = spalte[y] if x < lit else _leer(spalte[y], bg)
    return zellen(px, bg, modus)
