"""
Der Devtools-Bus der Kern-KI.

Zwei Dinge muessen stimmen, sonst ist das Werkzeug schlimmer als keines:

  1. **Er darf das Gespraech nie stoeren.** Ein Debug-Kanal, der einen Turn
     abreissen laesst, kostet echtes Geld und echtes Vertrauen.
  2. **Er muss die Wahrheit zeigen** — vor allem, WO die Cache-Breakpoints
     sitzen. Genau danach schaut man, wenn die Rechnung nicht aufgeht.
"""
import pytest

import kidebug


@pytest.fixture(autouse=True)
def sauberer_bus():
    kidebug._BUF.clear()
    kidebug._SUBS.clear()
    vorher = kidebug.an()
    kidebug.einschalten(True)
    yield
    kidebug.einschalten(vorher)
    kidebug._BUF.clear()
    kidebug._SUBS.clear()


# ── Er darf nie stoeren ────────────────────────────────────────────────

def test_aus_heisst_wirklich_aus():
    """Solange niemand zuschaut, soll nichts gesammelt werden — der volle
    Prompt im Speicher ist nur sinnvoll, wenn ihn jemand liest."""
    kidebug.einschalten(False)
    kidebug.emit("ai.req", modell="x")
    assert kidebug.history() == []


def test_emit_wirft_nie():
    """Auch nicht bei Werten, die sich nicht serialisieren lassen."""
    class Boese:
        def __repr__(self):
            raise RuntimeError("nope")

    assert kidebug.emit("ai.req", ding=Boese()) is not None or True   # kein Wurf


def test_request_wirft_nie_bei_muell():
    kidebug.request(modell="x", schiene="gross",
                    system=None, messages=None, tools=None)
    kidebug.request(modell="x", schiene="gross",
                    system=[{}], messages=[{}], tools=[{}])


def test_ein_langsamer_zuhoerer_bremst_den_chat_nicht():
    """Volle Queue → das Event geht fuer diesen Zuhoerer verloren, nicht der
    Turn."""
    q = kidebug.subscribe()
    for _ in range(q.maxsize + 50):
        kidebug.emit("ai.out", bloecke=["x"])
    assert q.full()
    kidebug.unsubscribe(q)


# ── Er muss die Wahrheit zeigen ────────────────────────────────────────

def test_cache_breakpoints_sind_sichtbar():
    """Die Frage, wegen der man das Terminal aufmacht: liegt der Breakpoint
    wirklich VOR dem Wechselnden?"""
    kidebug.request(
        modell="claude-sonnet-5", schiene="gross",
        system=[{"type": "text", "text": "statisch",
                 "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "was steht an?",
             "cache_control": {"type": "ephemeral", "ttl": "1h"}},
            {"type": "text", "text": "## Jetzt\n16.08."},
        ]}],
        tools=[{"function": {"name": "read_calendar"}}])

    ev = kidebug.history()[-1]
    assert ev["system"][0]["cache"] is True
    bloecke = ev["messages"][0]["bloecke"]
    assert bloecke[0]["cache"] is True      # der User-Text
    assert bloecke[1]["cache"] is False     # das Wechselnde dahinter
    assert ev["tools"] == ["read_calendar"]


def test_beide_dialekte_gehen_durch_denselben_bauer():
    """Der OpenAI-Pfad hat den System-Prompt als String und Messages ohne
    Block-Listen — dasselbe Event muss trotzdem herauskommen."""
    kidebug.request(modell="qwen-plus", schiene="gross",
                    system="statischer kopf",
                    messages=[{"role": "user", "content": "hallo"}],
                    tools=[{"function": {"name": "read_news"}}])
    ev = kidebug.history()[-1]
    assert ev["system"][0]["text"] == "statischer kopf"
    assert ev["messages"][0]["bloecke"][0]["text"] == "hallo"
    assert ev["tools"] == ["read_news"]


def test_tool_ergebnisse_und_denken_werden_lesbar():
    """Was der Chat versteckt, soll hier stehen."""
    class Denk:
        type = "thinking"
        thinking = "kurz ueberlegen"

    assert "kurz ueberlegen" in kidebug._text_von_block(Denk())
    assert "tool_result" in kidebug._text_von_block(
        {"type": "tool_result", "tool_use_id": "t1", "content": "leer"})


def test_historie_ist_gedeckelt():
    for i in range(kidebug._BUF.maxlen + 100):
        kidebug.emit("ai.out", bloecke=[str(i)])
    assert len(kidebug.history()) == kidebug._BUF.maxlen


def test_zuhoerer_bekommen_live():
    q = kidebug.subscribe()
    kidebug.emit("ai.tool", name="read_calendar")
    ev = q.get_nowait()
    assert ev["kind"] == "ai.tool" and ev["name"] == "read_calendar"
    kidebug.unsubscribe(q)
