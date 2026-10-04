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


# ── Die anderen Apps: Symbole im selben Stil (Sasha, 03.10.2026) ────────────
# "Überrasch einfach mal" — für post ein Brief, für karte ein Globus. Jedes
# Symbol nutzt dieselbe Mechanik wie Elektronik: 16×9 Zellen, zu = helle
# Linie, dann klappen Ober- und Unterhälfte auf (`s`), dann wachsen die
# Details (`g`); offen läuft eine kleine Ruhe-Animation (`t` ms). Hinter dem
# Schriftzug liegt eine abgedunkelte Platte, damit er immer lesbar bleibt.
# Ein Motiv ist eine Funktion (P, x, y, g, t) → (farbe, deckkraft) | None
# auf dem vollen, offenen 32×54-Feinraster; ry ≈ 1,5·rx ergibt einen Kreis.
_W, _H, _MX, _MY = EL_W * FX, EL_H * FY, 16, 27


def _pal(core, edge, glow, akzent, dunkel):
    return {k: _hex(v) for k, v in (("core", core), ("edge", edge), ("glow", glow),
                                     ("akzent", akzent), ("dunkel", dunkel))}


SYM_FARBEN = {
    "post":     _pal("#f3dcaa", "#fff4d6", "#c8913f", "#e0442e", "#7a4a1c"),
    "karte":    _pal("#1f6fe0", "#9fdcff", "#3aa0ff", "#4cc36a", "#0b2f6b"),
    "kalender": _pal("#eef1f6", "#ffffff", "#9aa6b8", "#ef4a52", "#3a4252"),
    "klavier":  _pal("#ece7dc", "#ffffff", "#b583ff", "#d06cff", "#17151c"),
    "notizen":  _pal("#ffd84a", "#fff3b0", "#5b8def", "#ff7a59", "#8a6a12"),
    "graph":    _pal("#22d3b4", "#b6fff0", "#14a08a", "#ffd166", "#0d4f45"),
    "fokus":    _pal("#ff8a3d", "#ffe0c2", "#ffb27a", "#ff3d5a", "#5a2410"),
    "tutor":    _pal("#ff6fb5", "#ffd1e8", "#ff9fcf", "#ffffff", "#5c1238"),
}
_GRUND = {"nacht": (_hex("#000000"), _hex("#ffffff")),     # (hintergrund, schrift)
          "tag": (_hex("#ffffff"), _hex("#001a40"))}


def _in_ellipse(x, y, cx, cy, rx, ry):
    return ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2


def _strich(x, y, ax, ay, bx, by, dicke=.75):
    """Liegt (x, y) auf der Strecke a–b (Feinpixel, y gestaucht wie im Bild)?"""
    px, py = x + .5, (y + .5) * AY
    ax, ay, bx, by = ax, ay * AY, bx, by * AY
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy or 1.0
    u = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return math.hypot(px - ax - u * vx, py - ay - u * vy) <= dicke


