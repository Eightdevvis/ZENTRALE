"""
Der .ics-Speicher des Kalenders (core/kalender_ics.py) und der Umschalter.

Geprüft wird, was Sasha versprochen ist (memory/werkzeuge/kalender_ics_bauplan.md):
  * eine Rundreise des vollen Kalenders verliert nichts, nicht einmal die
    Reihenfolge;
  * json und ics liefern über die Fassade dieselben öffentlichen Ergebnisse;
  * ein Schreiben fasst nur die geänderte Datei an;
  * Verlauf, Grabsteine, Massenlösch-Sperre, Wiederherstellen, Snapshots,
    Rückfall-Sperre und git-Spiegel tun, was sie sollen.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

import kalender
import kalender_ics
import kalender_migration
import kalender_sicherung as sich
import kalender_speicher
from kalender_ics import IcsSpeicher, ohne_interna
from kalender_json import JsonSpeicher
from _kalender_voll import ohne_erlebt, voll

FIX = Path(__file__).parent / "fixtures" / "kalender" / "vdir"


@pytest.fixture
def ics(tmp_path, monkeypatch):
    """Die Fassade im .ics-Modus, alles in tmp_path."""
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "ics")
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "ai_calendar.json")
    kalender_ics.cache_leeren()
    yield kalender
    kalender_ics.cache_leeren()


def _sp(tmp_path, **kw) -> IcsSpeicher:
    kw.setdefault("anker", date(2026, 6, 3))
    return IcsSpeicher(tmp_path / "kalender", tmp_path / "kalender_neben.json",
                       tmp_path / "kalender_verlauf", tmp_path / "kalender_snapshots", **kw)


def _ics_dateien(tmp_path):
    return sorted((tmp_path / "kalender").rglob("*.ics"))


def _aussen_sauber(obj):
    """Nirgends darf ein internes _ics-Feld nach außen dringen."""
    if isinstance(obj, dict):
        assert not any(isinstance(k, str) and k.startswith("_ics") for k in obj), obj
        for v in obj.values():
            _aussen_sauber(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _aussen_sauber(v)


# ── Rundreise: nichts geht verloren ────────────────────────────────────

def test_voller_kalender_rundreise_exakt(tmp_path):
    sp = _sp(tmp_path)
    sp.speichern(voll(), erlaube_massenloeschung=True)
    kalender_ics.cache_leeren()
    zurueck = ohne_interna(sp.laden())
    erwartet = ohne_erlebt()
    assert kalender_migration._unterschiede(erwartet, zurueck) == []
    assert zurueck == erwartet
    # auch die Reihenfolge der Tage im Dict (bestimmt die Reihenfolge
    # gleichzeitiger Termine und damit den Text der Alarme)
    assert list(zurueck["layers"]) == list(erwartet["layers"])
    for n in erwartet["layers"]:
        assert list(zurueck["layers"][n]["entries"]) == list(erwartet["layers"][n]["entries"])
    assert list(zurueck) == list(erwartet)


def test_erlebt_wandert_unveraendert_ins_archiv(tmp_path):
    sp = _sp(tmp_path)
    sp.speichern(voll(), erlaube_massenloeschung=True)
    neben = json.loads((tmp_path / "kalender_neben.json").read_text(encoding="utf-8"))
    assert neben["archiv"]["erlebt"] == voll()["layers"]["erlebt"]
    assert not (tmp_path / "kalender" / "erlebt").exists()


def test_feld_inventar_findet_jedes_feld(tmp_path):
    sp = _sp(tmp_path)
    sp.speichern(voll(), erlaube_massenloeschung=True)
    inv = kalender_migration.feld_inventar(voll(), sp)
    assert inv["fehlend"] == []
    assert inv["erlebt_im_archiv"]
    w = inv["wohin"]
    assert w["label"]["SUMMARY"] >= 10
    assert "X-ZENTRALE-ABSAGE-NOETIG" in w["absage_noetig"]
    assert "EXDATE + X-ZENTRALE-AUS" in w["aus"]
    assert any("ZEIT-ROH" in z for z in w["time"])               # "9:30"
    assert "X-ZENTRALE-EXTRAS" in w["tags"]
    assert "Nebendaten nicht_abbildbar" in w["termin (nicht abbildbar)"]


def test_eine_datei_pro_termin_und_routine(tmp_path):
    sp = _sp(tmp_path)
    sp.speichern(voll(), erlaube_massenloeschung=True)
    v = ohne_erlebt()
    termine = sum(len(l) for lobj in v["layers"].values()
                  for t, l in lobj["entries"].items()
                  if t != "2026-13-01" and l and not any(e.get("label") == "Verdreht" for e in l))
    routinen = sum(len(lobj["routines"]) for lobj in v["layers"].values())
    assert len(_ics_dateien(tmp_path)) == termine + routinen
    # Ordner = Ebenen, mit vdir-Metadaten für vdirsyncer
    assert (tmp_path / "kalender" / "termine" / "displayname").read_text().strip() == "Termine"
    assert (tmp_path / "kalender" / "routinen" / "color").read_text().strip() == "#5577ff"


# ── json und ics: dieselben öffentlichen Ergebnisse ────────────────────

def test_beide_speicher_liefern_dasselbe(tmp_path):
    """Der Kern des Umschalters: über ALLE öffentlichen Lesefunktionen
    (dieselbe Liste wie die Migrations-Prüfung) gleich."""
    sp_ics = _sp(tmp_path / "i")
    sp_ics.speichern(voll(), erlaube_massenloeschung=True)
    sp_json = JsonSpeicher(tmp_path / "j" / "ai_calendar.json")
    sp_json.speichern(ohne_erlebt())
    n, abw = kalender_migration.funktionen_vergleichen(
        sp_json, sp_ics, voll(), heute=date(2026, 7, 1), jahre=1)
    assert n > 300
    assert abw == []


SZENARIO = [
    ("add_entry", ("termine", "2026-06-20", "Zahnarzt"), {"time": "09:30", "ort": "Praxis"}),
    ("add_entry", ("termine", "2026-06-20", "Zweiter"), {"time": "9"}),
    ("add_span", ("termine", "2026-06-22", "2026-06-25", "Urlaub"), {"ort": "See"}),
    ("set_span_time", ("termine", "2026-06-22", "Urlaub", "2026-06-24", "14:00"), {}),
    ("add_routine", ("routinen", "Geige", "FREQ=WEEKLY;BYDAY=TU"), {"time": "17:45", "ende": "18:30",
                                                                    "absage_noetig": True}),
    ("add_routine", ("routinen", "Parkour", "FREQ=WEEKLY;BYDAY=WE"), {"time": "18:00"}),
    ("add_routine", ("routinen", "Parkour", "FREQ=WEEKLY;BYDAY=FR"), {"time": "20:00"}),
    ("set_routine_skip", ("routinen", "Parkour", "2026-06-19"), {"off": True, "time": "20:00"}),
    ("add_pause", ("Geige", "2026-06-29", "2026-07-10"), {"grund": "Ferien"}),
    ("add_entry", ("termine", "2026-06-30", "Reise"), {"bis": "2026-07-02", "ort": "Wien"}),
    ("routine_aendern", ("geige",), {"time": "18:00"}),
    ("delete_entry", ("2026-06-20", "zweit"), {}),
    ("add_layer", ("training", "Training", "#00ff00", False), {}),
    ("add_entry", ("training", "2026-06-21", "Lauf"), {}),
    ("delete_routine", ("routinen", "Parkour"), {"day": "2026-06-17"}),
    ("set_span_time", ("termine", "2026-06-22", "Urlaub", "2026-06-24", ""), {}),
]


def _szenario_spielen(k):
    ergebnisse = []
    k.ensure_init()
    for name, args, kw in SZENARIO:
        ergebnisse.append((name, getattr(k, name)(*args, **kw)))
    ref = date(2026, 6, 22)
    ergebnisse.append(("entries", k.entries_in_range(date(2026, 6, 1), date(2026, 7, 31))))
    ergebnisse.append(("week", k.week_view(ref)))
    ergebnisse.append(("month", k.month_view(ref)))
    ergebnisse.append(("read", k.render_range_for_tool(date(2026, 6, 1), date(2026, 7, 31))))
    ergebnisse.append(("finden", k.routine_finden("geige")))
    ergebnisse.append(("konflikt", k.conflicts_for_proposed("termine", "2026-07-01", "X", "18:00")))
    ergebnisse.append(("naechster", k.naechster_termin(datetime(2026, 6, 23, 12, 0))))
    return json.loads(json.dumps(ergebnisse, default=str, sort_keys=True))


def test_dieselben_schreibwege_ergeben_dasselbe(tmp_path, monkeypatch):
    """Dieselben Handgriffe (wie sie TUI und KI-Werkzeuge machen) durch die
    Fassade, einmal je Speicher — jedes Zwischen- und Endergebnis gleich."""
    raus = {}
    for art in ("json", "ics"):
        monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", art)
        monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / art / "ai_calendar.json")
        kalender_ics.cache_leeren()
        raus[art] = _szenario_spielen(kalender)
    assert raus["json"] == raus["ics"]
    _aussen_sauber(raus["ics"])


def test_nichts_internes_dringt_nach_aussen(ics):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "A", time="10:00")
    ics.add_span("termine", "2026-06-21", "2026-06-23", "B")
    ics.add_routine("routinen", "C", "FREQ=WEEKLY;BYDAY=MO", time="08:00")
    _aussen_sauber(ics.entries_in_range(date(2026, 6, 1), date(2026, 6, 30)))
    _aussen_sauber(ics.routine_finden("c"))
    _aussen_sauber(ics.week_view(date(2026, 6, 22)))
    _aussen_sauber(ics.month_view(date(2026, 6, 22)))


def test_erlebt_gibt_es_im_ics_modus_nicht_mehr(ics):
    ics.ensure_init()
    assert "erlebt" not in ics._load_raw()["layers"]
    assert ics.add_entry("erlebt", "2026-06-01", "Sport") is False


# ── Fixtures aus der Kalender-Session über die Fassade ─────────────────

def test_fixtures_ueber_die_fassade(ics, tmp_path):
    shutil.copytree(FIX, tmp_path / "kalender")
    tage = ics.entries_in_range(date(2026, 8, 25), date(2026, 10, 15))

    def am(tag, label):
        return [e for e in tage.get(tag, []) if e["label"] == label]

    messe = {t: (am(t, "Messe")[0].get("time"), am(t, "Messe")[0].get("ende"))
             for t in ("2026-10-07", "2026-10-08", "2026-10-09")}
    assert messe == {"2026-10-07": ("10:00", "18:00"), "2026-10-08": ("09:00", "17:00"),
                     "2026-10-09": ("10:00", "14:00")}
    b = {t: am(t, "Wochenende Berlin")[0] for t in ("2026-10-09", "2026-10-10", "2026-10-11")}
    assert (b["2026-10-09"].get("time"), b["2026-10-09"].get("ende")) == ("18:00", None)
    assert (b["2026-10-10"].get("time"), b["2026-10-10"].get("ende")) == (None, None)
    assert (b["2026-10-11"].get("time"), b["2026-10-11"].get("ende")) == (None, "14:00")
    assert b["2026-10-09"]["span_first"] and b["2026-10-11"]["span_last"]
    assert am("2026-10-03", "Tag der Deutschen Einheit")[0].get("time") is None
    # Geige: Di+Do ab dem 01.09. — davor nicht (eigener Anfang)
    assert not am("2026-08-27", "Geige") and not am("2026-08-25", "Geige")
    assert am("2026-09-01", "Geige") and am("2026-09-03", "Geige")
    assert am("2026-09-01", "Geige")[0]["recurring"] is True
    assert am("2026-09-05", "Parkour")[0]["time"] == "18:30"
    # Die Ebenen kommen aus den Ordnern, auch ohne Nebendaten.
    assert set(ics._load_raw()["layers"]) == {"termine", "routinen"}


def test_fremde_datei_wird_beim_zurueckschreiben_nicht_beschaedigt(ics, tmp_path):
    shutil.copytree(FIX, tmp_path / "kalender")
    ics.set_span_time("termine", "2026-10-07", "Messe", "2026-10-08", "08:00")
    tag = ics.entries_in_range(date(2026, 10, 7), date(2026, 10, 9))
    zeiten = [(t, e.get("time"), e.get("ende")) for t, es in tag.items() for e in es
              if e["label"] == "Messe"]
    assert zeiten == [("2026-10-07", "10:00", "18:00"), ("2026-10-08", "08:00", "17:00"),
                      ("2026-10-09", "10:00", "14:00")]
    # dieselbe Datei (gleicher Name), weiterhin EINE UID
    text = (tmp_path / "kalender" / "termine" / "messe.ics").read_text()
    assert text.count("UID:messe") == 4  # Master + 3 Abweichungen


# ── Nur ändern, was sich ändert ────────────────────────────────────────

def test_ein_termin_fasst_nur_seine_datei_an(ics, tmp_path):
    ics.ensure_init()
    for i in range(5):
        ics.add_entry("termine", f"2026-06-{10 + i}", f"T{i}", time="10:00")
    vorher = {p: (p.stat().st_mtime_ns, p.stat().st_ino) for p in _ics_dateien(tmp_path)}
    ics.add_entry("termine", "2026-06-20", "Neu")
    nachher = {p: (p.stat().st_mtime_ns, p.stat().st_ino) for p in _ics_dateien(tmp_path)}
    assert len(nachher) == len(vorher) + 1
    assert all(nachher[p] == v for p, v in vorher.items())


def test_aenderung_landet_im_verlauf(ics, tmp_path):
    ics.ensure_init()
    ics.add_routine("routinen", "Geige", "FREQ=WEEKLY;BYDAY=TU", time="17:45")
    ics.routine_aendern("geige", time="18:00")
    v = sich.verlauf_liste(tmp_path / "kalender_verlauf")
    assert [x["aktion"] for x in v if x["ebene"] == "routinen"] == ["geaendert"]
    alt = v[0]["pfad"].read_text() if v[0]["ebene"] == "routinen" else \
        [x for x in v if x["ebene"] == "routinen"][0]["pfad"].read_text()
    assert "T174500" in alt                      # die ALTE Fassung


def test_loeschen_hinterlaesst_verlauf_und_grabstein(ics, tmp_path):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "Weg")
    assert ics.delete_entry("2026-06-20", "weg") == 1
    assert _ics_dateien(tmp_path) == []
    v = sich.verlauf_liste(tmp_path / "kalender_verlauf")
    assert [x["aktion"] for x in v] == ["geloescht"]
    assert len(sich.grabsteine_lesen(tmp_path / "kalender_verlauf")) == 1


def test_wiederherstellen_holt_den_termin_zurueck(ics, tmp_path):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "Weg", time="10:00")
    ics.delete_entry("2026-06-20", "weg")
    v = sich.verlauf_liste(tmp_path / "kalender_verlauf")[0]
    sp = kalender_speicher.ics_speicher(ics.CAL_PATH)
    uid = sp.wiederherstellen(v["pfad"])
    assert uid
    assert [e["label"] for e in ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))["2026-06-20"]] == ["Weg"]
    assert sich.grabsteine_lesen(tmp_path / "kalender_verlauf") == {}


def test_wiederherstellen_ist_selbst_umkehrbar(ics, tmp_path):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "A", time="10:00")
    ics.delete_entry("2026-06-20", "a")
    ics.add_entry("termine", "2026-06-21", "B")
    geloescht = sich.verlauf_liste(tmp_path / "kalender_verlauf")[0]
    sp = kalender_speicher.ics_speicher(ics.CAL_PATH)
    sp.wiederherstellen(geloescht["pfad"])
    sp.wiederherstellen(geloescht["pfad"])      # zweimal: die jetzige wandert vorher weg
    aktionen = [x["aktion"] for x in sich.verlauf_liste(tmp_path / "kalender_verlauf")]
    assert "vor-wiederherstellen" in aktionen


# ── Grabsteine: der Sync bringt Gelöschtes nicht zurück ─────────────────

def test_vom_sync_zurueckgebrachte_datei_ist_ein_geist(ics, tmp_path):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "Weg")
    datei = _ics_dateien(tmp_path)[0]
    kopie = datei.read_bytes()
    ics.delete_entry("2026-06-20", "weg")
    datei.write_bytes(kopie)                    # rsync vom anderen Knoten
    kalender_ics.cache_leeren()
    assert not ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))
    ics.add_entry("termine", "2026-06-21", "Anderes")   # nächstes Schreiben räumt auf
    assert not datei.exists()
    assert "geist" in [x["aktion"] for x in sich.verlauf_liste(tmp_path / "kalender_verlauf")]


def test_spaeter_bearbeitete_datei_ist_kein_geist(ics, tmp_path):
    """Hat der andere Knoten den Termin NACH der Löschung bearbeitet, gilt
    die neuere Fassung — neueste gewinnt, wie beim Sync."""
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "Weg")
    datei = _ics_dateien(tmp_path)[0]
    kopie = datei.read_text()
    ics.delete_entry("2026-06-20", "weg")
    spaeter = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y%m%dT%H%M%SZ")
    import re
    kopie = re.sub(r"LAST-MODIFIED:\d+T\d+Z", f"LAST-MODIFIED:{spaeter}", kopie)
    datei.write_text(kopie)
    kalender_ics.cache_leeren()
    assert ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))["2026-06-20"][0]["label"] == "Weg"


def test_aufraeumen_vor_vdirsyncer(ics, tmp_path):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "Weg")
    datei = _ics_dateien(tmp_path)[0]
    kopie = datei.read_bytes()
    ics.delete_entry("2026-06-20", "weg")
    datei.write_bytes(kopie)
    assert kalender_speicher.ics_speicher(ics.CAL_PATH).aufraeumen() == 1
    assert not datei.exists()


# ── Massenlösch-Sperre ─────────────────────────────────────────────────

def test_massenloeschung_wird_verweigert(ics, tmp_path):
    ics.ensure_init()
    for i in range(7):
        ics.add_entry("termine", "2026-06-20", f"Probe {i}")
    with pytest.raises(sich.KalenderGesperrt):
        ics.delete_entry("2026-06-20", "probe")
    # NICHTS gelöscht — alles oder nichts
    assert len(ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))["2026-06-20"]) == 7
    assert len(_ics_dateien(tmp_path)) == 7


def test_sperre_ist_einstellbar(ics, monkeypatch):
    monkeypatch.setenv("ZENTRALE_KALENDER_LOESCHSPERRE", "10")
    ics.ensure_init()
    for i in range(7):
        ics.add_entry("termine", "2026-06-20", f"Probe {i}")
    assert ics.delete_entry("2026-06-20", "probe") == 7


def test_fuenf_auf_einmal_gehen_noch(ics):
    ics.ensure_init()
    for i in range(5):
        ics.add_entry("termine", "2026-06-20", f"Probe {i}")
    assert ics.delete_entry("2026-06-20", "probe") == 5


# ── Robustheit ─────────────────────────────────────────────────────────

def test_kaputte_datei_wird_uebersprungen_und_nie_geloescht(ics, tmp_path):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "Gut")
    kaputt = tmp_path / "kalender" / "termine" / "kaputt.ics"
    kaputt.write_text("BEGIN:VCALENDAR\nDas ist Murks")
    kalender_ics.cache_leeren()
    assert [e["label"] for e in ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))["2026-06-20"]] == ["Gut"]
    ics.add_entry("termine", "2026-06-21", "Noch einer")
    assert kaputt.exists()


def test_externe_aenderung_wird_gesehen(ics, tmp_path):
    """Der Lese-Cache darf eine Änderung durch vdirsyncer nicht verdecken."""
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "Alt")
    ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))
    datei = _ics_dateien(tmp_path)[0]
    datei.write_text(datei.read_text().replace("SUMMARY:Alt", "SUMMARY:Neu am Handy"))
    assert ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))["2026-06-20"][0]["label"] == "Neu am Handy"


def test_neuer_kalender_von_aussen_wird_eine_ebene(ics, tmp_path):
    ics.ensure_init()
    o = tmp_path / "kalender" / "arbeit"
    o.mkdir()
    (o / "displayname").write_text("Arbeit\n")
    shutil.copy(FIX / "termine" / "kino.ics", o / "kino.ics")
    kalender_ics.cache_leeren()
    lyr = ics._load_raw()["layers"]["arbeit"]
    assert lyr["label"] == "Arbeit"
    assert ics.entries_in_range(date(2026, 10, 14), date(2026, 10, 14))["2026-10-14"][0]["layer"] == "arbeit"


def test_zwischen_laden_und_speichern_extern_geloescht_bleibt_geloescht(tmp_path):
    sp = _sp(tmp_path)
    d = {"version": 1, "layers": {"termine": {"label": "T", "entries": {
        "2026-06-20": [{"label": "A"}], "2026-06-21": [{"label": "B"}]}, "routines": []}}}
    sp.speichern(d)
    kalender_ics.cache_leeren()
    geladen = sp.laden()
    # vdirsyncer löscht A (am Handy gelöscht), während ZENTRALE B ändert
    for p in _ics_dateien(tmp_path):
        if "SUMMARY:A" in p.read_text():
            p.unlink()
    geladen["layers"]["termine"]["entries"]["2026-06-21"][0]["label"] = "B2"
    sp.speichern(geladen)
    kalender_ics.cache_leeren()
    labels = [e["label"] for es in sp.laden()["layers"]["termine"]["entries"].values() for e in es]
    assert labels == ["B2"]


def test_pause_ohne_routine_geht_nicht_verloren(ics):
    ics.ensure_init()
    ics.add_pause("Gibtsnicht", "2026-07-01", "2026-07-10", grund="x")
    assert ics._load_raw()["pausen"] == [{"label": "Gibtsnicht", "von": "2026-07-01",
                                          "bis": "2026-07-10", "grund": "x"}]


def test_pause_markiert_die_routine_als_ausgefallen(ics):
    ics.ensure_init()
    ics.add_routine("routinen", "Geige", "FREQ=WEEKLY;BYDAY=TU", time="17:45")
    ics.add_pause("Geige", "2026-07-01", "2026-07-10", grund="Ferien")
    e = ics.entries_in_range(date(2026, 7, 7), date(2026, 7, 7))["2026-07-07"][0]
    assert e["ausfall"] == "Ferien"


# ── Rückfall-Sperre und Umschalter ─────────────────────────────────────

def test_json_schreibt_nicht_mehr_nach_der_migration(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "json")
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "ai_calendar.json")
    (tmp_path / "kalender_neben.json").write_text(json.dumps({"migriert_am": "2026-10-07T08:00:00+00:00"}))
    with pytest.raises(sich.KalenderGesperrt):
        kalender.add_entry("termine", "2026-06-20", "X")
    assert not (tmp_path / "ai_calendar.json").exists()


def test_ohne_marker_schreibt_json_wie_immer(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "json")
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "ai_calendar.json")
    (tmp_path / "kalender_neben.json").write_text("{}")
    assert kalender.add_entry("termine", "2026-06-20", "X")


@pytest.mark.parametrize("wert,erwartet", [("json", "json"), ("ics", "ics"), ("ICS", "ics"),
                                           ("murks", "json"), ("", "json")])
def test_umschalter_werte(monkeypatch, wert, erwartet):
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", wert)
    assert kalender_speicher.modus() == erwartet


def test_default_ist_json(monkeypatch):
    monkeypatch.delenv("ZENTRALE_KALENDER_SPEICHER", raising=False)
    import ai_config
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_legacy", {})
    assert kalender_speicher.modus() == "json"
    assert kalender._speicher().art == "json"


def test_pfade_liegen_neben_der_alten_datei(tmp_path):
    p = kalender_speicher.pfade(tmp_path / "ai_calendar.json")
    assert p["vdir"] == tmp_path / "kalender"
    assert p["neben"] == tmp_path / "kalender_neben.json"
    assert p["verlauf"] == tmp_path / "kalender_verlauf"


# ── Snapshots ──────────────────────────────────────────────────────────

def test_erstes_schreiben_des_tages_macht_snapshot(ics, tmp_path):
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "A")
    ics.add_entry("termine", "2026-06-21", "B")
    snaps = list((tmp_path / "kalender_snapshots").glob("*.tar.gz"))
    assert len(snaps) == 1
    import tarfile
    with tarfile.open(snaps[0]) as t:
        namen = t.getnames()
    # Stand VOR dem ersten Termin-Schreiben: Nebendaten ja, Termin A noch nicht
    assert "kalender_neben.json" in namen
    assert not any(n.endswith(".lock") for n in namen)


# ── git-Spiegel ────────────────────────────────────────────────────────

@pytest.mark.skipif(not shutil.which("git"), reason="git fehlt")
def test_git_spiegel_committet_jede_aenderung(ics, tmp_path, monkeypatch):
    ziel = tmp_path / "spiegel"
    monkeypatch.setenv("ZENTRALE_KALENDER_GIT_SPIEGEL", str(ziel))
    import kalender_spiegel
    echt = kalender_spiegel.spiegeln
    monkeypatch.setattr(kalender_spiegel, "spiegeln",
                        lambda q, z, g, warten=False: echt(q, z, g, warten=True))
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-20", "A")
    ics.delete_entry("2026-06-20", "a")
    log = subprocess.run(["git", "log", "--oneline"], cwd=ziel, capture_output=True, text=True).stdout
    assert len(log.strip().splitlines()) == 3
    assert not list((ziel / "kalender").rglob("*.ics"))           # Löschung gespiegelt
    assert (ziel / "kalender_neben.json").exists()
    assert not (ziel / "kalender" / ".zentrale.lock").exists()


def test_kaputter_git_spiegel_verhindert_nie_das_schreiben(ics, tmp_path, monkeypatch):
    blockade = tmp_path / "datei_statt_ordner"
    blockade.write_text("x")
    monkeypatch.setenv("ZENTRALE_KALENDER_GIT_SPIEGEL", str(blockade / "repo"))
    import kalender_spiegel
    echt = kalender_spiegel.spiegeln
    monkeypatch.setattr(kalender_spiegel, "spiegeln",
                        lambda q, z, g, warten=False: echt(q, z, g, warten=True))
    ics.ensure_init()
    assert ics.add_entry("termine", "2026-06-20", "A") is True
    assert ics.entries_in_range(date(2026, 6, 20), date(2026, 6, 20))


def test_spiegel_ist_in_tests_aus():
    assert kalender_speicher.git_spiegel_pfad() is None


# ── Der vdirsyncer-Wrapper ─────────────────────────────────────────────

def _falsches_vdirsyncer(tmp_path, monkeypatch, skript):
    """Ein Ersatz-vdirsyncer im PATH: kein Netz, kein Google."""
    b = tmp_path / "bin"
    b.mkdir()
    exe = b / "vdirsyncer"
    exe.write_text(f"#!{sys.executable}\n" + skript)
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}{os.pathsep}{os.environ['PATH']}")


def test_wrapper_laeuft_nur_im_ics_modus(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import kalender_sync
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "json")
    assert kalender_sync.main([]) == 1
    assert "nicht auf 'ics'" in capsys.readouterr().out


def test_wrapper_raeumt_geister_und_meldet_schwund(ics, tmp_path, monkeypatch, capsys):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import kalender_sync
    ics.ensure_init()
    ics.add_entry("termine", "2026-06-19", "Geist")
    geist = _ics_dateien(tmp_path)[0]
    kopie = geist.read_bytes()
    ics.delete_entry("2026-06-19", "geist")
    geist.write_bytes(kopie)                          # vom Sync zurückgebracht
    for i in range(8):
        ics.add_entry("termine", "2026-06-20", f"T{i}")
    gesehen = tmp_path / "gesehen.txt"
    vdir = tmp_path / "kalender" / "termine"
    _falsches_vdirsyncer(tmp_path, monkeypatch, f"""
import pathlib, sys
v = pathlib.Path({str(vdir)!r})
pathlib.Path({str(gesehen)!r}).write_text("\\n".join(sorted(p.name for p in v.glob("*.ics"))))
for p in sorted(v.glob("*.ics"))[:7]:
    p.unlink()
sys.exit(3)
""")
    assert kalender_sync.main([]) == 3                # Exit-Code von vdirsyncer
    assert geist.name not in gesehen.read_text()      # Geist vorher weg
    assert "ACHTUNG: 7 Termine" in capsys.readouterr().out
