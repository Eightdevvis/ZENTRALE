# tui/ansichten/eigene_apps.py
#
# Die selbst gebauten Apps in der TUI (2026-10-10, Werkstatt,
# memory/hub/werkstatt.md). Das Backend kennt sie (GET
# /api/werkstatt/apps, core/werkstatt.py); hier wird daraus, was die TUI
# braucht — ohne je Datei zu lesen (die TUI ist ein Thin Client):
#   - ein Platz im App-Rad (startseite.EIGENE_APPS, hinter den festen),
#   - ein Pixel-Symbol (pixel.symbol_eintragen: Raster oder Motiv),
#   - eine Adresse zentrale://<slug>/ im Router (sprung.py), die ihren Desk
#     öffnet (Vorlage „desk"; eine neue Vorlage bekommt hier ihren Öffner).
# Seit 2026-10-25 auch die Apps aus dem Schaufenster (GET /api/apps, die mit
# `quelle`): gleicher Platz im Rad (vor den selbst gebauten), ihr Symbol aus
# `icon`, und ihre Adresse öffnet über app_oeffnen.py die eingerichtete
# Ansicht (bei mehreren mit Wahl).
# Geholt wird im Hintergrund: beim Start, nach jeder Änderung in der
# Werkstatt und sonst jede Minute (eine App kann auch von einem anderen
# Rechner kommen, über den Abgleich).

import threading
import time

from . import startseite
from .basis import api_call

try:
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

NEU_HOLEN_S = 60.0


class EigeneApps:
    def __init__(self, z, router, desk, oeffner=None):
        self.z, self.router, self.desk = z, router, desk
        self.oeffner = oeffner           # app_oeffnen.AppOeffnen (Apps aus dem Laden)
        self.apps = []                   # wie vom Backend, in Rad-Reihenfolge
        self.laden_apps = []             # Apps aus dem Schaufenster (/api/apps mit quelle)
        self._zuletzt = 0.0
        # Wie im Hintergrund geholt wird; Tests setzen „gleich ausführen".
        self.starten = lambda f: threading.Thread(target=f, daemon=True).start()

    def laden(self):
        """Im Hintergrund neu holen (Fehler: alles bleibt, wie es war)."""
        self._zuletzt = time.monotonic()

        def holen():
            try:
                d = api_call("/api/werkstatt/apps") or {}
            except Exception:
                return
            liste = d.get("apps") if isinstance(d, dict) else None
            if isinstance(liste, list):
                self.uebernehmen(liste)

        def holen_laden():
            try:
                d = api_call("/api/apps", timeout=5.0)
            except Exception:
                return
            if isinstance(d, list):
                self.laden_uebernehmen([a for a in d if isinstance(a, dict) and a.get("quelle")])
        self.starten(holen)
        if self.oeffner is not None:
            self.starten(holen_laden)

    def pflegen(self):
        """Aus der Hauptschleife: ab und zu frisch holen."""
        if time.monotonic() - self._zuletzt > NEU_HOLEN_S:
            self.laden()

    def uebernehmen(self, liste):
        """Liste vom Backend → Rad, Symbole, Router."""
        neu = [a for a in liste if isinstance(a, dict) and a.get("slug")]
        weg = {a["slug"] for a in self.apps} - {a["slug"] for a in neu}
        for slug in weg:
            pixel.symbol_austragen(slug)
            self.router.abmelden(slug)
        for a in neu:
            pixel.symbol_eintragen(a["slug"], a.get("icon"))
            self.router.registrieren(a["slug"], self._oeffner(a), self.desk.DESK)
        self.apps = neu
        self._rad()

    def laden_uebernehmen(self, liste):
        """Apps aus dem Schaufenster (Einträge aus /api/apps) → Rad, Symbole,
        Router. Ein Name, den ein festes Symbol trägt, bleibt unangetastet."""
        fest = set(pixel.FESTE_MOTIVE) | set(startseite.RAD_SYMBOLE)
        neu = [a for a in liste if a.get("name") and a["name"] not in fest]
        weg = {a["name"] for a in self.laden_apps} - {a["name"] for a in neu}
        for name in weg:
            pixel.symbol_austragen(name)
            self.router.abmelden(name)
        for a in neu:
            pixel.symbol_eintragen(a["name"], a.get("icon"))
            self.router.registrieren(a["name"], self._oeffner_laden(a), None)
        self.laden_apps = neu
        self._rad()

    def _rad(self):
        startseite.EIGENE_APPS[:] = ([("app:" + a["name"], a["name"]) for a in self.laden_apps]
                                     + [("app:" + a["slug"], a["slug"]) for a in self.apps])

    def _oeffner_laden(self, app):
        def zeigen(pfad, abfrage):
            return self.oeffner.oeffnen(app)
        return zeigen

    def _oeffner(self, app):
        def zeigen(pfad, abfrage):
            if app.get("vorlage") == "desk" and app.get("desk"):
                self.desk.direkt(app["desk"])
                return True
            return False
        return zeigen
