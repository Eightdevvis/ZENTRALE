"""Kalender-Werkzeuge ohne Fallen (core/ki_kalender.py, ki_kalender_aendern.py).

2026-10-08, nach Sashas Kalender-Testlauf. Jeder Test hier ist eine Falle
aus dem Gespräch 20261008-132404:

  - edit_calendar_routine per Name änderte ALLE Treffer („2 Routine(n)");
  - Reparatur durch Löschen + Neu verlor Ende und Ort;
  - add_calendar_routine hatte kein Ortsfeld (Ort landete im Titel) und nahm
    ohne Ende still etwas an;
  - es gab kein Werkzeug, einen einzelnen Termin zu ändern;
  - die Pause „Geigenstunde" traf die Routine „Geigenstunde @ Geigenschule"
    nicht — und das Ergebnis sagte „OK";
  - die Warnungen ließen sich nur raten.

Die Tests laufen gegen beide Kalender-Speicher (json und ics).
"""
import re
from datetime import date, timedelta

import pytest

import kalender
import ki_kalender
import ki_werkzeuge  # noqa: F401  — meldet die Ausführer an
import werkzeug_befund

pytestmark = pytest.mark.kalender_beide

DO = date.today() + timedelta(days=(3 - date.today().weekday()) % 7 + 7)   # Donnerstag in 1–2 Wochen
DO_ISO = DO.isoformat()


@pytest.fixture
def gross():
    marke = werkzeug_befund.schiene_setzen("gross")
    yield
    werkzeug_befund.schiene_zuruecksetzen(marke)


# Seit 2026-10-09 verlangt add_calendar_routine auf gross einen Zeitraum.
# Die älteren Tests hier prüfen anderes — sie bekommen einen weiten Standard.
# Wer den Zeitraum selbst prüft, ruft roh() auf.
VON_STD = (date.today() - timedelta(days=60)).isoformat()
BIS_STD = (date.today() + timedelta(days=365)).isoformat()


def roh(name, **args):
    return ki_werkzeuge._verteilen(name, args)


def tun(name, **args):
    if name == "add_calendar_routine" and werkzeug_befund.schiene() == "gross":
        args.setdefault("von", VON_STD)
        args.setdefault("bis", BIS_STD)
    return roh(name, **args)


def kennungen(text, art="r"):
    return list(dict.fromkeys(re.findall(r"#(%s[0-9a-f]+)" % art, text)))


def routinen():
    return [s for s in ki_kalender.stuecke() if s.art == "routine"]


# ── Lesen ──────────────────────────────────────────────────────────────

def test_lesen_zeigt_kennung_und_alle_felder(gross):
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:10", ende="19:10", ort="Geigenschule")
    tun("add_calendar_pause", label="Geigenstunde", von=DO_ISO, bis=DO_ISO, grund="Ferien")
    text = tun("read_calendar", zeitraum="naechste_30_tage", suche="Geige")
    k = kennungen(text)
    assert len(k) == 1
    assert "18:10–19:10 Geigenstunde @ Geigenschule [termine] ↻" in text
    assert "fällt aus (Ferien)" in text
    assert "Serien darin:" in text and "wöchentlich do" in text
    assert "FREQ=WEEKLY;BYDAY=TH" in text and "Pause" in text


def test_klein_liest_wie_gemessen():
    """Ohne gross keine Kennungen: das qwen bekommt die alte Ausgabe."""
    tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:10")
    text = tun("read_calendar", zeitraum="naechste_30_tage")
    assert "#" not in text
    assert text == kalender.render_range_for_tool(*kalender.resolve_range("naechste_30_tage"))


def test_kennung_ist_kurz_stabil_und_unterscheidet_doppel(gross):
    for _ in range(2):
        tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:00")
    a = [s.kennung for s in routinen()]
    b = [s.kennung for s in routinen()]
    assert a == b and len(set(a)) == 2
    assert all(re.fullmatch(r"r[0-9a-f]{4,}", k) for k in a)


