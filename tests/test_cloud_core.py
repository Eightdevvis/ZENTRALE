"""
core/cloud.py — der Anthropic-Pfad des Kerns.

Getestet wird, was OHNE API-Key und ohne Netz prüfbar ist: die Übersetzung
zwischen den beiden Tool-Dialekten, der Zuschnitt des System-Prompts (das ist
die Cache-Mechanik und damit der Kostenhebel) und die Isolations-Invariante
zwischen lokalem und Cloud-Graphen.

Der eigentliche Streaming-Loop braucht die API und wird hier NICHT gefahren.
"""
import os

import pytest

import ai
import cloud
import graph
import ai_backends


# ── Tool-Schema-Übersetzung ────────────────────────────────────────────

def test_tools_werden_vollstaendig_uebersetzt():
    """Jedes Kern-Tool kommt im Anthropic-Format an - keins fällt weg."""
    out = cloud._to_anthropic_tools(ai.TOOLS)
    assert len(out) == len(ai.TOOLS)
    for t in out:
        assert set(t) == {"name", "description", "input_schema"}
        assert t["name"]
        assert t["input_schema"].get("type") == "object"


def test_tool_reihenfolge_bleibt():
    """Tools werden VOR dem System-Prompt gerendert und sind Teil des
    Cache-Präfixes. Umsortieren würde bei jedem Turn den Cache wegwerfen."""
    namen_vorher  = [t.get("function", t)["name"] for t in ai.TOOLS]
    namen_nachher = [t["name"] for t in cloud._to_anthropic_tools(ai.TOOLS)]
    assert namen_vorher == namen_nachher


def test_uebersetzung_toleriert_beide_schema_formen():
    roh = [{"type": "function", "function": {"name": "a", "description": "d",
                                             "parameters": {"type": "object"}}},
           {"name": "b", "description": "d2", "parameters": {"type": "object"}}]
    assert [t["name"] for t in cloud._to_anthropic_tools(roh)] == ["a", "b"]


def test_uebersetzung_ohne_tools():
    assert cloud._to_anthropic_tools([]) == []
    assert cloud._to_anthropic_tools(None) == []


# ── System-Prompt: die Cache-Mechanik ──────────────────────────────────

def test_statischer_block_traegt_cache_control():
    blocks = cloud._system_blocks(None, "", False, tutor_mode=False)
    assert len(blocks) == 2
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    # Der wechselnde Block darf KEINEN Breakpoint haben - sonst würde jeder
    # Turn eine eigene Cache-Zeile schreiben, die nie wieder gelesen wird.
    assert "cache_control" not in blocks[1]


def test_statischer_block_ist_ueber_turns_byte_identisch():
    """Der Kern der Sache: ein Cache-Treffer verlangt ein byte-identisches
    Präfix. Unterschiedlicher Graph-Kontext und Mic-Flag dürfen den statischen
    Block NICHT anfassen."""
    a = cloud._system_blocks(None, "", False, tutor_mode=False)
    b = cloud._system_blocks(None, "## Erinnerung\nirgendwas", True, tutor_mode=False)
    assert a[0]["text"] == b[0]["text"]
    assert a[1]["text"] != b[1]["text"]


def test_jetzt_block_steht_nicht_im_statischen_teil():
    """Der Jetzt-Block enthält die UHRZEIT. Stünde er im gecachten Block,
    wäre der Cache bei jedem Turn kaputt - das war der teuerste Einzelfehler
    im ganzen Umbau."""
    blocks = cloud._system_blocks(None, "", False, tutor_mode=False)
    assert "## Jetzt" not in blocks[0]["text"]
    assert "## Jetzt" in blocks[1]["text"]


def test_graph_kontext_steht_im_wechselnden_teil():
    mem = "## Erinnerung\nSasha mag Karten."
    blocks = cloud._system_blocks(None, mem, False, tutor_mode=False)
    assert mem not in blocks[0]["text"]
    assert mem in blocks[1]["text"]


def test_statischer_block_enthaelt_die_persona():
    blocks = cloud._system_blocks(None, "", False, tutor_mode=False)
    assert ai._SYSTEM_PROMPT in blocks[0]["text"]
    assert ai._CAPABILITIES_PROMPT in blocks[0]["text"]


