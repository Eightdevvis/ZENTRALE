"""
scripts/beispiele_etikettieren.py (2026-10-10): aus gesammelten Beispielen
Etiketten im SetFit-Format. Ohne --wirklich fragt es kein Modell, zeigt nur
die geschätzten Kosten.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import beispiele_etikettieren as et  # noqa: E402
import klassifikator_beispiele  # noqa: E402


def _beispiele():
    klassifikator_beispiele.schreiben({
        "saetze": [{"satz": "Hab ich eingetragen.", "art": "behauptung_tat", "sicher": 1.0},
                   {"satz": "Shall I look it up?", "art": "sonst", "sicher": 0.0}],
        "auskunft": {"erledigt": ["kalender"], "fragt_erlaubnis": True, "schiebt_auf": False},
        "befunde": [], "protokoll": []})
    klassifikator_beispiele.schreiben({
        "saetze": [{"satz": "Das Wetter ist schön.", "art": "sonst", "sicher": 0.0}],
        "auskunft": None, "befunde": [], "protokoll": []})


def _zeilen(pfad):
    return [json.loads(z) for z in open(pfad, encoding="utf-8")]


def test_ohne_modell_wortliste_und_auskunft(tmp_path, capsys):
    _beispiele()
    aus = tmp_path / "e.jsonl"
    assert et.main(["--aus", str(aus)]) == 0
    assert _zeilen(aus) == [
        {"text": "Hab ich eingetragen.", "label": "behauptung_tat", "quelle": "wortliste"},
        {"text": "Shall I look it up?", "label": "erlaubnisfrage", "quelle": "auskunft"}]
    assert "1 ohne" in capsys.readouterr().out


def test_modell_nur_mit_wirklich(tmp_path, capsys):
    _beispiele()
    aus = tmp_path / "e.jsonl"
    gefragt = []

    def fragen(system, text, modell, anbieter):
        gefragt.append(text)
        return "ja" if "Tatsache" in text else "nein"
    et.main(["--aus", str(aus), "--modell", "claude-haiku-4-5"], fragen=fragen)
    out = capsys.readouterr().out
    assert gefragt == [] and "Nichts gefragt" in out and "€" in out
    et.main(["--aus", str(aus), "--modell", "claude-haiku-4-5", "--wirklich"], fragen=fragen)
    assert gefragt
    assert _zeilen(aus)[-1] == {"text": "Das Wetter ist schön.", "label": "fakt",
                                "quelle": "modell"}


def test_kosten_schaetzung_waechst_mit_den_fragen():
    assert 0 < et.kosten_schaetzen("claude-haiku-4-5", 10) < et.kosten_schaetzen(
        "claude-haiku-4-5", 100)
