"""Modell-Profile (core/profil/modelle/, 2026-10-09).

Ein Profil legt sich über die Schiene und darf für EIN Modell (qwen) Prompt,
Werkzeuge und Aufruf-Werte ändern. Was hier vor allem gilt: wer kein Profil
hat (Claude), fährt byte-gleich wie vorher — dasselbe Schienen-Objekt,
derselbe Kopf, dieselben Werkzeuge, derselbe Aufruf.
"""

import copy
import json
import sys
import types

import pytest

import cloud
import cloud_openai
import profil
from profil import gross, modelle


@pytest.fixture
def mit_qwen_profil(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", json.dumps({"qwen-*": "qwen"}))


# ── Zuordnung ──────────────────────────────────────────────────────────

def test_claude_bekommt_kein_profil(mit_qwen_profil):
    for m in ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"):
        assert profil.fuer_backend("cloud", modell=m) is gross


def test_standard_ohne_einstellung_laesst_claude_unberuehrt(monkeypatch):
    monkeypatch.delenv("ZENTRALE_MODELL_PROFILE", raising=False)
    assert profil.fuer_backend("cloud", modell="claude-sonnet-5") is gross
    assert not any(n.startswith("claude") for n in modelle.STANDARD)


def test_ohne_modell_wie_bisher(mit_qwen_profil):
    assert profil.fuer_backend("cloud") is gross
    assert cloud._profil() is gross


def test_qwen_bekommt_profil_ueber_gross(mit_qwen_profil):
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    assert s is not gross
    assert s.PROFIL == "qwen"
    # Die Schiene bleibt gross: Ausführer und Prüfer sind genauso streng.
    assert s.NAME == "gross"
    assert s.MERKMALE == gross.MERKMALE


def test_genauer_name_vor_muster(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE",
                       json.dumps({"qwen-*": "qwen", "qwen-max": "gibtsnicht"}))
    # Genauer Name gewinnt — und ein unbekanntes Profil heißt: keins.
    assert modelle.name_fuer("qwen-max") is None
    assert modelle.name_fuer("qwen-plus") == "qwen"


def test_leere_zuordnung_schaltet_ab(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", "{}")
    assert profil.fuer_backend("cloud", modell="qwen-plus") is gross


def test_kaputte_einstellung_faellt_auf_standard(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", "{kein json")
    assert modelle.zuordnung() == modelle.STANDARD


# ── Claude byte-gleich ────────────────────────────────────────────────

def test_kopf_fuer_claude_byte_gleich(mit_qwen_profil):
    ohne = cloud._static_system(None, tutor_mode=False)
    mit = cloud._static_system(None, tutor_mode=False,
                               schiene=cloud._profil("claude-sonnet-5"))
    assert mit == ohne


def test_profil_veraendert_gross_nicht(mit_qwen_profil):
    vorher_tools = copy.deepcopy(gross.TOOLS)
    vorher_system = gross.system()
    s = profil.fuer_backend("cloud", modell="qwen-plus")
    s.system()
    _ = s.TOOLS
    assert gross.TOOLS == vorher_tools
    assert gross.system() == vorher_system
    assert cloud.cloud_tools() is gross.TOOLS


# ── Der Aufruf ─────────────────────────────────────────────────────────

class _Strom:
    """Gefälschter OpenAI-Client: merkt sich die Aufruf-Argumente, antwortet
    mit einem Text ohne Werkzeug."""

    def __init__(self):
        self.aufrufe = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.aufrufe.append(kw)
        delta = types.SimpleNamespace(content="ok", tool_calls=None,
                                      reasoning_content=None)
        return iter([types.SimpleNamespace(
            usage=None, choices=[types.SimpleNamespace(delta=delta)])])


def _eine_runde(adapter):
    gen = adapter.runde()
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


def test_adapter_ohne_profil_wie_bisher():
    client = _Strom()
    a = cloud_openai._OpenAIAdapter(client, "claude-x", [{"role": "user", "content": "hi"}],
                                    [{"type": "function", "function": {"name": "t"}}])
    _eine_runde(a)
    kw = client.aufrufe[0]
    assert "tool_choice" not in kw and "extra_body" not in kw
    assert kw["temperature"] == cloud_openai._TEMP
    assert kw["max_tokens"] == cloud_openai._MAX_TOKENS


def test_adapter_nimmt_werte_des_profils(monkeypatch):
    attrappe = types.ModuleType("attrappe")
    attrappe.NAME = "attrappe"
    attrappe.TEMPERATUR = 0.1
    attrappe.MAX_TOKENS = 1234
    attrappe.tool_choice = lambda **lage: "required" if lage["nr"] == 0 else None
    s = modelle.ModellSchiene(gross, attrappe)
    client = _Strom()
    a = cloud_openai._OpenAIAdapter(client, "m", [{"role": "user", "content": "hi"}],
                                    [{"type": "function", "function": {"name": "t"}}],
                                    profil=s)
    _eine_runde(a)
    _eine_runde(a)
    erst, dann = client.aufrufe
    assert erst["temperature"] == 0.1 and erst["max_tokens"] == 1234
    assert erst["tool_choice"] == "required"
    assert "tool_choice" not in dann


def test_aufrufer_wert_geht_vor_profil():
    attrappe = types.ModuleType("attrappe")
    attrappe.NAME = "attrappe"
    attrappe.TEMPERATUR = 0.1
    s = modelle.ModellSchiene(gross, attrappe)
    a = cloud_openai._OpenAIAdapter(_Strom(), "m", [], [], temperatur=0.9, profil=s)
    assert a.temperatur == 0.9


def test_profil_ohne_werkzeuge_bietet_kein_tool_choice():
    attrappe = types.ModuleType("attrappe")
    attrappe.NAME = "attrappe"
    attrappe.tool_choice = lambda **lage: "required"
    s = modelle.ModellSchiene(gross, attrappe)
    client = _Strom()
    a = cloud_openai._OpenAIAdapter(client, "m", [{"role": "user", "content": "hi"}],
                                    [], profil=s)
    _eine_runde(a)
    assert "tool_choice" not in client.aufrufe[0]
