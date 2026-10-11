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
    assert namen[-9:] == ["set_calendar_phase", "edit_calendar_phase", "delete_calendar_phase",
                          "set_calendar_group", "set_calendar_layer", "set_calendar_style",
                          "read_calendar_sources",
                          "set_calendar_source", "clear_calendar_source"]


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


# ── Titel aus Liste/Projekt (Kern kalender_quelle, 2026-10-10) ─────────

@pytest.fixture
def todo():
    import lists
    liste = lists.create_list("todo")
    lists.add_item(liste["id"], "Steuern planen")
    lists.add_item(liste["id"], "Bad putzen")
    return liste["id"]


def test_quellen_lesen_zeigt_ids(todo):
    text = tun("read_calendar_sources")
    assert f"quelle_art=liste quelle_id={todo}: todo — oben: Steuern planen" in text


def test_block_fuer_die_todo_liste(todo):
    """Prüfstand f14: „blocke mir morgen 2 Stunden für meine todo liste"."""
    morgen = (HEUTE + timedelta(days=1)).isoformat()
    r = tun("add_calendar_entry", day=morgen, time="10:00", ende="12:00", kategorie="keine",
            quelle_art="liste", quelle_id=todo)
    assert r.status == "ok", r
    assert "„todo“" in r and "EINGETRAGEN (#t" in r
    assert "(aus Liste: todo, jetzt: „Steuern planen“)" in r
    text = tun("read_calendar", start_date=morgen, end_date=morgen)
    assert "Steuern planen (aus Liste: todo)" in text


@pytest.mark.parametrize("args, code", [
    ({"quelle_art": "liste", "quelle_id": "gibtsnicht"}, "K-QUELLE-UNBEKANNT"),
    ({"quelle_art": "liste"}, "K-QUELLE-UNGUELTIG"),
    ({"quelle_art": "ordner", "quelle_id": "x"}, "K-QUELLE-ART-UNBEKANNT"),
])
def test_quelle_abbruch_schreibt_nichts(todo, args, code):
    vorher = _stand()
    r = tun("add_calendar_entry", day=MO.isoformat(), kategorie="keine", **args)
    assert r.code == code, r
    assert _stand() == vorher


def test_quelle_setzen_und_loesen(todo):
    r = tun("add_calendar_entry", day=MO.isoformat(), label="Lernen", time="10:00",
            kategorie="keine")
    k = kennung(r, "t")
    r = tun("set_calendar_source", kennung=k, quelle_art="liste", quelle_id=todo)
    assert r.status == "ok" and "jetzt: „Steuern planen“" in r, r
    r = tun("clear_calendar_source", kennung=k, titel_uebernehmen=True)
    assert r.status == "ok" and "ohne Quelle" in r, r
    assert [e["label"] for e in _tag(MO)] == ["Steuern planen"]
    r = tun("clear_calendar_source", kennung=k)
    assert r.code == "K-OHNE-QUELLE", r
    p = _schlaf()
    r = tun("set_calendar_source", kennung=p, quelle_art="liste", quelle_id=todo)
    assert r.code == "K-IST-PHASE", r


# ── Aussehen (set_calendar_style, 2026-10-11) ──────────────────────────

def _termin():
    r = tun("add_calendar_entry", day=MO.isoformat(), label="Zahnarzt", time="09:00",
            ende="10:00", kategorie="keine")
    assert r.status == "ok", r
    return "#" + kennung(r, "t")


def test_stil_setzen_nur_genannte_felder_und_beleg():
    k = _termin()
    r = tun("set_calendar_style", kennung=k, rahmen="double", rahmenfarbe="#ff8800")
    assert r.status == "ok" and "GEÄNDERT" in r and "border-style: double" in r, r
    r = tun("set_calendar_style", kennung=k, hintergrund="#112233")
    # Beleg aus dem nachgelesenen Eintrag: der alte Rahmen bleibt, die Farbe kommt dazu.
    assert r.status == "ok" and "border-style: double" in r and "#112233" in r, r


def test_stil_entfernen_und_ohne_felder():
    k = _termin()
    assert tun("set_calendar_style", kennung=k, muster="punkte").status == "ok"
    r = tun("set_calendar_style", kennung=k, entfernen="ja")
    assert r.status == "ok" and "Standard-Aussehen" in r, r
    vorher = _stand()
    r = tun("set_calendar_style", kennung=k)
    assert r.code == "K-STIL-UNGUELTIG", r
    assert _stand() == vorher


def test_stil_kennt_kein_none():
    """11.10.2026, Sasha: nur „nicht gesetzt" — kein none im Werkzeug; ein
    none wird abgelehnt und schreibt nichts."""
    import werkzeug_kalender
    w = next(a for a in werkzeug_kalender.AKTIONEN if a["name"] == "set_calendar_style")
    for feld in ("rahmen", "muster"):
        f = w["inputSchema"]["properties"][feld]
        assert "none" not in f["enum"] and "none" not in f["description"]
    k = _termin()
    vorher = _stand()
    r = tun("set_calendar_style", kennung=k, rahmen="none")
    assert r.status != "ok", r
    assert _stand() == vorher


def test_stil_ungueltig_schreibt_nichts():
    k = _termin()
    vorher = _stand()
    r = tun("set_calendar_style", kennung=k, rahmen="wellig")
    assert r.status != "ok" and r.code.startswith("K-"), r
    r = tun("set_calendar_style", kennung=k, rahmenfarbe="orange")
    assert r.status != "ok" and r.code.startswith("K-"), r
    assert _stand() == vorher


def test_stil_nicht_fuer_phasen():
    k = "#" + _schlaf()
    r = tun("set_calendar_style", kennung=k, rahmen="dashed")
    assert r.code == "K-IST-PHASE", r


def test_stil_einzelne_eigenschaft_zuruecksetzen():
    """2026-10-11: „nicht gesetzt" statt none — zuruecksetzen nimmt die
    Eigenschaft aus dem Stil, der Rest bleibt."""
    k = _termin()
    assert tun("set_calendar_style", kennung=k, rahmen="double", muster="punkte").status == "ok"
    r = tun("set_calendar_style", kennung=k, zuruecksetzen=["muster"])
    assert r.status == "ok" and "border-style: double" in r and "muster" not in r, r
    vorher = _stand()
    r = tun("set_calendar_style", kennung=k, zuruecksetzen=["muster"])   # schon weg
    assert r.code == "K-STIL-UNGUELTIG", r
    assert _stand() == vorher
