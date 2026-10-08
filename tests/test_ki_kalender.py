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


def tun(name, **args):
    return ki_werkzeuge._verteilen(name, args)


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
    s = [s for s in routinen() if s.rrule.endswith("TH")][0]
    assert (s.time, s.ende, s.ort) == ("18:10", "19:10", "Geigenschule")
    assert [s for s in routinen() if s.rrule.endswith("TU")][0].time == "17:00"


def test_alte_kennung_trifft_nichts(gross):
    tun("add_calendar_routine", label="Geige", rrule="FREQ=WEEKLY;BYDAY=TH", time="18:00")
    alt = routinen()[0].kennung
    tun("edit_calendar_routine", kennung=alt, aktion="aendern", time="18:10")
    r = tun("edit_calendar_routine", kennung=alt, aktion="aendern", time="19:00")
    assert r.status == "fehlgeschlagen" and "gibt es nicht (mehr)" in r
    assert routinen()[0].time == "18:10"


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
    r = tun("add_calendar_pause", label="Geigenstunde", von=DO_ISO, bis=DO_ISO)
    assert r.status == "teilweise"
    assert "KEINE Routine" in r and "Geigenstunde @ Geigenschule" in r


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


# ── Einzeltermine ──────────────────────────────────────────────────────

def test_einzeltermin_aendern_nur_genannte_felder(gross):
    tun("add_calendar_entry", layer="termine", day=DO_ISO, label="Drive",
        time="18:30", ende="19:30", ort="Halle")
    k = kennungen(tun("read_calendar", start_date=DO_ISO, end_date=DO_ISO), "t")[0]
    r = tun("edit_calendar_entry", kennung=k, time="19:00", ende="20:00")
    assert r.status == "ok" and "19:00–20:00 Drive @ Halle" in r.beleg
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
    assert '"Geigenstunde" (wöchentlich do 18:10–19:10)' in f and "Ende 19:00" in f
    f = erlaubnis.frage("edit_calendar_routine", {"kennung": "r0000", "aktion": "loeschen"})
    assert "gibt es so nicht" in f
