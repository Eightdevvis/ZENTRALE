"""
Tagesrhythmus (Phasen) und Gruppen (CATEGORIES) — seit 10.10.2026.

Sasha: „jeder mensch hat nen rythmus … ‚ich werde gegen 10 hungrig' ist kein
termin … wenn ich heute come down um 9:30 habe, dann 3 tage um 2 in sbett
gehe, muss das änderbar sein" und „in der monatsansicht seh ich lieber uni
uni uni". Geprüft gegen BEIDE Speicher:
  * Phase mit Motiv, über Mitternacht, pro Tag / pro Zeitraum / ab jetzt,
  * Phasen sind nie ein Termin (kein Alarm, keine Rückfrage, kein Countdown),
  * die KI liest sie als eigene, ruhige Zeile,
  * Gruppe hin und zurück (.ics CATEGORIES), für einen ganzen Kurs,
  * jede Ablehnung schreibt nichts.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_ics
import kalender_kategorie
import kalender_kennung as kk
import kalender_rhythmus

pytestmark = pytest.mark.kalender_beide

VON = "2026-10-01"


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_routine("termine", "Geigenstunde", "FREQ=WEEKLY;BYDAY=TU",
                         time="17:45", ende="18:30")
    kalender.add_entry("termine", "2026-10-14", "Kino", time="19:00", ende="21:00")
    return tmp_path


def _stand(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != ".zentrale.lock"}


def _tag(iso):
    return kalender.entries_in_range(date.fromisoformat(iso), date.fromisoformat(iso)).get(iso, [])


def _k(label):
    return next(e["kennung"] for e in kk.alle_eintraege() if e["label"] == label)


def _ics():
    return kalender._speicher().art == "ics"


def _ics_text(tmp_path, ordner):
    return "\n".join(p.read_text() for p in tmp_path.rglob(f"{ordner}/*.ics"))


def _schlaf():
    return kk.phase_anlegen("Schlaf", "23:00", ende="07:00", motiv="schlaf", von=VON)


# ── Phase anlegen ──────────────────────────────────────────────────────
def test_phase_anlegen_mit_motiv(cal):
    p = kk.phase_anlegen("Hunger", "10:00", motiv="Essen", von=VON)
    assert p["layer"] == "rhythmus" and p["motiv"] == "essen" and p["art"] == "routine"
    assert p["kennung"] and p["kategorie"] == "keine" and p["seit"] == VON
    e = [x for x in _tag("2026-10-05") if x["label"] == "Hunger"][0]
    assert e["layer"] == "rhythmus" and e["motiv"] == "essen" and e["kennung"] == p["kennung"]
    assert kk.phasen() == [kk.eintrag(p["kennung"])]
    assert not _tag("2026-09-30") or all(x["label"] != "Hunger" for x in _tag("2026-09-30"))


def test_phase_ueber_mitternacht(cal):
    p = _schlaf()
    assert (p["time"], p["ende"]) == ("23:00", "07:00")
    e = [x for x in _tag("2026-10-06") if x["label"] == "Schlaf"][0]
    assert e["ueber_nacht"] is True and e["ende"] == "07:00"
    # normale Termine bleiben streng
    with pytest.raises(kk.KalenderAbgelehnt) as f:
        kk.routine_aendern(_k("Geigenstunde"), ende="17:00")
    assert f.value.code == "ENDE-VOR-BEGINN"
    if _ics():
        text = _ics_text(cal, "rhythmus")
        assert "TRANSP:TRANSPARENT" in text and "X-ZENTRALE-MOTIV:schlaf" in text
        assert "DTEND;TZID=Europe/Berlin:20261002T070000" in text
        assert "X-ZENTRALE-EXTRAS" not in text            # alles echt abgebildet
        assert "TRANSP" not in _ics_text(cal, "termine")
        kalender_ics.cache_leeren()
        assert kk.eintrag(p["kennung"]) == p


def test_phase_bis_auf_weiteres_und_ende(cal):
    k = _schlaf()["kennung"]
    p = kk.phase_aendern(k, bis="2026-10-10")
    assert "UNTIL=20261010" in p["rrule"]
    assert any(x["label"] == "Schlaf" for x in _tag("2026-10-10"))
    assert not any(x["label"] == "Schlaf" for x in _tag("2026-10-11"))
    p = kk.phase_aendern(k, bis="", time="22:30", motiv="nachthimmel")
    assert "UNTIL" not in p["rrule"] and p["time"] == "22:30" and p["motiv"] == "nachthimmel"
    assert any(x["label"] == "Schlaf" for x in _tag("2026-11-11"))


# ── Variabel: ein Tag, ein Zeitraum ────────────────────────────────────
def test_phase_tag_aendern(cal):
    k = _schlaf()["kennung"]
    kk.routine_tag_aendern(k, "2026-10-07", time="23:30", ende="06:30")
    e = [x for x in _tag("2026-10-07") if x["label"] == "Schlaf"][0]
    assert (e["time"], e["ende"], e["ueber_nacht"]) == ("23:30", "06:30", True)
    kalender_ics.cache_leeren()
    assert kk.eintrag(k)["abweichungen"]["2026-10-07"] == {
        "tag": "2026-10-07", "time": "23:30", "ende": "06:30"}


def test_phase_zeitraum_aendern(cal):
    """„3 Tage um 2 ins Bett"."""
    k = _schlaf()["kennung"]
    p = kk.routine_zeitraum_aendern(k, "2026-10-12", "2026-10-14", time="02:00", ende="09:00")
    assert sorted(p["abweichungen"]) == ["2026-10-12", "2026-10-13", "2026-10-14"]
    for t in ("2026-10-12", "2026-10-13", "2026-10-14"):
        e = [x for x in _tag(t) if x["label"] == "Schlaf"][0]
        assert (e["time"], e["ende"]) == ("02:00", "09:00") and not e.get("ueber_nacht")
    assert [x["time"] for x in _tag("2026-10-15") if x["label"] == "Schlaf"] == ["23:00"]
    # zurück zur Regel: Abweichungen fallen weg
    p = kk.routine_zeitraum_aendern(k, "2026-10-12", "2026-10-14", time="", ende="")
    assert "abweichungen" not in p
    assert [x["time"] for x in _tag("2026-10-13") if x["label"] == "Schlaf"] == ["23:00"]