def test_tutor_modus_ohne_kern_bloecke():
    """Fremdes Tool-Set: eigener vollständiger Prompt, keine Bild-Marker,
    keine Kern-Meta-Regeln - genau wie im lokalen Pfad."""
    blocks = cloud._system_blocks("EIGENER PROMPT", "", False, tutor_mode=True)
    assert blocks[0]["text"] == "EIGENER PROMPT"
    assert ai._ASCII_MARKER_PROMPT not in blocks[0]["text"]
    # Den Jetzt-Block kriegt der Tutor trotzdem.
    assert "## Jetzt" in blocks[1]["text"]


def test_statischer_block_ueberschreitet_die_cache_mindestgroesse():
    """Anthropic cacht ein Präfix erst ab einer Mindestgröße (Opus 5: 512
    Token) - darunter passiert stillschweigend nichts. Grobe Zeichen-Schätzung
    reicht hier als Untergrenze."""
    blocks = cloud._system_blocks(None, "", False, tutor_mode=False)
    assert len(blocks[0]["text"]) > 2048


# ── History-Aufbereitung ───────────────────────────────────────────────

def test_system_rollen_fliegen_raus():
    """Der lokale Pfad hängt den System-Prompt als erste 'system'-Message in
    die Liste; bei Anthropic ist system ein eigenes Feld."""
    msgs = cloud._prepare_messages([
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "hallo"},
    ])
    assert msgs == [{"role": "user", "content": "hallo"}]


def test_history_beginnt_immer_mit_user():
    msgs = cloud._prepare_messages([
        {"role": "assistant", "content": "ich zuerst"},
        {"role": "user", "content": "hallo"},
    ])
    assert msgs[0]["role"] == "user"


def test_leere_history_wird_nie_leer_uebergeben():
    """Anthropic lehnt eine leere messages-Liste ab."""
    for leer in ([], None, [{"role": "user", "content": ""}]):
        msgs = cloud._prepare_messages(leer)
        assert msgs and msgs[0]["role"] == "user" and msgs[0]["content"]


def test_leere_turns_fliegen_raus():
    msgs = cloud._prepare_messages([
        {"role": "user", "content": "eins"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "zwei"},
    ])
    assert [m["content"] for m in msgs] == ["eins", "zwei"]


# ── Isolations-Invariante ──────────────────────────────────────────────

def test_cloud_graph_ist_nicht_der_core_graph():
    """Lokal sieht alles von Cloud. Cloud sieht nichts von lokal. Wäre das
    derselbe Pfad, ginge Sashas kompletter Konzept-Graph an die API."""
    assert os.path.abspath(cloud.CLOUD_GRAPH) != os.path.abspath(graph._GRAPH_FILE)
    assert cloud.CLOUD_GRAPH.endswith("ai_graph_cloud.json")


def test_cloud_graph_ist_absolut():
    """graph.py cacht Stores nach Pfad-String - zwei Schreibweisen desselben
    Pfades wären zwei Locks auf einer Datei."""
    assert os.path.isabs(cloud.CLOUD_GRAPH)


def test_getrennte_stores_teilen_keinen_zustand():
    st_core  = graph._get_store()
    st_cloud = graph._get_store(cloud.CLOUD_GRAPH)
    assert st_core is not st_cloud
    assert st_core.lock is not st_cloud.lock


def test_tool_result_shape():
    r = cloud._tool_result("toolu_1", "ergebnis")
    assert r == {"type": "tool_result", "tool_use_id": "toolu_1",
                 "content": "ergebnis"}


# ── Backend-Wahl ───────────────────────────────────────────────────────

@pytest.fixture
def kein_env_override(monkeypatch):
    monkeypatch.delenv("ZENTRALE_CHAT_BACKEND", raising=False)


def _status(local, cloud_da, provider="claude"):
    return {"local": local, "cloud": cloud_da, "cloud_provider": provider,
            "any": local or cloud_da}


def test_chat_kennt_jetzt_beide_backends():
    assert ai_backends.module_backends("chat") == (ai_backends.LOCAL,
                                                   ai_backends.CLOUD)


def test_auto_nimmt_lokal_wenn_beide_da(monkeypatch, kein_env_override):
    monkeypatch.setattr(ai_backends, "status", lambda *a, **k: _status(True, True))
    monkeypatch.setattr(ai_backends, "chat_backend", lambda: "auto")
    assert ai_backends.pick("chat") == ai_backends.LOCAL


def test_auto_faellt_auf_cloud_zurueck(monkeypatch, kein_env_override):
    monkeypatch.setattr(ai_backends, "status", lambda *a, **k: _status(False, True))
    monkeypatch.setattr(ai_backends, "chat_backend", lambda: "auto")
    assert ai_backends.pick("chat") == ai_backends.CLOUD


