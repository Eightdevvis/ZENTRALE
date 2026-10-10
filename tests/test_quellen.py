"""
Die Quellen-Zeile (2026-10-10, core/quellen.py): Python zieht aus den
Werkzeug-Ergebnissen eines Zugs, welche Seiten wirklich GELESEN wurden —
die KI muss keine Adresse mehr abschreiben (Prüfstand 10.10., f08: Zeiten
richtig, Adresse fehlte). web_search zählt nie: Treffer sind Hinweise.

Gefälschte Modelle, kein echter Aufruf, kein Netz.
"""
import json

import pytest

import ai_backends
import ai_config
import cloud
import consolidation
import erlaubnis
import gespraeche
import kern
import ki_browser
import ki_prompt
import net
import quellen
import web
import werkzeug_schleife
import zug_ablauf
from werkzeug_befund import mit_kopf

R = werkzeug_schleife.Runde
SERVER = "http://127.0.0.1:42987"


def _seite(pfad, titel, text="Text " * 80):
    return mit_kopf(ki_browser._gelesen({
        "url": SERVER + pfad, "host": "127.0.0.1", "titel": titel, "text": text,
        "elemente": [], "rahmen_fremd": 0}))


SUCHE = mit_kopf("Treffer = Hinweise, NICHT gelesen.\nWeb-Suche 'x' - 1 Treffer:\n"
                 "1. Ferien Saarland\n   https://www.ferien.example/saarland\n   …")


# ── Was zählt ──────────────────────────────────────────────────────────

def test_f08_nur_die_seite_auf_der_sie_stehen_blieb():
    """Der Weg vom 10.10.: Start → Suche → zurück → Fakultät → Analysis I.
    Start und Suche waren Durchgang — in der Zeile steht nur Analysis I."""
    schritte = [
        ("browser_open", {"url": SERVER + "/"}, _seite("/", "Vorlesungsverzeichnis"), False),
        ("browser_click", {"nr": 3}, _seite("/suche", "Suche"), False),
        ("browser_back", {}, _seite("/", "Vorlesungsverzeichnis"), False),
        ("browser_click", {"nr": 1}, _seite("/", "Vorlesungsverzeichnis"), False),
        ("browser_click", {"nr": 2}, _seite("/veranstaltung?id=4711", "Analysis I"), False),
    ]
    assert quellen.aus_schritten(schritte) == [
        {"titel": "Analysis I", "url": SERVER + "/veranstaltung?id=4711",
         "werkzeug": "browser_click"}]


def test_websuche_zaehlt_nie_und_fehler_auch_nicht():
    schritte = [
        ("web_search", {"query": "ferien"}, SUCHE, False),
        ("fetch_url", {"url": "https://www.ferien.example/saarland"},
         mit_kopf("[Fehler beim Laden von https://www.ferien.example/saarland: "
                  "Verbindung fehlgeschlagen]"), False),
        ("browser_open", {"url": "https://lsf.example/"},
         mit_kopf(ki_browser._fehler("Seite im Browser öffnen", ki_browser.BrowserFehler(
             "B-LADEN", "https://lsf.example/ nicht erreichbar"))), False),
    ]
    assert quellen.aus_schritten(schritte) == []
    assert quellen.zeile([]) == ""


def test_fetch_url_mit_titel_aus_der_seite(monkeypatch):
    monkeypatch.setattr(net, "get", lambda url, **k: (
        "<html><head><title>Ferien Saarland 2026</title></head><body><p>"
        + "Herbstferien vom 12.10. bis 23.10.2026. " * 20 + "</p></body></html>").encode())
    text = mit_kopf(web.hole("www.saarland.example/ferien"))
    assert "Titel: „Ferien Saarland 2026“" in text
    q = quellen.aus_schritten([("fetch_url", {"url": "www.saarland.example/ferien"},
                                text, False)])
    assert q == [{"titel": "Ferien Saarland 2026", "url": "https://www.saarland.example/ferien",
                  "werkzeug": "fetch_url"}]
    assert quellen.zeile(q) == ("Quellen: „Ferien Saarland 2026“ – "
                                "https://www.saarland.example/ferien")


