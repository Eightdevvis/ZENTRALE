"""
Desk View: die Datei (core/desk.py, JSON Canvas 1.0), die Routen
(/api/desk), der Abgleich (data/desk/** auf der Positivliste, .canvas als
JSON zusammengeführt) und die Ansicht tui/ansichten/desk.py gegen ein
gefälschtes Backend. 2026-10-09, memory/system/desk_view.md.
"""
import copy
import io
import json
import os
import types
import urllib.error

import pytest

import abgleich_auswahl
import abgleich_zusammenfuehren as zf
import desk


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def datei(name):
    return os.path.join(desk.ordner(), name + ".canvas")


def schreibe(name, daten):
    os.makedirs(desk.ordner(), exist_ok=True)
    with open(datei(name), "w", encoding="utf-8") as f:
        json.dump(daten, f)


def lies(name):
    with open(datei(name), encoding="utf-8") as f:
        return json.load(f)


# ── Datei ─────────────────────────────────────────────────────────────

def test_anlegen_laden_leer():
    d = desk.anlegen("Elektronik")
    assert d["name"] == "Elektronik" and d["elemente"] == [] and d["verbindungen"] == []
    assert lies("Elektronik") == {"nodes": [], "edges": []}
    assert [x["name"] for x in desk.liste()] == ["Elektronik"]
    with pytest.raises(desk.DeskFehler) as e:
        desk.anlegen("Elektronik")
    assert e.value.code == 409


@pytest.mark.parametrize("name", ["", "../x", "a/b", ".versteckt", "x" * 61])
def test_name_ungueltig(name):
    with pytest.raises(desk.DeskFehler):
        desk.anlegen(name)


def test_umlaute_und_leerzeichen_im_namen():
    assert desk.anlegen("Geige Übung")["name"] == "Geige Übung"


def test_rundreise_zellen_pixel_und_schnuere():
    desk.anlegen("d")
    st = desk.laden("d")["stand"]
    el = [{"id": "a1", "art": "notiz", "x": 2, "y": -3, "w": 24, "h": 6, "text": "# Titel\nhallo"},
          {"id": "b2", "art": "notiz", "x": 40, "y": 1, "w": 20, "h": 5, "text": ""}]
    vb = [{"id": "e1", "von": "a1", "nach": "b2", "von_seite": "right", "nach_seite": "left"}]
    d = desk.speichern("d", el, vb, st)
    roh = lies("d")
    assert roh["nodes"][0] == {"id": "a1", "type": "text", "text": "# Titel\nhallo",
                               "x": 20, "y": -60, "width": 240, "height": 120}
    assert roh["edges"] == [{"id": "e1", "fromNode": "a1", "toNode": "b2",
                             "fromSide": "right", "toSide": "left"}]
    assert d["elemente"][0] == {"id": "a1", "x": 2, "y": -3, "w": 24, "h": 6,
                                "art": "notiz", "text": "# Titel\nhallo"}
    assert d["verbindungen"] == [{"id": "e1", "von": "a1", "nach": "b2"}]
    assert d["stand"] != st


def test_obsidian_lagen_bleiben_wenn_nicht_bewegt():
    """Eine Lage aus Obsidian (x=13) wird nicht aufs 10er-Raster gezogen,
    solange der Kasten in Zellen nicht bewegt wurde."""
    schreibe("o", {"nodes": [{"id": "n", "type": "text", "text": "x", "x": 13, "y": 7,
                              "width": 251, "height": 63, "color": "4"}], "edges": []})
    d = desk.laden("o")
    desk.speichern("o", d["elemente"], d["verbindungen"], d["stand"])
    assert lies("o")["nodes"][0] == {"id": "n", "type": "text", "text": "x", "x": 13, "y": 7,
                                     "width": 251, "height": 63, "color": "4"}
    d = desk.laden("o")
    d["elemente"][0]["x"] += 1
    desk.speichern("o", d["elemente"], d["verbindungen"], d["stand"])
    k = lies("o")["nodes"][0]
    assert k["x"] == 20 and k["color"] == "4"


def test_fremde_knoten_bleiben_und_sind_nicht_bearbeitbar():
    schreibe("f", {"nodes": [{"id": "g", "type": "file", "file": "bild.png", "x": 0, "y": 0,
                              "width": 100, "height": 100}],
                   "edges": [], "zusatz": {"bleibt": True}})
    d = desk.laden("f")
    assert d["elemente"][0]["art"] == "fremd" and d["elemente"][0]["titel"] == "bild.png"
    d["elemente"][0]["text"] = "versuch"
    desk.speichern("f", d["elemente"], [], d["stand"])
    roh = lies("f")
    assert roh["nodes"][0]["type"] == "file" and "text" not in roh["nodes"][0]
    assert roh["zusatz"] == {"bleibt": True}


