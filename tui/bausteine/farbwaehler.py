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
# Tasten (nur gängige, terminal-sichere): Pfeile schieben den Cursor um
# genau ein Feld, + (auch =) zoomt hinein, - zoomt hinaus; Bild↑/Bild↓ (auch ] und [) ändern die Helligkeit; # öffnet ein
# Hex-Feld (#rrggbb, CSS), Ziffern/a–f tippen, ⌫ löscht; Enter nimmt,
# Esc bricht ab (im Hex-Feld: schließt nur das Feld).
#
# Baustein-Regeln (tui_bauplan.md „Bausteine"): kennt keinen Aufrufer,
# speichert nichts. `taste(ch)` → None | ("fertig", "#rrggbb") |
# ("abbruch",). Gerechnet wird rein (`rad_zellen`, `regler`), gezeichnet
# über den Kontext der TUI (`zeichne(z, y, x, h, w)`: safe_addstr,
# pix_attr, draw_box). Zwei Farbwege (2026-10-11): mit 24 Bit (Kontext.echt,
# tui/echtfarbe.py) malt `rad_echt` exakte Halbblöcke an curses vorbei;
# sonst über Farbpaare — der Kreis wird so grob gerastert, dass er in die
# freien Pixel-Paare passt (`rad_fuer_budget`), nie läuft das Budget mitten
# im Bild über und färbt andere Ansichten um.
# Doku: memory/hub/bausteine_farbe_stil.md.

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
# Ein Pfeil = genau ein Feld (2026-10-11, vorher 1/12 Radius = 1,4 × 0,7 Felder).
RAND = 2                                # Felder Abstand zum Rand, ab dem der Ausschnitt mitwandert
MASS_ERSATZ = (17, 35)                  # (hoehe, breite) des Kreises, bevor er einmal gezeichnet war
# 256 Farben: hineinzoomen nur, solange mindestens dieser Anteil benachbarter
# Felder verschiedene Terminal-Farben zeigt (sonst nur noch breite Stufen).
GRENZE_256 = 0.25
FEINER_NICHT = "feiner geht hier nicht"
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


def _masse(breite, hoehe, seiten=pixel.ZELL_SEITEN_ERSATZ):
    """Feinpixel-Raster und Radius (in Feinpixel-Breiten) für breite×hoehe Felder;
    seiten = Zellhöhe/Zellbreite (pixel.zell_seiten)."""
    W, H = breite * pixel.FX, hoehe * pixel.FY
    return W, H, min(W, H * pixel.zell_ay(seiten)) / 2


def radius_spalten(breite, hoehe, seiten):
    """Radius des Kreises bei Zoom 1, gemessen in Spaltenbreiten."""
    return min(breite, hoehe * seiten) / 2


def zelle_punkt(breite, hoehe, blick, zoom, seiten, r, c):
    """Mitte der Zelle (r, c) im Ausschnitt → Punkt (u, v) im Einheitskreis.
    blick = Kreispunkt in der Mitte des Ausschnitts."""
    k = radius_spalten(breite, hoehe, seiten) * zoom
    return (blick[0] + ((c + .5) - breite / 2) / k,
            blick[1] + (hoehe / 2 - (r + .5)) * seiten / k)


def punkt_zelle(breite, hoehe, blick, zoom, seiten, punkt):
    """Punkt (u, v) → (zeile, spalte) als Kommazahlen (Zellmitte = x,5)."""
    k = radius_spalten(breite, hoehe, seiten) * zoom
    return (hoehe / 2 - (punkt[1] - blick[1]) * k / seiten,
            breite / 2 + (punkt[0] - blick[0]) * k)


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
def rad_zellen(breite, hoehe, mitte, zoom, wert, stufen, bg, modus="mix",
               seiten=pixel.ZELL_SEITEN_ERSATZ):
    """Der Kreis (Ausschnitt um `mitte` = (u, v) bei `zoom`) als Zeilen von
    Zellen (zeichen, fg, bg) — der Weg über curses-Farbpaare (256 Farben).

    Jedes Feld hat EINE Farbe (aus der Feldmitte) als Vordergrund auf dem
    Grund `bg`; am Kreisrand wählt ein Sextant (Modus "half": Halbblock),
    welcher Teil des Feldes im Kreis liegt. So kostet jede Farbe genau ein
    Farbpaar (farbe, bg) — Rand und Inneres teilen es — und die Zahl der
    Paare ist die Zahl der Farben (2026-10-10: Mischfelder mit zwei Farben
    brauchten bei 30×15 Feldern über 250 Paare, mehr als es gibt)."""
    teile = ((1, 2) if modus == "half" else (2, 3))          # Teilfelder je Zelle
    raus = []
    for r in range(hoehe):
        zeile = []
        for c in range(breite):
            bits = 0
            for j in range(teile[1]):
                for i in range(teile[0]):
                    u, v = zelle_punkt(breite, hoehe, mitte, zoom, seiten,
                                       r + (j + .5) / teile[1] - .5,
                                       c + (i + .5) / teile[0] - .5)
                    if u * u + v * v <= 1:
                        bits |= 1 << (j * teile[0] + i)
            if not bits:
                zeile.append((" ", bg, bg))
                continue
            u, v = zelle_punkt(breite, hoehe, mitte, zoom, seiten, r, c)
            farbe = _quantisiert(u, v, zoom, wert, stufen)
            if modus == "half":
                ch = {1: "▀", 2: "▄", 3: "█"}[bits]
            else:
                ch = pixel.sextant(bits)
            zeile.append((ch, farbe, bg))
        raus.append(zeile)
    return raus


