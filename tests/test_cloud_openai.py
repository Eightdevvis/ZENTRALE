"""
core/cloud_openai.py — der OpenAI-kompatible Kern-Pfad (Qwen/DashScope & Co).

Gleiche Bauart wie test_cloud_loop.py: ein gefälschter Client skriptet die
Antworten, der ECHTE chat_stream() läuft dagegen. Wichtigster Punkt hier ist
nicht die Funktion an sich, sondern dass BEIDE Cloud-Dialekte sich gleich
verhalten — Event-Protokoll, Gate, terminale Tools, Puffern des Tool-
Geschwätzes. Wo sie auseinanderlaufen, ist die gemeinsame Naht keine.
"""
import pytest

import ai
import cloud
import cloud_openai


# ── Fake-OpenAI ────────────────────────────────────────────────────────

class FakeFn:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = FakeFn(name, arguments)


class FakeDelta:
    def __init__(self, content=None, tool_calls=None, reasoning_content=None):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content


class FakeChoice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class FakeChunk:
    def __init__(self, delta, finish_reason=None):
        self.choices = [FakeChoice(delta, finish_reason)]


class FakeCompletions:
    def __init__(self, runden, calls):
        self._runden = list(runden)
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        if not self._runden:
            raise AssertionError("mehr Runden angefragt als skriptet")
        return iter(self._runden.pop(0))


class FakeClient:
    def __init__(self, runden):
        self.calls = []
        self.chat = type("C", (), {"completions": FakeCompletions(runden, self.calls)})()


@pytest.fixture
def fake(monkeypatch):
    def bauen(runden):
        c = FakeClient(runden)
        monkeypatch.setattr(cloud_openai, "_get_client", lambda prov: c)
        monkeypatch.setattr(cloud_openai, "_provider",
                            lambda name=None: {"kind": "openai_compat",
                                               "base_url": "http://test",
                                               "key_env": "X",
                                               "default_model": "qwen-plus"})
        return c
    return bauen


@pytest.fixture(autouse=True)
def kein_echter_graph(monkeypatch):
    gespeichert = []
    monkeypatch.setattr(cloud_openai.graph, "context_for_query",
                        lambda *a, **k: "## Erinnerung\n(test)")
    monkeypatch.setattr(ai, "_ensure_seed_once", lambda *a, **k: None)
    monkeypatch.setattr(ai, "_async_save_turn",
                        lambda u, a, store=None: gespeichert.append((u, a, store)))
    return gespeichert


def _text(*stuecke, finish="stop"):
    chunks = [FakeChunk(FakeDelta(content=s)) for s in stuecke]
    chunks.append(FakeChunk(FakeDelta(), finish_reason=finish))
    return chunks


def _tool(name, args_json, id="call_1", index=0):
    return [
        FakeChunk(FakeDelta(tool_calls=[FakeToolCall(index, id=id, name=name)])),
        FakeChunk(FakeDelta(tool_calls=[FakeToolCall(index, arguments=args_json)])),
        FakeChunk(FakeDelta(), finish_reason="tool_calls"),
    ]


def _msgs(t="was steht an?"):
    return [{"role": "user", "content": t}]


def _lauf(gen):
    return list(gen)


# ── Grundfälle ─────────────────────────────────────────────────────────

def test_einfache_antwort(fake, kein_echter_graph):
    fake([_text("Hallo ", "Sasha.")])
    assert _lauf(cloud_openai.chat_stream(_msgs())) == ["Hallo Sasha."]
    # Derselbe Cloud-Graph wie beim Anthropic-Pfad: die Grenze verlaeuft
    # zwischen "im Haus" und "draussen", nicht zwischen zwei Anbietern.
    assert kein_echter_graph[0][2] == cloud.CLOUD_GRAPH


def test_reasoning_wird_reflect_event(fake):
    chunks = [FakeChunk(FakeDelta(reasoning_content="ich denke…")),
              FakeChunk(FakeDelta(content="Antwort.")),
              FakeChunk(FakeDelta(), finish_reason="stop")]
    fake([chunks])
    events = _lauf(cloud_openai.chat_stream(_msgs()))
    assert {"reflect": "ich denke…"} in events
    assert "Antwort." in events


def test_tools_gehen_ohne_uebersetzung_raus(fake):
    """Das Tool-Set der Schiene ist bereits OpenAI-Schema - anders als beim
    Anthropic-Pfad ist hier nichts zu uebersetzen."""
    from profil import gross
    c = fake([_text("ok")])
    _lauf(cloud_openai.chat_stream(_msgs()))
    assert c.calls[0]["tools"] is gross.TOOLS
    assert c.calls[0]["messages"][0]["role"] == "system"


def test_system_prompt_hat_dieselbe_reihenfolge_wie_anthropic(fake):
    """Beide Pfade benutzen denselben Bauer - der statische Kopf steht im
    System-Prompt, das Wechselnde (Uhrzeit, Graph) haengt hinten an der
    letzten User-Nachricht. Egal welcher Provider."""
    c = fake([_text("ok")])
    _lauf(cloud_openai.chat_stream(_msgs()))
    msgs = c.calls[0]["messages"]
    from profil import gross
    sys_text = msgs[0]["content"]
    assert gross.SYSTEM in sys_text
    # Die Uhrzeit darf NICHT im System-Prompt stehen - sie wuerde jeden
    # impliziten Praefix-Cache des Anbieters bei jedem Turn wegwerfen.
    assert "## Jetzt" not in sys_text
    assert msgs[-1]["role"] == "user"
    assert "## Jetzt" in msgs[-1]["content"]