def test_loeschen_eines_elements_nimmt_seine_schnuere_mit():
    desk.anlegen("k")
    st = desk.laden("k")["stand"]
    el = [{"id": i, "art": "notiz", "x": 0, "y": 0, "w": 5, "h": 3} for i in ("a", "b", "c")]
    vb = [{"id": "ab", "von": "a", "nach": "b"}, {"id": "bc", "von": "b", "nach": "c"}]
    st = desk.speichern("k", el, vb, st)["stand"]
    d = desk.speichern("k", el[:1] + el[2:], vb, st)      # b weg, Schnüre noch mitgeschickt
    assert d["verbindungen"] == [] and lies("k")["edges"] == []


def test_schnuere_ohne_angabe_bleiben_wie_sie_sind():
    schreibe("s", {"nodes": [{"id": "a", "type": "text", "text": "", "x": 0, "y": 0, "width": 50, "height": 60},
                             {"id": "b", "type": "text", "text": "", "x": 100, "y": 0, "width": 50, "height": 60}],
                   "edges": [{"id": "e", "fromNode": "a", "toNode": "b", "label": "weil", "color": "1"}]})
    d = desk.laden("s")
    assert d["verbindungen"] == [{"id": "e", "von": "a", "nach": "b", "label": "weil"}]
    desk.speichern("s", d["elemente"], None, d["stand"])
    assert lies("s")["edges"][0]["color"] == "1"
    d = desk.laden("s")
    desk.speichern("s", d["elemente"], d["verbindungen"], d["stand"])
    assert lies("s")["edges"][0] == {"id": "e", "fromNode": "a", "toNode": "b",
                                     "label": "weil", "color": "1"}


def test_stand_schuetzt_vor_ueberschreiben():
    desk.anlegen("w")
    alt = desk.laden("w")["stand"]
    schreibe("w", {"nodes": [{"id": "x", "type": "text", "text": "von woanders", "x": 0, "y": 0,
                              "width": 50, "height": 60}], "edges": []})
    with pytest.raises(desk.DeskKonflikt) as e:
        desk.speichern("w", [], [], alt)
    assert e.value.code == 409 and e.value.stand == desk.laden("w")["stand"]
    assert lies("w")["nodes"][0]["text"] == "von woanders"


def test_kaputte_datei_wird_nie_ueberschrieben():
    os.makedirs(desk.ordner(), exist_ok=True)
    with open(datei("kaputt"), "w") as f:
        f.write("{nicht json")
    with pytest.raises(desk.DeskFehler) as e:
        desk.laden("kaputt")
    assert e.value.code == 422
    with pytest.raises(desk.DeskFehler):
        desk.speichern("kaputt", [], [])
    assert open(datei("kaputt")).read() == "{nicht json"
    assert desk.liste()[0]["elemente"] is None


@pytest.mark.parametrize("el", [
    {"id": "a b", "art": "notiz", "x": 0, "y": 0, "w": 5, "h": 3},
    {"id": "a", "art": "notiz", "x": "1", "y": 0, "w": 5, "h": 3},
    {"id": "a", "art": "notiz", "x": 0, "y": 0, "w": 1, "h": 3},
    {"id": "a", "art": "fremd", "x": 0, "y": 0, "w": 5, "h": 3},
    {"id": "a", "art": "notiz", "x": 0, "y": 0, "w": 5, "h": 3, "text": "x" * 20001},
])
def test_unsinn_wird_abgelehnt(el):
    desk.anlegen("u")
    with pytest.raises(desk.DeskFehler):
        desk.speichern("u", [el], [])
    assert lies("u") == {"nodes": [], "edges": []}


def test_ordner_per_einstellung_und_standard(monkeypatch, tmp_path):
    monkeypatch.setenv("ZENTRALE_DESK_ORDNER", str(tmp_path / "x"))
    assert desk.ordner() == str(tmp_path / "x")
    monkeypatch.delenv("ZENTRALE_DESK_ORDNER")
    assert desk.ordner().endswith(os.path.join("data", "desk"))


# ── Routen ────────────────────────────────────────────────────────────

