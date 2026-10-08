"""Der Tutor fährt auf der EINEN Straße des Kerns (2026-10-08).

Vorher: eigene Anbieter-Liste (tutor/providers.py) und zwei eigene
Cloud-Schleifen. Diese Tests zeigen, dass (1) kern.fahrzeug() aus Namen +
Modell den richtigen Weg auflöst, (2) kern.fahren() die Regler des Tutors
bis zum Anbieter durchreicht, (3) ein echter Tutor-Zug über die echte
cloud_openai-Schleife läuft (gefälschter Client, kein Geld), und (4) es nur
noch eine Anbieter-Liste gibt.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ai                # noqa: E402
import ai_backends       # noqa: E402
import cloud             # noqa: E402
import cloud_openai      # noqa: E402
import kern              # noqa: E402
import providers         # noqa: E402

from tests.test_cloud_openai import FakeClient, _text, _tool   # noqa: E402


# ── 1. fahrzeug() ──────────────────────────────────────────────────────

def test_fahrzeug_lokal():
    fz = kern.fahrzeug("local")
    assert fz.art == "ollama" and fz.anbieter == "local" and fz.modell is None


def test_fahrzeug_cloud_nimmt_eingestelltes_modell(monkeypatch):
    monkeypatch.setattr(ai_backends, "chat_model", lambda name=None: "qwen-max")
    fz = kern.fahrzeug("qwen")
    assert (fz.art, fz.modell) == ("openai_compat", "qwen-max")
    assert kern.fahrzeug("qwen", "qwen-turbo").modell == "qwen-turbo", \
        "ein ausdrückliches Modell geht vor"
    assert kern.fahrzeug("claude", "claude-haiku-4-5").art == "anthropic"


def test_fahrzeug_auto_folgt_der_aktuellen_wahl(monkeypatch):
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: None)
    assert kern.fahrzeug().art == "ollama", "keine Cloud → lokal"
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "qwen")
    monkeypatch.setattr(ai_backends, "chat_model", lambda name=None: "qwen-plus")
    assert kern.fahrzeug("auto").anbieter == "qwen"


def test_unbekannter_anbieter_gibt_fehler_statt_absturz():
    fz = kern.fahrzeug("gibtsnicht")
    assert fz.art is None
    ev = list(kern.fahren(fz, [], system="x", tools=[], tool_executor=None))
    assert len(ev) == 1 and "gibtsnicht" in ev[0]["fehler"]


# ── 2. fahren() reicht die Regler durch ────────────────────────────────

def _fang(monkeypatch, modul, name="chat_stream"):
    gesehen = {}

    def fake(verlauf, **kw):
        gesehen.update(kw, verlauf=verlauf)
        yield "ok"
    monkeypatch.setattr(modul, name, fake)
    return gesehen


def test_fahren_openai_bekommt_deckel_und_temperatur(monkeypatch):
    g = _fang(monkeypatch, cloud_openai)
    out = list(kern.fahren(kern.Fahrzeug("qwen", "openai_compat", "qwen-plus"),
                           [{"role": "user", "content": "hola"}], system="S",
                           tools=[{"x": 1}], tool_executor=print,
                           max_tokens=140, temperatur=0.4))
    assert out == ["ok"]
    assert g["provider"] == "qwen" and g["model"] == "qwen-plus"
    assert g["max_tokens"] == 140 and g["temperatur"] == 0.4
    assert g["system"] == "S" and g["tools"] == [{"x": 1}]


def test_fahren_anthropic_bekommt_effort(monkeypatch):
    g = _fang(monkeypatch, cloud)
    list(kern.fahren(kern.Fahrzeug("claude", "anthropic", "claude-sonnet-5"), [],
                     system="S", tools=[], tool_executor=None,
                     max_tokens=2000, effort="low"))
    assert g["effort"] == "low" and g["max_tokens"] == 2000
    assert g["tools"] == [], "leere Liste = fremdes Tool-Set, NICHT die Kern-Werkzeuge"


def test_fahren_lokal_nie_mit_kern_werkzeugen(monkeypatch):
    """tools=None hieße im Kern: voller Chat mit Sashas Gedächtnis. fahren()
    macht daraus immer eine Liste."""
    g = _fang(monkeypatch, ai)
    list(kern.fahren(kern.fahrzeug("local"), [], system="S", tools=None,
                     tool_executor=None))
    assert g["tools"] == []


# ── 3. Ein echter Tutor-Zug über die echte Schleife ────────────────────

@pytest.fixture
def tutor_welt(tmp_path, monkeypatch):
    from tutor import config, memory, session, srs, staende, tools
    root = str(tmp_path)
    monkeypatch.setattr(tools, "_DATA_ROOT", root)
    monkeypatch.setattr(memory, "_DATA_DIR", root)
    monkeypatch.setattr(srs, "_DATA_ROOT", root)
    monkeypatch.setattr(config, "_overrides", {})
    monkeypatch.setattr(memory, "remember", lambda *a, **k: None)
    sid = staende.anlegen(root, "T", lang="es", level=0)
    staende.waehlen(root, sid)
    config.set_override("provider", "qwen")
    config.set_override("model", "qwen-plus")
    session.deactivate()
    session.activate()
    yield session
    session.deactivate()


def test_tutor_zug_faehrt_ueber_cloud_openai(tutor_welt, monkeypatch):
    c = FakeClient([_tool("express", '{"action": "wave"}'),
                    _text("¡Ho", "la!")])
    monkeypatch.setattr(cloud_openai, "_get_client", lambda prov: c)
    out = list(tutor_welt.respond_stream("hola"))
    assert "".join(out) == "¡Hola!", "nur Text ans Zimmer, keine Events"
    assert tutor_welt.room_state()["gesture"] == "wave", \
        "das Tutor-Werkzeug lief über die gemeinsame Schleife"
    erste = c.calls[0]
    assert erste["max_tokens"] == 140, "der harte Deckel gegen Monologe"
    assert erste["temperature"] == 0.4
    assert erste["model"] == "qwen-plus"
    namen = {t["function"]["name"] for t in erste["tools"]}
    assert "express" in namen and "read_calendar" not in namen, \
        "nur die Tutor-Werkzeuge, nie die des Kerns"
    alles = str(erste["messages"])
    assert "## Jetzt" not in alles, "kein deutscher Jetzt-Block im Tutor"
    assert erste["messages"][0]["role"] == "system"
    assert "Lucía" in erste["messages"][0]["content"]


def test_tutor_cloud_fehler_kommt_nicht_als_rede(tutor_welt, monkeypatch):
    class Kaputt:
        chat = type("C", (), {"completions": type("X", (), {
            "create": staticmethod(lambda **k: (_ for _ in ()).throw(
                RuntimeError("401 kaputt")))})()})()
    monkeypatch.setattr(cloud_openai, "_get_client", lambda prov: Kaputt())
    out = list(tutor_welt.respond_stream("hola"))
    assert out == [], "ein Fehler darf nie als ihre Aussage vorgelesen werden"


# ── 4. Nur noch eine Anbieter-Liste ────────────────────────────────────

def test_keine_zweite_anbieterliste_im_tutor():
    weg = ["providers.py", "cloud.py", "openai_compat.py"]
    da = [f for f in weg if os.path.exists(os.path.join(ROOT, "tutor", f))]
    assert not da, f"alte Tutor-Anbieter-Module wieder da: {da}"


def test_tutor_liste_kommt_aus_dem_kern():
    from tutor import anbieter
    namen = [p["name"] for p in anbieter.liste()]
    assert namen[0] == "local"
    assert set(namen[1:]) == set(providers.PROVIDERS)


def test_datenschutz_flagge_aus_dem_kern():
    from tutor import anbieter
    assert anbieter.trains_on_data("deepseek") is True
    assert anbieter.trains_on_data("qwen") is False
    assert anbieter.trains_on_data("local") is False
    assert anbieter.trains_on_data("groq") is True, "unverifiziert zählt als ja"
    assert anbieter.trains_on_data("gibtsnicht") is True


def test_unbekannter_tutor_anbieter_faellt_auf_lokal(tutor_welt):
    from tutor import config
    config.set_override("provider", "mistral_alt_xyz")
    _prof, pname, prov, _m = tutor_welt._resolve()
    assert pname == "local" and prov["kind"] == "ollama"


def test_gedaechtnis_verdichtung_nie_im_vollen_chat(monkeypatch):
    """Bis 2026-10-08: lokal ai.chat_stream(tools=None) = voller Chat mit
    Sashas Graph und Auto-Save in sein Gedächtnis."""
    from tutor import memory
    g = _fang(monkeypatch, ai)
    memory._distill("local", "qwen", "qwen-plus", "notizen")
    assert g["tools"] == [] and "system" in g


def test_gedaechtnis_verdichtung_cloud_ueber_jeden_anbieter(monkeypatch):
    """Früher nur OpenAI-kompatibel; ein Claude-Tutor verdichtete nie."""
    from tutor import memory
    g = _fang(monkeypatch, cloud)
    assert memory._distill("cloud", "claude", None, "notizen") == "ok"
    assert g["tools"] == []
