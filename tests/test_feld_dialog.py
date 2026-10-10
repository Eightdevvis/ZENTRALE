"""
Der Dialog aus dem JSON Schema des Katalogs (tui/bausteine/feld_dialog.py,
2026-10-10, vorher eine eigene `felder`-Liste): jede Art Eigenschaft
(Auswahl mit Titeln, enum, ja/nein, ganze Zahl, Zahl, Datum, Text),
if/then-Regeln, Grenzen — die Regeln kommen aus dem Katalog-Eintrag des
Kalenders, nicht aus der TUI. Und: was der Dialog durchlässt, prüft der Hub
(core/kachel_parameter.py) mit demselben Schema — wo JSON Schema nichts
sagen kann (höchstens 31 Tage zwischen zwei Daten), sagt nur der Hub nein.
"""
import curses
from datetime import date, timedelta

import pytest

import kachel_parameter
import kacheln
from kachel_form import KachelFehler
from tui.bausteine.feld_dialog import FeldDialog

HEUTE = date.today()


def kalender_schema():
    (e,) = [x for x in kacheln.katalog() if x["app"] == "kalender"]
    return e["parameter"]


def tippe(m, text, loeschen=12):
    for _ in range(loeschen):
        m.taste(127)
    for c in text:
        m.taste(ord(c))


def test_kalender_aus_dem_katalog_vorgaben_und_mitlaufend():
    m = FeldDialog(kalender_schema(), "kalender")
    zeilen, cursor = m.anzeige(44, 10)
    assert zeilen[:3] == ["art   ‹ mitlaufend ›", "tage  7", "      ab heute, jeden tag neu"]
    assert cursor == (0, 6)
    assert m.taste(10) == "speichern"
    assert m.aenderungen() == {"werte": {"modus": "mitlaufend", "tage": 7}}


def test_31_tage_regel_kommt_aus_dem_schema():
    m = FeldDialog(kalender_schema(), "kalender")
    m.taste(curses.KEY_DOWN)
    tippe(m, "40")
    assert m.taste(10) is None and "höchstens 31 tage" in m.anzeige(44, 10)[0][-1]
    tippe(m, "31")
    assert m.taste(10) == "speichern" and m.aenderungen()["werte"]["tage"] == 31
    tippe(m, "")
    assert m.taste(10) is None and "tage fehlt" in m.fehler


def test_fest_zeigt_von_bis_mit_vorgaben_von_heute():
    m = FeldDialog(kalender_schema(), "kalender")
    m.taste(curses.KEY_RIGHT)                                 # Auswahl: → fest
    assert [f["name"] for f in m.sichtbar()] == ["modus", "von", "bis"]
    von, bis = HEUTE.isoformat(), (HEUTE + timedelta(days=6)).isoformat()
    zeilen = m.anzeige(44, 10)[0]
    assert zeilen[1:4] == ["von   " + von, "bis   " + bis, "      höchstens 31 tage ab „von“"]
    m.taste(curses.KEY_DOWN); m.taste(curses.KEY_DOWN)       # bis
    tippe(m, "2026-1x-13")                                    # x kommt nicht hinein
    assert m.eingabe["bis"] == "2026-1-13" and m.taste(10) is None and "JJJJ-MM-TT" in m.fehler
    tippe(m, "2026-11-13")
    assert m.taste(10) == "speichern"
    assert m.aenderungen()["werte"] == {"modus": "fest", "von": von, "bis": "2026-11-13"}
    assert m.taste(27) == "abbrechen"


def test_spanne_prueft_nur_der_hub():
    """Abstand zweier Daten kann JSON Schema nicht sagen: der Dialog lässt
    durch, der Hub sagt nein — mit einem Satz, den der Dialog zeigt."""
    m = FeldDialog(kalender_schema(), "kalender")
    m.eingabe.update(modus="fest", von="2026-10-14", bis="2026-11-30")
    werte, grund = m.pruefen()
    assert grund is None
    adresse = "zentrale://kalender/ausschnitt?bis=2026-11-30&modus=fest&von=2026-10-14"
    status, a = kacheln.holen({"adresse": adresse, "w": 0, "h": 0})
    assert status == 400 and a["text"] == "höchstens 31 tage"
    m.eingabe["bis"] = "2026-10-01"
    assert kacheln.holen({"adresse": adresse.replace("11-30", "10-01"), "w": 0, "h": 0})[1]["text"] \
        == "„bis\" liegt vor „von\""


SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {"title": "titel", "type": "string", "maxLength": 5, "default": ""},
        "fertig": {"title": "fertig", "type": "boolean", "default": False},
        "anzahl": {"title": "anzahl", "type": "integer", "minimum": 2, "default": 3},
        "ort": {"title": "ort", "type": "string", "default": "b",
                "oneOf": [{"const": "a", "title": "A"}, {"const": "b", "title": "B"},
                          {"const": "c", "title": "C"}]},
        "tag": {"title": "tag", "type": "string", "format": "date", "default": "2026-10-15"},
        "farbe": {"title": "farbe", "type": "string", "enum": ["rot", "blau"]},
        "faktor": {"title": "faktor", "type": "number"},
    },
    "required": ["anzahl", "tag"],
    "additionalProperties": False,
}


