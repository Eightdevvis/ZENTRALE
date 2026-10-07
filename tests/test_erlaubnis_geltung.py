"""Geltungsbereiche des Erlaubnis-Gates (2026-10-07, Sasha: „beides
einstellbar machen"): ein Ja gilt einmal, für dieses Gespräch oder immer.

Gefahren im Blick: ein „immer" für etwas, das löscht oder in die Kernakten
schreibt; ein Gesprächs-Ja, das in ein anderes Gespräch hinüberreicht; ein
langer Programm-Lauf, den ein altes „immer" still deckt.
"""
import pytest

import ai_config
import erlaubnis
import ki_werkzeuge  # noqa: F401  — meldet die Ausführer an
import state
import werkzeug_register
import werkzeug_schleife
import zug


@pytest.fixture(autouse=True)
def sauber(monkeypatch):
    """Jeder Test beginnt ohne „immer" und ohne Gesprächs-Ja."""
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    ai_config.set_override("immer_erlaubt", [])
    erlaubnis.gespraech_beginnt("__leer__")
    erlaubnis.gespraech_beginnt(None)
    yield
    ai_config.set_override("immer_erlaubt", None)
    ai_config._config.pop("immer_erlaubt", None)


def _fahren(name, args, antwort, gid="g1"):
    """run_tool im Zug von Gespräch gid; Sasha antwortet `antwort` (None =
    es darf gar nicht gefragt werden). -> (fragen, ausgeführt)"""
    fragen, ausgefuehrt = [], []

    def wait():
        assert antwort is not None, "es wurde gefragt, obwohl schon erlaubt"
        return antwort
    alt = state.wait_permission
    state.wait_permission = wait
    marke = zug.beginnen(gid)
    try:
        gen = werkzeug_schleife.run_tool(
            name, args, tutor_mode=False,
            active_exec=lambda n, a: ausgefuehrt.append(n) or "ok",
            user_query="", store=None)
        try:
            while True:
                ev = next(gen)
                if "permission" in ev:
                    fragen.append(ev["permission"])
        except StopIteration:
            pass
    finally:
        zug.beenden(marke)
        state.wait_permission = alt
    return fragen, ausgefuehrt


TERMIN = {"label": "Zahnarzt", "day": "2026-10-09", "time": "10:00"}


@pytest.fixture(autouse=True)
def kein_kalender(monkeypatch):
    import kalender
    monkeypatch.setattr(kalender, "conflicts_for_proposed", lambda *a, **k: [])


def test_frage_bietet_alle_drei_und_nein():
    fragen, _ = _fahren("add_calendar_entry", TERMIN, "nein")
    f = fragen[0]
    assert f["optionen"] == ["ja, nur dieses mal", "ja, für dieses gespräch",
                             "ja, immer", "nein"]
    assert f["geltung"] == ["einmal", "gespraech", "immer", "nein"]
    assert f["erlaubnis"] is True


def test_einmal_gilt_nur_einmal():
    _, aus = _fahren("add_calendar_entry", TERMIN, "ja, nur dieses mal")
    assert aus == ["add_calendar_entry"]
    fragen, _ = _fahren("add_calendar_entry", TERMIN, "nein")
    assert len(fragen) == 1


def test_altes_ja_ist_einmal():
    _, aus = _fahren("add_calendar_entry", TERMIN, "ja")
    assert aus == ["add_calendar_entry"]
    assert erlaubnis.vorab("add_calendar_entry") is None


def test_nein_fuehrt_nicht_aus():
    _, aus = _fahren("add_calendar_entry", TERMIN, "nein")
    assert aus == []


def test_gespraech_gilt_im_gespraech_und_endet_beim_wechsel():
    erlaubnis.gespraech_beginnt("g1")
    _fahren("web_search", {"query": "x"}, "ja, für dieses gespräch")
    fragen, aus = _fahren("web_search", {"query": "y"}, None)
    assert fragen == [] and aus == ["web_search"]
    # Ein anderes Werkzeug ist davon nicht erfasst.
    fragen, _ = _fahren("fetch_url", {"url": "https://a.b"}, "nein")
    assert len(fragen) == 1
    # Anderes Gespräch: wieder fragen.
    fragen, _ = _fahren("web_search", {"query": "z"}, "nein", gid="g2")
    assert len(fragen) == 1
    # Wechsel hin und zurück hebt auf.
    erlaubnis.gespraech_beginnt("g2")
    erlaubnis.gespraech_beginnt("g1")
    fragen, _ = _fahren("web_search", {"query": "z"}, "nein")
    assert len(fragen) == 1


