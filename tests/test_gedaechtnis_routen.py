"""Gedächtnis für Sasha sichtbar und änderbar (Phase 3 des Claude-Web-Plans,
2026-10-07): GET /api/gedaechtnis, PUT /api/gedaechtnis/<akte>,
POST /api/skills/<name>/status (ui/routen/skills.py), dahinter
gedaechtnis.kernakte_* und skills.status_setzen.

Geprüft: was die Ansicht bekommt; nur die drei Kernakten sind schreibbar
(alles andere 404); atomar mit .bak; Konflikt, wenn die KI inzwischen
geschrieben hat (409); Skill an/aus wirkt auf Prompt und load_skill;
Fehlerfälle mit Klartext.
"""
import os

import pytest

import gedaechtnis
import skills
import state


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def _datei(name):
    return os.path.join(gedaechtnis._DIR, name + ".md")


def _schreiben(name, text):
    os.makedirs(gedaechtnis._DIR, exist_ok=True)
    with open(_datei(name), "w", encoding="utf-8") as f:
        f.write(text)


def _skill(name, status="aktiv"):
    ordner = gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)
    os.makedirs(ordner, exist_ok=True)
    with open(os.path.join(ordner, name + ".md"), "w", encoding="utf-8") as f:
        f.write(f"## {name}\n- beschreibung: wenn {name}\n- erstellt: 2026-10-07\n"
                f"- herkunft: sasha\n- status: {status}\n\nSchritt eins.\n")


# ── GET ────────────────────────────────────────────────────────────────

def test_get_liefert_kernakten_bereiche_und_skills(client):
    _schreiben("hausregeln", "# Hausregeln\n\n- Nicht duzen.\n")
    _schreiben("sasha", "# Sasha\n\nStudiert.\n")
    os.makedirs(os.path.join(gedaechtnis._DIR, "dossiers"), exist_ok=True)
    _schreiben("dossiers/umzug", "# umzug\n")
    _skill("kurz")
    d = client.get("/api/gedaechtnis").get_json()
    assert [k["akte"] for k in d["kernakten"]] == ["hausregeln", "steckbrief", "ziele"]
    akten = {k["akte"]: k for k in d["kernakten"]}
    assert "Nicht duzen" in akten["hausregeln"]["text"]
    assert "Studiert" in akten["steckbrief"]["text"]       # Datei heißt sasha.md
    assert akten["ziele"]["text"] == "" and akten["ziele"]["stand"]
    bereiche = {b["bereich"]: b["titel"] for b in d["bereiche"]}
    assert bereiche["dossiers"] == ["umzug"] and bereiche["notizen"] == []
    assert "skills" not in bereiche
    assert [s["name"] for s in d["skills"]] == ["kurz"]


# ── PUT Kernakte ───────────────────────────────────────────────────────

def test_put_schreibt_atomar_mit_bak(client):
    _schreiben("ziele", "# Ziele\n\n- alt\n")
    r = client.put("/api/gedaechtnis/ziele", json={"text": "# Ziele\n\n- Marathon\n"})
    assert r.status_code == 200
    assert "Marathon" in r.get_json()["text"]
    with open(_datei("ziele"), encoding="utf-8") as f:
        assert f.read() == "# Ziele\n\n- Marathon\n"
    with open(_datei("ziele") + ".bak", encoding="utf-8") as f:
        assert "- alt" in f.read()
    # Was im Kopf der KI steht, ist die neue Fassung.
    assert "Marathon" in gedaechtnis.kopf_block()
    # Keine Zwischendatei bleibt liegen.
    assert not [n for n in os.listdir(gedaechtnis._DIR) if n.endswith(".tmp")]


def test_put_legt_eine_fehlende_akte_an_ohne_bak(client):
    r = client.put("/api/gedaechtnis/hausregeln", json={"text": "- Kurz antworten."})
    assert r.status_code == 200
    assert os.path.exists(_datei("hausregeln"))
    assert not os.path.exists(_datei("hausregeln") + ".bak")


@pytest.mark.parametrize("akte", ["dossiers", "sasha", "notizen", "skills", "tagebuch",
                                  "HAUSREGELN", "..", "umzug"])
