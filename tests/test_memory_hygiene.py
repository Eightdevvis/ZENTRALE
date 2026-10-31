"""
Memory-Hygiene: das Rohmaterial bleibt erhalten.

Bis 2026-10-31 stand hier auch der Konzept-Graph (keine stillen Merges,
Quellen je Knoten). Der ist aus dem Code; geblieben ist das Transkript, das
nach jedem Turn geschrieben wird (core/consolidation.py → core/transkript.py)
und das search_chats liest.
"""
import json

import pytest

import consolidation
import transkript


# ── Transkript-Schicht ─────────────────────────────────────────────────

@pytest.fixture
def transkript_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(transkript, "_DIR", str(tmp_path / "ai_transcripts"))
    return tmp_path / "ai_transcripts"


def test_turns_landen_woertlich_in_der_datei(transkript_dir):
    ids = transkript.schreiben([("ich hab ein klapprad", "schoen"),
                                ("es heisst Falter", "notiert")])
    assert len(ids) == 2
    zeilen = [json.loads(z) for z in
              open(transkript.datei(), encoding="utf-8").read().splitlines()]
    assert zeilen[0]["user"] == "ich hab ein klapprad"
    assert zeilen[1]["ai"] == "notiert"


def test_ids_sind_nachschlagbar(transkript_dir):
    ids = transkript.schreiben([("erste", "a"), ("zweite", "b")])
    assert transkript.lesen(ids[1])["user"] == "zweite"
    assert transkript.lesen("2099-01:5") is None
    assert transkript.lesen("kaputt") is None


def test_append_only_haengt_an_statt_zu_ueberschreiben(transkript_dir):
    transkript.schreiben([("eins", "a")])
    ids = transkript.schreiben([("zwei", "b")])
    assert ids == ["%s:2" % transkript._monat()]
    assert transkript.lesen("%s:1" % transkript._monat())["user"] == "eins"


def test_cloud_und_lokal_haben_getrennte_dateien(transkript_dir):
    """Beide bleiben im Haus — aber welcher Turn zu welchem Gedaechtnis
    gehoert, darf nicht verwischen, sonst ist die Isolations-Invariante nur
    noch halb wahr."""
    transkript.schreiben([("lokal", "a")], store=None)
    transkript.schreiben([("wolke", "b")], store="cloud")
    assert transkript.datei(None) != transkript.datei("/tmp/x.json")
    assert "lokal" in open(transkript.datei(None), encoding="utf-8").read()
    assert "lokal" not in open(transkript.datei("/tmp/x.json"),
                               encoding="utf-8").read()


def test_ein_kaputter_pfad_reisst_die_konsolidierung_nicht_ab(monkeypatch):
    """Ein volles Dateisystem darf den Worker nicht abreißen lassen."""
    monkeypatch.setattr(transkript, "_DIR", "/proc/gibtsnicht/nirgends")
    assert transkript.schreiben([("egal", "a")]) == []


# ── Der Worker davor ───────────────────────────────────────────────────

def test_worker_groups_by_store():
    """Local and cloud turns never land in one write: the isolation
    invariant must survive the batching."""
    buendel = consolidation._buendel_schnueren(
        [("a", "1", None), ("b", "2", "cloud"), ("c", "3", None)])
    assert buendel[None] == [("a", "1"), ("c", "3")]
    assert buendel["cloud"] == [("b", "2")]


def test_record_turns_skips_trivial_turns(transkript_dir):
    assert consolidation.record_turns("ok", "gut") == []
    ids = consolidation.record_turns(
        [("hi", "hallo"), ("ich hab ein klapprad", "schoen")], store="cloud")
    assert len(ids) == 1
    assert "klapprad" in open(transkript.datei("cloud"), encoding="utf-8").read()
