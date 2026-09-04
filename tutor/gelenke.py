#!/usr/bin/env python3
# tutor/gelenke.py
#
# LIEST die Gelenke aus einem gemalten Bild und schreibt sie nach rig.json.
#
# Die Gegenrichtung zu schablone.py: dort werden aus Zahlen Kreuze gezeichnet,
# hier werden aus gemalten Punkten wieder Zahlen. Damit gibt SASHA die Figur
# vor — er malt Lucía so, wie sie aussehen soll, markiert auf einer eigenen
# Ebene die Gelenke, und der Bauplan richtet sich danach. Nicht umgekehrt.
#
# So geht es:
#   1. Figur malen, wie sie sein soll (Proportionen ganz frei).
#   2. Eine NEUE, leere Ebene darüber. Darauf pro Gelenk EINEN Punkt setzen,
#      in der Farbe aus der Tabelle unten (Farbkarte: --farbkarte).
#      Pinselgrösse egal, Hauptsache ein satter Klecks; die Mitte zählt.
#   3. NUR diese Ebene als PNG exportieren (Rest transparent).
#   4. Einlesen lassen — es entsteht ein Kontrollbild zum Prüfen.
#
# Links und rechts muss nicht unterschieden werden: wo eine Farbe zweimal
# vorkommt (Schultern, Ellbogen, Hüftgelenke, Knie, Augen), entscheidet die
# Lage im Bild, welcher Punkt der linke ist.
#
# Aufruf:
#   venv/bin/python tutor/gelenke.py --farbkarte
#   venv/bin/python tutor/gelenke.py punkte.png
#   venv/bin/python tutor/gelenke.py punkte.png --figur lucia --schreiben

import os
import sys
import json
import argparse

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame


# Farbe → welche Slots sie meint. Steht ein Paar drin, wird nach x-Lage
# aufgeteilt (linker Punkt zuerst). Die Farben sind bewusst grell und weit
# auseinander, damit sie sich nicht verwechseln lassen.
FARBEN = [
    ((255, 0, 255),   ['kopf'],                            'Nacken — wo der Kopf sitzt'),
    ((255, 255, 0),   ['torso'],                           'Hüfte — Drehpunkt des Rumpfes'),
    ((255, 0, 0),     ['arm_l_ober', 'arm_r_ober'],        'die beiden Schultern'),
    ((255, 128, 0),   ['arm_l_unter', 'arm_r_unter'],      'die beiden Ellbogen'),
    ((0, 220, 0),     ['bein_l_ober', 'bein_r_ober'],      'die beiden Hüftgelenke'),
    ((0, 0, 255),     ['bein_l_unter', 'bein_r_unter'],    'die beiden Knie'),
    ((0, 255, 255),   ['auge_l', 'auge_r'],                'die beiden Augen'),
    ((255, 255, 255), ['mund'],                            'der Mund'),
    ((0, 0, 0),       ['__boden'],                         'Fusspunkt — wo sie auf dem Boden steht'),
]

_TOLERANZ = 90       # wie weit ein Pixel von der Zielfarbe abweichen darf
_MIN_ALPHA = 100     # durchscheinende Pixel (Pinselrand) zählen nicht


def _abstand(a, b):
    return sum((int(x) - int(y)) ** 2 for x, y in zip(a, b)) ** 0.5


def punkte_finden(pfad):
    """Sucht alle Farbkleckse und gibt je Farbe die Schwerpunkte zurück."""
    pygame.init()
    bild = pygame.image.load(pfad)
    try:
        bild = bild.convert_alpha()
    except pygame.error:
        pygame.display.set_mode((1, 1))
        bild = bild.convert_alpha()
    w, h = bild.get_size()

    # Pixel den Zielfarben zuordnen
    treffer = {i: [] for i in range(len(FARBEN))}
    for y in range(h):
        for x in range(w):
            r, g, b, a = bild.get_at((x, y))
            if a < _MIN_ALPHA:
                continue
            bester, bester_abstand = None, _TOLERANZ
            for i, (farbe, _slots, _txt) in enumerate(FARBEN):
                d = _abstand((r, g, b), farbe)
                if d < bester_abstand:
                    bester, bester_abstand = i, d
            if bester is not None:
                treffer[bester].append((x, y))

    # Kleckse derselben Farbe zu Gruppen zusammenfassen (Nachbarschaft)
    gruppen = {}
    for i, pixel in treffer.items():
        gruppen[i] = _clustern(pixel)
    return gruppen, (w, h)


