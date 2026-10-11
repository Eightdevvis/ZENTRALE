"""Graph-Werkzeug: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle).
Die Welt hat zwei Zahl-Graphen („schlaf", „laune", test_fussleiste.GRAPHEN)."""
from tui import zentrale_tui as zt


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def liste(u):
    u.graphen.oeffnen()


def solo(typ, *getippt):
    """„schlaf" solo öffnen, als Graph vom Typ `typ`, dann etwas tippen
    (damit ⌫ und enter in der Ansicht etwas zu tun haben)."""
    def aufbau(u):
        liste(u)
        u.G["graphs"][0]["type"] = typ
        _t(u, 10, *getippt)
    return aufbau


ZUSTAENDE = {
    "liste": liste,
    "liste:leer": lambda u: (liste(u), u.G.update(graphs=[])),
    "liste:frage": lambda u: (liste(u), _t(u, "d")),
    "neu": lambda u: (liste(u), _t(u, "n", "x")),
    "erinnerung": lambda u: (liste(u), _t(u, "r")),              # „20:00" steht schon
    "solo:zahl": solo("number", "7"),
    "solo:zeit": solo("time", "2"),
    "solo:periode": solo("period", "2"),
    "solo:periode:bis": solo("period", *"22:00", 10, "7"),
    "solo:skala": solo("scale"),
}
