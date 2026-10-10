"""
Neue Prüfungen des Prüfstands (2026-10-09): was die KI sagt (antwort),
wie oft sie fragt (fragen), Routinen mit Zeitraum (regeln.zeitraum), der
Seiten-Server für den Browser, und die Fälle f08–f11.
"""
import json
import os
import sys
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from pruefstand_teile import endzustand, faelle, umgebung  # noqa: E402

import kalender  # noqa: E402


def _erg(*antworten, werkzeuge=None, fragen=None):
    zuege = [{"sagt": "x", "antwort": a, "kontext": "", "werkzeuge": [], "fragen": []}
             for a in antworten]
    if werkzeuge:
        zuege[0]["werkzeuge"] = werkzeuge
    if fragen:
        zuege[0]["fragen"] = fragen
    return {"zuege": zuege}


def test_antwort_enthaelt_und_muster_vereinfacht():
    erg = _erg("Analysis I: Mo 10:00–12:00 und Do 8:30 – 10 Uhr, gelesen auf "
               "http://127.0.0.1:5/veranstaltung?id=4711")
    p = {"antwort": {"enthaelt": ["127.0.0.1:5/veranstaltung"],
                     "muster": [r"\bmo\b[^\n]{0,60}\b10(:00)?\s*(-|bis)\s*12",
                                r"\bdo\b[^\n]{0,60}\b0?8[:.]30\s*(-|bis)\s*10"]}}
    assert endzustand.eine(p, erg) is None
    p["antwort"]["enthaelt"] = ["lsf.uni-saarland.de"]
    assert "fehlt" in endzustand.eine(p, erg)


def test_antwort_nicht_muster_und_eins_von_muster():
    erg = _erg("Laut Suchtreffer bis 15.02.2027 — die Seite selbst konnte ich nicht öffnen.")
    assert endzustand.eine({"antwort": {"eins_von_muster": ["suchtreffer", "vorschau"]}}, erg) is None
    assert endzustand.eine({"antwort": {"eins_von_muster": ["vorschau"]}}, erg)
    g = endzustand.eine({"antwort": {"nicht_muster": [r"15\.02"]}}, erg)
    assert "15.02" in g


def test_antwort_zug_alle_und_einzeln():
    erg = _erg("Alles korrigiert.", "Gut.")
    p = {"antwort": {"zug": "alle", "nicht_muster": ["korrigiert"]}}
    assert "Zug 1" in endzustand.eine(p, erg)
    assert endzustand.eine({"antwort": {"nicht_muster": ["korrigiert"]}}, erg) is None   # letzter
    assert "gibt es nicht" in endzustand.eine({"antwort": {"zug": 5}}, erg)


def test_erfundene_kennung_faellt_auf_gesehene_nicht():
    w = [{"name": "read_calendar", "args": {}, "ergebnis": "#r89f8 Analysis I mo,mi"}]
    erg = _erg("#r89f8 steht, #rdabc auch.", werkzeuge=w)
    g = endzustand.eine({"antwort": {"kennungen_belegt": True}}, erg)
    assert g.startswith("Kennung(en) #rdabc nie")
    erg = _erg("#r89f8 steht.", werkzeuge=w)
    assert endzustand.eine({"antwort": {"kennungen_belegt": True}}, erg) is None


def test_quellen_zeile_statt_antworttext():
    """f08 seit 2026-10-10: die Adresse steht in der Quellen-Zeile, die
    Python schreibt — nicht mehr im Text der KI."""
    erg = _erg("Analysis I: Mo 10–12, Do 8:30–10.")
    erg["zuege"][0]["quellen"] = [{"titel": "Analysis I", "werkzeug": "browser_click",
                                   "url": "http://127.0.0.1:5/veranstaltung?id=4711"}]
    p = {"quellen": {"zug": 1, "enthaelt": ["127.0.0.1:5/veranstaltung?id=4711"],
                     "nicht_enthaelt": ["id=4712"]}}
    assert endzustand.eine(p, erg) is None
    assert endzustand.eine({"quellen": {"anzahl": 1}}, erg) is None
    g = endzustand.eine({"quellen": {"enthaelt": ["lsf.uni-saarland.de"]}}, erg)
    assert "fehlt in den Quellen" in g and "id=4711" in g
    assert "darf nicht" in endzustand.eine({"quellen": {"nicht_enthaelt": ["4711"]}}, erg)
    leer = _erg("weiß ich nicht")
    assert "keine" in endzustand.eine({"quellen": {"enthaelt": ["x"]}}, leer)
    assert endzustand.eine({"quellen": {"anzahl": 0}}, leer) is None
    assert endzustand.eine({"quellen": {}}, None) == "Quellen-Prüfung ohne Lauf"


