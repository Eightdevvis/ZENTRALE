"""core/dateien.py — Datendateien sind danach alt oder neu, nie halb."""
import json
import os
import stat

import pytest

import dateien


def test_json_landet_wie_vorher_mit_json_dump(tmp_path):
    p = tmp_path / "listen.json"
    daten = {"name": "Einkauf", "punkte": ["Brot", "Käse"]}
    dateien.json_schreiben(p, daten)
    assert p.read_text(encoding="utf-8") == json.dumps(daten, indent=2,
                                                        ensure_ascii=False)
    assert os.listdir(tmp_path) == ["listen.json"]


def test_rechte_der_alten_datei_bleiben(tmp_path):
    p = tmp_path / "schluessel.json"
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o600)
    dateien.json_schreiben(p, {"k": 1})
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_absturz_laesst_die_alte_fassung_heil(tmp_path, monkeypatch):
    p = tmp_path / "notizen.json"
    p.write_text('{"alt": true}', encoding="utf-8")

    def kaputt(*a, **k):
        raise OSError("Platte voll")

    monkeypatch.setattr(dateien.os, "fsync", kaputt)
    with pytest.raises(OSError):
        dateien.json_schreiben(p, {"neu": True})
    assert json.loads(p.read_text(encoding="utf-8")) == {"alt": True}
    assert os.listdir(tmp_path) == ["notizen.json"]


def test_legt_fehlende_ordner_an(tmp_path):
    p = tmp_path / "a" / "b" / "werte.json"
    dateien.json_schreiben(p, [1, 2])
    assert json.loads(p.read_text(encoding="utf-8")) == [1, 2]


def test_kalender_nutzt_denselben_helfer():
    import kalender_sicherung
    assert kalender_sicherung.atomar_schreiben is dateien.atomar_schreiben


def test_kein_datenmodul_schreibt_mehr_nackt():
    """Die Module, die am 07.10. umgestellt wurden, dürfen nicht wieder mit
    open(..., 'w') + json.dump schreiben."""
    import pathlib
    import re
    kern = pathlib.Path(dateien.__file__).parent
    for name in ("lists", "notes", "graphs", "melodies", "takt", "news",
                 "usage", "graph", "ai_config"):
        text = (kern / f"{name}.py").read_text(encoding="utf-8")
        assert not re.search(r"open\([^)]*['\"]w['\"][^)]*\)\s+as\s+\w+:\s*\n\s*_?json\.dump",
                             text), name