def test_ohne_ende_wird_nichts_angenommen(gross):
    r = tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:10")
    assert "18:10 (ohne Ende)" in r and "frag nach" in r
    assert routinen()[0].ende is None


def test_ort_und_ende_landen_in_ihren_feldern(gross):
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:10", ende="19:00", ort="Geigenschule")
    s = routinen()[0]
    assert (s.label, s.time, s.ende, s.ort) == ("Geigenstunde", "18:10", "19:00", "Geigenschule")


# ── Ändern: eine Routine, nur genannte Felder ──────────────────────────

def test_name_mit_zwei_treffern_aendert_nichts(gross):
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH", time="17:45")
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:00")
    vorher = [dict(s.roh) for s in routinen()]
    r = tun("edit_calendar_routine", label="Geigenstunde", aktion="aendern", time="18:10")
    assert r.status == "fehlgeschlagen"
    assert "Nichts geändert" in r and "trifft 2" in r and "Frag Sasha" in r
    assert len(kennungen(r)) == 2
    assert [dict(s.roh) for s in routinen()] == vorher


def test_aendern_per_kennung_laesst_den_rest_stehen(gross):
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:10", ende="19:00", ort="Geigenschule")
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TU", time="17:00")
    ziel = [s for s in routinen() if s.time == "18:10"][0]
    r = tun("edit_calendar_routine", kennung="#" + ziel.kennung, aktion="aendern", ende="19:10")
    assert r.status == "ok"
    assert "18:10–19:10 @ Geigenschule" in r.beleg
    s = [s for s in routinen() if "BYDAY=TH" in s.rrule][0]
    assert (s.time, s.ende, s.ort) == ("18:10", "19:10", "Geigenschule")
    assert [s for s in routinen() if "BYDAY=TU" in s.rrule][0].time == "17:00"


def test_kennung_ueberlebt_aenderung_geloeschte_trifft_nichts(gross):
    """Seit 2026-10-09 aus der festen Kennung des Kerns: nach einer Änderung
    dieselbe; nach dem Löschen trifft sie nichts mehr (K-KENNUNG-UNBEKANNT)."""
    tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:00")
    alt = routinen()[0].kennung
    r = tun("edit_calendar_routine", kennung=alt, aktion="aendern", time="18:10")
    assert r.status == "ok" and f"(#{alt})" in r and routinen()[0].kennung == alt
    assert tun("edit_calendar_routine", kennung=alt, aktion="loeschen").status == "ok"
    r = tun("edit_calendar_routine", kennung=alt, aktion="aendern", time="19:00")
    assert r.status == "fehlgeschlagen" and r.code == "K-KENNUNG-UNBEKANNT"
    assert "gibt es nicht (mehr)" in r and routinen() == []


def test_ende_vor_beginn_wird_abgelehnt(gross):
    tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:00", ende="19:00")
    r = tun("edit_calendar_routine", label="Geige", aktion="aendern", time="19:30")
    assert r.status == "fehlgeschlagen" and "nicht nach Beginn" in r
    assert routinen()[0].ende == "19:00"


def test_nur_am_aendert_ein_datum(gross):
    tun("add_calendar_routine", label="Fahrschule", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="19:00", ende="20:00")
    r = tun("edit_calendar_routine", label="Fahrschule", aktion="aendern",
            nur_am=DO_ISO, time="19:30", ende="20:30")
    assert r.status == "ok" and "19:30–20:30 Fahrschule" in r
    tag = kalender.entries_in_range(DO, DO)[DO_ISO][0]
    naechste = (DO + timedelta(days=7)).isoformat()
    andere = kalender.entries_in_range(DO + timedelta(days=7), DO + timedelta(days=7))[naechste][0]
    assert (tag["time"], andere["time"]) == ("19:30", "19:00")


def test_nur_am_loeschen_sagt_nur_den_tag_ab(gross):
    tun("add_calendar_routine", label="Fahrschule", rrule="FREQ=WEEKLY;BYDAY=TH", time="19:00")
    r = tun("edit_calendar_routine", label="Fahrschule", aktion="loeschen", nur_am=DO_ISO)
    assert r.status == "ok" and "die Serie bleibt" in r
    assert len(routinen()) == 1
    assert kalender.entries_in_range(DO, DO)[DO_ISO][0].get("deaktiviert")


