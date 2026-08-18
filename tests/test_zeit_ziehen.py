"""
Die Uhrzeit wird GEZOGEN, nicht gedrueckt.

Sie stand bis zum 18.08.2026 im Jetzt-Block, und weil sie jede Runde eine
andere war, rechnete das Modell jedes Mal nach, wie lange es noch bis zum
naechsten Termin ist — "in 16 Minuten", "noch 3 Minuten", obwohl Sasha den
Termin laengst gesehen hatte.

Erst stand dagegen eine Prompt-Regel. Sashas Vorschlag war strenger und
besser: die Uhr ganz raus und zu einem Werkzeug machen. Eine Regel ist eine
Bitte — dass sie die Zeit nicht hat, ist eine Tatsache. Das aktive Erinnern
kommt stattdessen aus dem Takt, der anstoesst, wenn ein Termin eine Stunde
bzw. eine halbe Stunde entfernt ist.

Das Datum bleibt im Prompt: es wechselt einmal am Tag statt jede Minute,
und ohne es waere jede Aussage ueber "heute" ein Tool-Aufruf.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import ai
import kalender


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return kalender


# ── Der Prompt ────────────────────────────────────────────────────────

def test_jetzt_block_nennt_keine_uhrzeit():
    """Der Kern der Sache: was sie nicht weiss, kann sie nicht ausrechnen."""
    text = ai._now_prompt()
    assert not re.search(r"\b\d{1,2}:\d{2}\b", text)


def test_jetzt_block_nennt_das_datum_weiter():
    """Ohne Datum waere jede Aussage ueber 'heute' ein Tool-Aufruf — und
    jeder Tool-Aufruf ist ein zweiter kompletter Call."""
    heute = datetime.now()
    text = ai._now_prompt()
    assert str(heute.year) in text
    assert str(heute.day) in text


def test_jetzt_block_sagt_wo_die_uhrzeit_herkommt():
    """Eine Luecke ohne Hinweis fuellt ein Sprachmodell mit einer Erfindung."""
    text = ai._now_prompt()
    assert "read_time" in text
    assert "rate" in text.lower()


# ── Das Werkzeug ──────────────────────────────────────────────────────

def test_read_time_steht_auf_beiden_schienen():
    from profil import gross, klein
    for tools in (klein.TOOLS, gross.TOOLS):
        assert any(t["function"]["name"] == "read_time" for t in tools)


def test_read_time_braucht_keine_freigabe():
    """Lesen ohne Nebenwirkung. Ein Gate hier waere nur eine Frage, die
    Sasha jedes Mal wegklicken muss."""
    assert "read_time" not in ai.PERMISSION_REQUIRED_TOOLS


def test_read_time_nennt_uhrzeit_und_naechsten_termin(cal):
    cal.add_routine("routinen", "Geigenstunde", "FREQ=DAILY", time="23:59")
    antwort = ai._execute_tool("read_time", {})
    assert re.search(r"\b\d{1,2}:\d{2}\b", antwort)
    assert "Geigenstunde" in antwort


def test_read_time_ohne_termin_behauptet_keinen(cal):
    antwort = ai._execute_tool("read_time", {})
    assert "nichts mehr an" in antwort


# ── Der naechste Termin ───────────────────────────────────────────────

def test_naechster_termin_zaehlt_die_minuten(cal):
    cal.add_entry("termine", "2026-08-18", "Zahnarzt", time="09:00")
    n = cal.naechster_termin(datetime(2026, 8, 18, 8, 0))
    assert (n["label"], n["minuten"], n["morgen"]) == ("Zahnarzt", 60, False)


def test_naechster_termin_ueberspringt_was_vorbei_ist(cal):
    cal.add_entry("termine", "2026-08-18", "Zahnarzt", time="09:00")
    cal.add_entry("termine", "2026-08-18", "Geige", time="17:45")
    assert cal.naechster_termin(datetime(2026, 8, 18, 12, 0))["label"] == "Geige"


def test_naechster_termin_greift_auf_morgen_ueber(cal):
    """Abends ist die naechste Verabredung eine von morgen — sonst saehe
    ein Anstoss um 23:00 nie, dass um 8:00 etwas ansteht."""
    cal.add_entry("termine", "2026-08-19", "Vorlesung", time="08:00")
    n = cal.naechster_termin(datetime(2026, 8, 18, 22, 0))
    assert n["morgen"] is True
    assert n["minuten"] == 600


def test_ganztags_erzeugt_keinen_countdown(cal):
    """Ein Eintrag ohne Uhrzeit hat keinen Abstand — ihn mit 0 Minuten zu
    fuehren hiesse, staendig 'jetzt gleich' zu melden."""
    cal.add_entry("termine", "2026-08-18", "Geburtstag")
    assert cal.naechster_termin(datetime(2026, 8, 18, 9, 0)) is None


def test_leerer_kalender_gibt_nichts_vor(cal):
    assert cal.naechster_termin(datetime(2026, 8, 18, 9, 0)) is None
