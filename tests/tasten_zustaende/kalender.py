"""Kalender: zu jeder Ansicht der Tastentabelle ein Weg dorthin
(tests/test_tastentabellen.py drückt dort jede Taste der Tabelle).

Der gewählte Tag ist nie heute (sonst täte Strg-G nichts), der Beispieltag
kalender_beispiel.HEUTE hat mehrere Termine, der „leere" Tag wird gesucht."""
import curses
from datetime import date, timedelta

from tui import zentrale_tui as zt
from tui.ansichten import kalender_beispiel as kb
from tui.ansichten import kalender_phasen
from tui.ansichten import kalender_werkzeuge as kw

ESC, ENTER, TAB = 27, 10, 9
AUSWAHL = {"listen": [{"art": "liste", "id": "l_todo", "name": "todo",
                       "titel": "Steuern planen", "zustand": "ok"},
                      {"art": "liste", "id": "l_haus", "name": "tasks",
                       "titel": "Bad putzen", "zustand": "ok"}],
           "projekte": []}


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))
        try:
            zt.bild_zeichnen(u)
        except curses.error:
            pass


def _bed(u):
    return u.kalender.bedienung


def _tag(u, d):
    _bed(u).setze_tag(d)
    _t(u)


def _beispieltag():
    d = date.fromisoformat(kb.HEUTE)
    return d if d != date.today() else d + timedelta(days=1)


def _leerer_tag(u):
    d = _beispieltag() + timedelta(days=1)
    while not (_bed(u).termine(d) == [] and d != date.today()):
        d += timedelta(days=1)
    return d


def _kal(u, tag=None):
    u.kalender.oeffnen()
    _t(u)
    _tag(u, tag or _beispieltag())


def _todo(u, weekplan="voll"):
    _kal(u)
    _t(u, TAB, TAB)
    d = _bed(u).daten()
    if weekplan == "leer":
        d["weekplan"]["items"] = []
    elif weekplan == "ohne":
        d["weekplan"] = None


def _vom_monat(u, leer=False, kasten=0, weekplan="voll"):
    u.kalender.oeffnen()
    _t(u, "v")
    _tag(u, _leerer_tag(u) if leer else _beispieltag())
    _t(u, ENTER, *([TAB] * kasten))
    if weekplan != "voll":
        d = _bed(u).daten()
        if weekplan == "leer":
            d["weekplan"]["items"] = []
        else:
            d["weekplan"] = None


def _woche(u, leer=False):
    u.kalender.oeffnen()
    _t(u, "v", "v")
    _tag(u, _leerer_tag(u) if leer else _beispieltag())


# ── Kästen ────────────────────────────────────────────────────────────
def _frage(u, schritt):
    _kal(u)
    _bed(u)._starte(kw.Dialog("frage", [schritt], lambda a: kw._plan()))
    _t(u)


def _formular(u, art=None):
    _bed(u)._quellen_holen = lambda: AUSWAHL
    _kal(u)
    _t(u, "a")
    for _ in range(12):
        if art is None or _bed(u).W["dialog"].feld.art == art:
            break
        _t(u, TAB)
    if art is None:
        _t(u, "x")                               # Titel: ⌫ hat etwas zu löschen


def _formular_eigene(u):
    """Gruppe auf „eigene" (← von „keine"), ein Zeichen Name getippt."""
    _formular(u)
    for _ in range(16):
        if _bed(u).W["dialog"].feld.name == "gruppe":
            break
        _t(u, TAB)
    _t(u, curses.KEY_LEFT, "x")


def _advanced(u, zeile=0):
    _formular(u, "advanced")
    _t(u, ENTER, *([curses.KEY_DOWN] * zeile))


def _advanced_liste(u):
    _advanced(u)
    _t(u, curses.KEY_RIGHT, curses.KEY_DOWN)     # Typ liste, Zeile „Liste"


def _advanced_vorwarnung(u):
    _advanced(u)
    _t(u, curses.KEY_LEFT, curses.KEY_DOWN)      # Typ deadline, Zeile „Vorwarnung"


def _advanced_stil(u):
    _advanced(u, 1)
    _bed(u).W["dialog"].box.stil = {"border-style": "solid"}     # ⌫ hat etwas zu nehmen


def _quellen(u, suche="t"):
    _advanced_liste(u)
    _t(u, ENTER, *suche)


