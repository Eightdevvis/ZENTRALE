"""Die erzeugten Kalender-Werkzeuge: Phasen, Gruppe, Ebene (2026-10-10).

Die bisherigen Kalender-Fälle laufen in tests/test_ki_kalender.py mit beiden
Wegen (erzeugt / von Hand). Hier, was nur der erzeugte kann:
  - Phasen des Tagesrhythmus anlegen, ändern (ab jetzt, einzelne Tage, ein
    Zeitraum), löschen — über Mitternacht erlaubt;
  - die Gruppe eines Eintrags setzen (Pflicht beim Anlegen);
  - fest ↔ vielleicht;
  - read_calendar zeigt Motiv, Gruppe und „bis Folgetag";
  - ganz oder gar nicht, Codes, Fragen.
"""
import copy
import re
from datetime import date, timedelta

import pytest

import kalender
import kalender_kennung
import ki_kalender
import ki_werkzeuge  # noqa: F401  — meldet die Ausführer an
import werkzeug_befund
import werkzeug_register

pytestmark = pytest.mark.kalender_beide

HEUTE = date.today()
MO = HEUTE + timedelta(days=(0 - HEUTE.weekday()) % 7 + 7)


@pytest.fixture(autouse=True)
def gross():
    werkzeug_register.erzeugte_einsetzen(True)
    marke = werkzeug_befund.schiene_setzen("gross")
    yield
    werkzeug_befund.schiene_zuruecksetzen(marke)


def tun(name, **args):
    return ki_werkzeuge._verteilen(name, args)


def kennung(text, art="r"):
    return re.findall(r"#(%s[0-9a-f]+)" % art, text)[0]


def _tag(d: date) -> list:
    return kalender.entries_in_range(d, d).get(d.isoformat()) or []


def _stand():
    return copy.deepcopy(kalender._load_raw())


def _schlaf():
    r = tun("set_calendar_phase", label="Schlaf", motiv="schlaf", time="23:00", ende="07:00")
    assert r.status == "ok", r
    return kennung(r)


# ── Phasen ─────────────────────────────────────────────────────────────

def test_phase_ueber_mitternacht_anlegen_und_lesen():
    r = tun("set_calendar_phase", label="Schlaf", motiv="Schlaf", time="23:00", ende="07:00")
    assert r.status == "ok", r
    assert r.startswith("Phase „Schlaf“ (schlaf) täglich 23:00–07:00 (bis Folgetag)")
    assert "EINGETRAGEN (#r" in r
    e = [x for x in _tag(HEUTE) if x["label"] == "Schlaf"][0]
    assert e["layer"] == "rhythmus" and e.get("ueber_nacht")
    text = tun("read_calendar", start_date=HEUTE.isoformat(), end_date=HEUTE.isoformat())
    assert "23:00–07:00 (bis Folgetag) Schlaf [rhythmus · schlaf] ↻" in text


def test_phase_ist_kein_termin_beim_zaehlen():
    _schlaf()
    r = tun("add_calendar_entry", day=HEUTE.isoformat(), label="Arzt", time="10:00",
            kategorie="keine")
    assert "Der Tag hat 1 Eintrag." in r


@pytest.mark.parametrize("args, code", [
    ({"label": "Schlaf", "motiv": "traum", "time": "23:00"}, "K-MOTIV-UNBEKANNT"),
    ({"label": "Schlaf", "motiv": "schlaf"}, "K-PHASE-OHNE-ZEIT"),
    ({"label": "", "motiv": "schlaf", "time": "23:00"}, "K-TITEL-LEER"),
    ({"label": "Schlaf", "motiv": "schlaf", "time": "23:00", "ende": "23:00"},
     "K-ENDE-VOR-BEGINN"),
    ({"label": "Schlaf", "motiv": "schlaf", "time": "23:00", "rrule": "FREQ=DAILY;COUNT=3"},
     "K-RRULE-MIT-ENDE"),
    ({"label": "Schlaf", "motiv": "schlaf", "time": "23:00", "farbe": "blau"},
     "K-UNBEKANNTES-FELD"),
])
def test_phase_abbruch_schreibt_nichts(args, code):
    vorher = _stand()
    r = tun("set_calendar_phase", **args)
    assert r.status == "fehlgeschlagen" and r.code == code, r
    assert "ABGEBROCHEN – nichts eingetragen" in r
    assert _stand() == vorher


