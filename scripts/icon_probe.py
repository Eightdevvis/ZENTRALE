#!/usr/bin/env python3
"""
Zeichnet die Symbole der Chat-Seitenleiste (tui/ansichten/symbole.py) so,
wie xfce4-terminal sie mit „Monospace 10" zeigt — als PNG zum Anschauen.

Warum ein eigenes Bild statt eines Screenshots (2026-10-08): das Terminal
zeichnet Zeichen je nach Block ganz verschieden. Sextanten (U+1FB00) und
Blöcke malt VTE SELBST als volle Rechtecke — grob. Braille (U+2800) hat
DejaVu Sans Mono nicht; es kommt aus der Ersatzschrift DejaVu Sans als feine
runde Punkte. Ein Bild, das alles mit einer Schrift zeichnet, lügt also.
Dieses Skript bildet beides nach: Sextanten als Rechtecke, Braille aus
DejaVu Sans, der Rest aus DejaVu Sans Mono. Symbole nur so prüfen
(memory/system/pixelstil.md).

Aufruf (System-Python mit Pillow, nicht das venv):
    python3 scripts/icon_probe.py ZIELORDNER
legt ZIELORDNER/symbole_nacht.png und symbole_tag.png an.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tui.ansichten import symbole  # noqa: E402

SCHRIFTEN = "/usr/share/fonts/truetype/dejavu/"
MONO = ImageFont.truetype(SCHRIFTEN + "DejaVuSansMono.ttf", 13)   # Monospace 10
ERSATZ = ImageFont.truetype(SCHRIFTEN + "DejaVuSans.ttf", 13)     # Braille u. a.
ZW, ZH = 8, 17                      # Zelle bei Monospace 10 / 96 dpi
ZOOM = 3

MENUE = [("search", "Search"), ("new", "New"), ("projects", "Projects"),
         ("files", "Files"), ("customize", "Customize")]


def sextant_bits(ch):
    """Sextant/Block → 6 Bits (VTE zeichnet sie als volle Rechtecke), sonst None."""
    o = ord(ch)
    if ch == "█":
        return 63
    if ch == "▌":
        return 0b010101
    if ch == "▐":
        return 0b101010
    if 0x1FB00 <= o <= 0x1FB3B:
        n = o - 0x1FB00 + 1
        for leer in (21, 42):          # die zwei, die es als ▌ ▐ schon gibt
            if n >= leer:
                n += 1
        return n
    return None


def zelle(d, spalte, zeile, ch, farbe):
    x, y = spalte * ZW, zeile * ZH
    bits = sextant_bits(ch)
    if bits is not None:
        for i in range(6):
            if bits >> i & 1:
                x0, y0 = x + (i % 2) * ZW // 2, y + (i // 2) * ZH // 3
                d.rectangle([x0, y0, x0 + ZW // 2 - 1, y0 + ZH // 3 - 1], fill=farbe)
    elif ch.strip():
        schrift = MONO if MONO.getmask(ch).getbbox() and ord(ch) < 0x2800 else ERSATZ
        d.text((x, y), ch, font=schrift, fill=farbe)


def bild(thema, pfad):
    """Wie die offene Leiste: Auf/Zu oben, darunter die fünf Einträge, je
    zwei Zeilen, Beschriftung auf der oberen; daneben gewählt (Glimmen)."""
    _g, _a, bg = symbole.FARBEN[thema]
    schrift = symbole.FARBEN[thema][0]
    zeilen = []                         # [(spalte, ch, farbe)] je Zeile
    for name, text in [("seite", "")] + MENUE:
        for r in range(symbole.HOEHE):
            z = []
            for spalte0, an in ((1, False), (20, True)):
                for i, (ch, fg, _bg) in enumerate(symbole.symbol_zellen(name, thema, an)[r]):
                    z.append((spalte0 + i, ch, fg))
                if r == 0:
                    z += [(spalte0 + 5 + k, c, schrift) for k, c in enumerate(text)]
            zeilen.append(z)
        if name == "seite":
            zeilen.append([])
    breite = 36
    img = Image.new("RGB", (breite * ZW, (len(zeilen) + 1) * ZH), bg)
    d = ImageDraw.Draw(img)
    for r, z in enumerate(zeilen):
        for spalte, ch, farbe in z:
            zelle(d, spalte, r, ch, farbe)
    img = img.resize((img.width * ZOOM, img.height * ZOOM), Image.NEAREST)
    img.save(pfad)


if __name__ == "__main__":
    ziel = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(ziel, exist_ok=True)
    for thema in ("nacht", "tag"):
        bild(thema, os.path.join(ziel, "symbole_%s.png" % thema))
    print("geschrieben nach", ziel)
