"""
Bewertungen der KI-Antworten (core/rueckmeldungen.py, Routen in
ui/routen/gespraeche.py, 2026-10-08): speichern, ändern (das letzte gilt),
eine Datei pro Rechner, was die Antwort benutzt hat, Fehlerfälle.
"""
import json
import os

import pytest

import gespraeche
import rueckmeldungen


def _gespraech(werkzeuge=None):
    gid = gespraeche.neu("Fahrrad")
    gespraeche.anhaengen(gid, "user", "wie flicke ich?")
    a = gespraeche.anhaengen(gid, "assistant", "Mit Flickzeug. " * 30,
                             anbieter="anthropic", modell="claude-x",
                             werkzeuge=werkzeuge or [])
    return gid, a["id"]


def test_bewerten_speichert_mit_kontext_der_antwort():
    gid, nid = _gespraech([
        {"name": "load_skill", "args": "name=wochenplan"},
        {"name": "web_search", "args": "query=flicken"},
        {"name": "run_code", "args": "code=print(1), skill=pdf"},
        {"name": "load_skill", "args": "name=wochenplan, datei=x.md"}])
    e = rueckmeldungen.bewerten(gid, nid, -1, "  zu lang  ")
    assert e["wert"] == -1 and e["kommentar"] == "zu lang"
    assert e["anbieter"] == "anthropic" and e["modell"] == "claude-x"
    assert e["werkzeuge"] == ["load_skill", "web_search", "run_code"]
    assert e["skills"] == ["wochenplan", "pdf"]
    assert e["gespraech"] == gid and e["nachricht"] == nid and e["id"] and e["ts"]


def test_aendern_ist_ein_neues_ereignis_das_letzte_gilt():
    gid, nid = _gespraech()
    rueckmeldungen.bewerten(gid, nid, 1)
    rueckmeldungen.bewerten(gid, nid, -1, "doch nicht")
    assert len(rueckmeldungen.ereignisse()) == 2          # nichts überschrieben
    akt = rueckmeldungen.aktuelle()
    assert len(akt) == 1 and akt[0]["wert"] == -1 and akt[0]["kommentar"] == "doch nicht"


def test_eine_datei_pro_rechner_nur_angehaengt():
    gid, nid = _gespraech()
    rueckmeldungen.bewerten(gid, nid, 1, knoten="pc")
    rueckmeldungen.bewerten(gid, nid, -1, knoten="laptop")
    namen = sorted(os.listdir(rueckmeldungen.ordner()))
    assert namen == ["laptop.jsonl", "pc.jsonl"]
    # Zusammengelegt nach Zeit: das spätere (laptop) gilt.
    assert rueckmeldungen.aktuelle()[0]["wert"] == -1
    with open(os.path.join(rueckmeldungen.ordner(), "pc.jsonl"), encoding="utf-8") as f:
        assert json.loads(f.readline())["wert"] == 1


def test_halbe_zeile_wird_uebersprungen():
    gid, nid = _gespraech()
    rueckmeldungen.bewerten(gid, nid, 1, knoten="pc")
    with open(os.path.join(rueckmeldungen.ordner(), "pc.jsonl"), "a", encoding="utf-8") as f:
        f.write('{"ts": "2099", "nachr')
    assert [e["wert"] for e in rueckmeldungen.aktuelle()] == [1]


def test_neueste_zuerst_und_nach_gespraech_filtern():
    g1, n1 = _gespraech()
    g2, n2 = _gespraech()
    rueckmeldungen.bewerten(g1, n1, 1)
    rueckmeldungen.bewerten(g2, n2, -1)
    assert [e["nachricht"] for e in rueckmeldungen.aktuelle()] == [n2, n1]
    assert [e["nachricht"] for e in rueckmeldungen.aktuelle(g1)] == [n1]


@pytest.mark.parametrize("wert", [0, 2, "gut", None, "1.5"])
def test_falscher_wert(wert):
    gid, nid = _gespraech()
    with pytest.raises(rueckmeldungen.Ungueltig):
        rueckmeldungen.bewerten(gid, nid, wert)
    assert rueckmeldungen.ereignisse() == []


def test_zu_langer_kommentar():
    gid, nid = _gespraech()
    with pytest.raises(rueckmeldungen.Ungueltig):
        rueckmeldungen.bewerten(gid, nid, 1, "x" * (rueckmeldungen.KOMMENTAR_MAX + 1))


def test_nur_antworten_der_ki_lassen_sich_bewerten():
    gid, nid = _gespraech()
    frage = gespraeche.nachrichten(gid)[0]["id"]
    for g, n in ((gid, frage), (gid, "gibt-es-nicht"), ("gibt-es-nicht", nid)):
        with pytest.raises(rueckmeldungen.Unbekannt):
            rueckmeldungen.bewerten(g, n, 1)


def test_ausschnitt_titel_und_verworfene_antwort():
    gid, nid = _gespraech()
    rueckmeldungen.bewerten(gid, nid, -1)
    e = rueckmeldungen.mit_kontext(rueckmeldungen.aktuelle())[0]
    assert e["gespraech_titel"] == "Fahrrad"
    assert e["ausschnitt"].startswith("Mit Flickzeug.") and e["ausschnitt"].endswith("…")
    assert len(e["ausschnitt"]) == rueckmeldungen.AUSSCHNITT
    gespraeche.verwerfen_ab(gid, nid)                       # wiederholt
    e = rueckmeldungen.mit_kontext(rueckmeldungen.aktuelle())[0]
    assert e["verworfen"] is True and e["ausschnitt"] == ""


# ── Routen ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def test_route_bewerten_und_liste(client):
    gid, nid = _gespraech()
    r = client.post("/api/rueckmeldung", json={"gespraech": gid, "nachricht": nid,
                                               "wert": 1, "kommentar": "genau richtig"})
    assert r.status_code == 200 and r.get_json()["rueckmeldung"]["wert"] == 1
    client.post("/api/rueckmeldung", json={"gespraech": gid, "nachricht": nid, "wert": -1})
    liste = client.get("/api/rueckmeldungen").get_json()["rueckmeldungen"]
    assert len(liste) == 1 and liste[0]["wert"] == -1 and "kommentar" not in liste[0]
    assert liste[0]["gespraech_titel"] == "Fahrrad" and liste[0]["ausschnitt"]
    assert client.get("/api/rueckmeldungen?gespraech=" + gid).get_json()["rueckmeldungen"]
    assert client.get("/api/rueckmeldungen?gespraech=anderes").get_json() == {"rueckmeldungen": []}


def test_route_fehler(client):
    gid, nid = _gespraech()
    r = client.post("/api/rueckmeldung", json={"gespraech": gid, "nachricht": nid, "wert": 5})
    assert r.status_code == 400 and "gut" in r.get_json()["error"]
    r = client.post("/api/rueckmeldung", json={"gespraech": gid, "nachricht": "x", "wert": 1})
    assert r.status_code == 404
    r = client.post("/api/rueckmeldung", json={})
    assert r.status_code in (400, 404)
    assert rueckmeldungen.ereignisse() == []
