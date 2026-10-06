# ui/routen/__init__.py
#
# Die HTTP-Routen von ZENTRALE, ein Modul pro Bereich. ui/app.py legt die
# Flask-App an und hängt hier alle Bereiche ein — neue Routen gehören in
# den passenden Bereich (oder einen neuen), nie zurück in app.py.

from ui.routen import zustand, erfassung, klavier, listen, notizen, karte, kalender, ki, stimme, tutor, mail

BEREICHE = (zustand, erfassung, klavier, listen, notizen, karte, kalender, ki, stimme, tutor, mail,)


def einhaengen(app):
    """Alle Bereichs-Blueprints an die App hängen."""
    for bereich in BEREICHE:
        app.register_blueprint(bereich.bp)