def test_loeschen_trifft_nicht_den_aehnlichen_namen(gross):
    """routine_loeschen im Kern sucht per Teilstring: 'Geige' nähme
    'Geigenstunde' mit. Hier wird vorher nachgerechnet."""
    tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=MO", time="10:00")
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:00")
    ziel = [s for s in routinen() if s.label == "Geige"][0]
    r = tun("edit_calendar_routine", kennung=ziel.kennung, aktion="loeschen")
    assert r.status == "ok"
    assert [s.label for s in routinen()] == ["Geigenstunde"]


# ── Pausen ─────────────────────────────────────────────────────────────

def test_pause_ohne_passende_routine_ist_kein_erfolg(gross):
    tun("add_calendar_routine", label="Geigenstunde @ Geigenschule",
        rrule="FREQ=WEEKLY;BYDAY=TH", time="18:10")
    vorher = kalender._load_raw()
    r = tun("add_calendar_pause", label="Geigenstunde", von=DO_ISO, bis=DO_ISO)
    # Seit 2026-10-09 kein „teilweise": abgebrochen, NICHTS gespeichert.
    assert r.status == "fehlgeschlagen" and r.code == "K-PAUSE-KEINE-ROUTINE"
    assert "ABGEBROCHEN – nichts eingetragen" in r and "Geigenstunde @ Geigenschule" in r
    assert kalender._load_raw() == vorher


def test_pause_per_kennung_trifft(gross):
    tun("add_calendar_routine", label="Geigenstunde @ Geigenschule",
        rrule="FREQ=WEEKLY;BYDAY=TH", time="18:10")
    r = tun("add_calendar_pause", kennung=routinen()[0].kennung, von=DO_ISO, bis=DO_ISO,
            grund="Herbstferien")
    assert r.status == "ok" and DO.strftime("%d.%m.") in r
    assert kalender.entries_in_range(DO, DO)[DO_ISO][0]["ausfall"] == "Herbstferien"


def test_pause_mit_offenem_ende_traegt_den_tag_ein(gross):
    """Prüfstand f01, 08.10. abends: „fällt wegen der Ferien jetzt aus, weißt
    du bis wann?" — ohne Ende ging nichts, die Geige am Abend blieb stehen."""
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:10", ende="19:00")
    r = tun("add_calendar_pause", kennung=routinen()[0].kennung, von=DO_ISO,
            grund="Herbstferien")
    assert r.status == "ok"
    assert "NUR am" in r.beleg and "Ende noch offen" in r.beleg and "frag" in r
    assert kalender.entries_in_range(DO, DO)[DO_ISO][0]["ausfall"] == "Herbstferien"
    naechste = DO + timedelta(days=7)
    assert not kalender.entries_in_range(naechste, naechste)[naechste.isoformat()][0].get("ausfall")


def test_pause_ohne_ende_bleibt_auf_klein_ein_fehler():
    """Die klein-Schiene ist gemessen; ihr Vertrag (von UND bis) bleibt."""
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:10", ende="19:00")
    r = tun("add_calendar_pause", label="Geigenstunde", von=DO_ISO)
    assert werkzeug_befund.status_von(r) == "fehlgeschlagen"
    assert not kalender.entries_in_range(DO, DO)[DO_ISO][0].get("ausfall")


def test_pause_frage_nennt_das_offene_ende():
    import werkzeug_fragen
    f = werkzeug_fragen._frage_pause({"label": "Geigenstunde", "von": DO_ISO})
    assert DO_ISO in f and "Ende noch offen" in f


