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


def test_key_datei_wird_nur_fuer_den_besitzer_geschrieben(monkeypatch, tmp_path):
    """Die Datei trägt API-Keys: immer 600, auch neu angelegt (2026-10-08)."""
    import stat
    ziel = tmp_path / "ai_config.json"
    monkeypatch.setattr(ai_config, "_DIR", str(tmp_path))
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(ziel))
    monkeypatch.setattr(ai_config, "_config", {"keys": {"X": "geheim"}})
    ai_config._save()
    assert stat.S_IMODE(ziel.stat().st_mode) == 0o600
