"""Die Routen der Gespräche (ui/routen/ki.py, ui/routen/gespraeche.py) mit
dem Flask-Test-Client — Claude-Web-Plan Phase 2, 2026-10-07."""
import json

import pytest

import ai_backends
import gespraeche
import kern


@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    return app.test_client()


def _antwort(monkeypatch, *stuecke, gesehen=None):
    """Der Kern antwortet mit diesen Stücken (Text oder Events)."""
    def gen(history, **k):
        if gesehen is not None:
            gesehen.append(history)
        yield from stuecke

    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)


def _events(r):
    return [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
            if z.startswith("data:")]


# ── /api/chat schreibt ins aktive Gespräch ────────────────────────────

def test_werkzeug_ergebnis_wird_gekuerzt_mitgespeichert(client, monkeypatch):
    """Seit 2026-10-07: der Schritt „Used … ›" in der TUI klappt das Ergebnis
    auf — es bleibt gekürzt im Verlauf, auch ein Fehler."""
    from ui.routen import ki as ki_routen
    lang = "x" * 1000
    _antwort(monkeypatch,
             {"werkzeug": {"phase": "start", "name": "read_note", "args": {"name": "a"}}},
             {"werkzeug": {"phase": "fertig", "name": "read_note", "text": lang}},
             {"werkzeug": {"phase": "start", "name": "web_search", "args": {"query": "b"}}},
             {"werkzeug": {"phase": "fehler", "name": "web_search", "text": "kein netz"}},
             "fertig")
    client.post("/api/chat", json={"message": "los"}).get_data()
    w = gespraeche.nachrichten(gespraeche.aktiv())[1]["werkzeuge"]
    assert len(w[0]["ergebnis"]) <= ki_routen.ERGEBNIS_MAX
    assert w[1] == {"name": "web_search", "args": "query=b", "fehler": True,
                    "ergebnis": "kein netz"}


def test_chat_legt_ein_gespraech_an_und_speichert_antwort_mit_denken(client, monkeypatch):
    _antwort(monkeypatch, {"reflect": "erst "}, {"reflect": "nachdenken"},
             {"werkzeug": {"phase": "start", "name": "read_note", "args": {"name": "ideen"}}},
             "Steht ", "drin.")
    ev = _events(client.post("/api/chat", json={"message": "was steht in ideen?"}))
    gid = gespraeche.aktiv()
    assert gid and ev[1] == {"gespraech": gid, "nachricht": ev[1]["nachricht"]}
    ns = gespraeche.nachrichten(gid)
    assert [(n["rolle"], n["text"]) for n in ns] == [
        ("user", "was steht in ideen?"), ("assistant", "Steht drin.")]
    assert ns[1]["denken"] == "erst nachdenken"
    assert ns[1]["werkzeuge"] == [{"name": "read_note", "args": "name=ideen"}]
    assert ns[1]["anbieter"] == "test"
    # Erster Zug: der Titel kommt mit (ohne Cloud-Verbindung: die ersten Wörter).
    assert {"titel": "was steht in ideen?", "gespraech": gid} in ev
    assert ev[-1] == {"done": True}


def test_chat_schickt_das_gespraech_als_verlauf(client, monkeypatch):
    gesehen = []
    _antwort(monkeypatch, "ok", gesehen=gesehen)
    client.post("/api/chat", json={"message": "eins"}).get_data()
    client.post("/api/chat", json={"message": "zwei"}).get_data()
    assert gesehen[-1] == [{"role": "user", "content": "eins"},
                           {"role": "assistant", "content": "ok"},
                           {"role": "user", "content": "zwei"}]


def test_chat_in_ein_bestimmtes_gespraech(client, monkeypatch):
    _antwort(monkeypatch, "ok")
    a = gespraeche.neu("a")
    client.post("/api/chat", json={"message": "hier", "gespraech": a}).get_data()
    assert [n["text"] for n in gespraeche.nachrichten(a)] == ["hier", "ok"]
    assert gespraeche.aktiv() == a


