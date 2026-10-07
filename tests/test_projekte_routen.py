"""Routen der Projekte (Phase 6, 2026-10-07): ui/routen/projekte.py und die
Projekt-Kabel in /api/chat, /api/chat/clear und /api/gespraeche.

Verhalten und Fehlerfälle über den Flask-Test-Client; kein KI-Backend nötig
(der Chat-Zug läuft gegen einen gefälschten Cloud-Weg)."""
import pytest

import ai_backends
import gedaechtnis
import gespraeche
import kern
import projekte
import state
from ui.app import app


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)


@pytest.fixture
def c():
    app.config.update(TESTING=True)
    return app.test_client()


def _anlegen(c, name="Geige", **mehr):
    r = c.post("/api/projekte", json={"name": name, **mehr})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def _fake_cloud(monkeypatch):
    gesehen = []

    class Modul:
        @staticmethod
        def chat_stream(h, **k):
            gesehen.append(k)
            return iter(["antwort"])
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    return gesehen


def test_anlegen_liste_laden(c):
    pid = _anlegen(c, "Umzug Berlin", anweisungen="Kostenliste führen.")
    liste = c.get("/api/projekte").get_json()["projekte"]
    assert [p["id"] for p in liste] == [pid]
    p = c.get(f"/api/projekte/{pid}").get_json()
    assert p["name"] == "Umzug Berlin"
    assert "Kostenliste" in p["anweisungen"] and p["stand"]
    assert p["gespraeche"] == [] and p["wissen"] == []


@pytest.mark.parametrize("body", [{}, {"name": "  "}, {"name": "neu"}])
def test_anlegen_fehler(c, body):
    r = c.post("/api/projekte", json=body)
    assert r.status_code == 400 and r.get_json()["error"]


def test_anlegen_doppelt(c):
    _anlegen(c)
    assert c.post("/api/projekte", json={"name": "geige"}).status_code == 400


def test_unbekanntes_projekt_ist_404(c):
    assert c.get("/api/projekte/nichts").status_code == 404
    assert c.put("/api/projekte/nichts/anweisungen", json={"text": "x"}).status_code == 404
    assert c.post("/api/projekte/nichts/wissen", json={"name": "a", "text": "b"}).status_code == 404
    assert c.post("/api/projekte/nichts/archiv", json={}).status_code == 404
    assert c.post("/api/projekte/zuordnen", json={"projekt": "nichts"}).status_code == 404


def test_anweisungen_put_mit_stand_und_409(c):
    pid = _anlegen(c, anweisungen="alt")
    stand = c.get(f"/api/projekte/{pid}").get_json()["stand"]
    r = c.put(f"/api/projekte/{pid}/anweisungen", json={"text": "neu", "stand": stand})
    assert r.status_code == 200 and r.get_json()["anweisungen"] == "neu\n"
    # Derselbe (jetzt alte) Stand noch einmal → 409, nichts überschrieben.
    r = c.put(f"/api/projekte/{pid}/anweisungen", json={"text": "anders", "stand": stand})
    assert r.status_code == 409
    assert projekte.anweisungen_lesen(pid) == "neu\n"
    assert c.put(f"/api/projekte/{pid}/anweisungen", json={}).status_code == 400
    lang = "x" * (projekte.MAX_ANWEISUNGEN + 1)
    assert c.put(f"/api/projekte/{pid}/anweisungen", json={"text": lang}).status_code == 400


def test_wissen_text_datei_und_sperre(c, tmp_path):
    pid = _anlegen(c)
    r = c.post(f"/api/projekte/{pid}/wissen", json={"name": "noten", "text": "Bach"})
    assert r.status_code == 201 and r.get_json()["name"] == "noten.md"
    datei = tmp_path / "plan.txt"
    datei.write_text("Tonleitern", encoding="utf-8")
    r = c.post(f"/api/projekte/{pid}/wissen", json={"pfad": str(datei)})
    assert r.status_code == 201 and r.get_json()["name"] == "plan.txt"
    geheim = tmp_path / ".env"
    geheim.write_text("KEY=1", encoding="utf-8")
    r = c.post(f"/api/projekte/{pid}/wissen", json={"pfad": str(geheim)})
    assert r.status_code == 400
    r = c.post(f"/api/projekte/{pid}/wissen", json={"pfad": "/nirgends/da.md"})
    assert r.status_code == 404 and r.get_json()["fehlt"] is True
    # Die TUI auf einem anderen Rechner schickt den Text mit.
    r = c.post(f"/api/projekte/{pid}/wissen", json={"pfad": "/nirgends/da.md", "text": "von drüben"})
    assert r.status_code == 201
    r = c.post(f"/api/projekte/{pid}/wissen", json={"pfad": "/x/.env", "text": "KEY=1"})
    assert r.status_code == 400
    assert c.post(f"/api/projekte/{pid}/wissen", json={"name": "leer", "text": " "}).status_code == 400
    namen = [w["name"] for w in c.get(f"/api/projekte/{pid}").get_json()["wissen"]]
    assert namen == ["da.md", "noten.md", "plan.txt"]


