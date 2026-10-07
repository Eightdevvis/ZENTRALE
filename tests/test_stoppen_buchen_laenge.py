"""Nachbesserungen nach Sashas Durchsicht (2026-10-07):

* Gestoppte Antworten bei OpenAI-kompatiblen Anbietern werden geschätzt
  gebucht (vorher: gar nicht).
* Der Stoppknopf erreicht einen laufenden run_code: die Prozessgruppe stirbt
  sofort (echter bwrap-Lauf, übersprungen ohne bwrap).
* Eine Nachricht bis 20 000 Zeichen kommt vollständig bei der KI an; die
  Route lehnt Längeres mit Klartext ab.
"""
import json
import os
import shutil
import threading
import time
from types import SimpleNamespace

import pytest

import ai_backends
import cloud_openai
import sandbox
import usage
import werkzeug_schleife
import zug


# ── Buchung beim Stoppen ───────────────────────────────────────────────

def _strom(abbruch, stuecke):
    class Strom:
        def __iter__(self):
            for i, (text, denk) in enumerate(stuecke):
                d = SimpleNamespace(content=text, tool_calls=None,
                                    reasoning_content=denk)
                yield SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=d)])
            abbruch.set()
            yield SimpleNamespace(usage=None, choices=[])

        def close(self):
            pass
    return Strom()


def test_gestoppt_ohne_zahlen_wird_geschaetzt_gebucht(monkeypatch):
    abbruch = threading.Event()
    gebucht, log = [], []
    monkeypatch.setattr(usage, "buchen",
                        lambda m, **k: gebucht.append((m, k)) or 0.0123)
    import state
    monkeypatch.setattr(state, "push_log", log.append)
    msgs = [{"role": "system", "content": "s" * 3500},
            {"role": "user", "content": "frage"}]
    tools = [{"type": "function", "function": {"name": "x", "description": "d" * 350}}]
    stuecke = [("A" * 350, None), (None, "D" * 350)]
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **k: _strom(abbruch, stuecke))))
    a = cloud_openai._OpenAIAdapter(client, "qwen-plus", msgs, tools, abbruch=abbruch)
    with pytest.raises(werkzeug_schleife.Gestoppt):
        list(a.runde())
    assert len(gebucht) == 1
    modell, k = gebucht[0]
    assert modell == "qwen-plus" and k["geschaetzt"] is True
    gesendet = len(json.dumps(msgs, ensure_ascii=False)) + len(json.dumps(tools, ensure_ascii=False))
    assert k["input_tokens"] == int(gesendet / 3.5)
    assert k["output_tokens"] == int(700 / 3.5)       # Text + Denken
    assert any("geschätzt" in z for z in log)


def test_geschaetzt_steht_im_eigenen_topf(monkeypatch, tmp_path):
    monkeypatch.setattr(usage, "_FILE", str(tmp_path / "u.json"))
    usage.buchen("qwen-plus", input_tokens=1000, output_tokens=100, geschaetzt=True)
    usage.buchen("qwen-plus", input_tokens=1000, output_tokens=100)
    d = json.loads((tmp_path / "u.json").read_text())
    monat = next(iter(d["monate"]))
    assert d["monate"][monat]["calls"] == 2
    assert d["geschaetzt"][monat]["calls"] == 1
    assert d["geschaetzt"][monat]["euro"] > 0


def test_mit_zahlen_wird_nicht_geschaetzt(monkeypatch):
    """Kamen die Zahlen schon (include_usage), wird wie immer gebucht."""
    abbruch = threading.Event()
    gebucht = []
    monkeypatch.setattr(usage, "buchen", lambda m, **k: gebucht.append(k) or 0.0)

    class Strom:
        def __iter__(self):
            d = SimpleNamespace(content="x", tool_calls=None, reasoning_content=None)
            yield SimpleNamespace(usage=SimpleNamespace(prompt_tokens=50, completion_tokens=5,
                                                        prompt_tokens_details=None),
                                  choices=[SimpleNamespace(delta=d)])
            abbruch.set()
            yield SimpleNamespace(usage=None, choices=[])

        def close(self):
            pass
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **k: Strom())))
    a = cloud_openai._OpenAIAdapter(client, "qwen-plus", [{"role": "system", "content": "s"}],
                                    [], abbruch=abbruch)
    with pytest.raises(werkzeug_schleife.Gestoppt):
        list(a.runde())
    assert gebucht == [{"input_tokens": 50, "output_tokens": 5, "cache_read": 0}]