def _farbe_genau(u, v, wert, kante, bg):
    """Exakte Farbe am Punkt, am Kreisrand weich in den Grund (kante = eine
    Pixelbreite im Einheitskreis)."""
    d = math.hypot(u, v)
    deckung = max(0.0, min(1.0, (1 - d) / kante + .5))
    if deckung <= 0:
        return bg
    f, s = punkt_zu_farbton(u, v)
    farbe = hsv_rgb(f, min(1.0, s), wert)
    return farbe if deckung >= 1 else pixel.mix(bg, farbe, deckung)


@lru_cache(maxsize=16)
def rad_echt(breite, hoehe, blick, zoom, wert, seiten, bg):
    """Der Kreis für 24 Bit: je Zelle ein Halbblock ▀ mit zwei exakten
    Farben (oben = Vordergrund, unten = Hintergrund). Ein Halbpixel ist
    1 × seiten/2 Spaltenbreiten — bei 1:2-Zellen quadratisch. Keine
    Rasterung, keine Paare: jede Zelle zeigt die Farbe, die dort liegt."""
    k = radius_spalten(breite, hoehe, seiten) * zoom
    kante = min(1.0, seiten / 2) / k
    raus = []
    for r in range(hoehe):
        zeile = []
        for c in range(breite):
            oben = zelle_punkt(breite, hoehe, blick, zoom, seiten, r - .25, c)
            unten = zelle_punkt(breite, hoehe, blick, zoom, seiten, r + .25, c)
            zeile.append(("▀", _farbe_genau(*oben, wert, kante, bg),
                          _farbe_genau(*unten, wert, kante, bg)))
        raus.append(zeile)
    return raus


def unterscheidbar(zellen, farbe):
    """Anteil der Nachbarzellen im Kreis (waagerecht und senkrecht), die das
    Terminal in VERSCHIEDENEN Farben zeigt (farbe = RGB → Terminal-Farbe).
    Klein heißt: das Bild besteht aus breiten Stufen gleicher Farbe."""
    gleich = anders = 0
    for r, zeile in enumerate(zellen):
        for c, (ch, fg, _bg) in enumerate(zeile):
            if ch == " ":
                continue
            for r2, c2 in ((r, c + 1), (r + 1, c)):
                if r2 < len(zellen) and c2 < len(zellen[r2]) and zellen[r2][c2][0] != " ":
                    if farbe(fg) == farbe(zellen[r2][c2][1]):
                        gleich += 1
                    else:
                        anders += 1
    return anders / max(1, gleich + anders)


def paare(zellen, farbe):
    """Wie viele Farbpaare die Zellen brauchen (farbe = RGB → Terminal-Nummer)."""
    return len({(farbe(fg), farbe(bg)) for zeile in zellen for _ch, fg, bg in zeile})


def regler(wert_stufen, farbton, saettigung):
    """Helligkeits-Regler von oben (1.0) nach unten (0.0): Liste von RGB."""
    n = max(2, wert_stufen)
    return [hsv_rgb(farbton, saettigung, 1 - i / (n - 1)) for i in range(n)]


