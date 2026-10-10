"""
Der Dialog aus den Feldern des Katalogs (tui/bausteine/feld_dialog.py,
2026-10-10): jeder Feld-Typ, wenn-Bedingungen, Grenzen — die 31-Tage-Regel
kommt aus dem Katalog-Eintrag des Kalenders, nicht aus der TUI. Und: Dialog
und Hub (core/kachel_felder.py) sagen zu denselben Eingaben dasselbe.
"""
import curses
from datetime import date

import pytest

import kachel_felder
import kacheln
from kachel_form import KachelFehler
from tui.bausteine.feld_dialog import FeldDialog

HEUTE = date(2026, 10, 14)


def kalender_felder():
    (e,) = [x for x in kacheln.katalog() if x["app"] == "kalender"]
    return e["felder"]


def tippe(m, text, loeschen=12):
    for _ in range(loeschen):
        m.taste(127)
    for c in text:
        m.taste(ord(c))


def test_kalender_aus_dem_katalog_vorgaben_und_mitlaufend():
    m = FeldDialog(kalender_felder(), "kalender", heute=HEUTE)
    zeilen, cursor = m.anzeige(44, 10)
    assert zeilen[:3] == ["art   ‹ mitlaufend ›", "tage  7", "      ab heute, jeden tag neu"]
    assert cursor == (0, 6)
    assert m.taste(10) == "speichern"
    assert m.aenderungen() == {"werte": {"modus": "mitlaufend", "tage": 7}}


def test_31_tage_regel_kommt_aus_dem_katalog():
    m = FeldDialog(kalender_felder(), "kalender", heute=HEUTE)
    m.taste(curses.KEY_DOWN)
    tippe(m, "40")
    assert m.taste(10) is None and "höchstens 31 tage" in m.anzeige(44, 10)[0][-1]
    tippe(m, "31")
    assert m.taste(10) == "speichern" and m.aenderungen()["werte"]["tage"] == 31
    tippe(m, "")
    assert m.taste(10) is None and "tage fehlt" in m.fehler


def test_fest_von_bis_mit_vorgaben_heute_und_spanne():
    m = FeldDialog(kalender_felder(), "kalender", heute=HEUTE)
    m.taste(curses.KEY_RIGHT)                                 # wahl: → fest
    assert [f["name"] for f in m.sichtbar()] == ["modus", "von", "bis"]
    assert m.anzeige(44, 10)[0][1:3] == ["von   2026-10-14", "bis   2026-10-20"]
    m.taste(curses.KEY_DOWN); m.taste(curses.KEY_DOWN)       # bis
    tippe(m, "2026-11-30")
    assert m.taste(10) is None and "höchstens 31 tage" in m.fehler
    tippe(m, "2026-10-01")
    assert m.taste(10) is None and "liegt vor" in m.fehler
    tippe(m, "2026-11-13")
    assert m.taste(10) == "speichern"
    assert m.aenderungen()["werte"] == {"modus": "fest", "von": "2026-10-14", "bis": "2026-11-13"}
    tippe(m, "2026-1x-13")                                    # x kommt nicht hinein
    assert m.eingabe["bis"] == "2026-1-13" and m.taste(10) is None and "JJJJ-MM-TT" in m.fehler
    assert m.taste(27) == "abbrechen"


def test_jeder_typ_text_bool_zahl_wahl_datum():
    felder = [{"name": "titel", "typ": "text", "titel": "titel", "vorgabe": "",
               "grenzen": {"max_laenge": 5}},
              {"name": "fertig", "typ": "bool", "titel": "fertig", "vorgabe": False},
              {"name": "anzahl", "typ": "zahl", "titel": "anzahl", "vorgabe": 3,
               "grenzen": {"min": 2}},
              {"name": "ort", "typ": "wahl", "titel": "ort", "vorgabe": "b",
               "werte": [{"wert": "a", "titel": "A"}, {"wert": "b", "titel": "B"},
                         {"wert": "c", "titel": "C"}]},
              {"name": "tag", "typ": "datum", "titel": "tag", "vorgabe": "heute+1"}]
    m = FeldDialog(felder, "probe", heute=HEUTE)
    assert m.hoehe >= len(felder) + 4
    tippe(m, "abcdefg", 0)                                    # text: höchstens 5
    assert m.eingabe["titel"] == "abcde"
    m.taste(9)                                                # tab → bool
    m.taste(ord(" "))
    assert m.anzeige(40, 12)[0][1].endswith("‹ ja ›")
    m.taste(9)
    tippe(m, "1")
    assert m.taste(10) is None and "anzahl: mindestens 2" in m.fehler
    tippe(m, "-")                                             # Minus nur vorne
    m.taste(ord("4"))
    assert m.eingabe["anzahl"] == "-4"
    tippe(m, "4")
    m.taste(curses.KEY_DOWN)
    m.taste(curses.KEY_LEFT)                                  # wahl rückwärts
    assert m.eingabe["ort"] == "a"
    m.taste(curses.KEY_LEFT)                                  # und rundherum
    assert m.eingabe["ort"] == "c" and "‹ C ›" in m.anzeige(40, 12)[0][3]
    m.taste(curses.KEY_UP); m.taste(curses.KEY_UP); m.taste(curses.KEY_UP)
    assert m.anzeige(40, 12)[1] == (0, len("anzahl  ") + 5)    # zurück im text-feld, cursor am ende
    assert m.taste(19) == "speichern"                         # ctrl+s wie enter
    assert m.aenderungen()["werte"] == {"titel": "abcde", "fertig": True, "anzahl": 4,
                                        "ort": "c", "tag": "2026-10-15"}


def test_ohne_felder_geht_enter_gleich():
    m = FeldDialog([], "leer")
    assert m.anzeige(30, 5)[0] == ["", ""] and m.taste(10) == "speichern"
    assert m.aenderungen() == {"werte": {}}


@pytest.mark.parametrize("eingabe", [
    {"modus": "mitlaufend", "tage": "7"}, {"modus": "mitlaufend", "tage": "0"},
    {"modus": "mitlaufend", "tage": "32"}, {"modus": "mitlaufend", "tage": ""},
    {"modus": "fest", "von": "2026-10-14", "bis": "2026-11-13"},
    {"modus": "fest", "von": "2026-10-14", "bis": "2026-11-14"},
    {"modus": "fest", "von": "2026-10-14", "bis": "2026-10-13"},
    {"modus": "fest", "von": "2026-10-14", "bis": "nie"},
])
def test_dialog_und_hub_sagen_dasselbe(eingabe):
    felder = kalender_felder()
    m = FeldDialog(felder, "kalender", heute=HEUTE)
    m.eingabe.update(eingabe)
    werte, grund = m.pruefen()
    try:
        hub = kachel_felder.pruefen(felder, {k: v for k, v in eingabe.items()
                                             if k in {f["name"] for f in m.sichtbar()}})
    except KachelFehler:
        hub = None
    assert (werte is None) == (hub is None), (grund, hub)
    if werte is not None:
        assert werte == hub
