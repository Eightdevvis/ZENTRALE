"""Die Zugangsdaten des Adapters (core/adapter_geheim.py): je Eintrag
verschlüsselt, Konto- oder Geräteschlüssel, umschlüsseln, KI-Schlüssel aus
ai_config.json übernehmen (einmalig, beliebig oft, mit Rückfall) — und NIE
in der Datensicherung, die Klartext nach GitHub schickt."""
import importlib.util
import json
import os
import stat

import pytest

import abgleich_auswahl as auswahl
import adapter_geheim as geheim
import ai_config
import konto

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def einst(monkeypatch):
    conf = {}
    monkeypatch.setattr(ai_config, "_config", conf)
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    monkeypatch.setattr(ai_config, "injiziert", set())
    return conf


@pytest.fixture
def angemeldet(monkeypatch):
    from cryptography.fernet import Fernet
    k = Fernet.generate_key()
    monkeypatch.setattr(konto, "angemeldet", lambda: True)
    monkeypatch.setattr(konto, "konto_schluessel", lambda: k)
    return k


def _roh():
    with open(geheim.datei(), encoding="utf-8") as f:
        return json.load(f)


def test_ohne_konto_mit_geraeteschluessel_und_nur_fuer_mich_lesbar():
    assert geheim.setzen("ki/ANTHROPIC_API_KEY", "sk-ant-xyz-1234567890") is True
    assert geheim.lesen("ki/ANTHROPIC_API_KEY") == "sk-ant-xyz-1234567890"
    e = _roh()["eintraege"]["ki/ANTHROPIC_API_KEY"]
    assert e["zu"] == "geraet" and "sk-ant" not in open(geheim.datei()).read()
    assert stat.S_IMODE(os.stat(geheim.datei()).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.environ["ZENTRALE_ADAPTER_SCHLUESSEL"]).st_mode) == 0o600
    assert not geheim.darf_abgleichen()


def test_derselbe_wert_wird_nicht_neu_verschluesselt():
    geheim.setzen("a", "1")
    vorher = _roh()
    assert geheim.setzen("a", "1") is False
    assert _roh() == vorher


def test_anmelden_schluesselt_um_abmelden_zurueck(angemeldet, monkeypatch):
    monkeypatch.setattr(konto, "angemeldet", lambda: False)     # erst ohne Konto
    geheim.setzen("ki/X", "wert")
    assert _roh()["eintraege"]["ki/X"]["zu"] == "geraet"
    monkeypatch.setattr(konto, "angemeldet", lambda: True)
    assert geheim.umschluesseln() == 1
    assert _roh()["eintraege"]["ki/X"]["zu"] == "konto" and geheim.lesen("ki/X") == "wert"
    assert geheim.darf_abgleichen()
    assert geheim.vor_abmelden() == 1
    assert _roh()["eintraege"]["ki/X"]["zu"] == "geraet" and geheim.lesen("ki/X") == "wert"


def test_fremder_schluessel_ist_unlesbar_nicht_kaputt(angemeldet, monkeypatch):
    geheim.setzen("ki/X", "wert")
    from cryptography.fernet import Fernet
    monkeypatch.setattr(konto, "konto_schluessel", lambda: Fernet.generate_key())
    assert geheim.lesen("ki/X") is None
    assert geheim.namen() == ["ki/X"]


def test_ki_schluessel_wandern_einmal_und_beliebig_oft(einst, monkeypatch):
    einst["keys"] = {"ANTHROPIC_API_KEY": "sk-ant-aaaaaaaaaaaaaaaa", "MISTRAL_API_KEY": "m-1", "LEER": ""}
    einst["chat_backend"] = "cloud"
    r = geheim.ki_uebernehmen()
    assert r == {"uebernommen": ["ANTHROPIC_API_KEY", "MISTRAL_API_KEY"], "behalten": []}
    assert "keys" not in einst or not any(einst["keys"].values())
    assert einst["chat_backend"] == "cloud"            # Einstellungen bleiben
    assert geheim.lesen("ki/ANTHROPIC_API_KEY") == "sk-ant-aaaaaaaaaaaaaaaa"
    assert geheim.ki_uebernehmen() == {"uebernommen": [], "behalten": []}


