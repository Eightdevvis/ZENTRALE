"""
Kosten sichtbar machen und deckeln — plus der Multi-Provider-Schnitt.

Sasha ist knapp bei Kasse. Zwei Dinge müssen deshalb stimmen:

  1. **Die Zahl.** Ohne €-Anzeige nach jedem Turn ist jede Sparmaßnahme
     Bauchgefühl, und der Deckel hätte nichts, worauf er prüft.
  2. **Der Deckel fällt zurück, statt abzuschalten.** Eine Assistentin, die
     ab dem 20. schweigt, ist kaputt. Eine, die ab dem 20. billiger denkt,
     ist immer noch da.

Dazu die Architektur-Zusage: auf einen anderen Anbieter (Grok, GPT, Gemini …)
umzuschalten soll eine Config-Zeile sein, kein Umbau.
"""
import pytest

import ai_backends
import prices
import providers
import usage


@pytest.fixture(autouse=True)
def leere_buchhaltung(tmp_path, monkeypatch):
    """Buchhaltung in ein Wegwerf-Verzeichnis lenken — die echte
    data/ai_usage.json geht Tests nichts an."""
    monkeypatch.setattr(usage, "_FILE", str(tmp_path / "ai_usage.json"))
    yield


@pytest.fixture
def keine_env(monkeypatch):
    for p in providers.PROVIDERS.values():
        monkeypatch.delenv(p["key_env"], raising=False)
    for v in ("ZENTRALE_CHAT_PROVIDER", "ZENTRALE_CLOUD_MODEL",
              "ZENTRALE_CHAT_EFFORT", "ZENTRALE_CHAT_BACKEND",
              "ZENTRALE_CLOUD_PROVIDER"):
        monkeypatch.delenv(v, raising=False)


# ── Die Testsuite darf die echte Buchhaltung nicht anfassen ────────────

def test_die_suite_bucht_nicht_in_die_echte_datei():
    """Passiert, ohne dass es jemand merkt: die Cloud-Tests fahren einen
    gefälschten API-Client mit erfundenen Token-Zahlen, und der läuft ganz
    normal durch usage.buchen(). Ein Testlauf schrieb so 345 Claude-Calls für
    0,20 € in data/ai_usage.json — die Anzeige lügt, und der Budget-Deckel
    rechnet gegen Geld, das nie jemand ausgegeben hat.

    Abgesichert in tests/conftest.py über ZENTRALE_USAGE_FILE."""
    import os
    ziel = os.environ.get("ZENTRALE_USAGE_FILE")
    assert ziel, "conftest.py setzt ZENTRALE_USAGE_FILE nicht mehr"
    repo_data = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data"))
    assert not os.path.abspath(ziel).startswith(repo_data)


# ── Preistabelle ───────────────────────────────────────────────────────

def test_jeder_provider_hat_einen_preis_fuer_sein_billigmodell():
    """Die Konsolidierung laeuft ueber cheap_model und feuert OHNE Sashas
    Zutun. Ein Modell ohne Preis waere genau dort ein blinder Fleck."""
    for name in providers.PROVIDERS:
        mdl = providers.cheap_model(name)
        assert mdl, f"{name}: kein cheap_model und kein default_model"
        assert prices.bekannt(mdl), \
            f"{name}: kein Preis für {mdl!r} in core/prices.py"


def test_das_billigmodell_ist_auch_wirklich_billiger():
    """Sonst ist die Umstellung ein Kommentar ohne Wirkung."""
    for name, p in providers.PROVIDERS.items():
        if not p.get("cheap_model"):
            continue
        billig = prices.fuer(p["cheap_model"])
        normal = prices.fuer(p["default_model"])
        assert billig["out"] < normal["out"], name


def test_ohne_eintrag_faellt_cheap_model_auf_das_default_zurueck():
    """Lieber teurer konsolidieren als gar nicht — ohne Extraktor merkt sich
    die KI nichts, und das ist der Punkt der ganzen Sache."""
    assert providers.cheap_model("mistral") == \
        providers.PROVIDERS["mistral"]["default_model"]


