"""Schaufenster: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle). Die Welt
hat zwei Kategorien: Icons (post, karte; Themen pixel, post, karte) und Apps
(leer), test_fussleiste.antwort."""
import curses

from tui import zentrale_tui as zt


def regal(u):
    u.shop.oeffnen()


def apps(u):
    """Kategorie Apps mit zwei Apps — die Welt hat sie leer."""
    regal(u)
    u.SHOP.update(kat=1, sel=0, themen=["geld"], stuecke=[{
        "@type": "SoftwareApplication", "@id": "zentrale://shop/apps/" + n,
        "identifier": n, "name": n, "description": "", "category": "apps",
        "keywords": ["geld"], "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}}
        for n in ("budget", "sparbuch")])


ZUSTAENDE = {
    "regal": regal,
    "regal:ohne_thema": lambda u: (regal(u), u.SHOP.update(themen=[])),
    "leer": lambda u: (regal(u), zt.taste_verteilen(u, curses.KEY_RIGHT)),     # Apps
    "leer:thema": lambda u: (regal(u), u.SHOP.update(stuecke=[], thema="pixel")),
    "apps": apps,
    "apps:ohne_thema": lambda u: (apps(u), u.SHOP.update(themen=[])),
    "laedt": lambda u: (apps(u), u.SHOP.update(laedt=True)),
    "wahl": lambda u: (apps(u), u.shop.app_laden()),
    "fehler": lambda u: (regal(u), u.SHOP.update(kategorien=[], stuecke=[], themen=[],
                                                 msg="backend nicht erreichbar")),
}