def _stylebox(u, feld=0):
    _advanced(u, 1)
    _t(u, ENTER)
    sb = _bed(u).W["dialog"].box.unter
    sb.werte["border-color"] = "#aa7766"         # ⌫ und r haben etwas zu tun
    sb.feld = feld
    if feld == 0:
        _t(u, curses.KEY_RIGHT)                  # Rahmen gesetzt: r/⌫ wirken
    _t(u)


def _farbe(u, *tasten):
    _stylebox(u, 1)
    _t(u, curses.KEY_RIGHT, "+", *tasten)        # Wähler auf, einmal hineingezoomt


def _rhythmus(u, phasen):
    _kal(u)
    bed = _bed(u)
    bed._starte(kalender_phasen.PhasenListe(phasen, None, bed.tag(), date.today(),
                                            zurueck=bed._rhythmus_kasten))
    _t(u)


PHASEN = [{"kennung": "p1", "label": "Schlaf", "time": "23:00", "ende": "07:00",
           "motiv": "nacht", "rrule": "FREQ=DAILY", "seit": "2026-10-01"},
          {"kennung": "p2", "label": "Hunger", "time": "12:00", "ende": "13:00",
           "motiv": "nacht", "rrule": "FREQ=DAILY", "seit": "2026-10-01"}]

ZUSTAENDE = {
    "a:termine": _kal,
    "a:termine_leer": lambda u: (_kal(u), _tag(u, _leerer_tag(u))),
    "a:kalender": lambda u: (_kal(u), _t(u, TAB)),
    "a:todo": _todo,
    "a:todo_leer": lambda u: _todo(u, "leer"),
    "a:todo_ohne": lambda u: _todo(u, "ohne"),
    "a:termine_vom_monat": _vom_monat,
    "a:termine_leer_vom_monat": lambda u: _vom_monat(u, leer=True),
    "a:kalender_vom_monat": lambda u: _vom_monat(u, kasten=1),
    "a:todo_vom_monat": lambda u: _vom_monat(u, kasten=2),
    "a:todo_leer_vom_monat": lambda u: _vom_monat(u, kasten=2, weekplan="leer"),
    "a:todo_ohne_vom_monat": lambda u: _vom_monat(u, kasten=2, weekplan="ohne"),
    "b:monat": lambda u: (_kal(u), _t(u, "v")),
    "c:woche": _woche,
    "c:woche_leer": lambda u: _woche(u, leer=True),
    "ansehen": lambda u: (_kal(u), _t(u, ENTER)),
    "frage:text": lambda u: (_kal(u), _t(u, "g", "1")),
    "frage:ny": lambda u: _frage(u, kw.Schritt("ok", "löschen?", art="wahl",
                                               wahl={"y": True, "n": False})),
    "frage:at": lambda u: _frage(u, kw._wahl_umfang({"label": "Kurs"})),
    "frage:ant": lambda u: _frage(u, kw.Schritt("wie", "löschen?", art="wahl",
                                                wahl={"a": "alle", "t": "dieses", "n": None})),
    "frage:wahl": lambda u: _frage(u, kw.Schritt("ok", "nehmen?", art="wahl",
                                                 wahl={"x": True, "": False})),
    "formular:text": _formular,
    "formular:wahl": lambda u: _formular(u, "wahl"),
    "formular:advanced": lambda u: _formular(u, "advanced"),
    "formular:wahltext": _formular_eigene,
    "advanced:typ": _advanced,
    "advanced:liste": _advanced_liste,
    "advanced:vorwarnung": _advanced_vorwarnung,
    "advanced:stil": _advanced_stil,
    "advanced:status": lambda u: _advanced(u, 2),
    "quellen:liste": _quellen,
    "quellen:leer": lambda u: _quellen(u, "zzz"),
    "stylebox:wahl": _stylebox,
    "stylebox:farbe": lambda u: _stylebox(u, 1),
    "stylebox:gesperrt": lambda u: _stylebox(u, 5),
    "stylebox:leer": None,              # der Kalender gibt der Stylebox immer Felder
    "stylebox:farbe:kreis": _farbe,
    "stylebox:farbe:regler": lambda u: _farbe(u, TAB),
    "stylebox:farbe:hex": lambda u: _farbe(u, "#", "f"),
    "rhythmus:liste": lambda u: _rhythmus(u, PHASEN),
    "rhythmus:leer": lambda u: _rhythmus(u, []),
}