def test_routen_ganzer_weg(client):
    r = client.post("/api/desk", json={"name": "Elektronik"})
    assert r.status_code == 201
    st = r.get_json()["stand"]
    assert client.post("/api/desk", json={"name": "Elektronik"}).status_code == 409
    assert client.post("/api/desk", json={"name": "../x"}).status_code == 400
    assert client.get("/api/desk").get_json()["desks"][0]["name"] == "Elektronik"
    el = [{"id": "a", "art": "notiz", "x": 1, "y": 1, "w": 10, "h": 4, "text": "hi"}]
    r = client.put("/api/desk/Elektronik", json={"elemente": el, "verbindungen": [], "stand": st})
    assert r.status_code == 200 and r.get_json()["elemente"][0]["text"] == "hi"
    r = client.put("/api/desk/Elektronik", json={"elemente": [], "stand": st})
    assert r.status_code == 409 and r.get_json()["stand"]
    assert client.get("/api/desk/Elektronik").get_json()["elemente"][0]["id"] == "a"
    assert client.get("/api/desk/Fehlt").status_code == 404
    assert client.get("/api/desk/Geige%20%C3%9Cbung").status_code == 404


# ── Abgleich ──────────────────────────────────────────────────────────

def test_desk_ordner_steht_auf_der_positivliste():
    assert abgleich_auswahl.passt("data/desk/Elektronik.canvas", abgleich_auswahl.ABGLEICH)
    assert abgleich_auswahl.passt("data/desk/Elektronik.canvas", abgleich_auswahl.SICHERN)
    assert not abgleich_auswahl.passt("data/desk/.Elektronik.canvas.1.2.tmp",
                                      abgleich_auswahl.ABGLEICH)


def test_canvas_wird_als_json_nach_id_zusammengefuehrt():
    """Zwei Rechner schieben verschiedene Zettel — beide Änderungen bleiben,
    und heraus kommt wieder gültiges JSON (als Text zusammengeführt stünden
    zwei Fassungen in der Datei)."""
    def k(i, x):
        return {"id": i, "type": "text", "text": i, "x": x, "y": 0, "width": 50, "height": 60}
    basis = {"nodes": [k("a", 0), k("b", 100)], "edges": []}
    hier = copy.deepcopy(basis); hier["nodes"][0]["x"] = 10
    dort = copy.deepcopy(basis); dort["nodes"][1]["x"] = 200
    dort["edges"].append({"id": "e", "fromNode": "a", "toNode": "b"})
    b = lambda d: json.dumps(d).encode()
    erg = zf.zusammenfuehren("data/desk/x.canvas", b(basis), b(hier), b(dort))
    assert zf.art("data/desk/x.canvas") == "json"
    neu = json.loads(erg.inhalt)
    assert [n["x"] for n in neu["nodes"]] == [10, 200] and neu["edges"][0]["id"] == "e"
    assert not erg.konflikte


# ── Die Ansicht gegen ein gefälschtes Backend ─────────────────────────

class Schirm:
    def __init__(self):
        self.folge = []

    def getch(self):
        return self.folge.pop(0) if self.folge else -1

    def getmaxyx(self):
        return (30, 100)

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def ansicht(monkeypatch, client):
    """Desk-Ansicht, deren api_call direkt an den Flask-Test-Client geht —
    also gegen den echten core/desk.py im Wegwerf-Ordner."""
    import curses
    from tui.ansichten import desk as desk_ansicht
    from tui.ansichten import kontext
    monkeypatch.setattr(curses, "keyname", lambda c: b"")
    aufrufe = []

    def api(pfad, method="GET", body=None, timeout=3.0):
        aufrufe.append((method, pfad))
        r = client.open(pfad, method=method, json=body)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(pfad, r.status_code, "x", {}, io.BytesIO(r.data))
        return r.get_json()
    monkeypatch.setattr(desk_ansicht, "api_call", api)
    z = kontext.Kontext(Schirm(), None, False, None)
    z.apply_theme("night")
    d = desk_ansicht.Desk(z)
    d.aufrufe = aufrufe
    return d


def tippe(d, text):
    for b in text.encode("utf-8"):
        d.taste(b)


