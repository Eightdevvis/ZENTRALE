"""
Prüfstand-Kosten getrennt von Sashas Chat (2026-10-09).

Sasha: „ich will NICH sehen was du zum testen nutzt, jedenfalls nich
gemischt mit der chat ausgabe." Prüfstand-Läufe hatten seinen Monatsdeckel
gerissen, sein Chat fiel auf qwen-plus zurück. Geprüft wird hier:
  - core/usage.py bucht nach Herkunft (chat oben, andere in eigenem Topf),
    alte Dateien gelten als chat; Deckel und Anzeige sehen nur chat;
  - der Prüfstand bucht über einen Prozess-Kontext in seinen Topf;
  - das Umbuch-Skript für die alten Läufe (nur zeigen; wirklich mit Sicherung,
    doppelt ausführen bucht nichts doppelt).
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import ai_backends  # noqa: E402
import usage  # noqa: E402
from pruefstand_teile import kind  # noqa: E402

import pruefstand_umbuchen as umb  # noqa: E402


@pytest.fixture
def buch(tmp_path, monkeypatch):
    """Eigene Buchhaltung je Test, Herkunft danach wieder chat."""
    datei = tmp_path / "ai_usage.json"
    monkeypatch.setattr(usage, "_FILE", str(datei))
    alt = usage.herkunft_setzen(usage.CHAT)
    yield datei
    usage.herkunft_setzen(alt)


def test_ohne_herkunft_bucht_wie_immer_in_den_chat(buch):
    eur = usage.buchen("claude-sonnet-5", output_tokens=10_000)
    d = json.loads(buch.read_text())
    assert usage.monat_euro() == pytest.approx(eur)
    assert "herkunft" not in d and d["modelle"]["claude-sonnet-5"]["calls"] == 1


def test_pruefstand_bucht_in_den_eigenen_topf_und_nicht_in_den_chat(buch):
    usage.buchen("claude-sonnet-5", output_tokens=1_000)
    chat = usage.monat_euro()
    usage.herkunft_setzen(usage.PRUEFSTAND)
    eur = usage.buchen("claude-sonnet-5", output_tokens=50_000)
    usage.herkunft_setzen(usage.CHAT)
    assert usage.monat_euro() == pytest.approx(chat)
    assert usage.monat_euro(usage.PRUEFSTAND) == pytest.approx(eur)
    assert usage.uebersicht()["monat"] == pytest.approx(chat, abs=1e-4)
    assert usage.uebersicht(usage.PRUEFSTAND)["modelle"]["claude-sonnet-5"] == \
        pytest.approx(eur, abs=1e-4)


def test_herkunft_als_block_und_zurueck(buch):
    with usage.herkunft_block("titel"):
        assert usage.aktuelle_herkunft() == "titel"
        usage.buchen("claude-haiku-4-5", output_tokens=1000)
    assert usage.aktuelle_herkunft() == usage.CHAT
    assert usage.monat_euro() == 0.0 and usage.monat_euro("titel") > 0


def test_alte_datei_ohne_toepfe_bleibt_lesbar(buch):
    from datetime import date
    m = date.today().isoformat()[:7]
    buch.write_text(json.dumps({"tage": {}, "monate": {m: {"euro": 3.5, "calls": 9}},
                                "modelle": {}}))
    assert usage.monat_euro() == 3.5
    assert usage.monat_euro(usage.PRUEFSTAND) == 0.0


def test_batch_faktor_halbiert(buch):
    voll = usage.buchen("claude-sonnet-5", input_tokens=10_000, output_tokens=10_000)
    halb = usage.buchen("claude-sonnet-5", input_tokens=10_000, output_tokens=10_000, faktor=0.5)
    assert halb == pytest.approx(voll / 2)


def test_deckel_und_rueckfall_zaehlen_nur_den_chat(buch, monkeypatch):
    werte = {"budget_monat_euro": 1.0}
    monkeypatch.setattr(ai_backends.ai_config, "setting",
                        lambda name, default=None: werte.get(name, default))
    usage.herkunft_setzen(usage.PRUEFSTAND)
    usage.buchen("claude-opus-5", output_tokens=200_000)      # weit über 1 €
    usage.herkunft_setzen(usage.CHAT)
    lage = ai_backends.budget_lage()
    assert lage["status"] == "ok" and lage["ausgegeben"] == 0.0


def test_topf_setzen_markiert_das_log_und_stellt_zurueck(buch, capsys):
    zurueck = kind.topf_setzen()
    assert usage.aktuelle_herkunft() == usage.PRUEFSTAND
    zurueck()
    assert usage.aktuelle_herkunft() == usage.CHAT
    assert kind.TOPF_MARKE in capsys.readouterr().out


# ── Umbuchen der alten Läufe ───────────────────────────────────────────

def _lauf(wurzel, name, zeilen, marke=False):
    p = wurzel / name / "protokolle"
    p.mkdir(parents=True)
    (p / "f01.log").write_text(("PRÜFSTAND-KOSTEN → eigener Topf (pruefstand)\n" if marke else "")
                               + "\n".join(zeilen) + "\n", encoding="utf-8")
    return p / "f01.log"


ZEILEN = ["09:10:11  CLOUD ← claude-sonnet-5 in=476 cache_read=0 cache_write=17208 out=56 "
          "≈0.1000€ (heute 0.78€)",
          "09:10:13  CLOUD ← claude-sonnet-5 in=2 cache_read=1 cache_write=1 out=1 ≈0.0500€ (heute 0.79€)",
          "17:07:41  PRÜFSTAND-RICHTER ← claude-haiku-4-5 in=2802 out=368 ≈0.0200€",
          "irgendwas ohne Kosten"]


def _buchhaltung(tag, euro=5.0):
    return {"tage": {tag: {"euro": euro, "calls": 50}},
            "monate": {tag[:7]: {"euro": euro, "calls": 50}},
            "modelle": {"claude-sonnet-5": {"euro": euro - 1, "calls": 40},
                        "claude-haiku-4-5": {"euro": 1.0, "calls": 10}}}


def test_belege_kopien_zaehlen_einmal_marke_gar_nicht(tmp_path):
    log = _lauf(tmp_path, "lauf1", ZEILEN)
    _lauf(tmp_path, "lauf1_kopie", ZEILEN)
    _lauf(tmp_path, "neu", ZEILEN[:1], marke=True)
    os.utime(log, (1_700_000_000, 1_700_000_000))           # Original ist älter
    belege = umb.belege_sammeln([str(tmp_path)])
    assert len(belege) == 3
    assert {b["lauf"] for b in belege} == {"lauf1"}
    assert sum(b["euro"] for b in belege) == pytest.approx(0.17)


def test_umbuchen_verschiebt_und_ist_wiederholbar(tmp_path):
    _lauf(tmp_path, "lauf1", ZEILEN)
    belege = umb.belege_sammeln([str(tmp_path)])
    tag = belege[0]["tag"]
    d = _buchhaltung(tag)
    neu, warn = umb.umbuchen(d, belege)
    assert len(neu) == 3 and not warn
    assert d["monate"][tag[:7]]["euro"] == pytest.approx(5.0 - 0.17)
    assert d["modelle"]["claude-haiku-4-5"]["euro"] == pytest.approx(0.98)
    p = d["herkunft"]["pruefstand"]
    assert p["monate"][tag[:7]] == {"euro": pytest.approx(0.17), "calls": 3}
    assert p["tage"][tag]["calls"] == 3
    # Zweimal ausgeführt: nichts mehr umzubuchen.
    neu2, _ = umb.umbuchen(d, belege)
    assert neu2 == [] and d["monate"][tag[:7]]["euro"] == pytest.approx(4.83)


def test_umbuchen_nie_unter_null(tmp_path):
    _lauf(tmp_path, "lauf1", ZEILEN)
    belege = umb.belege_sammeln([str(tmp_path)])
    tag = belege[0]["tag"]
    d = _buchhaltung(tag, euro=0.05)
    _, warn = umb.umbuchen(d, belege)
    assert d["monate"][tag[:7]]["euro"] == 0.0 and warn


def test_skript_zeigt_nur_und_schreibt_erst_mit_wirklich(tmp_path, monkeypatch, capsys):
    _lauf(tmp_path / "belege", "lauf1", ZEILEN)
    tag = umb.belege_sammeln([str(tmp_path / "belege")])[0]["tag"]
    datei = tmp_path / "ai_usage.json"
    datei.write_text(json.dumps(_buchhaltung(tag)))
    vorher = datei.read_text()
    args = ["x", "--datei", str(datei), "--belege", str(tmp_path / "belege")]
    monkeypatch.setattr(sys, "argv", args)
    assert umb.main() == 0
    assert datei.read_text() == vorher and "Nur gezeigt" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", args + ["--wirklich"])
    assert umb.main() == 0
    d = json.loads(datei.read_text())
    assert d["herkunft"]["pruefstand"]["monate"][tag[:7]]["euro"] == pytest.approx(0.17)
    sicherungen = [n for n in os.listdir(tmp_path) if ".vor-umbuchung-" in n]
    assert len(sicherungen) == 1
    assert (tmp_path / sicherungen[0]).read_text() == vorher
    monkeypatch.setattr(sys, "argv", args + ["--wirklich"])
    umb.main()
    assert "alles schon erledigt" in capsys.readouterr().out
