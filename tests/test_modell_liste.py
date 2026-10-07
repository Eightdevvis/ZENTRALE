"""Die Modell-Liste vom Anbieter (core/modell_liste.py, 2026-10-07, Sasha:
„/modell sollte einfach alle anzeigen die available is"), das Budget bis
100 € und der Preis für Modelle, die nicht in der Tabelle stehen.

Kein echtes Netz: _holen_json wird ersetzt.
"""
import json
import os

import pytest

import ki_einstellungen
import modell_liste
import prices
import usage


@pytest.fixture
def netz(monkeypatch, tmp_path):
    """Holen an, Cache in tmp, Antworten nach URL. -> dict der Anfragen."""
    monkeypatch.setenv("ZENTRALE_MODELL_LISTE_HOLEN", "an")
    monkeypatch.setenv("ZENTRALE_MODELL_CACHE_DIR", str(tmp_path))
    antworten, anfragen = {}, []

    def holen(url, kopf):
        anfragen.append((url, dict(kopf)))
        for teil, a in antworten.items():
            if teil in url:
                if isinstance(a, Exception):
                    raise a
                return a(url) if callable(a) else a
        raise OSError("kein Netz")
    monkeypatch.setattr(modell_liste, "_holen_json", holen)
    return {"antworten": antworten, "anfragen": anfragen, "cache": tmp_path}


QWEN = {"data": [{"id": "qwen-plus"}, {"id": "qwen3-max"}, {"id": "text-embedding-v3"},
                 {"id": "qwen-turbo"}, {"id": "paraformer-realtime-v2"},
                 {"id": "wanx2.1-t2i-turbo"}, {"id": "qwen-vl-max"},
                 {"id": "cosyvoice-v1"}, {"id": "qwen2.5-72b-instruct"}]}