def test_ansicht_neuer_desk_zettel_anlegen_ablegen_bearbeiten(ansicht):
    import curses
    d, D = ansicht, ansicht.DESK
    d.oeffnen()
    assert D["active"] and D["ebene"] == "wahl" and D["desks"] == []
    d.taste(10)                                   # „+ neuer desk"
    tippe(d, "Elektronik")
    d.taste(10)
    assert D["ebene"] == "canvas" and D["desk"] == "Elektronik"
    d.draw_desk(2, 0, 26, 100)
    d.taste(ord("+"))
    assert D["canvas"].modus == "greifen"
    d.taste(curses.KEY_RIGHT)
    d.taste(10)                                   # ablegen → gespeichert
    assert ("PUT", "/api/desk/Elektronik") in d.aufrufe
    assert len(desk.laden("Elektronik")["elemente"]) == 1
    d.taste(ord("e"))
    assert D["modal"] is not None
    tippe(d, "# Bauteile\nWiderstände")
    d.taste(19)                                   # ctrl+s
    assert D["modal"] is None
    assert desk.laden("Elektronik")["elemente"][0]["text"] == "# Bauteile\nWiderstände"
    d.draw_desk(2, 0, 26, 100)                    # zeichnen stürzt nicht ab
    d.taste(27)                                   # esc → zurück zur Auswahl
    assert D["ebene"] == "wahl" and D["desks"][0]["name"] == "Elektronik"


def test_ansicht_modal_esc_verwirft(ansicht):
    d, D = ansicht, ansicht.DESK
    desk.speichern(desk.anlegen("a")["name"],
                   [{"id": "z", "art": "notiz", "x": 0, "y": 0, "w": 10, "h": 4, "text": "alt"}], [])
    d.oeffnen()
    d.taste(10)
    D["canvas"].fokus = "z"
    d.taste(ord("e"))
    tippe(d, "neu")
    d.taste(27)
    assert D["modal"] is None
    assert desk.laden("a")["elemente"][0]["text"] == "alt"


def test_ansicht_verbinden_und_loeschen_speichert(ansicht):
    import curses
    d, D = ansicht, ansicht.DESK
    desk.speichern(desk.anlegen("v")["name"],
                   [{"id": "a", "art": "notiz", "x": 0, "y": 0, "w": 10, "h": 4},
                    {"id": "b", "art": "notiz", "x": 30, "y": 0, "w": 10, "h": 4}], [])
    d.oeffnen(); d.taste(10)
    D["canvas"].fokus = "a"
    d.taste(ord("v"))
    d.taste(10)
    assert desk.laden("v")["verbindungen"][0]["von"] == "a"
    assert desk.laden("v") and lies("v")["edges"][0]["fromSide"] == "right"
    d.taste(ord("d"))
    d.taste(ord("j"))
    assert [e["id"] for e in desk.laden("v")["elemente"]] == ["b"]
    assert desk.laden("v")["verbindungen"] == []


def test_ansicht_konflikt_laedt_neu_und_sagt_es(ansicht):
    import curses
    d, D = ansicht, ansicht.DESK
    desk.speichern(desk.anlegen("k")["name"],
                   [{"id": "a", "art": "notiz", "x": 0, "y": 0, "w": 10, "h": 4}], [])
    d.oeffnen(); d.taste(10)
    schreibe("k", {"nodes": [], "edges": []})        # anderer Rechner war schneller
    D["canvas"].fokus = "a"
    d.taste(10); d.taste(curses.KEY_DOWN); d.taste(10)
    assert "woanders" in D["msg"] and D["canvas"].elemente == []


def test_ansicht_ohne_backend(monkeypatch):
    from tui.ansichten import desk as desk_ansicht
    from tui.ansichten import kontext

    def kein(*a, **k):
        raise urllib.error.URLError("weg")
    monkeypatch.setattr(desk_ansicht, "api_call", kein)
    z = kontext.Kontext(Schirm(), None, False, None)
    z.apply_theme("night")
    d = desk_ansicht.Desk(z)
    d.oeffnen()
    assert "nicht erreichbar" in d.DESK["msg"]
    d.taste(10); tippe(d, "x"); d.taste(10)
    assert d.DESK["ebene"] == "wahl" and "nicht angelegt" in d.DESK["msg"]


def test_shift_pfeil_als_rohe_folge_schiebt(ansicht):
    d, D = ansicht, ansicht.DESK
    desk.anlegen("p")
    d.oeffnen(); d.taste(10)
    vx = D["canvas"].vx
    d.z.stdscr.folge = [ord(c) for c in "[1;2C"]
    d.taste(27)
    assert D["canvas"].vx > vx and D["ebene"] == "canvas"