def test_routine_loeschen_sagt_was_verloren_geht(gross):
    """Prüfstand f01, 08.10. spät: zwei Geigen-Regeln, nur eine mit Ort. Die
    KI löschte die mit Ort — und kein Ergebnis sagte, dass der Ort weg ist."""
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="17:45", ende="18:30", ort="Geigenschule")
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:00")
    mit_ort = [s for s in routinen() if s.ort][0]
    ohne = [s for s in routinen() if not s.ort][0]
    r = tun("edit_calendar_routine", kennung=mit_ort.kennung, aktion="loeschen")
    assert r.status == "ok"
    assert "verloren" in r and "Ort 'Geigenschule'" in r and f"#{ohne.kennung}" in r
    assert "Ende" in r                     # die gelöschte hatte ein Ende, die andere nicht


def test_routine_loeschen_ohne_verlust_ohne_hinweis(gross):
    for t in ("17:45", "18:00"):
        tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
            time=t, ende="19:00", ort="Geigenschule")
    r = tun("edit_calendar_routine", kennung=routinen()[0].kennung, aktion="loeschen")
    assert r.status == "ok" and "verloren" not in r


def test_routine_aendern_nennt_gleichnamige_mit_mehr_feldern(gross):
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="17:45", ende="18:30", ort="Geigenschule")
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:00", ende="19:00")
    ohne = [s for s in routinen() if not s.ort][0]
    r = tun("edit_calendar_routine", kennung=ohne.kennung, aktion="aendern",
            time="18:10", ende="19:00")
    assert r.status == "ok"
    assert "gleichnamige" in r and "Ort 'Geigenschule'" in r and "löschst du sie" in r


def test_termin_loeschen_per_name_ohne_tag(gross):
    """„lösch nyam": es gab genau einen — trotzdem kam zweimal „day + label
    ist nötig" (Prüfstand f01)."""
    morgen = (date.today() + timedelta(days=1)).isoformat()
    tun("add_calendar_entry", layer="termine", day=morgen, label="nyam")
    r = tun("delete_calendar_entry", label="nyam")
    assert r.status == "ok" and "„nyam“" in r and "GELÖSCHT" in r
    for d in (morgen, DO_ISO):
        tun("add_calendar_entry", layer="termine", day=d, label="Drive")
    r = tun("delete_calendar_entry", label="Drive")
    assert werkzeug_befund.status_von(r) == "fehlgeschlagen" and "trifft 2" in r


def test_termin_per_name_ohne_tag_bleibt_auf_klein_ein_fehler():
    morgen = (date.today() + timedelta(days=1)).isoformat()
    tun("add_calendar_entry", layer="termine", day=morgen, label="nyam")
    r = tun("delete_calendar_entry", label="nyam")
    assert werkzeug_befund.status_von(r) == "fehlgeschlagen"


# ── Einzeltermine ──────────────────────────────────────────────────────

def test_einzeltermin_aendern_nur_genannte_felder(gross):
    tun("add_calendar_entry", layer="termine", day=DO_ISO, label="Drive",
        time="18:30", ende="19:30", ort="Halle")
    k = kennungen(tun("read_calendar", start_date=DO_ISO, end_date=DO_ISO), "t")[0]
    r = tun("edit_calendar_entry", kennung=k, time="19:00", ende="20:00")
    assert r.status == "ok" and r.beleg.startswith(
        f"Kalendereintrag „Drive“ am {ki_kalender.datum(DO_ISO)} 19:00–20:00 @ Halle GEÄNDERT (#{k})")
    neu = (DO + timedelta(days=1)).isoformat()
    k2 = kennungen(r, "t")[0]
    r = tun("edit_calendar_entry", kennung=k2, neuer_tag=neu)
    assert r.status == "ok"
    e = kalender.entries_in_range(DO, DO + timedelta(days=1))
    assert DO_ISO not in e
    assert (e[neu][0]["time"], e[neu][0]["ende"], e[neu][0]["ort"]) == ("19:00", "20:00", "Halle")


def test_loeschen_per_name_nur_bei_einem_treffer(gross):
    tun("add_calendar_entry", layer="termine", day=DO_ISO, label="Kino", time="18:00")
    tun("add_calendar_entry", layer="termine", day=DO_ISO, label="Kino mit Lea", time="21:00")
    r = tun("delete_calendar_entry", day=DO_ISO, label="Kin")
    assert r.status == "fehlgeschlagen" and "trifft 2" in r
    r = tun("delete_calendar_entry", day=DO_ISO, label="Kino")      # genauer Titel geht vor
    assert r.status == "ok"
    assert [e["label"] for e in kalender.entries_in_range(DO, DO)[DO_ISO]] == ["Kino mit Lea"]


