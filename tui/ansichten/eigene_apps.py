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
    def __init__(self, z, router, desk):
        self.z, self.router, self.desk = z, router, desk
        self.apps = []                   # wie vom Backend, in Rad-Reihenfolge
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
        self.starten(holen)

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
        startseite.EIGENE_APPS[:] = [("app:" + a["slug"], a["slug"]) for a in neu]

    def _oeffner(self, app):
        def zeigen(pfad, abfrage):
            if app.get("vorlage") == "desk" and app.get("desk"):
                self.desk.direkt(app["desk"])
                return True
            return False
        return zeigen
