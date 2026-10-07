# tui/ansichten/denkadern.py
#
# Die Denk-Animation des Chats (2026-10-07). Sasha: „wenn sie nachdenkt, dass
# dann so leichte leuchtende pulsierende adern von ihr ausstrahlen, je länger
# sie denkt, desto mehr erstrecken die sich, die adern sind aber nich normal
# förmig sondern bilden spiralen und erinnern etwas an das muster vom gehirn,
# aber ziemlich geometrisch in der kreis spiralform halt".
#
# Bauregel (reine Geometrie, kein Zufall — zwei Bilder zur selben Zeit sind
# gleich, und Tests brauchen keinen Bildschirm):
#   - ein Kern in der Mitte, daraus ARME: logarithmische Spiralen
#     r = r0·e^(k·θ), gleichmäßig um den Kern verteilt, drehen sich sehr
#     langsam;
#   - an jedem Arm WINDUNGEN: bei Radien, die geometrisch wachsen (r0·g^m),
#     zweigt eine Locke ab — ein Kreisbogen mit schrumpfendem Radius, der
#     sich nach innen einrollt, abwechselnd links und rechts. Das ist das
#     „Gehirn" in Kreisgeometrie: gefaltete Bögen, selbstähnlich, weiter
#     außen größer;
#   - REICHWEITE wächst mit der Denkdauer: R = R_max·(1 − e^(−dauer/τ)).
#     Erst schnell, dann immer langsamer — wer lange denkt, füllt den Platz;
#   - PULS: eine Helligkeitswelle läuft vom Kern nach außen (entlang der
#     Bogenlänge), dazu ein leises Atmen. Ruhig: eine Welle braucht ~2,6 s;
#   - ENDE: das Muster zieht sich zum Kern zurück und verblasst (ausklang
#     0 → 1).
#
# Gezeichnet im Pixelstil der TUI (memory/system/pixelstil.md): je
# Zeichenfeld 2×3 Feinpixel als Sextant (pixel.sextant), EINE Leuchtfarbe pro
# Feld aus wenigen Stufen zwischen Grund und Glimmen — kantig, wenige Farben,
# wie die Bernsteinleiste. Die Farben sind die des Auges (pixel.AUGE_FARBEN),
# damit es dieselbe KI bleibt.
#
# Kosten: ~2 000 Abtastpunkte je Bild, gerechnet höchstens BILDER_JE_S mal pro
# Sekunde (Zeit wird gerastert, Zwischenbilder kommen aus dem Speicher).

import math
from functools import lru_cache

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

BILDER_JE_S = 10          # so oft ändert sich das Bild höchstens (Akku: Laptop)
TAU = 9.0                 # s — nach TAU ist 63 % der Reichweite erreicht
ARME = 5
STEIGUNG = 0.34           # k der log. Spirale: kleiner = enger gewickelt
WACHSTUM = 1.6           # g: Abstand der Windungen entlang des Arms (Radius-Faktor)
WELLE = 22.0              # Feinpixel zwischen zwei Pulswellen
WELLE_S = 2.6             # s, bis eine Welle eine Wellenlänge weiter ist
DREHUNG = 0.035           # rad/s — kaum merklich, nur dass es lebt
AUSKLANG_S = 0.9          # so lange zieht sich das Muster nach dem Denken zurück
STUFEN = 5                # Helligkeitsstufen (wenige Farben, Pixelstil)
SCHWELLE = 0.10           # darunter bleibt ein Feinpixel dunkel

# Feinpixel je Zeichenfeld (Sextant) und ihr Seitenverhältnis: ein Feld ist
# ~9×18 Bildpunkte, ein Sextant-Pixel also 4,5×6 — 4/3 so hoch wie breit.
SX, SY = 2, 3
HOCH = 4.0 / 3.0


def _farben(thema):
    """Grund, Ader, Glimmen — vom Auge, damit es dieselbe KI bleibt."""
    F = pixel.AUGE_FARBEN["tag" if thema == "tag" else "nacht"]
    if thema == "tag":                  # auf Weiß leuchtet nichts: dunkler werden
        return F["bg"], F["iris"], F["irisrand"]
    return F["bg"], F["iris"], F["irishell"]


def reichweite(dauer, r_max):
    """Wie weit die Adern nach `dauer` Sekunden Denken reichen (Feinpixel)."""
    d = max(0.0, float(dauer))
    return 2.0 + (r_max - 2.0) * (1.0 - math.exp(-d / TAU))


def _ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _puls(s, t):
    """Helligkeit 0..1 an Bogenlänge s zur Zeit t: Grundglimmen + eine
    schmale Welle, die nach außen wandert."""
    phase = (s / WELLE - t / WELLE_S) % 1.0
    welle = max(0.0, math.cos(2 * math.pi * phase)) ** 6
    atmen = 0.88 + 0.12 * math.sin(2 * math.pi * t / 4.2)
    return min(1.0, (0.22 + 0.78 * welle) * atmen)


