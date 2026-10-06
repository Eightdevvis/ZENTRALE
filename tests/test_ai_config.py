"""data/ai_config.json trägt die API-Keys — sie darf nie halb geschrieben sein."""
import json
import os

import ai_config


def test_speichern_ist_atomar(monkeypatch, tmp_path):
    ziel = tmp_path / "ai_config.json"
    ziel.write_text(json.dumps({"keys": {"X": "alt"}}), encoding="utf-8")
    monkeypatch.setattr(ai_config, "_DIR", str(tmp_path))
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(ziel))
    monkeypatch.setattr(ai_config, "_config", {"keys": {"X": "neu"}})
    ai_config._save()
    assert json.loads(ziel.read_text(encoding="utf-8")) == {"keys": {"X": "neu"}}
    assert os.listdir(tmp_path) == ["ai_config.json"]      # keine Reste


def test_absturz_beim_schreiben_laesst_die_alte_datei_heil(monkeypatch, tmp_path):
    ziel = tmp_path / "ai_config.json"
    ziel.write_text(json.dumps({"keys": {"X": "alt"}}), encoding="utf-8")
    monkeypatch.setattr(ai_config, "_DIR", str(tmp_path))
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(ziel))
    monkeypatch.setattr(ai_config, "_config", {"keys": {"X": "neu"}})

    def kaputt(*a, **k):
        raise OSError("Strom weg")

    import dateien
    monkeypatch.setattr(dateien.os, "fsync", kaputt)
    ai_config._save()
    assert json.loads(ziel.read_text(encoding="utf-8")) == {"keys": {"X": "alt"}}
    assert os.listdir(tmp_path) == ["ai_config.json"]
