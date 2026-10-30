# tui/ansichten/rad_wahl.py
#
# Was Enter auf der Startseite öffnet (2026-10-10). Bis dahin stand in
# zentrale_tui.taste_verteilen eine if-Kette je Buchstabe. Seit die Räder
# selbst gebaute Apps tragen (Werkstatt, memory/hub/werkstatt.md), ist
# es eine Tabelle: fester Schlüssel → Öffner; eine eigene App ("app:<slug>")
# geht über ihre Adresse zentrale://<slug>/ an den Router (sprung.py) — so
# braucht keine neue App eine neue Zeile hier.
#
# u = das Bündel der Hauptschleife (zentrale_tui.run_ui).

import os

from . import cloud_folder
from .basis import BEENDEN

# Sasha, 2026-10-10: Elektronik bleibt fest im Rad und ist ein Desk.
ELEKTRONIK_DESK = "Elektronik"


def _tutor(u):
    if os.environ.get("ZENTRALE_ROOM_PARENT"):
        # Die TUI wurde AUS dem Zimmer heraus geöffnet (Wand-Kiosk, room.py
        # Alt+Z): das Zimmer liegt darunter und läuft weiter. 'u' heißt hier
        # »zurück ins Zimmer« — TUI zu, kein zweites Zimmer, das sich mit
        # dem ersten ums Mikro streitet.
        return BEENDEN
    u.app_start.tutor_oeffnen()
    return None


def _shop(u):
    """Den Shop baut eine eigene Sitzung (tui/ansichten/shop.py, Klasse
    Shop). Solange er nicht da ist: ein Hinweis statt eines Absturzes."""
    shop = getattr(u, "shop", None)
    if shop is None:
        u.bz.cmd_msg = "shop kommt gleich"
        return None
    shop.oeffnen()
    return None


OEFFNEN = {
    "a": lambda u: u.chat.oeffnen(),            # Leertaste: KI-Chat
    "k": lambda u: u.klavier.oeffnen(),
    "p": lambda u: u.post.oeffnen(),
    "c": lambda u: u.kalender.oeffnen(),
    "f": lambda u: u.fokus.oeffnen(),
    "n": lambda u: u.notizen.oeffnen(),
    "g": lambda u: u.graphen.oeffnen(),
    "m": lambda u: u.karte.oeffnen(),
    "u": _tutor,
    "e": lambda u: u.desk.direkt(ELEKTRONIK_DESK),
    # The cloud folder (2026-10-29): no view, it opens in the file manager.
    "cloud": lambda u: cloud_folder.open_folder(u) and None,
    # Erschaffen-Rad
    "werkstatt": lambda u: u.werkstatt.oeffnen(),
    "shop": _shop,
    # Schematix, the wiring map (2026-10-30, memory/hub/schematix.md)
    "schematix": lambda u: u.schematix.oeffnen(),
}


def oeffnen(u, schluessel):
    """Die App zum Schlüssel öffnen. -> BEENDEN | None"""
    if schluessel.startswith("app:"):
        u.router.zeigen("zentrale://%s/" % schluessel[4:])
        return None
    f = OEFFNEN.get(schluessel)
    return f(u) if f else None
