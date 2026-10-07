"""
Der Löschwächter vor dem Google-Sync (scripts/kalender_sync.py).

Sasha, 07.10.2026: „bitte bitte lösch nix aus google calendar aus versehen".
Fehlen lokal seit dem letzten Sync mehr Termine als die Löschsperre erlaubt,
darf vdirsyncer gar nicht erst laufen — sonst trüge es die Lücke als
Löschung zu Google.
"""
import importlib.util
import os

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "kalender_sync", os.path.join(os.path.dirname(__file__), "..", "scripts", "kalender_sync.py"))
ks = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ks)


@pytest.fixture
def vdir(tmp_path, monkeypatch):
    monkeypatch.setattr(ks, "STAND", str(tmp_path / "stand.json"))
    v = tmp_path / "kalender" / "termine"
    v.mkdir(parents=True)
    for i in range(10):
        (v / ("t%d.ics" % i)).write_text("x")
    return tmp_path / "kalender"


def test_erster_lauf_kennt_keine_fehlenden(vdir):
    assert ks._fehlende(vdir) == []


def test_nach_dem_merken_fehlt_was_geloescht_wurde(vdir):
    ks._stand_merken(vdir)
    for i in range(3):
        (vdir / "termine" / ("t%d.ics" % i)).unlink()
    assert ks._fehlende(vdir) == ["termine/t0.ics", "termine/t1.ics", "termine/t2.ics"]


def test_neue_termine_zaehlen_nicht_als_fehlend(vdir):
    ks._stand_merken(vdir)
    (vdir / "termine" / "neu.ics").write_text("x")
    assert ks._fehlende(vdir) == []