def test_jeder_provider_hat_einen_preis_fuer_sein_default_modell():
    """Sonst zeigt die €-Anzeige beim ersten Umschalten Unsinn — und der
    Deckel rechnet gegen eine Fantasiezahl."""
    for name, p in providers.PROVIDERS.items():
        mdl = p.get("default_model")
        assert prices.bekannt(mdl), \
            f"{name}: kein Preis für {mdl!r} in core/prices.py"


def test_unbekanntes_modell_macht_den_deckel_nicht_blind():
    """Eine fehlende Preiszeile darf nicht dazu führen, dass ein Turn als
    gratis verbucht wird — sonst schützt der Deckel ausgerechnet dann nicht,
    wenn etwas Neues läuft."""
    assert not prices.bekannt("brandneu-3000")
    assert prices.euro("brandneu-3000", input_tokens=1_000_000) > 0


def test_cache_lesen_ist_billiger_als_frischer_input():
    voll = prices.euro("claude-sonnet-5", input_tokens=1_000_000)
    ausm_cache = prices.euro("claude-sonnet-5", cache_read=1_000_000)
    assert ausm_cache < voll / 5          # Anthropic: 10 %


def test_ausgabe_ist_der_teure_posten():
    """Der Grund, warum `effort` der größte Hebel ist."""
    rein = prices.euro("claude-opus-5", input_tokens=100_000)
    raus = prices.euro("claude-opus-5", output_tokens=100_000)
    assert raus == pytest.approx(rein * 5, rel=0.01)


def test_billigstes_modell_wird_gefunden():
    assert prices.billigstes(["claude-opus-5", "qwen-turbo",
                              "claude-sonnet-5"]) == "qwen-turbo"
    assert prices.billigstes([]) is None


# ── Buchhaltung ────────────────────────────────────────────────────────

def test_buchen_summiert_tag_und_monat():
    a = usage.buchen("claude-sonnet-5", input_tokens=1000, output_tokens=500)
    b = usage.buchen("claude-sonnet-5", input_tokens=1000, output_tokens=500)
    assert a > 0 and b == pytest.approx(a)
    assert usage.heute_euro() == pytest.approx(a + b)
    assert usage.monat_euro() == pytest.approx(a + b)
    assert usage.uebersicht()["calls_heute"] == 2


def test_buchen_trennt_nach_modell():
    usage.buchen("claude-opus-5", output_tokens=1000)
    usage.buchen("qwen-plus", output_tokens=1000)
    modelle = usage.uebersicht()["modelle"]
    assert set(modelle) == {"claude-opus-5", "qwen-plus"}
    # Teuerstes zuerst - beim Draufschauen soll sofort klar sein, wo das Geld
    # hingeht.
    assert list(modelle)[0] == "claude-opus-5"


def test_kaputte_buchhaltung_reisst_kein_gespraech_ab(monkeypatch):
    monkeypatch.setattr(usage, "_schreiben",
                        lambda d: (_ for _ in ()).throw(OSError("platte voll")))
    assert usage.buchen("claude-sonnet-5", output_tokens=100) > 0


# ── Budget ─────────────────────────────────────────────────────────────

@pytest.fixture
def budget(monkeypatch):
    """Deckel setzen, ohne die echte Config anzufassen."""
    werte = {}

    def setting(name, default=None):
        return werte.get(name, default)

    monkeypatch.setattr(ai_backends.ai_config, "setting", setting)
    return werte


def test_ohne_deckel_immer_ok(budget):
    usage.buchen("claude-opus-5", output_tokens=10_000_000)
    assert ai_backends.budget_lage()["status"] == "ok"


def test_deckel_warnt_ab_80_prozent(budget):
    budget["budget_monat_euro"] = 10.0
    usage.buchen("claude-opus-5", output_tokens=370_000)   # ~8,50 €
    lage = ai_backends.budget_lage()
    assert 0.8 <= lage["anteil"] < 1.0
    assert lage["status"] == "warn"


def test_deckel_erreicht_meldet_over(budget):
    budget["budget_monat_euro"] = 1.0
    usage.buchen("claude-opus-5", output_tokens=200_000)   # ~4,60 €
    assert ai_backends.budget_lage()["status"] == "over"