def test_ohne_gespraech_kein_gespraechs_knopf():
    fragen, _ = _fahren("web_search", {"query": "x"}, "nein", gid=None)
    assert "ja, für dieses gespräch" not in fragen[0]["optionen"]


def test_immer_ueberdauert_gespraechswechsel_und_wird_gespeichert(monkeypatch):
    gespeichert = []
    monkeypatch.setattr(ai_config, "_save", lambda: gespeichert.append(
        list(ai_config._config.get("immer_erlaubt") or [])))
    _fahren("run_code", {"code": "print(1)"}, "ja, immer")
    assert gespeichert[-1] == ["run_code"]
    erlaubnis.gespraech_beginnt("anderes")
    fragen, aus = _fahren("run_code", {"code": "print(2)"}, None, gid="anderes")
    assert fragen == [] and aus == ["run_code"]
    assert erlaubnis.immer_liste() == ["run_code"]


@pytest.mark.parametrize("name,args", [
    ("write_note", {"name": "hausregeln", "text": "kurz"}),
    ("write_note", {"name": "sasha", "text": "mag Tee"}),
    ("delete_calendar_entry", {"label": "x", "day": "2026-10-09"}),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "loeschen"}),
    ("rewrite_note", {"name": "umzug", "content": "neu"}),
    ("edit_skill", {"name": "kurz", "inhalt": "neu"}),
    ("fetch_document", {"url": "https://a.b/x.pdf", "name": "x"}),
    ("save_from_sandbox", {"lauf": "g1--x", "datei": "a.txt"}),
])
def test_kernakten_und_loeschen_ohne_immer(name, args):
    fragen, _ = _fahren(name, args, "nein")
    assert "ja, immer" not in fragen[0]["optionen"]
    assert "ja, für dieses gespräch" in fragen[0]["optionen"]


def test_immer_von_hand_in_der_config_greift_bei_kernakten_nicht():
    """Steht write_note/delete trotzdem in der Liste (von Hand eingetragen),
    wird weiter gefragt — die Regel gilt beim Prüfen, nicht nur beim Anbieten."""
    ai_config.set_override("immer_erlaubt", ["write_note", "delete_calendar_entry"])
    fragen, aus = _fahren("write_note", {"name": "hausregeln", "text": "x"}, "nein")
    assert len(fragen) == 1 and aus == []
    fragen, _ = _fahren("delete_calendar_entry", {"label": "x"}, "nein")
    assert len(fragen) == 1


def test_ein_gefaelschtes_immer_bei_kernakte_wird_nicht_gemerkt():
    _fahren("write_note", {"name": "ziele", "text": "x"}, "ja, immer")
    assert "write_note" not in erlaubnis.immer_liste()


def test_zuruecknehmen_einzeln_und_alle():
    _fahren("run_code", {"code": "1"}, "ja, immer")
    _fahren("web_search", {"query": "q"}, "ja, immer")
    _fahren("fetch_url", {"url": "https://a.b"}, "ja, für dieses gespräch")
    u = erlaubnis.uebersicht()
    assert [e["name"] for e in u["immer"]] == ["run_code", "web_search"]
    assert u["immer"][0]["was"] == "programme abgeschottet ausführen"
    assert [e["name"] for e in u["gespraech"]] == ["fetch_url"]
    assert erlaubnis.zuruecknehmen("web_search") == ["web_search"]
    assert erlaubnis.immer_liste() == ["run_code"]
    fragen, _ = _fahren("web_search", {"query": "q"}, "nein")
    assert len(fragen) == 1
    assert erlaubnis.zuruecknehmen() == ["fetch_url", "run_code"]
    assert erlaubnis.immer_liste() == [] and erlaubnis.gespraech_liste() == []
    assert erlaubnis.zuruecknehmen("run_code") == []


