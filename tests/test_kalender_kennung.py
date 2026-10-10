"""
Termine und Routinen per fester Kennung (core/kalender_kennung.py).

Anlass 08.10.2026: die KI änderte „die Geigenstunde" und traf beide
gleichnamigen Serien. Geprüft gegen BEIDE Speicher:
  * die Kennung überlebt Umbenennen, Uhrzeit, Ort (Wunsch 2 von ASSISTANT),
  * gleichnamige Routinen sind einzeln zu treffen,
  * eine Ablehnung schreibt NICHTS (Datei-Inhalt vorher == nachher, Wunsch 3),
  * feste Codes statt stiller Korrekturen.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_kennung as kk

pytestmark = pytest.mark.kalender_beide


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_routine("termine", "Geigenstunde", "FREQ=WEEKLY;BYDAY=TU",
                         time="17:45", ende="18:30", ort="Geigenschule")
    kalender.add_routine("termine", "Geigenstunde", "FREQ=WEEKLY;BYDAY=TU",
                         time="18:10", ende="19:10")
    kalender.add_entry("termine", "2026-10-14", "Kino", time="19:00", ende="21:00")
    kalender.add_span("termine", "2026-10-07", "2026-10-09", "Messe")
    return tmp_path


def _k(label, art, time=None):
    return next(e["kennung"] for e in kk.alle_eintraege()
                if e["label"] == label and e["art"] == art
                and (time is None or e.get("time") == time))


def _stand(tmp_path):
    """Alles, was der Kalender auf Platte hat (ohne Sperrdatei)."""
    aus = {}
    for p in sorted(tmp_path.rglob("*")):
        if p.is_file() and p.name != ".zentrale.lock":
            aus[str(p.relative_to(tmp_path))] = p.read_bytes()
    return aus


def _tag(iso):
    return kalender.entries_in_range(date.fromisoformat(iso), date.fromisoformat(iso)).get(iso, [])


# ── Lesen ──────────────────────────────────────────────────────────────
def test_alle_eintraege_mit_kennung_art_und_ohne_interna(cal):
    alle = kk.alle_eintraege()
    assert {e["art"] for e in alle} == {"routine", "einmal", "spanne"}
    assert all(e["kennung"] for e in alle)
    assert len({e["kennung"] for e in alle}) == len(alle)
    assert not any(k.startswith("_ics") or k == "uid" for e in alle for k in e)
    kino = next(e for e in alle if e["label"] == "Kino")
    assert kino["tag"] == "2026-10-14"
    messe = next(e for e in alle if e["label"] == "Messe")
    assert (messe["von"], messe["bis"]) == ("2026-10-07", "2026-10-09")


def test_ausgegebene_tage_tragen_die_kennung(cal):
    k = _k("Geigenstunde", "routine", "18:10")
    assert any(e.get("kennung") == k for e in _tag("2026-10-13"))
    km = _k("Messe", "spanne")
    assert all(e.get("kennung") == km for e in _tag("2026-10-08") if e["label"] == "Messe")


# ── Kennung überlebt Änderungen ────────────────────────────────────────
def test_kennung_ueberlebt_umbenennen_zeit_und_ort(cal):
    k = _k("Geigenstunde", "routine", "18:10")
    r = kk.routine_aendern(k, label="Violine", time="18:00", ende="19:00", ort="Schule")
    assert r["kennung"] == k and r["label"] == "Violine"
    kt = _k("Kino", "einmal")
    e = kk.eintrag_aendern(kt, label="Kino mit Lea", tag="2026-10-15", time="20:00", ende="22:00")
    assert e["kennung"] == kt and e["tag"] == "2026-10-15"
    assert kk.eintrag(kt)["label"] == "Kino mit Lea"


def test_gleichnamige_routinen_einzeln(cal):
    k = _k("Geigenstunde", "routine", "18:10")
    kk.routine_aendern(k, time="18:00", ende="19:00")
    zeiten = sorted((e["time"], e.get("ende")) for e in _tag("2026-10-13")
                    if e["label"] == "Geigenstunde")
    assert zeiten == [("17:45", "18:30"), ("18:00", "19:00")]
    kk.routine_loeschen(k)
    assert [e["time"] for e in _tag("2026-10-13") if e["label"] == "Geigenstunde"] == ["17:45"]


# ── Ablehnen schreibt nichts ───────────────────────────────────────────
@pytest.mark.parametrize("aufruf,code", [
    (lambda k: kk.routine_aendern(k["r"], ende="17:00"), "ENDE-VOR-BEGINN"),
    (lambda k: kk.routine_aendern(k["r"], rrule="FREQ=KAPUTT"), "RRULE-UNGUELTIG"),
    (lambda k: kk.routine_aendern(k["r"], time="25:00"), "ZEIT-UNGUELTIG"),
    (lambda k: kk.routine_aendern("gibtsnicht", time="10:00"), "KENNUNG-UNBEKANNT"),
    (lambda k: kk.routine_aendern(k["e"], time="10:00"), "FALSCHE-ART"),
    (lambda k: kk.routine_absagen(k["r"], "2026-10-14"), "KEIN-VORKOMMEN"),
    (lambda k: kk.routine_tag_aendern(k["r"], "2026-10-13", ende="17:00"), "ENDE-VOR-BEGINN"),
    (lambda k: kk.eintrag_aendern(k["e"], ende="18:00"), "ENDE-VOR-BEGINN"),
    (lambda k: kk.eintrag_aendern(k["e"], label="  "), "TITEL-LEER"),
    (lambda k: kk.eintrag_aendern(k["s"], bis="2026-10-01"), "SPANNE-VERDREHT"),
    (lambda k: kk.eintrag_aendern(k["s"], times={"2026-10-20": "10:00"}), "TAG-AUSSERHALB"),
    (lambda k: kk.eintrag_aendern(k["s"], time="10:00"), "UNBEKANNTES-FELD"),
])
def test_ablehnung_mit_code_und_nichts_geschrieben(cal, aufruf, code):
    k = {"r": _k("Geigenstunde", "routine", "18:10"), "e": _k("Kino", "einmal"),
         "s": _k("Messe", "spanne")}
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt) as fehler:
        aufruf(k)
    assert fehler.value.code == code and fehler.value.code in kk.CODES
    assert fehler.value.grund
    assert _stand(cal) == vorher, "bei einer Ablehnung darf nichts geschrieben sein"


# ── Routinen: Tag, Absage, Pause ───────────────────────────────────────
def test_absagen_und_wieder_an(cal):
    k = _k("Geigenstunde", "routine", "18:10")
    kk.routine_absagen(k, "2026-10-13")
    assert any(e.get("deaktiviert") for e in _tag("2026-10-13") if e.get("kennung") == k)
    kk.routine_absagen(k, "2026-10-13", an=True)
    assert not any(e.get("deaktiviert") for e in _tag("2026-10-13") if e.get("kennung") == k)


def test_nur_dieser_tag(cal):
    k = _k("Geigenstunde", "routine", "18:10")
    kk.routine_tag_aendern(k, "2026-10-13", time="19:00", ende="20:00")
    assert [(e["time"], e["ende"]) for e in _tag("2026-10-13") if e.get("kennung") == k] \
        == [("19:00", "20:00")]
    assert [e["time"] for e in _tag("2026-10-20") if e.get("kennung") == k] == ["18:10"]


def test_pause_haengt_an_der_kennung_und_ueberlebt_umbenennen(cal):
    k = _k("Geigenstunde", "routine", "18:10")
    kk.routine_pause(k, "2026-10-12", "2026-10-18", "Herbstferien")
    kk.routine_aendern(k, label="Violine")
    an = [e for e in _tag("2026-10-13") if e.get("kennung") == k]
    assert an and an[0].get("ausfall") == "Herbstferien"
    andere = [e for e in _tag("2026-10-13") if e["label"] == "Geigenstunde"]
    assert andere and not andere[0].get("ausfall"), "die gleichnamige andere bleibt"


def test_alte_titel_pause_wandert_beim_umbenennen_mit(cal):
    kalender.add_pause("Kurs", "2026-10-12", "2026-10-18", "Ferien")
    kalender.add_routine("termine", "Kurs", "FREQ=WEEKLY;BYDAY=WE", time="10:00")
    k = _k("Kurs", "routine")
    kk.routine_aendern(k, label="Kurs neu")
    assert [e.get("ausfall") for e in _tag("2026-10-14") if e.get("kennung") == k] == ["Ferien"]


# ── Spannen ────────────────────────────────────────────────────────────
def test_spanne_zeiten_je_tag_und_verschieben(cal):
    k = _k("Messe", "spanne")
    kk.eintrag_aendern(k, times={"2026-10-08": "09:00"}, enden={"2026-10-08": "17:00"})
    assert [(e["time"], e.get("ende")) for e in _tag("2026-10-08") if e.get("kennung") == k] \
        == [("09:00", "17:00")]
    kk.eintrag_aendern(k, von="2026-10-14")                   # eine Woche später, Zeiten mit
    assert [(e["time"], e.get("ende")) for e in _tag("2026-10-15") if e.get("kennung") == k] \
        == [("09:00", "17:00")]
    assert kk.eintrag(k)["bis"] == "2026-10-16"
    kk.eintrag_loeschen(k)
    with pytest.raises(kk.KalenderAbgelehnt):
        kk.eintrag(k)


# ── Alarme mit Datum ───────────────────────────────────────────────────
def test_alarme_haben_einen_tag(cal, monkeypatch):
    import kalender_konflikte
    heute = date.today()
    tag = heute.isoformat()
    kalender.add_entry("termine", tag, "A", time="10:00", ende="11:00")
    kalender.add_entry("termine", tag, "B", time="10:30", ende="11:30")
    alarme = kalender.open_alarms(3)
    assert any(a.get("tag") == tag for a in alarme), alarme


# ── Ebene wechseln: committed ↔ uncommitted (10.10.2026) ───────────────
def test_ebene_wechseln_hin_und_zurueck(cal):
    k = _k("Geigenstunde", "routine", "18:10")
    kk.routine_pause(k, "2026-10-12", "2026-10-18", "Ferien")
    kk.routine_tag_aendern(k, "2026-10-20", time="19:00")
    e = kk.ebene_wechseln(k)
    assert e["kennung"] == k and e["layer"] == "uncommitted"
    tag = [x for x in _tag("2026-10-13") if x.get("kennung") == k]
    assert tag and tag[0]["layer"] == "uncommitted" and tag[0].get("ausfall") == "Ferien"
    assert [x["time"] for x in _tag("2026-10-20") if x.get("kennung") == k] == ["19:00"]
    assert kk.ebene_wechseln(k)["layer"] == "termine"
    for kn, art in (("Kino", "einmal"), ("Messe", "spanne")):
        kx = _k(kn, art)
        assert kk.ebene_wechseln(kx, "uncommitted")["layer"] == "uncommitted"
        assert kk.ebene_wechseln(kx, "uncommitted")["layer"] == "uncommitted"   # schon da
        assert kk.ebene_wechseln(kx)["layer"] == "termine"
    assert len(kk.alle_eintraege()) == 4


def test_ebene_unbekannt_schreibt_nichts(cal):
    k = _k("Kino", "einmal")
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt) as f:
        kk.ebene_wechseln(k, "erlebt")
    assert f.value.code == "EBENE-UNBEKANNT" and _stand(cal) == vorher


def test_uncommitted_eigener_ordner_im_ics(cal):
    if kalender._speicher().art != "ics":
        pytest.skip("nur .ics hat Ordner")
    k = _k("Kino", "einmal")
    kk.ebene_wechseln(k)
    ordner = {p.parent.name for p in kalender._speicher().vdir.rglob("*.ics")
              if k in p.read_text(encoding="utf-8")}
    assert ordner == {"uncommitted"}


def test_kalender_beide_wirklich(_kalender_speicher_art):
    """Die Marke kalender_beide schaltet den Speicher wirklich um."""
    assert kalender._speicher().art == _kalender_speicher_art


def test_uncommitted_nur_hinweis(cal, monkeypatch):
    """Kein Alarm, keine Rückfrage, keine Abwesenheit — KI liest „vielleicht"."""
    import kalender_konflikte as kf
    tag = date.today().isoformat()
    kalender.add_entry("termine", tag, "Fest", time="10:00", ende="11:00")
    kalender.add_entry("termine", tag, "Vielleicht", time="10:30", ende="11:30")
    kk.ebene_wechseln(_k("Vielleicht", "einmal"))
    assert not [a for a in kalender.open_alarms(2) if a.get("tag") == tag]
    assert kf.conflicts_for_proposed("termine", tag, "Neu", "10:45", "11:15")   # gegen „Fest"
    assert kf.conflicts_for_proposed("uncommitted", tag, "Neu", "10:45", "11:15") == []
    text = kf.render_range_for_tool(date.today(), date.today())
    assert "[uncommitted · vielleicht]" in text and "Vielleicht" in text
