"""
Eine Routine aendern und loeschen — der Fall vom 18.08.2026.

Sasha sagte, die Geigenstunde sei jetzt um 18:00 statt 17:45. Sie fragte,
ob sie eine Routine EINTRAGEN soll — obwohl sie eine bestehende aendern
sollte —, legte sie an, und musste dann einraeumen, dass sie die alte
nicht loeschen kann. Beides zu Recht: `add_routine` war das einzige
Werkzeug fuer Routinen, und `delete_entry` fasst absichtlich nur
Einmal-Termine an.

Die Luecke war also keine Prompt-Schwaeche, sondern ein fehlendes
Werkzeug — deshalb pruefen diese Tests den Mechanismus, nicht die
Wortwahl.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import ai
import kalender


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_routine("routinen", "Geigenstunde", "FREQ=WEEKLY;BYDAY=TU",
                         time="17:45", ende="18:30", ort="Geigenschule")
    return kalender


def _routine(k, name="geige"):
    treffer = k.routine_finden(name)
    return treffer[0][2] if treffer else None


# ── Die Kernfaehigkeit ────────────────────────────────────────────────

def test_uhrzeit_aendern_erzeugt_keine_zweite_routine(cal):
    """Der eigentliche Fehler: aus einer Verschiebung wurden zwei Termine."""
    assert cal.routine_aendern("geige", time="18:00", ende="18:45") == 1
    assert len(cal.routine_finden("geige")) == 1
    r = _routine(cal)
    assert (r["time"], r["ende"]) == ("18:00", "18:45")


def test_ungenannte_felder_bleiben_stehen(cal):
    """Wer die Uhrzeit verschiebt, will den Ort nicht verlieren."""
    cal.routine_aendern("geige", time="18:00")
    r = _routine(cal)
    assert r["ort"] == "Geigenschule"
    assert r["rrule"] == "FREQ=WEEKLY;BYDAY=TU"
    assert r["ende"] == "18:30"


def test_leerer_string_loescht_das_feld(cal):
    """Der Weg, einen Ort wieder loszuwerden — None heisst 'nicht anfassen',
    "" heisst 'weg damit'."""
    cal.routine_aendern("geige", ort="")
    assert "ort" not in _routine(cal)


def test_label_und_rrule_lassen_sich_nicht_leeren(cal):
    """Ohne die beiden ist es keine Routine mehr, sondern Datenmuell im
    Kalender, den niemand mehr findet, um ihn zu loeschen."""
    cal.routine_aendern("geige", neues_label="", rrule="")
    r = _routine(cal)
    assert r["label"] == "Geigenstunde"
    assert r["rrule"] == "FREQ=WEEKLY;BYDAY=TU"


def test_umbenennen_geht(cal):
    """Der Suchbegriff heisst `label`, der neue Titel `neues_label` — waeren
    es zwei Bedeutungen desselben Parameters, flaeche das Umbenennen mit
    einer Ausnahme auf, und zwar erst beim Benutzer."""
    assert cal.routine_aendern("geige", neues_label="Violine") == 1
    assert cal.routine_finden("geige") == []
    assert _routine(cal, "Violine")["time"] == "17:45"


def test_werkzeug_benennt_um(cal):
    antwort = ai._execute_tool(
        "edit_calendar_routine",
        {"label": "geige", "aktion": "aendern", "neuer_titel": "Violine"})
    assert "geändert" in antwort
    assert _routine(cal, "Violine") is not None


def test_loeschen_entfernt_die_regel(cal):
    assert cal.routine_loeschen("geige") == 1
    assert cal.routine_finden("geige") == []


def test_aenderung_steht_in_der_datei(cal):
    """Der Kalender wird bei jedem Lesen aus der Datei geholt; eine
    Aenderung, die nur im Speicher haengt, waere naechste Woche weg."""
    cal.routine_aendern("geige", time="18:00")
    assert '"18:00"' in cal.CAL_PATH.read_text(encoding="utf-8")


# ── Ehrlichkeit statt Erfolgsmeldung ──────────────────────────────────

def test_nicht_gefunden_meldet_null(cal):
    """0 statt einer Ausnahme, damit der Aufrufer 'nichts geaendert' sagen
    kann statt einen Erfolg zu behaupten — derselbe Vertrag wie bei
    delete_entry."""
    assert cal.routine_aendern("gibtsnicht", time="09:00") == 0
    assert cal.routine_loeschen("gibtsnicht") == 0


def test_kaputte_rrule_wird_abgewiesen_und_aendert_nichts(cal):
    """Eine ungueltige Wiederholung wuerde beim Lesen jedes Mal fliegen —
    also gar nicht erst schreiben."""
    assert cal.routine_aendern("geige", rrule="FREQ=BLOEDSINN") == 0
    assert _routine(cal)["rrule"] == "FREQ=WEEKLY;BYDAY=TU"


def test_leerer_titel_trifft_nicht_alles(cal):
    """Ein Teilstring-Match auf "" wuerde jede Routine treffen — das waere
    ein stiller Totalschaden."""
    assert cal.routine_finden("") == []
    assert cal.routine_loeschen("") == 0


# ── Das Werkzeug, so wie die KI es sieht ──────────────────────────────

def test_werkzeug_aendert_und_loescht(cal):
    assert "geändert" in ai._execute_tool(
        "edit_calendar_routine",
        {"label": "geige", "aktion": "aendern", "time": "18:00"})
    assert _routine(cal)["time"] == "18:00"
    assert "gelöscht" in ai._execute_tool(
        "edit_calendar_routine", {"label": "geige", "aktion": "loeschen"})


def test_werkzeug_ohne_neue_werte_meldet_fehler(cal):
    """Sonst quittiert es einen Erfolg, ohne etwas getan zu haben."""
    antwort = ai._execute_tool("edit_calendar_routine",
                               {"label": "geige", "aktion": "aendern"})
    assert antwort.startswith("[Fehler")


def test_werkzeug_braucht_freigabe(cal):
    """Dauerhaftes Aendern und Loeschen geht nie ohne Knopf."""
    assert "edit_calendar_routine" in ai.PERMISSION_REQUIRED_TOOLS


def test_frage_nennt_was_sich_aendert(cal):
    """Sasha sieht nur die Frage, nicht den Werkzeug-Aufruf. 'Soll ich die
    Routine aendern?' waere nicht zustimmungsfaehig."""
    frage = ai._permission_question(
        "edit_calendar_routine",
        {"label": "Geigenstunde", "aktion": "aendern", "time": "18:00"})
    assert "Geigenstunde" in frage and "18:00" in frage
    loesch = ai._permission_question(
        "edit_calendar_routine", {"label": "Sport", "aktion": "loeschen"})
    assert "lösch" in loesch.lower() and "Sport" in loesch


def test_beschreibung_weist_vom_falschen_werkzeug_weg():
    """Der urspruengliche Fehlgriff: add_calendar_routine fuer eine
    Verschiebung. Beide Schienen muessen das benennen, sonst greift sie
    wieder daneben."""
    from profil import gross, klein
    fuer = lambda tools: next(
        t["function"]["description"] for t in tools
        if t["function"]["name"] == "edit_calendar_routine")
    assert "add_calendar_routine" in fuer(klein.TOOLS)
    assert "add_calendar_routine" in fuer(gross.TOOLS)
