"""„Jetzt und als Nächstes" im wechselnden Teil, Smalltalk ohne Nachschlagen.

Sasha, 26.10.2026 (Leitbild-Szene „Bei ihr einchecken", Gespräch
20261026-201032-04ec42): auf „meow" soll sie nichts nachschlagen, sondern im
Blick haben, was laut Kalender gerade läuft und als Nächstes kommt, und
höchstens sanft fragen. qwen hatte stattdessen den Kalender gelesen, eine
Terminliste aufgesagt und den Tagesrhythmus als Termin angesagt.

Festgehalten wird:
  * der Abschnitt nennt den laufenden Termin mit Ende, die nächsten Termine,
    Deadlines im Vorwarn-Fenster, den Rhythmus getrennt als Rhythmus — und
    keine Minuten;
  * auf gross steht er im wechselnden Teil, der Kalender-Satz ist dort weg,
    die Deadline steht nicht doppelt; klein bleibt wie es war;
  * qwen erzwingt bei Gruß/Smalltalk kein Werkzeug, bei Kalenderfragen weiter.
Kein Test hier ruft ein Modell.
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_kennung as kk
import uhr

# Montag, 26.10.2026, 21:11 — die Uhrzeit aus dem Gespräch.
JETZT = datetime(2026, 10, 26, 21, 11)


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_routine("termine", "Ana HÜ", "FREQ=DAILY", time="20:30", ende="22:00")
    kalender.add_entry("termine", "2026-10-27", "Mensa mit Tim", time="12:00", ende="13:00")
    kalender.add_entry("termine", "2026-10-27", "Ana HÜ schwere Aufgaben",
                       time="14:00", ende="16:00")
    kalender.add_entry("termine", "2026-10-27", "Kino", time="19:00", ende="21:00")
    kalender.add_entry("termine", "2026-10-28", "Analysis Blatt 3", time="23:59",
                       typ="deadline")
    kk.phase_anlegen("come down, meditation, violin", "21:00", ende="23:00",
                     motiv="nachthimmel", von="2026-10-01")
    return tmp_path


def _block(jetzt=JETZT):
    with uhr.gestellt(jetzt):
        return kalender.jetzt_und_naechstes()


@pytest.mark.kalender_beide
def test_block_laufend_naechstes_deadline_rhythmus_ohne_minuten(cal):
    b = _block()
    assert b.startswith("## Jetzt und als Nächstes\n")
    assert "- Laut Kalender läuft gerade: Ana HÜ (bis 22:00). Ob er dabei ist, weißt du nicht." in b
    # Rhythmus eigene Zeile, als Rhythmus gekennzeichnet, nie unter „läuft"
    assert ("- Tagesrhythmus gerade (kein Termin, nicht ansagen): "
            "come down, meditation, violin (bis 23:00).") in b
    laeuft = next(z for z in b.splitlines() if z.startswith("- Laut Kalender"))
    assert "violin" not in laeuft
    # höchstens drei kommende, sortiert; Kino (das vierte) fehlt
    assert ("- Als Nächstes: morgen 12:00 Mensa mit Tim · morgen 14:00 Ana HÜ schwere "
            "Aufgaben · morgen 19:00 Kino.") in b
    assert "- Deadline Analysis Blatt 3 in 2 Tagen (Mi 28.10. 23:59)." in b
    assert "sagst es nicht auf" in b and "nimm es nicht an" in b
    assert not re.search(r"\bmin\b|Minute|in \d+ h\b", b)


@pytest.mark.kalender_beide
def test_ueber_nacht_aus_gestern_und_kein_termin(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kk.phase_anlegen("Schlaf", "23:00", ende="07:00", motiv="schlaf", von="2026-10-01")
    b = _block(datetime(2026, 10, 27, 2, 0))
    assert "- Laut Kalender läuft gerade kein Termin." in b
    assert "Schlaf (bis 07:00)" in b
    assert "Als Nächstes" not in b          # der Rhythmus kommt nie „als Nächstes"


@pytest.mark.kalender_beide
def test_leerer_kalender_kein_block(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    assert _block() == ""


def _wechselnd(monkeypatch, schiene, alarme=()):
    import cloud
    import profil
    import state
    monkeypatch.setattr(cloud, "_profil", lambda modell=None: profil.hol(schiene))
    monkeypatch.setattr(state, "get_alarms", lambda: list(alarme))
    with uhr.gestellt(JETZT):
        return cloud._volatile_text(False, False)


@pytest.mark.kalender_beide
def test_gross_hat_den_block_ohne_kalender_satz_und_ohne_doppel(cal, monkeypatch):
    with uhr.gestellt(JETZT):
        alarme = kalender.open_alarms()
    assert any(a["kind"] == "Deadline" for a in alarme)
    v = _wechselnd(monkeypatch, "gross", alarme)
    assert "## Jetzt und als Nächstes" in v and "Ana HÜ (bis 22:00)" in v
    assert "read_calendar" not in v and "NICHT" not in v and "UHRZEIT" not in v
    assert v.count("Analysis Blatt 3") == 1          # nicht auch unter „Offene Erinnerungen"


@pytest.mark.kalender_beide
def test_klein_bleibt_wie_es_war(cal, monkeypatch):
    import ki_prompt
    v = _wechselnd(monkeypatch, "klein")
    assert "Jetzt und als Nächstes" not in v
    assert "hast du NICHT im Kopf: dafür read_calendar rufen" in v
    assert ki_prompt._now_prompt().split("\n")[0] == "## Jetzt"


# ── qwen: Smalltalk ohne Werkzeug-Zwang ─────────────────────────────────

_TOOLS = [{"function": {"name": "read_calendar"}}, {"function": {"name": "antwort"}}]


def _wahl(text, nr=0):
    from profil.modelle import qwen
    return qwen.tool_choice(nr=nr, verlauf=[{"role": "user", "content": text}],
                            tools=_TOOLS)


def test_meow_ohne_werkzeug_zwang_kalenderfrage_mit(monkeypatch):
    monkeypatch.setenv("ZENTRALE_ANTWORT_PFLICHT", "an")
    for text in ("meow", "hey", "was machst du so", "guten morgen :)"):
        assert _wahl(text) is None, text
        assert _wahl(text, nr=1) is None, text
    assert _wahl("wann hab ich geige?") == "required"
    assert _wahl("was steht heute an") == "required"
    assert _wahl("wie spät ist es") == "required"
    assert _wahl("trag morgen um 10 zahnarzt ein")["function"]["name"] == "read_calendar"


def test_erinnerung_bei_smalltalk_ohne_erst_werkzeug():
    from profil.modelle import qwen
    meow = qwen.erinnerung([{"role": "user", "content": "meow"}])
    assert "erst Werkzeug" not in meow and "ohne Werkzeug" in meow
    frage = qwen.erinnerung([{"role": "user", "content": "wann ist geige"}])
    assert "erst Werkzeug, dann Antwort" in frage


def test_regel_8_drängt_bei_smalltalk_nicht():
    from profil.modelle import qwen
    text = qwen.system("")
    assert "Antwort danach kurz: was jetzt im Kalender steht" not in text
    assert "Bei Gruß oder Smalltalk" in text and "rufst du kein Werkzeug" in text
    assert "oder eine Frage zum Kalender beantwortest: read_calendar" in text