# ── run_code stoppen ───────────────────────────────────────────────────

braucht_bwrap = pytest.mark.skipif(not sandbox.verfuegbar(),
                                   reason="bwrap fehlt oder startet nicht")


@braucht_bwrap
def test_stopp_toetet_einen_laufenden_prozess_sofort():
    abbruch = threading.Event()
    threading.Timer(0.5, abbruch.set).start()
    start = time.monotonic()
    erg = sandbox.ausfuehren(
        "open('/arbeit/lebt', 'w').write('1')\n"
        "import time\nfor i in range(600):\n"
        "    time.sleep(0.1)\n    open('/arbeit/lebt', 'w').write(str(i))\n",
        zeitlimit_s=60, abbruch=abbruch)
    dauer = time.monotonic() - start
    assert dauer < 5, "nicht erst nach dem Zeitlimit"
    assert erg["gestoppt"] and erg["abgebrochen"]
    assert "vom Nutzer gestoppt" in erg["fehler"]
    assert "VOM NUTZER GESTOPPT" in sandbox.als_text(erg)
    # Der Prozess ist wirklich weg: die Datei ändert sich nicht mehr.
    pfad = os.path.join(erg["ordner"], "lebt")
    stand = open(pfad).read()
    time.sleep(0.5)
    assert open(pfad).read() == stand
    shutil.rmtree(erg["ordner"], ignore_errors=True)


@braucht_bwrap
def test_stopp_ueber_den_zug_erreicht_run_code():
    """Der Weg wie im Betrieb: Route → zug(abbruch) → run_code → sandbox."""
    import ki_werkzeuge
    abbruch = threading.Event()
    threading.Timer(0.5, abbruch.set).start()
    marke = zug.beginnen("g-stopp", abbruch=abbruch)
    try:
        start = time.monotonic()
        text = ki_werkzeuge._verteilen(
            "run_code", {"code": "sleep 100", "sprache": "shell", "zeitlimit": 60})
    finally:
        zug.beenden(marke)
    assert time.monotonic() - start < 5
    assert "VOM NUTZER GESTOPPT" in text


def test_ohne_stopp_bleibt_das_zeitlimit(monkeypatch):
    """_warten: Zeit um → 'zeit', Signal → 'gestoppt', fertig → rc."""
    class Proc:
        def __init__(self, ende):
            self.ende = ende

        def wait(self, timeout=None):
            if time.monotonic() >= self.ende:
                return 0
            import subprocess
            time.sleep(timeout)
            raise subprocess.TimeoutExpired("x", timeout)
    assert sandbox._warten(Proc(time.monotonic() + 10), 0.3, None) == (None, "zeit")
    ev = threading.Event()
    ev.set()
    assert sandbox._warten(Proc(time.monotonic() + 10), 5, ev) == (None, "gestoppt")
    assert sandbox._warten(Proc(time.monotonic()), 5, None) == (0, None)


# ── 20 000 Zeichen kommen an ───────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    return app.test_client()


def test_20000_zeichen_kommen_ungekuerzt_beim_anbieter_an(client, monkeypatch):
    """Der ganze Weg bis zum Anthropic-Request: Route → Gespräch → Verlauf →
    cloud._prepare_messages."""
    import cloud
    import kern
    gesehen = {}

    def chat(history, **k):
        gesehen["msgs"] = cloud._prepare_messages(history)
        yield "ok"
    monkeypatch.setattr(kern, "chat", chat)
    text = "".join("wort%d " % i for i in range(4000))[:20000]
    assert len(text) == 20000
    r = client.post("/api/chat", json={"message": text})
    r.get_data()
    letzte = gesehen["msgs"][-1]["content"][0]["text"]
    assert letzte == text


def test_zu_lange_nachricht_wird_abgelehnt(client):
    r = client.post("/api/chat", json={"message": "x" * 20001})
    assert r.status_code == 400
    fehler = r.get_json()["error"]
    assert "zu lang" in fehler and "20.000" in fehler and "/anhang" in fehler
