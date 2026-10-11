"""Post: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle).
Daten: test_fussleiste (Kategorien arbeit/privat, drei Mails)."""
import test_fussleiste as F
from tui import zentrale_tui as zt


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


def _ohne_kategorien(u):
    u.post.oeffnen()
    u.MAIL["data"] = {"categories": []}


def _antwort(u):
    F._post_lesen(u)
    _t(u, "a", "x")                          # schon ein Zeichen getippt


ZUSTAENDE = {
    "kategorien": F._post,
    "kategorien:leer": _ohne_kategorien,
    "ordner:leer": lambda u: (F._post_liste(u), u.MAIL.update(mails=[])),
    # Cursor auf der mittleren Mail: N (rauf) kennt der Rand-Trick des Tests nicht
    "liste": lambda u: (F._post_liste(u), u.MAIL.update(msel=1)),
    "liste:eingang": lambda u: (F._eingang_liste(u), u.MAIL.update(msel=1)),
    "lesen": F._post_lesen,
    "lesen:eingang": F._eingang_lesen,
    "lesen:offen": lambda u: (F._post_lesen(u), u.MAIL.update(expanded=True)),
    "lesen:offen:eingang": lambda u: (F._eingang_lesen(u), u.MAIL.update(expanded=True)),
    "einsortieren": lambda u: (F._post_liste(u), _t(u, "s")),
    "loeschen:frage": lambda u: (F._post_liste(u), _t(u, "d")),
    "antwort": _antwort,
    "antwort:frage": lambda u: (_antwort(u), _t(u, 27)),
}
