"""
Die Datei-Bausteine der Kalender-Absicherung (core/kalender_sicherung.py).

Jeder Baustein gegen den Fehler, für den er da ist: ein Absturz mitten im
Schreiben, zwei Prozesse gleichzeitig, ein Sync, der Namen überschreibt,
ein Backup, das beim Auspacken ausbricht.
"""

import os
import sys
import tarfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender_sicherung as sich


# ── atomar schreiben ───────────────────────────────────────────────────

def test_atomar_schreibt_und_ersetzt(tmp_path):
    p = tmp_path / "a" / "x.ics"
    sich.atomar_schreiben(p, "eins")
    sich.atomar_schreiben(p, b"zwei")
    assert p.read_text() == "zwei"
    assert [q.name for q in p.parent.iterdir()] == ["x.ics"]     # keine Reste


def test_absturz_beim_ersetzen_laesst_die_alte_fassung(tmp_path, monkeypatch):
    p = tmp_path / "x.ics"
    p.write_text("alt")

    def kaputt(*a, **k):
        raise OSError("Strom weg")
    monkeypatch.setattr(sich.os, "replace", kaputt)
    with pytest.raises(OSError):
        sich.atomar_schreiben(p, "neu")
    assert p.read_text() == "alt"
    assert [q.name for q in tmp_path.iterdir()] == ["x.ics"]     # temp aufgeräumt


def test_temp_dateien_sehen_nie_wie_termine_aus(tmp_path, monkeypatch):
    """Bliebe eine Temp-Datei doch liegen (kill -9), darf vdirsyncer sie nie
    für einen Termin halten."""
    gesehen = []
    echt = sich.os.replace

    def merken(a, b):
        gesehen.append(Path(a).name)
        return echt(a, b)
    monkeypatch.setattr(sich.os, "replace", merken)
    sich.atomar_schreiben(tmp_path / "x.ics", "a")
    assert gesehen and not gesehen[0].endswith(".ics") and gesehen[0].startswith(".")


# ── Sperre ─────────────────────────────────────────────────────────────

def test_sperre_haelt_einen_zweiten_fern(tmp_path):
    lock = tmp_path / ".lock"
    drin = threading.Event()
    raus = threading.Event()

    def halten():
        with sich.dateisperre(lock):
            drin.set()
            raus.wait(5)
    t = threading.Thread(target=halten)
    t.start()
    drin.wait(5)
    try:
        with pytest.raises(sich.KalenderGesperrt):
            with sich.dateisperre(lock, warten_s=0.3):
                pass
    finally:
        raus.set()
        t.join()
    with sich.dateisperre(lock, warten_s=1):      # danach wieder frei
        pass


# ── Verlauf ────────────────────────────────────────────────────────────

def test_verlaufsnamen_sind_eindeutig(tmp_path):
    jetzt = datetime(2026, 10, 6, 12, 0, 0, 1, tzinfo=timezone.utc)
    a = sich.verlauf_ablegen(tmp_path, "1", "termine", "uid@x", "geaendert", jetzt=jetzt)
    b = sich.verlauf_ablegen(tmp_path, "2", "termine", "uid@x", "geaendert", jetzt=jetzt)
    assert a != b and a.read_text() == "1" and b.read_text() == "2"
    assert a.parent.name == "2026-10"
    assert sich.knoten() in a.name


def test_verlauf_liste_neueste_zuerst_und_filter(tmp_path):
    for i, uid in enumerate(["a", "b", "a"]):
        sich.verlauf_ablegen(tmp_path, str(i), "termine", uid, "geaendert",
                             jetzt=datetime(2026, 10, 6, 12, 0, i, tzinfo=timezone.utc))
    alle = sich.verlauf_liste(tmp_path)
    assert [x["pfad"].read_text() for x in alle] == ["2", "1", "0"]
    assert [x["pfad"].read_text() for x in sich.verlauf_liste(tmp_path, uid="a")] == ["2", "0"]