# ── Tool-Loop ──────────────────────────────────────────────────────────

def test_tool_loop_und_gepuffertes_geschwaetz(fake):
    c = fake([
        [FakeChunk(FakeDelta(content="Ich schau nach…")),
         *_tool("read_calendar", '{"range":"heute"}')],
        _text("Heute ist frei."),
    ])
    gerufen = []
    events = _lauf(cloud_openai.chat_stream(
        _msgs(), tool_executor=lambda n, a: gerufen.append((n, a)) or "leer"))
    assert gerufen == [("read_calendar", {"range": "heute"})]
    assert events == ["Heute ist frei."]
    assert "Ich schau nach…" not in events        # Geschwaetz bleibt drin
    letzte = c.calls[1]["messages"][-1]
    assert letzte["role"] == "tool" and letzte["content"] == "leer"


def test_kaputte_argumente_kippen_nicht(fake):
    """Fragmentiertes JSON kommt bei kleineren Modellen wirklich vor."""
    c = fake([_tool("read_calendar", "{kaputt"), _text("ok")])
    gerufen = []
    _lauf(cloud_openai.chat_stream(
        _msgs(), tool_executor=lambda n, a: gerufen.append(a) or "x"))
    assert gerufen == [{}]


def test_runden_grenze_haelt(fake):
    fake([_tool("read_calendar", "{}")] * cloud_openai._MAX_ROUNDS)
    events = _lauf(cloud_openai.chat_stream(_msgs(), tool_executor=lambda n, a: "x"))
    assert any(isinstance(e, str) and "Tool-Tiefe" in e for e in events)


def test_krachendes_tool_reisst_den_turn_nicht_ab(fake):
    c = fake([_tool("read_file", '{"path":"/weg"}'), _text("Gibt es nicht.")])

    def kaputt(n, a):
        raise FileNotFoundError("/weg")

    assert _lauf(cloud_openai.chat_stream(_msgs(), tool_executor=kaputt)) \
        == ["Gibt es nicht."]
    assert "fehlgeschlagen" in c.calls[1]["messages"][-1]["content"]


# ── Geteilte Bedeutung: Gate und terminale Tools ───────────────────────

@pytest.fixture
def gate(monkeypatch):
    import state
    z = {"antwort": "ja"}
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    monkeypatch.setattr(state, "request_permission", lambda **k: None)
    monkeypatch.setattr(state, "wait_permission", lambda: z["antwort"])
    return z


def test_gate_gilt_auch_hier(fake, gate):
    gate["antwort"] = "nein"
    c = fake([_tool("add_calendar_entry", '{"label":"Zahnarzt"}'),
              _text("Ok, lasse ich.")])
    ausgefuehrt = []
    events = _lauf(cloud_openai.chat_stream(
        _msgs(), tool_executor=lambda n, a: ausgefuehrt.append(n) or "ok"))
    assert any(isinstance(e, dict) and "permission" in e for e in events)
    assert ausgefuehrt == []
    assert "abgelehnt" in c.calls[1]["messages"][-1]["content"]


def test_antwort_tool_ist_auch_hier_terminal(fake):
    c = fake([_tool("antwort", '{"text":"Das war\'s."}')])
    assert _lauf(cloud_openai.chat_stream(_msgs())) == ["Das war's."]
    assert len(c.calls) == 1


def test_lies_news_feuert_cinema(fake):
    c = fake([_tool("lies_news", "{}")])
    events = _lauf(cloud_openai.chat_stream(
        _msgs(), tool_executor=lambda n, a: "Sendung (Stand 12:00):\n\nGuten Tag."))
    assert events[0] == {"cinema": True}
    assert events[1] == "Guten Tag."
    assert len(c.calls) == 1


# ── Fehlerfälle ────────────────────────────────────────────────────────

def test_api_fehler_wird_gemeldet(fake, monkeypatch):
    class Kaputt:
        def create(self, **kw):
            raise RuntimeError("kein Netz")

    c = fake([_text("egal")])
    c.chat.completions = Kaputt()
    events = _lauf(cloud_openai.chat_stream(_msgs()))
    assert len(events) == 1 and "kein Netz" in events[0]


def test_falscher_dialekt_wird_abgelehnt(monkeypatch):
    monkeypatch.setattr(cloud_openai, "_provider",
                        lambda name=None: {"kind": "anthropic"})
    events = _lauf(cloud_openai.chat_stream(_msgs()))
    assert len(events) == 1 and "kein OpenAI-kompatibler" in events[0]


# ── Gleichheit der beiden Dialekte ─────────────────────────────────────

def test_beide_pfade_haben_dieselbe_signatur():
    import inspect
    a = inspect.signature(cloud.chat_stream).parameters
    b = inspect.signature(cloud_openai.chat_stream).parameters
    gemeinsam = ["messages", "model", "system", "tools", "tool_executor", "via_mic"]
    assert [p for p in a if p in gemeinsam] == gemeinsam
    assert [p for p in b if p in gemeinsam] == gemeinsam


def test_beide_pfade_teilen_die_tool_bedeutung():
    """Was terminal ist und was bestaetigt werden muss, steht genau einmal."""
    import inspect
    quelle = inspect.getsource(cloud_openai)
    assert "cloud.run_tool" in quelle
    assert "PERMISSION_REQUIRED_TOOLS" not in quelle