def test_zeitraum_auch_fuer_normale_routinen(cal):
    k = _k("Geigenstunde")
    kk.routine_zeitraum_aendern(k, "2026-10-01", "2026-10-31", ort="Aula")
    assert all(x["ort"] == "Aula" for t in ("2026-10-06", "2026-10-27")
               for x in _tag(t) if x["label"] == "Geigenstunde")


# ── Nie ein Termin ─────────────────────────────────────────────────────
def test_phasen_machen_keine_alarme_und_keinen_countdown(cal, monkeypatch):
    morgen = date.today() + timedelta(days=1)
    kalender.add_entry("termine", morgen.isoformat(), "Probe", time="20:00", ende="22:00")
    kk.phase_anlegen("Runterkommen", "19:30", ende="23:00", motiv="nachthimmel",
                     von=date.today().isoformat())
    assert not any("Runterkommen" in a["text"] for a in kalender.open_alarms(5))
    assert kalender.conflicts_for_proposed("termine", morgen.isoformat(), "Neu",
                                           "20:00", "21:00") != []          # Probe zählt
    assert not any("Runterkommen" in z for z in kalender.conflicts_for_proposed(
        "termine", morgen.isoformat(), "Neu", "20:00", "21:00"))
    assert kalender.conflicts_for_proposed("rhythmus", morgen.isoformat(), "X",
                                           "20:00", "21:00") == []
    from datetime import datetime
    n = kalender.naechster_termin(datetime.combine(morgen, datetime.min.time()))
    assert n and n["label"] == "Probe"


def test_ki_liest_ruhige_zeile_und_hinweis(cal):
    _schlaf()
    text = kalender.render_range_for_tool(date(2026, 10, 6), date(2026, 10, 6))
    assert "  [rhythmus · schlaf] 23:00-07:00 (bis Folgetag) Schlaf" in text
    imp = kalender.imprint_for_prompt(0)
    assert "[rhythmus · schlaf]" in imp and "Tagesrhythmus" in imp and "KEIN Termin" in imp


def test_phase_wechselt_nicht_die_ebene(cal):
    k = _schlaf()["kennung"]
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt) as f:
        kk.ebene_wechseln(k)
    assert f.value.code == "IST-PHASE" and _stand(cal) == vorher


