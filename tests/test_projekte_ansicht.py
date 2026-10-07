"""Projekte in der TUI ohne Bildschirm (tui/ansichten/projekte.py, Phase 6 des
Claude-Web-Plans, 2026-10-07): reine Helfer, /projekt und die Übersicht gegen
ein gefälschtes Backend, Editor-Weg, Wissen per Pfad (auch vom anderen
Rechner), Zeichnen in eine Attrappe, Kasten-Titel „Projekt · Gespräch"."""
import curses
import io
import json
import os
import threading
import types
import urllib.error

import pytest

from tui.ansichten import chat as chatmod
from tui.ansichten import chat_befehle, gespraechsliste
from tui.ansichten import projekte as pmod
from tui.ansichten.projekte import (Projekte, detail_zeilen, finden, groesse_text,
                                    liste_zeilen, projekt_name, wahl)

PROJEKTE = [{"id": "geige", "name": "Geige", "wissen": 2},
            {"id": "umzug-berlin", "name": "Umzug Berlin", "wissen": 0}]
DETAIL = {"id": "geige", "name": "Geige", "archiviert": False,
          "anweisungen": "# Regeln\n\n- Fingersätze nennen.\n", "stand": "s1",
          "wissen": [{"name": "noten.md", "groesse": 2048}],
          "gespraeche": [{"id": "g1", "titel": "Partita üben", "letzte": "2026-10-06T10:00:00+00:00"},
                         {"id": "g2", "titel": "Bogen", "archiviert": True, "letzte": ""}]}


# ── Reine Helfer ───────────────────────────────────────────────────────

def test_projekt_name_aus_liste_oder_neu():
    eintraege = [{"id": "g1", "projekt_name": "Geige"}, {"id": "g2"}]
    assert projekt_name(eintraege, "g1") == "Geige"
    assert projekt_name(eintraege, "g2") == ""
    assert projekt_name(eintraege, None, {"id": "geige", "name": "Geige"}) == "Geige"
    assert projekt_name(eintraege, None, None) == ""
    assert projekt_name(None, "x", "kaputt") == ""


def test_finden_nach_id_oder_name():
    assert finden(PROJEKTE, "geige")["id"] == "geige"
    assert finden(PROJEKTE, "umzug  BERLIN")["id"] == "umzug-berlin"
    assert finden(PROJEKTE, "umzug-berlin")["id"] == "umzug-berlin"
    assert finden(PROJEKTE, "umzug") is None
    assert finden(None, "x") is None


def test_wahl_steht_auf_dem_aktuellen():
    w = wahl(PROJEKTE, "Umzug Berlin")
    assert [t for t, _ in w["optionen"]] == ["Geige", "Umzug Berlin", "kein projekt",
                                            "neues projekt …"]
    assert w["idx"] == 1 and "jetzt: Umzug Berlin" in w["titel"]
    assert wahl(PROJEKTE, "")["idx"] == 2                 # „kein projekt"
    assert wahl([], "")["optionen"][-1][1] == {"neu": True}


def test_groesse_text():
    assert groesse_text(12) == "12 B" and groesse_text(2048) == "2 KB"
    assert groesse_text(3 * 1024 * 1024) == "3.0 MB" and groesse_text("x") == ""


def test_liste_und_detail_zeilen_passen_in_die_breite():
    z = liste_zeilen(PROJEKTE, 0, 30)
    assert z[0][0].startswith("› Geige") and z[0][0].endswith("2 dateien")
    assert z[0][1] == "gewaehlt" and all(len(t) <= 30 for t, _ in z)
    zeilen, ziel = detail_zeilen(DETAIL, 1, 40)
    texte = [t for t, _ in zeilen]
    assert "anweisungen" in texte and "wissen" in texte and "gespräche" in texte
    assert any("noten.md" in t and t.endswith("2 KB") for t in texte)
    assert zeilen[ziel][0].startswith("› Bogen (archiv)")
    assert all(len(t) <= 40 for t in texte)
    leer, _ = detail_zeilen({"id": "x"}, 0, 20)
    assert any("noch keine" in t for t, _ in leer)


def test_gespraechsliste_zeigt_und_findet_das_projekt():
    e = [{"id": "g1", "titel": "Partita", "projekt_name": "Geige", "letzte": ""},
         {"id": "g2", "titel": "Kisten", "letzte": ""}]
    zeilen = gespraechsliste.listen_zeilen(e, 0, 40)
    assert "Geige · Partita" in zeilen[0][0]
    assert [x["id"] for x in gespraechsliste.filtern(e, "geige")] == ["g1"]


