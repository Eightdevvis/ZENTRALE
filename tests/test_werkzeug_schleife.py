"""
Die EINE Werkzeug-Schleife (core/werkzeug_schleife.py) — hier vor allem vom
lokalen Weg aus gesehen, den bis 10/2026 kein einziger Test abdeckte.

Ollama wird über ein Runden-Skript gefälscht: jede Runde ist eine Liste von
Stream-Chunks, wie net.stream_post sie liefern würde. Geprüft wird, dass der
lokale Weg jetzt dasselbe kann wie die Cloud: werkzeug-Events, ein
krachendes Tool reißt den Zug nicht ab, Fehler und Rundengrenze kommen als
fehler-Event statt als Antworttext. Dazu, dass app.py ein fehler-Event NICHT
in den Verlauf schreibt.
"""
import pytest

import ai
import ai_backends
import state
import werkzeug_schleife


# ── Ollama-Fake ────────────────────────────────────────────────────────

def _text(t):
    return [{"message": {"content": t}}, {"done": True, "message": {}}]


def _tool(name, args):
    return [{"message": {"content": "", "tool_calls": [
        {"function": {"name": name, "arguments": args}}]}},
        {"done": True, "message": {}}]


@pytest.fixture
def ollama(monkeypatch):
    """Runden-Skript einhängen; die gesendeten Payloads werden mitgeschrieben."""
    gesendet = []

    def bauen(runden):
        runden = list(runden)

        def stream_post(url, payload):
            # Kopie: die Schleife haengt danach an dieselbe Liste an.
            gesendet.append({**payload, "messages": list(payload["messages"])})
            yield from runden.pop(0)

        monkeypatch.setattr(ai.net, "stream_post", stream_post)
        return gesendet

    return bauen


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    """Alles abklemmen, was beim Prompt-Bau oder Speichern echte Daten anfasst."""
    gespeichert = []
    monkeypatch.setattr(ai, "_ensure_seed_once", lambda *a, **k: None)
    monkeypatch.setattr(ai, "_imprint_prompt", lambda: "")
    monkeypatch.setattr(ai, "_alarm_prompt", lambda: "")
    monkeypatch.setattr(ai, "_should_think", lambda m: False)
    monkeypatch.setattr(ai, "_async_save_turn",
                        lambda u, a, store=None: gespeichert.append((u, a)))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    return gespeichert


def _msgs(text="was steht an?"):
    return [{"role": "user", "content": text}]


def _texte(events):
    return [e for e in events if isinstance(e, str)]


def _art(events, schluessel):
    return [e[schluessel] for e in events
            if isinstance(e, dict) and schluessel in e]


# ── Lokal: dasselbe wie die Cloud ─────────────────────────────────────

def test_lokal_einfache_antwort(ollama, ruhig):
    ollama([_text("Nichts Besonderes.")])
    events = list(ai.chat_stream(_msgs()))
    assert _texte(events) == ["Nichts Besonderes."]
    assert ruhig == [("was steht an?", "Nichts Besonderes.")]


def test_lokal_meldet_werkzeuge_wie_die_cloud(ollama):
    gesendet = ollama([_tool("read_calendar", {}), _text("Zahnarzt um 3.")])
    events = list(ai.chat_stream(_msgs(),
                                 tools=None,
                                 tool_executor=lambda n, a: "15:00 Zahnarzt"))
    phasen = [w["phase"] for w in _art(events, "werkzeug")]
    assert phasen == ["start", "fertig"]
    assert _texte(events) == ["Zahnarzt um 3."]
    # Runde 2 sieht den Assistant-Zug mit tool_calls und das Ergebnis.
    zweite = gesendet[1]["messages"]
    assert zweite[-2]["role"] == "assistant" and zweite[-2]["tool_calls"]
    assert zweite[-1] == {"role": "tool", "content": "15:00 Zahnarzt"}


def test_lokal_krachendes_tool_reisst_den_zug_nicht_ab(ollama):
    gesendet = ollama([_tool("read_file", '{"path": "/weg"}'),
                       _text("Die Datei gibt es nicht.")])

    def kaputt(n, a):
        raise FileNotFoundError("/weg")

    events = list(ai.chat_stream(_msgs(), tool_executor=kaputt))
    assert _texte(events) == ["Die Datei gibt es nicht."]
    assert [w["phase"] for w in _art(events, "werkzeug")] == ["start", "fehler"]
    assert "fehlgeschlagen" in gesendet[1]["messages"][-1]["content"]


def test_lokal_think_aus_nach_dem_ersten_tool(ollama, monkeypatch):
    """qwen3.5-Template-Bug: die Synthese-Runde mit think kippt die Antwort
    ins thinking-Feld. Das muss der Adapter weiter abfangen."""
    monkeypatch.setattr(ai, "_should_think", lambda m: True)
    monkeypatch.setattr(ai, "ADAPTIVE_THINK", True)
    monkeypatch.setattr(ai, "SUPPORTS_THINK", True)
    gesendet = ollama([_tool("read_calendar", {}), _text("ok")])
    list(ai.chat_stream(_msgs(), tool_executor=lambda n, a: "x"))
    assert gesendet[0]["think"] is True
    assert gesendet[1]["think"] is False


def test_lokal_rundengrenze_ist_ein_fehler_event(ollama):
    ollama([_tool("read_calendar", {})] * ai_backends.STANDARD_RUNDEN)
    events = list(ai.chat_stream(_msgs(), tool_executor=lambda n, a: "x"))
    assert _texte(events) == []
    fehler = _art(events, "fehler")
    assert len(fehler) == 1 and "Tool-Tiefe" in fehler[0]