def test_alias_name_trifft_dasselbe_werkzeug():
    _fahren("web_suche", {"query": "q"}, "ja, immer")
    assert erlaubnis.immer_liste() == ["web_search"]
    fragen, _ = _fahren("web_search", {"query": "q"}, None)
    assert fragen == []


# ── run_code länger als 2 Minuten: eigene Frage, nur „einmal" ──────────

def test_langer_lauf_fragt_mit_dauer_und_nur_einmal():
    _fahren("run_code", {"code": "1"}, "ja, immer")
    fragen, aus = _fahren("run_code", {"code": "import time", "zeitlimit": 600},
                          "ja, nur dieses mal")
    assert len(fragen) == 1, "ein altes „immer“ deckt keinen langen Lauf"
    assert fragen[0]["optionen"] == ["ja, nur dieses mal", "nein"]
    assert "bis zu 10 Minuten" in fragen[0]["frage"]
    assert aus == ["run_code"]
    # 120 s gehen weiter mit dem „immer".
    fragen, _ = _fahren("run_code", {"code": "1", "zeitlimit": 120}, None)
    assert fragen == []


def test_langer_lauf_merkt_sich_nichts():
    erlaubnis.merken("run_code", erlaubnis.IMMER, {"zeitlimit": 900})
    assert erlaubnis.immer_liste() == []


def test_run_code_fuehrt_bis_30_minuten_aus(monkeypatch):
    import sandbox
    gesehen = {}

    def falsch(code, sprache, zeitlimit_s, lauf_id=None, abbruch=None):
        gesehen["zeit"] = zeitlimit_s
        return sandbox._ergebnis(rc=0)
    monkeypatch.setattr(sandbox, "ausfuehren", falsch)
    ki_werkzeuge._verteilen("run_code", {"code": "1", "zeitlimit": 600})
    assert gesehen["zeit"] == 600
    ki_werkzeuge._verteilen("run_code", {"code": "1", "zeitlimit": 99999})
    assert gesehen["zeit"] == 1800


def test_jedes_gegatete_werkzeug_hat_alltagswoerter():
    for w in werkzeug_register.WERKZEUGE:
        if w.erlaubnis is not False:
            assert w.alltag, w.name


# ── Route ──────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from ui.app import app
    app.config["TESTING"] = True
    return app.test_client()


def test_route_liste_und_zuruecknehmen(client):
    marke = zug.beginnen("g1")
    try:
        erlaubnis.merken("run_code", erlaubnis.IMMER)
    finally:
        zug.beenden(marke)
    d = client.get("/api/erlaubnis").get_json()
    assert d["immer"] == [{"name": "run_code", "was": "programme abgeschottet ausführen"}]
    assert client.post("/api/erlaubnis/zuruecknehmen", json={}).status_code == 400
    d = client.post("/api/erlaubnis/zuruecknehmen", json={"werkzeug": "run_code"}).get_json()
    assert d["weg"] == ["run_code"] and d["immer"] == []


def test_gespraechswechsel_per_route_hebt_auf(client):
    import gespraeche
    gid = gespraeche.neu("a")
    erlaubnis.gespraech_beginnt(gid)
    marke = zug.beginnen(gid)
    try:
        erlaubnis.merken("web_search", erlaubnis.GESPRAECH)
        assert erlaubnis.vorab("web_search") == erlaubnis.GESPRAECH
    finally:
        zug.beenden(marke)
    andere = gespraeche.neu("b")
    client.post("/api/gespraeche/aktiv", json={"id": andere})
    assert erlaubnis.gespraech_liste() == []


def test_permission_answer_nimmt_alte_und_neue_antworten(client, monkeypatch):
    import ai_backends
    monkeypatch.setattr(ai_backends, "chat_available", lambda: "cloud")
    state.request_permission(options=erlaubnis.optionen("run_code"))
    assert client.post("/api/permission_answer", json={"answer": "ja"}).status_code == 200
    assert state.wait_permission(0.1) == "ja, nur dieses mal"
    state.request_permission(options=erlaubnis.optionen("run_code"))
    assert client.post("/api/permission_answer",
                       json={"answer": "ja, immer"}).status_code == 200
    assert state.wait_permission(0.1) == "ja, immer"
    state.request_permission(options=["Deutsch", "Englisch"])
    assert client.post("/api/permission_answer", json={"answer": "ja"}).status_code == 400