def test_openai_kompatibel_holt_filtert_und_sortiert(netz, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    netz["antworten"]["dashscope"] = QWEN
    liste, quelle = modell_liste.holen("qwen")
    assert quelle == "anbieter"
    # Tabelle (Standard, billig) zuerst, dann alphabetisch; nur Chat.
    assert liste == ["qwen-plus", "qwen-turbo", "qwen-vl-max",
                     "qwen2.5-72b-instruct", "qwen3-max"]
    url, kopf = netz["anfragen"][0]
    assert url.endswith("/compatible-mode/v1/models")
    assert kopf == {"Authorization": "Bearer sk-test"}


def test_anthropic_mit_seiten(netz, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")

    def seiten(url):
        if "after_id" not in url:
            return {"data": [{"id": "claude-opus-5", "type": "model"}],
                    "has_more": True, "last_id": "claude-opus-5"}
        return {"data": [{"id": "claude-sonnet-5"}, {"id": "claude-haiku-4-5"}],
                "has_more": False, "last_id": "claude-haiku-4-5"}
    netz["antworten"]["anthropic.com"] = seiten
    liste, quelle = modell_liste.holen("claude")
    assert quelle == "anbieter"
    assert liste == ["claude-sonnet-5", "claude-haiku-4-5", "claude-opus-5"]
    assert netz["anfragen"][0][1]["x-api-key"] == "sk-ant"
    assert "anthropic-version" in netz["anfragen"][0][1]
    assert "after_id=claude-opus-5" in netz["anfragen"][1][0]


def test_cache_24_stunden(netz, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    netz["antworten"]["dashscope"] = QWEN
    modell_liste.holen("qwen", jetzt=1000.0)
    modell_liste.holen("qwen", jetzt=1000.0 + 23 * 3600)
    assert len(netz["anfragen"]) == 1
    datei = netz["cache"] / "modelle.json"
    assert "qwen3-max" in json.loads(datei.read_text())["qwen"]["modelle"]
    modell_liste.holen("qwen", jetzt=1000.0 + 25 * 3600)
    assert len(netz["anfragen"]) == 2


def test_rueckfall_auf_tabelle_und_fehler_wird_gemerkt(netz, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    netz["antworten"]["dashscope"] = OSError("Zeitüberschreitung")
    liste, quelle = modell_liste.holen("qwen", jetzt=5000.0)
    assert (liste, quelle) == (["qwen-plus", "qwen-turbo"], "tabelle")
    modell_liste.holen("qwen", jetzt=5000.0 + 60)
    assert len(netz["anfragen"]) == 1, "offline nicht bei jedem Öffnen warten"
    modell_liste.holen("qwen", jetzt=5000.0 + 11 * 60)
    assert len(netz["anfragen"]) == 2


def test_fehler_nach_erfolg_behaelt_die_alte_liste(netz, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    netz["antworten"]["dashscope"] = QWEN
    modell_liste.holen("qwen", jetzt=0.0)
    netz["antworten"]["dashscope"] = OSError("weg")
    liste, quelle = modell_liste.holen("qwen", jetzt=2 * 86400.0)
    assert quelle == "tabelle" and "qwen3-max" in liste


def test_kaputte_antwort_und_leere_liste(netz, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    netz["antworten"]["dashscope"] = {"data": []}
    assert modell_liste.holen("qwen")[1] == "tabelle"


def test_ohne_schluessel_oder_ausgeschaltet_kein_netz(netz, monkeypatch):
    assert modell_liste.holen("qwen")[1] == "tabelle"
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setenv("ZENTRALE_MODELL_LISTE_HOLEN", "aus")
    assert modell_liste.holen("qwen") == (["qwen-plus", "qwen-turbo"], "tabelle")
    assert netz["anfragen"] == []


def test_gemini_namen_ohne_models_vorsatz(netz, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    netz["antworten"]["googleapis"] = {"data": [{"id": "models/gemini-2.5-pro"},
                                                {"id": "models/text-embedding-004"}]}
    assert modell_liste.holen("gemini")[0] == ["gemini-2.5-pro"]


@pytest.mark.parametrize("name,chat", [
    ("gpt-4o", True), ("text-embedding-3-small", False), ("whisper-1", False),
    ("tts-1-hd", False), ("dall-e-3", False), ("omni-moderation-latest", False),
    ("gpt-4o-realtime-preview", False), ("llama-guard-3-8b", False),
    ("mistral-embed", False), ("qwen-vl-max", True), ("deepseek-reasoner", True),
    ("", False),
])
def test_chat_filter(name, chat):
    assert modell_liste.ist_chat(name) is chat


def test_einstellungen_liefern_die_ganze_liste(netz, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    netz["antworten"]["dashscope"] = QWEN
    stand = ki_einstellungen.lesen()
    qwen = next(a for a in stand["anbieter_liste"] if a["name"] == "qwen")
    assert "qwen3-max" in qwen["modelle"] and qwen["modelle_quelle"] == "anbieter"
    andere = next(a for a in stand["anbieter_liste"] if a["name"] == "grok")
    assert andere["modelle_quelle"] == "tabelle"


def test_route_liefert_die_liste(netz, monkeypatch):
    from ui.app import app
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    netz["antworten"]["dashscope"] = QWEN
    d = app.test_client().get("/api/ai/einstellungen").get_json()
    qwen = next(a for a in d["anbieter_liste"] if a["name"] == "qwen")
    assert "qwen2.5-72b-instruct" in qwen["modelle"]
    assert "sk-test" not in json.dumps(d)


def test_cache_liegt_nicht_im_echten_cache_oder_data():
    pfad = os.path.realpath(modell_liste._cache_pfad())
    assert not pfad.startswith(os.path.realpath(os.path.expanduser("~/.cache")))
    assert "/codicus/ZENTRALE/data/" not in pfad


# ── Budget bis 100 € ───────────────────────────────────────────────────

@pytest.mark.parametrize("wert,euro", [("100", 100.0), ("99,99", 99.99), (0.5, 0.5),
                                       ("aus", None)])
def test_budget_bis_100(wert, euro):
    assert ki_einstellungen.budget_lesen(wert) == euro


@pytest.mark.parametrize("wert", ["100,01", "101", 1000, "0", "-5"])
def test_budget_ueber_100_oder_null_geht_nicht(wert):
    with pytest.raises(ki_einstellungen.Ungueltig) as e:
        ki_einstellungen.budget_lesen(wert)
    assert "100 €" in str(e.value)


# ── Preis für unbekannte Modelle ───────────────────────────────────────

def test_unbekanntes_modell_kostet_nicht_null():
    assert prices.euro("qwen3-irgendwas", input_tokens=1_000_000) > 0
    assert prices.fuer("qwen3-irgendwas") == prices.UNBEKANNT


def test_datums_fassung_findet_den_grundpreis():
    assert prices.fuer("claude-sonnet-5-20260101") == prices.PREISE["claude-sonnet-5"]
    assert prices.bekannt("gpt-4o-2024-08-06")
    assert prices.fuer("models/gemini-2.5-flash") == prices.PREISE["gemini-2.5-flash"]


def test_teure_familie_wird_nicht_unterschaetzt():
    assert prices.fuer("claude-opus-9")["out"] >= prices.PREISE["claude-opus-5"]["out"]
    assert prices.fuer("claude-fable-7")["out"] >= prices.PREISE["claude-fable-5"]["out"]


def test_unbekannter_preis_steht_einmal_im_log(monkeypatch):
    import state
    zeilen = []
    monkeypatch.setattr(state, "push_log", zeilen.append)
    usage._unbekannt_gemeldet.discard("neu-modell-x")
    usage.buchen("neu-modell-x", input_tokens=10)
    usage.buchen("neu-modell-x", input_tokens=10)
    usage.buchen("gpt-4o", input_tokens=10)
    treffer = [z for z in zeilen if "neu-modell-x" in z]
    assert len(treffer) == 1 and "nicht in der Preistabelle" in treffer[0]
    assert not any("gpt-4o" in z for z in zeilen)
