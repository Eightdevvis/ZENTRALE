# tutor/pixel_zimmer.py
#
# Das Zimmer in Pixel-Optik (2026-10-08). Sasha: „bau das ganze neu in pixel
# game optik … aber behalt das alte design als backup". Das alte Zimmer
# (room.draw_room & Co.) bleibt unverändert; welches gilt, sagt die Einstellung
# `tutor_optik` (pixel | alt) — kommt über /api/tutor/config, im Fenster per
# --optik übersteuerbar.
#
# Regeln, damit es Pixel-Kunst bleibt und kein Matsch wird:
#   • EIN Raster: die Szene wird auf einer kleinen Leinwand gemalt (Höhe ≈180)
#     und ganzzahlig hochskaliert, Nachbar-Pixel, nie weich.
#   • Feste Palette (16 Farben je Tag/Nacht), keine Verläufe — Abstufung nur
#     über Dithering (Schachbrett).
#   • Schrift ohne Kantenglättung auf einem eigenen, halb so groben Raster
#     (Text muss lesbar bleiben; ganz grob wäre sie Matsch).
#   • Harte Kästen mit 1-Pixel-Rand statt runder Ecken und Transparenz.
#   • Die Figur: Sashas gemalte Puppe (bzw. die alte Figur) wird in voller
#     Größe gezeichnet und mit Nachbar-Pixeln auf das Raster gebracht — sein
#     Entwurf bleibt, er bekommt nur dasselbe Raster wie das Zimmer.
#
# Nur pygame, nichts aus dem Projekt (fährt im Aussenposten-Paket mit).

import math

import pygame

# ── Paletten ───────────────────────────────────────────────────────────
# Je 16 Farben. Namen nach der Sache, nicht nach dem Ton.
NACHT = dict(
    wand=(54, 44, 66), wand2=(64, 52, 78), sockel=(36, 28, 44),
    boden=(92, 62, 46), boden2=(76, 50, 38), fuge=(48, 32, 26),
    himmel=(28, 40, 72), mond=(236, 228, 184), rahmen=(150, 122, 104),
    sofa=(78, 102, 132), sofa2=(104, 132, 164), sofa_dk=(52, 68, 92),
    pflanze=(76, 132, 72), topf=(168, 96, 64), licht=(255, 214, 128),
    teppich=(150, 70, 70), teppich2=(186, 104, 92),
    kontur=(20, 14, 26), papier=(246, 240, 226), tinte=(30, 24, 34),
    hud=(232, 220, 236), hud_dim=(156, 140, 168), panel=(24, 18, 32),
    du=(140, 200, 236), sie=(248, 200, 150), gold=(244, 200, 96),
    gut=(120, 200, 120), mittel=(214, 176, 96), schlecht=(214, 112, 112),
    tv=(18, 16, 24), tv_an=(70, 120, 150), buch1=(170, 70, 70),
    buch2=(80, 120, 170), buch3=(200, 170, 80), regal=(110, 76, 56),
)
TAG = dict(
    wand=(226, 214, 230), wand2=(236, 226, 238), sockel=(180, 160, 168),
    boden=(206, 168, 128), boden2=(188, 150, 112), fuge=(150, 114, 82),
    himmel=(140, 192, 236), mond=(252, 236, 160), rahmen=(160, 130, 108),
    sofa=(132, 162, 196), sofa2=(170, 196, 222), sofa_dk=(98, 124, 158),
    pflanze=(92, 152, 84), topf=(182, 112, 74), licht=(255, 230, 160),
    teppich=(196, 112, 104), teppich2=(222, 150, 132),
    kontur=(56, 40, 52), papier=(252, 248, 238), tinte=(40, 32, 40),
    hud=(52, 40, 60), hud_dim=(110, 96, 120), panel=(246, 240, 248),
    du=(36, 104, 160), sie=(168, 84, 44), gold=(176, 124, 24),
    gut=(56, 150, 70), mittel=(176, 128, 36), schlecht=(186, 70, 70),
    tv=(34, 30, 40), tv_an=(96, 150, 180), buch1=(186, 84, 84),
    buch2=(84, 128, 184), buch3=(210, 178, 92), regal=(150, 108, 78),
)

RASTER_H = 180          # Höhe der Szenen-Leinwand in Pixeln (Richtwert)