def test_uid_mit_sonderzeichen_bricht_nicht_aus(tmp_path):
    p = sich.verlauf_ablegen(tmp_path, "x", "termine", "../../etc/passwd~x", "geloescht")
    assert tmp_path in p.parents
    assert len(p.stem.split("~")) == 5


# ── Grabsteine ─────────────────────────────────────────────────────────

def test_grabsteine(tmp_path):
    t = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    sich.grabstein_setzen(tmp_path, "u1@x", "termine", jetzt=t)
    assert sich.grabsteine_lesen(tmp_path) == {"u1@x": t}
    sich.grabstein_entfernen(tmp_path, "u1@x")
    assert sich.grabsteine_lesen(tmp_path) == {}


def test_kaputter_grabstein_versteckt_nichts(tmp_path):
    (tmp_path / "grabsteine").mkdir()
    (tmp_path / "grabsteine" / "x.json").write_text("{kaputt")
    assert sich.grabsteine_lesen(tmp_path) == {}


# ── Massenlösch-Sperre ─────────────────────────────────────────────────

def test_loeschsperre():
    sich.loeschungen_pruefen(5, 5)
    with pytest.raises(sich.KalenderGesperrt):
        sich.loeschungen_pruefen(6, 5)
    sich.loeschungen_pruefen(600, 5, erlaubt=True)


# ── Snapshots ──────────────────────────────────────────────────────────

def _quelle(tmp_path):
    v = tmp_path / "data" / "kalender" / "termine"
    v.mkdir(parents=True)
    (v / "a.ics").write_text("A")
    (tmp_path / "data" / "kalender" / ".zentrale.lock").write_text("")
    return tmp_path / "data"


def test_hoechstens_ein_snapshot_pro_tag(tmp_path):
    basis = _quelle(tmp_path)
    snap = tmp_path / "snap"
    a = sich.snapshot_machen(snap, basis, [basis / "kalender"], heute=date(2026, 10, 6))
    b = sich.snapshot_machen(snap, basis, [basis / "kalender"], heute=date(2026, 10, 6))
    assert a and b is None
    with tarfile.open(a) as t:
        assert t.getnames() == ["kalender", "kalender/termine", "kalender/termine/a.ics"]


def test_rotation_behaelt_30_tage_und_monatserste(tmp_path):
    for tag in ("2026-10-06", "2026-09-07", "2026-09-05", "2026-09-01",
                "2026-01-01", "2024-01-01", "2026-08-15"):
        (tmp_path / f"kalender_{tag}_pc.tar.gz").write_text("x")
    (tmp_path / "kalender_2026-08-14_laptop.tar.gz").write_text("x")
    weg = sich.snapshots_rotieren(tmp_path, heute=date(2026, 10, 6))
    bleiben = sorted(p.name for p in tmp_path.iterdir())
    assert bleiben == ["kalender_2026-01-01_pc.tar.gz", "kalender_2026-09-01_pc.tar.gz",
                       "kalender_2026-09-07_pc.tar.gz", "kalender_2026-10-06_pc.tar.gz"]
    # auch der Snapshot des ANDEREN Knotens wird weggeräumt
    assert any("laptop" in p.name for p in weg)


def test_snapshot_auspacken_bricht_nicht_aus(tmp_path):
    boese = tmp_path / "boese.tar.gz"
    with tarfile.open(boese, "w:gz") as t:
        info = tarfile.TarInfo("../ausbruch.txt")
        info.size = 1
        import io
        t.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(sich.KalenderGesperrt):
        sich.snapshot_auspacken(boese, tmp_path / "ziel")
    assert not (tmp_path / "ausbruch.txt").exists()


def test_snapshot_auspacken(tmp_path):
    basis = _quelle(tmp_path)
    a = sich.snapshot_machen(tmp_path / "snap", basis, [basis / "kalender"],
                             heute=date(2026, 10, 6))
    sich.snapshot_auspacken(a, tmp_path / "zurueck")
    assert (tmp_path / "zurueck" / "kalender" / "termine" / "a.ics").read_text() == "A"
