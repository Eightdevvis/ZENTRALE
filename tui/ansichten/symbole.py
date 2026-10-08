# tui/ansichten/symbole.py
#
# Die Symbole der Chat-Seitenleiste (Search, New, Projects, Files,
# Customize und das Auf/Zu der Leiste) als Braille-Punkte: 4 Felder breit,
# 2 Zeilen hoch, je Feld 2×4 Punkte — zusammen 8×8 Punkte.
#
# Warum Braille (Sasha, 08.10.2026, nach einem Bildvergleich aller
# Varianten): Sextanten zeichnet das Terminal (VTE) selbst als volle Blöcke —
# bei so kleinen Formen wirkt das grob, „dickflüssig". Braille kommt aus der
# Ersatzschrift (DejaVu Sans) als feine runde Punkte mit Luft dazwischen:
# filigran, und mit 8×8 Punkten genug für Lupe, Ordner, Blatt und Zahnrad.
# Die Varianten davor (Sextant-Pixel 4×2, ein Unicode-Zeichen je Symbol,
# umschaltbar über `tui_symbole`) sind damit raus. Regel:
# memory/system/pixelstil.md. Prüfen nur mit scripts/icon_probe.py, das
# die Ersatzschriften nachbildet.
#
# Farbe gilt je Feld: Grund '#' oder Akzent '+'. Ein Feld mit beidem gibt es
# nicht (ein Zeichen hat eine Farbe) — Akzent liegt deshalb auf Feldgrenzen
# (Spalten 0-1, 2-3, 4-5, 6-7; Zeilen 0-3, 4-7).
#
# Reine Funktionen, kein curses.

from functools import lru_cache

BREITE, HOEHE = 4, 2                    # Felder je Symbol
PUNKTE_X, PUNKTE_Y = 2, 4               # Braille-Punkte je Feld

# Braille-Punkt (x, y) im Feld → Bit (Unicode-Block U+2800: Punkte 1-2-3
# links oben nach unten, 4-5-6 rechts, 7 und 8 die untere Reihe).
BITS = {(0, 0): 1, (0, 1): 2, (0, 2): 4, (1, 0): 8,
        (1, 1): 16, (1, 2): 32, (0, 3): 64, (1, 3): 128}

# 8 Zeilen × 8 Spalten. '#' Grund, '+' Akzent, '.' leer. Ein Braille-Punkt
# sitzt in einem Raster von etwa 4×4 Bildpunkten — Kreise dürfen rund sein.
BILDER = {
    # Lupe: rundes Glas, Stiel schräg nach unten rechts
    "search":    ["..####..",
                  ".#....#.",
                  "#......#",
                  "#......#",
                  ".#....#.",
                  "..####..",
                  "......##",
                  ".......#"],
    # Plus, ganz in Akzent — das Einzige, was etwas Neues macht
    "new":       ["...++...",
                  "...++...",
                  "...++...",
                  "++++++++",
                  "...++...",
                  "...++...",
                  "...++...",
                  "........"],
    # Ordner mit Reiter
    "projects":  ["###.....",
                  "#..#....",
                  "########",
                  "#......#",
                  "#......#",
                  "#......#",
                  "########",
                  "........"],
    # Blatt mit Eselsohr
    "files":     ["#####...",
                  "#...##..",
                  "#...#.#.",
                  "#...####",
                  "#......#",
                  "#......#",
                  "########",
                  "........"],
    # Zahnrad (Sashas Wahl „z3" aus vier Entwürfen, 08.10.2026)
    "customize": ["...##...",
                  "#.####.#",
                  ".##..##.",
                  "##....##",
                  "##....##",
                  ".##..##.",
                  "#.####.#",
                  "...##..."],
    # Auf/Zu der Leiste: ein Fenster, links davon eine abgesetzte Spalte
    # (Akzent). Die Spalte ist eine Punktreihe dünn wie die übrigen Linien
    # (eine 2 Punkte breite wirkte am 08.10. im Bild zu schwer) und liegt
    # allein in den Feldern der Spalten 0-1 — so bleibt jedes Feld einfarbig.
    # Ein geschlossener Rahmen um beides hätte grüne Ecken gegeben.
    "seite":     ["+.######",
                  "+.#....#",
                  "+.#....#",
                  "+.#....#",
                  "+.#....#",
                  "+.#....#",
                  "+.######",
                  "........"],
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

# Das Zeichen hinter einem Gespräch mit Dokument — dasselbe Blatt wie bei
# Dokumenten im Verlauf. In einer Listenzeile ist für ein 4×2-Symbol kein Platz.
DOKU = "▤"


def codieren(bild):
    """Raster aus '#'/'+'/'.' → Zeilen von (Braille-Zeichen, akzent?).
    Ein Feld ist Akzent, sobald ein Punkt darin '+' ist."""
    hoehe, breite = len(bild), max((len(z) for z in bild), default=0)
    zeilen = []
    for zr in range(0, hoehe, PUNKTE_Y):
        raus = []
        for zc in range(0, breite, PUNKTE_X):
            bits, akzent = 0, False
            for (x, y), bit in BITS.items():
                r, c = zr + y, zc + x
                p = bild[r][c] if r < hoehe and c < len(bild[r]) else "."
                if p != ".":
                    bits |= bit
                    akzent = akzent or p == "+"
            raus.append((chr(0x2800 + bits), akzent))
        zeilen.append(tuple(raus))
    return tuple(zeilen)


@lru_cache(maxsize=64)
def symbol_zellen(name, thema="nacht", an=False):
    """Ein Symbol als Zeilen von Feldern:
    (((zeichen, fg, bg) × BREITE) × HOEHE). Unbekannter Name → leer."""
    thema = "tag" if thema == "tag" else "nacht"
    grund, akzent, bg = (FARBEN_AN if an else FARBEN)[thema]
    bild = BILDER.get(name)
    if not bild:
        return tuple(tuple((" ", bg, bg) for _ in range(BREITE)) for _ in range(HOEHE))
    return tuple(tuple((zeichen, akzent if akz else grund, bg) for zeichen, akz in zeile)
                 for zeile in codieren(bild))