def test_mehrtaegig_wird_am_zweiten_tag_gefunden_und_ganz_geloescht(gross):
    """Am 08.10.: 'nyam' am 09.10. löschen → „nicht gefunden", weil die
    Reise unter ihrem ERSTEN Tag gespeichert ist."""
    kalender.add_span("termine", DO_ISO, (DO + timedelta(days=1)).isoformat(), "nyam")
    r = tun("delete_calendar_entry", day=(DO + timedelta(days=1)).isoformat(), label="nyam")
    assert r.status == "ok" and "ganz gelöscht" in r
    assert not kalender.entries_in_range(DO, DO + timedelta(days=1))


# ── Warnungen ──────────────────────────────────────────────────────────

def test_warnungen_lesbar_und_frisch(gross):
    heute = date.today()
    tun("add_calendar_entry", layer="termine", day=heute.isoformat(), label="Geige",
        time="18:10", ende="19:10")
    tun("add_calendar_entry", layer="termine", day=heute.isoformat(), label="Fahrschule",
        time="19:00", ende="20:00")
    w = tun("read_calendar_warnings")
    assert "Teil-Überlappung" in w and "Geige" in w and "frisch berechnet" in w
    assert "Geige" in tun("read_calendar_warnings", suche="Fahrschule")
    k = kennungen(tun("read_calendar", start_date=heute.isoformat(),
                      end_date=heute.isoformat()), "t")
    r = tun("edit_calendar_entry", kennung=k[0], ende="19:00")
    assert "Keine Kalender-Warnung nennt 'Geige'" in r
    assert "Keine Kalender-Warnungen" in tun("read_calendar_warnings")


# ── Die Fragen an Sasha nennen den Termin, nicht die Kennung ───────────

def test_frage_mit_kennung_nennt_was_gemeint_ist(gross):
    import erlaubnis
    tun("add_calendar_routine", label="Geigenstunde", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:10", ende="19:10")
    k = routinen()[0].kennung
    f = erlaubnis.frage("edit_calendar_routine", {"kennung": k, "aktion": "aendern",
                                                  "ende": "19:00"})
    assert '"Geigenstunde" (wöchentlich do 18:10–19:10' in f and "Ende 19:00" in f
    f = erlaubnis.frage("edit_calendar_routine", {"kennung": "r0000", "aktion": "loeschen"})
    assert "gibt es so nicht" in f


# ── Ganz oder gar nicht (2026-10-09) ───────────────────────────────────
# Bricht ein Kalender-Werkzeug ab, ist der Datenstand wie vorher: das Dict
# des Speichers gleich, und im JSON-Speicher die Datei Byte für Byte.

def _stand():
    import copy
    roh = copy.deepcopy(kalender._load_raw())
    datei = kalender.CAL_PATH.read_bytes() if kalender._speicher().art != "ics" \
        and kalender.CAL_PATH.exists() else None
    return roh, datei


@pytest.fixture
def bestand(gross):
    tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH",
        time="18:10", ende="19:00", ort="Schule")
    tun("add_calendar_routine", label="Chor", rrule="FREQ=WEEKLY;BYDAY=MO", time="14:00")
    tun("add_calendar_routine", label="Chor", rrule="FREQ=WEEKLY;BYDAY=WE", time="14:00")
    tun("add_calendar_entry", layer="termine", day=DO_ISO, label="Drive",
        time="18:30", ende="19:30")
    import kalender_kennung
    kalender_kennung.alle_eintraege()          # feste Kennungen vergeben (schreibt einmal)


