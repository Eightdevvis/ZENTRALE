"""
Memory-Hygiene: keine stillen Merges, und das Rohmaterial bleibt erhalten.

Zwei Fehlerklassen, die beide LEISE sind — das ist der Grund, warum sie
eigene Tests brauchen:

  1. **Fehlmerge.** Die Alias-Auflösung verschmolz bei Cosinus ≥ 0.78
     automatisch zwei Knoten. Danach gibt es keinen zweiten mehr, den man
     wieder auseinandernehmen könnte, und niemand sieht, dass etwas passiert
     ist. „Pi" und „Pizza" standen als Warnung im alten Kommentar.
  2. **Destillat ohne Original.** Der Graph merkt sich, DASS eine Beziehung
     besteht, nicht WAS gesagt wurde. Was der Extraktor wegwirft, war weg.
"""
import json

import pytest

import graph
import transkript


@pytest.fixture
def aehnlichkeit(monkeypatch):
    """Embedder, bei dem ALLES einander maximal ähnlich ist.

    Der harte Fall: mit diesem Embedder hätte die alte Logik jeden neuen
    Knoten in den ersten bestehenden gemerged.
    """
    monkeypatch.setattr(graph.embeddings, "_embed_raw", lambda t: [1.0, 0.0])
    monkeypatch.setattr(graph.embeddings, "_cloud_embed", lambda t: [1.0, 0.0])
    graph.embeddings._query_cache.clear()


def _graph(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ── Keine stillen Merges mehr ──────────────────────────────────────────

def test_aehnliche_knoten_verschmelzen_nicht_mehr(tmp_path, aehnlichkeit):
    """Die Abnahme aus dem Plan: zwei Knoten, keine Fusion."""
    p = str(tmp_path / "g.json")
    graph.add_turn_extraction([{"name": "Pi", "type": "concept"}], [], store=p)
    graph.add_turn_extraction([{"name": "Pizza", "type": "concept"}], [], store=p)

    namen = set(_graph(p)["nodes"])
    assert "Pi" in namen
    assert "Pizza" in namen


def test_statt_zu_verschmelzen_wird_verbunden(tmp_path, aehnlichkeit):
    """Der Spread soll den Nachbarn trotzdem erreichen — nur ohne
    Datenverlust und sichtbar."""
    p = str(tmp_path / "g.json")
    graph.add_turn_extraction([{"name": "Pi", "type": "concept"}], [], store=p)
    graph.add_turn_extraction([{"name": "Pizza", "type": "concept"}], [], store=p)

    kanten = [(e["from"], e["rel"], e["to"]) for e in _graph(p)["edges"]]
    assert ("Pizza", "alias-von", "Pi") in kanten


def test_eine_falsche_alias_kante_ist_reparierbar(tmp_path, aehnlichkeit):
    """Der ganze Punkt der Umstellung: ein Fehler soll rückgängig zu machen
    sein. Eine Kante loeschen ist trivial — einen Merge rueckgaengig machen
    unmoeglich, weil der zweite Knoten nie existiert hat."""
    p = str(tmp_path / "g.json")
    graph.add_turn_extraction([{"name": "Pi", "type": "concept"}], [], store=p)
    graph.add_turn_extraction([{"name": "Pizza", "type": "concept"}], [], store=p)

    d = _graph(p)
    d["edges"] = [e for e in d["edges"] if e["rel"] != "alias-von"]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f)

    # Beide Knoten stehen noch, mit allem was an ihnen hing.
    namen = set(_graph(p)["nodes"])
    assert {"Pi", "Pizza"} <= namen


def test_echte_schreibweisen_verschmelzen_weiterhin(tmp_path, aehnlichkeit):
    """Exakt / Gross-klein / Stamm bleiben — das sind Schreibweisen desselben
    Wortes, kein Aehnlichkeits-Rateschluss. Sie wegzuwerfen haette den Graphen
    mit Dubletten geflutet."""
    p = str(tmp_path / "g.json")
    graph.add_turn_extraction([{"name": "Zentrale", "type": "concept"}], [], store=p)
    graph.add_turn_extraction([{"name": "zentrale", "type": "concept"}], [], store=p)
    graph.add_turn_extraction([{"name": "Hunde", "type": "concept"}], [], store=p)
    graph.add_turn_extraction([{"name": "Hund", "type": "concept"}], [], store=p)

    namen = set(_graph(p)["nodes"])
    assert len([n for n in namen if n.lower() == "zentrale"]) == 1
    assert not ({"Hund", "Hunde"} <= namen)


def test_zeitknoten_bekommen_keine_alias_kanten(tmp_path, aehnlichkeit):
    """Datums-Knoten haben kein Embedding und keine Synonyme. Eine
    alias-von-Kante zwischen zwei Tagen waere reiner Muell im Spread."""
    p = str(tmp_path / "g.json")
    graph.add_turn_extraction(
        [{"name": "Kaffee", "type": "concept"}],
        [{"from": "Kaffee", "to": "2026-08-16", "rel": "geschah-am"}], store=p)
    kanten = [e for e in _graph(p)["edges"] if e["rel"] == "alias-von"]
    assert all(not e["from"][:4].isdigit() and not e["to"][:4].isdigit()
               for e in kanten)


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
    transkript.schreiben([("wolke", "b")], store="/tmp/ai_graph_cloud.json")
    assert transkript.datei(None) != transkript.datei("/tmp/x.json")
    assert "lokal" in open(transkript.datei(None), encoding="utf-8").read()
    assert "lokal" not in open(transkript.datei("/tmp/x.json"),
                               encoding="utf-8").read()


def test_ein_kaputter_pfad_reisst_die_konsolidierung_nicht_ab(monkeypatch):
    """Lieber ein Knoten ohne Quelle als ein verlorener Knoten."""
    monkeypatch.setattr(transkript, "_DIR", "/proc/gibtsnicht/nirgends")
    assert transkript.schreiben([("egal", "a")]) == []


def test_knoten_tragen_ihre_quelle(tmp_path, aehnlichkeit):
    p = str(tmp_path / "g.json")
    graph.add_turn_extraction([{"name": "Falter", "type": "concept"}], [],
                              store=p, quellen=["2026-08:7"])
    assert _graph(p)["nodes"]["Falter"]["quellen"] == ["2026-08:7"]


def test_quellen_sind_gedeckelt_und_ohne_dubletten(tmp_path, aehnlichkeit):
    """Ein oft erwaehntes Konzept sammelte sonst hunderte IDs."""
    p = str(tmp_path / "g.json")
    for i in range(transkript.MAX_QUELLEN + 10):
        graph.add_turn_extraction([{"name": "Falter", "type": "concept"}], [],
                                  store=p, quellen=[f"2026-08:{i}"])
    graph.add_turn_extraction([{"name": "Falter", "type": "concept"}], [],
                              store=p, quellen=["2026-08:1"])

    q = _graph(p)["nodes"]["Falter"]["quellen"]
    assert len(q) <= transkript.MAX_QUELLEN
    assert len(q) == len(set(q))


def test_ohne_quellen_bleibt_der_knoten_wie_bisher(tmp_path, aehnlichkeit):
    """Der lokale Pfad ruft add_turn_extraction ohne quellen — da darf sich
    nichts aendern."""
    p = str(tmp_path / "g.json")
    graph.add_turn_extraction([{"name": "Falter", "type": "concept"}], [], store=p)
    assert "quellen" not in _graph(p)["nodes"]["Falter"]