def test_gestoppte_antwort_wird_als_abgebrochen_gespeichert(client, monkeypatch):
    _antwort(monkeypatch, "halb fert", {"gestoppt": True})
    client.post("/api/chat", json={"message": "x"}).get_data()
    letzte = gespraeche.nachrichten(gespraeche.aktiv())[-1]
    assert letzte["abgebrochen"] is True and letzte["text"] == "halb fert"
    h = client.get("/api/chat/history").get_json()
    assert h[-1]["content"] == "halb fert\n\n(abgebrochen)" and h[-1]["abgebrochen"]


def test_history_liefert_denken_und_markiert_gelesen(client, monkeypatch):
    _antwort(monkeypatch, {"reflect": "hm"}, "ja")
    client.post("/api/chat", json={"message": "x"}).get_data()
    gid = gespraeche.aktiv()
    gespraeche.anhaengen(gid, "assistant", "nachgereicht")      # z. B. vom anderen Rechner
    assert gespraeche.liste()[0]["ungelesen"] is True
    h = client.get("/api/chat/history").get_json()
    assert [m["role"] for m in h] == ["user", "assistant", "assistant"]
    assert h[1]["denken"] == "hm" and h[1]["id"]
    assert gespraeche.liste()[0]["ungelesen"] is False


def test_history_geht_auch_ohne_ki(client, monkeypatch):
    gid = gespraeche.neu("alt")
    gespraeche.anhaengen(gid, "user", "von gestern")
    gespraeche.aktiv_setzen(gid)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: None)
    assert client.get("/api/chat/history").get_json()[0]["content"] == "von gestern"


def test_clear_beginnt_ein_neues_und_behaelt_das_alte(client, monkeypatch):
    _antwort(monkeypatch, "ok")
    client.post("/api/chat", json={"message": "erstes"}).get_data()
    alt = gespraeche.aktiv()
    assert client.post("/api/chat/clear").get_json()["ok"]
    assert gespraeche.aktiv() is None
    assert client.get("/api/chat/history").get_json() == []
    client.post("/api/chat", json={"message": "zweites"}).get_data()
    neu = gespraeche.aktiv()
    assert neu != alt and gespraeche.nachrichten(alt)[0]["text"] == "erstes"
    assert {g["id"] for g in gespraeche.liste()} == {alt, neu}


# ── Wiederholen und Bearbeiten ────────────────────────────────────────

def test_wiederholen_verwirft_die_antwort_und_fragt_neu(client, monkeypatch):
    _antwort(monkeypatch, "schlecht")
    client.post("/api/chat", json={"message": "frage"}).get_data()
    gesehen = []
    _antwort(monkeypatch, "besser", gesehen=gesehen)
    r = client.post("/api/chat/wiederholen", json={})
    assert r.content_type.startswith("text/event-stream")
    assert {"token": "besser"} in _events(r)
    assert gesehen[0] == [{"role": "user", "content": "frage"}]
    assert [n["text"] for n in gespraeche.nachrichten(gespraeche.aktiv())] == ["frage", "besser"]


def test_bearbeiten_ersetzt_ab_der_nachricht(client, monkeypatch):
    _antwort(monkeypatch, "a1")
    client.post("/api/chat", json={"message": "f1"}).get_data()
    client.post("/api/chat", json={"message": "f2 mit tippfehler"}).get_data()
    gid = gespraeche.aktiv()
    f2 = gespraeche.letzte_nutzer_nachricht(gid)["id"]
    _antwort(monkeypatch, "a2")
    client.post("/api/chat", json={"message": "f2 richtig", "ersetzt": f2}).get_data()
    assert [n["text"] for n in gespraeche.nachrichten(gid)] == ["f1", "a1", "f2 richtig", "a2"]


def test_wiederholen_ohne_frage_ist_400(client, monkeypatch):
    assert client.post("/api/chat/wiederholen", json={}).status_code == 400


