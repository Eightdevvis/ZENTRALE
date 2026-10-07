"""
Ein Kalender (Sasha, 07.10.2026): „routinen" zieht nach „termine".

Geprüft an einem Wegwerf-Kalender gegen beide Speicher: danach gibt es nur
noch eine Ebene, und jeder Tag sieht gleich aus (bis aufs Ebenen-Feld).
"""
import importlib.util
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import ki_werkzeuge

pytestmark = pytest.mark.kalender_beide

_SPEC = importlib.util.spec_from_file_location(
    "vereinen", os.path.join(os.path.dirname(__file__), "..", "scripts",
                             "kalender_ebenen_vereinen.py"))
vereinen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vereinen)


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_routine("routinen", "Geige", "FREQ=WEEKLY;BYDAY=TU", time="10:00", ende="11:00")
    kalender.add_routine("routinen", "Parkour", "FREQ=WEEKLY;BYDAY=SA", time="18:30")
    kalender.add_entry("termine", "2026-10-14", "Kino", time="19:00")
    return kalender


def _ohne_ebene():
    d = date(2026, 10, 1)
    tage = kalender.entries_in_range(d, d + timedelta(days=60))
    return {iso: sorted(json.dumps({k: v for k, v in e.items() if k != "layer"},
                                   sort_keys=True) for e in es) for iso, es in tage.items()}


def test_alles_in_einer_ebene_und_nichts_veraendert(cal):
    vorher = _ohne_ebene()
    z = vereinen._vereinen(kalender)
    assert z["routinen"] == 2 and not z["schon_einer"]
    import kalender_ics
    kalender_ics.cache_leeren()
    assert "routinen" not in kalender._load_raw()["layers"]
    assert _ohne_ebene() == vorher
    assert {e["layer"] for es in kalender.entries_in_range(
        date(2026, 10, 1), date(2026, 10, 31)).values() for e in es} == {"termine"}


def test_zweimal_ist_harmlos(cal):
    vereinen._vereinen(kalender)
    assert vereinen._vereinen(kalender)["schon_einer"]


def test_ki_schreibt_routinen_jetzt_nach_termine(cal):
    vereinen._vereinen(kalender)
    out = ki_werkzeuge._add_calendar_routine(
        {"layer": "routinen", "label": "Miete", "rrule": "FREQ=MONTHLY;BYMONTHDAY=1"})
    assert "Fehler" not in out
    assert [l for l, _i, _r in kalender.routine_finden("Miete")] == ["termine"]
