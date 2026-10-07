"""
Kalender-Werkzeuge (tui/ansichten/kalender_werkzeuge.py): Eingaben lesen,
Dialoge Schritt für Schritt wie calcurse, und welche Backend-Aufrufe daraus
werden. Reine Logik — ohne Terminal und ohne Backend.
"""
from datetime import date

import pytest

from tui.ansichten import kalender_werkzeuge as kw

TAG = date(2026, 10, 7)          # Mittwoch
HEUTE = date(2026, 10, 7)


def tippe(d, *eingaben):
    """Jede Eingabe: Text + Enter, oder ein einzelnes Wahl-Zeichen."""
    for e in eingaben:
        s = d.schritt
        assert s is not None, "Dialog schon fertig, %r übrig" % (e,)
        if s.art == "wahl":
            d.taste(ord(e))
        else:
            d.eingabe = ""
            for b in e.encode("utf-8"):      # wie curses: Byte für Byte
                d.taste(b)
            d.taste(10)
    return d


# ── Eingaben ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("roh,soll", [
    ("9", "09:00"), ("9:5", "09:05"), ("930", "09:30"), ("18.00", "18:00"),
    ("1830", "18:30"), ("25:00", None), ("abc", None), ("", None)])
def test_zeit(roh, soll):
    assert kw.zeit(roh) == soll


@pytest.mark.parametrize("roh,soll", [
    ("+45", 45), ("+1:30", 90), ("+2h", 120), ("+2d20h", 2 * 1440 + 1200),
    ("+1h30m", 90), ("45", None), ("+", None), ("+x", None)])
def test_dauer(roh, soll):
    assert kw.dauer(roh) == soll


def test_datum_ohne_jahr_meint_das_naechste():
    assert kw.datum("14.10.", HEUTE) == date(2026, 10, 14)
    assert kw.datum("1.3.", HEUTE) == date(2027, 3, 1)
    assert kw.datum("14.10.26", HEUTE) == date(2026, 10, 14)
    assert kw.datum("2026-12-24", HEUTE) == date(2026, 12, 24)
    assert kw.datum("31.02.", HEUTE) is None


def test_wochentage():
    assert kw.wochentage("di do") == ["TU", "TH"]
    assert kw.wochentage("Do,Di") == ["TU", "TH"]
    assert kw.wochentage("mo-fr") == ["MO", "TU", "WE", "TH", "FR"]
    assert kw.wochentage("") == []
    assert kw.wochentage("xx") is None


def test_regel_text():
    assert kw.regel_text("FREQ=WEEKLY;BYDAY=TU,TH") == "wöchentlich: Di, Do"
    assert kw.regel_text("FREQ=DAILY;INTERVAL=2;UNTIL=20261013T235959") == \
        "alle 2 Tage bis 13.10.2026"
    assert kw.regel_text("FREQ=MONTHLY;BYMONTHDAY=7") == "monatlich am 7."


# ── Formular (Modal) ───────────────────────────────────────────────────
def fuelle(f, **werte):
    """Felder per Name setzen (Text oder Auswahl), dann Enter."""
    for name, wert in werte.items():
        feld = next(x for x in f.felder if x.name == name)
        if feld.art == "wahl":
            feld.wahl = feld.optionen.index(wert)
        else:
            feld.text = wert
    return f.taste(10)


def test_formular_tippen_tab_und_umlaute():
    f = kw.formular_neu(TAG, HEUTE)
    for b in "Gießen".encode("utf-8"):
        f.taste(b)
    assert f.feld.text == "Gießen"
    f.taste(9)
    assert f.feld.name == "datum"
    f.taste(9)
    f.taste(261)                                   # → in der Auswahl
    assert f.feld.roh() == "ja"
    assert "von" not in [x.name for x in f.sichtbar()]   # ganztägig: keine Uhrzeit
    assert f.taste(27) == "abbruch"


def test_anlegen_termin_mit_ende_prueft_kollision():
    f = kw.formular_neu(TAG, HEUTE)
    assert fuelle(f, titel="Zahnarzt", von="14:00", bis="15:00") == "fertig"
    p = f.plan()
    assert p["aufrufe"] == [("POST", "/api/calendar/entry", {
        "layer": "termine", "day": "2026-10-07", "label": "Zahnarzt",
        "time": "14:00", "ende": "15:00"})]
    assert p["konflikt"] == {"day": "2026-10-07", "label": "Zahnarzt",
                             "time": "14:00", "ende": "15:00"}


