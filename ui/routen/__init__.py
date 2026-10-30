# ui/routen/__init__.py
#
# Die HTTP-Routen von ZENTRALE, ein Modul pro Bereich. ui/app.py legt die
# Flask-App an und hängt hier alle Bereiche ein — neue Routen gehören in
# den passenden Bereich (oder einen neuen), nie zurück in app.py.

from ui.routen import zugang, zustand, erfassung, klavier, listen, notizen, kalender, ki, gespraeche, stimme, mail, skills, ablage, projekte, morgenblick, abgleich, desk, kachel
# karte ist seit 2026-10-22 eine App (Repo zentrale-karte): /api/map/* reicht hub_apps weiter.
from ui.routen import shop  # Schaufenster (2026-10-10)
from ui.routen import werkstatt  # Werkstatt (2026-10-10)
from ui.routen import tasten  # Tastentabellen der Apps (2026-10-11)
from ui.routen import browser  # Browser-Front unter /zentrale (2026-10-12)
from ui.routen import hub_apps  # Apps: Liste, Start/Stopp, Weiterleitung (2026-10-22)
from ui.routen import hub_wires  # Wires of this node, Run gate (building kit steps 9/9b, 2026-10-30)
from ui.routen import schematix  # Schematix, the wiring map (building kit steps 13-15, 2026-10-30)

# zugang zuerst: seine Prüfung (before_app_request) muss vor allem anderen
# laufen (memory/betrieb/zugang.md, 2026-10-08). hub_apps gleich danach: die
# Weiterleitung an Apps (routen im app.toml) greift vor allen eigenen Routen.
BEREICHE = (zugang, hub_apps, zustand, erfassung, klavier, listen, notizen, kalender, ki, gespraeche, stimme, mail, skills, ablage, projekte, morgenblick, abgleich, desk, kachel,
            shop, werkstatt, tasten, browser, hub_wires, schematix,)


def einhaengen(app):
    """Alle Bereichs-Blueprints an die App hängen."""
    for bereich in BEREICHE:
        app.register_blueprint(bereich.bp)
