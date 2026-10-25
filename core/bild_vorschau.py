# core/bild_vorschau.py
#
# Ein Bild als Zeichen fürs Terminal: Sashas eigener ASCII-Filter aus dem
# alten Browser-Frontend, nach Python übertragen (2026-10-10). Vorlage:
# ui/static/ascii.js (ASCII.canvasToAscii) und der
# Foto-Filter in ui/templates/monolith.html (stretchCanvas,
# asciiColorHTML; Historie: Commit ed3c82c). Sasha wollte ausdrücklich
# diesen Filter wieder, keinen fremden (chafa o. ä.).
#
# Was er tut, wie im Original:
#   1. Bild „cover" in eine Arbeitsfläche (formatfüllend, mittig beschnitten)
#   2. Auto-Levels: jeden Farbkanal am 1-%/99-%-Perzentil aufs volle
#      0–255 ziehen (flache Fotos werden lesbar); flacher Kanal bleibt
#   3. blockweise mitteln, Helligkeit 0.299 R + 0.587 G + 0.114 B,
#      gamma, invert, auf eine Zeichen-Rampe
#   4. Modus „farbe": jedes Zeichen bekommt die Durchschnittsfarbe seines
#      Blocks, Leerzeichen keine
#
# Neu fürs Terminal: eine Zelle ist etwa doppelt so hoch wie breit
# (ZELLE_HOCH) — sonst wäre das Bild gestaucht. Und die Farben werden auf
# höchstens FARBEN_HOECHSTENS je Bild gebracht (xterm-256), weil jede Farbe
# in curses ein eigenes Farbpaar kostet und die Paare knapp sind
# (tui/ansichten/kontext.py, PIX).
#
# Pillow wird erst beim ersten Bild geladen: fehlt es (Knoten ohne
# Backend-Pakete), sagt die Vorschau das, statt beim Import umzufallen.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): weiß nichts vom
# Desk, nur Datei → Zeilen aus [zeichen, farbe|None].

import os
import threading
from collections import Counter, OrderedDict

RAMPE_FOTO = " .,:;-~=+ox*#%8B@"        # monolith.html, Foto-Filter (17 Stufen)
RAMPE_KLEIN = " .:-=+*#%@"              # ascii.js, canvasToAscii-Standard
MODI = ("mono", "farbe")
ZELLE_HOCH = 2.0                        # Zelle: Höhe / Breite
FARBEN_HOECHSTENS = 32
CACHE_GROESSE = 64
ARBEIT_JE_ZELLE = (4, 8)                # Arbeitsfläche: Pixel je Zelle (b, h)
SCHNITT = 0.01                          # Auto-Levels: 1 % / 99 %


class KeinBild(ValueError):
    """Die Datei ist da, aber kein Bild, das Pillow lesen kann."""


class OhnePillow(RuntimeError):
    """Pillow fehlt auf diesem Rechner."""


def _pil():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise OhnePillow("für die bildvorschau fehlt Pillow (requirements.txt)")
    return Image, ImageOps


# ── xterm-256 ─────────────────────────────────────────────────────────
# Kopie von rgb_256/xterm_rgb aus tui/pixel.py (2026-10-10): der Kern darf
# nicht aus tui/ importieren (Bauplan: die TUI ist eine Front über HTTP).
# Dieselbe Rechnung hier und dort heißt: die Farben, die hier gewählt
# werden, landen in der TUI auf genau denselben Paaren.
_WUERFEL = (0, 95, 135, 175, 215, 255)


def _d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def rgb_256(c):
    """Nächste xterm-256-Farbe (Würfel oder Graurampe) zu RGB."""
    def q(v):
        return min(range(6), key=lambda i: abs(_WUERFEL[i] - v))
    qi = [q(v) for v in c]
    wuerfel = tuple(_WUERFEL[i] for i in qi)
    gi = max(0, min(23, round((sum(c) / 3 - 8) / 10)))
    grau = (8 + gi * 10,) * 3
    if _d2(c, wuerfel) <= _d2(c, grau):
        return 16 + 36 * qi[0] + 6 * qi[1] + qi[2]
    return 232 + gi


