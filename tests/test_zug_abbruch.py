"""Ein abgebrochener Zug (Fehler, Rundengrenze, gestoppt ohne Text) wird
gespeichert und die KI erfährt im nächsten Zug davon — als Systemhinweis,
nicht als ihre Worte (2026-10-09, Sasha: „sieht die ai eigentlich diese
fehlermeldung …?")."""
import json

import pytest

import ai_backends
import cloud
import cloud_openai
import gespraeche
import kern

GRENZE = "Maximale Tool-Tiefe erreicht (8 Runden) — die Aufgabe ist zu groß"


@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    return app.test_client()


def _antwort(monkeypatch, *zuege, gesehen=None):
    """Der Kern antwortet Zug für Zug mit diesen Stück-Listen."""
    zuege = list(zuege)

    def gen(history, **k):
        if gesehen is not None:
            gesehen.append(history)
        yield from zuege.pop(0)

    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)


def _events(r):
    return [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
            if z.startswith("data:")]


ABBRUCH = [{"werkzeug": {"phase": "start", "name": "browser_open", "args": {"url": "lsf"}}},
           {"werkzeug": {"phase": "fertig", "name": "browser_open", "text": "Seite"}},
           {"werkzeug": {"phase": "start", "name": "browser_click", "args": {"nr": 9}}},
           {"werkzeug": {"phase": "fehler", "name": "browser_click", "text": "weg"}},
           {"fehler": GRENZE}]


def test_abgebrochener_zug_wird_mit_fehler_und_werkzeugen_gespeichert(client, monkeypatch):
    _antwort(monkeypatch, ABBRUCH)
    ev = _events(client.post("/api/chat", json={"message": "stundenplan"}))
    ns = gespraeche.nachrichten(gespraeche.aktiv())
    assert [n["rolle"] for n in ns] == ["user", "assistant"]
    assert ns[1]["fehler"] == GRENZE and ns[1]["text"] == ""
    assert [w["name"] for w in ns[1]["werkzeuge"]] == ["browser_open", "browser_click"]
    abbruch = next(e for e in ev if "abbruch" in e)
    assert abbruch["antwort"] == ns[1]["id"] and abbruch["abbruch"] == GRENZE
    h = client.get("/api/chat/history").get_json()
    assert h[-1]["fehler"] == GRENZE and h[-1]["role"] == "assistant"


def test_gestoppt_ohne_text_wird_auch_gespeichert(client, monkeypatch):
    _antwort(monkeypatch, [{"gestoppt": True}])
    client.post("/api/chat", json={"message": "x"}).get_data()
    letzte = gespraeche.nachrichten(gespraeche.aktiv())[-1]
    assert letzte["rolle"] == "assistant" and "gestoppt" in letzte["fehler"]
    assert not letzte.get("abgebrochen")


def test_fehler_mit_text_behaelt_text_und_meldung(client, monkeypatch):
    _antwort(monkeypatch, ["halb ", {"fehler": GRENZE}])
    client.post("/api/chat", json={"message": "x"}).get_data()
    letzte = gespraeche.nachrichten(gespraeche.aktiv())[-1]
    assert letzte["text"] == "halb " and letzte["fehler"] == GRENZE


def test_ki_bekommt_den_abbruch_im_naechsten_zug_als_systemhinweis(client, monkeypatch):
    gesehen = []
    _antwort(monkeypatch, ABBRUCH, ["ok"], gesehen=gesehen)
    client.post("/api/chat", json={"message": "stundenplan"}).get_data()
    client.post("/api/chat", json={"message": "und jetzt?"}).get_data()
    verlauf = gesehen[-1]
    hinweis = verlauf[1]
    assert hinweis["role"] == "assistant"
    t = hinweis["content"]
    assert t.startswith("[System, nicht deine Worte: Dein letzter Zug brach ab")
    assert GRENZE.split(" —")[0] in t and "browser_open(url=lsf)" in t
    assert "browser_click(nr=9) ✗" in t
    # Anthropic- und OpenAI-Weg geben ihn als Text der Antwort weiter.
    a = cloud._prepare_messages(verlauf)
    assert a[1]["role"] == "assistant" and "Dein letzter Zug brach ab" in a[1]["content"][0]["text"]
    o = cloud_openai._prepare_messages(verlauf, "system")
    assert o[2]["role"] == "assistant" and "Dein letzter Zug brach ab" in o[2]["content"]


def test_fehler_hinweis_kuerzt_lange_spuren():
    n = {"fehler": "x", "werkzeuge": [{"name": "w%d" % i, "args": "a" * 200} for i in range(30)]}
    t = gespraeche.fehler_hinweis(n)
    assert "… 18 weitere" in t and "w12" not in t and len(t) < 2000
    assert gespraeche.fehler_hinweis({"text": "normal"}) == ""


def test_wiederholen_ersetzt_den_fehler_eintrag(client, monkeypatch):
    _antwort(monkeypatch, ABBRUCH, ["jetzt klappt's"])
    client.post("/api/chat", json={"message": "stundenplan"}).get_data()
    gid = gespraeche.aktiv()
    client.post("/api/chat/wiederholen", json={"gespraech": gid}).get_data()
    ns = gespraeche.nachrichten(gid)
    assert [(n["rolle"], n["text"], n.get("fehler")) for n in ns] == [
        ("user", "stundenplan", None), ("assistant", "jetzt klappt's", None)]
