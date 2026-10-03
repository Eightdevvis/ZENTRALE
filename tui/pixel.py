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


# ── Elektronik: Symbol fürs App-Rad ─────────────────────────────────────────
# Entworfen in der Vorschau-Seite (Sasha, 03.10.2026) und 1:1 von dort
# übertragen — auch der Zufall (`_rnd`) ist bitgleich, damit genau die
# abgenickten Zacken stehen. Ein durchscheinend blaues Feld ohne Rand, das
# hinter dem Schriftzug dunkel ist und nach oben/unten gerastert in sich
# verjüngende Pixelzacken ausläuft. `offen` 0 = zu (Pille), 1 = offen:
# erst eine helle Linie, dann klappen Ober- und Unterhälfte auf, dann
# wachsen die Zacken. Offen glitzert es, eine Abtastlinie läuft hoch.
EL_W, EL_H = 16, 9                       # Zellen
EL_LABEL_ZEILE = 4                       # Zeile der Schriftplatte = Zeile der Pille
_CX0, _CX1, _CY0, _CY1, _YC, _PLATE = 4, 28, 12, 42, 27, (24, 30)
EL_FARBEN = {
    "nacht": {"bg": _hex("#000000"), "core": _hex("#2f7dff"), "edge": _hex("#9be6ff"),
              "glow": _hex("#47b8ff"), "pill": _hex("#123a6b"), "pillTxt": _hex("#bfe9ff"),
              "label": _hex("#ffffff")},
    "tag":   {"bg": _hex("#ffffff"), "core": _hex("#2f7dff"), "edge": _hex("#0b4fb3"),
              "glow": _hex("#3d8ef0"), "pill": _hex("#d3e6ff"), "pillTxt": _hex("#0b3d8a"),
              "label": _hex("#001a40")},
}
_BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _rnd(*k):
    """Deterministischer Zufall 0..1 — bitgleich zur Vorschau (JS)."""
    h = 2166136261
    for v in k:
        h = (h ^ ((int(v) * 2654435761) % 4294967296)) & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF
    return h / 4294967296


def _ease(t):
    return 0.0 if t <= 0 else 1.0 if t >= 1 else 1 - (1 - t) ** 3


def _jsround(v):
    """Math.round aus JS (x.5 rundet immer nach oben, auch negativ)."""
    return math.floor(v + .5)


@lru_cache(maxsize=4)
def _spikes(d):
    """Zacken-Bauplan einer Seite (d -1 oben, 1 unten): ([(x0, w, L, lean)], reach)."""
    lst, reach = [], [0] * (EL_W * FX)
    x, i = _CX0 + int(_rnd(d, 61) * 2), 0
    while x < _CX1:
        w = min(_CX1 - x, 2 + int(_rnd(i, d, 63) * 3))          # 2–4 breit
        L = (4, 6, 7, 9)[int(_rnd(i, d, 65) * 4)]
        lean = int(_rnd(i, d, 67) * 3) - 1                      # -1 links, 0 mittig, 1 rechts
        lst.append((x, w, L, lean))
        for c in range(x, x + w):
            reach[c] = L
        x += w + 1 + int(_rnd(i, d, 69) * 2)                    # 1–2 Luft
        i += 1
    return tuple(lst), tuple(reach)


def _el_flach(F, x, y):
    """Flaches Bild des Kerns (ohne Rand): (farbe, deckkraft)."""
    if _PLATE[0] <= y < _PLATE[1] and _CX0 + 2 <= x < _CX1 - 2:
        return F["core"], .42                                   # Schriftplatte
    if (y == _PLATE[0] - 3 or y == _PLATE[1] + 2) and _CX0 + 4 <= x < _CX1 - 4:
        return F["glow"], .45                                   # Leiterbahnen
    v = abs(y + .5 - _YC) / ((_CY1 - _CY0) / 2)
    d = -1 if y + .5 < _YC else 1
    r = _spikes(d)[1][x]
    reach = (r - 3) / 6 if r else -.2                           # Fade folgt den Zacken
    jag = (int(_rnd(x >> 1, d, 47) * 3) - 1) * .08
    k = max(0.0, min(1.0, (v + (reach - .5) * .55 + jag - .2) / .75)) ** 1.3
    kq = min(1.0, math.floor(k * 3 + _BAYER[(y >> 1) & 3][x & 3] / 16) / 3)   # gerastert
    return mix(F["core"], F["glow"], kq), .30 + .58 * kq