def test_befehle_sind_bekannt():
    for roh, name, arg in (("/projekt", "projekt", ""), ("/projekt neu Geige", "projekt", "neu Geige"),
                           ("/projekte", "projekte", ""), ("/project geige", "projekt", "geige")):
        e = chat_befehle.lesen(roh)
        assert (e.art, e.name, e.arg) == ("befehl", name, arg), roh
    assert "/project" in chat_befehle.hilfe_text()


def test_kastentitel_zeigt_projekt_und_gespraech():
    c = chatmod.Chat.__new__(chatmod.Chat)
    c.AI = {"backend": "cloud", "model": "m", "provider": "claude", "kosten_heute": 0.5,
            "budget": {}, "neu": False, "titel": "Partita", "projekt": "Geige"}
    c.AI_LOCK = threading.Lock()
    assert c.ai_titel(200) == "ki-chat · Geige · Partita · cloud (claude) · 0,50€ heute"
    c.AI["titel"] = ""
    assert c.ai_titel(200).startswith("ki-chat · Geige · cloud")


# ── Mit gefälschtem Backend ────────────────────────────────────────────

class FakeChat:
    def __init__(self):
        self.AI = {"msg": "", "liste": None, "gedaechtnis": None, "streaming": False,
                   "gid": "g1", "gespraeche": [{"id": "g1"}], "input": "", "cur": 0,
                   "wahl": None}
        self.AI_LOCK = threading.Lock()
        self.z = types.SimpleNamespace(stdscr=types.SimpleNamespace(
            clear=lambda: None, refresh=lambda: None))
        self.geoeffnet, self.geleert = [], 0

    def gespraech_oeffnen(self, gid):
        self.geoeffnet.append(gid)

    def leeren(self):
        self.geleert += 1
        self.AI["gid"] = None


def _http(code, daten):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(json.dumps(daten).encode()))


@pytest.fixture
def backend(monkeypatch):
    zustand = {"aufrufe": [], "fehler": {}, "liste": json.loads(json.dumps(PROJEKTE))}

    def api(pfad, methode="GET", body=None, timeout=3.0):
        zustand["aufrufe"].append((methode, pfad, body))
        f = zustand["fehler"].get((methode, pfad))
        if f:
            raise f() if callable(f) else f
        if pfad.startswith("/api/projekte?") or pfad == "/api/projekte":
            if methode == "POST":
                p = {"id": body["name"].lower(), "name": body["name"]}
                zustand["liste"].append(p)
                return p
            return {"projekte": zustand["liste"]}
        if pfad == "/api/projekte/zuordnen":
            n = next((p["name"] for p in zustand["liste"] if p["id"] == body["projekt"]), None)
            return {"gespraech": body["gespraech"], "projekt": body["projekt"], "name": n}
        if pfad == "/api/projekte/geige":
            return json.loads(json.dumps(DETAIL))
        if pfad == "/api/chat/clear":
            return {"ok": True, "projekt": body.get("projekt"), "name": "Geige"}
        return {"ok": True, "name": "plan.txt", "stand": "s2"}
    monkeypatch.setattr(pmod, "api_call", api)
    return zustand


def _tippe(p, *tasten):
    for t in tasten:
        if isinstance(t, str) and len(t) > 1:
            for b in t.encode("utf-8"):
                p.taste(b)
        else:
            p.taste(ord(t) if isinstance(t, str) else t)


def _posts(backend, pfad):
    return [a[2] for a in backend["aufrufe"] if a[0] in ("POST", "PUT") and a[1] == pfad]


def test_projekt_ohne_argument_ist_eine_auswahl(backend):
    c = FakeChat()
    p = Projekte(c)
    p.befehl("projekt", "")
    w = c.AI["wahl"]
    assert w and [t for t, _ in w["optionen"]][:2] == ["Geige", "Umzug Berlin"]
    w["aktion"](w["optionen"][0][1])
    assert _posts(backend, "/api/projekte/zuordnen") == [{"gespraech": "g1", "projekt": "geige"}]
    assert c.AI["projekt"] == "Geige" and "Geige" in c.AI["msg"]
    assert c.AI["gespraeche"][0]["projekt_name"] == "Geige"
    w["aktion"]({"neu": True})
    assert c.AI["input"] == "/project new " and c.AI["cur"] == len(c.AI["input"])


def test_projekt_mit_namen_neu_und_kein(backend):
    c = FakeChat()
    p = Projekte(c)
    p.befehl("projekt", "umzug berlin")
    assert _posts(backend, "/api/projekte/zuordnen")[-1]["projekt"] == "umzug-berlin"
    p.befehl("projekt", "kein")
    assert _posts(backend, "/api/projekte/zuordnen")[-1]["projekt"] is None
    assert c.AI["projekt"] == ""
    p.befehl("projekt", "neu Chor")
    assert _posts(backend, "/api/projekte") == [{"name": "Chor"}]
    assert _posts(backend, "/api/projekte/zuordnen")[-1]["projekt"] == "chor"
    assert "angelegt" in c.AI["msg"]
    n = len(backend["aufrufe"])
    p.befehl("projekt", "gibtsnicht")
    assert "/project new gibtsnicht" in c.AI["msg"]
    assert not [a for a in backend["aufrufe"][n:] if a[0] == "POST"]


