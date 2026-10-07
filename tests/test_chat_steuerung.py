"""
Steuerung des Chats (Claude-Web-Plan, Phase 1, 2026-10-07): Stoppen bis in
die Werkzeug-Schleife und die Einstellungs-Route hinter den Slash-Befehlen.

Stoppen heißt nicht „Verbindung kappen": der Kern läuft sonst weiter und
bezahlt. Geprüft wird deshalb an jeder Stelle, an der das Signal greifen
muss — vor der Runde, zwischen Werkzeugen, mitten im Anbieter-Strom (alle
drei Dialekte) — und dass das bis dahin Verbrauchte gebucht wird.
"""
import threading
import time
from types import SimpleNamespace

import pytest

import ai
import ai_backends
import ai_config
import cloud
import cloud_openai
import consolidation
import kern
import ki_einstellungen
import providers
import state
import werkzeug_schleife


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    gemerkt = []
    monkeypatch.setattr(consolidation, "zug_vormerken",
                        lambda u, a, store=None: gemerkt.append((u, a)))
    return gemerkt


# ── Fake-Adapter für die Schleife ──────────────────────────────────────

class SkriptAdapter:
    modell = "test"

    def __init__(self, runden):
        self.runden = list(runden)
        self.gefragt = 0

    def runde(self):
        self.gefragt += 1
        r = self.runden.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
        yield  # Generator

    def assistent_anhaengen(self, runde):
        pass

    def ergebnisse_anhaengen(self, ergebnisse):
        pass


def _laufen(adapter, abbruch, exec_=None):
    return list(werkzeug_schleife.laufen(
        adapter, tutor_mode=False, user_query="x", abbruch=abbruch,
        active_exec=exec_ or (lambda n, a: "ok")))


def _calls(*namen):
    return [(f"c{i}", n, {}) for i, n in enumerate(namen)]


def test_abbruch_mitten_in_der_werkzeug_runde_beendet_die_schleife():
    abbruch = threading.Event()
    gelaufen = []

    def exec_(name, args):
        gelaufen.append(name)
        abbruch.set()                    # Sasha drückt Esc, während es läuft
        return "ok"

    a = SkriptAdapter([werkzeug_schleife.Runde("", _calls("read_file", "web_search")),
                       werkzeug_schleife.Runde("nie", [])])
    events = _laufen(a, abbruch, exec_)

    assert gelaufen == ["read_file"], "nach dem Stopp lief noch ein Werkzeug"
    assert a.gefragt == 1, "nach dem Stopp kam noch eine Runde"
    assert events[-1] == {"gestoppt": True}
    assert "nie" not in events


def test_gestoppt_vor_der_ersten_runde_fragt_das_modell_gar_nicht():
    abbruch = threading.Event()
    abbruch.set()
    a = SkriptAdapter([werkzeug_schleife.Runde("x", [])])
    assert _laufen(a, abbruch) == [{"gestoppt": True}]
    assert a.gefragt == 0


def test_gestoppt_im_strom_gibt_den_halben_text_roh_aus(ruhig):
    a = SkriptAdapter([werkzeug_schleife.Gestoppt("Ich wollte gerade")])
    events = _laufen(a, threading.Event())
    assert events == ["Ich wollte gerade", {"gestoppt": True}]
    assert ruhig == [], "ein abgebrochener Zug darf nicht gemerkt werden"


def test_ohne_abbruch_signal_laeuft_alles_wie_bisher():
    a = SkriptAdapter([werkzeug_schleife.Runde("fertig", [])])
    assert "fertig" in _laufen(a, None)


# ── Die drei Anbieter-Ströme ───────────────────────────────────────────