def test_schlaf_die_naechsten_drei_tage_ab_zwei():
    """Prüfstand f12: „die nächsten 3 Tage geh ich erst um 2 ins Bett" —
    nur diese Tage, die Phase sonst wie gehabt."""
    k = _schlaf()
    von, bis = HEUTE + timedelta(days=1), HEUTE + timedelta(days=3)
    r = tun("edit_calendar_phase", kennung=k, time="02:00", nur_von=von.isoformat(),
            nur_bis=bis.isoformat())
    assert r.status == "ok", r
    assert "NUR vom" in r and "die übrigen Tage der Serie bleiben" in r
    for d in (von, von + timedelta(days=1), bis):
        assert [x["time"] for x in _tag(d) if x["label"] == "Schlaf"] == ["02:00"]
    for d in (HEUTE, bis + timedelta(days=1)):
        assert [x["time"] for x in _tag(d) if x["label"] == "Schlaf"] == ["23:00"]


def test_phase_ab_jetzt_und_einzelner_tag_und_loeschen():
    k = _schlaf()
    r = tun("edit_calendar_phase", kennung=k, time="22:30", ende="06:30")
    assert r.status == "ok" and "22:30–06:30 (bis Folgetag)" in r, r
    morgen = HEUTE + timedelta(days=1)
    r = tun("edit_calendar_phase", kennung=k, nur_am=morgen.isoformat(), ende="09:00")
    assert r.status == "ok" and "NUR am" in r, r
    assert [x["ende"] for x in _tag(morgen) if x["label"] == "Schlaf"] == ["09:00"]
    r = tun("delete_calendar_phase", kennung=k)
    assert r.status == "ok" and "GELÖSCHT" in r
    assert not [x for x in _tag(HEUTE) if x["label"] == "Schlaf"]


def test_phase_werkzeug_trifft_keine_routine():
    r = tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:00",
            von=HEUTE.isoformat(), bis=(HEUTE + timedelta(days=60)).isoformat(),
            kategorie="keine")
    vorher = _stand()
    for name, args in (("edit_calendar_phase", {"time": "19:00"}),
                       ("delete_calendar_phase", {})):
        r2 = tun(name, kennung=kennung(r), **args)
        assert r2.code == "K-KEINE-PHASE", r2
    assert _stand() == vorher


def test_phase_zeitraum_zu_lang():
    k = _schlaf()
    vorher = _stand()
    r = tun("edit_calendar_phase", kennung=k, time="01:00", nur_von=HEUTE.isoformat(),
            nur_bis=(HEUTE + timedelta(days=400)).isoformat())
    assert r.code == "K-ZEITRAUM-ZU-LANG", r
    assert _stand() == vorher


def test_routine_ueber_einen_zeitraum_aendern():
    r = tun("add_calendar_routine", label="Training", rrule="FREQ=DAILY", time="18:00",
            ende="19:00", von=HEUTE.isoformat(), bis=(HEUTE + timedelta(days=30)).isoformat(),
            kategorie="keine")
    k = kennung(r)
    von, bis = HEUTE + timedelta(days=2), HEUTE + timedelta(days=4)
    r = tun("edit_calendar_routine", kennung=k, aktion="aendern", time="19:00", ende="20:00",
            nur_von=von.isoformat(), nur_bis=bis.isoformat())
    assert r.status == "ok", r
    assert [x["time"] for x in _tag(von + timedelta(days=1))] == ["19:00"]
    assert [x["time"] for x in _tag(bis + timedelta(days=1))] == ["18:00"]
    for args, code in (({"nur_von": von.isoformat()}, "K-PFLICHTFELD"),
                       ({"nur_am": von.isoformat(), "nur_von": von.isoformat(),
                         "nur_bis": bis.isoformat()}, "K-UNBEKANNTES-FELD")):
        r = tun("edit_calendar_routine", kennung=k, aktion="aendern", time="07:00", **args)
        assert r.code == code, r