def test_projekt_fehler_und_erinnerungen(backend):
    c = FakeChat()
    p = Projekte(c)
    backend["fehler"][("POST", "/api/projekte")] = lambda: _http(400, {"error": "Ein Projekt „Geige“ gibt es schon."})
    p.befehl("projekt", "neu Geige")
    assert c.AI["msg"] == "ein projekt „geige“ gibt es schon."
    c.AI["gid"] = "erinnerungen"
    p.befehl("projekt", "")
    assert c.AI["wahl"] is None and "erinnerungen" in c.AI["msg"]
    backend["fehler"][("GET", "/api/projekte")] = urllib.error.URLError("weg")
    c.AI["gid"] = "g1"
    p.befehl("projekt", "geige")
    assert "keine verbindung" in c.AI["msg"]


def test_uebersicht_liste_detail_und_gespraech_oeffnen(backend):
    c = FakeChat()
    c.AI["liste"] = {"offen": True}
    p = Projekte(c)
    p.befehl("projekte", "")
    assert c.AI["projekte"]["liste"][0]["id"] == "geige" and c.AI["liste"] is None
    _tippe(p, curses.KEY_DOWN, curses.KEY_UP, 10)
    assert c.AI["projekte"]["detail"]["id"] == "geige"
    assert "e instructions" in p.fusszeile()
    _tippe(p, curses.KEY_DOWN, curses.KEY_DOWN, 10)       # rundum zurück zu g1
    assert c.geoeffnet == ["g1"] and c.AI["projekte"] is None


def test_uebersicht_neues_gespraech_im_projekt(backend):
    c = FakeChat()
    p = Projekte(c)
    p.oeffnen()
    _tippe(p, 10, "n")
    assert _posts(backend, "/api/chat/clear") == [{"projekt": "geige"}]
    assert c.geleert == 1 and c.AI["projekt"] == "Geige" and c.AI["projekte"] is None


def test_uebersicht_neues_projekt_und_archiv(backend):
    c = FakeChat()
    p = Projekte(c)
    p.oeffnen()
    _tippe(p, "n", "Chor ü", 10)
    assert _posts(backend, "/api/projekte") == [{"name": "Chor ü"}]
    _tippe(p, "a")                # archiviert das gewählte (oben: Geige)
    assert _posts(backend, "/api/projekte/geige/archiv") == [{"an": True}]
    _tippe(p, "z")
    assert c.AI["projekte"]["archiv"] is True
    _tippe(p, 27)
    assert c.AI["projekte"] is None


def test_wissen_per_pfad(backend, tmp_path):
    c = FakeChat()
    p = Projekte(c)
    p.oeffnen()
    _tippe(p, 10, "w", str(tmp_path / "plan.txt"), 10)
    assert _posts(backend, "/api/projekte/geige/wissen") == [{"pfad": str(tmp_path / "plan.txt")}]
    assert "plan.txt" in c.AI["msg"]


def test_wissen_vom_anderen_rechner_schickt_den_text(backend, tmp_path):
    datei = tmp_path / "plan.txt"
    datei.write_text("Tonleitern", encoding="utf-8")
    zaehler = {"n": 0}

    def erst_fehlt():
        zaehler["n"] += 1
        return _http(404, {"error": "gibt es nicht", "fehlt": True})
    c = FakeChat()
    p = Projekte(c)
    p.oeffnen()
    _tippe(p, 10)
    backend["fehler"][("POST", "/api/projekte/geige/wissen")] = erst_fehlt
    # Erst fehlt sie beim Backend → die TUI liest selbst und schickt den Text.
    echt = pmod.api_call

    def api(pfad, methode="GET", body=None, timeout=3.0):
        if body and "text" in body:
            backend["fehler"].pop(("POST", "/api/projekte/geige/wissen"), None)
        return echt(pfad, methode, body, timeout)
    pmod.api_call = api
    try:
        p.wissen_hinzufuegen(c.AI["projekte"]["detail"], str(datei))
    finally:
        pmod.api_call = echt
    posts = _posts(backend, "/api/projekte/geige/wissen")
    assert posts[-1] == {"pfad": str(datei), "text": "Tonleitern"}
    assert zaehler["n"] == 1