def test_archivieren_und_zurueck(c):
    pid = _anlegen(c)
    assert c.post(f"/api/projekte/{pid}/archiv", json={}).get_json()["archiviert"] is True
    assert c.get("/api/projekte").get_json()["projekte"] == []
    assert [p["id"] for p in c.get("/api/projekte?archiv=1").get_json()["projekte"]] == [pid]
    assert c.post(f"/api/projekte/{pid}/archiv", json={"an": False}).get_json()["archiviert"] is False


def test_zuordnen_und_loesen(c):
    pid = _anlegen(c)
    gid = gespraeche.neu()
    gespraeche.anhaengen(gid, "user", "hallo")
    r = c.post("/api/projekte/zuordnen", json={"gespraech": gid, "projekt": pid})
    assert r.status_code == 200 and r.get_json()["name"] == "Geige"
    eintrag = c.get("/api/gespraeche").get_json()["gespraeche"][0]
    assert eintrag["projekt"] == pid and eintrag["projekt_name"] == "Geige"
    assert [g["id"] for g in c.get(f"/api/gespraeche?projekt={pid}").get_json()["gespraeche"]] == [gid]
    assert [g["id"] for g in c.get(f"/api/projekte/{pid}").get_json()["gespraeche"]] == [gid]
    r = c.post("/api/projekte/zuordnen", json={"gespraech": gid, "projekt": None})
    assert r.status_code == 200 and gespraeche.projekt_von(gid) is None


def test_zuordnen_fehler(c):
    pid = _anlegen(c)
    assert c.post("/api/projekte/zuordnen",
                  json={"gespraech": "gibts-nicht", "projekt": pid}).status_code == 404
    e = gespraeche.erinnerungen()
    assert c.post("/api/projekte/zuordnen",
                  json={"gespraech": e, "projekt": pid}).status_code == 400
    assert c.get("/api/gespraeche?projekt=nichts").status_code == 404
    # Ohne gespraech, obwohl eins offen ist: welches wäre gemeint?
    g = gespraeche.neu()
    gespraeche.aktiv_setzen(g)
    assert c.post("/api/projekte/zuordnen", json={"projekt": pid}).status_code == 400


def test_neu_aus_einem_projekt_bleibt_im_projekt(c, monkeypatch):
    gesehen = _fake_cloud(monkeypatch)
    pid = _anlegen(c)
    gid = gespraeche.neu(projekt=pid)
    gespraeche.anhaengen(gid, "user", "hallo")
    gespraeche.aktiv_setzen(gid)
    r = c.post("/api/chat/clear", json={})
    assert r.get_json()["projekt"] == pid
    assert c.get("/api/gespraeche").get_json()["neu_projekt"] == {"id": pid, "name": "Geige"}
    c.post("/api/chat", json={"message": "neue frage"}).get_data()
    neu = gespraeche.aktiv()
    assert neu != gid and gespraeche.projekt_von(neu) == pid
    assert gesehen[-1].get("projekt") == pid


def test_neu_ohne_projekt_und_ausdruecklich(c, monkeypatch):
    _fake_cloud(monkeypatch)
    pid = _anlegen(c)
    assert c.post("/api/chat/clear", json={}).get_json()["projekt"] is None
    assert c.post("/api/chat/clear", json={"projekt": "nichts"}).status_code == 404
    assert c.post("/api/chat/clear", json={"projekt": pid}).get_json()["projekt"] == pid
    # Zuordnen, bevor das neue Gespräch existiert: lösen.
    assert c.post("/api/projekte/zuordnen", json={"projekt": None}).status_code == 200
    c.post("/api/chat", json={"message": "x"}).get_data()
    assert gespraeche.projekt_von(gespraeche.aktiv()) is None


def test_chat_ohne_projekt_gibt_keins_mit(c, monkeypatch):
    gesehen = _fake_cloud(monkeypatch)
    c.post("/api/chat", json={"message": "x"}).get_data()
    assert "projekt" not in gesehen[-1]