# ── Gruppen ────────────────────────────────────────────────────────────
def test_kategorie_hin_und_zurueck(cal):
    k = _k("Kino")
    e = kk.kategorie_setzen(k, "Uni")
    assert e["kategorie"] == "uni" and "kategorie_name" not in e
    assert [x["kategorie"] for x in _tag("2026-10-14")] == ["uni"]
    assert "[termine · Uni] 19:00-21:00 Kino" in kalender.render_range_for_tool(
        date(2026, 10, 14), date(2026, 10, 14))
    if _ics():
        assert "CATEGORIES:Uni" in _ics_text(cal, "termine")
    e = kk.kategorie_setzen(k, "custom", "Chor")
    assert (e["kategorie"], e["kategorie_name"]) == ("custom", "Chor")
    if _ics():
        assert "CATEGORIES:Chor" in _ics_text(cal, "termine")
        kalender_ics.cache_leeren()
        assert kk.eintrag(k) == e
    # ein eigener Name, der zum Katalog passt, ist der Katalog
    assert kk.kategorie_setzen(k, "custom", "arbeit")["kategorie"] == "arbeit"
    e = kk.kategorie_setzen(k, "keine")
    assert e["kategorie"] == "keine"
    if _ics():
        assert "CATEGORIES" not in _ics_text(cal, "termine")


def test_kategorie_an_routine_vorkommen_und_beim_anlegen(cal):
    kk.routine_aendern(_k("Geigenstunde"), kategorie="custom", kategorie_name="Musik")
    e = [x for x in _tag("2026-10-06") if x["label"] == "Geigenstunde"][0]
    assert (e["kategorie"], e["kategorie_name"]) == ("custom", "Musik")
    kalender.add_entry("termine", "2026-10-20", "Klausur", time="10:00", kategorie="uni")
    assert kk.eintrag(_k("Klausur"))["kategorie"] == "uni"
    p = kk.phase_anlegen("Lernen", "09:00", ende="12:00", motiv="fokus", von=VON,
                         kategorie="uni")
    assert p["kategorie"] == "uni"


def test_kategorie_beim_anlegen_aus_der_tui(cal):
    """Das TUI-Formular (Feld „Gruppe") legt Routine und Spanne über
    kalender_bearbeiten an — die Gruppe kommt gleich mit (10.10.2026)."""
    import kalender_bearbeiten as kb
    assert kb.routine_neu("termine", "Analysis Übung", VON, "w", 1, None, ["WE"], "12:00",
                          "14:00", None, "uni")
    assert kk.eintrag(_k("Analysis Übung"))["kategorie"] == "uni"
    assert kb.spanne_neu("termine", "2026-10-20", "2026-10-21", "Exkursion",
                         tageszeit=("09:00", "17:00"), kategorie="custom",
                         kategorie_name="Feldarbeit")
    e = kk.eintrag(_k("Exkursion"))
    assert (e["kategorie"], e["kategorie_name"]) == ("custom", "Feldarbeit")
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt):
        kb.spanne_neu("termine", "2026-10-22", "2026-10-23", "X", kategorie="hobby")
    assert _stand(cal) == vorher


def test_kategorie_fuer_kurs(cal):
    kalender.add_entry("termine", "2026-10-15", "Analysis I @ HS 1", time="10:00")
    kalender.add_routine("termine", "Analysis Übung", "FREQ=WEEKLY;BYDAY=WE", time="12:00")
    kalender.add_routine("termine", "ExPhy Vorlesung", "FREQ=WEEKLY;BYDAY=TH", time="08:30")
    kalender.add_span("termine", "2026-10-20", "2026-10-21", "Analysis Klausurphase")
    kk.phase_anlegen("Analysis lernen", "20:00", motiv="fokus", von=VON)   # Phase: nie
    vorher = _stand(cal)
    p = kk.kategorie_fuer_kurs("Analysis", "uni", probe=True)
    assert p["geaendert"] == 3 and _stand(cal) == vorher
    assert {e["kategorie"] for e in p["eintraege"]} == {"uni"}
    r = kk.kategorie_fuer_kurs("analysis", "uni")
    assert r["schluessel"] == "analysis" and r["geaendert"] == 3
    assert {e["label"] for e in r["eintraege"]} == {
        "Analysis I @ HS 1", "Analysis Übung", "Analysis Klausurphase"}
    assert kk.kategorie_fuer_kurs("Experimentalphysik", "uni")["geaendert"] == 1
    assert kk.kategorie_fuer_kurs("exphy", "uni")["geaendert"] == 0      # schon gesetzt
    assert kk.eintrag(_k("Analysis lernen"))["kategorie"] == "keine"
    assert kk.eintrag(_k("Kino"))["kategorie"] == "keine"