def test_jede_art_eigenschaft():
    kachel_parameter.schema_pruefen(SCHEMA)                   # ein gültiges Schema
    m = FeldDialog(SCHEMA, "probe")
    arten = {f["name"]: f["art"] for f in m.felder}
    assert arten == {"titel": "text", "fertig": "bool", "anzahl": "zahl", "ort": "wahl",
                     "tag": "datum", "farbe": "wahl", "faktor": "zahl"}
    assert m.hoehe >= len(m.felder) + 4
    tippe(m, "abcdefg", 0)                                    # text: höchstens 5
    assert m.eingabe["titel"] == "abcde"
    m.taste(9)                                                # tab → ja/nein
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
    m.taste(curses.KEY_LEFT)                                  # Auswahl rückwärts
    assert m.eingabe["ort"] == "a"
    m.taste(curses.KEY_LEFT)                                  # und rundherum, mit Titel
    assert m.eingabe["ort"] == "c" and "‹ C ›" in m.anzeige(40, 12)[0][3]
    m.taste(curses.KEY_DOWN); m.taste(curses.KEY_DOWN)       # farbe: enum ohne Titel
    assert m.anzeige(40, 12)[0][5].endswith("‹ rot ›")
    m.taste(curses.KEY_DOWN)
    tippe(m, "1.5")                                           # number nimmt einen Punkt
    m.taste(curses.KEY_UP); m.taste(curses.KEY_UP); m.taste(curses.KEY_UP)
    m.taste(curses.KEY_UP); m.taste(curses.KEY_UP); m.taste(curses.KEY_UP)
    assert m.anzeige(40, 12)[1] == (0, len("anzahl  ") + 5)    # zurück im text-feld
    assert m.taste(19) == "speichern"                         # ctrl+s wie enter
    werte = m.aenderungen()["werte"]
    assert werte == {"titel": "abcde", "fertig": True, "anzahl": 4, "ort": "c",
                     "tag": "2026-10-15", "farbe": "rot", "faktor": 1.5}
    assert kachel_parameter.pruefen(SCHEMA, werte) == werte    # der Hub sieht es genauso


def test_freiwillige_leere_felder_fehlen_im_ergebnis():
    m = FeldDialog(SCHEMA, "probe")
    m.eingabe.update(faktor="")
    assert "faktor" not in m.pruefen()[0]
    m.eingabe.update(tag="")
    assert m.pruefen() == (None, "tag fehlt")                 # required


def test_ohne_felder_geht_enter_gleich():
    m = FeldDialog({}, "leer")
    assert m.anzeige(30, 5)[0] == ["", ""] and m.taste(10) == "speichern"
    assert m.aenderungen() == {"werte": {}}


@pytest.mark.parametrize("eingabe", [
    {"modus": "mitlaufend", "tage": "7"}, {"modus": "mitlaufend", "tage": "0"},
    {"modus": "mitlaufend", "tage": "32"}, {"modus": "mitlaufend", "tage": ""},
    {"modus": "fest", "von": "2026-10-14", "bis": "2026-11-13"},
    {"modus": "fest", "von": "2026-10-14", "bis": "nie"},
    {"modus": "fest", "von": "", "bis": "2026-10-14"},
])
def test_dialog_und_schema_sagen_dasselbe(eingabe):
    """Was das Schema ausdrücken kann, sehen Dialog und Hub gleich."""
    schema = kalender_schema()
    m = FeldDialog(schema, "kalender")
    m.eingabe.update(eingabe)
    werte, grund = m.pruefen()
    sichtbar = {f["name"] for f in m.sichtbar()}
    try:
        hub = kachel_parameter.pruefen(schema, {k: v for k, v in eingabe.items() if k in sichtbar})
    except KachelFehler as e:
        hub, hub_grund = None, str(e)
    assert (werte is None) == (hub is None), (grund, hub)
    if werte is not None:
        assert werte == hub
    else:
        assert grund == hub_grund


def test_die_tui_braucht_kein_paket_fuer_schemas():
    """Die TUI bleibt bei der Standardbibliothek: kein jsonschema, kein yaml
    (2026-10-10). Die Schemas liest feld_dialog.py selbst."""
    import os
    wurzel = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tui")
    for ort, _o, namen in os.walk(wurzel):
        for n in namen:
            if n.endswith(".py"):
                with open(os.path.join(ort, n), encoding="utf-8") as f:
                    text = f.read()
                assert "import jsonschema" not in text and "from jsonschema" not in text, n
                assert "import yaml" not in text, n