def test_anderer_wert_im_adapter_bleibt_hier_als_rueckfall(einst):
    geheim.setzen("ki/OPENAI_API_KEY", "neu")
    einst["keys"] = {"OPENAI_API_KEY": "alt"}
    assert geheim.ki_uebernehmen() == {"uebernommen": [], "behalten": ["OPENAI_API_KEY"]}
    assert einst["keys"] == {"OPENAI_API_KEY": "alt"}
    assert geheim.lesen("ki/OPENAI_API_KEY") == "neu"


def test_rangfolge_umgebung_vor_adapter_vor_ai_config(einst, monkeypatch):
    geheim.setzen("ki/GROQ_API_KEY", "aus-dem-adapter")
    geheim.setzen("ki/XAI_API_KEY", "aus-dem-adapter")
    monkeypatch.setenv("GROQ_API_KEY", "aus-ai-config")
    ai_config.injiziert.add("GROQ_API_KEY")              # stammt aus ai_config.json
    monkeypatch.setenv("XAI_API_KEY", "echte-umgebung")
    assert geheim.schluessel_einspielen() == ["GROQ_API_KEY"]
    assert os.environ["GROQ_API_KEY"] == "aus-dem-adapter"
    assert os.environ["XAI_API_KEY"] == "echte-umgebung"


def test_neues_geraet_hat_nach_dem_einspielen_eine_ki(einst, monkeypatch):
    """Ein Gerät, das gerade beigetreten ist: kein ai_config-Key, nur der
    Adapter aus der Cloud — providers findet einen Anbieter."""
    import providers
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert providers.configured() is None
    geheim.setzen("ki/ANTHROPIC_API_KEY", "sk-ant-bbbbbbbbbbbbbbbb")
    geheim.schluessel_einspielen()
    assert providers.configured() == "claude"
    monkeypatch.delenv("ANTHROPIC_API_KEY")


# ── Nie in die Datensicherung ──────────────────────────────────────────

def test_geheim_steht_nur_im_abgleich_nie_in_der_sicherung():
    assert "data/adapter/geheim.enc" in auswahl.ABGLEICH
    assert not auswahl.passt("data/adapter/geheim.enc", auswahl.SICHERN)
    for m in auswahl.SICHERN:
        assert not m.startswith("data/adapter/geheim") and m != "data/adapter/**"
    assert set(auswahl.GEHEIM) <= set(auswahl.NUR_ABGLEICH)


def test_daten_sichern_greift_nie_nach_geheimen_dateien(tmp_path):
    """Ein ZENTRALE-Ordner mit allem, was geheim ist — daten_sichern
    sieht nichts davon (Positivliste), auch nicht neben einem Anschluss."""
    spec = importlib.util.spec_from_file_location(
        "daten_sichern", os.path.join(ROOT, "scripts", "daten_sichern.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = tmp_path / "data"
    for rel, inhalt in {"adapter/geheim.enc": "{}", "adapter/geheim.enc.bak": "x",
                        "adapter/geheim.json": "{}", "adapter/bruecke/google-kalender.json": "{}",
                        "adapter/anschluesse/google-kalender.json": "{}",
                        "ai_config.json": '{"keys": {}}', "mail_secrets.enc": "x",
                        "lists.json": "[]"}.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(inhalt)
    gesichert = mod.auswahl(str(tmp_path))
    assert gesichert == ["data/adapter/anschluesse/google-kalender.json", "data/lists.json"]
    for rel in gesichert:
        assert "geheim" not in rel and "secret" not in rel and not rel.endswith(".enc")
