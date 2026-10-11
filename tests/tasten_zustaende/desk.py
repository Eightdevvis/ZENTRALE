"""Desk: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle). Der Desk
„Elektronik" aus tests/test_fussleiste.py: Zettel m in der Mitte, je einer
oben/unten/links/rechts, ein Bild b, eine Kachel k."""
import curses

import test_fussleiste as F
from tui import zentrale_tui as zt
from tui.bausteine.feld_dialog import FeldDialog

_LINKS = curses.KEY_LEFT


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def _fokus(eid):
    def aufbau(u):
        F._desk(u)
        u.DESK["canvas"].fokus = eid
    return aufbau


def _fremd(u):
    """Ein Knoten, den nur Obsidian kennt: Art ohne eigene Zeilen."""
    F._desk(u)
    c = u.DESK["canvas"]
    c.elemente.append({"id": "f", "art": "fremd", "typ": "file", "titel": "plan.pdf",
                       "x": 60, "y": 0, "w": 12, "h": 4})
    c.fokus = "f"


def _bild_wahl(u):
    F._desk(u); _t(u, "+")
    u.DESK["art_wahl"]["sel"] = 1                    # bild
    _t(u, 10)


def _pfad(u):
    _bild_wahl(u); _t(u, curses.KEY_DOWN, 10, "a", "b", _LINKS)


def _dialog(schema=None, feld=0):
    """Wähler hinter + → Kalender (Katalog des Hubs) → Dialog; mit `schema`
    ein anderer Dialog an derselben Stelle (Auswahl, mehrere Felder, keins)."""
    def aufbau(u):
        F._desk(u); _t(u, "+")
        u.DESK["art_wahl"]["sel"] = 2                # kachel: kalender/ausschnitt
        _t(u, 10)
        if schema is not None:
            u.DESK["modal"] = FeldDialog(schema, titel="kalender")
            u.DESK["modal"].feld = feld
    return aufbau


_WAHL = {"modus": {"title": "modus", "enum": ["woche", "monat"]}}
_ZAHL = {"tage": {"title": "tage", "type": "integer", "default": 7}}

ZUSTAENDE = {
    "wahl": F._desk_wahl,
    "name": lambda u: (F._desk_wahl(u), _t(u, "n", "a", "b", _LINKS)),
    "neu": F._desk_neu,
    "bild": _bild_wahl,
    "pfad": _pfad,
    "canvas:ruhe": _fokus(None),
    "canvas:kasten": _fremd,
    "canvas:notiz": F._desk,
    "canvas:bild": F._desk_bild,
    "canvas:kachel": F._desk_kachel,
    "canvas:greifen": F._desk_greifen,
    "canvas:verbinden": F._desk_verbinden,
    "canvas:frage": F._desk_frage,
    "canvas:groesse": F._desk_groesse,
    # Zettel „mitte" bearbeiten: zweite Zeile „x", Cursor davor (so tun auch
    # ↑↓, home und del etwas)
    "text:schreiben": lambda u: (F._desk(u), _t(u, "e", 10, "x", _LINKS)),
    "titel:tippen": lambda u: (F._desk_bild(u), _t(u, "e", "a", "b", _LINKS)),
    "dialog:tippen": _dialog(),
    "dialog:waehlen": _dialog({"properties": _WAHL}),
    "dialog:felder:tippen": _dialog({"properties": dict(_ZAHL, **_WAHL)}),
    "dialog:felder:waehlen": _dialog({"properties": dict(_ZAHL, **_WAHL)}, feld=1),
    "dialog:leer": _dialog({}),
}