def test_ueber_budget_faellt_auf_den_billigsten_anbieter_zurueck(
        budget, keine_env, monkeypatch):
    """Der Kern der Sache: NICHT abschalten, sondern billiger weiterreden."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "x")
    budget["chat_provider"] = "claude"

    # Noch im Budget → die ausdrückliche Wahl gilt.
    budget["budget_monat_euro"] = 100.0
    assert ai_backends.cloud_provider() == "claude"

    # Budget aufgebraucht → billigster erreichbarer Anbieter.
    budget["budget_monat_euro"] = 0.01
    usage.buchen("claude-opus-5", output_tokens=100_000)
    assert ai_backends.cloud_provider() == "qwen"


def test_ueber_budget_ohne_alternative_schaltet_nicht_ab(
        budget, keine_env, monkeypatch):
    """Gibt es nur einen Anbieter, bleibt er - lieber teuer weiterreden als
    stumm dastehen. Die Warnung sieht Sasha im Titel."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    budget["chat_provider"] = "claude"
    budget["budget_monat_euro"] = 0.01
    usage.buchen("claude-opus-5", output_tokens=100_000)
    assert ai_backends.cloud_provider() == "claude"


# ── Multi-Provider: umschalten ist eine Config-Zeile ───────────────────

def test_alle_anbieter_sind_bedienbar():
    """Jeder Eintrag in der Registry muss von einem der beiden Cloud-Module
    bedient werden können - sonst steht dort ein Anbieter, den man wählen
    kann und der dann nicht geht."""
    for name in providers.PROVIDERS:
        assert ai_backends.cloud_kind_for(name) in ("anthropic", "openai_compat")


def test_die_neuen_anbieter_sind_da():
    for name in ("grok", "gemini", "openai", "deepseek", "groq"):
        assert name in providers.PROVIDERS
        assert providers.PROVIDERS[name]["kind"] == "openai_compat", \
            "die sprechen alle OpenAI-kompatibel - dafuer gibt es genau EIN Modul"


def test_jeder_anbieter_steht_in_der_praeferenz():
    """Sonst faellt er bei 'auto' hinten runter, ohne dass es jemand merkt."""
    for name in providers.PROVIDERS:
        assert name in providers.PREFERENCE


def test_modell_wird_pro_anbieter_gespeichert(budget, keine_env):
    """`claude-opus-5` bedeutet Grok nichts. Ein Wechsel hin und zurueck darf
    die Modellwahl nicht vergessen."""
    budget["chat_models"] = {"claude": "claude-opus-5", "grok": "grok-4"}
    assert ai_backends.chat_model("claude") == "claude-opus-5"
    assert ai_backends.chat_model("grok") == "grok-4"
    # ohne gespeicherte Wahl: das default_model des Anbieters
    assert ai_backends.chat_model("gemini") == \
        providers.PROVIDERS["gemini"]["default_model"]


def test_ausdrueckliche_anbieterwahl_ohne_key_taeuscht_nichts_vor(
        budget, keine_env, monkeypatch):
    """Still auf einen anderen Anbieter ausweichen waere gefaehrlich - wohin
    die Daten gehen, ist keine Nebensache."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "x")
    budget["chat_provider"] = "grok"          # kein XAI_API_KEY gesetzt
    assert ai_backends.cloud_provider() is None


def test_auto_nimmt_den_ersten_mit_key(budget, keine_env, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "x")
    budget["chat_provider"] = "auto"
    assert ai_backends.cloud_provider() == "qwen"


# ── Effort ─────────────────────────────────────────────────────────────

def test_effort_default_ist_sparsam(budget, keine_env):
    """Auf Opus 5 ist Denken per Default an und zaehlt als Output - der
    teuerste Token. Default 'low' ist eine Geld-Entscheidung."""
    assert ai_backends.chat_effort() == "low"


def test_effort_nimmt_nur_gueltige_stufen(budget, keine_env):
    budget["chat_effort"] = "voll_aufdrehen"
    assert ai_backends.chat_effort() == "low"
    with pytest.raises(ValueError):
        ai_backends.set_chat_effort("voll_aufdrehen")
