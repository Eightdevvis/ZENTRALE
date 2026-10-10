# tui/bausteine/farbwaehler.py
#
# Farbwähler als Modal für jede Ansicht (2026-10-10, Sasha: ein Regenbogen-
# Kreis, ein kleiner Kreis darin, den man mit den Pfeiltasten auf die Farbe
# schiebt; + / - zoomen hinein für feinere Abstufungen).
#
# Farbraum HSV (entschieden 2026-10-10): Winkel = Farbton (0° Rot rechts,
# gegen den Uhrzeigersinn über Gelb, Grün, Cyan, Blau, Magenta), Abstand zur
# Mitte = Sättigung (Mitte weiß/grau, Rand voll), Helligkeit (Value) als
# Regler rechts daneben. HSV statt HSL, weil bei HSL der Rand bei voller
# Helligkeit weiß würde und der Kreis bei 100 % nichts zeigte; HSV ist auch
# das, was die meisten Mal-Programme im Kreis zeigen.
#
# Tasten (nur gängige, terminal-sichere): Pfeile schieben den Kreis,
# + (auch =) zoomt hinein, - zoomt hinaus — der Schritt schrumpft mit dem
# Zoom; Bild↑/Bild↓ (auch ] und [) ändern die Helligkeit; # öffnet ein
# Hex-Feld (#rrggbb, CSS), Ziffern/a–f tippen, ⌫ löscht; Enter nimmt,
# Esc bricht ab (im Hex-Feld: schließt nur das Feld).
#
# Baustein-Regeln (tui_bauplan.md „Bausteine"): kennt keinen Aufrufer,
# speichert nichts. `taste(ch)` → None | ("fertig", "#rrggbb") |
# ("abbruch",). Gerechnet wird rein (`rad_zellen`, `regler`), gezeichnet
# über den Kontext der TUI (`zeichne(z, y, x, h, w)`: safe_addstr,
# pix_attr, draw_box). Farbpaare: der Kreis wird so grob gerastert, dass er
# in die freien Pixel-Paare passt (`_rad_fuer_budget`) — nie läuft das
# Budget mitten im Bild über und färbt andere Ansichten um.
# Doku: memory/system/bausteine_farbe_stil.md.

import colorsys
import curses
import math
from functools import lru_cache

try:
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

import stil as stil_kern                # core/stil.py (Pfad: bausteine/__init__.py)

ZOOM = (1, 2, 4, 8, 16)
SCHRITT = 1 / 12                        # Pfeil-Schritt bei Zoom 1 (Anteil des Radius)
WERT_SCHRITT = 0.05                     # Helligkeit je Taste bei Zoom 1
# Rasterstufen (Farbtöne, Sättigungen) je Zoom-Ausschnitt, fein → grob. Die
# erste, deren Farben ins Paar-Budget passen, gewinnt.
STUFEN = ((24, 8), (24, 6), (16, 6), (16, 5), (12, 5), (12, 4), (8, 4),
          (8, 3), (6, 3), (6, 2), (4, 2))
RESERVE = 8                             # Paare für Muster, Kreis-Marke, Rahmen
HEX_ZIFFERN = "0123456789abcdefABCDEF"
MARKE = "○"                             # einspaltig (East-Asian-Width A)

ENTER = (10, 13, curses.KEY_ENTER)
ZURUECK = (curses.KEY_BACKSPACE, 127, 8)
ESC = 27
HOCH = (curses.KEY_PPAGE, ord("]"))
RUNTER = (curses.KEY_NPAGE, ord("["))
REIN = (ord("+"), ord("="))
RAUS = (ord("-"), ord("_"))


# ── Geometrie und Farbe (rein) ──────────────────────────────────────────────
def punkt_zu_farbton(u, v):
    """Punkt im Einheitskreis (u nach rechts, v nach oben) → (farbton in
    Grad 0..360, sättigung 0..1)."""
    farbton = math.degrees(math.atan2(v, u)) % 360
    return farbton, min(1.0, math.hypot(u, v))


def farbton_zu_punkt(farbton, saettigung):
    w = math.radians(farbton)
    return saettigung * math.cos(w), saettigung * math.sin(w)


def hsv_rgb(farbton, saettigung, wert):
    r, g, b = colorsys.hsv_to_rgb((farbton % 360) / 360, saettigung, wert)
    return (round(r * 255), round(g * 255), round(b * 255))


def hsv_hex(farbton, saettigung, wert):
    return stil_kern.rgb_zu_hex(hsv_rgb(farbton, saettigung, wert))


def hex_hsv(text):
    r, g, b = stil_kern.hex_zu_rgb(text)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return h * 360, s, v


def kontrast(rgb):
    """Schwarz oder Weiß, je nachdem, was auf rgb lesbar ist."""
    hell = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    return (0, 0, 0) if hell > 140 else (255, 255, 255)