def elektronik_pixel(offen, t_ms, farben="nacht"):
    """Das Symbol als Feinpixel-Raster (EL_H*6 × EL_W*2), RGB | None."""
    F = EL_FARBEN[farben]
    W, H = EL_W * FX, EL_H * FY
    a = [[0.0] * W for _ in range(H)]
    col = [[None] * W for _ in range(H)]

    def put(x, y, c, al):
        if 0 <= x < W and 0 <= y < H and al >= a[y][x]:
            a[y][x], col[y][x] = al, c

    s = _ease(min(1.0, offen / .62))                            # Klappen
    grow = _ease(max(0.0, (offen - .55) / .45))                 # Zacken
    idle = offen >= 1
    if s < .04:                                                 # zu: helle Linie
        half = _jsround(((_CX1 - _CX0) / 2) * min(1.0, offen / .04 + .35))
        for x in range(16 - half, 16 + half):
            put(x, 26, F["edge"], .9)
            put(x, 27, F["glow"], .5)
    else:
        top = _jsround(_YC - (_YC - _CY0) * s)
        bot = _jsround(_YC + (_CY1 - _YC) * s)
        shade = .45 + .55 * s
        for y in range(top, bot):                               # Klappen: zur Mitte gestaucht
            src = _jsround(_YC + (y + .5 - _YC) / s - .5)
            yy = max(_CY0, min(_CY1 - 1, src))
            for x in range(_CX0, _CX1):
                c, al = _el_flach(F, x, yy)
                put(x, y, c, al * shade)
        for d in (-1, 1):                                       # Zacken, sich verjüngend
            for n, (x0, w, L, lean) in enumerate(_spikes(d)[0]):
                ln = _jsround(L * grow)
                for k in range(1, ln + 1):
                    wk = max(1, _jsround(w * (1 - (k - 1) / (L + 1))))
                    off = 0 if lean < 0 else (w - wk if lean > 0 else (w - wk) // 2)
                    y = top - k if d < 0 else bot - 1 + k
                    if k > 2 and _rnd(n, k, d, 13) < .04 * k:
                        continue                                # selten ein Loch
                    al = max(.62, .95 * (1 - k / (L + 6)))
                    for c in range(wk):
                        a2 = al
                        if idle and _rnd(x0 + off + c, y, t_ms // 180) < .08:
                            a2 = 1                              # Glitzern
                        put(x0 + off + c, y, F["edge"] if k == ln and al > .5 else F["glow"], a2)
        for x in range(_CX0, _CX1):                             # losgelöste Pixel
            for d in (-1, 1):
                if _rnd(x, d, 17) < .28 and grow > .85:
                    y = (top - 10 - int(_rnd(x, 19) * 2)) if d < 0 else (bot + 9 + int(_rnd(x, 21) * 2))
                    put(x, y, F["glow"], (.6 + .35 * _rnd(x, y, t_ms // 240)) if idle else .65)
        if idle:                                                # Abtastlinie
            sy = _CY1 - 1 - int((t_ms % 2400) / 2400 * (_CY1 - _CY0 + 8))
            if _CY0 < sy < _CY1 - 1 and (sy < _PLATE[0] or sy >= _PLATE[1]):
                for x in range(_CX0 + 1, _CX1 - 1):
                    put(x, sy, F["edge"], .7)
    return [[mix(F["bg"], col[y][x], a[y][x]) if a[y][x] > 0 else None for x in range(W)]
            for y in range(H)]


@lru_cache(maxsize=32)
def elektronik_zellen(offen, t_ms, farben="nacht", modus="mix"):
    """Symbol als Zellen: (zeilen, schrift). zeilen[r][c] = (zeichen, fg, bg)
    oder None (leer — dort bleibt sichtbar, was darunter liegt); schrift =
    [(spalte, zeichen, fg, bg)] für `ELEKTRONIK` auf der Platte, sobald offen."""
    F = EL_FARBEN[farben]
    px = elektronik_pixel(offen, t_ms, farben)
    zeilen = []
    for r in range(EL_H):
        line = []
        for c in range(EL_W):
            fine = [px[r * FY + y][c * FX + x] for y in range(FY) for x in range(FX)]
            line.append(None if all(p is None for p in fine)
                        else zelle([p or F["bg"] for p in fine], modus))
        zeilen.append(line)
    schrift = []
    if offen > .92:
        text = "ELEKTRONIK"
        c0 = (EL_W - len(text)) // 2
        for i, ch in enumerate(text):
            z = zeilen[EL_LABEL_ZEILE][c0 + i]
            unter = z[2] if z else F["bg"]
            schrift.append((c0 + i, ch, F["label"], unter))
    return zeilen, schrift


def elektronik_pille(fern=False, farben="nacht"):
    """Farben der Pille im Rad: (grund, text) — weiter hinten blasser."""
    F = EL_FARBEN[farben]
    if fern:
        return mix(F["pill"], F["bg"], .45), mix(F["pillTxt"], F["bg"], .4)
    return F["pill"], F["pillTxt"]
