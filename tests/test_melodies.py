"""
Melodie-Registry (core/melodies.py): CRUD + das Normalisieren der Noten gegen
ein temporäres data/-Verzeichnis. Kein Flask, kein Browser — nur die Modul-Logik
(die Klaviatur selbst lebt im Template).
"""
import pytest

import melodies as mel_mod


@pytest.fixture()
def mel(tmp_path, monkeypatch):
    """core.melodies auf ein frisches data/-Verzeichnis umbiegen (isoliert je Test)."""
    monkeypatch.setattr(mel_mod, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(mel_mod, "_REGISTRY", str(tmp_path / "melodies.json"))
    return mel_mod


NOTES = [
    {"n": 60, "t": 0, "d": 300},
    {"n": 64, "t": 400, "d": 250},
    {"n": 67, "t": 800, "d": 600},
]


# ── CRUD ──────────────────────────────────────────────────────────────

def test_create_list_rename_delete(mel):
    assert mel.list_melodies() == []

    m = mel.create_melody("Regen", NOTES)
    assert m["id"] == "m_regen"
    assert m["dur"] == 1400                       # letzte Note: 800 + 600
    assert [e["n"] for e in m["notes"]] == [60, 64, 67]
    assert mel.get_melody("m_regen")["name"] == "Regen"

    r = mel.rename_melody("m_regen", "Regen im Hof")
    assert r["name"] == "Regen im Hof" and r["id"] == "m_regen"   # id bleibt

    mel.delete_melody("m_regen")
    assert mel.list_melodies() == [] and mel.get_melody("m_regen") is None


def test_ids_kollisionsfrei(mel):
    a = mel.create_melody("Regen", NOTES)
    b = mel.create_melody("Regen", NOTES)
    c = mel.create_melody("regen!", NOTES)
    assert [a["id"], b["id"], c["id"]] == ["m_regen", "m_regen_2", "m_regen_3"]


def test_umlaute_und_sonderzeichen_im_namen(mel):
    m = mel.create_melody("Übung /../ 1", NOTES)
    assert m["id"] == "m_ubung_1"                 # ascii-gefaltet, kein Pfad-Ausbruch
    assert m["name"] == "Übung /../ 1"            # Anzeigename bleibt heil


def test_unbekannte_id(mel):
    with pytest.raises(KeyError):
        mel.rename_melody("m_gibtsnicht", "x")
    mel.delete_melody("m_gibtsnicht")             # löschen ist still


# ── Noten-Normalisierung ──────────────────────────────────────────────

def test_notes_werden_sortiert_und_geputzt(mel):
    m = mel.create_melody("Krude", [
        {"n": 67, "t": 800, "d": 100},
        "kaputt",                                  # kein Dict
        {"n": 5, "t": 0, "d": 100},                # unter dem Klaviaturumfang
        {"n": 130, "t": 0, "d": 100},              # darüber
        {"n": "60", "t": "100", "d": "50"},        # Strings → int
        {"n": 62, "t": -20, "d": 0},               # negative Zeit, Dauer 0
    ])
    assert [(e["n"], e["t"], e["d"]) for e in m["notes"]] == [
        (62, 0, 1), (60, 100, 50), (67, 800, 100),
    ]


def test_leere_melodie_und_leerer_name(mel):
    with pytest.raises(ValueError):
        mel.create_melody("Leer", [])
    with pytest.raises(ValueError):
        mel.create_melody("Leer", [{"n": 999, "t": 0, "d": 10}])   # alles gefiltert
    with pytest.raises(ValueError):
        mel.create_melody("   ", NOTES)
    with pytest.raises(ValueError):
        mel.rename_melody(mel.create_melody("Da", NOTES)["id"], "  ")


def test_deckel_bei_vielen_noten(mel):
    viele = [{"n": 60, "t": i, "d": 10} for i in range(mel_mod.MAX_NOTES + 500)]
    m = mel.create_melody("Lang", viele)
    assert len(m["notes"]) == mel_mod.MAX_NOTES