def test_vorwahl_cloud_schlaegt_verfuegbares_lokal(monkeypatch, kein_env_override):
    """Das ist der Schalter, der den Cloud-Assistenten überhaupt einschaltet:
    ohne ihn gewinnt das lokale 9b jeden Turn, einfach weil es läuft."""
    monkeypatch.setattr(ai_backends, "status", lambda *a, **k: _status(True, True))
    monkeypatch.setattr(ai_backends, "chat_backend", lambda: ai_backends.CLOUD)
    assert ai_backends.pick("chat") == ai_backends.CLOUD


def test_vorwahl_faellt_nicht_still_auf_das_andere_zurueck(monkeypatch,
                                                           kein_env_override):
    """Ein stiller Fallback wäre hier gefährlich - der Unterschied ist, ob
    Sashas Daten das Haus verlassen."""
    monkeypatch.setattr(ai_backends, "status", lambda *a, **k: _status(True, False))
    monkeypatch.setattr(ai_backends, "chat_backend", lambda: ai_backends.CLOUD)
    assert ai_backends.pick("chat") is None


def test_provider_ohne_dialekt_zaehlt_fuer_den_chat_nicht(monkeypatch,
                                                          kein_env_override):
    """Erreichbar heißt noch nicht bedienbar: kennt die Registry für den
    Provider kein 'kind', kann der Kern nicht mit ihm reden - dann ist Cloud
    für den Chat nicht da, auch wenn ein Key gesetzt ist."""
    monkeypatch.setattr(ai_backends, "status",
                        lambda *a, **k: _status(False, True, provider="gibtsnicht"))
    monkeypatch.setattr(ai_backends, "chat_backend", lambda: "auto")
    assert ai_backends.pick("chat") is None


def test_qwen_zaehlt_seit_dem_openai_pfad(monkeypatch, kein_env_override):
    """DashScope spricht OpenAI-kompatibel - seit core/cloud_openai.py kann
    der Kern das bedienen."""
    monkeypatch.setattr(ai_backends, "status",
                        lambda *a, **k: _status(False, True, provider="qwen"))
    monkeypatch.setattr(ai_backends, "chat_backend", lambda: "auto")
    assert ai_backends.pick("chat") == ai_backends.CLOUD


# ── Welches Modul bedient welchen Provider ─────────────────────────────

def test_dialekt_pro_provider():
    assert ai_backends.cloud_kind_for("claude") == "anthropic"
    assert ai_backends.cloud_kind_for("qwen") == "openai_compat"
    assert ai_backends.cloud_kind_for("gibtsnicht") is None
    assert ai_backends.cloud_kind_for(None) is None


def test_jeder_provider_mit_key_hat_einen_dialekt():
    """Sonst faellt ein Provider still durch: Key gesetzt, status()=cloud da,
    aber niemand kann mit ihm reden."""
    import providers
    for name, p in providers.PROVIDERS.items():
        assert ai_backends.cloud_kind_for(name), f"{name} hat kein nutzbares kind"
        assert p.get("default_model"), f"{name} hat kein default_model"


def test_modul_wahl_folgt_dem_dialekt(monkeypatch):
    import cloud
    import cloud_openai
    monkeypatch.setattr(ai_backends, "status",
                        lambda *a, **k: _status(False, True, provider="claude"))
    assert ai_backends.chat_cloud_module() is cloud
    monkeypatch.setattr(ai_backends, "status",
                        lambda *a, **k: _status(False, True, provider="qwen"))
    assert ai_backends.chat_cloud_module() is cloud_openai
    monkeypatch.setattr(ai_backends, "status",
                        lambda *a, **k: _status(False, True, provider="gibtsnicht"))
    assert ai_backends.chat_cloud_module() is None


def test_env_uebersteuert_die_config(monkeypatch):
    monkeypatch.setenv("ZENTRALE_CHAT_BACKEND", "cloud")
    assert ai_backends.chat_backend() == ai_backends.CLOUD


def test_unsinn_in_der_vorwahl_faellt_auf_auto(monkeypatch):
    monkeypatch.setenv("ZENTRALE_CHAT_BACKEND", "gibtsnicht")
    assert ai_backends.chat_backend() == "auto"


def test_set_chat_backend_lehnt_unsinn_ab():
    with pytest.raises(ValueError):
        ai_backends.set_chat_backend("halbcloud")
