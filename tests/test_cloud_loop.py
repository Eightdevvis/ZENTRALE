"""
core/cloud.py — der Tool-Loop, gegen einen gefälschten Anthropic-Client.

Warum das hier existiert: der Loop ist das Stück, das man sonst erst beim
ersten bezahlten API-Call kennenlernt. Ein Fake-Client, der die Antworten der
API skriptet, lässt den ECHTEN cloud.chat_stream() laufen — Event-Protokoll,
Erlaubnis-Gate, terminale Tools, Runden-Grenze, alles ohne Netz und ohne Key.

Was hier NICHT geprüft wird: ob die API die Requests akzeptiert. Dafür gibt
es scripts/cloud_smoke.py.
"""
import pytest

import ai
import cloud


# ── Fake-Anthropic ─────────────────────────────────────────────────────

class FakeDelta:
    def __init__(self, typ, text):
        self.type = typ
        if typ == "text_delta":
            self.text = text
        else:
            self.thinking = text


class FakeEvent:
    def __init__(self, delta=None, typ="content_block_delta"):
        self.type = typ
        self.delta = delta


class FakeBlock:
    """Ein content-Block: text, thinking oder tool_use."""
    def __init__(self, type, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class FakeUsage:
    input_tokens = 100
    output_tokens = 20
    cache_read_input_tokens = 90
    cache_creation_input_tokens = 0


class FakeFinal:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content
        self.usage = FakeUsage()


class FakeStream:
    def __init__(self, runde):
        self._runde = runde

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for txt in self._runde.get("thinking", []):
            yield FakeEvent(FakeDelta("thinking_delta", txt))
        for txt in self._runde.get("text", []):
            yield FakeEvent(FakeDelta("text_delta", txt))
        # Ein Event, das uns nicht interessiert - der Loop muss es überspringen.
        yield FakeEvent(typ="content_block_stop")

    def get_final_message(self):
        return FakeFinal(self._runde.get("stop_reason", "end_turn"),
                         self._runde.get("content", []))


class FakeMessages:
    def __init__(self, runden, calls):
        self._runden = list(runden)
        self._calls = calls

    def stream(self, **kwargs):
        self._calls.append(kwargs)
        if not self._runden:
            raise AssertionError("mehr API-Runden angefragt als skriptet")
        return FakeStream(self._runden.pop(0))


class FakeClient:
    def __init__(self, runden):
        self.calls = []
        self.messages = FakeMessages(runden, self.calls)


@pytest.fixture
def fake(monkeypatch):
    """Baut einen Fake-Client aus einem Runden-Skript und hängt ihn ein."""
    gebaut = {}

    def bauen(runden):
        c = FakeClient(runden)
        monkeypatch.setattr(cloud, "_get_client", lambda: c)
        gebaut["client"] = c
        return c

    yield bauen


@pytest.fixture(autouse=True)
def kein_echter_graph(monkeypatch):
    """Graph-Lesen/Schreiben abklemmen: die Tests prüfen den Loop, nicht das
    Memory. Die gespeicherten Turns werden mitgeschrieben, damit wir die
    Isolations-Invariante prüfen können."""
    gespeichert = []
    monkeypatch.setattr(cloud.graph, "context_for_query",
                        lambda *a, **k: "## Erinnerung\n(test)")
    monkeypatch.setattr(ai, "_ensure_seed_once", lambda *a, **k: None)
    monkeypatch.setattr(ai, "_async_save_turn",
                        lambda u, a, store=None: gespeichert.append((u, a, store)))
    monkeypatch.setattr(cloud.ai, "_ensure_seed_once", lambda *a, **k: None)
    return gespeichert


def _tool_block(name, args, id="toolu_1"):
    return FakeBlock("tool_use", name=name, input=args, id=id)


def _msgs(text="was steht an?"):
    return [{"role": "user", "content": text}]


def _lauf(gen):
    """Generator leerlaufen lassen und die Events einsammeln.

    OHNE die `werkzeug`-Ereignisse: die sind seit dem 20.08.2026 ein reiner
    ANZEIGE-Kanal (Tool-Calls im Chat sichtbar machen) und gehoeren nicht
    zum Tool-Protokoll, um das es in dieser Datei geht. Sie stehen in jedem
    Tool-Lauf drin und wuerden hier nur jede Erwartung um Rauschen
    ergaenzen. Geprueft werden sie in tests/test_transparenz.py.
    """
    return [e for e in gen
            if not (isinstance(e, dict) and "werkzeug" in e)]


# ── Der einfachste Fall: eine Runde, nur Text ──────────────────────────

def test_einfache_antwort(fake, kein_echter_graph):
    fake([{"text": ["Hallo ", "Sasha."], "stop_reason": "end_turn"}])
    events = _lauf(cloud.chat_stream(_msgs()))
    assert events == ["Hallo Sasha."]
    # Turn landet im CLOUD-Graphen, nicht im lokalen.
    assert kein_echter_graph == [("was steht an?", "Hallo Sasha.", cloud.CLOUD_GRAPH)]


def test_denk_tokens_werden_reflect_events(fake):
    fake([{"thinking": ["ich schau ", "mal nach"],
           "text": ["Fertig."], "stop_reason": "end_turn"}])
    events = _lauf(cloud.chat_stream(_msgs()))
    assert {"reflect": "ich schau "} in events
    assert {"reflect": "mal nach"} in events
    # Denken ist innerer Monolog: NICHT im Antworttext.
    assert "Fertig." in events
    assert not any(isinstance(e, str) and "ich schau" in e for e in events)


def test_denken_landet_nicht_im_gespeicherten_turn(fake, kein_echter_graph):
    fake([{"thinking": ["grübel"], "text": ["Antwort."], "stop_reason": "end_turn"}])
    _lauf(cloud.chat_stream(_msgs()))
    assert kein_echter_graph[0][1] == "Antwort."


# ── Request-Form ───────────────────────────────────────────────────────

def test_request_traegt_cache_breakpoint_und_tools(fake):
    c = fake([{"text": ["ok"], "stop_reason": "end_turn"}])
    _lauf(cloud.chat_stream(_msgs()))
    kw = c.calls[0]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    from profil import gross
    assert len(kw["tools"]) == len(gross.TOOLS)
    assert kw["thinking"]["type"] == "adaptive"
    assert kw["output_config"]["effort"] == cloud._effort()
    # Sampling-Parameter sind ab Opus 4.7 ein 400 - sie dürfen NIE mitgehen.
    for verboten in ("temperature", "top_p", "top_k"):
        assert verboten not in kw


def _breakpoints(kw) -> list:
    """Alle Cache-Breakpoints eines Requests einsammeln (system + messages)."""
    treffer = list(kw["system"])
    for m in kw["messages"]:
        c = m.get("content")
        if isinstance(c, list):
            treffer.extend(b for b in c if isinstance(b, dict))
    return [b for b in treffer if "cache_control" in b]


def test_wechselndes_haengt_hinten_an_der_letzten_user_nachricht(fake, monkeypatch):
    """Der Kern des Cache-Umbaus. Graph-Kontext und Uhrzeit standen frueher im
    system-Feld, also VOR dem gesamten Verlauf — und weil die Uhr jeden Turn
    eine andere ist, ging der ganze Verlauf jedes Mal ungecacht raus
    (gemessen: in=7236, cache_read=0 fuer eine Drei-Wort-Antwort).

    Der Graph-Kontext ist inzwischen per Default aus (Datei-Gedaechtnis).
    Hier wird er absichtlich eingeschaltet: geprueft wird die PLATZIERUNG
    des Wechselnden, und der Graph ist davon das anschaulichste Beispiel."""
    monkeypatch.setattr(cloud.ai, "GRAPH_KONTEXT", True)
    c = fake([{"text": ["ok"], "stop_reason": "end_turn"}])
    _lauf(cloud.chat_stream(_msgs()))
    kw = c.calls[0]

    from profil import gross
    system = kw["system"][0]["text"]
    assert gross.SYSTEM in system
    assert "## Jetzt" not in system          # die Uhr gehoert NICHT nach vorn
    assert "## Erinnerung" not in system     # der Graph auch nicht

    letzte = kw["messages"][-1]
    assert letzte["role"] == "user"
    bloecke = letzte["content"]
    assert bloecke[0]["text"] == "was steht an?"
    assert "## Jetzt" in bloecke[-1]["text"]
    assert "## Erinnerung" in bloecke[-1]["text"]


def test_breakpoint_sitzt_vor_dem_wechselnden(fake):
    """Der Breakpoint muss auf dem User-Text liegen, nicht auf dem Block
    dahinter. Saesse er hinter dem Wechselnden, wuerde jeder Turn eine eigene
    Cache-Zeile schreiben, die nie wieder gelesen wird — reine Mehrkosten."""
    c = fake([{"text": ["ok"], "stop_reason": "end_turn"}])
    _lauf(cloud.chat_stream(_msgs()))
    bloecke = c.calls[0]["messages"][-1]["content"]
    assert bloecke[-2]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in bloecke[-1]


def test_verlauf_ist_ueber_die_turns_praefix_identisch(fake):
    """Ein Cache-Treffer verlangt einen byte-identischen Praefix. Was in Turn 1
    die neueste Nachricht war, muss in Turn 2 als Verlauf ZEICHENGLEICH wieder
    auftauchen — sonst waechst cache_read nie."""
    c = fake([{"text": ["ok"], "stop_reason": "end_turn"}])
    _lauf(cloud.chat_stream(_msgs("erste frage")))
    erste = c.calls[0]["messages"][0]["content"][0]["text"]

    c2 = fake([{"text": ["ok"], "stop_reason": "end_turn"}])
    _lauf(cloud.chat_stream([
        {"role": "user",      "content": "erste frage"},
        {"role": "assistant", "content": "erste antwort"},
        {"role": "user",      "content": "zweite frage"},
    ]))
    assert c2.calls[0]["messages"][0]["content"][0]["text"] == erste


def test_hoechstens_vier_breakpoints(fake):
    """Anthropic erlaubt maximal 4. Einer mehr ist eine 400 mitten im
    Gespraech — und zwar erst dann, wenn genug Tool-Runden zusammenkommen."""
    c = fake([
        {"content": [_tool_block("read_calendar", {}, id="t1")],
         "stop_reason": "tool_use"},
        {"content": [_tool_block("read_calendar", {}, id="t2")],
         "stop_reason": "tool_use"},
        {"content": [_tool_block("read_calendar", {}, id="t3")],
         "stop_reason": "tool_use"},
        {"text": ["nix los"], "stop_reason": "end_turn"},
    ])
    _lauf(cloud.chat_stream(_msgs()))
    for kw in c.calls:
        assert len(_breakpoints(kw)) <= 4


def test_tool_runde_zieht_den_breakpoint_nach(fake):
    """Ohne mitwandernden Breakpoint zahlt Runde 3 die Ergebnisse von Runde 2
    noch einmal voll. Der alte muss dabei weg — sonst sammeln sich die
    Breakpoints bis zur 400."""
    c = fake([
        {"content": [_tool_block("read_calendar", {}, id="t1")],
         "stop_reason": "tool_use"},
        {"content": [_tool_block("read_calendar", {}, id="t2")],
         "stop_reason": "tool_use"},
        {"text": ["nix los"], "stop_reason": "end_turn"},
    ])
    _lauf(cloud.chat_stream(_msgs()))

    # Runde 2 sieht die tool_results von Runde 1 — markiert.
    runde2 = c.calls[1]["messages"]
    assert runde2[-1]["content"][-1]["type"] == "tool_result"
    assert "cache_control" in runde2[-1]["content"][-1]

    # Runde 3: der Breakpoint ist weitergewandert, der alte ist abgeraeumt.
    runde3 = c.calls[2]["messages"]
    assert "cache_control" in runde3[-1]["content"][-1]
    alte_results = [m for m in runde3[:-1]
                    if isinstance(m.get("content"), list)
                    and any(isinstance(b, dict) and b.get("type") == "tool_result"
                            for b in m["content"])]
    for m in alte_results:
        assert not any("cache_control" in b for b in m["content"])


def test_zweite_runde_nutzt_denselben_statischen_block(fake):
    """Der Cache-Treffer haengt daran, dass Block [0] ueber die Runden
    byte-identisch bleibt - auch nach einer Tool-Runde."""
    c = fake([
        {"content": [_tool_block("read_calendar", {})], "stop_reason": "tool_use"},
        {"text": ["nix los"], "stop_reason": "end_turn"},
    ])
    _lauf(cloud.chat_stream(_msgs(), tool_executor=lambda n, a: "leer"))
    assert len(c.calls) == 2
    assert c.calls[0]["system"][0]["text"] == c.calls[1]["system"][0]["text"]


# ── Tool-Loop ──────────────────────────────────────────────────────────

def test_tool_wird_ausgefuehrt_und_ergebnis_geht_zurueck(fake):
    c = fake([
        {"text": ["Ich schau nach…"],
         "content": [_tool_block("read_calendar", {"range": "heute"})],
         "stop_reason": "tool_use"},
        {"text": ["Heute ist frei."], "stop_reason": "end_turn"},
    ])
    gerufen = []

    def executor(name, args):
        gerufen.append((name, args))
        return "keine Termine"

    events = _lauf(cloud.chat_stream(_msgs(), tool_executor=executor))
    assert gerufen == [("read_calendar", {"range": "heute"})]
    assert events == ["Heute ist frei."]
    # Das Vorgeplänkel der Tool-Runde darf den User NIE erreichen (es wuerde
    # sonst auch vorgelesen).
    assert "Ich schau nach…" not in events
    # Ergebnis geht als tool_result in EINER user-Message zurueck.
    letzte = c.calls[1]["messages"][-1]
    assert letzte["role"] == "user"
    assert letzte["content"][0]["type"] == "tool_result"
    assert letzte["content"][0]["content"] == "keine Termine"


def test_mehrere_tools_in_einer_message(fake):
    """Auf mehrere user-Messages aufzuteilen bringt dem Modell bei, keine
    parallelen Tool-Calls mehr zu machen."""
    c = fake([
        {"content": [_tool_block("read_calendar", {}, "t1"),
                     _tool_block("read_file", {"pfad": "x"}, "t2")],
         "stop_reason": "tool_use"},
        {"text": ["fertig"], "stop_reason": "end_turn"},
    ])
    _lauf(cloud.chat_stream(_msgs(), tool_executor=lambda n, a: f"ergebnis-{n}"))
    inhalt = c.calls[1]["messages"][-1]["content"]
    assert len(inhalt) == 2
    assert [b["tool_use_id"] for b in inhalt] == ["t1", "t2"]


def test_runden_grenze_haelt(fake):
    """Ein Modell, das ewig Tools ruft, darf nicht ewig Geld verbrennen."""
    fake([{"content": [_tool_block("read_calendar", {})],
           "stop_reason": "tool_use"}] * cloud._MAX_ROUNDS)
    events = _lauf(cloud.chat_stream(_msgs(), tool_executor=lambda n, a: "x"))
    assert any(isinstance(e, str) and "Tool-Tiefe" in e for e in events)


# ── Erlaubnis-Gate ─────────────────────────────────────────────────────

@pytest.fixture
def gate(monkeypatch):
    """Fängt den blockierenden Permission-Dialog ab."""
    import state
    zustand = {"antwort": "ja", "gefragt": []}
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    monkeypatch.setattr(state, "request_permission",
                        lambda **k: zustand["gefragt"].append(k))
    monkeypatch.setattr(state, "wait_permission", lambda: zustand["antwort"])
    return zustand


def test_gate_fragt_vor_schreibendem_tool(fake, gate):
    c = fake([
        {"content": [_tool_block("add_calendar_entry",
                                 {"label": "Zahnarzt", "day": "2026-08-20"})],
         "stop_reason": "tool_use"},
        {"text": ["Eingetragen."], "stop_reason": "end_turn"},
    ])
    ausgefuehrt = []
    events = _lauf(cloud.chat_stream(
        _msgs(), tool_executor=lambda n, a: ausgefuehrt.append(n) or "ok"))

    perm = [e for e in events if isinstance(e, dict) and "permission" in e]
    assert len(perm) == 1
    assert "Zahnarzt" in perm[0]["permission"]["frage"]
    assert ausgefuehrt == ["add_calendar_entry"]   # "ja" → ausgefuehrt


def test_gate_nein_fuehrt_nicht_aus(fake, gate):
    gate["antwort"] = "nein"
    c = fake([
        {"content": [_tool_block("add_calendar_entry", {"label": "Zahnarzt"})],
         "stop_reason": "tool_use"},
        {"text": ["Ok, lasse ich."], "stop_reason": "end_turn"},
    ])
    ausgefuehrt = []
    _lauf(cloud.chat_stream(
        _msgs(), tool_executor=lambda n, a: ausgefuehrt.append(n) or "ok"))
    assert ausgefuehrt == []
    # Das Modell muss ERFAHREN, dass abgelehnt wurde - sonst behauptet es,
    # es haette eingetragen.
    zurueck = c.calls[1]["messages"][-1]["content"][0]["content"]
    assert "abgelehnt" in zurueck


def test_lesende_tools_werden_nicht_gegatet(fake, gate):
    fake([
        {"content": [_tool_block("read_calendar", {})], "stop_reason": "tool_use"},
        {"text": ["frei"], "stop_reason": "end_turn"},
    ])
    events = _lauf(cloud.chat_stream(_msgs(), tool_executor=lambda n, a: "leer"))
    assert not any(isinstance(e, dict) and "permission" in e for e in events)


def test_frage_knopf_liefert_die_wahl_zurueck(fake, gate):
    gate["antwort"] = "morgen"
    c = fake([
        {"content": [_tool_block("frage_knopf",
                                 {"frage": "Wann?", "optionen": ["heute", "morgen"]})],
         "stop_reason": "tool_use"},
        {"text": ["Alles klar."], "stop_reason": "end_turn"},
    ])
    events = _lauf(cloud.chat_stream(_msgs(), tool_executor=lambda n, a: "x"))
    perm = [e for e in events if isinstance(e, dict) and "permission" in e][0]
    assert perm["permission"]["optionen"] == ["heute", "morgen"]
    assert "morgen" in c.calls[1]["messages"][-1]["content"][0]["content"]


# ── Terminale Tools ────────────────────────────────────────────────────

def test_antwort_tool_ist_terminal(fake, kein_echter_graph):
    """Kein zweiter API-Call - der Text IST die Antwort."""
    c = fake([{"content": [_tool_block("antwort", {"text": "Das war's."})],
               "stop_reason": "tool_use"}])
    events = _lauf(cloud.chat_stream(_msgs()))
    assert events == ["Das war's."]
    assert len(c.calls) == 1
    assert kein_echter_graph[0][2] == cloud.CLOUD_GRAPH


def test_lies_news_feuert_cinema_und_ist_terminal(fake):
    c = fake([{"content": [_tool_block("lies_news", {})], "stop_reason": "tool_use"}])
    events = _lauf(cloud.chat_stream(
        _msgs(), tool_executor=lambda n, a: "Sendung (Stand 12:00):\n\nGuten Tag."))
    assert events[0] == {"cinema": True}
    assert events[1] == "Guten Tag."     # Meta-Kopf abgeschnitten
    assert len(c.calls) == 1


# ── Bild-Marker ────────────────────────────────────────────────────────

def test_bild_marker_wird_eigenes_event(fake, monkeypatch):
    monkeypatch.setattr(ai.ascii_lib, "pick", lambda n: ("winken", "o/"))
    fake([{"text": ["Hi [[bild: winken]] du."], "stop_reason": "end_turn"}])
    events = _lauf(cloud.chat_stream(_msgs()))
    assert {"ascii": "o/", "name": "winken"} in events
    # Marker ist aus dem Text raus - er soll nicht vorgelesen werden.
    text = [e for e in events if isinstance(e, str)][0]
    assert "[[bild:" not in text


# ── Fehlerfälle ────────────────────────────────────────────────────────

def test_krachendes_tool_reisst_den_turn_nicht_ab(fake):
    """Die Runde ist bezahlt - ein Tool-Fehler darf sie nicht wegwerfen.
    Das Modell soll den Fehler SEHEN und reagieren können."""
    c = fake([
        {"content": [_tool_block("read_file", {"path": "/gibtsnicht"})],
         "stop_reason": "tool_use"},
        {"text": ["Die Datei gibt es nicht."], "stop_reason": "end_turn"},
    ])

    def kaputt(name, args):
        raise FileNotFoundError("/gibtsnicht")

    events = _lauf(cloud.chat_stream(_msgs(), tool_executor=kaputt))
    assert events == ["Die Datei gibt es nicht."]
    zurueck = c.calls[1]["messages"][-1]["content"][0]
    assert zurueck["is_error"] is True
    assert "gibtsnicht" in zurueck["content"]


def test_erfolgreiches_tool_hat_kein_is_error(fake):
    c = fake([
        {"content": [_tool_block("read_calendar", {})], "stop_reason": "tool_use"},
        {"text": ["ok"], "stop_reason": "end_turn"},
    ])
    _lauf(cloud.chat_stream(_msgs(), tool_executor=lambda n, a: "leer"))
    assert "is_error" not in c.calls[1]["messages"][-1]["content"][0]


def test_stop_reason_tool_use_ohne_tool_block(fake):
    """Kante: das Modell sagt 'tool_use', liefert aber gar keinen tool_use-Block.
    Naiv gebaut hängt man dann eine user-Message mit LEEREM content an - und
    die lehnt die API mit 400 ab. Der Loop muss die Runde stattdessen als
    fertig behandeln."""
    c = fake([{"text": ["nur text"],
               "content": [FakeBlock("text", text="nur text")],
               "stop_reason": "tool_use"}])
    events = _lauf(cloud.chat_stream(_msgs()))
    assert events == ["nur text"]
    assert len(c.calls) == 1        # keine zweite, sinnlose Runde


def test_leere_antwort_bricht_nicht(fake):
    """Modell liefert gar nichts (z.B. max_tokens im Denken verbraucht)."""
    fake([{"stop_reason": "end_turn", "content": []}])
    events = _lauf(cloud.chat_stream(_msgs()))
    assert all(not isinstance(e, str) or e == "" for e in events)


def test_refusal_wird_sauber_gemeldet(fake):
    fake([{"content": [], "stop_reason": "refusal"}])
    events = _lauf(cloud.chat_stream(_msgs()))
    assert any(isinstance(e, str) and "abgelehnt" in e for e in events)


def test_api_fehler_reisst_den_stream_nicht_ab(fake, monkeypatch):
    class Kaputt:
        def stream(self, **kw):
            raise RuntimeError("kein Netz")

    class C:
        messages = Kaputt()

    monkeypatch.setattr(cloud, "_get_client", lambda: C())
    events = _lauf(cloud.chat_stream(_msgs()))
    assert len(events) == 1
    assert "Cloud-Fehler" in events[0] and "kein Netz" in events[0]


# ── Cloud an, Ollama aus ───────────────────────────────────────────────

def test_cloud_laeuft_auch_ohne_ollama(fake, tmp_path, monkeypatch):
    """Der Cloud-Kern denkt in der Cloud, braucht Ollama aber weiter für die
    EMBEDDINGS (Memory). Ist Ollama weg, liefert embed() None. Das darf den
    Chat höchstens gedächtnislos machen, nicht abstürzen lassen — sonst wäre
    ausgerechnet der Pfad kaputt, der laufen soll, wenn lokal nichts geht.

    Läuft bewusst gegen den ECHTEN Graph-Code, nur mit totem Embedder.
    """
    import embeddings
    import graph

    store = str(tmp_path / "ai_graph_cloud.json")
    monkeypatch.setattr(cloud, "CLOUD_GRAPH", store)
    monkeypatch.setattr(embeddings, "embed_query", lambda *a, **k: None)
    monkeypatch.setattr(embeddings, "embed_document", lambda *a, **k: None)
    # Echten Graph-Pfad wiederherstellen (die autouse-Fixture klemmt ihn ab).
    monkeypatch.setattr(cloud.graph, "context_for_query", graph.context_for_query)

    # Seed gegen den echten Graphen laufen lassen, ebenfalls ohne Embedder.
    monkeypatch.setattr(ai, "_ensure_seed_once",
                        lambda store=None: graph.ensure_seed(store=store))

    fake([{"text": ["Ich hab dazu nichts gespeichert."], "stop_reason": "end_turn"}])
    events = _lauf(cloud.chat_stream(_msgs("was weisst du ueber mich?")))
    assert events == ["Ich hab dazu nichts gespeichert."]


def test_kontext_ohne_embedder_ist_leer_nicht_kaputt(tmp_path, monkeypatch):
    """Dieselbe Lage eine Ebene tiefer: kein Embedder → kein Kontext, aber
    auch keine Exception."""
    import embeddings
    import graph

    monkeypatch.setattr(embeddings, "embed_query", lambda *a, **k: None)
    monkeypatch.setattr(embeddings, "embed_document", lambda *a, **k: None)
    store = str(tmp_path / "leer.json")
    ctx = graph.context_for_query("irgendwas", store=store)
    assert isinstance(ctx, str)


# ── Das Rauchtest-Skript selbst ────────────────────────────────────────

def _smoke_modul():
    import importlib.util
    import os
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "cloud_smoke.py")
    spec = importlib.util.spec_from_file_location("cloud_smoke", pfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rauchtest_bricht_ohne_key_ab(monkeypatch):
    """Fail-safe: lieber gar nicht starten als mit halber Konfiguration."""
    import providers
    for p in providers.PROVIDERS.values():
        monkeypatch.delenv(p["key_env"], raising=False)
    mod = _smoke_modul()
    monkeypatch.setattr("sys.argv", ["cloud_smoke.py"])
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert e.value.code == 1


def test_rauchtest_lehnt_provider_ohne_dialekt_ab(monkeypatch):
    import providers
    monkeypatch.setattr(providers, "PROVIDERS",
                        dict(providers.PROVIDERS,
                             seltsam={"base_url": "http://x", "key_env": "SELTSAM_KEY"}))
    monkeypatch.setenv("SELTSAM_KEY", "x")
    mod = _smoke_modul()
    monkeypatch.setattr("sys.argv", ["cloud_smoke.py", "--provider", "seltsam"])
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert e.value.code == 1


def test_rauchtest_laeuft_alle_stufen_durch(fake, monkeypatch, capsys):
    """Das Skript wird einmal mit echtem Geld laufen - vorher soll feststehen,
    dass es nicht an einem Tippfehler stirbt."""
    import state
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(cloud, "is_available", lambda: True)
    fake([
        {"text": ["Hallo."], "stop_reason": "end_turn"},        # Stufe 1
        {"text": ["Hallo."], "stop_reason": "end_turn"},        # Stufe 2
        {"content": [_tool_block("read_calendar", {})],         # Stufe 3
         "stop_reason": "tool_use"},
        {"text": ["Nichts los."], "stop_reason": "end_turn"},
    ])
    monkeypatch.setattr(ai, "_execute_tool", lambda n, a: "keine Termine")

    sicherung = (state.push_log, state.wait_permission, state.request_permission)
    try:
        mod = _smoke_modul()
        monkeypatch.setattr("sys.argv", ["cloud_smoke.py"])
        mod.main()
    finally:
        state.push_log, state.wait_permission, state.request_permission = sicherung

    aus = capsys.readouterr().out
    assert "Erreichbarkeit" in aus and "Prompt-Cache" in aus and "Tool-Loop" in aus
    assert "Cache greift" in aus          # FakeUsage meldet cache_read=90
    assert "fertig" in aus


# ── Tutor-Modus (fremdes Tool-Set) ─────────────────────────────────────

def test_tutor_modus_ohne_memory_und_ohne_gate(fake, gate, kein_echter_graph):
    eigene_tools = [{"type": "function",
                     "function": {"name": "get_confirmed_vocab",
                                  "description": "d", "parameters": {"type": "object"}}}]
    c = fake([
        {"content": [_tool_block("get_confirmed_vocab", {})], "stop_reason": "tool_use"},
        {"text": ["你好"], "stop_reason": "end_turn"},
    ])
    events = _lauf(cloud.chat_stream(_msgs(), system="TUTOR", tools=eigene_tools,
                                     tool_executor=lambda n, a: "hallo"))
    assert events == ["你好"]
    assert len(c.calls[0]["tools"]) == 1          # nur das fremde Tool-Set
    assert kein_echter_graph == []                # kein Memory-Schreiben
    assert not any(isinstance(e, dict) for e in events)