def _pfade(reach, t, sx_stretch):
    """Alle leuchtenden Punkte: [(x, y_sicht, helligkeit)] relativ zum Kern,
    x in Feinpixeln, y in „Sicht-Einheiten" (x-Pixelbreiten)."""
    k = STEIGUNG
    wurzel = math.sqrt(1 + k * k)
    r0 = 3.5
    punkte = []
    if reach <= r0:
        return punkte
    dreh = DREHUNG * t
    th_max = math.log(reach / r0) / k
    for j in range(ARME):
        phi = j * 2 * math.pi / ARME + dreh
        th = 0.0
        while th <= th_max:
            r = r0 * math.exp(k * th)
            s = (r - r0) * wurzel / k
            hell = _puls(s, t)
            if reach - r < 3.0:                     # die wachsende Spitze glimmt
                hell = max(hell, 0.85)
            punkte.append((sx_stretch * r * math.cos(th + phi), r * math.sin(th + phi), hell))
            th += 0.55 / (r * wurzel)
        # Windungen: Locken an Radien r0·g^m, abwechselnd links/rechts
        m, rb = 2, r0 * WACHSTUM ** 2      # erst ab etwas Abstand: am Kern wäre es Brei
        while rb < reach:
            thb = math.log(rb / r0) / k
            winkel = thb + phi
            bx, by = rb * math.cos(winkel), rb * math.sin(winkel)
            sb = (rb - r0) * wurzel / k
            # Tangente des Arms; die Locke beginnt quer dazu
            tang = winkel + math.atan2(1.0, k)
            seite = 1 if (m + j) % 2 else -1
            rho0 = 0.26 * rb + 1.0
            # Mittelpunkt der Locke: senkrecht zur Tangente, Abstand rho0
            mx = bx + rho0 * math.cos(tang + seite * math.pi / 2)
            my = by + rho0 * math.sin(tang + seite * math.pi / 2)
            a0 = math.atan2(by - my, bx - mx)
            reif = (reach - rb) / (0.45 * rb + 4.0)   # wie weit die Locke schon ist
            u_max = 2.4 * math.pi * min(1.0, max(0.0, reif))
            u, su = 0.0, 0.0
            while u <= u_max:
                rho = rho0 * math.exp(-0.16 * u)
                w = a0 + seite * u
                hell = _puls(sb + su, t) * (0.9 - 0.25 * u / (2.4 * math.pi))
                punkte.append((sx_stretch * (mx + rho * math.cos(w)), my + rho * math.sin(w), hell))
                du = 0.6 / max(1.0, rho)
                u += du
                su += rho * du
            m += 1
            rb = r0 * WACHSTUM ** m
    return punkte


@lru_cache(maxsize=8)
def _bild(t_q, dauer_q, ausklang_q, breite, hoehe, thema):
    t = t_q / BILDER_JE_S
    dauer = dauer_q / BILDER_JE_S
    ausklang = ausklang_q / 20.0
    W, H = breite * SX, hoehe * SY
    if W <= 0 or H <= 0:
        return tuple()
    hv = H * HOCH                                # Höhe in Sicht-Einheiten
    r_max = 0.96 * min(W / 2.0, hv / 2.0)
    # Breite Flächen: das Muster darf sich etwas in die Breite ziehen, bleibt
    # aber erkennbar Kreis (höchstens 1,6×).
    stretch = max(1.0, min(1.6, (W / 2.0) / max(1.0, hv / 2.0)))
    zurueck = _ease(ausklang)
    reach = reichweite(dauer, r_max) * (1.0 - zurueck)
    dimm = 1.0 - zurueck
    cx, cy = W / 2.0, hv / 2.0
    feld = {}

    def setze(x, yv, hell):
        px, py = int(x + cx), int((yv + cy) / HOCH)
        if 0 <= px < W and 0 <= py < H:
            key = (py, px)
            if hell > feld.get(key, 0.0):
                feld[key] = hell

    if dimm > 0.02:
        for x, yv, hell in _pfade(reach, t, stretch):
            setze(x, yv, hell * dimm)
        # der Kern: eine kleine helle Scheibe, die mitatmet
        kern = (0.75 + 0.25 * _puls(0.0, t)) * dimm
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                setze(dx, dy * HOCH, kern if dx * dy == 0 else kern * 0.5)

    bg, ader, glimm = _farben(thema)
    zellen = {}
    for (py, px), hell in feld.items():
        if hell < SCHWELLE:
            continue
        r, c = py // SY, px // SX
        bit = 1 << ((py % SY) * 2 + (px % SX))
        bits, best = zellen.get((r, c), (0, 0.0))
        zellen[(r, c)] = (bits | bit, max(best, hell))
    zeilen = []
    for r in range(hoehe):
        zeile = []
        for c in range(breite):
            z = zellen.get((r, c))
            if z is None:
                zeile.append(None)
                continue
            bits, hell = z
            stufe = max(1, min(STUFEN, int(math.ceil(hell * STUFEN))))
            a = stufe / STUFEN
            if thema == "tag":                  # auf Weiß sonst zu blass
                a = 0.35 + 0.65 * a
            fg = pixel.mix(bg, ader, a / 0.6) if a <= 0.6 else pixel.mix(ader, glimm, (a - 0.6) / 0.4)
            zeile.append((pixel.sextant(bits), fg, bg))
        zeilen.append(tuple(zeile))
    return tuple(zeilen)


def adern_zellen(t, dauer, breite, hoehe, thema="nacht", ausklang=0.0):
    """Das Muster als Zeichenfelder. -> Zeilen (hoehe) × Felder (breite),
    jedes (zeichen, fg_rgb, bg_rgb) oder None (durchsichtig).

    t         Uhr der Animation in s (Puls, Drehung)
    dauer     wie lange sie schon denkt, in s (Reichweite)
    thema     "nacht" | "tag"
    ausklang  0 = denkt noch, 1 = ganz zurückgezogen (nach dem Denken)."""
    return _bild(int(t * BILDER_JE_S), int(dauer * BILDER_JE_S),
                 int(max(0.0, min(1.0, ausklang)) * 20), int(breite), int(hoehe),
                 "tag" if thema == "tag" else "nacht")


def hoehe_fuer(platz):
    """Wie viele Zeilen der Verlauf der Animation gibt: genug für Spiralen,
    nie mehr als die Hälfte des Platzes."""
    return max(0, min(13, platz // 2)) if platz >= 8 else 0