def test_tage_anders_nachgelesen_werden_zurueckgenommen(monkeypatch):
    k = _schlaf()
    vorher = _stand()
    echt = kalender_kennung.eintrag

    def falsch(x):
        e = echt(x)
        for a in (e.get("abweichungen") or {}).values():
            a["time"] = "05:55"
        return e
    monkeypatch.setattr(kalender_kennung, "eintrag", falsch)
    r = tun("edit_calendar_phase", kennung=k, time="02:00",
            nur_von=(HEUTE + timedelta(days=1)).isoformat(),
            nur_bis=(HEUTE + timedelta(days=2)).isoformat())
    assert r.code == "W-NICHT-GESPEICHERT" and "wiederhergestellt" in r, r
    assert _stand() == vorher


# ── Gruppe ─────────────────────────────────────────────────────────────

def test_gruppe_ist_beim_anlegen_pflicht():
    vorher = _stand()
    r = tun("add_calendar_entry", day=HEUTE.isoformat(), label="Arzt")
    assert r.code == "K-PFLICHTFELD" and "kategorie" in r, r
    r = tun("add_calendar_entry", day=HEUTE.isoformat(), label="Arzt", kategorie="sport")
    assert r.code == "K-KATEGORIE-UNBEKANNT", r
    r = tun("add_calendar_entry", day=HEUTE.isoformat(), label="Arzt", kategorie="custom")
    assert r.code == "K-KATEGORIE-NAME-FEHLT", r
    assert _stand() == vorher


def test_analysis_gehoert_zur_uni():
    """Prüfstand f13: „Analysis I gehört zur Uni-Gruppe"."""
    r = tun("add_calendar_routine", label="Analysis I", rrule="FREQ=WEEKLY;BYDAY=MO",
            time="10:00", ende="12:00", von=MO.isoformat(),
            bis=(MO + timedelta(days=28)).isoformat(), kategorie="keine")
    k = kennung(r)
    r = tun("set_calendar_group", kennung=k, kategorie="uni")
    assert r.status == "ok" and "Gruppe jetzt Uni" in r and f"(#{k})" in r, r
    assert kalender_kennung.eintrag(ki_kalender.finden(k)[0].uid)["kategorie"] == "uni"
    text = tun("read_calendar", start_date=MO.isoformat(), end_date=MO.isoformat())
    assert "[termine · Uni]" in text
    r = tun("set_calendar_group", kennung=k, kategorie="custom", kategorie_name="Mathe")
    assert r.status == "ok" and "Gruppe jetzt Mathe" in r
    r = tun("set_calendar_group", kennung=k, kategorie="keine")
    assert r.status == "ok" and "Gruppe jetzt keine" in r


def test_gruppe_beim_anlegen_steht_im_beleg():
    r = tun("add_calendar_entry", day=MO.isoformat(), label="Schicht", time="08:00",
            ende="16:00", kategorie="arbeit")
    assert r.status == "ok", r
    uid = ki_kalender.finden(kennung(r, "t"))[0].uid
    assert kalender_kennung.eintrag(uid)["kategorie"] == "arbeit"


def test_gruppe_unbekannte_kennung():
    r = tun("set_calendar_group", kennung="#r0000", kategorie="uni")
    assert r.code == "K-KENNUNG-UNBEKANNT", r


# ── Ebene: fest ↔ vielleicht ───────────────────────────────────────────

def test_vielleicht_und_wieder_fest():
    r = tun("add_calendar_entry", day=MO.isoformat(), label="Kino", time="20:00",
            kategorie="keine")
    k = kennung(r, "t")
    r = tun("set_calendar_layer", kennung=k, ebene="uncommitted")
    assert r.status == "ok" and "jetzt vielleicht" in r, r
    assert [e["layer"] for e in _tag(MO)] == ["uncommitted"]
    text = tun("read_calendar", start_date=MO.isoformat(), end_date=MO.isoformat())
    assert "[uncommitted · vielleicht]" in text
    r = tun("set_calendar_layer", kennung=k, ebene="termine")
    assert r.status == "ok" and "jetzt fest" in r
    assert [e["layer"] for e in _tag(MO)] == ["termine"]


