#!/usr/bin/env python3
# tutor/schablone.py
#
# Erzeugt die MAL-SCHABLONE für die Puppe: ein PNG in Leinwandgröße, auf dem
# jeder Körperteil-Bereich umrissen und jeder Drehpunkt als Fadenkreuz mit
# Namen eingezeichnet ist.
#
# Wofür: Sasha öffnet die Schablone in seinem Malprogramm als unterste,
# halbtransparente Hilfsebene. Er malt darüber — jedes Teil auf eine eigene
# Ebene. Weil die Leinwand bei allen Teilen gleich gross ist und er nichts
# verschiebt, sitzen am Ende alle Drehpunkte automatisch richtig. Er muss
# also nirgends einen Drehpunkt "definieren"; die Schablone zeigt sie nur an,
# damit er weiss, wo ein Gelenk sitzt (dort darf das Teil nicht abgeschnitten
# wirken, dort dreht es sich später).
#
# Die Schablone wird aus rig.json erzeugt und bleibt damit automatisch
# richtig, wenn sich am Bauplan etwas ändert.
#
# Aufruf:  venv/bin/python tutor/schablone.py
#          venv/bin/python tutor/schablone.py --test <ordner>   (Prüfteile)

import os
import sys
import json
import math
import argparse

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame


# Ungefähre Ausdehnung der Teile auf der Leinwand — nur als Malhilfe gedacht,
# nicht als Grenze: wer breitere Ärmel malt, malt einfach drüber hinaus.
# (drehpunkt-relativ: nach oben/unten/links/rechts in Pixeln)
_BEREICHE = {
    'torso':        (240, 20, 100, 100),
    'kopf':         (180, 30, 95, 95),
    'arm_l_ober':   (25, 100, 30, 30),
    'arm_l_unter':  (20, 105, 28, 28),
    'arm_r_ober':   (25, 100, 30, 30),
    'arm_r_unter':  (20, 105, 28, 28),
    'bein_l_ober':  (20, 95, 32, 32),
    'bein_l_unter': (15, 95, 28, 28),
    'bein_r_ober':  (20, 95, 32, 32),
    'bein_r_unter': (15, 95, 28, 28),
    'auge_l':       (18, 18, 20, 20),
    'auge_r':       (18, 18, 20, 20),
    'mund':         (16, 16, 26, 26),
}

# Damit sich die Namen am Rand nicht überlagern (Gelenke liegen teils auf
# gleicher Höhe), bekommt jeder Slot einen kleinen vertikalen Versatz.
_LABEL_VERSATZ = {
    'auge_l': -16, 'auge_r': -16, 'mund': 8, 'kopf': 0,
    'arm_l_ober': -14, 'arm_r_ober': -14,
    'arm_l_unter': 0, 'arm_r_unter': 0,
    'bein_l_ober': -16, 'bein_r_ober': 14,
    'bein_l_unter': -16, 'bein_r_unter': 14,
    'torso': 0,
}

_GITTER = (58, 58, 68)
_UMRISS = (90, 130, 170)
_PIVOT = (230, 70, 90)
_TEXT = (150, 160, 175)
_BODEN = (110, 95, 60)


def _rig_lesen(ordner):
    with open(os.path.join(ordner, 'rig.json'), 'r', encoding='utf-8') as f:
        return json.load(f)


def schablone_bauen(ordner):
    d = _rig_lesen(ordner)
    lw = d['leinwand']
    W, H = int(lw['breite']), int(lw['hoehe'])
    boden = int(lw['boden_y'])
    mitte = int(lw['mitte_x'])

    pygame.init()
    pygame.font.init()
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    font = pygame.font.SysFont('dejavusans', 13)
    klein = pygame.font.SysFont('dejavusans', 11)

    # Gitter alle 32 px — hilft beim Augenmass
    for gx in range(0, W, 32):
        pygame.draw.line(surf, _GITTER + (70,), (gx, 0), (gx, H))
    for gy in range(0, H, 32):
        pygame.draw.line(surf, _GITTER + (70,), (0, gy), (W, gy))

    # Mittelachse + Bodenlinie
    pygame.draw.line(surf, _GITTER + (180,), (mitte, 0), (mitte, H), 1)
    pygame.draw.line(surf, _BODEN + (220,), (0, boden), (W, boden), 2)
    surf.blit(klein.render('Boden — hier stehen die Fuesse', True, _BODEN), (8, boden + 5))

    # Silhouette der heutigen Figur — zeigt die Proportionen, an denen Zimmer,
    # Couch und Sprechblase ausgerichtet sind. Nur Orientierung, keine Vorgabe:
    # wer anders proportioniert malen will, sagt Bescheid, dann wandern die
    # Drehpunkte in rig.json mit.
    sil = (120, 128, 145, 38)
    E = 6.0                       # Leinwand-Pixel pro Einheit der alten Figur
    def u(ux, uy):                # Einheiten → Leinwand
        return (mitte + ux * E, boden + uy * E)
    pygame.draw.polygon(surf, sil, [u(-15, -22), u(15, -22), u(12, -62), u(-12, -62)])
    pygame.draw.circle(surf, sil, (int(mitte), int(boden - 78 * E)), int(15 * E))
    for sx in (-1, 1):
        pygame.draw.rect(surf, sil, (mitte + sx * 14 * E - 3 * E, boden - 59 * E, 6 * E, 30 * E))
        pygame.draw.rect(surf, sil, (mitte + sx * 5 * E - 4 * E, boden - 26 * E, 8 * E, 28 * E))

    # Teilbereiche + Drehpunkte
    for slot in d['reihenfolge']:
        info = d['slots'].get(slot)
        if not info:
            continue
        px, py = info['pivot']
        oben, unten, links, rechts = _BEREICHE.get(slot, (40, 40, 40, 40))
        r = pygame.Rect(px - links, py - oben, links + rechts, oben + unten)
        pygame.draw.rect(surf, _UMRISS + (110,), r, 1)

        # Fadenkreuz auf dem Drehpunkt
        pygame.draw.line(surf, _PIVOT + (255,), (px - 9, py), (px + 9, py), 2)
        pygame.draw.line(surf, _PIVOT + (255,), (px, py - 9), (px, py + 9), 2)
        pygame.draw.circle(surf, _PIVOT + (255,), (int(px), int(py)), 4, 1)

        # Beschriftung seitlich rausziehen, mit Fuehrungslinie — sonst kleben
        # die Namen der linken und rechten Gliedmasse aufeinander.
        links_herum = px <= mitte
        bx = 14 if links_herum else W - 14
        by = py + _LABEL_VERSATZ.get(slot, 0)
        txt = font.render(slot, True, _TEXT)
        tx = bx if links_herum else bx - txt.get_width()
        pygame.draw.line(surf, _UMRISS + (90,),
                         (tx + (txt.get_width() + 4 if links_herum else -4), by),
                         (px, py), 1)
        surf.blit(txt, (tx, by - 8))

    kopf = pygame.font.SysFont('dejavusans', 15, bold=True)
    surf.blit(kopf.render('Mal-Schablone — Kreuze = Drehpunkte', True, (200, 205, 215)), (10, 8))
    surf.blit(klein.render('Als unterste Hilfsebene benutzen. Jedes Teil auf EIGENE Ebene,', True, _TEXT), (10, 28))
    surf.blit(klein.render('nichts verschieben, jede Ebene einzeln als PNG exportieren.', True, _TEXT), (10, 42))

    ziel = os.path.join(ordner, 'SCHABLONE.png')
    pygame.image.save(surf, ziel)
    return ziel, (W, H)