def _masse(breite, hoehe):
    """Feinpixel-Raster und Radius (in Feinpixel-Breiten) für breite×hoehe Felder."""
    W, H = breite * pixel.FX, hoehe * pixel.FY
    return W, H, min(W, H * pixel.AY) / 2


def _quantisiert(u, v, zoom, wert, stufen):
    """Farbe am Punkt, gerastert relativ zum Ausschnitt: hineinzoomen zeigt
    feinere Stufen, ohne mehr Farben (= Farbpaare) zu brauchen."""
    r = math.hypot(u, v)
    if r > 1:
        u, v = u / r, v / r
    nf, ns = stufen
    schritt_f, schritt_s = 360 / (nf * zoom), 1 / (ns * zoom)
    f, s = punkt_zu_farbton(u, v)
    f = round(f / schritt_f) * schritt_f
    s = min(1.0, round(s / schritt_s) * schritt_s)
    return hsv_rgb(f, s, wert)


@lru_cache(maxsize=64)
def rad_zellen(breite, hoehe, mitte, zoom, wert, stufen, bg, modus="mix"):
    """Der Kreis (Ausschnitt um `mitte` = (u, v) bei `zoom`) als Zeilen von
    Zellen (zeichen, fg, bg).

    Jedes Feld hat EINE Farbe (aus der Feldmitte) als Vordergrund auf dem
    Grund `bg`; am Kreisrand wählt ein Sextant (Modus "half": Halbblock),
    welcher Teil des Feldes im Kreis liegt. So kostet jede Farbe genau ein
    Farbpaar (farbe, bg) — Rand und Inneres teilen es — und die Zahl der
    Paare ist die Zahl der Farben (2026-10-10: Mischfelder mit zwei Farben
    brauchten bei 30×15 Feldern über 250 Paare, mehr als es gibt)."""
    W, H, radius = _masse(breite, hoehe)
    mu, mv = mitte
    teile = ((1, 2) if modus == "half" else (2, 3))          # Teilfelder je Zelle
    raus = []
    for r in range(hoehe):
        zeile = []
        for c in range(breite):
            bits = 0
            for j in range(teile[1]):
                for i in range(teile[0]):
                    qx = (c + (i + .5) / teile[0]) * pixel.FX
                    py = (r + (j + .5) / teile[1]) * pixel.FY
                    u = mu + (qx - W / 2) / radius / zoom
                    v = mv + (H / 2 - py) * pixel.AY / radius / zoom
                    if u * u + v * v <= 1:
                        bits |= 1 << (j * teile[0] + i)
            if not bits:
                zeile.append((" ", bg, bg))
                continue
            u = mu + ((c + .5) * pixel.FX - W / 2) / radius / zoom
            v = mv + (H / 2 - (r + .5) * pixel.FY) * pixel.AY / radius / zoom
            farbe = _quantisiert(u, v, zoom, wert, stufen)
            if modus == "half":
                ch = {1: "▀", 2: "▄", 3: "█"}[bits]
            else:
                ch = pixel.sextant(bits)
            zeile.append((ch, farbe, bg))
        raus.append(zeile)
    return raus


def paare(zellen, farbe):
    """Wie viele Farbpaare die Zellen brauchen (farbe = RGB → Terminal-Nummer)."""
    return len({(farbe(fg), farbe(bg)) for zeile in zellen for _ch, fg, bg in zeile})


def regler(wert_stufen, farbton, saettigung):
    """Helligkeits-Regler von oben (1.0) nach unten (0.0): Liste von RGB."""
    n = max(2, wert_stufen)
    return [hsv_rgb(farbton, saettigung, 1 - i / (n - 1)) for i in range(n)]