@pytest.mark.parametrize("name, args, code", [
    ("add_calendar_entry", {"day": DO_ISO, "label": "Arzt", "time": "10:00", "ende": "09:00"},
     "K-ENDE-VOR-BEGINN"),
    ("add_calendar_entry", {"day": "morgen", "label": "Arzt"}, "K-DATUM-UNGUELTIG"),
    ("add_calendar_entry", {"day": DO_ISO, "label": "Arzt", "layer": "gibtsnicht"},
     "K-EBENE-UNBEKANNT"),
    ("add_calendar_routine", {"label": "Lauf", "rrule": "FREQ=QUATSCH"}, "K-RRULE-UNGUELTIG"),
    ("add_calendar_routine", {"label": "Lauf", "rrule": "FREQ=DAILY", "time": "25:00"},
     "K-ZEIT-UNGUELTIG"),
    ("edit_calendar_routine", {"label": "Chor", "aktion": "aendern", "time": "15:00"},
     "K-MEHRDEUTIG"),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "aendern", "time": "19:30"},
     "K-ENDE-VOR-BEGINN"),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "umbauen"}, "K-AKTION-UNGUELTIG"),
    ("edit_calendar_routine", {"kennung": "#r0000", "aktion": "loeschen"}, "K-KENNUNG-UNBEKANNT"),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "aendern", "nur_am": "2026-01-02",
                               "time": "17:00", "ende": "18:00"}, "K-KEIN-VORKOMMEN"),
    ("add_calendar_pause", {"label": "Geigenstunde", "von": DO_ISO, "bis": DO_ISO},
     "K-PAUSE-KEINE-ROUTINE"),
    ("add_calendar_pause", {"label": "Geige", "von": DO_ISO, "bis": "2020-01-01"},
     "K-SPANNE-VERDREHT"),
    ("add_calendar_routine", {"label": "Lauf", "rrule": "FREQ=DAILY", "von": "", "bis": ""},
     "K-ZEITRAUM-FEHLT"),
    ("add_calendar_routine", {"label": "Lauf", "rrule": "FREQ=DAILY;COUNT=5"},
     "K-RRULE-MIT-ENDE"),
    ("add_calendar_routine", {"label": "Lauf", "rrule": "FREQ=DAILY",
                              "von": "2026-12-01", "bis": "2026-11-01"}, "K-SPANNE-VERDREHT"),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "aendern", "bis": "2000-01-01"},
     "K-SPANNE-VERDREHT"),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "aendern",
                               "rrule": "FREQ=WEEKLY;BYDAY=FR;UNTIL=20270101T000000"},
     "K-RRULE-MIT-ENDE"),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "aendern", "nur_am": DO_ISO,
                               "von": DO_ISO}, "K-UNBEKANNTES-FELD"),
    ("delete_calendar_entry", {"day": DO_ISO, "label": "Kino"}, "K-NICHT-GEFUNDEN"),
    ("edit_calendar_entry", {"day": DO_ISO, "label": "Drive"}, "K-NICHTS-ZU-AENDERN"),
    ("edit_calendar_entry", {"day": DO_ISO, "label": "Drive", "bis": DO_ISO},
     "K-UNBEKANNTES-FELD"),
])
def test_abbruch_laesst_den_kalender_wie_er_war(bestand, name, args, code):
    vorher = _stand()
    r = tun(name, **args)
    assert r.status == "fehlgeschlagen" and r.code == code, r
    assert "ABGEBROCHEN – nichts" in r and f"Fehler {code}:" in r
    assert _stand() == vorher


def test_anders_als_verlangt_wird_zurueckgenommen(bestand, monkeypatch):
    """Steht ein neuer Eintrag nachgelesen anders da als verlangt, wird er
    wieder gelöscht — nichts bleibt, Code W-NICHT-GESPEICHERT."""
    import kalender_kennung
    vorher = _stand()
    echt = kalender_kennung.eintrag
    monkeypatch.setattr(kalender_kennung, "eintrag",
                        lambda k: dict(echt(k), ende="23:59"))
    for name, args in (("add_calendar_entry", {"day": DO_ISO, "label": "Arzt",
                                               "time": "10:00", "ende": "11:00"}),
                       ("add_calendar_routine", {"label": "Lauf", "rrule": "FREQ=DAILY",
                                                 "time": "07:00", "ende": "07:30"})):
        r = tun(name, **args)
        assert r.code == "W-NICHT-GESPEICHERT" and "wieder gelöscht" in r, r
        # kalender_kennung.routine_loeschen legt ein leeres „pausen" an, wo
        # keins war — inhaltlich dasselbe (gemeldet an die Kalender-Sitzung).
        jetzt = dict(_stand()[0])
        if jetzt.get("pausen") == [] and "pausen" not in vorher[0]:
            del jetzt["pausen"]
        assert jetzt == vorher[0]