class _AnthStrom:
    """Anthropic-Strom: message_start (Eingabe bezahlt), Text, dann löst der
    Test mitten drin das Stoppen aus."""

    def __init__(self, abbruch):
        self.abbruch, self.zu = abbruch, False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.zu = True
        return False

    def __iter__(self):
        u = SimpleNamespace(input_tokens=1200, output_tokens=1,
                            cache_read_input_tokens=300,
                            cache_creation_input_tokens=0)
        yield SimpleNamespace(type="message_start",
                              message=SimpleNamespace(usage=u))
        yield SimpleNamespace(type="content_block_delta",
                              delta=SimpleNamespace(type="text_delta", text="Hal"))
        self.abbruch.set()
        yield SimpleNamespace(type="content_block_delta",
                              delta=SimpleNamespace(type="text_delta", text="lo"))
        raise AssertionError("Strom wurde nach dem Stopp weitergelesen")

    def get_final_message(self):
        raise AssertionError("final gibt es nach einem Stopp nicht")


def test_anthropic_strom_bricht_ab_schliesst_und_bucht(monkeypatch):
    import usage
    gebucht = []
    monkeypatch.setattr(usage, "buchen",
                        lambda m, **k: gebucht.append((m, k)) or 0.0)
    abbruch = threading.Event()
    strom = _AnthStrom(abbruch)
    client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **k: strom))
    a = cloud._AnthropicAdapter(client, "claude-sonnet-5", [], [], [],
                                abbruch=abbruch)
    with pytest.raises(werkzeug_schleife.Gestoppt) as e:
        list(a.runde())
    assert e.value.text == "Hal"
    assert strom.zu, "der Anthropic-Strom blieb offen"
    assert gebucht and gebucht[0][1]["input_tokens"] == 1200
    assert gebucht[0][1]["cache_read"] == 300


def test_openai_strom_bricht_ab_und_schliesst():
    abbruch = threading.Event()

    class Strom:
        zu = False

        def __iter__(self):
            d = SimpleNamespace(content="Te", tool_calls=None, reasoning_content=None)
            yield SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=d)])
            abbruch.set()
            yield SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=d)])
            raise AssertionError("weitergelesen")

        def close(self):
            Strom.zu = True

    client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **k: Strom())))
    a = cloud_openai._OpenAIAdapter(client, "qwen-plus",
                                    [{"role": "system", "content": "s"}], [],
                                    abbruch=abbruch)
    with pytest.raises(werkzeug_schleife.Gestoppt) as e:
        list(a.runde())
    assert e.value.text == "Te"
    assert Strom.zu


def test_ollama_strom_bricht_ab_und_schliesst(monkeypatch):
    abbruch = threading.Event()
    zu = []

    def stream_post(url, payload):
        try:
            yield {"message": {"content": "lo"}}
            abbruch.set()
            yield {"message": {"content": "kal"}}
            raise AssertionError("weitergelesen")
        finally:
            zu.append(True)

    monkeypatch.setattr(ai.net, "stream_post", stream_post)
    a = ai._OllamaAdapter("qwen", [], [], False, abbruch=abbruch)
    with pytest.raises(werkzeug_schleife.Gestoppt) as e:
        list(a.runde())
    assert e.value.text == "lo"
    assert zu == [True]


def test_kern_reicht_das_signal_bis_zum_weg_durch(monkeypatch):
    gesehen = {}

    def chat_stream(verlauf, **k):
        gesehen.update(k)
        yield "x"

    monkeypatch.setattr(ai, "chat_stream", chat_stream)
    ev = threading.Event()
    list(kern.chat([], backend=ai_backends.LOCAL, abbruch=ev))
    assert gesehen["abbruch"] is ev


# ── Route: /api/chat und /api/chat/stop ────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    state.clear_chat_history()
    yield app.test_client()
    state.clear_chat_history()


def _modul(monkeypatch, gen):
    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)


def test_erstes_event_ist_die_strom_nummer(client, monkeypatch):
    _modul(monkeypatch, lambda h, **k: iter(["hi"]))
    body = client.post("/api/chat", json={"message": "x"}).get_data(as_text=True)
    assert body.startswith('data: {"strom": "z')