def test_fetch_document_nur_aus_dem_netz():
    ok = mit_kopf("Dokument „Modulhandbuch“ ABGELEGT in quellen/modulhandbuch: 900 Zeichen.")
    q = quellen.aus_schritten([
        ("fetch_document", {"url": "https://uni.example/mhb.pdf", "name": "Modulhandbuch"}, ok, False),
        ("fetch_document", {"url": "Input/plan.pdf", "name": "Plan"}, ok, False)])
    assert q == [{"titel": "Modulhandbuch", "url": "https://uni.example/mhb.pdf",
                  "werkzeug": "fetch_document"}]


def test_neues_oeffnen_und_lesen_zaehlen_doppelte_nicht():
    schritte = [
        ("browser_open", {}, _seite("/a", "A"), False),
        ("browser_read", {"ab": 4000}, mit_kopf(f"Adresse: {SERVER}/a\n── Text ──\n…"), False),
        ("browser_click", {"nr": 1}, _seite("/b", "B"), False),     # A gelesen, dann weiter
        ("browser_open", {}, _seite("/c", "C"), False),              # B war Endpunkt
        ("browser_type", {"nr": 1, "text": "x"}, mit_kopf("In [1] „Titel“ steht jetzt: „x“."), False),
        ("browser_open", {}, _seite("/c#oben", "C"), False),         # dieselbe Seite
    ]
    q = quellen.aus_schritten(schritte)
    assert [(x["titel"], x["url"].rsplit("/", 1)[1], x["werkzeug"]) for x in q] == [
        ("A", "a", "browser_read"), ("B", "b", "browser_click"), ("C", "c", "browser_open")]


def test_hoechstens_sechs():
    schritte = [("fetch_url", {"url": f"https://s{i}.example/"},
                 mit_kopf(f"Inhalt von https://s{i}.example/:\nText"), False) for i in range(9)]
    q = quellen.aus_schritten(schritte)
    assert len(q) == quellen.MAX == 6 and q[0]["titel"] == "s0.example"


# ── Durch die Schleife, die Route und die TUI ──────────────────────────

class _Skript:
    modell = "test"

    def __init__(self, runden):
        self.runden = list(runden)

    def runde(self):
        if False:
            yield
        return self.runden.pop(0)

    def assistent_anhaengen(self, r):
        pass

    def ergebnisse_anhaengen(self, e):
        pass


ERGEBNISSE = {
    "web_search": "Treffer = Hinweise, NICHT gelesen.\n1. LSF\n   " + SERVER + "/\n   …",
    "browser_open": ki_browser._gelesen({"url": SERVER + "/", "host": "127.0.0.1",
                                         "titel": "Vorlesungsverzeichnis", "text": "x " * 80,
                                         "elemente": [], "rahmen_fremd": 0}),
    "browser_click": ki_browser._gelesen({"url": SERVER + "/veranstaltung?id=4711",
                                          "host": "127.0.0.1", "titel": "Analysis I",
                                          "text": "Mo 10:00–12:00 " * 10, "elemente": [],
                                          "rahmen_fremd": 0}),
}
RUNDEN = [R("", [("c1", "web_search", {"query": "lsf"})]),
          R("", [("c2", "browser_open", {"url": SERVER + "/"})]),
          R("", [("c3", "browser_click", {"nr": 2})]),
          R("Analysis I ist Mo 10–12.")]


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: False)
    monkeypatch.setattr(ai_config, "_overrides", {})


def test_schleife_meldet_quellen_nur_auf_gross():
    exec_ = lambda n, a: ERGEBNISSE[n]           # noqa: E731
    ev = list(werkzeug_schleife.laufen(_Skript(RUNDEN), tutor_mode=False, active_exec=exec_,
                                       user_query="x", schiene="gross"))
    q = [e["quellen"] for e in ev if isinstance(e, dict) and "quellen" in e]
    assert q == [[{"titel": "Analysis I", "url": SERVER + "/veranstaltung?id=4711",
                   "werkzeug": "browser_click"}]]
    klein = list(werkzeug_schleife.laufen(_Skript(RUNDEN), tutor_mode=False, active_exec=exec_,
                                          user_query="x", schiene="klein"))
    assert not any(isinstance(e, dict) and "quellen" in e for e in klein)