def _clustern(pixel, radius=14):
    """Simples Gruppieren: was nah beieinander liegt, ist derselbe Klecks."""
    offen = list(pixel)
    cluster = []
    while offen:
        keim = offen.pop()
        gruppe = [keim]
        gewachsen = True
        while gewachsen:
            gewachsen = False
            rest = []
            for p in offen:
                if any(abs(p[0] - q[0]) <= radius and abs(p[1] - q[1]) <= radius
                       for q in gruppe):
                    gruppe.append(p)
                    gewachsen = True
                else:
                    rest.append(p)
            offen = rest
        if len(gruppe) >= 4:                       # Einzelpixel = Rauschen
            sx = sum(p[0] for p in gruppe) / len(gruppe)
            sy = sum(p[1] for p in gruppe) / len(gruppe)
            cluster.append((sx, sy, len(gruppe)))
    cluster.sort(key=lambda c: c[0])               # nach x, also links zuerst
    return cluster


def zuordnen(gruppen):
    """Ordnet die gefundenen Kleckse den Slots zu. Meldet, was nicht passt."""
    pivots, boden, meldungen = {}, None, []
    for i, (farbe, slots, beschreibung) in enumerate(FARBEN):
        gefunden = gruppen.get(i, [])
        erwartet = len(slots)
        if len(gefunden) != erwartet:
            meldungen.append('%s: %d Punkt(e) erwartet, %d gefunden  (%s)'
                             % (beschreibung, erwartet, len(gefunden), 'RGB%s' % (farbe,)))
            if not gefunden:
                continue
        for slot, (sx, sy, _n) in zip(slots, gefunden):
            if slot == '__boden':
                boden = (sx, sy)
            else:
                pivots[slot] = (round(sx), round(sy))
    return pivots, boden, meldungen