def _m_post(P, x, y, g, t):
    """Ein Brief: Papier, Lasche als V, unten zwei feine Falze, Wachssiegel."""
    x0, x1, y0, y1 = 3, 29, 11, 45
    if not (x0 <= x < x1 and y0 <= y < y1):
        return None
    if x in (x0, x1 - 1) or y in (y0, y1 - 1):
        return P["glow"], .95                                      # Kante
    spitze = 11 + 19 * g                                           # die Lasche klappt runter
    if _strich(x, y, x0, y0, _MX, spitze, .8) or _strich(x, y, x1 - 1, y0, _MX, spitze, .8):
        return P["glow"], .9
    if _strich(x, y, x0, y1 - 1, 12, 33, .45) or _strich(x, y, x1 - 1, y1 - 1, 20, 33, .45):
        return P["glow"], .55                                      # untere Falze
    if g > .6 and _in_ellipse(x, y, _MX, 38, 3.2, 4.6) <= 1:       # Siegel
        glanz = (t // 120) % 14 == 0 and _in_ellipse(x, y, _MX - 1, 36.5, 1.2, 1.6) <= 1
        return (P["edge"] if glanz else P["akzent"]), 1.0
    licht = .06 * (1 - (y - y0) / (y1 - y0))
    return mix(P["core"], P["edge"], licht + (.12 if y < spitze and abs(x + .5 - _MX) * 1.7 < spitze - y else 0)), .92


def _m_karte(P, x, y, g, t):
    """Ein Globus, der sich langsam dreht: Ozean, Kontinente, Gradnetz."""
    rx, ry = 13.0, 19.5
    e = _in_ellipse(x, y, _MX, _MY, rx, ry)
    if e > 1:
        return None
    if e > .86:
        return P["edge"], .9                                       # Atmosphäre / Rand
    nx = (x + .5 - _MX) / rx
    ny = (y + .5 - _MY) / ry
    lat = math.asin(max(-1.0, min(1.0, ny)))
    breite = math.sqrt(max(1e-6, 1 - ny * ny))
    lon = math.asin(max(-1.0, min(1.0, nx / breite))) + t / 3000.0  # Drehung
    land = (math.sin(2 * lon + .7) * math.cos(2.2 * lat) + .55 * math.sin(5 * lon - 1.3 + 3 * lat)
            + .35 * math.cos(3 * lon + 4 * lat))
    licht = .55 + .45 * (1 - math.hypot(nx + .35, ny + .35) / 1.6)  # Licht von links oben
    if g > 0 and land > 1.05 - .55 * g:
        return mix(P["dunkel"], P["akzent"], licht), .95
    netz = abs(((lon * 6 / math.pi) % 1) - .5) > .46 or abs(lat) < .045 or abs(abs(lat) - .55) < .03
    if netz and g > .3:
        return mix(P["core"], P["glow"], .8), .9
    return mix(P["dunkel"], P["core"], licht), .9


def _m_kalender(P, x, y, g, t):
    """Ein Kalenderblatt: Ringe, rote Kopfleiste, Raster, ein Tag blinkt."""
    x0, x1, y0, y1 = 4, 28, 9, 47
    for rx_ in (9, 22):                                            # Ringe oben
        if rx_ <= x < rx_ + 2 and 5 <= y < 12:
            return P["dunkel"], 1.0
    if not (x0 <= x < x1 and y0 <= y < y1):
        return None
    if y < 16:
        return P["akzent"], .95                                    # Kopfleiste
    if x in (x0, x1 - 1) or y == y1 - 1:
        return P["glow"], .9
    sp, ze = (x - x0 - 1) // 5, (y - 17) // 7                      # 5 Spalten, 4 Zeilen
    linie = (x - x0 - 1) % 5 == 4 or (y - 17) % 7 == 6
    if linie and g > .2:
        return P["glow"], .55 + .35 * g
    if (sp, ze) == (3, 3) and (t // 500) % 2 == 0 and g > .5:      # heute
        return P["akzent"], .85
    return P["core"], .92


def _m_klavier(P, x, y, g, t):
    """Klaviatur: sieben weisse Tasten, fünf schwarze; eine Taste leuchtet
    nach der anderen auf."""
    x0, y0, y1 = 2, 12, 43
    if not (x0 <= x < x0 + 28 and y0 <= y < y1):
        return None
    taste, innen = (x - x0) // 4, (x - x0) % 4
    lang = y0 + int(18 * g)                                        # schwarze wachsen runter
    for k in (0, 1, 3, 4, 5):                                      # zwischen C-D, D-E, F-G, G-A, A-H
        mitte = x0 + 4 * (k + 1)
        if mitte - 1 <= x < mitte + 1 and y < lang:
            return P["dunkel"], 1.0
    if innen == 3 or y == y1 - 1:
        return P["dunkel"], .9                                     # Fugen
    if taste == (t // 260) % 7:
        return mix(P["core"], P["akzent"], .65), 1.0               # gespielt
    return mix(P["core"], P["edge"], .3 * (1 - (y - y0) / (y1 - y0))), .95


def _m_notizen(P, x, y, g, t):
    """Ein Notizblock mit Linien, Rand und einer Zeile, die gerade entsteht;
    rechts unten lehnt ein Bleistift."""
    if _strich(x, y, 21, 49, 30, 31, 1.1):                         # Bleistift
        if _strich(x, y, 21, 49, 22.6, 45.8, 1.1):
            return P["dunkel"], 1.0
        if _strich(x, y, 28.6, 33.8, 30, 31, 1.1):
            return P["akzent"], 1.0
        return mix(P["akzent"], P["core"], .5), 1.0
    x0, x1, y0, y1 = 5, 25, 7, 49
    if not (x0 <= x < x1 and y0 <= y < y1):
        return None
    if y < 11:
        return (P["core"] if (x - x0) % 4 == 2 and y in (8, 9) else P["dunkel"]), 1.0
    if x == x0 + 3:
        return P["akzent"], .7                                     # Rand
    zeile = (y - 13) % 5 == 4
    if zeile and g > .2:
        if y == 37 and x0 + 5 <= x < x0 + 5 + int((t % 2400) / 2400 * 14):
            return P["dunkel"], .95                                # wird geschrieben
        return P["glow"], .45 + .3 * g
    return P["core"], .92


def _m_graph(P, x, y, g, t):
    """Ein Balkendiagramm, das steigt; die Balken wippen leise."""
    if x == 4 and 8 <= y < 47 or y == 46 and 4 <= x < 29:
        return P["glow"], .9                                       # Achsen
    for i, (bx, h) in enumerate(((7, 12), (12, 18), (17, 26), (22, 34))):
        if bx <= x < bx + 3:
            hoch = int(h * g + math.sin(t / 400 + i * 1.3) * (1.4 if g >= 1 else 0))
            top = 46 - hoch
            if top <= y < 46:
                return (P["edge"] if y == top else mix(P["glow"], P["core"], (46 - y) / 34)), .95
    return None


def _m_fokus(P, x, y, g, t):
    """Eine Zielscheibe; ein Ring pulst von innen nach aussen."""
    rx = math.sqrt(_in_ellipse(x, y, _MX, _MY, 1, 1.5))           # Abstand in rx-Einheiten
    if rx > 13:
        return None
    puls = (t % 1600) / 1600 * 13
    if g >= 1 and abs(rx - puls) < .6:
        return P["edge"], .85
    band = int(rx / 2.6)                                           # 0 = Mitte … 4 = aussen
    if band > int(g * 5):
        return None                                                # Ringe wachsen von innen
    if band == 0:
        return P["akzent"], 1.0
    return (P["core"] if band % 2 == 0 else P["dunkel"]), (.95 if band % 2 == 0 else .7)


def _m_tutor(P, x, y, g, t):
    """Eine Sprechblase, in der drei Punkte tippen."""
    if _strich(x, y, 9, 37, 6, 47, 1.3) or _strich(x, y, 9, 37, 12, 39, 1.3):
        return P["core"], .95                                      # Zipfel
    x0, x1, y0, y1 = 3, 29, 8, 39
    if not (x0 <= x < x1 and y0 <= y < y1):
        return None
    ecke = (min(x - x0, x1 - 1 - x), min(y - y0, y1 - 1 - y))
    if ecke[0] + ecke[1] * AY < 2:
        return None                                                # runde Ecken
    if ecke[0] == 0 or ecke[1] == 0:
        return P["edge"], .95
    for i, px in enumerate((10, 16, 22)):
        hub = 1 if g >= 1 and (t // 220) % 3 == i else 0
        if g > .5 and _in_ellipse(x, y, px, 34 - hub, 2.2, 3.3) <= 1:
            return P["akzent"], 1.0
    return mix(P["core"], P["edge"], .15 * (1 - (y - y0) / (y1 - y0))), .9


MOTIVE = {"post": _m_post, "karte": _m_karte, "kalender": _m_kalender,
          "klavier": _m_klavier, "notizen": _m_notizen, "graph": _m_graph,
          "fokus": _m_fokus, "tutor": _m_tutor}


def symbol_pixel(name, offen, t_ms, farben="nacht"):
    """Symbol einer App als Feinpixel-Raster (wie elektronik_pixel)."""
    if name == "elektronik":
        return elektronik_pixel(offen, t_ms, farben)
    P, motiv = SYM_FARBEN[name], MOTIVE[name]
    bg, _ = _GRUND[farben]
    s = _ease(min(1.0, offen / .62))                               # Klappen
    g = _ease(max(0.0, (offen - .55) / .45))                       # Details
    t = t_ms if offen >= 1 else 0
    px = [[None] * _W for _ in range(_H)]
    if s < .04:                                                    # zu: helle Linie
        half = _jsround(12 * min(1.0, offen / .04 + .35))
        for x in range(_MX - half, _MX + half):
            px[26][x] = mix(bg, P["edge"], .9)
            px[27][x] = mix(bg, P["glow"], .5)
        return px
    for y in range(_H):
        src = _jsround(_MY + (y + .5 - _MY) / s - .5)              # zur Mitte gestaucht
        if not 0 <= src < _H:
            continue
        for x in range(_W):
            r = motiv(P, x, src, g, t)
            if r:
                px[y][x] = mix(bg, r[0], r[1] * (.45 + .55 * s))
    if offen > .92:                                                # Platte hinter der Schrift
        n = len(name)
        x0 = (EL_W - n) // 2 * FX - 2
        for y in range(EL_LABEL_ZEILE * FY, (EL_LABEL_ZEILE + 1) * FY):
            for x in range(max(0, x0), min(_W, x0 + n * FX + 4)):
                px[y][x] = mix(px[y][x] or bg, bg, .62)
    return px


@lru_cache(maxsize=64)
def symbol_zellen(name, offen, t_ms, farben="nacht", modus="mix"):
    """Wie elektronik_zellen, für jede App mit Symbol."""
    if name == "elektronik":
        return elektronik_zellen(offen, t_ms, farben, modus)
    bg, schrift_farbe = _GRUND[farben]
    px = symbol_pixel(name, offen, t_ms, farben)
    zeilen = []
    for r in range(EL_H):
        line = []
        for c in range(EL_W):
            fine = [px[r * FY + y][c * FX + x] for y in range(FY) for x in range(FX)]
            line.append(None if all(p is None for p in fine)
                        else zelle([p or bg for p in fine], modus))
        zeilen.append(line)
    schrift = []
    if offen > .92:
        text = name.upper()
        c0 = (EL_W - len(text)) // 2
        for i, ch in enumerate(text):
            z = zeilen[EL_LABEL_ZEILE][c0 + i]
            schrift.append((c0 + i, ch, schrift_farbe, z[2] if z else bg))
    return zeilen, schrift


def _hell(c):
    """Wahrgenommene Helligkeit 0..255."""
    return .299 * c[0] + .587 * c[1] + .114 * c[2]


# Pillenfarbe je App: die kräftigste Farbe des Motivs, nicht zwingend die
# Grundfläche (Kalender und Klavier sind innen fast weiss → rot bzw. violett;
# Karte grün wie die Kontinente — Sasha, 04.10.2026).
PILLE = {"post": "core", "karte": "akzent", "kalender": "akzent",
         "klavier": "glow", "notizen": "core", "graph": "core",
         "fokus": "core", "tutor": "core"}


def bunt(c):
    """Die nächste BUNTE Farbe des 6×6×6-Würfels der 256er-Palette, als RGB.
    Blasse oder dunkle Töne fielen sonst auf die Graurampe — weggedrehte
    Pillen wurden grau (Sasha, 04.10.2026). Exakt eine Würfelfarbe, damit die
    TUI sie unverändert trifft, auch im 256er-Modus."""
    def ton(v):                                             # Farbton als Richtung
        m = sum(v) / 3
        x = [k - m for k in v]
        n = math.sqrt(sum(k * k for k in x)) or 1.0
        return [k * 100 / n for k in x]
    t0 = ton(c)
    best = None
    for r in _CUBE:
        for g in _CUBE:
            for b in _CUBE:
                if max(r, g, b) - min(r, g, b) < 40:
                    continue                                    # zu grau
                t1 = ton((r, g, b))                             # Farbton zählt mit
                d = _d2(c, (r, g, b)) + 2.5 * sum((p - q) ** 2 for p, q in zip(t0, t1))
                if best is None or d < best[0]:
                    best = (d, (r, g, b))
    return best[1]


def symbol_pille(name, fern=False, farben="nacht"):
    """Farben der Pille einer App im Rad: (grund, text) — kräftig in der
    Farbe der App (Sasha: die Pillen dürfen alle farbig sein), auch weiter
    hinten nie grau. Die Schrift nimmt hell oder dunkel, je nachdem, was
    auf dem Grund lesbar ist."""
    if name == "elektronik":
        grund, text = elektronik_pille(fern, farben)
        return bunt(grund), text
    P = SYM_FARBEN[name]
    bg, _ = _GRUND[farben]
    grund = mix(P[PILLE[name]], bg, .2 if farben == "nacht" else .1)
    if fern:
        grund = mix(grund, bg, .35)
    grund = bunt(grund)
    text = P["dunkel"] if _hell(grund) > 150 else mix(P["edge"], _hex("#ffffff"), .5)
    if fern:
        text = mix(text, grund, .35)
    return grund, text


# ── Das Auge der KI (Sasha, 04.10.2026) ─────────────────────────────────────
# Leertaste öffnet den KI-Chat; in der Mitte schaut ein grosses Auge im Stil
# der App-Symbole. `offen` 0→1: die Lider gehen auf. Offen blinzelt es ab und
# zu und schaut sich langsam um; solange die KI denkt (`denkt`), zieht sich die
# Pupille zusammen, die Iris pulst und ein Funkenring kreist.
AUGE_W, AUGE_H = 38, 14                              # Zellen ("gross", Sasha)
_AW, _AH = AUGE_W * FX, AUGE_H * FY                  # 76 × 84 Feinpixel
_AK = (_AW / 2 - 1.5) / 24.5                         # Massstab gegen den 52er-Entwurf
_ACX, _ACY, _ARX, _ARY = _AW / 2, _AH / 2 + 2, _AW / 2 - 1.5, 17.0 * _AK
AUGE_FARBEN = {
    "nacht": {"bg": _hex("#000000"), "weiss": _hex("#dfe9f2"), "schatten": _hex("#7d93a8"),
              "iris": _hex("#25c99a"), "irishell": _hex("#a6ffe0"), "irisrand": _hex("#0b4a3a"),
              "pupille": _hex("#03100c"), "rand": _hex("#9fe8d2"), "wimper": _hex("#4fd8b0")},
    "tag":   {"bg": _hex("#ffffff"), "weiss": _hex("#f4f8fb"), "schatten": _hex("#9fb2c4"),
              "iris": _hex("#14a37a"), "irishell": _hex("#6fe8bf"), "irisrand": _hex("#073b2d"),
              "pupille": _hex("#02100b"), "rand": _hex("#0b5c46"), "wimper": _hex("#0e7a5c")},
}


def _blick(t_ms):
    """Wohin schaut das Auge? Alle 1,8 s ein neues Ziel, weich angefahren.
    -> (dx, dy) in Feinpixeln."""
    seg, rest = divmod(t_ms, 1800)
    def ziel(k):
        if _rnd(k, 5) < .35:
            return 0.0, 0.0                                         # geradeaus
        return (_rnd(k, 7) * 2 - 1) * 9 * _AK, (_rnd(k, 11) * 2 - 1) * 3.5 * _AK
    a, b = ziel(seg - 1), ziel(seg)
    u = _ease(min(1.0, rest / 450))                                 # 0,45 s Blickwechsel
    return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u


def _lid(t_ms):
    """Lidöffnung 0..1 durch Blinzeln: alle ~4–6 s für 180 ms zu und wieder auf."""
    periode = 4300 + int(_rnd(t_ms // 4300, 3) * 1700)
    p = t_ms % periode
    if p < 180:
        return abs(1 - p / 90)                                      # 1 → 0 → 1
    return 1.0


def auge_zustand(offen, t_ms, denkt=False):
    """Uhrzeit → sichtbarer Zustand, grob gerastert, damit ein ruhig
    schauendes Auge aus dem Zwischenspeicher kommt statt neu gerechnet
    zu werden. -> (lid, blick_x, blick_y, puls, ring)"""
    o = _ease(max(0.0, min(1.0, offen))) * (_lid(t_ms) if offen >= 1 else 1.0)
    bx, by = _blick(t_ms) if offen >= 1 else (0.0, 0.0)
    puls = .5 + .5 * math.sin(t_ms / 160) if denkt else 0.0
    ring = (t_ms // 250) % 12 if denkt else 0
    if denkt:
        bx = by = 0.0                                               # denkend schaut es geradeaus
    return (round(o * 20) / 20, round(bx * 2) / 2, round(by * 2) / 2,
            round(puls * 4) / 4, ring)


def auge_pixel(offen, t_ms, denkt=False, farben="nacht"):
    """Das Auge als Feinpixel-Raster (_AH × _AW), RGB | None."""
    return _auge_pixel(auge_zustand(offen, t_ms, denkt), denkt, farben)


def _auge_pixel(zustand, denkt, farben):
    F = AUGE_FARBEN[farben]
    o, bx, by, puls, ring = zustand
    t_ms = ring * 250
    ir_x = 8.6 * _AK                                                # Iris-Radius (x)
    pu_x = ((2.0 + .4 * puls) if denkt else 3.3) * _AK              # Pupille
    px = [[None] * _AW for _ in range(_AH)]
    for y in range(_AH):
        for x in range(_AW):
            dx = (x + .5 - _ACX) / _ARX
            if abs(dx) >= 1:
                continue
            halb = _ARY * (1 - dx * dx) ** .85                      # Mandelform
            dy = y + .5 - _ACY
            if abs(dy) > halb * o + .6:
                # Wimpern über dem Oberlid
                if (o > .6 and dy < 0 and abs(dy) < halb * o + 4.5 * _AK
                        and int(x) % 8 == 4 and abs(dx) < .75):
                    px[y][x] = mix(F["bg"], F["wimper"], .8)
                continue
            if abs(dy) > halb * o - .9:                             # Lidrand
                px[y][x] = F["rand"]
                continue
            # Iris (Kreis: ry = 1,5·rx)
            ix, iy = (x + .5 - _ACX - bx), (y + .5 - _ACY - by) / 1.5
            r = math.hypot(ix, iy)
            if r < ir_x:
                if r < pu_x:
                    c = F["pupille"]
                    if math.hypot(ix + 1.4 * _AK, iy + 1.3 * _AK) < 1.1 * _AK:
                        c = F["irishell"]                           # Lichtpunkt
                elif r > ir_x - 1.1 * _AK:
                    c = F["irisrand"]
                else:
                    k = (r - pu_x) / (ir_x - pu_x)
                    strahl = .15 * math.sin(math.atan2(iy, ix) * 9)     # Irisfasern
                    k = min(1.0, max(0.0, k + strahl - .25 * puls))
                    kq = math.floor(k * 3 + _BAYER[y & 3][x & 3] / 16) / 3
                    c = mix(F["irishell"], F["iris"], kq)
                px[y][x] = c
                continue
            if denkt and abs(r - (ir_x + 2.2 * _AK)) < .7 * _AK:     # Funkenring
                w = math.atan2(iy, ix)
                if (math.floor((w + t_ms / 300) * 6 / math.pi)) % 3 == 0:
                    px[y][x] = F["irishell"]
                    continue
            schatten = max(0.0, min(1.0, (abs(dx) - .55) / .45)) * .6 + \
                max(0.0, -dy / halb) * .25 if halb else 0
            px[y][x] = mix(F["weiss"], F["schatten"], schatten)
    return px


def auge_zellen(offen, t_ms, denkt=False, farben="nacht", modus="mix"):
    """Das Auge als Zellen: zeilen[r][c] = (zeichen, fg, bg) oder None."""
    return _auge_zellen(auge_zustand(offen, t_ms, denkt), denkt, farben, modus)


@lru_cache(maxsize=256)
def _auge_zellen(zustand, denkt, farben, modus):
    F = AUGE_FARBEN[farben]
    px = _auge_pixel(zustand, denkt, farben)
    zeilen = []
    for r in range(AUGE_H):
        line = []
        for c in range(AUGE_W):
            fine = [px[r * FY + y][c * FX + x] for y in range(FY) for x in range(FX)]
            line.append(None if all(p is None for p in fine)
                        else zelle([p or F["bg"] for p in fine], modus))
        zeilen.append(line)
    return zeilen