def testteile_bauen(rig_ordner, ziel_ordner):
    """Bunte Prüf-Teile in Leinwandgröße — nur zum Testen der Mechanik."""
    d = _rig_lesen(rig_ordner)
    lw = d['leinwand']
    W, H = int(lw['breite']), int(lw['hoehe'])
    os.makedirs(os.path.join(ziel_ordner, 'gesicht'), exist_ok=True)
    with open(os.path.join(ziel_ordner, 'rig.json'), 'w', encoding='utf-8') as f:
        json.dump(d, f)

    pygame.init()
    farben = {
        'torso': (190, 80, 80), 'kopf': (240, 205, 175),
        'arm_l_ober': (120, 170, 210), 'arm_l_unter': (90, 140, 190),
        'arm_r_ober': (120, 210, 170), 'arm_r_unter': (90, 190, 140),
        'bein_l_ober': (200, 170, 90), 'bein_l_unter': (170, 140, 70),
        'bein_r_ober': (180, 150, 200), 'bein_r_unter': (150, 120, 180),
    }
    for slot, farbe in farben.items():
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        px, py = d['slots'][slot]['pivot']
        oben, unten, links, rechts = _BEREICHE[slot]
        if slot == 'kopf':
            pygame.draw.circle(s, farbe, (int(px), int(py - 84)), 92)
        elif slot == 'torso':
            pygame.draw.polygon(s, farbe, [(px - 78, py), (px + 78, py),
                                           (px + 66, py - 240), (px - 66, py - 240)])
        else:
            pygame.draw.rect(s, farbe, (px - links, py - 6, links + rechts, unten),
                             border_radius=14)
        # Drehpunkt sichtbar markieren, damit man Fehler sofort sieht
        pygame.draw.circle(s, (255, 255, 255), (int(px), int(py)), 5)
        pygame.image.save(s, os.path.join(ziel_ordner, slot + '.png'))

    for slot, varianten in d.get('varianten', {}).items():
        px, py = d['slots'][slot]['pivot']
        for name, rel in varianten.items():
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            if slot.startswith('auge'):
                if name == 'zu':
                    pygame.draw.line(s, (40, 30, 35), (px - 11, py), (px + 11, py), 4)
                else:
                    rr = 12 if name == 'weit' else 8
                    pygame.draw.circle(s, (40, 30, 35), (int(px), int(py)), rr)
            else:
                if name == 'offen':
                    pygame.draw.circle(s, (120, 40, 50), (int(px), int(py)), 14)
                elif name == 'strich':
                    pygame.draw.line(s, (120, 40, 50), (px - 14, py), (px + 14, py), 4)
                elif name == 'traurig':
                    pygame.draw.arc(s, (120, 40, 50), (px - 16, py, 32, 20), 0, math.pi, 4)
                else:
                    pygame.draw.arc(s, (120, 40, 50), (px - 16, py - 12, 32, 24),
                                    math.pi, 2 * math.pi, 4)
            pygame.image.save(s, os.path.join(ziel_ordner, rel))
    return ziel_ordner


def main():
    hier = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description='Mal-Schablone fuer die Tutor-Puppe')
    ap.add_argument('--figur', default='lucia')
    ap.add_argument('--test', metavar='ORDNER', help='Pruef-Teile erzeugen')
    a = ap.parse_args()

    ordner = os.path.join(hier, 'assets', 'figuren', a.figur)
    if a.test:
        os.makedirs(a.test, exist_ok=True)
        testteile_bauen(ordner, a.test)
        print('Testteile in', a.test)
        return
    ziel, groesse = schablone_bauen(ordner)
    print('Schablone: %s  (%dx%d)' % (ziel, groesse[0], groesse[1]))


if __name__ == '__main__':
    main()