def test_grenze_haengt_am_modell_nicht_am_weg(ollama, monkeypatch):
    """Sasha, 05.10.2026: eine Regel für alle, Standard 8; ein kleines Modell
    bekommt per Config weniger."""
    import ai_config
    monkeypatch.setattr(ai_config, "setting",
                        lambda n, d=None: {"qwen3.5:9b": 5, "kaputt": "x"}
                        if n == "runden_grenzen" else d)
    assert ai_backends.runden_grenze("qwen3.5:9b") == 5
    assert ai_backends.runden_grenze("claude-sonnet-5") == 8
    assert ai_backends.runden_grenze("kaputt") == 8
    assert ai_backends.runden_grenze(None) == 8

    gesendet = ollama([_tool("read_calendar", {})] * 5)
    events = list(ai.chat_stream(_msgs(), model="qwen3.5:9b",
                                 tool_executor=lambda n, a: "x"))
    assert len(gesendet) == 5
    assert "5 Runden" in _art(events, "fehler")[0]


def test_lokal_ollama_weg_ist_ein_fehler_event(monkeypatch):
    def tot(url, payload):
        raise ConnectionError("Ollama antwortet nicht")
        yield  # pragma: no cover

    monkeypatch.setattr(ai.net, "stream_post", tot)
    events = list(ai.chat_stream(_msgs()))
    assert events == [{"fehler": "Ollama-Fehler: Ollama antwortet nicht"}]


def test_lokal_tutor_bleibt_ohne_gate_und_roh(ollama, ruhig):
    """Fremdes Tool-Set (Tutor): kein Gate, keine Bild-Marker, kein Auto-Save."""
    ollama([_tool("add_calendar_entry", {}), _text("[[bild: x]] hallo")])
    ausgefuehrt = []
    events = list(ai.chat_stream(
        _msgs(), system="TUTOR", tools=[{"type": "function"}],
        tool_executor=lambda n, a: ausgefuehrt.append(n) or "ok"))
    assert ausgefuehrt == ["add_calendar_entry"]           # nicht gegatet
    assert not _art(events, "permission")
    assert _texte(events) == ["[[bild: x]] hallo"]          # roh
    assert ruhig == []                                      # nichts gespeichert


def test_ablehnung_mit_richtigstellung(ollama, monkeypatch):
    monkeypatch.setattr(state, "request_permission", lambda **k: None)
    monkeypatch.setattr(state, "wait_permission", lambda: "nein")
    gesendet = ollama([_tool("add_calendar_entry", {"label": "x"}),
                       _text("Lasse ich.")])
    list(ai.chat_stream(_msgs(), tool_executor=lambda n, a: "ok"))
    zurueck = gesendet[1]["messages"][-1]["content"]
    assert "abgelehnt" in zurueck and "Richtigstellung" in zurueck


# ── Die Schleife selbst ───────────────────────────────────────────────

class _Adapter:
    modell = "test"

    def __init__(self, runden):
        self.runden = list(runden)
        self.verlauf = []

    def runde(self):
        r = self.runden.pop(0)
        if isinstance(r, Exception):
            raise r
        yield {"reflect": "hm"}
        return r

    def assistent_anhaengen(self, runde):
        self.verlauf.append(("assistent", runde.text))

    def ergebnisse_anhaengen(self, ergebnisse):
        self.verlauf.append(("ergebnisse", ergebnisse))


def test_abbruch_geht_woertlich_raus():
    a = _Adapter([werkzeug_schleife.Abbruch("Abgelehnt.")])
    events = list(werkzeug_schleife.laufen(
        a, tutor_mode=True, active_exec=None, user_query=""))
    assert events == [{"fehler": "Abgelehnt."}]


def test_terminales_tool_beendet_den_zug(monkeypatch):
    monkeypatch.setattr(ai, "_async_save_turn", lambda *a, **k: None)
    a = _Adapter([werkzeug_schleife.Runde("", [("c1", "antwort", {"text": "Fertig."})]),
                  werkzeug_schleife.Runde("nie", [])])
    events = list(werkzeug_schleife.laufen(
        a, tutor_mode=False, active_exec=None, user_query=""))
    assert _texte(events) == ["Fertig."]
    assert len(a.runden) == 1          # zweite Runde nie gefragt


def test_ergebnisse_kommen_mit_call_id_zurueck():
    a = _Adapter([werkzeug_schleife.Runde("", [("c1", "x", {}), ("c2", "y", {})]),
                  werkzeug_schleife.Runde("ok", [])])
    list(werkzeug_schleife.laufen(
        a, tutor_mode=True, active_exec=lambda n, a: n.upper(), user_query=""))
    assert a.verlauf[1] == ("ergebnisse", [("c1", "X", False), ("c2", "Y", False)])


# ── app.py: fehler geht an Sasha, nicht in den Verlauf ────────────────

def test_fehler_landet_nicht_im_verlauf(monkeypatch):
    import ai_backends
    from ui.app import app

    class Modul:
        @staticmethod
        def chat_stream(history, **k):
            yield {"fehler": "Cloud-Fehler: kein Netz"}

    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "chat_cloud_module", lambda: Modul)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    state.clear_chat_history()

    app.config.update(TESTING=True)
    r = app.test_client().post("/api/chat", json={"message": "hallo"})
    body = r.get_data(as_text=True)

    assert '"fehler": "Cloud-Fehler: kein Netz"' in body
    assert '"token"' not in body
    verlauf = state.get_chat_history()
    assert [m["role"] for m in verlauf] == ["user"]
    state.clear_chat_history()