def test_gestoppter_text_bleibt_mit_vermerk_im_verlauf(client, monkeypatch):
    def gen(h, abbruch=None, **k):
        yield "Die Antwort fing so an"
        state.chat_zug_stoppen()          # wie POST /api/chat/stop aus der TUI
        assert werkzeug_schleife.gestoppt(abbruch)
        yield {"gestoppt": True}

    _modul(monkeypatch, gen)
    body = client.post("/api/chat", json={"message": "x"}).get_data(as_text=True)
    assert '"gestoppt": true' in body
    assert state.get_chat_history()[-1] == {
        "role": "assistant", "content": "Die Antwort fing so an\n\n(abgebrochen)"}


def test_gestoppt_ohne_text_landet_nicht_im_verlauf(client, monkeypatch):
    _modul(monkeypatch, lambda h, **k: iter([{"gestoppt": True}]))
    client.post("/api/chat", json={"message": "x"}).get_data()
    assert [m["role"] for m in state.get_chat_history()] == ["user"]


def test_zug_ist_nach_dem_strom_abgemeldet(client, monkeypatch):
    _modul(monkeypatch, lambda h, **k: iter(["hi"]))
    client.post("/api/chat", json={"message": "x"}).get_data()
    assert client.post("/api/chat/stop", json={}).get_json()["gestoppt"] is False


def test_stop_route_trifft_den_genannten_zug(client):
    sid, ev = state.chat_zug_beginnen()
    try:
        r = client.post("/api/chat/stop", json={"strom": "gibts-nicht"})
        assert r.status_code == 200 and r.get_json()["gestoppt"] is False
        assert not ev.is_set()
        r = client.post("/api/chat/stop", json={"strom": sid})
        assert r.get_json()["gestoppt"] is True and ev.is_set()
    finally:
        state.chat_zug_beenden(sid)


def test_stop_ohne_nummer_und_ohne_body(client):
    sid, ev = state.chat_zug_beginnen()
    try:
        r = client.post("/api/chat/stop")
        assert r.status_code == 200 and r.get_json()["gestoppt"] is True
        assert ev.is_set()
    finally:
        state.chat_zug_beenden(sid)


def test_stoppen_beendet_eine_offene_erlaubnis_frage():
    sid, _ev = state.chat_zug_beginnen()
    state.request_permission()
    raus = {}
    t = threading.Thread(target=lambda: raus.update(w=state.wait_permission(5)))
    t.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    state.chat_zug_stoppen(sid)
    t.join(2)
    state.chat_zug_beenden(sid)
    assert raus.get("w") == "nein"
    assert time.monotonic() - t0 < 1


# ── Einstellungen ──────────────────────────────────────────────────────

@pytest.fixture
def einst(monkeypatch, tmp_path):
    """ai_config komplett in ein Wegwerf-Verzeichnis: die Setter schreiben
    mit persist=True, und das darf nie Sashas data/ai_config.json sein."""
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(tmp_path / "ai_config.json"))
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_legacy", {})
    monkeypatch.setattr(ai_config, "_overrides", {})
    for p in providers.PROVIDERS.values():
        monkeypatch.delenv(p["key_env"], raising=False)
    for name in ("CHAT_PROVIDER", "CHAT_EFFORT", "CHAT_BACKEND",
                 "BUDGET_MONAT_EURO", "CHAT_MODELS"):
        monkeypatch.delenv("ZENTRALE_" + name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "geheim-123")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "geheim-456")
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def test_einstellungen_lesen(einst):
    d = einst.get("/api/ai/einstellungen").get_json()
    assert d["anbieter"] == "auto" and d["anbieter_aktiv"] == "claude"
    assert d["effort"] == "low" and "max" in d["effort_stufen"]
    mit_key = {a["name"] for a in d["anbieter_liste"] if a["schluessel"]}
    assert mit_key == {"claude", "qwen"}
    qwen = next(a for a in d["anbieter_liste"] if a["name"] == "qwen")
    assert qwen["modelle"] == ["qwen-plus", "qwen-turbo"]
    assert "geheim" not in str(d), "ein Schlüssel ist in der Antwort gelandet"