def test_phase_kann_nicht_vielleicht_werden():
    k = _schlaf()
    vorher = _stand()
    r = tun("set_calendar_layer", kennung=k, ebene="uncommitted")
    assert r.code == "K-IST-PHASE", r
    r = tun("set_calendar_layer", kennung=k, ebene="irgendwo")
    assert r.code == "K-EBENE-UNBEKANNT", r
    assert _stand() == vorher


# ── Fragen an Sasha, Register ──────────────────────────────────────────

def test_fragen_nennen_was_passiert():
    import erlaubnis
    k = _schlaf()
    f = erlaubnis.frage("edit_calendar_phase", {"kennung": k, "time": "02:00",
                                                "nur_von": "2026-10-11", "nur_bis": "2026-10-13"})
    assert f.startswith('Soll ich die Phase "Schlaf"') and "Beginn 02:00" in f
    assert "nur vom 2026-10-11" in f and k not in f
    f = erlaubnis.frage("set_calendar_phase", {"label": "Essen", "motiv": "essen", "time": "12:00"})
    assert f == "Soll ich die Phase eintragen: Titel Essen, Art essen, Beginn 12:00?"
    f = erlaubnis.frage("add_calendar_entry", {"label": "Uni-Tag", "day": "2026-10-12",
                                               "kategorie": "uni"})
    assert "(Gruppe Uni)?" in f
    for name in ("set_calendar_phase", "edit_calendar_phase", "delete_calendar_phase",
                 "set_calendar_group", "set_calendar_layer"):
        assert erlaubnis.braucht_erlaubnis(name, {"kennung": "x"})


def test_aus_heisst_die_alten_werkzeuge():
    try:
        werkzeug_register.erzeugte_einsetzen(False)
        namen = {t["function"]["name"] for t in werkzeug_register.schema("gross")}
        assert "set_calendar_phase" not in namen and "add_calendar_entry" in namen
        add = werkzeug_register.eintrag("add_calendar_entry")
        assert add.erzeugt is None and "kategorie" not in add.parameter_auf("gross")["properties"]
    finally:
        werkzeug_register.erzeugte_einsetzen(True)
    add = werkzeug_register.eintrag("add_calendar_entry")
    assert add.erzeugt == "kalender" and "kategorie" in add.parameter_auf("gross")["required"]
    namen = [t["function"]["name"] for t in werkzeug_register.schema("gross")]
    assert namen[-5:] == ["set_calendar_phase", "edit_calendar_phase", "delete_calendar_phase",
                          "set_calendar_group", "set_calendar_layer"]


def test_klein_bekommt_nichts_neues():
    namen = {t["function"]["name"] for t in werkzeug_register.schema("klein")}
    assert not namen & {"set_calendar_phase", "set_calendar_group", "set_calendar_layer"}
    add = [t for t in werkzeug_register.schema("klein")
           if t["function"]["name"] == "add_calendar_entry"][0]
    assert "kategorie" not in add["function"]["parameters"]["properties"]


def test_jedes_neue_werkzeug_belegt_echt():
    k = _schlaf()
    r = tun("add_calendar_entry", day=MO.isoformat(), label="Kino", kategorie="keine")
    t = kennung(r, "t")
    for name, args in (("edit_calendar_phase", {"kennung": k, "ende": "06:00"}),
                       ("set_calendar_group", {"kennung": t, "kategorie": "arbeit"}),
                       ("set_calendar_layer", {"kennung": t, "ebene": "uncommitted"}),
                       ("delete_calendar_phase", {"kennung": k})):
        r = tun(name, **args)
        assert isinstance(r, werkzeug_befund.Befund) and r.status == "ok" and r.beleg, (name, r)


def test_qwen_zuschnitt():
    from profil.modelle import qwen
    tools = {t["function"]["name"]: t for t in qwen.werkzeuge(werkzeug_register.schema("gross"))}
    add = tools["add_calendar_entry"]["function"]
    assert "layer" not in add["parameters"]["properties"]
    assert "kategorie" in add["parameters"]["required"]
    assert tools["set_calendar_phase"]["function"]["description"].startswith(
        "Trägt eine Phase des Tagesrhythmus ein (z.B. Schlaf")
