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
            for ch in e:
                d.taste(ord(ch))
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


# ── a: Anlegen ─────────────────────────────────────────────────────────
def test_anlegen_termin_mit_ende_prueft_kollision():
    p = tippe(kw.dialog_anlegen(TAG), "14:00", "15:00", "Zahnarzt").plan()
    assert p["aufrufe"] == [("POST", "/api/calendar/entry", {
        "layer": "termine", "day": "2026-10-07", "label": "Zahnarzt",
        "time": "14:00", "ende": "15:00"})]
    assert p["konflikt"] == {"day": "2026-10-07", "label": "Zahnarzt",
                             "time": "14:00", "ende": "15:00"}


def test_anlegen_mit_dauer_ueber_tage_wird_spanne():
    p = tippe(kw.dialog_anlegen(date(2026, 10, 9)), "18:00", "+1d20h", "Berlin").plan()
    (m, pfad, body), = p["aufrufe"]
    assert (m, pfad) == ("POST", "/api/calendar/spanne")
    assert body == {"von": "2026-10-09", "bis": "2026-10-11", "label": "Berlin",
                    "start_zeit": "18:00", "end_zeit": "14:00"}


def test_anlegen_ende_vor_start_ist_naechster_tag():
    p = tippe(kw.dialog_anlegen(TAG), "22:00", "02:00", "Party").plan()
    assert p["aufrufe"][0][2]["bis"] == "2026-10-08"


def test_anlegen_ganztags_mehrere_tage():
    d = kw.dialog_anlegen(TAG)
    tippe(d, "", "3", "Urlaub")
    assert d.plan()["aufrufe"] == [("POST", "/api/calendar/spanne", {
        "von": "2026-10-07", "bis": "2026-10-09", "label": "Urlaub"})]


def test_falsche_eingabe_bleibt_stehen():
    d = kw.dialog_anlegen(TAG)
    tippe(d, "abc")
    assert d.schritt.name == "start" and "uhrzeit" in d.fehler
    assert d.taste(27) == "abbruch"


# ── e: Bearbeiten ──────────────────────────────────────────────────────
GEIGE = {"label": "Geige", "layer": "routinen", "recurring": True,
         "time": "10:00", "ende": "11:00", "rrule": "FREQ=WEEKLY;BYDAY=WE"}
MESSE = {"label": "Messe", "layer": "termine", "spanning": True,
         "von": "2026-10-06", "bis": "2026-10-08", "time": "10:00", "ende": "18:00"}
ZAHN = {"label": "Zahnarzt", "layer": "termine", "time": "14:00", "ende": "15:00"}


def test_einmal_startzeit_vorbelegt_und_gesendet():
    d = kw.dialog_bearbeiten(ZAHN, TAG, HEUTE)
    tippe(d, "1")
    assert d.eingabe == "14:00"                       # calcurse zeigt den jetzigen Wert
    tippe(d, "14:30")
    (m, pfad, body), = d.plan()["aufrufe"]
    assert (m, pfad) == ("PUT", "/api/calendar/eintrag")
    assert body["new"] == {"time": "14:30"} and body["time"] == "14:00"


def test_routine_nur_dieser_tag():
    d = tippe(kw.dialog_bearbeiten(GEIGE, TAG, HEUTE), "d", "1", "12:00")
    (m, pfad, body), = d.plan()["aufrufe"]
    assert pfad == "/api/calendar/routine/abweichung"
    assert body["day"] == "2026-10-07" and body["new"] == {"time": "12:00"}


def test_routine_alle_wiederholung():
    d = tippe(kw.dialog_bearbeiten(GEIGE, TAG, HEUTE), "a", "6", "w", "1", "di do", "")
    (m, pfad, body), = d.plan()["aufrufe"]
    assert (m, pfad) == ("PUT", "/api/calendar/routine")
    assert body["new"]["wiederholung"] == {"freq": "w", "intervall": 1, "bis": None,
                                           "wochentage": ["TU", "TH"]}


def test_spanne_einzelner_tag_und_alle():
    d = tippe(kw.dialog_bearbeiten(MESSE, TAG, HEUTE), "d", "1", "09:00")
    (_, pfad, body), = d.plan()["aufrufe"]
    assert pfad == "/api/calendar/spanne/tag"
    assert (body["von"], body["day"], body["time"], body["ende"]) == \
        ("2026-10-06", "2026-10-07", "09:00", "18:00")
    d = tippe(kw.dialog_bearbeiten(MESSE, TAG, HEUTE), "a", "5", "+7")
    (m, pfad, body), = d.plan()["aufrufe"]
    assert (m, pfad, body["new"]) == ("PUT", "/api/calendar/spanne", {"verschieben": 7})


# ── r: Wiederholen ─────────────────────────────────────────────────────
def test_taeglich_mit_ende_wird_spanne_und_original_weg():
    d = tippe(kw.dialog_wiederholen(ZAHN, TAG, HEUTE), "t", "1", "09.10.2026")
    neu, weg = d.plan()["aufrufe"]
    assert neu == ("POST", "/api/calendar/spanne", {
        "von": "2026-10-07", "bis": "2026-10-09", "label": "Zahnarzt",
        "tageszeit": ["14:00", "15:00"]})
    assert weg[0:2] == ("DELETE", "/api/calendar/eintrag")


def test_woechentlich_wird_routine_ab_diesem_tag():
    d = tippe(kw.dialog_wiederholen(ZAHN, TAG, HEUTE), "w", "2", "", "")
    neu, weg = d.plan()["aufrufe"]
    assert neu[1] == "/api/calendar/routine"
    assert (neu[2]["freq"], neu[2]["intervall"], neu[2]["seit"]) == ("w", 2, "2026-10-07")
    assert neu[2]["wochentage"] is None                 # = Wochentag des Tags


def test_wiederholen_einer_routine_fragt_gleich_die_regel():
    d = kw.dialog_wiederholen(GEIGE, TAG, HEUTE)
    assert d.schritt.name == "freq"


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
