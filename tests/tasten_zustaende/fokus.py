"""Liste/Fokus: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle).
Daten: test_fussleiste.LISTEN (einkauf: milch offen, brot erledigt; ideen
und reise leer), /api/projects ist leer — Projekt-Knoten der Wurzel werden
hier von Hand gesetzt."""
import curses

import test_fussleiste as F
from tui import zentrale_tui as zt


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def wald(u):
    u.fokus.oeffnen()


def _projekt(u, mit_kindern):
    """Wurzel mit „milch" als Projekt-Knoten oben (Ordner oder Blatt)."""
    if mit_kindern:
        F.JETZT["listen"][0]["items"][0]["items"] = [{"id": 5, "text": "x", "done": False}]
    wald(u)
    u.L["proots"] = [{"lid": "l1", "iid": 1}]
    u.L["fsel"] = 0


def ebene(u):
    F._ebene(u)                                 # „einkauf", Cursor auf milch


def _alles_erledigt(u):
    F.JETZT["listen"][0]["items"][0]["done"] = True   # nur noch der Bernstein
    ebene(u)


def _nur_eine_liste(u):
    F.JETZT["listen"] = F.JETZT["listen"][:1]
    wald(u)
    _t(u, ">")


ZUSTAENDE = {
    "wald": wald,
    "wald:ordner": lambda u: _projekt(u, True),
    "wald:punkt": lambda u: _projekt(u, False),
    "wald:leer": lambda u: (wald(u), u.L.update(lists=[], proots=[])),
    "wald:frage": lambda u: (wald(u), _t(u, "d")),
    "wald:neu": lambda u: (wald(u), _t(u, "n", "x")),
    "wald:umbenennen": lambda u: (wald(u), _t(u, "r")),
    "liste": ebene,
    "liste:bernstein": lambda u: (ebene(u), _t(u, curses.KEY_UP)),
    "liste:bernstein:leer": _alles_erledigt,
    "liste:leer": lambda u: (wald(u), _t(u, curses.KEY_DOWN, 10)),   # „ideen"
    "liste:neu": lambda u: (ebene(u), _t(u, "a", "x")),
    "liste:umbenennen": lambda u: (ebene(u), _t(u, "r")),
    "einordnen": F._einordnen,
    "einordnen:leer": _nur_eine_liste,
    "verschieben": lambda u: (ebene(u), _t(u, "m")),
    "verschieben:name": lambda u: (ebene(u), _t(u, "m", 10)),
}
