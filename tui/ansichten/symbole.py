# tui/ansichten/symbole.py
#
# Kleine Pixel-Symbole für die Seitenleiste des Chats (2026-10-07). Sasha:
# „für icons kannst du dann btw unseren pixelart stil nehmen den wir in der
# tui schon haben". Dieselben Sextant-Pixel wie die großen Symbole des Rads
# (pixel.py), nur winzig: ein Symbol ist 3 Felder breit und 1 Feld hoch, je
# Feld 2×3 Pixel → 6×3 Pixel. Ein Pixel ist ~4,5 breit und 6 hoch, das
# Symbol also etwa 27×18 — wie ein breites Emoji in der Zeile.
#
# Warum nicht pixel.zellen (2×6 Feinpixel je Feld): bei EINER Zeile Höhe
# mittelt es je zwei Feinpixel-Zeilen, die Formen werden Brei (am
# 07.10.2026 als Bild geprüft). Hier wird jedes Feld direkt als Sextant
# gesetzt, eine Farbe je Feld: Grund '#' oder Akzent '+' (wer im Feld einen
# Akzent-Pixel hat, ist Akzent). Wenige Farben, kantig — Regeln in
# memory/system/pixelstil.md.
#
# Reine Funktionen, kein curses: symbol_zellen(name, thema) → [(zeichen, fg, bg)].

from functools import lru_cache

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

BREITE = 3                              # Felder je Symbol

# 3 Zeilen × 6 Spalten. '#' Grund, '+' Akzent, '.' leer.
BILDER = {
    "search":    [".###..",
                  "#...#.",
                  ".###++"],
    "new":       ["..++..",
                  "++++++",
                  "..++.."],
    "projects":  ["##....",
                  "######",
                  "######"],
    "files":     ["####..",
                  "#..##.",
                  "#####."],
    "customize": ["#.####",
                  "####.#",
                  "##.###"],
    "chats":     ["######",
                  "#.++.#",
                  "######"],
    "seite":     ["######",
                  "++#..#",
                  "######"],
    "outputs":   ["#####.",
                  "#.++#.",
                  "######"],
}

# Farben je Thema: (grund, akzent, hintergrund) — die Grundfarbe ist die
# Schrift der Leiste, der Akzent das Grün des Auges (dieselbe KI).
FARBEN = {
    "nacht": ((0x9a, 0xa8, 0xb4), (0x1f, 0xb8, 0x8c), (0, 0, 0)),
    "tag":   ((0x4a, 0x55, 0x68), (0x0b, 0x7a, 0x5c), (255, 255, 255)),
}
# Gewählt/Fokus: dieselben Formen, heller bzw. kräftiger (Glimmen).
FARBEN_AN = {
    "nacht": ((0xff, 0xff, 0xff), (0x9d, 0xf5, 0xd6), (0, 0, 0)),
    "tag":   ((0x00, 0x1a, 0x40), (0x07, 0x3b, 0x2d), (255, 255, 255)),
}


@lru_cache(maxsize=64)
def symbol_zellen(name, thema="nacht", an=False):
    """Ein Symbol als Felder: ((zeichen, fg, bg), …) — BREITE Stück.
    Unbekannter Name → leere Felder."""
    thema = "tag" if thema == "tag" else "nacht"
    grund, akzent, bg = (FARBEN_AN if an else FARBEN)[thema]
    bild = BILDER.get(name)
    if not bild:
        return tuple((" ", bg, bg) for _ in range(BREITE))
    raus = []
    for c in range(BREITE):
        bits, farbe = 0, grund
        for y in range(3):
            for x in range(2):
                p = bild[y][c * 2 + x]
                if p != ".":
                    bits |= 1 << (y * 2 + x)
                if p == "+":
                    farbe = akzent
        raus.append((pixel.sextant(bits), farbe, bg))
    return tuple(raus)


# Das kleine Zeichen hinter einem Gespräch mit Dokument (1 Feld, wie 🗎):
# ein Blatt mit umgeknickter Ecke — oben nur links, darunter voll.
DOKU = pixel.sextant(1 | 4 | 8 | 16 | 32)