def test_titel_schluessel_wie_die_tui():
    t = kalender_kategorie.titel_schluessel
    assert t("Analysis I @ HS 1") == "analysis"
    assert t("ExPhy-Übung") == "experimentalphysik"
    assert t("Theoretische Physik") == "theoretische"
    assert t("") == ""


# ── Ablehnen schreibt nichts ───────────────────────────────────────────
@pytest.mark.parametrize("aufruf,code", [
    (lambda: kk.phase_anlegen("X", "10:00", motiv="einhorn", von=VON), "MOTIV-UNBEKANNT"),
    (lambda: kk.phase_anlegen("X", "", motiv="schlaf", von=VON), "PHASE-OHNE-ZEIT"),
    (lambda: kk.phase_anlegen("X", "10:00", ende="10:00", motiv="schlaf", von=VON),
     "ENDE-VOR-BEGINN"),
    (lambda: kk.phase_anlegen("X", "10:00", motiv="schlaf", von=VON, bis="2026-09-01"),
     "SPANNE-VERDREHT"),
    (lambda: kk.phase_anlegen("X", "10:00", motiv="schlaf", von=VON, kategorie="hobby"),
     "KATEGORIE-UNBEKANNT"),
    (lambda: kk.kategorie_setzen(_k("Kino"), "foo"), "KATEGORIE-UNBEKANNT"),
    (lambda: kk.kategorie_setzen(_k("Kino"), "custom"), "KATEGORIE-NAME-FEHLT"),
    (lambda: kk.kategorie_setzen(_k("Kino"), "uni", "Uni2"), "UNBEKANNTES-FELD"),
    (lambda: kk.kategorie_fuer_kurs("Biologie", "uni"), "KEIN-TREFFER"),
    (lambda: kk.phase_aendern(_k("Geigenstunde"), time="18:00"), "KEINE-PHASE"),
    (lambda: kk.phase_loeschen(_k("Geigenstunde")), "KEINE-PHASE"),
    (lambda: kk.routine_aendern(_k("Geigenstunde"), motiv="schlaf"), "KEINE-PHASE"),
    (lambda: kk.routine_zeitraum_aendern(_k("Geigenstunde"), "2026-10-10", "2026-10-01",
                                         time="18:00"), "SPANNE-VERDREHT"),
    (lambda: kk.routine_zeitraum_aendern(_k("Geigenstunde"), "2026-01-01", "2027-06-01",
                                         time="18:00"), "ZEITRAUM-ZU-LANG"),
    (lambda: kk.routine_zeitraum_aendern(_k("Geigenstunde"), "2026-10-07", "2026-10-08",
                                         time="18:00"), "KEIN-VORKOMMEN"),
    (lambda: kk.routine_zeitraum_aendern(_k("Geigenstunde"), "2026-10-01", "2026-10-31",
                                         time="19:00", ende="18:00"), "ENDE-VOR-BEGINN"),
    (lambda: kk.routine_zeitraum_aendern(_k("Geigenstunde"), "2026-10-01", "2026-10-31",
                                         tag="2026-10-02"), "UNBEKANNTES-FELD"),
    (lambda: kalender.add_entry("termine", "2026-10-20", "Y", kategorie="hobby"),
     "KATEGORIE-UNBEKANNT"),
])
def test_ablehnung_schreibt_nichts(cal, aufruf, code):
    _schlaf()
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt) as f:
        aufruf()
    assert f.value.code == code and code in kk.CODES
    assert _stand(cal) == vorher


