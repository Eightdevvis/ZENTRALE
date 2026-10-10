"""
Kurzfall f01k (2026-10-10, tests/pruefstand/faelle/f01k_geige_kurz.yaml):
lädt, steht in der Liste, `--fall f01` trifft ihn NICHT mit (sonst liefe
still ein zweiter, bezahlter Fall), und ein Trockenlauf mit gefälschtem
Modell geht über die echte Route — die Antworten über das Werkzeug antwort
(Selbstauskunft, nur gross).
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from pruefstand_teile import faelle, kind  # noqa: E402
from test_cloud_loop import FakeBlock, FakeClient  # noqa: E402

import ai_backends  # noqa: E402
import cloud  # noqa: E402


def _fall():
    return faelle.finden(["f01k"])[0]


def test_f01k_laedt_und_ist_f01_in_kurz():
    k = _fall()
    lang = faelle.finden(["f01"])
    assert [f["id"] for f in lang] == ["f01_geige_08okt"]
    f01 = lang[0]
    assert k["id"] == "f01k_geige_kurz" and len(k["zuege"]) == 2
    assert [z["sagt"] for z in k["zuege"]] == [z["sagt"] for z in f01["zuege"][:2]]
    for feld in ("kalender", "netz", "antworten", "gedaechtnis", "jetzt"):
        assert k[feld] == f01[feld], feld
    was = " ".join(e["was"] for e in k["endzustand"])
    assert "nyam" in was and "Ferienende" in was


def test_praefix_ohne_unterstrich_trifft_weiter():
    assert [f["id"] for f in faelle.finden(["f01k_geige"])] == ["f01k_geige_kurz"]
    assert faelle.finden(["f0"])            # Anfang ohne „_“: wie bisher alle


def _antwort(text, erledigt=(), id="a"):
    return {"stop_reason": "tool_use", "content": [FakeBlock(
        "tool_use", name="antwort", id=id,
        input={"text": text, "erledigt": list(erledigt), "fragt_erlaubnis": False,
               "schiebt_auf": False})]}


RUNDEN = [
    _antwort("Ja, kann ich.", id="a1"),
    {"stop_reason": "tool_use", "content": [
        FakeBlock("tool_use", name="delete_calendar_entry",
                  input={"label": "nyam", "day": "2026-10-08"}, id="t1"),
        FakeBlock("tool_use", name="add_calendar_pause",
                  input={"label": "Geigenstunde", "von": "2026-10-08"}, id="t2")]},
    _antwort("nyam ist gelöscht, Geige fällt heute aus. Bis wann die Ferien gehen, "
             "weiß ich nicht.", ["kalender"], id="a2"),
]


@pytest.fixture
def lauf(monkeypatch, tmp_path):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "chat_cloud_kind", lambda: "anthropic")
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "claude")
    monkeypatch.setattr(cloud, "_model", lambda: "claude-sonnet-5")
    monkeypatch.setattr(cloud.graph, "einmal_seeden", lambda *a, **k: None)
    client = FakeClient([dict(r) for r in RUNDEN])
    monkeypatch.setattr(cloud, "_get_client", lambda: client)
    erg = kind.ausfuehren(_fall(), code_wurzel=ROOT, tmp=str(tmp_path / "probe"),
                          richter_fragen=None)
    return erg, client


def test_f01k_trockenlauf(lauf):
    erg, client = lauf
    assert not erg.get("absturz"), erg.get("absturz")
    assert len(erg["zuege"]) == 2 and len(client.calls) == 3
    assert erg["zuege"][0]["antwort"] == "Ja, kann ich."
    assert erg["zuege"][1]["antwort"].startswith("nyam ist gelöscht")
    ez = {e["was"]: e for e in erg["endzustand"]}
    assert len(ez) == len(_fall()["endzustand"])
    assert ez["nyam ist weg"]["ok"], ez["nyam ist weg"]
    # Die doppelte Geige hat das Modell nicht angefasst (die Pause scheiterte
    # ehrlich an K-MEHRDEUTIG): der Endzustand sieht es — auch am 15.10.
    # stehen zwei statt einer, und ausgefallen ist dort nichts.
    assert not ez["Genau eine Geigenstunde-Regel"]["ok"]
    ferien = ez["Kein Ferienende ohne Beleg — Geige 15.10. bleibt stehen"]
    assert not ferien["ok"] and ferien["grund"].startswith("2 statt 1")
    assert "K-MEHRDEUTIG" in erg["zuege"][1]["werkzeuge"][1]["ergebnis"]
