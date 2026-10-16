"""
Ausfälle durch eine Pause zählen nicht als Konflikt (16.10.2026).

Anlass: die Rückfrage beim Eintragen meldete eine Teil-Überlappung mit der
Geigenstunde — an einem Tag, an dem sie wegen Herbstferien ausfällt.
Ein ausgefallenes Vorkommen findet nicht statt: keine Rückfrage, kein Alarm.
An den anderen Tagen bleibt die Kollision.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender

pytestmark = pytest.mark.kalender_beide

_MORGEN = date.today() + timedelta(days=1)
_UEBERMORGEN = date.today() + timedelta(days=2)


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_routine("termine", "Geigenstunde", "FREQ=DAILY",
                         time="18:00", ende="19:00", ort="Geigenschule")
    kalender.add_pause("Geigenstunde", _MORGEN.isoformat(), _MORGEN.isoformat(),
                       "Herbstferien")
    return tmp_path


def test_rueckfrage_schweigt_am_ausfalltag(cal):
    assert kalender.conflicts_for_proposed(
        "termine", _MORGEN.isoformat(), "Probe", "18:30", "19:30") == []


def test_rueckfrage_meldet_an_anderen_tagen(cal):
    w = kalender.conflicts_for_proposed(
        "termine", _UEBERMORGEN.isoformat(), "Probe", "18:30", "19:30")
    assert any("Geigenstunde" in z for z in w)


def test_alarm_nur_an_tagen_ohne_ausfall(cal):
    for tag in (_MORGEN, _UEBERMORGEN):
        kalender.add_entry("termine", tag.isoformat(), "Probe",
                           time="18:30", ende="19:30")
    tage = {a.get("tag") for a in kalender.open_alarms(5)
            if "Geigenstunde" in a["text"]}
    assert _UEBERMORGEN.isoformat() in tage
    assert _MORGEN.isoformat() not in tage