def test_effort_setzen_und_unsinn(einst, tmp_path):
    r = einst.post("/api/ai/einstellungen", json={"effort": "High"})
    assert r.status_code == 200 and r.get_json()["effort"] == "high"
    assert "high" in (tmp_path / "ai_config.json").read_text()
    r = einst.post("/api/ai/einstellungen", json={"effort": "turbo"})
    assert r.status_code == 400 and "Stufen" in r.get_json()["error"]
    assert ai_backends.chat_effort() == "high"


def test_anbieter_ohne_schluessel_wird_abgelehnt(einst):
    r = einst.post("/api/ai/einstellungen", json={"anbieter": "grok"})
    assert r.status_code == 400 and "Schlüssel" in r.get_json()["error"]
    r = einst.post("/api/ai/einstellungen", json={"anbieter": "quatsch"})
    assert r.status_code == 400 and "kenne ich nicht" in r.get_json()["error"]
    assert ai_backends.chat_provider() == "auto"
    r = einst.post("/api/ai/einstellungen", json={"anbieter": "qwen"})
    assert r.get_json()["anbieter_aktiv"] == "qwen"


def test_modell_eines_anderen_anbieters_wechselt_den_anbieter(einst):
    r = einst.post("/api/ai/einstellungen", json={"modell": "qwen-turbo"})
    d = r.get_json()
    assert d["anbieter_aktiv"] == "qwen" and d["modell"] == "qwen-turbo"
    # Freier Name, der nirgends steht → beim aktuellen Anbieter
    d = einst.post("/api/ai/einstellungen", json={"modell": "qwen-max"}).get_json()
    assert d["anbieter_aktiv"] == "qwen" and d["modell"] == "qwen-max"
    # ausdrücklich mit Anbieter
    d = einst.post("/api/ai/einstellungen",
                   json={"anbieter": "claude", "modell": "claude-opus-5"}).get_json()
    assert d["anbieter_aktiv"] == "claude" and d["modell"] == "claude-opus-5"
    r = einst.post("/api/ai/einstellungen", json={"modell": "zwei worte"})
    assert r.status_code == 400


def test_budget(einst):
    assert einst.post("/api/ai/einstellungen",
                      json={"budget": "12,50"}).get_json()["budget"] == 12.5
    assert einst.post("/api/ai/einstellungen",
                      json={"budget": "aus"}).get_json()["budget"] is None
    for unsinn in ("-3", "0", "viel", 999999, True):
        r = einst.post("/api/ai/einstellungen", json={"budget": unsinn})
        assert r.status_code == 400, unsinn
    assert ai_backends.budget_monat() is None


def test_weg(einst):
    assert einst.post("/api/ai/einstellungen",
                      json={"weg": "lokal"}).get_json()["weg"] == "local"
    assert einst.post("/api/ai/einstellungen",
                      json={"weg": "auto"}).get_json()["weg"] == "auto"
    assert einst.post("/api/ai/einstellungen", json={"weg": "mond"}).status_code == 400


def test_unsinn_in_einem_feld_setzt_gar_nichts(einst):
    r = einst.post("/api/ai/einstellungen",
                   json={"effort": "max", "budget": "viel"})
    assert r.status_code == 400
    assert ai_backends.chat_effort() == "low"


def test_leerer_oder_kaputter_body(einst):
    assert einst.post("/api/ai/einstellungen", json={}).status_code == 400
    assert einst.post("/api/ai/einstellungen", data="kein json",
                      content_type="application/json").status_code == 400


def test_budget_lesen_rein():
    assert ki_einstellungen.budget_lesen("20 €") == 20.0
    assert ki_einstellungen.budget_lesen("") is None
    with pytest.raises(ki_einstellungen.Ungueltig):
        ki_einstellungen.budget_lesen("nan")