def marke_feld(breite, hoehe, mitte, zoom, punkt, seiten=pixel.ZELL_SEITEN_ERSATZ):
    """In welchem Feld (zeile, spalte) des Kreises der Punkt liegt."""
    r, c = punkt_zelle(breite, hoehe, mitte, zoom, seiten, punkt)
    return (max(0, min(hoehe - 1, math.floor(r))),
            max(0, min(breite - 1, math.floor(c))))


def _ungerade(n):
    """Ungerade Felderzahl: dann liegt die Kreismitte in der Mitte EINES
    Feldes, und der Cursor kann sie genau treffen."""
    return n if n % 2 else n - 1


# ── Zustand und Tasten ──────────────────────────────────────────────────────
class Farbwaehler:
    """Modal: Farbe aus Kreis + Helligkeit wählen oder als Hex tippen.

    Zustand (2026-10-11): Farbton, Sättigung, Helligkeit (HSV) und der
    Ausschnitt `blick` als eigener Zustand. Vorher stand der Cursor als
    Kreispunkt (u, v) im Zustand, der Pfeil schob um 1/12 Radius — das sind
    1,4 Spalten bzw. 0,7 Zeilen, deshalb bewegte jeder dritte Druck senkrecht
    nichts (gemessen: 4 von 6). Und ab Zoom 2 war der Ausschnitt immer um
    den Cursor zentriert: jeder Druck schob das ganze Bild darunter weg
    (gemessen: 180–210 von 578 Zellen anders je Druck)."""
    titel = "farbe"

    def __init__(self, start=None):
        self.farbton_grad, self.saettigung = 0.0, 0.0
        self.wert = 1.0
        self.zoom_stufe = 0
        self.blick = (0.0, 0.0)          # Kreispunkt in der Mitte des Ausschnitts
        self.hex_feld = None            # None = zu, sonst die getippten Ziffern
        self.fehler = ""
        self.hinweis = ""               # z. B. „feiner geht hier nicht"
        self._fest = None               # genau gesetztes Hex (Start/getippt) bis zur nächsten Bewegung
        self.stufen_jetzt = None        # zuletzt gezeichnete Rasterstufe (für Tests/Anzeige)
        self._stufen_je_zoom = {}       # 256er-Weg: Raster je Zoom fest (wird nur gröber)
        # Maße des zuletzt gezeichneten Kreises (breite, hoehe, zellform) und
        # der Farbweg ("echt" 24 Bit | "256" | "paare" curses-24-Bit | None):
        # die Tasten rechnen in Feldern dieses Bildes.
        self.geo = (MASS_ERSATZ[1], MASS_ERSATZ[0], pixel.ZELL_SEITEN_ERSATZ)
        self.weg = None
        self.farbe_256 = pixel.rgb_256  # RGB → Terminal-Farbe für den 256er-Weg
        h = stil_kern.hex_lesen(start) if start else None
        if h:
            self.setzen(h)

    # Lesen
    @property
    def zoom(self):
        return ZOOM[self.zoom_stufe]

    @property
    def u(self):
        return farbton_zu_punkt(self.farbton_grad, self.saettigung)[0]

    @property
    def v(self):
        return farbton_zu_punkt(self.farbton_grad, self.saettigung)[1]

    @property
    def wert_schritt(self):
        return max(1 / 255, WERT_SCHRITT / self.zoom)

    @property
    def farbton(self):
        return self.farbton_grad % 360, self.saettigung

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
        der verankerte Ausschnitt (wandert erst, wenn der Cursor an den Rand
        kommt)."""
        return (0.0, 0.0) if self.zoom == 1 else self.blick

    def zelle(self):
        """(zeile, spalte) des Cursors im Ausschnitt (Kommazahlen)."""
        b, h, seiten = self.geo
        return punkt_zelle(b, h, self.mitte(), self.zoom, seiten, (self.u, self.v))

    # Schreiben
    def setzen(self, text):
        h = stil_kern.hex_lesen(text)
        if not h:
            return False
        f, s, w = hex_hsv(h)
        if s > 0:
            self.farbton_grad = f
        self.saettigung, self.wert, self._fest = s, w, h
        self._verankern()
        return True

    def _punkt(self, u, v):
        r = math.hypot(u, v)
        if r > 1:
            u, v = u / r, v / r
        f, s = punkt_zu_farbton(u, v)
        if s > 1e-9:                    # in der Mitte bleibt der Farbton stehen
            self.farbton_grad = f
        self.saettigung, self._fest = min(1.0, s), None

    def _verankern(self):
        """Ausschnitt so legen, dass der Cursor genau in der Mitte des
        mittleren Feldes steht (ungerade Felderzahl) — danach liegen alle
        Schritte auf Feldmitten."""
        self.blick = (self.u, self.v) if self.zoom > 1 else (0.0, 0.0)

    def _pfeil(self, dr, dc):
        """Genau ein Feld weiter: auf die Mitte des Nachbarfeldes. Am Rand
        des Ausschnitts (RAND Felder) wandert der Ausschnitt um ganze Felder
        mit — so bleibt alles auf dem Raster und das Bild springt nicht."""
        b, h, seiten = self.geo
        r, c = self.zelle()
        r, c = math.floor(r) + dr, math.floor(c) + dc
        if self.zoom > 1:
            k = radius_spalten(b, h, seiten) * self.zoom
            rand = min(RAND, (min(b, h) - 1) // 2)
            dx = min(0, c - rand) + max(0, c - (b - 1 - rand))
            dy = min(0, r - rand) + max(0, r - (h - 1 - rand))
            if dx or dy:
                self.blick = (self.blick[0] + dx / k, self.blick[1] - dy * seiten / k)
                r, c = r - dy, c - dx
        self._punkt(*zelle_punkt(b, h, self.mitte(), self.zoom, seiten, r, c))

    def _zoomen(self, d):
        neu = max(0, min(len(ZOOM) - 1, self.zoom_stufe + d))
        if neu == self.zoom_stufe:
            if d > 0:
                self.hinweis = FEINER_NICHT
            return
        if d > 0 and self.weg in ("256", "paare") and not self._zoom_lohnt(ZOOM[neu]):
            self.hinweis = FEINER_NICHT
            return
        self.zoom_stufe = neu
        self._verankern()

    def _zoom_lohnt(self, zoom):
        """256 Farben (oder curses-24-Bit auf 16er-Stufen): hineinzoomen nur, solange benachbarte Felder dort noch
        verschiedene Terminal-Farben zeigen. Dahinter kämen nur breite
        Stufen gleicher Farbe (gemessen vorher: Zoom 16 = 4 Farben)."""
        b, h, seiten = self.geo
        zellen = rad_zellen(b, h, (self.u, self.v), zoom, round(self.wert, 4),
                            STUFEN[0], (0, 0, 0), "half", seiten)
        return unterscheidbar(zellen, self.farbe_256) >= GRENZE_256

    def taste(self, ch):
        """→ None | ("fertig", "#rrggbb") | ("abbruch",)."""
        if self.hex_feld is not None:
            erg = self._taste_hex(ch)
            if erg != "weiter":
                return erg
        self.fehler = self.hinweis = ""
        if ch == ESC:
            return ("abbruch",)
        if ch in ENTER:
            return ("fertig", self.hex)
        if ch == curses.KEY_LEFT:
            self._pfeil(0, -1)
        elif ch == curses.KEY_RIGHT:
            self._pfeil(0, 1)
        elif ch == curses.KEY_UP:
            self._pfeil(-1, 0)
        elif ch == curses.KEY_DOWN:
            self._pfeil(1, 0)
        elif ch in REIN:
            self._zoomen(1)
        elif ch in RAUS:
            self._zoomen(-1)
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
    def masse(h, w, seiten=pixel.ZELL_SEITEN_ERSATZ):
        """Aufteilung des Innenraums h×w: (kreis_hoehe, kreis_breite), beide
        ungerade; die Breite folgt der Zellform, damit der Kreis rund ist."""
        kh = max(3, _ungerade(h - 2))
        kb = max(5, _ungerade(min(round(kh * seiten) + 1, w - 2 - 4 - 15)))
        return kh, kb

    def _geo_setzen(self, kh, kb, seiten):
        geo = (kb, kh, seiten)
        if geo != self.geo:
            self.geo = geo
            self._verankern()            # neues Raster: Cursor wieder auf eine Feldmitte

    def rad_fuer_budget(self, kh, kb, bg, farbe, budget, modus="mix",
                        seiten=pixel.ZELL_SEITEN_ERSATZ):
        """Feinste Rasterung, deren Paare ins Budget passen → (zellen, stufen);
        reicht nicht einmal die gröbste, (None, None) — dann zeigt das Modal
        nur Text. Je Zoom bleibt das Raster fest (2026-10-11): begonnen wird
        bei der Stufe, die für diesen Zoom schon galt — es wird höchstens
        gröber, nie springt es beim Schieben hin und her."""
        mitte, wert = self.mitte(), round(self.wert, 4)
        start = self._stufen_je_zoom.get(self.zoom, 0)
        for i in range(start, len(STUFEN)):
            z = rad_zellen(kb, kh, mitte, self.zoom, wert, STUFEN[i], bg, modus, seiten)
            if paare(z, farbe) <= budget:
                self._stufen_je_zoom[self.zoom] = i
                return z, STUFEN[i]
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
        seiten = pixel.zell_seiten()
        kh, kb = self.masse(ih - 1, iw, seiten)
        self._geo_setzen(kh, kb, seiten)
        farbig = getattr(z, "has_color", False) and C.get("pix_bg") is not None
        echt = farbig and getattr(z, "echt", None) is not None
        if echt:
            self.weg = "echt"
            self._zeichne_echt(z, iy, ix, kh, kb)
        elif farbig:
            self.weg = "paare" if C.get("pix_true") else "256"
            farbig = self._zeichne_farbig(z, iy, ix, kh, kb)
        else:
            self.weg = None
            z.safe_addstr(iy + 1, ix, "dieses terminal zeigt", C.get("dim", 0))
            z.safe_addstr(iy + 2, ix, "keine farben — # tippt hex", C.get("dim", 0))
        self._zeichne_seite(z, iy, ix + kb + 6, iw - kb - 6, farbig, echt)
        hinweis = " · ".join("%s %s" % t for t in self.tasten())
        z.safe_addstr(y + h - 2, ix, hinweis[:iw], C.get("faint", 0))

    def _marke(self, kh, kb):
        b, h, seiten = self.geo
        return marke_feld(kb, kh, self.mitte(), self.zoom, (self.u, self.v), seiten)

    def _zeichne_echt(self, z, iy, ix, kh, kb):
        """24 Bit (tui/echtfarbe.py): Kreis, Marke und Regler als eine Fläche
        exakter Farben; curses sieht dort nur den Platzhalter."""
        bg = z.C["pix_bg"]
        zellen = [list(zeile) for zeile in
                  rad_echt(kb, kh, self.mitte(), self.zoom, round(self.wert, 4),
                           self.geo[2], bg)]
        self.stufen_jetzt = None
        mr, mc = self._marke(kh, kb)
        farbe = self.rgb
        zellen[mr][mc] = (MARKE, kontrast(farbe), farbe)
        f, s = self.farbton
        stufen = regler(kh, f, s)
        zeile_wert = round((1 - self.wert) * (len(stufen) - 1))
        for i, stufe in enumerate(stufen):
            zellen[i] += [(" ", bg, bg)] * 2 + [(" ", stufe, stufe)] * 2
        z.echt_malen(iy, ix, zellen)
        z.safe_addstr(iy + zeile_wert, ix + kb + 4, "◀", z.C.get("bright", 0))

    def _zeichne_farbig(self, z, iy, ix, kh, kb):
        C, PIX = z.C, z.PIX
        bg = C["pix_bg"]
        frei = (PIX["top"] - PIX["base"]) - len(PIX["pairs"])
        budget = frei - RESERVE - kh - 2                      # Regler + Feld
        self.farbe_256 = z.pix_farbe
        zellen, self.stufen_jetzt = self.rad_fuer_budget(
            kh, kb, bg, z.pix_farbe, budget, getattr(z, "PIX_MODUS", "mix"), self.geo[2])
        if zellen is None:               # nicht einmal grob: lieber Text als fremde Farben kippen
            z.safe_addstr(iy, ix, "zu wenig farben frei", C.get("dim", 0))
            return False
        for r, zeile in enumerate(zellen):
            for c, (ch, fg, hg) in enumerate(zeile):
                z.safe_addstr(iy + r, ix + c, ch, z.pix_attr(fg, hg))
        mr, mc = self._marke(kh, kb)
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

    def _zeichne_seite(self, z, y, x, w, farbig, echt=False):
        C = z.C
        farbe = self.rgb
        if echt:
            z.echt_malen(y, x, [[(" ", farbe, farbe)] * min(w, 12)] * 3)
        elif farbig:
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
        elif self.hinweis:
            z.safe_addstr(y + 10, x, self.hinweis[:w], C.get("faint", 0))


def leeren(z, y, x, h, w):
    """Was unter dem Modal liegt, wegwischen (ein Modal deckt ab)."""
    for i in range(h):
        z.safe_addstr(y + i, x, " " * w, z.C.get("ink", 0))