def test_route_speichert_sendet_und_protokolliert(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    monkeypatch.setattr(ai_backends, "modell_wechsel", lambda: None)

    def gen(history, **k):
        zug_ablauf.system("fester Kopf")         # macht das Ablauf-Protokoll scharf
        yield from werkzeug_schleife.laufen(
            _Skript(RUNDEN), tutor_mode=False, user_query="x", schiene="gross",
            active_exec=lambda n, a: ERGEBNISSE[n])

    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    monkeypatch.setattr(cloud, "_profil", lambda: __import__("profil").gross)
    monkeypatch.setattr(ki_prompt, "_alarm_prompt", lambda: "")
    client = app.test_client()
    r = client.post("/api/chat", json={"message": "wann ist analysis I?"})
    ev = [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
          if z.startswith("data:")]
    gesendet = next(e["quellen"] for e in ev if "quellen" in e)
    assert [x["url"] for x in gesendet] == [SERVER + "/veranstaltung?id=4711"]
    gid = gespraeche.aktiv()
    antwort = gespraeche.nachrichten(gid)[-1]
    assert antwort["quellen"] == gesendet
    assert SERVER not in antwort["text"]                 # nie im Text der KI
    h = client.get("/api/chat/history").get_json()[-1]
    assert h["quellen"] == gesendet
    ablauf = gespraeche.ablauf(gid, antwort["id"])
    eintrag = next(e for e in ablauf if e["art"] == "quellen")
    assert zug_ablauf.kopfzeile(eintrag) == "Quellen · 1 gelesene Seite(n)"
    assert "veranstaltung?id=4711 (browser_click)" in zug_ablauf.inhalt(eintrag)

    # TUI: dezent unter der Antwort, vor der Erledigt-Zeile.
    from tui.ansichten.chat_gespraeche import verlauf_aus
    from tui.ansichten import spur, verlauf
    log = verlauf_aus([h])
    i_ai = max(i for i, (rolle, _t) in enumerate(log) if rolle == "ai")
    assert log[i_ai + 1] == ("quellen", f"Quellen: „Analysis I“ – {SERVER}/veranstaltung?id=4711")
    stile = {s for z in verlauf.verlauf_zeilen(log, 60) for t, s, _z in z
             if t.startswith("Quellen")}
    assert stile == {"leise"}
    assert spur.kopf(eintrag) == "sources: 1 page(s) read"


def test_tui_strom_zeigt_quellen_unter_der_antwort(monkeypatch):
    from types import SimpleNamespace
    from test_chat_strom import _laufen as strom_laufen, _Schirm
    from tui.ansichten import chat, chat_gespraeche, chat_strom
    ch = chat.Chat(SimpleNamespace(stdscr=_Schirm(), C={}))
    ch.AI.update(active=True, gid="a", titel="t", loaded=True, log=[("user", "alt")])
    ch.verlauf_laden = lambda gid=None: None
    monkeypatch.setattr(chat_gespraeche, "api_call", lambda *a, **k: {})
    monkeypatch.setattr(chat_strom, "api_call", lambda *a, **k: {})
    strom_laufen(ch, monkeypatch, [
        {"strom": "z1"}, {"gespraech": "a", "nachricht": "n1"},
        {"token": "Mo 10–12."},
        {"quellen": [{"titel": "Analysis I", "url": SERVER + "/v", "werkzeug": "browser_click"}]},
        {"done": True}])
    log = ch.AI["log"]
    i = log.index(("ai", "Mo 10–12."))
    assert log[i + 1] == ("quellen", f"Quellen: „Analysis I“ – {SERVER}/v")
    assert "quellen" not in ch.AI