def test_anlegen_mit_dauer_ueber_tage_wird_spanne():
    f = kw.formular_neu(date(2026, 10, 9), HEUTE)
    fuelle(f, titel="Berlin", von="18:00", bis="+1d20h")
    (m, pfad, body), = f.plan()["aufrufe"]
    assert (m, pfad) == ("POST", "/api/calendar/spanne")
    assert body == {"layer": "termine", "von": "2026-10-09", "bis": "2026-10-11",
                    "label": "Berlin", "start_zeit": "18:00", "end_zeit": "14:00"}


def test_anlegen_ende_vor_start_ist_naechster_tag():
    f = kw.formular_neu(TAG, HEUTE)
    fuelle(f, titel="Party", von="22:00", bis="02:00")
    assert f.plan()["aufrufe"][0][2]["bis"] == "2026-10-08"


def test_anlegen_ganztags_mehrere_tage():
    f = kw.formular_neu(TAG, HEUTE)
    fuelle(f, titel="Urlaub", ganz="ja", tage="3")
    assert f.plan()["aufrufe"] == [("POST", "/api/calendar/spanne", {
        "layer": "termine", "von": "2026-10-07", "bis": "2026-10-09", "label": "Urlaub"})]


def test_anlegen_mit_wiederholung_wird_routine_oder_spanne():
    f = kw.formular_neu(TAG, HEUTE)
    fuelle(f, titel="Geige", von="10:00", bis="11:00", wied="wöchentlich", wtage="di do")
    (_, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/routine"
    assert (body["freq"], body["wochentage"], body["seit"], body["ende"]) == \
        ("w", ["TU", "TH"], "2026-10-07", "11:00")
    f = kw.formular_neu(TAG, HEUTE)
    fuelle(f, titel="Messe", von="10:00", bis="18:00", wied="täglich", wbis="09.10.2026")
    (_, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/spanne" and body["tageszeit"] == ["10:00", "18:00"]


def test_falsche_eingabe_bleibt_stehen():
    f = kw.formular_neu(TAG, HEUTE)
    assert fuelle(f, titel="X", von="abc") == "weiter"
    assert f.feld.name == "von" and "uhrzeit" in f.fehler
    assert fuelle(f, titel="") == "weiter" and f.feld.name == "titel"


# ── e: Bearbeiten ──────────────────────────────────────────────────────
GEIGE = {"label": "Geige", "layer": "termine", "recurring": True,
         "time": "10:00", "ende": "11:00", "rrule": "FREQ=WEEKLY;BYDAY=WE"}
MESSE = {"label": "Messe", "layer": "termine", "spanning": True,
         "von": "2026-10-06", "bis": "2026-10-08", "time": "10:00", "ende": "18:00"}
ZAHN = {"label": "Zahnarzt", "layer": "termine", "time": "14:00", "ende": "15:00"}


def test_einmal_vorbelegt_und_gesendet():
    f = kw.formular_bearbeiten(ZAHN, TAG, HEUTE)
    assert {x.name: x.roh() for x in f.felder}["von"] == "14:00"
    fuelle(f, von="14:30")
    (m, pfad, body), = f.plan()["aufrufe"]
    assert (m, pfad) == ("PUT", "/api/calendar/eintrag")
    assert body["time"] == "14:00" and body["new"]["time"] == "14:30"
    assert body["new"]["ende"] == "15:00"


def test_routine_fragt_erst_dieser_oder_alle():
    d = kw.formular_bearbeiten(GEIGE, TAG, HEUTE)
    assert isinstance(d, kw.Dialog)
    d.taste(ord("d"))
    f = d.plan()["weiter"]
    fuelle(f, von="12:00", bis="13:00")
    (_, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/routine/abweichung"
    assert body["day"] == "2026-10-07" and body["new"]["time"] == "12:00"


def test_routine_alle_wiederholung_aendern():
    d = kw.formular_bearbeiten(GEIGE, TAG, HEUTE)
    d.taste(ord("a"))
    f = d.plan()["weiter"]
    assert {x.name: x.roh() for x in f.felder}["wied"] == "wöchentlich"
    fuelle(f, wtage="di do")
    (m, pfad, body), = f.plan()["aufrufe"]
    assert (m, pfad) == ("PUT", "/api/calendar/routine")
    assert body["new"]["wiederholung"]["wochentage"] == ["TU", "TH"]
    d = kw.formular_bearbeiten(GEIGE, TAG, HEUTE)
    d.taste(ord("a"))
    f = d.plan()["weiter"]
    fuelle(f, titel="Violine")
    assert "wiederholung" not in f.plan()["aufrufe"][0][2]["new"], "Regel unverändert"


def test_spanne_einzelner_tag_und_alle():
    d = kw.formular_bearbeiten(MESSE, TAG, HEUTE)
    d.taste(ord("d"))
    f = d.plan()["weiter"]
    fuelle(f, von="09:00")
    (_, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/spanne/tag"
    assert (body["von"], body["day"], body["time"], body["ende"]) == \
        ("2026-10-06", "2026-10-07", "09:00", "18:00")
    d = kw.formular_bearbeiten(MESSE, TAG, HEUTE)
    d.taste(ord("a"))
    f = d.plan()["weiter"]
    fuelle(f, erster="13.10.2026", letzter="15.10.2026")
    (m, pfad, body), = f.plan()["aufrufe"]
    assert (m, pfad) == ("PUT", "/api/calendar/spanne")
    assert body["new"]["verschieben"] == 7 and "bis" not in body["new"]


# ── r: Wiederholen ─────────────────────────────────────────────────────
def test_taeglich_mit_ende_wird_spanne_und_original_weg():
    f = kw.formular_wiederholen(ZAHN, TAG, HEUTE)
    assert f.feld.name == "wied"
    fuelle(f, wied="täglich", wbis="09.10.2026")
    neu, weg = f.plan()["aufrufe"]
    assert neu[1] == "/api/calendar/spanne" and neu[2]["tageszeit"] == ["14:00", "15:00"]
    assert weg[0:2] == ("DELETE", "/api/calendar/eintrag")


def test_woechentlich_wird_routine_ab_diesem_tag():
    f = kw.formular_wiederholen(ZAHN, TAG, HEUTE)
    fuelle(f, wied="wöchentlich", alle="2")
    neu, weg = f.plan()["aufrufe"]
    assert neu[1] == "/api/calendar/routine"
    assert (neu[2]["freq"], neu[2]["intervall"], neu[2]["seit"]) == ("w", 2, "2026-10-07")


def test_wiederholen_einer_routine_geht_direkt_zur_regel():
    f = kw.formular_wiederholen(GEIGE, TAG, HEUTE)
    assert isinstance(f, kw.Formular) and f.feld.name == "wied"
    assert kw.formular_wiederholen(MESSE, TAG, HEUTE) is None


# ── d: Löschen ─────────────────────────────────────────────────────────
def test_loeschen_routine_alle_oder_dieses():
    d = tippe(kw.dialog_loeschen(GEIGE, TAG), "2")
    assert d.plan()["aufrufe"][0][1] == "/api/calendar/routine/skip"
    d = tippe(kw.dialog_loeschen(GEIGE, TAG), "1")
    assert d.plan()["aufrufe"][0][0:2] == ("DELETE", "/api/calendar/routine")
    d = tippe(kw.dialog_loeschen(GEIGE, TAG), "n")
    assert d.plan()["aufrufe"] == []


def test_loeschen_spanne_am_starttag_und_nein():
    d = tippe(kw.dialog_loeschen(MESSE, TAG), "j")
    assert d.plan()["aufrufe"][0][2]["day"] == "2026-10-06"
    assert tippe(kw.dialog_loeschen(ZAHN, TAG), "n").plan()["aufrufe"] == []


# ── Rest ───────────────────────────────────────────────────────────────
def test_einfuegen_aus_routine_wird_einmal_termin():
    p = kw.plan_einfuegen(kw.kopie(GEIGE), date(2026, 10, 10))
    (_, pfad, body), = p["aufrufe"]
    assert pfad == "/api/calendar/entry" and body["day"] == "2026-10-10"
    assert "recurring" not in body and body["label"] == "Geige"


def test_gehe_zu_leer_ist_heute():
    assert tippe(kw.dialog_gehe_zu(HEUTE), "").plan()["danach"]["tag"] == HEUTE


def test_details_zeigt_regel_und_spanne():
    z = "\n".join(kw.details(GEIGE, TAG))
    assert "wöchentlich: Mi" in z and "10:00 -> 11:00" in z
    z = "\n".join(kw.details(MESSE, TAG))
    assert "06.10.2026 bis 08.10.2026" in z


def test_auswahl_folgt_der_reihenfolge_der_ansicht():
    from tui.ansichten import kalender_beispiel as kb
    from tui.ansichten import kalender_ansichten as ka
    d = kb.api_daten("month", "2026-10-09")
    ws = [t["label"] for t in kw.eintraege(d, date(2026, 10, 9), False)]
    an = [t["label"] for t in ka._tag_eintraege(d, "2026-10-09", False)]
    assert ws == an and all("roh" in t for t in kw.eintraege(d, date(2026, 10, 9), False))
