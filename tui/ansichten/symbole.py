# tui/ansichten/symbole.py
#
# Die Symbole der Chat-Seitenleiste (Search, New, Projects, Files,
# Customize und das Auf/Zu der Leiste) in zwei umschaltbaren Arten
# (Einstellung `tui_symbole`, 2026-10-08):
#
#   pixel2   Pixel-Symbole im Pixelstil der TUI (pixel.py), 4 Felder breit
#            und 2 Zeilen hoch — je Feld 2×3 Sextant-Pixel, zusammen 8×6
#            Pixel, also etwa 36×36 Bildpunkte: ein quadratisches Symbol.
#   zeichen  ein einzelnes klares Unicode-Zeichen in der Akzentfarbe.
#
# Warum zwei Zeilen (Sasha, 08.10.2026: „die icons oben links sehen echt..
# schlecht aus. man erkennt gar nichts."): bis dahin war ein Symbol 3×1
# Felder = 6×3 Pixel. Drei Pixel Höhe reichen für keine Form — eine Lupe,
# ein Ordner und ein Blatt sahen gleich aus. Regel seitdem
# (memory/system/pixelstil.md): Pixel-Symbole nie kleiner als 2 Zeilen.
# Die Zeichen-Art gibt es daneben, damit Sasha vergleichen kann.
#
# Jedes Feld wird direkt als Sextant gesetzt, eine Farbe je Feld: Grund
# '#' oder Akzent '+' (wer im Feld einen Akzent-Pixel hat, ist Akzent).
# Deshalb liegen die Akzent-Teile der Bilder auf Feldgrenzen (Spalten 0-1,
# 2-3, 4-5, 6-7; Zeilen 0-2, 3-5).
#
# Reine Funktionen, kein curses.

from functools import lru_cache

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

ARTEN = ("pixel2", "zeichen")
STANDARD = "pixel2"

BREITE, HOEHE = 4, 2                    # pixel2: Felder je Symbol

# 6 Zeilen × 8 Spalten. '#' Grund, '+' Akzent, '.' leer. Ein Pixel ist
# etwa 4,5 breit und 6 hoch — Kreise sind deshalb breiter als hoch gezeichnet.
# Die unterste Pixelzeile bleibt meist leer: so stoßen zwei Symbole
# untereinander nicht aneinander, ohne dass eine ganze Leerzeile nötig ist.
BILDER = {
    # Lupe: Glas oben links, Stiel schräg nach unten rechts
    "search":    [".####...",
                  "#....#..",
                  "#....#..",
                  ".####.#.",
                  "......##",
                  "........"],
    # Plus, ganz in Akzent — das Einzige, was etwas Neues macht
    "new":       ["...++...",
                  "...++...",
                  "++++++++",
                  "...++...",
                  "...++...",
                  "........"],
    # Ordner mit Reiter
    "projects":  ["###.....",
                  "########",
                  "#......#",
                  "#......#",
                  "########",
                  "........"],
    # Blatt mit Eselsohr (Textzeilen darin machten es am 08.10. unruhig)
    "files":     [".####...",
                  ".#..##..",
                  ".#...#..",
                  ".#...#..",
                  ".#####..",
                  "........"],
    # Zahnrad mit Loch, Zähne auch schräg. Als einziges alle 6 Zeilen hoch:
    # in 5 sah es aus wie ein Käfer, gerade Zähne allein wie #, Regler wie ⇆
    # (alles am 08.10. als Bild verglichen). Es steht im Menü zuletzt, also
    # stößt nichts von unten an.
    "customize": ["#.####.#",
                  ".######.",
                  "###..###",
                  "###..###",
                  ".######.",
                  "#.####.#"],
    # Auf/Zu der Leiste: ein Fenster mit Spalte links (Akzent)
    "seite":     ["########",
                  "++#....#",
                  "++#....#",
                  "++#....#",
                  "########",
                  "........"],
}

# Die Zeichen-Art: in DejaVu Sans Mono (Monospace in xfce4-terminal)
# vorhanden und einspaltig — East-Asian-Width N oder A (VTE zeichnet A
# schmal, solange „ambiguous width" nicht auf breit steht; ● ▤ nutzt die
# TUI schon lange). Keine Emoji, kein ＋ (Vollbreite). Geprüft 2026-10-08.
ZEICHEN = {"search": "⌕", "new": "✚", "projects": "▦", "files": "▤",
           "customize": "⚙", "seite": "◧"}

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
# Files und bei Dokumenten im Verlauf. Bis 08.10. ein Sextant (1 Feld, nicht
# zu erkennen); in einer Listenzeile ist für ein Pixel-Symbol kein Platz.
DOKU = "▤"


def art(wert):
    """Einstellungswert → "pixel2" | "zeichen"; Unbekanntes → Standard."""
    w = str(wert or "").strip().lower()
    return w if w in ARTEN else STANDARD


def groesse(wie):
    """(Breite, Höhe) eines Symbols in Feldern."""
    return (BREITE, HOEHE) if art(wie) == "pixel2" else (1, 1)


@lru_cache(maxsize=64)
def symbol_zellen(name, thema="nacht", an=False):
    """Ein Pixel-Symbol als Zeilen von Feldern:
    (((zeichen, fg, bg) × BREITE) × HOEHE). Unbekannter Name → leer."""
    thema = "tag" if thema == "tag" else "nacht"
    grund, akzent, bg = (FARBEN_AN if an else FARBEN)[thema]
    bild = BILDER.get(name)
    if not bild:
        return tuple(tuple((" ", bg, bg) for _ in range(BREITE)) for _ in range(HOEHE))
    zeilen = []
    for r in range(HOEHE):
        raus = []
        for c in range(BREITE):
            bits, farbe = 0, grund
            for y in range(3):
                for x in range(2):
                    p = bild[r * 3 + y][c * 2 + x]
                    if p != ".":
                        bits |= 1 << (y * 2 + x)
                    if p == "+":
                        farbe = akzent
            raus.append((pixel.sextant(bits), farbe, bg))
        zeilen.append(tuple(raus))
    return tuple(zeilen)


def zeichen(name):
    """Das Zeichen der Zeichen-Art (unbekannt → ·)."""
    return ZEICHEN.get(name, "·")