def test_bearbeiten_mit_unbekannter_nachricht_ist_404_und_schreibt_nichts(client, monkeypatch):
    _antwort(monkeypatch, "a")
    client.post("/api/chat", json={"message": "f"}).get_data()
    gid = gespraeche.aktiv()
    r = client.post("/api/chat", json={"message": "neu", "ersetzt": "gibts-nicht"})
    assert r.status_code == 404
    assert [n["text"] for n in gespraeche.nachrichten(gid)] == ["f", "a"]


def test_bearbeiten_einer_ki_antwort_ist_400(client, monkeypatch):
    _antwort(monkeypatch, "a")
    client.post("/api/chat", json={"message": "f"}).get_data()
    ki = gespraeche.nachrichten(gespraeche.aktiv())[-1]["id"]
    assert client.post("/api/chat", json={"message": "x", "ersetzt": ki}).status_code == 400


# ── Fehlerfälle: unbekannte id ────────────────────────────────────────

@pytest.mark.parametrize("methode,pfad,body", [
    ("post", "/api/chat", {"message": "x", "gespraech": "gibts-nicht"}),
    ("post", "/api/chat/wiederholen", {"gespraech": "gibts-nicht"}),
    ("get", "/api/chat/history?gespraech=gibts-nicht", None),
    ("get", "/api/gespraeche/gibts-nicht", None),
    ("post", "/api/gespraeche/aktiv", {"id": "gibts-nicht"}),
    ("post", "/api/gespraeche/gibts-nicht/titel", {"titel": "x"}),
    ("post", "/api/gespraeche/gibts-nicht/archiv", {"an": True}),
])
def test_unbekanntes_gespraech_ist_404(client, methode, pfad, body):
    r = getattr(client, methode)(pfad, json=body) if body is not None \
        else getattr(client, methode)(pfad)
    assert r.status_code == 404
    assert gespraeche.liste() == [] and gespraeche.aktiv() is None


# ── Verwaltung ────────────────────────────────────────────────────────

def test_liste_neu_oeffnen_umbenennen_archivieren(client, monkeypatch):
    _antwort(monkeypatch, "ok")
    r = client.post("/api/gespraeche", json={"titel": "Fahrrad"})
    assert r.status_code == 201
    gid = r.get_json()["id"]
    assert gespraeche.aktiv() == gid
    client.post("/api/chat", json={"message": "schlauch"}).get_data()
    liste = client.get("/api/gespraeche").get_json()
    assert liste["aktiv"] == gid and liste["gespraeche"][0]["titel"] == "Fahrrad"

    assert client.post(f"/api/gespraeche/{gid}/titel", json={"titel": "  Rad  flicken "}) \
        .get_json()["titel"] == "Rad flicken"
    assert client.post(f"/api/gespraeche/{gid}/titel", json={"titel": " "}).status_code == 400

    geladen = client.get(f"/api/gespraeche/{gid}").get_json()
    assert geladen["kopf"]["titel"] == "Rad flicken" and len(geladen["nachrichten"]) == 2

    r = client.post(f"/api/gespraeche/{gid}/archiv", json={})
    assert r.get_json() == {"ok": True, "archiviert": True, "aktiv": None}
    assert client.get("/api/gespraeche").get_json()["gespraeche"] == []
    assert client.get("/api/gespraeche?archiv=1").get_json()["gespraeche"][0]["id"] == gid
    client.post(f"/api/gespraeche/{gid}/archiv", json={"an": False})
    assert client.get("/api/gespraeche").get_json()["gespraeche"][0]["id"] == gid

    assert client.post("/api/gespraeche/aktiv", json={"id": gid}).get_json()["aktiv"] == gid
    assert client.post("/api/gespraeche/aktiv", json={"id": None}).status_code == 200
    assert gespraeche.aktiv() is None


def test_erinnerungen_bleiben_wie_sie_sind(client):
    gespraeche.erinnerungen()
    assert client.post("/api/gespraeche/erinnerungen/titel",
                       json={"titel": "x"}).status_code == 400
    assert client.post("/api/gespraeche/erinnerungen/archiv", json={}).status_code == 400
    assert gespraeche.kopf("erinnerungen")["titel"] == "Erinnerungen"