def marke_feld(breite, hoehe, mitte, zoom, punkt):
    """In welchem Feld (zeile, spalte) des Kreises der Punkt liegt."""
    W, H, radius = _masse(breite, hoehe)
    qx = W / 2 + (punkt[0] - mitte[0]) * radius * zoom
    py = H / 2 - (punkt[1] - mitte[1]) * radius * zoom / pixel.AY
    return (max(0, min(hoehe - 1, int(py // pixel.FY))),
            max(0, min(breite - 1, int(qx // pixel.FX))))


# ── Zustand und Tasten ──────────────────────────────────────────────────────
class Farbwaehler:
    """Modal: Farbe aus Kreis + Helligkeit wählen oder als Hex tippen."""
    titel = "farbe"

    def __init__(self, start=None):
        self.u = self.v = 0.0
        self.wert = 1.0
        self.zoom_stufe = 0
        self.hex_feld = None            # None = zu, sonst die getippten Ziffern
        self.fehler = ""
        self._fest = None               # genau gesetztes Hex (Start/getippt) bis zur nächsten Bewegung
        self.stufen_jetzt = None        # zuletzt gezeichnete Rasterstufe (für Tests/Anzeige)
        h = stil_kern.hex_lesen(start) if start else None
        if h:
            self.setzen(h)

    # Lesen
    @property
    def zoom(self):
        return ZOOM[self.zoom_stufe]

    @property
    def schritt(self):
        return SCHRITT / self.zoom

    @property
    def wert_schritt(self):
        return max(1 / 255, WERT_SCHRITT / self.zoom)

    @property
    def farbton(self):
        return punkt_zu_farbton(self.u, self.v)

    @property
    def hex(self):
        if self._fest:
            return self._fest
        f, s = self.farbton
        return hsv_hex(f, s, self.wert)

    @property
    def rgb(self):
        return stil_kern.hex_zu_rgb(self.hex)

    def mitte(self):
        """Mitte des sichtbaren Ausschnitts: bei Zoom 1 die Kreismitte, sonst
        der Kreis selbst — man schaut durch eine Lupe auf die Stelle."""
        return (0.0, 0.0) if self.zoom == 1 else (self.u, self.v)

    # Schreiben
    def setzen(self, text):
        h = stil_kern.hex_lesen(text)
        if not h:
            return False
        f, s, w = hex_hsv(h)
        self.u, self.v = farbton_zu_punkt(f, s)
        self.wert, self._fest = w, h
        return True

    def _schieben(self, du, dv):
        u, v = self.u + du, self.v + dv
        r = math.hypot(u, v)
        if r > 1:
            u, v = u / r, v / r
        self.u, self.v, self._fest = u, v, None

    def taste(self, ch):
        """→ None | ("fertig", "#rrggbb") | ("abbruch",)."""
        if self.hex_feld is not None:
            erg = self._taste_hex(ch)
            if erg != "weiter":
                return erg
        self.fehler = ""
        if ch == ESC:
            return ("abbruch",)
        if ch in ENTER:
            return ("fertig", self.hex)
        s = self.schritt
        if ch == curses.KEY_LEFT:
            self._schieben(-s, 0)
        elif ch == curses.KEY_RIGHT:
            self._schieben(s, 0)
        elif ch == curses.KEY_UP:
            self._schieben(0, s)
        elif ch == curses.KEY_DOWN:
            self._schieben(0, -s)
        elif ch in REIN:
            self.zoom_stufe = min(len(ZOOM) - 1, self.zoom_stufe + 1)
        elif ch in RAUS:
            self.zoom_stufe = max(0, self.zoom_stufe - 1)
        elif ch in HOCH or ch in RUNTER:
            d = self.wert_schritt * (1 if ch in HOCH else -1)
            self.wert, self._fest = max(0.0, min(1.0, self.wert + d)), None
        elif ch == ord("#"):
            self.hex_feld = ""
        return None

    def _taste_hex(self, ch):
        """Tasten im Hex-Feld. "weiter" = die Taste gehört dem Kreis."""
        if ch == ESC:
            self.hex_feld = None
            return None
        if ch in ENTER:
            if len(self.hex_feld) in (3, 6) and self.setzen("#" + self.hex_feld):
                self.hex_feld = None
                return ("fertig", self.hex)
            self.fehler = "hex: 3 oder 6 zeichen 0–9 a–f"
            return None
        if ch in ZURUECK:
            self.hex_feld = self.hex_feld[:-1]
            return None
        if ch == ord("#"):
            self.hex_feld = ""
            return None
        if 0 <= ch < 256 and chr(ch) in HEX_ZIFFERN:
            if len(self.hex_feld) < 6:
                self.hex_feld += chr(ch).lower()
                if len(self.hex_feld) == 6:
                    self.setzen("#" + self.hex_feld)     # sofort sehen
            return None
        self.hex_feld = None            # andere Taste: Feld zu, Taste gilt dem Kreis
        return "weiter"

    def tasten(self):
        return [("pfeile", "farbe"), ("+ −", "zoom"), ("bild↑↓", "helligkeit"),
                ("#", "hex"), ("enter", "nehmen"), ("esc", "zurück")]

    # ── Bild (rein) ─────────────────────────────────────────────────────
    @staticmethod
    def masse(h, w):
        """Aufteilung des Innenraums h×w: (kreis_hoehe, kreis_breite)."""
        kh = max(3, h - 2)
        kb = max(6, min(2 * kh, w - 2 - 4 - 15))
        return kh, kb

    def rad_fuer_budget(self, kh, kb, bg, farbe, budget, modus="mix"):
        """Feinste Rasterung, deren Paare ins Budget passen → (zellen, stufen);
        reicht nicht einmal die gröbste, (None, None) — dann zeigt das Modal
        nur Text."""
        mitte, wert = self.mitte(), round(self.wert, 4)
        for stufen in STUFEN:
            z = rad_zellen(kb, kh, mitte, self.zoom, wert, stufen, bg, modus)
            if paare(z, farbe) <= budget:
                return z, stufen
        return None, None

    # ── Zeichnen ────────────────────────────────────────────────────────
    @staticmethod
    def mittig(H, W, h=20, w=64):
        """(y, x, h, w) für ein Modal mittig auf einem H×W-Schirm."""
        h, w = min(h, H), min(w, W)
        return max(0, (H - h) // 2), max(0, (W - w) // 2), h, w

    def zeichne(self, z, y, x, h, w):
        """Rahmen + Inhalt in y, x, h, w über den Kontext z der TUI."""
        C = z.C
        leeren(z, y, x, h, w)
        z.draw_box(y, x, h, w, "farbe wählen", C.get("acc", 0))
        iy, ix, ih, iw = y + 1, x + 2, h - 2, w - 4
        if ih < 5 or iw < 30:
            z.safe_addstr(iy, ix, self.hex[:iw], C.get("bright", 0))
            return
        kh, kb = self.masse(ih - 1, iw)
        farbig = getattr(z, "has_color", False) and C.get("pix_bg") is not None
        if farbig:
            farbig = self._zeichne_farbig(z, iy, ix, kh, kb)
        else:
            z.safe_addstr(iy + 1, ix, "dieses terminal zeigt", C.get("dim", 0))
            z.safe_addstr(iy + 2, ix, "keine farben — # tippt hex", C.get("dim", 0))
        self._zeichne_seite(z, iy, ix + kb + 6, iw - kb - 6, farbig)
        hinweis = " · ".join("%s %s" % t for t in self.tasten())
        z.safe_addstr(y + h - 2, ix, hinweis[:iw], C.get("faint", 0))

    def _zeichne_farbig(self, z, iy, ix, kh, kb):
        C, PIX = z.C, z.PIX
        bg = C["pix_bg"]
        frei = (PIX["top"] - PIX["base"]) - len(PIX["pairs"])
        budget = frei - RESERVE - kh - 2                      # Regler + Feld
        zellen, self.stufen_jetzt = self.rad_fuer_budget(
            kh, kb, bg, z.pix_farbe, budget, getattr(z, "PIX_MODUS", "mix"))
        if zellen is None:               # nicht einmal grob: lieber Text als fremde Farben kippen
            z.safe_addstr(iy, ix, "zu wenig farben frei", C.get("dim", 0))
            return False
        for r, zeile in enumerate(zellen):
            for c, (ch, fg, hg) in enumerate(zeile):
                z.safe_addstr(iy + r, ix + c, ch, z.pix_attr(fg, hg))
        mr, mc = marke_feld(kb, kh, self.mitte(), self.zoom, (self.u, self.v))
        farbe = self.rgb
        z.safe_addstr(iy + mr, ix + mc, MARKE, z.pix_attr(kontrast(farbe), farbe))
        # Helligkeit: ein Feld je Zeile, Marke ◀ an der Stelle des Werts
        f, s = self.farbton
        stufen = regler(kh, f, s)
        for i, farbe in enumerate(stufen):
            z.safe_addstr(iy + i, ix + kb + 2, "  ", z.pix_attr(farbe, farbe))
        zeile = round((1 - self.wert) * (len(stufen) - 1))
        z.safe_addstr(iy + zeile, ix + kb + 4, "◀", C.get("bright", 0))
        return True

    def _zeichne_seite(self, z, y, x, w, farbig):
        C = z.C
        farbe = self.rgb
        if farbig:
            for i in range(3):
                z.safe_addstr(y + i, x, " " * min(w, 12), z.pix_attr(farbe, farbe))
            if not C.get("pix_true"):
                z.safe_addstr(y + 3, x, ("≈ 256: %d" % pixel.rgb_256(farbe))[:w], C.get("faint", 0))
        z.safe_addstr(y + 5, x, self.hex[:w], C.get("bright", 0))
        f, s = self.farbton
        z.safe_addstr(y + 6, x, ("%3d° %3d%% %3d%%" % (round(f), round(s * 100),
                                                    round(self.wert * 100)))[:w], C.get("dim", 0))
        z.safe_addstr(y + 7, x, ("zoom %d×" % self.zoom)[:w], C.get("dim", 0))
        if self.hex_feld is not None:
            z.safe_addstr(y + 9, x, ("#" + self.hex_feld + "_")[:w], C.get("acc", 0))
        if self.fehler:
            z.safe_addstr(y + 10, x, self.fehler[:w], C.get("warn", 0))


def leeren(z, y, x, h, w):
    """Was unter dem Modal liegt, wegwischen (ein Modal deckt ab)."""
    for i in range(h):
        z.safe_addstr(y + i, x, " " * w, z.C.get("ink", 0))