def test_feste_form_aus_dem_echten_stand(gross):
    r = tun("add_calendar_entry", layer="termine", day=DO_ISO, label="Geigenstunde",
            time="18:10", ende="19:00", ort="Geigenschule")
    k = kennungen(r, "t")[0]
    assert r.startswith(f"Kalendereintrag „Geigenstunde“ am {ki_kalender.datum(DO_ISO)} "
                        f"18:10–19:00 @ Geigenschule EINGETRAGEN (#{k}).")
    r = tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH",
            time="18:10", ende="19:00", ort="Schule")
    k = kennungen(r)[0]
    r = tun("edit_calendar_routine", kennung=k, aktion="aendern", ort="Aula")
    assert r.startswith(f"Routine „Geige“ wöchentlich do 18:10–19:00 @ Aula"
                        f"{ki_kalender.zeitraum(VON_STD, BIS_STD)} GEÄNDERT (#{k})")


# ── Zeitraum einer Serie (2026-10-09) ──────────────────────────────────
# Sasha: „sie hat meine fächer eingetragen aber die routinen sind jetzt
# quasi für immer statt eine bestimmte periode, also auch diese und letzte
# woche". Seitdem verlangt add_calendar_routine auf gross von/bis.

MO = date.today() + timedelta(days=(0 - date.today().weekday()) % 7 + 7)   # Montag in 1–2 Wochen


def _montage(von: date, bis: date) -> list:
    return [t for t, es in kalender.entries_in_range(von, bis).items()
            if any(e.get("label") == "Analysis I" and not e.get("ausfall") for e in es)]


def test_routine_mit_zeitraum_nur_innerhalb(gross):
    bis = MO + timedelta(days=14)
    r = roh("add_calendar_routine", label="Analysis I", rrule="FREQ=WEEKLY;BYDAY=MO",
            time="10:00", ende="12:00", ort="Hörsaal 1", von=MO.isoformat(), bis=bis.isoformat())
    assert r.status == "ok", r
    assert (f"10:00–12:00 @ Hörsaal 1 vom {MO.strftime('%d.%m.%Y')} bis "
            f"{bis.strftime('%d.%m.%Y')} EINGETRAGEN") in r
    s = routinen()[0]
    assert s.roh.get("seit") == MO.isoformat()
    assert ki_kalender.regel_bis(s.rrule) == bis.isoformat()
    tage = _montage(MO - timedelta(days=21), bis + timedelta(days=21))
    assert tage == [(MO + timedelta(days=7 * i)).isoformat() for i in range(3)]


def test_routine_ohne_zeitraum_schreibt_nichts(gross):
    for args in ({}, {"von": MO.isoformat()}, {"bis": MO.isoformat()}):
        r = roh("add_calendar_routine", label="Analysis I", rrule="FREQ=WEEKLY;BYDAY=MO",
                time="10:00", **args)
        assert r.code == "K-ZEITRAUM-FEHLT" and "nichts eingetragen" in r, r
    assert routinen() == []


@pytest.mark.parametrize("regel", ["FREQ=WEEKLY;BYDAY=MO;UNTIL=20270213T235959",
                                   "FREQ=WEEKLY;COUNT=10;BYDAY=MO"])
def test_routine_ende_nur_ueber_bis(gross, regel):
    r = roh("add_calendar_routine", label="Analysis I", rrule=regel,
            von=MO.isoformat(), bis="2027-02-13")
    assert r.code == "K-RRULE-MIT-ENDE", r
    assert routinen() == []


