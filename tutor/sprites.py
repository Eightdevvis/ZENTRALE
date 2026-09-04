#!/usr/bin/env python3
# tutor/sprites.py
#
# Das RIG: gemalte Einzelteile statt pygame-Polygone für die Tutor-Persona.
#
# Prinzip (Papier-Puppe): die Figur ist kein Bild, sondern ein Satz Teile —
# Kopf, Torso, Arme, Beine — die jeweils an einem DREHPUNKT hängen und um
# diesen rotiert werden. Kopf hängt am Torso, Unterarm am Oberarm usw.
# (`eltern` in rig.json). Bewegt sich der Torso, kommt alles mit.
#
# Warum das für Sasha bequem ist: er malt jedes Teil auf einer IMMER GLEICH
# GROSSEN Leinwand an der Stelle, wo es am Körper sitzt, und exportiert jede
# Ebene einzeln als PNG mit transparentem Rest. Dadurch sind alle Teilbilder
# deckungsgleich, und der Drehpunkt ist bloss noch eine Koordinate in
# rig.json — er muss beim Malen NICHTS technisches markieren.
#
# Fehlt ein Teil, liefert `bild()` None; room.py zeichnet dann für genau
# dieses Teil weiter sein altes Polygon. So kann Teil für Teil gemalt werden,
# ohne dass je ein Stichtag kommt, an dem alles fertig sein muss.
#
# Die PNGs werden intern auf ihren sichtbaren Bereich zugeschnitten (der Rest
# ist ja transparent) — das kostet sonst bei jeder Drehung unnötig Rechenzeit.
# Der Drehpunkt wandert beim Zuschneiden korrekt mit.

import os
import json
import math
import time

import pygame


# Auf wie viel Grad die Drehung für den Cache gerundet wird. Feiner = weicher,
# aber mehr vorgedrehte Bilder im Speicher. 2° sieht man nicht.
_WINKEL_RASTER = 2.0
_SKALA_RASTER = 0.02
# So oft (Sekunden) wird geschaut, ob Sasha eine Datei neu gespeichert hat.
_RELOAD_INTERVALL = 1.0


class _Teil:
    """Ein gemaltes Einzelteil samt Drehpunkt, zugeschnitten und gecacht."""

    def __init__(self, flaeche, pivot_x, pivot_y, mtime):
        self.mtime = mtime
        roh = flaeche.convert_alpha()
        box = roh.get_bounding_rect()          # sichtbarer Bereich
        if box.width <= 0 or box.height <= 0:  # komplett leeres PNG
            box = pygame.Rect(0, 0, roh.get_width(), roh.get_height())
        self.bild = roh.subsurface(box).copy()
        # Drehpunkt relativ zur MITTE des zugeschnittenen Bildes
        self.px = pivot_x - (box.x + box.width / 2.0)
        self.py = pivot_y - (box.y + box.height / 2.0)
        self._cache = {}

    def gedreht(self, skala, winkel):
        """Bild in gewünschter Grösse/Drehung + Versatz des Drehpunkts dazu."""
        key = (round(skala / _SKALA_RASTER), round(winkel / _WINKEL_RASTER))
        fertig = self._cache.get(key)
        if fertig is None:
            sk = key[0] * _SKALA_RASTER
            wi = key[1] * _WINKEL_RASTER
            # Winkel-Konvention (siehe room.py): 0° = Teil hängt nach unten,
            # +90° = zeigt nach rechts. Das entspricht pygames Drehrichtung.
            bild = pygame.transform.rotozoom(self.bild, wi, max(0.01, sk))
            rad = math.radians(wi)
            co, si = math.cos(rad), math.sin(rad)
            vx, vy = self.px * sk, self.py * sk
            # Drehpunkt mitdrehen (Bildschirm-Koordinaten, y zeigt nach unten)
            dx = vx * co + vy * si
            dy = -vx * si + vy * co
            fertig = (bild, dx, dy)
            if len(self._cache) < 512:
                self._cache[key] = fertig
        return fertig


