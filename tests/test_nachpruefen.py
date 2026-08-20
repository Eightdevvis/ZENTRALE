"""
Der Nachpruef-Schritt — im Code, nicht in einer zweiten Modellrunde.

Sasha, 20.08.2026: *„nachprüfschritt natürlich also kosten niedrig wie
möglich aber nich auf kosten von qualität in diesem ausmaß!"*

Der Trick: das Tool-ERGEBNIS geht ohnehin ans Modell zurueck. Steht dort
der Beweis statt „OK", hat sie nachgesehen, ohne dass ein Aufruf mehr
anfaellt. Der Unterschied zwischen „Notiert." und „Neu in kataloge/ideen:
'Fraktal-Rendering'. Der Katalog hat jetzt 2 Eintraege." ist, dass ihr beim
zweiten Satz selbst auffaellt, wenn sie es gerade zum zweiten Mal
geschrieben hat.

Geprueft wird hier, was der Code garantiert. Ob sie die Auskunft dann auch
nutzt, kann kein Test zeigen — aber ohne die Auskunft kann sie es sicher
nicht.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import gedaechtnis
import kalender


EINTRAG = "## Fraktal-Rendering\n- thema: fraktale, shader\n- status: idee"


@pytest.fixture
def mem(monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", tempfile.mkdtemp())
    return gedaechtnis


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return kalender


# ── Der Beweis im Gedaechtnis ─────────────────────────────────────────

def test_das_ergebnis_sagt_wo_es_steht(mem):
    """"Notiert." beantwortet die Frage nicht, die man hinterher stellt."""
    antwort = mem.dossier_notieren("kataloge/ideen", EINTRAG)
    assert "kataloge/ideen" in antwort
    assert "Fraktal-Rendering" in antwort


def test_das_ergebnis_zaehlt_mit(mem):
    """Die Zahl ist der eigentliche Nachpruef-Schritt: springt sie nicht,
    wurde nichts angelegt — und das faellt IHR auf, nicht erst Sasha."""
    mem.dossier_notieren("kataloge/ideen", EINTRAG)
    zweite = mem.dossier_notieren(
        "kataloge/ideen", "## Oszi-Fourier\n- thema: fourier\n- status: idee")
    assert "2 Eintraege" in zweite


def test_ein_eintrag_heisst_ein_eintrag(mem):
    assert "1 Eintrag." in mem.dossier_notieren("kataloge/ideen", EINTRAG)


# ── Nichts doppelt ablegen ────────────────────────────────────────────

def test_derselbe_titel_ersetzt_statt_zu_verdoppeln(mem):
    """Zwei Eintraege mit demselben Titel sind das schlechteste Ergebnis:
    dieselbe Sache steht doppelt und niemand weiss, welche Fassung gilt."""
    mem.dossier_notieren("kataloge/ideen", EINTRAG)
    antwort = mem.dossier_notieren("kataloge/ideen",
                                   EINTRAG.replace("idee", "queued"))
    assert antwort.startswith("Aktualisiert")
    text = mem.dossier_lesen("kataloge/ideen")
    assert text.count("## Fraktal-Rendering") == 1
    assert "queued" in text and "status: idee" not in text


def test_woertlich_dasselbe_wird_nicht_zweimal_angehaengt(mem):
    mem.dossier_notieren("wegzeiten", "- Geigenschule: 7 min")
    antwort = mem.dossier_notieren("wegzeiten", "- Geigenschule: 7 min")
    assert "schon woertlich" in antwort
    assert mem.dossier_lesen("wegzeiten").count("Geigenschule") == 1


def test_dieselbe_sache_nicht_an_zwei_orten(mem):
    """Die letzte offene Gabel: eine Idee kann als Notiz ODER als
    Katalog-Eintrag festgehalten werden — beides fuer sich richtig. Am
    20.08.2026 hat sie beides gemacht. Entscheiden kann der Code das nicht;
    MERKEN, dass es die Sache schon woanders gibt, sehr wohl."""
    mem.dossier_notieren("kataloge/ideen", EINTRAG)
    antwort = mem.dossier_notieren("fraktal-rendering",
                                   "Interesse geweckt durch einen Kanal.")
    assert "kataloge/ideen" in antwort
    assert "Nichts geschrieben" in antwort
    assert "Interesse geweckt" not in mem.dossier_lesen("fraktal-rendering")


def test_eine_unbeteiligte_notiz_geht_normal_durch(mem):
    """Die Sperre darf nicht alles verdaechtigen — sonst schreibt sie gar
    nichts mehr auf."""
    mem.dossier_notieren("kataloge/ideen", EINTRAG)
    antwort = mem.dossier_notieren("wegzeiten", "- Uni: 20 min")
    assert not antwort.startswith("Achtung")
    assert "Uni" in mem.dossier_lesen("wegzeiten")


# ── Der Beweis im Kalender ────────────────────────────────────────────

def test_der_termin_wird_zurueckgelesen(cal):
    import ai
    antwort = ai._execute_tool(
        "add_calendar_entry",
        {"layer": "termine", "day": "2026-08-21", "label": "Zahnarzt",
         "time": "09:00"})
    assert "2026-08-21" in antwort
    assert "Zahnarzt" in antwort and "09:00" in antwort


def test_die_zweite_gleichnamige_routine_faellt_auf(cal):
    """Der Geigenstunden-Fall vom 18.08.2026: sie legte eine ZWEITE Regel
    an, statt die erste zu aendern, und merkte es erst, als Sasha fragte."""
    import ai
    ai._execute_tool("add_calendar_routine",
                     {"layer": "routinen", "label": "Geige",
                      "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45"})
    antwort = ai._execute_tool("add_calendar_routine",
                               {"layer": "routinen", "label": "Geige",
                                "rrule": "FREQ=WEEKLY;BYDAY=TU",
                                "time": "18:00"})
    assert "2 Regeln" in antwort
    assert "17:45" in antwort and "18:00" in antwort
    assert "edit_calendar_routine" in antwort


def test_ein_erfolg_ohne_deckung_wird_benannt(cal, monkeypatch):
    """Der wichtigste Fall: das Werkzeug meldet Erfolg, aber es steht
    nichts da. Dann sagt das Ergebnis das ausdruecklich, statt einen Erfolg
    zu behaupten."""
    import ai
    monkeypatch.setattr(kalender, "add_entry", lambda **kw: True)
    antwort = ai._execute_tool(
        "add_calendar_entry",
        {"layer": "termine", "day": "2026-08-21", "label": "Phantom"})
    assert "NICHT" in antwort
