"""
Alarm „Wochentag" (core/kalender_konflikte.py, 22.10.2026): ein gespeicherter
Eintrag, dessen Titel einen Wochentag nennt, an dem er nicht stattfindet
(qwen: „Sprechstunde Jonas Schömer (Mo)" mit BYDAY=WE). Uhr über core/uhr.py
gestellt, damit nichts vom heutigen Datum abhängt.
"""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_kennung as kk
import uhr

JETZT = datetime(2026, 10, 22, 9, 0)     # ein Donnerstag


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return tmp_path


def _wochentag():
    return [a for a in kalender.open_alarms() if a["kind"] == "Wochentag"]


@pytest.mark.kalender_beide
def test_routine_falscher_titel_ein_alarm_mit_stabiler_id(cal):
    kalender.add_routine("termine", "Sprechstunde Jonas Schömer (Mo)",
                         "FREQ=WEEKLY;BYDAY=WE", time="16:15", ende="17:15")
    kalender.add_routine("termine", "Uni (Mi)", "FREQ=WEEKLY;BYDAY=WE", time="10:00")
    kalender.add_routine("termine", "Miete Montag", "FREQ=MONTHLY;BYMONTHDAY=1")
    with uhr.gestellt(JETZT):
        al = _wochentag()
        assert [a["text"] for a in al] == [
            "Titel nennt Montag, die Serie läuft mittwochs: Sprechstunde Jonas Schömer (Mo)"]
        id_1 = al[0]["id"]
        uhr.vorstellen(days=3)
        assert [a["id"] for a in _wochentag()] == [id_1]


@pytest.mark.kalender_beide
def test_einzeltermin_und_phase(cal):
    kalender.add_entry("termine", "2026-10-27", "Treffen Freitag", time="18:00")  # Dienstag
    kalender.add_entry("termine", "2026-10-30", "Kino Freitag", time="20:00")      # passt
    kk.phase_anlegen("Schlaf (Mo)", "23:00", ende="07:00", motiv="schlaf",
                     rrule="FREQ=WEEKLY;BYDAY=WE", von="2026-10-01")
    with uhr.gestellt(JETZT):
        al = _wochentag()
    assert [(a["text"], a.get("tag")) for a in al] == [
        ("Titel nennt Freitag, der Termin ist am Dienstag, 27.10.: Treffen Freitag",
         "2026-10-27")]