def rig_aktualisieren(rig_pfad, pivots, boden, groesse):
    """Schreibt neue Drehpunkte in rig.json — Struktur bleibt, Zahlen ändern sich."""
    with open(rig_pfad, 'r', encoding='utf-8') as f:
        d = json.load(f)
    w, h = groesse
    d['leinwand']['breite'] = w
    d['leinwand']['hoehe'] = h
    if boden:
        d['leinwand']['boden_y'] = round(boden[1])
        d['leinwand']['mitte_x'] = round(boden[0])
    for slot, (x, y) in pivots.items():
        if slot in d['slots']:
            d['slots'][slot]['pivot'] = [x, y]
    with open(rig_pfad, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return d


def kontrollbild(quelle, pivots, boden, ziel, figurbild=None):
    """Zeigt, was erkannt wurde — zum Drüberschauen, bevor es gilt.

    Mit `figurbild` wird die gemalte Figur als Hintergrund daruntergelegt;
    dann sieht man nicht nur die Punkte, sondern ob der Ellbogen auch
    wirklich am Ellbogen sitzt."""
    pygame.init()
    pygame.font.init()
    grund = pygame.image.load(quelle).convert_alpha()
    w, h = grund.get_size()
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((22, 24, 30, 255))
    if figurbild:
        try:
            fig = pygame.image.load(figurbild).convert_alpha()
            if fig.get_size() != (w, h):
                fig = pygame.transform.smoothscale(fig, (w, h))
            surf.blit(fig, (0, 0))
        except Exception:
            pass
    surf.blit(grund, (0, 0))
    font = pygame.font.SysFont('dejavusans', 13)

    # Beschriftungen: pro Seite nach y sortiert und auseinandergeschoben,
    # sonst kleben Punkte auf gleicher Hoehe (Huefte/Huftgelenk) aufeinander.
    seiten = {True: [], False: []}
    for slot, (x, y) in pivots.items():
        seiten[x <= w / 2].append((y, slot, x))
    for links, eintraege in seiten.items():
        eintraege.sort()
        letztes_y = -999
        for y, slot, x in eintraege:
            ly = max(y, letztes_y + 17)
            letztes_y = ly
            pygame.draw.circle(surf, (255, 90, 110), (int(x), int(y)), 7, 2)
            pygame.draw.line(surf, (255, 90, 110), (x - 11, y), (x + 11, y), 1)
            pygame.draw.line(surf, (255, 90, 110), (x, y - 11), (x, y + 11), 1)
            t = font.render(slot, True, (235, 235, 245))
            tx = 10 if links else w - 10 - t.get_width()
            pygame.draw.line(surf, (120, 130, 150),
                             (tx + (t.get_width() + 4 if links else -4), ly), (x, y), 1)
            surf.blit(t, (tx, ly - 8))
    if boden:
        pygame.draw.line(surf, (200, 170, 90), (0, boden[1]), (w, boden[1]), 2)
        surf.blit(font.render('Boden', True, (200, 170, 90)), (10, boden[1] + 4))
    pygame.image.save(surf, ziel)
    return ziel


def farbkarte(ziel):
    """Farbfelder zum Pipette-Ziehen — damit die Farben sicher getroffen werden."""
    pygame.init()
    pygame.font.init()
    zeile, breite = 46, 460
    surf = pygame.Surface((breite, zeile * len(FARBEN) + 46), pygame.SRCALPHA)
    surf.fill((28, 30, 38, 255))
    font = pygame.font.SysFont('dejavusans', 14)
    klein = pygame.font.SysFont('dejavusans', 11)
    surf.blit(pygame.font.SysFont('dejavusans', 15, bold=True).render(
        'Gelenk-Farben — mit der Pipette abgreifen', True, (230, 232, 240)), (14, 12))
    for i, (farbe, slots, beschreibung) in enumerate(FARBEN):
        y = 44 + i * zeile
        pygame.draw.rect(surf, farbe, (14, y, 54, 30))
        pygame.draw.rect(surf, (90, 95, 110), (14, y, 54, 30), 1)
        surf.blit(font.render(beschreibung, True, (226, 228, 238)), (82, y + 2))
        anzahl = '1 Punkt' if len(slots) == 1 else '2 Punkte'
        surf.blit(klein.render('%s   RGB %d,%d,%d' % (anzahl, *farbe), True, (146, 152, 168)),
                  (82, y + 18))
    pygame.image.save(surf, ziel)
    return ziel


def main():
    hier = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description='Gelenke aus einem gemalten Punkte-Bild lesen')
    ap.add_argument('bild', nargs='?', help='PNG mit den Farbpunkten (nur diese Ebene)')
    ap.add_argument('--figur', default='lucia')
    ap.add_argument('--schreiben', action='store_true',
                    help='rig.json wirklich aendern (ohne dies nur anzeigen)')
    ap.add_argument('--farbkarte', action='store_true', help='Farbfelder-PNG erzeugen')
    ap.add_argument('--figurbild', help='gemalte Figur als Hintergrund im Kontrollbild')
    a = ap.parse_args()

    ordner = os.path.join(hier, 'assets', 'figuren', a.figur)
    if a.farbkarte:
        print('Farbkarte:', farbkarte(os.path.join(ordner, 'GELENK_FARBEN.png')))
        return
    if not a.bild:
        ap.error('bitte ein Punkte-PNG angeben (oder --farbkarte)')

    gruppen, groesse = punkte_finden(a.bild)
    pivots, boden, meldungen = zuordnen(gruppen)

    print('Bild: %dx%d' % groesse)
    for slot, (x, y) in sorted(pivots.items()):
        print('  %-14s %4d, %4d' % (slot, x, y))
    if boden:
        print('  %-14s %4d, %4d' % ('(boden)', boden[0], boden[1]))
    if meldungen:
        print('\nZu pruefen:')
        for m in meldungen:
            print('  !', m)

    pruef = kontrollbild(a.bild, pivots, boden, os.path.join(ordner, 'KONTROLLE.png'),
                         figurbild=a.figurbild)
    print('\nKontrollbild:', pruef)

    if a.schreiben:
        if meldungen:
            print('\nNICHT geschrieben — erst die Meldungen oben klaeren.')
            return
        rig_aktualisieren(os.path.join(ordner, 'rig.json'), pivots, boden, groesse)
        print('rig.json aktualisiert.')
        # Die Schablone wird aus rig.json gezeichnet — sie muss mitwandern,
        # sonst zeigt sie Drehpunkte, die es so nicht mehr gibt.
        try:
            import schablone
        except ImportError:
            from tutor import schablone
        ziel, groesse2 = schablone.schablone_bauen(ordner)
        print('Schablone neu gezeichnet: %s (%dx%d)' % (ziel, *groesse2))
    else:
        print('(nur angeschaut — mit --schreiben wird rig.json geaendert)')


if __name__ == '__main__':
    main()