def xterm_rgb(n):
    """RGB einer xterm-256-Farbnummer ab 16 (Würfel und Graurampe)."""
    if n >= 232:
        v = 8 + (n - 232) * 10
        return (v, v, v)
    i = n - 16
    return (_WUERFEL[i // 36], _WUERFEL[(i // 6) % 6], _WUERFEL[i % 6])


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def palette_kappen(farben, hoechstens=FARBEN_HOECHSTENS):
    """RGB-Liste → dieselbe Länge, jede auf xterm-256 gerundet; sind es mehr
    als `hoechstens` verschiedene, bleiben die häufigsten und der Rest nimmt
    die nächste davon."""
    nummern = [rgb_256(c) for c in farben]
    zaehlung = Counter(nummern)
    if len(zaehlung) <= hoechstens:
        bleiben = set(zaehlung)
    else:
        bleiben = {n for n, _ in zaehlung.most_common(hoechstens)}
    ersatz = {}
    for n in zaehlung:
        if n in bleiben:
            ersatz[n] = n
        else:
            c = xterm_rgb(n)
            ersatz[n] = min(bleiben, key=lambda b: _d2(c, xterm_rgb(b)))
    return [xterm_rgb(ersatz[n]) for n in nummern]


# ── Der Filter ────────────────────────────────────────────────────────

def _cover(img, breite, hoehe, Image):
    """drawImageCover: formatfüllend, mittig beschnitten."""
    iw, ih = img.size
    ziel = breite / hoehe
    if iw / ih > ziel:                          # zu breit: links/rechts weg
        nw = max(1, round(ih * ziel))
        x0 = (iw - nw) // 2
        img = img.crop((x0, 0, x0 + nw, ih))
    else:                                       # zu hoch: oben/unten weg
        nh = max(1, round(iw / ziel))
        y0 = (ih - nh) // 2
        img = img.crop((0, y0, iw, y0 + nh))
    return img.resize((breite, hoehe), Image.BILINEAR)


def auto_levels(img):
    """stretchCanvas: jeden Kanal am 1-%/99-%-Perzentil aufs volle 0–255
    ziehen. Ein flacher Kanal (hi <= lo) bleibt, wie er ist."""
    kanaele = []
    gesamt = img.size[0] * img.size[1]
    schnitt = gesamt * SCHNITT
    for k in img.split():
        hist = k.histogram()
        lo, hi, acc = 0, 255, 0
        for v in range(256):
            acc += hist[v]
            if acc >= schnitt:
                lo = v
                break
        acc = 0
        for v in range(255, -1, -1):
            acc += hist[v]
            if acc >= schnitt:
                hi = v
                break
        if hi <= lo:
            kanaele.append(k)
            continue
        sk = 255 / (hi - lo)
        # round wie im Original: ein Uint8ClampedArray rundet beim Zuweisen.
        kanaele.append(k.point([max(0, min(255, round((v - lo) * sk))) for v in range(256)]))
    Image, _ = _pil()
    return Image.merge("RGB", kanaele)


def filtern(img, spalten, zeilen, modus="mono", rampe=RAMPE_FOTO, gamma=1.0,
            invert=False, farben=FARBEN_HOECHSTENS):
    """Ein PIL-Bild → [[ [zeichen, "#rrggbb"|None], … ], …] (zeilen × spalten)."""
    Image, ImageOps = _pil()
    if modus not in MODI:
        raise ValueError("modus: mono oder farbe")
    img = ImageOps.exif_transpose(img).convert("RGB")
    aw, ah = ARBEIT_JE_ZELLE
    arbeit = auto_levels(_cover(img, spalten * aw, zeilen * ah, Image))
    # Blockmittel: BOX-Verkleinerung mittelt genau die Pixel eines Blocks —
    # dasselbe wie die Summen-Schleife in canvasToAscii.
    klein = arbeit.resize((spalten, zeilen), Image.BOX)
    bloecke = list(klein.get_flattened_data() if hasattr(klein, "get_flattened_data")
                   else klein.getdata())
    stufen = len(rampe) - 1
    zeichen = []
    for r, g, b in bloecke:
        # Gerundet (2026-10-10): 0.299+0.587+0.114 ergibt in Gleitkomma
        # knapp unter 1 — reines Weiß landete sonst eine Stufe unter „@".
        l = round((0.299 * r + 0.587 * g + 0.114 * b) / 255, 9)
        l = l ** gamma
        if invert:
            l = 1 - l
        l = max(0.0, min(1.0, l))
        zeichen.append(rampe[int(l * stufen)])
    if modus == "farbe":
        gekappt = palette_kappen(bloecke, farben)
        fg = [None if z == " " else _hex(c) for z, c in zip(zeichen, gekappt)]
    else:
        fg = [None] * len(zeichen)
    return [[[zeichen[j * spalten + i], fg[j * spalten + i]] for i in range(spalten)]
            for j in range(zeilen)]


# ── Datei → Vorschau, gemerkt ─────────────────────────────────────────

_cache = OrderedDict()
_sperre = threading.Lock()


def groesse(pfad):
    """(breite, hoehe) in Pixeln, gedreht wie die Kamera es meinte. KeinBild,
    wenn Pillow die Datei nicht lesen kann; FileNotFoundError, wenn sie fehlt."""
    Image, ImageOps = _pil()
    try:
        with Image.open(pfad) as img:
            img = ImageOps.exif_transpose(img)
            return img.size
    except FileNotFoundError:
        raise
    except Exception:
        raise KeinBild("das ist kein bild, das sich lesen lässt")


def vorschau(pfad, spalten, zeilen, modus="mono", invert=False):
    """Datei → Zeilen (siehe filtern). Gemerkt nach (pfad, mtime, spalten,
    zeilen, modus, invert) in einem kleinen LRU — ein Desk wird bei jedem
    Bild neu gezeichnet, ein Foto zu lesen kostet Zehntelsekunden."""
    if modus not in MODI:
        raise ValueError("modus: mono oder farbe")
    spalten = max(1, min(400, int(spalten)))
    zeilen = max(1, min(200, int(zeilen)))
    mtime = os.path.getmtime(pfad)              # FileNotFoundError: „weg"
    schluessel = (os.path.abspath(pfad), mtime, spalten, zeilen, modus, bool(invert))
    with _sperre:
        if schluessel in _cache:
            _cache.move_to_end(schluessel)
            return _cache[schluessel]
    Image, _ = _pil()
    try:
        with Image.open(pfad) as img:
            # JPEG gleich verkleinert dekodieren: ein 12-MP-Foto für 40×12
            # Zeichen ganz zu lesen wäre Verschwendung.
            img.draft("RGB", (spalten * ARBEIT_JE_ZELLE[0] * 2, zeilen * ARBEIT_JE_ZELLE[1] * 2))
            raus = filtern(img, spalten, zeilen, modus, invert=invert)
    except (FileNotFoundError, OhnePillow):
        raise
    except Exception:
        raise KeinBild("das ist kein bild, das sich lesen lässt")
    with _sperre:
        _cache[schluessel] = raus
        while len(_cache) > CACHE_GROESSE:
            _cache.popitem(last=False)
    return raus


def cache_leeren():
    with _sperre:
        _cache.clear()


def zellen_fuer(breite_px, hoehe_px, spalten):
    """Wie viele Zeilen braucht ein Bild bei `spalten` Zeichen Breite, damit
    es nicht gestaucht aussieht (Zelle ZELLE_HOCH mal so hoch wie breit)."""
    if not breite_px or not hoehe_px:
        return max(1, spalten // 3)
    return max(1, round(spalten * hoehe_px / breite_px / ZELLE_HOCH))


# ── Pixel-Icon fürs Rad (2026-10-10, Werkstatt) ───────────────────────
# Eine selbst gebaute App (core/werkstatt.py) bekommt ihr Symbol aus einem
# Bild in ~/Zentrale/Input. Das Rad zeichnet Symbole aus Feinpixeln
# (tui/pixel.py); ein Foto passt da nur als kleines, hartes Pixelbild:
# quadratisch beschnitten, ICON_SEITE² Pixel, wenige Farben (xterm-256 wie
# oben — jede Farbe kostet in curses ein Paar), Durchsichtiges ganz oder gar
# nicht. Gespeichert wird es als gewöhnliches PNG (icon.png neben app.toml),
# kein eigenes Format; die TUI bekommt es als Raster über HTTP.
ICON_SEITE = 16
ICON_FARBEN = 16


def _pixel_liste(img):
    """Alle Pixel als Liste (Pillow ≥ 12: get_flattened_data, getdata veraltet)."""
    f = getattr(img, "get_flattened_data", None) or img.getdata
    return list(f())


def icon_machen(quelle, seite=ICON_SEITE, farben=ICON_FARBEN) -> bytes:
    """Bild-Datei → PNG-Bytes des Pixel-Icons (seite × seite, RGBA).
    KeinBild, wenn Pillow die Datei nicht lesen kann."""
    import io
    Image, ImageOps = _pil()
    try:
        with Image.open(quelle) as roh:
            roh.draft("RGB", (seite * 8, seite * 8))
            img = ImageOps.exif_transpose(roh).convert("RGBA")
    except (FileNotFoundError, OhnePillow):
        raise
    except Exception:
        raise KeinBild("das ist kein bild, das sich lesen lässt")
    iw, ih = img.size
    k = min(iw, ih)                              # quadratisch, mittig beschnitten
    img = img.crop(((iw - k) // 2, (ih - k) // 2, (iw - k) // 2 + k, (ih - k) // 2 + k))
    img = img.resize((seite, seite), Image.LANCZOS)
    px = _pixel_liste(img)
    sichtbar = [i for i, p in enumerate(px) if p[3] >= 128]
    gekappt = palette_kappen([px[i][:3] for i in sichtbar], farben)
    neu = [(0, 0, 0, 0)] * len(px)
    for i, c in zip(sichtbar, gekappt):
        neu[i] = tuple(c) + (255,)
    img.putdata(neu)
    puffer = io.BytesIO()
    img.save(puffer, "PNG")
    return puffer.getvalue()


ICON_SEITE_APP = 32       # Symbole, die eine App mitbringt (app.toml `icon`)


def icon_raster(pfad, seite=ICON_SEITE) -> list:
    """Icon-PNG → seite Zeilen zu je seite Feldern: "#rrggbb" oder None
    (durchsichtig). Fremde Größen werden hart (NEAREST) angepasst.
    seite=None: in eigener Größe, wenn quadratisch und höchstens
    ICON_SEITE_APP, sonst auf ICON_SEITE_APP (Symbole aus App-Repos)."""
    Image, _ = _pil()
    try:
        with Image.open(pfad) as roh:
            img = roh.convert("RGBA")
    except (FileNotFoundError, OhnePillow):
        raise
    except Exception:
        raise KeinBild("das ist kein bild, das sich lesen lässt")
    if seite is None:
        w, h = img.size
        seite = w if (w == h and w <= ICON_SEITE_APP) else ICON_SEITE_APP
    if img.size != (seite, seite):
        img = img.resize((seite, seite), Image.NEAREST)
    px = _pixel_liste(img)
    return [[_hex(p[:3]) if p[3] >= 128 else None for p in px[r * seite:(r + 1) * seite]]
            for r in range(seite)]