def test_nur_die_drei_kernakten_sind_schreibbar(client, akte):
    r = client.put(f"/api/gedaechtnis/{akte}", json={"text": "x"})
    assert r.status_code == 404
    assert "Hausregeln" in r.get_json()["error"]
    assert not os.path.exists(_datei(akte))


def test_put_ohne_text_oder_zu_lang(client):
    assert client.put("/api/gedaechtnis/ziele", json={}).status_code == 400
    assert client.put("/api/gedaechtnis/ziele", json={"text": 5}).status_code == 400
    r = client.put("/api/gedaechtnis/ziele",
                   json={"text": "x" * (gedaechtnis.MAX_KERNAKTE + 1)})
    assert r.status_code == 400 and "höchstens" in r.get_json()["error"]
    assert not os.path.exists(_datei("ziele"))


def test_put_mit_veraltetem_stand_gibt_409(client):
    _schreiben("hausregeln", "- eins\n")
    stand = client.get("/api/gedaechtnis").get_json()["kernakten"][0]["stand"]
    # Inzwischen hängt die KI eine Regel an (write_note → regel_notieren).
    gedaechtnis.regel_notieren("zwei")
    r = client.put("/api/gedaechtnis/hausregeln", json={"text": "- eins geändert\n",
                                                        "stand": stand})
    assert r.status_code == 409
    assert "zwei" in gedaechtnis.hausregeln()            # nichts überschrieben
    # Mit dem aktuellen Stand geht es.
    stand = client.get("/api/gedaechtnis").get_json()["kernakten"][0]["stand"]
    assert client.put("/api/gedaechtnis/hausregeln",
                      json={"text": "- neu\n", "stand": stand}).status_code == 200


def test_leerer_text_leert_die_akte(client):
    _schreiben("ziele", "- alt\n")
    assert client.put("/api/gedaechtnis/ziele", json={"text": "  \n"}).status_code == 200
    assert gedaechtnis.ziele() == ""
    assert "Seine Ziele" not in gedaechtnis.kopf_block()


# ── Skill-Status ───────────────────────────────────────────────────────

def test_skill_ausschalten_und_wieder_an(client):
    _skill("kurz")
    r = client.post("/api/skills/kurz/status", json={"status": "aus"})
    assert r.status_code == 200 and r.get_json()["skill"]["status"] == "aus"
    assert "kurz" not in skills.prompt_block()
    assert "nicht aktiv" in skills.laden("kurz")
    ordner = gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)
    assert os.path.exists(os.path.join(ordner, "kurz.md.bak"))
    with open(os.path.join(ordner, "kurz.md"), encoding="utf-8") as f:
        text = f.read()
    assert "Schritt eins." in text and "herkunft:" in text   # Inhalt + Kopf bleiben
    r = client.post("/api/skills/kurz/status", json={"status": "aktiv"})
    assert r.get_json()["skill"]["status"] == "aktiv"
    assert "kurz" in skills.prompt_block()


def test_skill_status_fehlerfaelle(client):
    _skill("kurz")
    assert client.post("/api/skills/gibtsnicht/status",
                       json={"status": "aus"}).status_code == 404
    # Nur der genaue Dateiname — keine Schreibvarianten.
    assert client.post("/api/skills/Kurz/status", json={"status": "aus"}).status_code == 404
    for body in ({"status": "kaputt"}, {}, None):
        r = client.post("/api/skills/kurz/status", json=body)
        assert r.status_code == 400, body
    assert skills.alle()[0]["status"] == "aktiv"


def test_gleicher_status_schreibt_nichts():
    _skill("kurz")
    skills.status_setzen("kurz", "aktiv")
    ordner = gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)
    assert not os.path.exists(os.path.join(ordner, "kurz.md.bak"))


def test_vorgeschlagen_laesst_sich_freigeben():
    _skill("neu", status="vorgeschlagen")
    assert skills.status_setzen("neu", "aktiv")["status"] == "aktiv"
    assert "Schritt eins." in skills.laden("neu")