def test_f08_prueft_die_quellen_zeile():
    f08 = next(f for f in faelle.alle() if f["id"] == "f08_lsf_browser")
    arten = [p for p in f08["endzustand"] if "quellen" in p]
    assert arten and "{server}/veranstaltung?id=4711" in arten[0]["quellen"]["enthaelt"]
    assert not any("enthaelt" in (p.get("antwort") or {}) for p in f08["endzustand"])


def test_fragen_zaehlen():
    erg = _erg("ok", fragen=[{"art": "erlaubnis", "frage": "Browser 127.0.0.1?"},
                             {"art": "knopf", "frage": "welche?"}])
    assert endzustand.eine({"fragen": {"art": "erlaubnis", "anzahl": 1}}, erg) is None
    assert "2 statt 1" in endzustand.eine({"fragen": {"anzahl": 1}}, erg)
    assert endzustand.eine({"fragen": {"art": "erlaubnis"}}, None) == "Fragen-Prüfung ohne Lauf"


ZEITRAUM = {"regeln": {"label": "analysis", "anzahl": 1,
                       "zeitraum": {"von": "2026-10-12", "bis": "2027-02-12"}}}


def test_zeitraum_mit_seit_und_until_besteht():
    kalender.add_routine("termine", "Analysis I", "FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20270212T235959",
                         time="10:00", ende="12:00", seit="2026-10-12")
    assert endzustand.eine(ZEITRAUM) is None


def test_zeitraum_ohne_anfang_und_ende_faellt_durch():
    kalender.add_routine("termine", "Analysis I", "FREQ=WEEKLY;BYDAY=MO,WE",
                         time="10:00", ende="12:00")
    g = endzustand.eine(ZEITRAUM)
    assert "vor Beginn" in g and "nach dem Ende" in g


def test_zeitraum_zu_frueh_zu_ende():
    kalender.add_routine("termine", "Analysis I", "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261218T235959",
                         time="10:00", seit="2026-10-12")
    assert "nur bis 14.12.2026" in endzustand.eine(ZEITRAUM)


# ── Fälle laden ────────────────────────────────────────────────────────

def test_neue_faelle_laden():
    ids = {f["id"] for f in faelle.alle()}
    assert {"f08_lsf_browser", "f09_suchtreffer_nicht_gelesen",
            "f10_semester_zeitraum_behauptet", "f11_routine_mit_zeitraum"} <= ids


@pytest.mark.parametrize("pruefung, meldung", [
    ({"was": "x", "label": "a"}, "braucht eins von"),
    ({"was": "x", "antwort": {"muster": ["(kaputt"]}}, "kein gültiges Muster"),
    ({"was": "x", "regeln": {"label": "a", "zeitraum": {"von": "2027-01-01", "bis": "2026-01-01"}}},
     "von liegt nach bis"),
    ({"was": "x", "eins_von": [[{"was": "y", "antwort": {"nicht_muster": ["["]}}]]},
     "kein gültiges Muster"),
])
def test_kaputte_pruefung_faellt_vor_dem_lauf_auf(tmp_path, pruefung, meldung):
    p = tmp_path / "f.yaml"
    p.write_text(json.dumps({"id": "x", "titel": "y", "zuege": [{"sagt": "z"}],
                             "endzustand": [pruefung]}), encoding="utf-8")
    with pytest.raises(faelle.FallFehler, match=meldung):
        faelle.laden(str(p))


# ── Seiten für den Browser ─────────────────────────────────────────────

def test_seiten_server_liefert_die_seiten_des_falls():
    s = umgebung.SeitenServer([
        {"pfad": "/", "html": "<a href='{server}/v?id=1'>A</a>"},
        {"pfad": "/v?id=1", "html": "<p>Mo 10–12</p>"},
        {"pfad": "/alt", "weiter": "/v?id=1"}])
    zurueck = s.starten()
    try:
        start = urllib.request.urlopen(s.adresse + "/").read().decode()
        assert s.adresse + "/v?id=1" in start
        assert "Mo 10–12" in urllib.request.urlopen(s.adresse + "/alt").read().decode()
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(s.adresse + "/gibtsnicht")
        assert s.protokoll[:2] == ["/", "/alt"]
    finally:
        zurueck()


def test_ohne_seiten_kein_server_und_platzhalter():
    s = umgebung.SeitenServer(None)
    s.starten()()
    assert s.adresse is None
    fall = {"zuege": [{"sagt": "schau {server}/"}], "n": 3}
    assert umgebung.platzhalter(fall, {"{server}": "http://h"}) == \
        {"zuege": [{"sagt": "schau http://h/"}], "n": 3}
