# ui/routen/__init__.py
#
# Die HTTP-Routen von ZENTRALE, ein Modul pro Bereich. ui/app.py legt die
# Flask-App an und hängt hier alle Bereiche ein — neue Routen gehören in
# den passenden Bereich (oder einen neuen), nie zurück in app.py.

from ui.routen import zugang, zustand, erfassung, klavier, listen, notizen, karte, kalender, ki, gespraeche, stimme, mail, skills, ablage, projekte, morgenblick, abgleich, desk

# zugang zuerst: seine Prüfung (before_app_request) muss vor allem anderen
# laufen (memory/betrieb/zugang.md, 2026-10-08).
BEREICHE = (zugang, zustand, erfassung, klavier, listen, notizen, karte, kalender, ki, gespraeche, stimme, mail, skills, ablage, projekte, morgenblick, abgleich, desk,)


def einhaengen(app):
    """Alle Bereichs-Blueprints an die App hängen."""
    for bereich in BEREICHE:
        app.register_blueprint(bereich.bp)