class Rig:
    """Lädt einen Ordner gemalter Teile und zeichnet sie an die richtige Stelle.

    Benutzung aus room.py:
        rig = Rig(pfad)                      # einmal beim Start
        rig.aktualisieren()                  # pro Frame, lädt Geändertes nach
        if rig.hat('kopf'):
            rig.zeichne(surf, 'kopf', x, y, skala, winkel)
        else:
            ...altes Polygon...
    """

    def __init__(self, ordner):
        self.ordner = ordner
        self.leinwand = {'breite': 512, 'hoehe': 640, 'boden_y': 604, 'mitte_x': 256}
        self.slots = {}
        self.reihenfolge = []
        self.varianten = {}
        self._teile = {}          # "slot" oder "slot:variante" → _Teil | None
        self._letzter_check = 0.0
        self.aktiv = False
        self._lade_rig()

    # -- Laden ---------------------------------------------------------------
    def _lade_rig(self):
        pfad = os.path.join(self.ordner, 'rig.json')
        try:
            with open(pfad, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            return
        self.leinwand.update(d.get('leinwand') or {})
        self.slots = {k: v for k, v in (d.get('slots') or {}).items()}
        self.reihenfolge = list(d.get('reihenfolge') or self.slots.keys())
        self.varianten = d.get('varianten') or {}
        self.aktiv = True
        self._lade_alle()

    def _dateiname(self, slot, variante=None):
        if variante:
            rel = (self.varianten.get(slot) or {}).get(variante)
            if rel:
                return os.path.join(self.ordner, rel)
            return None
        return os.path.join(self.ordner, slot + '.png')

    def _lade_teil(self, slot, variante=None):
        """Lädt EIN Teil neu, wenn die Datei existiert und sich geändert hat."""
        key = slot if not variante else '%s:%s' % (slot, variante)
        pfad = self._dateiname(slot, variante)
        if not pfad or not os.path.exists(pfad):
            self._teile[key] = None
            return
        try:
            mtime = os.path.getmtime(pfad)
        except OSError:
            self._teile[key] = None
            return
        vorhanden = self._teile.get(key)
        if vorhanden is not None and abs(vorhanden.mtime - mtime) < 0.001:
            return                                   # unverändert
        info = self.slots.get(slot) or {}
        pv = info.get('pivot') or [self.leinwand['mitte_x'], self.leinwand['boden_y']]
        try:
            flaeche = pygame.image.load(pfad)
        except Exception:
            self._teile[key] = None
            return
        self._teile[key] = _Teil(flaeche, float(pv[0]), float(pv[1]), mtime)

    def _lade_alle(self):
        for slot in self.slots:
            self._lade_teil(slot)
            for variante in (self.varianten.get(slot) or {}):
                self._lade_teil(slot, variante)

    def aktualisieren(self):
        """Pro Frame aufrufen: zieht frisch gespeicherte Bilder nach (Hot-Reload).

        Damit kann Sasha ein Teil malen, speichern — und es erscheint im
        laufenden Zimmerfenster, ohne Neustart."""
        if not self.aktiv:
            return
        jetzt = time.time()
        if jetzt - self._letzter_check < _RELOAD_INTERVALL:
            return
        self._letzter_check = jetzt
        self._lade_alle()

    # -- Abfragen ------------------------------------------------------------
    def hat(self, slot, variante=None):
        return self.teil(slot, variante) is not None

    def teil(self, slot, variante=None):
        """Bestes vorhandenes Bild für einen Slot.

        Reihenfolge: gewünschte Variante → Grunddatei (<slot>.png) → irgendeine
        andere gemalte Variante. Letzteres, damit ein einzelner gemalter Mund
        schon überall erscheint und nicht auf einen Platzhalter zurückfällt,
        bloss weil die Variante für 'traurig' noch fehlt."""
        if variante:
            t = self._teile.get('%s:%s' % (slot, variante))
            if t is not None:
                return t
        t = self._teile.get(slot)
        if t is not None:
            return t
        for name in (self.varianten.get(slot) or {}):
            t = self._teile.get('%s:%s' % (slot, name))
            if t is not None:
                return t
        return None

    def leer(self):
        """True, wenn noch gar kein Teil gemalt ist → room.py bleibt bei Polygonen."""
        return not any(t is not None for t in self._teile.values())

    def _slot_vorhanden(self, slot):
        """Slots wie 'mund' haben keine eigene Datei, sondern nur Varianten —
        die gelten als vorhanden, sobald mindestens eine Variante gemalt ist."""
        if self._teile.get(slot) is not None:
            return True
        return any(self._teile.get('%s:%s' % (slot, v)) is not None
                   for v in (self.varianten.get(slot) or {}))

    def fehlende(self):
        """Slots, für die noch kein Bild existiert (in Zeichenreihenfolge)."""
        return [s for s in self.reihenfolge if not self._slot_vorhanden(s)]

    def gemalte(self):
        return [s for s in self.reihenfolge if self._slot_vorhanden(s)]

    # -- Zeichnen ------------------------------------------------------------
    def zeichne(self, surf, slot, x, y, skala, winkel=0.0, variante=None, alpha=255):
        """Setzt das Teil so, dass sein Drehpunkt genau auf (x, y) liegt."""
        t = self.teil(slot, variante)
        if t is None:
            return False
        bild, dx, dy = t.gedreht(skala, winkel)
        if alpha < 255:
            bild = bild.copy()
            bild.set_alpha(alpha)
        r = bild.get_rect()
        r.center = (int(round(x - dx)), int(round(y - dy)))
        surf.blit(bild, r)
        return True

    def figur_hoehe(self):
        """Höhe der Figur auf der Leinwand — für die Umrechnung der Skalierung."""
        return float(self.leinwand.get('boden_y', 604))


def lade_rig(name='lucia'):
    """Rig aus tutor/bilder/<name>/ laden. Gibt immer ein Rig zurück (evtl. leer)."""
    hier = os.path.dirname(os.path.abspath(__file__))
    return Rig(os.path.join(hier, 'bilder', name))