def test_phase_aendern_ablehnung_schreibt_nichts(cal):
    k = _schlaf()["kennung"]
    vorher = _stand(cal)
    for felder, code in (({"motiv": "x"}, "MOTIV-UNBEKANNT"), ({"ende": "23:00"}, "ENDE-VOR-BEGINN"),
                         ({"time": ""}, "PHASE-OHNE-ZEIT"), ({"bis": "2026-09-01"}, "SPANNE-VERDREHT")):
        with pytest.raises(kk.KalenderAbgelehnt) as f:
            kk.phase_aendern(k, **felder)
        assert f.value.code == code
    assert _stand(cal) == vorher


# ── Kataloge und Routen ────────────────────────────────────────────────
def test_kataloge_fest():
    assert {"nachthimmel", "schlaf", "essen", "sonne", "fokus", "sport", "ruhe",
            "unterwegs"} <= set(kalender_rhythmus.MOTIVE)
    assert set(kalender_kategorie.KATEGORIEN) == {"uni", "arbeit"}
    schl = [x["schluessel"] for x in kalender_kategorie.katalog()]
    assert schl[-2:] == ["keine", "custom"]


def test_abbildung_categories_verlustfrei():
    import kalender_ics_abbildung as abb
    for e in ({"label": "A", "time": "10:00", "kategorie": "custom", "kategorie_name": "Chor, Probe"},
              {"label": "B", "time": "10:00", "kategorie": "uni", "kategorie_name": "x"},
              {"label": "C", "kategorie": "custom", "kategorie_name": "Lesekreis"}):
        kal = abb.termin_kalender("2026-10-14", e, "u1@test")
        assert abb.lesen(kal)[0]["daten"] == e
    text = abb.termin_kalender("2026-10-14", {"label": "C", "kategorie": "custom",
                                             "kategorie_name": "Lesekreis"}, "u2@test").to_ical()
    assert b"CATEGORIES:Lesekreis" in text
    # von außen: mehrere Kategorien, die erste ist die Gruppe
    roh = text.replace(b"CATEGORIES:Lesekreis", b"CATEGORIES:uni,Extra")
    d = abb.datei_lesen(roh)[0]["daten"]
    assert (d["kategorie"], d["kategorien_weitere"]) == ("uni", ["Extra"])
    assert abb.lesen(abb.termin_kalender("2026-10-14", d, "u3@test"))[0]["daten"] == d


def test_routen(cal):
    from ui.app import app
    c = app.test_client()
    assert c.get("/api/calendar/motive").get_json()["ebene"] == "rhythmus"
    assert "uni" in [x["schluessel"] for x in c.get("/api/calendar/kategorien").get_json()["kategorien"]]
    r = c.post("/api/calendar/phase", json={"label": "Schlaf", "time": "23:00", "ende": "07:00",
                                            "motiv": "schlaf", "von": VON})
    assert r.status_code == 200
    k = r.get_json()["kennung"]
    r = c.post("/api/calendar/phase", json={"label": "X", "time": "10:00", "motiv": "einhorn"})
    assert r.status_code == 400 and r.get_json()["code"] == "MOTIV-UNBEKANNT"
    r = c.post("/api/calendar/routine/zeitraum",
               json={"kennung": k, "von": "2026-10-12", "bis": "2026-10-14", "time": "02:00"})
    assert r.status_code == 200 and len(r.get_json()["abweichungen"]) == 3
    assert c.put("/api/calendar/phase", json={"kennung": k, "motiv": "ruhe"}).get_json()["motiv"] == "ruhe"
    tage = c.get("/api/calendar?view=week&ref=2026-10-13").get_json()["days"]
    e = [x for x in tage["2026-10-13"] if x["label"] == "Schlaf"][0]
    assert (e["layer"], e["motiv"], e["kategorie"], e["time"]) == ("rhythmus", "ruhe", "keine", "02:00")
    r = c.post("/api/calendar/kategorie", json={"kennung": _k("Kino"), "kategorie": "uni"})
    assert r.get_json()["kategorie"] == "uni"
    r = c.post("/api/calendar/kategorie/kurs", json={"schluessel": "Kino", "kategorie": "arbeit",
                                                     "probe": True})
    assert r.get_json()["geaendert"] == 1 and kk.eintrag(_k("Kino"))["kategorie"] == "uni"
    assert len(c.get("/api/calendar/phasen").get_json()["phasen"]) == 1
    assert c.delete("/api/calendar/phase", json={"kennung": k}).status_code == 200
    assert kk.phasen() == []