def test_routine_bis_vor_von(gross):
    r = roh("add_calendar_routine", label="Analysis I", rrule="FREQ=WEEKLY;BYDAY=MO",
            von="2027-02-13", bis="2026-10-12")
    assert r.code == "K-SPANNE-VERDREHT", r
    assert routinen() == []


def test_klein_braucht_keinen_zeitraum():
    r = roh("add_calendar_routine", layer="routinen", label="Geige",
            rrule="FREQ=WEEKLY;BYDAY=TH", time="18:10")
    assert r.status == "ok", r
    s = routinen()[0]
    assert s.rrule == "FREQ=WEEKLY;BYDAY=TH" and "seit" not in s.roh


def test_aendern_begrenzt_eine_serie_fuer_immer(gross):
    """Sashas bestehende Uni-Routinen: ohne Zeitraum angelegt, nachträglich
    begrenzt."""
    kalender.add_routine(layer="termine", label="Analysis I", rrule_str="FREQ=WEEKLY;BYDAY=MO",
                         time="10:00", ende="12:00")
    text = tun("read_calendar", zeitraum="naechste_30_tage", suche="Analysis")
    assert "(ohne Enddatum)" in text
    bis = MO + timedelta(days=7)
    k = routinen()[0].kennung
    r = roh("edit_calendar_routine", kennung=k, aktion="aendern",
            von=MO.isoformat(), bis=bis.isoformat())
    assert r.status == "ok", r
    assert f"vom {MO.strftime('%d.%m.%Y')} bis {bis.strftime('%d.%m.%Y')} GEÄNDERT" in r
    s = routinen()[0]
    assert s.roh.get("seit") == MO.isoformat() and (s.time, s.ende) == ("10:00", "12:00")
    assert _montage(MO - timedelta(days=14), MO + timedelta(days=28)) == \
        [MO.isoformat(), bis.isoformat()]
    text = tun("read_calendar", zeitraum="naechste_30_tage", suche="Analysis")
    assert "(ohne Enddatum)" not in text
    assert f"vom {MO.strftime('%d.%m.%Y')} bis {bis.strftime('%d.%m.%Y')}" in text
    # Neue Wiederholung behält das Ende; nur bis verschiebt es.
    roh("edit_calendar_routine", kennung=k, aktion="aendern", rrule="FREQ=WEEKLY;BYDAY=TU")
    s = routinen()[0]
    assert "BYDAY=TU" in s.rrule and ki_kalender.regel_bis(s.rrule) == bis.isoformat()
    roh("edit_calendar_routine", kennung=k, aktion="aendern", bis="2027-02-13")
    s = routinen()[0]
    assert ki_kalender.regel_bis(s.rrule) == "2027-02-13" and s.rrule.count("UNTIL") == 1
    assert s.roh.get("seit") == MO.isoformat()


def test_zeitraum_anders_nachgelesen_wird_zurueckgenommen(gross, monkeypatch):
    import kalender_kennung
    echt = kalender_kennung.eintrag
    monkeypatch.setattr(kalender_kennung, "eintrag", lambda k: dict(echt(k), seit="2000-01-01"))
    r = roh("add_calendar_routine", label="Analysis I", rrule="FREQ=WEEKLY;BYDAY=MO",
            von=MO.isoformat(), bis="2027-02-13")
    assert r.code == "W-NICHT-GESPEICHERT" and "seit" in r, r
    assert routinen() == []


def test_frage_nennt_den_zeitraum():
    import erlaubnis
    f = erlaubnis.frage("add_calendar_routine", {"label": "Analysis I",
                                                 "rrule": "FREQ=WEEKLY;BYDAY=MO",
                                                 "von": "2026-10-12", "bis": "2027-02-13"})
    assert "vom 12.10.2026 bis 13.02.2027 eintragen?" in f
    f = erlaubnis.frage("edit_calendar_routine", {"label": "Analysis I", "aktion": "aendern",
                                                  "von": "2026-10-12", "bis": "2027-02-13"})
    assert "erster Tag 2026-10-12" in f and "letzter Tag 2027-02-13" in f