def test_wissen_gesperrt_zeigt_den_grund(backend, tmp_path):
    c = FakeChat()
    p = Projekte(c)
    p.oeffnen()
    _tippe(p, 10)
    backend["fehler"][("POST", "/api/projekte/geige/wissen")] = lambda: _http(
        400, {"error": "Diese Datei nehme ich nicht: Datei mit Zugangsdaten — gesperrt."})
    p.wissen_hinzufuegen(c.AI["projekte"]["detail"], "/x/.env")
    assert "zugangsdaten" in c.AI["msg"]
    assert len(_posts(backend, "/api/projekte/geige/wissen")) == 1   # kein zweiter Versuch


@pytest.fixture
def editor(monkeypatch, tmp_path):
    for f in ("def_prog_mode", "endwin", "reset_prog_mode"):
        monkeypatch.setattr(curses, f, lambda: None)
    monkeypatch.setattr(pmod, "editor_befehl", lambda: ["fake-editor"])
    monkeypatch.setattr(pmod.tempfile, "tempdir", str(tmp_path))
    aenderung = {"neu": None}

    def call(cmd):
        if aenderung["neu"] is not None:
            with open(cmd[-1], "w", encoding="utf-8") as f:
                f.write(aenderung["neu"])
        return 0
    monkeypatch.setattr(pmod.subprocess, "call", call)
    return aenderung


def test_anweisungen_im_editor_mit_stand(backend, editor, tmp_path):
    editor["neu"] = "- Immer Fingersätze.\n"
    c = FakeChat()
    p = Projekte(c)
    p.oeffnen()
    _tippe(p, 10, "e")
    assert _posts(backend, "/api/projekte/geige/anweisungen") == [
        {"text": "- Immer Fingersätze.\n", "stand": "s1"}]
    assert "gespeichert" in c.AI["msg"] and os.listdir(tmp_path) == []


def test_anweisungen_konflikt_laesst_den_text_liegen(backend, editor, tmp_path):
    editor["neu"] = "- meine fassung\n"
    backend["fehler"][("PUT", "/api/projekte/geige/anweisungen")] = lambda: _http(
        409, {"error": "Die Anweisungen wurden inzwischen geändert"})
    c = FakeChat()
    p = Projekte(c)
    p.oeffnen()
    _tippe(p, 10, "e")
    assert len(os.listdir(tmp_path)) == 1
    assert "inzwischen geändert" in c.AI["msg"] and str(tmp_path) in c.AI["msg"]


@pytest.mark.parametrize("breite,hoehe", [(80, 18), (40, 10), (136, 26), (12, 6)])
def test_zeichnen_bleibt_im_kasten(backend, breite, hoehe):
    c = FakeChat()
    gezeichnet = []

    def addclip(y, x, text, w, attr=0):
        gezeichnet.append((y, x, text[:max(0, w)]))
    c.z.C = {k: 0 for k in ("bright", "dim", "faint", "acc", "warn")}
    c.z.addclip = addclip
    p = Projekte(c)
    for schritt in ("liste", "detail", "eingabe"):
        p.oeffnen()
        if schritt != "liste":
            _tippe(p, 10)
        if schritt == "eingabe":
            _tippe(p, "w", "/ein/langer/pfad/zur/datei.md")
        c.AI["msg"] = "eine meldung"
        gezeichnet.clear()
        p.zeichnen(0, 0, hoehe, breite)
        for y, x, text in gezeichnet:
            assert 0 <= y < hoehe and x + len(text) <= breite, (schritt, y, x, text)


def test_chat_leitet_projekt_befehle_weiter(backend):
    c = chatmod.Chat.__new__(chatmod.Chat)
    c.AI = {"msg": "", "liste": None, "perm": None, "wahl": None, "streaming": False,
            "gid": "g1", "gespraeche": [], "input": "", "cur": 0}
    c.AI_LOCK = threading.Lock()
    c.z = types.SimpleNamespace(C={k: 0 for k in ("bright", "dim", "faint", "acc", "warn")},
                                addclip=lambda *a, **k: None)
    c.liste = types.SimpleNamespace(oeffnen=lambda: None)
    c.projekte = Projekte(c)
    c.befehl("projekt", "")
    assert c.AI["wahl"]["optionen"][0][0] == "Geige"
    assert c.AI["wahl"]["idx"] == 2                 # steht auf „kein projekt"
    c.taste(ord("1"))                              # Ziffer nimmt die erste
    assert _posts(backend, "/api/projekte/zuordnen")[-1]["projekt"] == "geige"
    c.befehl("projekte", "")
    assert "n new project" in c.fusszeile()
    c.projekte.taste(27)          # c.taste(27) läse erst nach (Alt-Taste?)
    assert c.AI["projekte"] is None
