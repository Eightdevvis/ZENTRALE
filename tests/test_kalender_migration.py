"""
Der Kalender-Umzug JSON -> .ics (core/kalender_migration.py,
scripts/kalender_migrieren.py).

Die Prüfung muss streng sein UND sie muss Fehler wirklich finden — deshalb
hier auch Tests, die absichtlich etwas kaputt machen und verlangen, dass die
Prüfung Alarm schlägt. Der echte Umzug wird nur in tmp_path ausgeführt.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

import kalender
import kalender_ics
import kalender_ics_abbildung as abb
import kalender_migration as mig
import kalender_sicherung as sich
from kalender_ics import IcsSpeicher, ohne_interna
from _kalender_voll import ohne_erlebt, voll


def _json(tmp_path, daten=None) -> Path:
    p = tmp_path / "data" / "ai_calendar.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(daten if daten is not None else voll(), ensure_ascii=False, indent=2))
    return p


# ── Prüfen ─────────────────────────────────────────────────────────────

def test_pruefen_voller_kalender_ist_gleich(tmp_path):
    p = _json(tmp_path)
    vorher = p.read_bytes()
    b = mig.pruefen(p, heute=date(2026, 7, 1), jahre=1)
    assert b["abweichungen"] == []
    assert b["gleich"]
    assert b["zahlen"]["routinen"] == 6 and b["zahlen"]["erlebt"] == 2
    assert b["nicht_abbildbar"] == 3              # kaputtes Datum, verdrehte Spanne, leerer Tag
    assert p.read_bytes() == vorher               # Prüfen ändert nichts
    assert not (tmp_path / "data" / "kalender").exists()


def test_pruefen_findet_einen_verlorenen_ort(tmp_path, monkeypatch):
    """Die Prüfung ist nur etwas wert, wenn sie einen Verlust auch FINDET.
    Hier wirft die Abbildung den Ort weg (und die Gegenprobe ist mit
    ausgeschaltet) — die Prüfung muss es merken."""
    echt = abb.termin_kalender

    def ohne_ort(tag, e, uid, pos=None, jetzt=None):
        return echt(tag, {k: v for k, v in e.items() if k != "ort"}, uid, pos, jetzt)
    monkeypatch.setattr(abb, "termin_kalender", ohne_ort)
    b = mig.pruefen(_json(tmp_path), heute=date(2026, 7, 1), jahre=1)
    assert not b["gleich"]
    assert any("ort" in a for a in b["abweichungen"])
    assert any("Feld-Inventar" in a for a in b["abweichungen"])


def test_pruefen_findet_eine_falsche_uhrzeit(tmp_path, monkeypatch):
    """Ein Fehler, der im Dict nicht auffiele, wenn man nur Felder zählt:
    die Zeit ist da, aber falsch. Die Funktions-Vergleiche finden ihn."""
    # Nur der LESEWEG des Speichers wird verfälscht — die Gegenprobe beim
    # Schreiben (abb.lesen) bliebe sonst wachsam und legte das Stück roh ab.
    echt = abb.datei_lesen

    def verschoben(roh):
        stuecke = echt(roh)
        for st in stuecke:
            if st["daten"].get("time") == "09:30":
                st["daten"]["time"] = "10:30"
        return stuecke
    monkeypatch.setattr(abb, "datei_lesen", verschoben)
    b = mig.pruefen(_json(tmp_path), heute=date(2026, 7, 1), jahre=1)
    assert not b["gleich"]
    assert any("entries_in_range" in a for a in b["abweichungen"])


def test_pruefen_vergleicht_reihenfolge_gleichzeitiger_termine(tmp_path, monkeypatch):
    """Die Reihenfolge entscheidet über Alarm-Texte (wer zuerst genannt
    wird). Ohne X-ZENTRALE-POS wäre sie zufällig — das muss auffallen."""
    echt = abb.datei_lesen

    def ohne_pos(roh):
        stuecke = echt(roh)
        for st in stuecke:
            st["pos"] = None
        return stuecke
    monkeypatch.setattr(abb, "datei_lesen", ohne_pos)
    b = mig.pruefen(_json(tmp_path), heute=date(2026, 6, 9), jahre=1)
    assert not b["gleich"]


def test_feld_inventar_meldet_fehlendes_blatt(tmp_path):
    sp = IcsSpeicher(tmp_path / "k", tmp_path / "n.json", tmp_path / "v", tmp_path / "s")
    sp.speichern(voll(), erlaube_massenloeschung=True)
    mehr = voll()
    mehr["layers"]["termine"]["entries"]["2026-06-03"][0]["neu"] = "nie geschrieben"
    inv = mig.feld_inventar(mehr, sp)
    assert ("layers", "termine", "entries", "2026-06-03", 0, "neu") in inv["fehlend"]


def test_echte_datenform_aus_dem_oktober(tmp_path):
    """Die Formen aus Sashas echter Datei (Stand 2026-10-06), nachgebaut:
    Uhrzeiten "10"/"18"/"8"/"2"/"9:30", Basel mit Zeit "10" in der Mitte,
    zwei Geigenstunden, Pausen für beide, aus-Listen."""
    d = {"version": 1, "layers": {
        "termine": {"label": "Termine", "color": "#ff5500", "default_visible": True, "entries": {
            "2026-06-08": [{"label": "Ungarn-Reise", "bis": "2026-06-12", "ort": "Ungarn"}],
            "2026-07-04": [{"label": "A", "time": "9:30"}],
            "2026-07-13": [{"label": "Basel", "bis": "2026-07-17", "times": {"2026-07-14": "10"}}],
            "2026-08-14": [{"label": "B", "time": "18"}],
            "2026-08-15": [{"label": "C", "time": "8"}],
            "2026-08-16": [{"label": "D", "time": "2"}],
            "2026-07-20": [{"label": "Spananien", "bis": "2026-08-15"}]}, "routines": []},
        "routinen": {"label": "Routinen", "color": "#5577ff", "default_visible": True, "entries": {}, "routines": [
            {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45", "ende": "18:30",
             "ort": "Geigenschule", "absage_noetig": True},
            {"label": "Fahrschule", "rrule": "FREQ=WEEKLY;BYDAY=TU,TH", "time": "19:00", "ende": "20:00",
             "ort": "Fahrschule", "aus": ["2026-06-30", "2026-07-14"]},
            {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "18:00"}]},
        "erlebt": {"label": "Erlebt (auto)", "color": "#888888", "default_visible": False,
                   "entries": {"2026-05-19": [{"label": "Sport"}]}, "routines": []}},
        "reisezeiten": {"Geigenschule": {"Fahrschule": 10}}, "puffer_min": 15,
        "pausen": [{"label": "Geigenstunde", "von": "2026-06-29", "bis": "2026-08-07", "grund": "Sommerferien"},
                   {"label": "Geigenstunde", "von": "2026-10-05", "bis": "2026-10-16", "grund": "Herbstferien"}]}
    b = mig.pruefen(_json(tmp_path, d), heute=date(2026, 10, 6))
    assert b["abweichungen"] == []
    assert b["nicht_abbildbar"] == 0


def test_erster_tag_ignoriert_erlebt():
    d = voll()
    assert mig.erster_tag(d) == date(2026, 6, 1)      # Pause "Niemand", nicht erlebt 05-19


# ── Ausführen ──────────────────────────────────────────────────────────

def test_ausfuehren_zieht_um(tmp_path):
    p = _json(tmp_path)
    gesetzt = []
    b = mig.ausfuehren(p, heute=date(2026, 10, 7), einstellung_setzen=gesetzt.append)
    assert b["gleich"]
    assert gesetzt == ["ics"]
    assert not p.exists()
    alt = tmp_path / "data" / "ai_calendar.json.vor-ics-2026-10-07"
    assert json.loads(alt.read_text()) == voll()           # nie gelöscht, nur umbenannt
    neben = json.loads((tmp_path / "data" / "kalender_neben.json").read_text())
    assert neben["migriert_am"] and neben["migriert_aus"] == "ai_calendar.json"
    kalender_ics.cache_leeren()
    sp = IcsSpeicher(tmp_path / "data" / "kalender", tmp_path / "data" / "kalender_neben.json",
                     tmp_path / "data" / "kalender_verlauf", tmp_path / "data" / "kalender_snapshots")
    assert ohne_interna(sp.laden()) == ohne_erlebt()


def test_ausfuehren_ueberschreibt_keinen_vorhandenen_kalender(tmp_path):
    p = _json(tmp_path)
    (tmp_path / "data" / "kalender" / "termine").mkdir(parents=True)
    (tmp_path / "data" / "kalender" / "termine" / "x.ics").write_text("x")
    with pytest.raises(mig.MigrationAbgebrochen):
        mig.ausfuehren(p, einstellung_setzen=lambda w: None)
    assert p.exists()


def test_ausfuehren_bricht_bei_abweichung_ab_und_aendert_nichts(tmp_path, monkeypatch):
    p = _json(tmp_path)
    monkeypatch.setattr(mig, "pruefen", lambda *a, **k: {"gleich": False, "abweichungen": ["x"]})
    gesetzt = []
    with pytest.raises(mig.MigrationAbgebrochen):
        mig.ausfuehren(p, einstellung_setzen=gesetzt.append)
    assert p.exists() and gesetzt == []
    assert not (tmp_path / "data" / "kalender").exists()


def test_nach_dem_umzug_verweigert_ein_json_knoten_das_schreiben(tmp_path, monkeypatch):
    p = _json(tmp_path)
    mig.ausfuehren(p, einstellung_setzen=lambda w: None)
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "json")
    monkeypatch.setattr(kalender, "CAL_PATH", p)
    with pytest.raises(sich.KalenderGesperrt):
        kalender.add_entry("termine", "2026-06-20", "X")


def test_nach_dem_umzug_laeuft_die_fassade_auf_ics(tmp_path, monkeypatch):
    p = _json(tmp_path)
    mig.ausfuehren(p, einstellung_setzen=lambda w: None)
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "ics")
    monkeypatch.setattr(kalender, "CAL_PATH", p)
    kalender_ics.cache_leeren()
    assert kalender.add_entry("termine", "2026-06-20", "Nach dem Umzug")
    tag = kalender.entries_in_range(date(2026, 6, 3), date(2026, 6, 3))["2026-06-03"]
    assert [e["label"] for e in tag if not e.get("recurring")] == ["TÜV-Frist", "Arzt"]
    assert kalender.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))["2026-06-20"][0]["label"] == "Nach dem Umzug"
    # die Rückfall-Sperre bleibt beim Schreiben erhalten
    neben = json.loads((tmp_path / "data" / "kalender_neben.json").read_text())
    assert neben["migriert_am"]


# ── Rückweg ────────────────────────────────────────────────────────────

def test_rueckweg_bringt_die_alte_json_zurueck(tmp_path):
    p = _json(tmp_path)
    mig.ausfuehren(p, einstellung_setzen=lambda w: None)
    gesetzt = []
    mig.zurueck(p, einstellung_setzen=gesetzt.append)
    assert gesetzt == ["json"]
    zurueck = json.loads(p.read_text())
    assert zurueck == voll()
    assert list(zurueck["layers"]) == list(voll()["layers"])   # erlebt am alten Platz
    neben = json.loads((tmp_path / "data" / "kalender_neben.json").read_text())
    assert "migriert_am" not in neben                         # Sperre aufgehoben


def test_rueckweg_ueberschreibt_keine_json(tmp_path):
    p = _json(tmp_path)
    with pytest.raises(mig.MigrationAbgebrochen):
        mig.zurueck(p, einstellung_setzen=lambda w: None)


# ── Das Skript ─────────────────────────────────────────────────────────

def test_skript_prueft_und_aendert_nichts(tmp_path, capsys):
    import kalender_migrieren
    p = _json(tmp_path)
    code = kalender_migrieren.main(["--json", str(p), "--jahre", "1"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "alles gleich" in out and "Feld-Inventar" in out
    assert p.exists() and not (tmp_path / "data" / "kalender").exists()


def test_skript_meldet_abbruch(tmp_path, capsys):
    import kalender_migrieren
    code = kalender_migrieren.main(["--zurueck", "--json", str(_json(tmp_path))])
    assert code == 1
    assert "ABGEBROCHEN" in capsys.readouterr().out