def raster(w: int, h: int):
    """(s, W, H): ganzzahliger Faktor und Leinwandgröße. s ≥ 2, damit es
    immer sichtbar Pixel sind; W/H folgen dem Fenster (kein Trauerrand)."""
    s = max(2, round(h / RASTER_H))
    return s, max(1, w // s), max(1, h // s)


def _dither(fl, rect, a, b):
    """Schachbrett aus zwei Palettenfarben — die einzige erlaubte „Abstufung"."""
    x0, y0, rw, rh = rect
    fl.fill(a, rect)
    for y in range(y0, y0 + rh):
        for x in range(x0 + ((y + x0) % 2), x0 + rw, 2):
            fl.set_at((x, y), b)


def _kasten(fl, rect, fuell, rand):
    pygame.draw.rect(fl, fuell, rect)
    pygame.draw.rect(fl, rand, rect, 1)


def _kreis(fl, farbe, cx, cy, r):
    """Pixel-Kreis ohne Kantenglättung (Mittelpunkt-Raster)."""
    for dy in range(-r, r + 1):
        dx = int(math.sqrt(max(0, r * r - dy * dy)) + 0.5)
        pygame.draw.line(fl, farbe, (cx - dx, cy + dy), (cx + dx, cy + dy))


# ── Hintergrund (statisch, einmal je Größe/Thema gemalt) ───────────────

def hintergrund(W: int, H: int, p: dict) -> pygame.Surface:
    fl = pygame.Surface((W, H))
    boden_y = int(H * 0.62)
    # Wand: Grund + Tapetenstreifen, Sockelleiste
    fl.fill(p['wand'], (0, 0, W, boden_y))
    for x in range(0, W, 12):
        fl.fill(p['wand2'], (x, 0, 4, boden_y))
    fl.fill(p['sockel'], (0, boden_y - 3, W, 3))
    # Boden: Dielen mit versetzten Fugen
    fl.fill(p['boden'], (0, boden_y, W, H - boden_y))
    reihe = 5
    for i, y in enumerate(range(boden_y, H, reihe)):
        fl.fill(p['boden2'] if i % 2 else p['boden'], (0, y, W, reihe))
        pygame.draw.line(fl, p['fuge'], (0, y), (W, y))
        versatz = (i * 23) % 40
        for x in range(versatz, W, 40):
            pygame.draw.line(fl, p['fuge'], (x, y), (x, y + reihe - 1))
    # Fenster
    fw, fh = int(W * 0.18), int(H * 0.30)
    fx, fy = int(W * 0.12), int(H * 0.12)
    _kasten(fl, (fx - 3, fy - 3, fw + 6, fh + 6), p['rahmen'], p['kontur'])
    fl.fill(p['himmel'], (fx, fy, fw, fh))
    _kreis(fl, p['mond'], fx + int(fw * 0.68), fy + int(fh * 0.32), max(3, fh // 7))
    if p is NACHT:          # Sterne nur nachts; tags ist der Kreis die Sonne
        for sx, sy in ((0.2, 0.25), (0.36, 0.62), (0.5, 0.18), (0.82, 0.72), (0.28, 0.82)):
            fl.set_at((fx + int(fw * sx), fy + int(fh * sy)), p['mond'])
    else:                   # eine Wolke
        cw_, cy_ = max(6, fw // 4), fy + int(fh * 0.7)
        fl.fill(p['papier'], (fx + 4, cy_, cw_, 3))
        fl.fill(p['papier'], (fx + 6, cy_ - 2, cw_ - 5, 2))
    fl.fill(p['rahmen'], (fx + fw // 2 - 1, fy, 2, fh))
    fl.fill(p['rahmen'], (fx, fy + fh // 2 - 1, fw, 2))
    fl.fill(p['rahmen'], (fx - 4, fy + fh + 3, fw + 8, 2))      # Fensterbank
    # Regal mit Büchern (rechts oben) — Umgebung, an die später Wörter kommen
    rx, ry, rw = int(W * 0.70), int(H * 0.20), int(W * 0.16)
    for k, yy in enumerate((ry, ry + 16)):
        fl.fill(p['regal'], (rx, yy + 12, rw, 2))
        x = rx + 2
        n = 0
        while x < rx + rw - 4:
            bw = 3 + (n * 7 + k * 3) % 3
            bh = 8 + (n * 5 + k) % 4
            fl.fill((p['buch1'], p['buch2'], p['buch3'])[(n + k) % 3],
                    (x, yy + 12 - bh, bw, bh))
            x += bw + 1
            n += 1
    # Teppich
    tw, th = int(W * 0.50), max(8, int(H * 0.12))
    tx, ty = int(W * 0.17), int(H * 0.80)
    pygame.draw.ellipse(fl, p['teppich2'], (tx, ty, tw, th))
    pygame.draw.ellipse(fl, p['teppich'], (tx + 3, ty + 2, tw - 6, th - 4))
    # Stehlampe links
    lx = int(W * 0.06)
    fl.fill(p['regal'], (lx - 1, int(H * 0.50), 2, int(H * 0.36)))
    fl.fill(p['regal'], (lx - 4, int(H * 0.86) - 1, 8, 2))
    pygame.draw.polygon(fl, p['licht'], [(lx - 7, int(H * 0.50)), (lx + 7, int(H * 0.50)),
                                         (lx + 4, int(H * 0.43)), (lx - 4, int(H * 0.43))])
    # Pflanze rechts
    px, py = int(W * 0.93), int(H * 0.72)
    _kasten(fl, (px - 6, py, 12, 10), p['topf'], p['kontur'])
    for i, (dx, dy) in enumerate(((-6, -14), (-2, -20), (3, -18), (7, -12), (0, -10))):
        pygame.draw.line(fl, p['pflanze'], (px, py), (px + dx, py + dy))
        fl.fill(p['pflanze'], (px + dx - 2, py + dy - 1, 4, 3))
    # Sofa
    cx, cy = int(W * 0.76), int(H * 0.72)
    cw, ch = int(W * 0.22), int(H * 0.12)     # kleiner als im alten Bild: die
                                              # Figur wirkte daneben wie ein Kind
    x0 = cx - cw // 2
    _kasten(fl, (x0, cy - int(ch * 0.75), cw, int(ch * 0.8)), p['sofa'], p['kontur'])
    fl.fill(p['sofa2'], (x0 + 1, cy - int(ch * 0.75) + 1, cw - 2, 3))
    _kasten(fl, (x0, cy, cw, int(ch * 0.55)), p['sofa_dk'], p['kontur'])
    for ax in (x0 - 5, x0 + cw - 3):
        _kasten(fl, (ax, cy - int(ch * 0.4), 8, int(ch * 0.95)), p['sofa'], p['kontur'])
    for kx in (x0 + int(cw * 0.18), x0 + int(cw * 0.56)):
        _kasten(fl, (kx, cy - int(ch * 0.25), int(cw * 0.22), int(ch * 0.3)), p['sofa2'], p['kontur'])
    return fl


def fernseher(fl, W, H, p, an: bool, titel: str, schrift_klein, t: float):
    """TV an der Wand: aus = schwarz mit Lichtkante, an = Bild mit Zeilen."""
    tw, th = int(W * 0.17), int(H * 0.17)
    tx, ty = int(W * 0.36), int(H * 0.16)
    _kasten(fl, (tx - 2, ty - 2, tw + 4, th + 4), p['kontur'], p['kontur'])
    if an:
        fl.fill(p['tv_an'], (tx, ty, tw, th))
        for y in range(ty + int(t * 8) % 3, ty + th, 3):     # laufende Zeilen
            pygame.draw.line(fl, p['himmel'], (tx, y), (tx + tw - 1, y))
    else:
        fl.fill(p['tv'], (tx, ty, tw, th))
        pygame.draw.line(fl, p['sockel'], (tx + 2, ty + 2), (tx + tw // 3, ty + 2))
    fl.fill(p['kontur'], (tx + tw // 2 - 1, ty + th + 2, 2, 3))
    return (tx, ty, tw, th)


# ── Das Pixelzimmer ────────────────────────────────────────────────────

class Pixelzimmer:
    """Hält die Leinwände und malt einen Frame. `schrift(size)` liefert eine
    pygame-Schrift (room._font: die, die auf dieser Maschine wirklich malt)."""

    def __init__(self, schrift):
        self.schrift = schrift
        self._bg_key = None
        self._bg = None
        self._fonts = {}

    def _f(self, groesse):
        if groesse not in self._fonts:
            self._fonts[groesse] = self.schrift(groesse)
        return self._fonts[groesse]

    def palette(self, thema: str) -> dict:
        return TAG if thema == 'day' else NACHT

    def zeichnen(self, screen, d: dict):
        """d: was room.main für diesen Frame weiß (siehe bild() unten)."""
        w, h = screen.get_size()
        s, W, H = raster(w, h)
        p = self.palette(d.get('thema'))
        key = (W, H, d.get('thema'))
        if key != self._bg_key:
            self._bg, self._bg_key = hintergrund(W, H, p), key
        fl = self._bg.copy()
        fernseher(fl, W, H, p, d.get('tv_an'), d.get('tv_titel') or '', None, d.get('t', 0.0))
        self._figur(fl, d.get('persona'), w, h, s)
        szene = pygame.transform.scale(fl, (W * s, H * s))
        screen.fill(p['kontur'])
        screen.blit(szene, (0, 0))
        # Text-Raster: halb so grob wie die Szene, damit Schrift lesbar bleibt.
        t = max(1, s // 2)
        ui = pygame.Surface((w // t, h // t), pygame.SRCALPHA)
        kx, ky = d.get('kopf') or (w // 2, h // 2)
        self._ui(ui, dict(d, kopf_ui=(int(kx / t), int(ky / t))), p, s / t)
        screen.blit(pygame.transform.scale(ui, (ui.get_width() * t, ui.get_height() * t)), (0, 0))

    # -- Figur ---------------------------------------------------------
    def _figur(self, fl, persona, w, h, s):
        """Persona in voller Größe auf eine durchsichtige Fläche malen, dann
        mit Nachbar-Pixeln auf das Raster bringen (kein Weichzeichnen)."""
        if persona is None:
            return
        voll = pygame.Surface((w, h), pygame.SRCALPHA)
        try:
            persona.draw(voll)
        except Exception:
            return
        klein = pygame.transform.scale(voll, (fl.get_width(), fl.get_height()))
        fl.blit(klein, (0, 0))

    # -- Oberfläche (Text-Raster) --------------------------------------
    def _ui(self, ui, d, p, k):
        """k = wie viele Text-Pixel ein Szenen-Pixel breit ist."""
        U, V = ui.get_size()
        # Schriftgröße folgt dem Fenster (auf dem Bildschirm ≈ h/30 für den
        # Fließtext), nie unter 11 Text-Pixel: klein ja, Matsch nein.
        t = d['h'] / V
        f_gross = self._f(max(14, round(d['h'] / 22 / t)))
        f = self._f(max(11, round(d['h'] / 30 / t)))
        f_klein = self._f(max(11, round(d['h'] / 34 / t)))
        # Kopfleiste: eine harte Zeile über die ganze Breite — Name, Mikro,
        # Musik links, Laune rechts. Nichts schwebt mehr über Fenster und TV.
        name = f_gross.render(d.get('name') or '', False, p['hud'])
        kh = name.get_height() + 6
        ui.fill(p['panel'], (0, 0, U, kh))
        pygame.draw.line(ui, p['kontur'], (0, kh), (U, kh))
        ui.blit(name, (6, 3))
        x = 6 + name.get_width() + 12
        for text, farbe in ((d.get('mikro') or '', p['du'] if d.get('mikro_aktiv') else p['hud_dim']),
                            (d.get('musik') or '', p['du']),
                            (d.get('meldung') or '', p['gold'])):
            if text:
                z = f_klein.render(text, False, farbe)
                ui.blit(z, (x, (kh - z.get_height()) // 2))
                x += z.get_width() + 12
        d = dict(d, kopf_h=kh)
        self._laune(ui, d, p, U, f_klein)
        # Sprechblase + Gedanke über dem Kopf
        kx, ky = d['kopf_ui']
        if d.get('blase'):
            self._blase(ui, p, f, d['blase'], kx, ky, d.get('blase_alpha', 255))
        if d.get('gedanke'):
            wort, bed = d['gedanke']
            self._gedanke(ui, p, f_gross, f_klein, wort, bed, kx, ky, d.get('gedanke_alpha', 255))
        self._leiste(ui, d, p, f_klein, U, V)

    def _laune(self, ui, d, p, U, f):
        stufen = 10
        bw = max(4, f.get_height() // 3)          # wächst mit der Schrift
        bh = max(6, f.get_height() // 2)
        kh = d.get('kopf_h', 20)
        x0 = U - 8 - stufen * (bw + 1)
        y0 = (kh - bh - 4) // 2
        lab = f.render('Laune', False, p['hud_dim'])
        ui.blit(lab, (x0 - lab.get_width() - 6, (kh - lab.get_height()) // 2))
        farbe = {'happy': p['gut'], 'ok': p['mittel']}.get(d.get('laune'), p['schlecht'])
        voll = round(max(0, min(100, d.get('batterie', 60))) / 10)
        _kasten(ui, (x0 - 2, y0, stufen * (bw + 1) + 3, bh + 4), p['kontur'], p['kontur'])
        for i in range(stufen):
            ui.fill(farbe if i < voll else p['sockel'], (x0 + i * (bw + 1), y0 + 2, bw, bh))

    def _blase(self, ui, p, f, text, kx, ky, alpha):
        U = ui.get_width()
        breite = min(U - 16, max(80, U // 3))
        zeilen = _umbrechen(f, text, breite - 12)[:5]
        lh = f.get_linesize()
        bh = len(zeilen) * lh + 10
        bw = max(f.size(z)[0] for z in zeilen) + 14 if zeilen else 40
        bx = max(6, min(U - bw - 6, kx - bw // 2))
        by = max(d_oben(ui), ky - bh - 12)
        fl = pygame.Surface((bw, bh + 7), pygame.SRCALPHA)
        _kasten(fl, (0, 0, bw, bh), p['papier'], p['kontur'])
        # Zipfel als Pixel-Treppe Richtung Kopf
        zx = max(6, min(bw - 10, kx - bx))
        for i in range(6):
            pygame.draw.line(fl, p['papier'], (zx - (5 - i), bh - 1 + i), (zx + (5 - i), bh - 1 + i))
            fl.set_at((zx - (5 - i) - 1, bh - 1 + i), p['kontur'])
            fl.set_at((zx + (5 - i) + 1, bh - 1 + i), p['kontur'])
        for i, z in enumerate(zeilen):
            fl.blit(f.render(z, False, p['tinte']), (7, 5 + i * lh))
        if alpha < 255:
            fl.set_alpha(alpha)
        ui.blit(fl, (bx, by))

    def _gedanke(self, ui, p, fg, fk, wort, bed, kx, ky, alpha):
        a = fg.render(wort, False, p['tinte'])
        b = fk.render(bed, False, p['hud_dim'] if p is TAG else (96, 92, 120)) if bed else None
        bw = max(a.get_width(), b.get_width() if b else 0) + 16
        bh = a.get_height() + (b.get_height() + 2 if b else 0) + 10
        bx = max(6, kx - bw - 24)
        by = max(d_oben(ui), ky - 6)
        fl = pygame.Surface((bw + 14, bh), pygame.SRCALPHA)
        _kasten(fl, (0, 0, bw, bh), p['papier'], p['gold'])
        pygame.draw.rect(fl, p['gold'], (1, 1, bw - 2, bh - 2), 1)
        fl.blit(a, ((bw - a.get_width()) // 2, 5))
        if b:
            fl.blit(b, ((bw - b.get_width()) // 2, 7 + a.get_height()))
        for i, (dx, r) in enumerate(((bw + 4, 2), (bw + 10, 1))):   # Gedanken-Punkte
            fl.fill(p['papier'], (dx - r, 8 - r + i * 3, 2 * r + 1, 2 * r + 1))
        if alpha < 255:
            fl.set_alpha(alpha)
        ui.blit(fl, (bx, by))

    def _leiste(self, ui, d, p, f, U, V):
        """Verlauf (bis 3 Zeilen, nur so hoch wie nötig) + Eingabezeile. Ist
        die Eingabe leer, steht dort die Bedienung (statt oben über dem Bild)."""
        lh = f.get_linesize()
        ein_h = lh + 6
        zeilen = []
        for rolle, text in d.get('log') or []:
            wer = 'Sasha' if rolle == 'user' else (d.get('name') or '')
            farbe = p['du'] if rolle == 'user' else p['sie']
            for i, z in enumerate(_umbrechen(f, f'{wer}: {text}', U - 12)):
                zeilen.append((farbe, z if i == 0 else '  ' + z))
        sichtbar = min(3, len(zeilen))
        if sichtbar:
            bar_h = lh * sichtbar + 6
            y0 = V - ein_h - bar_h
            bar = pygame.Surface((U, bar_h), pygame.SRCALPHA)
            bar.fill((*p['panel'], 210))
            ui.blit(bar, (0, y0))
            pygame.draw.line(ui, p['kontur'], (0, y0), (U, y0))
            sc = min(d.get('scroll', 0), max(0, len(zeilen) - 3))
            start = max(0, len(zeilen) - sichtbar - sc)
            for i, (farbe, z) in enumerate(zeilen[start:start + sichtbar]):
                ui.blit(f.render(z, False, farbe), (6, y0 + 3 + i * lh))
        _kasten(ui, (0, V - ein_h, U, ein_h), p['panel'], p['kontur'])
        text = (d.get('eingabe') or '') + (d.get('ime') or '')
        if text:
            z = f.render(text, False, p['hud'])
            ui.blit(z, (6, V - ein_h + 3))
            cx = 7 + z.get_width()
        else:
            z = f.render(d.get('hinweis') or '', False, p['hud_dim'])
            ui.blit(z, (max(6, U - z.get_width() - 6), V - ein_h + 3))
            cx = 7
        if (d.get('t', 0.0) % 1.0) < 0.5:
            ui.fill(p['hud'], (cx, V - ein_h + 3, 2, lh - 2))


def d_oben(ui):
    """Oberkante, unter der Blasen bleiben (unter der Kopfleiste)."""
    return 26


# ── Was ein Frame braucht (aus room.main, damit room.py nicht wächst) ──

def hud_zeilen(S, msg, avail, tts_ok, mic_err, mic, transcribing, hearing,
               here_s=120, sym=lambda t: t):
    """(Hinweis, Mikro-Zeile, Art) für die Kopfzeile — eine Quelle für beide
    Optiken (2026-10-08). Art: 'aktiv' (hört/versteht), 'pause', '' (ruhig)."""
    if msg:
        hint = msg
    elif avail is False:
        hint = 'verbinde…'
    elif avail and not tts_ok:
        hint = '🔇 keine Stimme (tts-service aus?)'
    else:
        hint = 'Esc Menü · ↑/↓ Verlauf · Enter reden · Alt+P Pause · Alt+D Drill · Alt+Z Zentrale'
    art = ''
    if mic_err:
        zeile = 'Mic: ' + mic_err
    elif not mic:
        zeile = 'Mic aus · Alt+H'
    elif transcribing:
        zeile, art = 'Mic: versteht…', 'aktiv'
    elif hearing:
        zeile, art = 'Mic: hört dich ●', 'aktiv'
    else:
        zeile = 'Mic: hört zu · Alt+H'
    # Anwesenheit (aus Sprache/Geräusch am Mikro): sichtbar, damit man an der
    # Wand sieht, ob sie einen gerade „bemerkt" hat.
    with S['lock']:
        act, pause = S['activity_ms'], S['pause']
    if act and (pygame.time.get_ticks() - act) / 1000.0 < here_s:
        zeile += ' · da'
    if pause:
        zeile, art = 'PAUSE · sie lässt dich in Ruhe · Alt+P', 'pause'
    return sym(hint), sym(zeile), art


def bild(S, w, h, t, thema, persona, tv_on, tv_title, avail, bub_text,
                bub_age, thought, thought_t, pname, msg, tts_ok, mic_err, mic,
                transcribing, hearing, music, mood, battery, log, scroll, inp,
                compose, here_s=120, sym=lambda t: t, linger=4.0, fade=1.3):
    """Was die Pixel-Optik für einen Frame braucht, als ein Dict."""
    hint, mic_line, mic_kind = hud_zeilen(S, msg, avail, tts_ok, mic_err, mic,
                                          transcribing, hearing, here_s, sym)
    blase, alpha = None, 255
    if bub_text and avail is not False and bub_age < linger + fade:
        blase = bub_text
        if bub_age > linger:
            alpha = int(255 * max(0.0, 1 - (bub_age - linger) / fade))
    gedanke = thought if (thought and avail is not False) else None
    return dict(w=w, h=h, t=t, thema=thema, persona=persona, tv_an=tv_on,
                tv_titel=tv_title, kopf=(persona.x, persona.head_top()),
                blase=blase, blase_alpha=alpha, gedanke=gedanke,
                gedanke_alpha=255 if thought_t > 1.0 else int(255 * max(0.0, thought_t)),
                name=pname, hinweis=hint, mikro=mic_line,
                meldung=msg or ('verbinde…' if avail is False else ''),
                mikro_aktiv=mic_kind == 'aktiv',
                musik=f'♪ {music}' if music else '', laune=mood, batterie=battery,
                log=log, scroll=scroll, eingabe=inp, ime=compose)


def _umbrechen(font, text, breite):
    """Zeichenweise (CJK hat keine Wortgrenzen), wie room._wrap."""
    zeilen, cur = [], ''
    for ch in text or '':
        if ch == '\n':
            zeilen.append(cur); cur = ''; continue
        if font.size(cur + ch)[0] > breite and cur:
            # am letzten Leerzeichen umbrechen, wenn es eins gibt
            if ' ' in cur:
                vorn, rest = cur.rsplit(' ', 1)
                zeilen.append(vorn); cur = rest + ch
            else:
                zeilen.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        zeilen.append(cur)
    return zeilen
