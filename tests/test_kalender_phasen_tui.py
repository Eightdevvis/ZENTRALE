"""
Der Kasten „Rhythmus" (tui/ansichten/kalender_phasen.py): Phasen anlegen,
ab jetzt ändern, löschen, nur an einem Tag, für einen Zeitraum.

Sasha, 10.10.2026: „wenn ich heute come down um 9:30 habe, dann 3 tage um 2
ins bett gehe, muss das änderbar sein … mach alles möglich". Reine Logik:
geprüft wird, welche Aufrufe aus Tasten und Formularen werden.
"""
from datetime import date

import pytest

from tui.ansichten import kalender_phasen as kp

TAG = date(2026, 10, 14)            # Mittwoch
HEUTE = date(2026, 10, 10)
MOTIVE = [{"schluessel": "nachthimmel", "name": "Nachthimmel"},
          {"schluessel": "schlaf", "name": "Schlaf"},
          {"schluessel": "essen", "name": "Essen"}]
SCHLAF = {"kennung": "u-schlaf", "label": "Schlaf", "time": "23:00", "ende": "07:00",
          "motiv": "schlaf", "rrule": "FREQ=DAILY", "seit": "2026-10-01", "layer": "rhythmus",
          "abweichungen": {"2026-10-14": {"tag": "2026-10-14", "time": "02:00"}}}
DOWN = {"kennung": "u-down", "label": "coming down", "time": "21:30", "ende": "23:00",
        "motiv": "nachthimmel", "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20261231",
        "seit": "2026-10-01", "layer": "rhythmus"}


def _feld(f, name):
    return next(x for x in f.felder if x.name == name)


def _waehle(f, name, wert):
    x = _feld(f, name)
    x.wahl = x.optionen.index(wert)


def _liste(phasen=(SCHLAF, DOWN)):
    return kp.PhasenListe(list(phasen), MOTIVE, TAG, HEUTE, zurueck=lambda: "LISTE")


# ── Regeln ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("rrule,wied,alle,wtage,bis", [
    ("FREQ=DAILY", "täglich", "1", "", ""),
    ("FREQ=DAILY;INTERVAL=2", "täglich", "2", "", ""),
    ("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "werktags", "1", "", ""),
    ("FREQ=WEEKLY;BYDAY=SA,SU;UNTIL=20261231", "wochenende", "1", "", "31.12.2026"),
    ("FREQ=WEEKLY;BYDAY=MO,WE", "an tagen", "1", "mo mi", ""),
    ("FREQ=MONTHLY;BYMONTHDAY=1", "wie bisher", "1", "", ""),
    ("FREQ=DAILY;COUNT=5", "wie bisher", "1", "", ""),
])
def test_regel_lesen(rrule, wied, alle, wtage, bis):
    assert kp.regel_lesen(rrule) == {"wied": wied, "alle": alle, "wtage": wtage, "bis": bis}


def test_regel_bauen():
    assert kp.regel_bauen("täglich") == "FREQ=DAILY"
    assert kp.regel_bauen("täglich", 3) == "FREQ=DAILY;INTERVAL=3"
    assert kp.regel_bauen("werktags") == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    assert kp.regel_bauen("an tagen", 2, ["MO", "FR"]) == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,FR"
    assert kp.regel_bauen("wie bisher") is None


# ── Liste ──────────────────────────────────────────────────────────────
def test_liste_zeigt_phasen_nach_zeit():
    zeilen = _liste().liste_zeilen()
    assert [z[2].split()[0] for z in zeilen] == ["coming", "Schlaf"]
    assert "23:00–07:00 (+1)" in zeilen[1][2] and "1 Tag anders" in zeilen[1][2]
    assert zeilen[0][3] and zeilen[0][1] == "k_m_nachthimmel"


def test_liste_tasten_oeffnen_formulare():
    li = _liste()
    assert li.taste(ord("j")) == "weiter" and li.gewaehlt is SCHLAF
    for ch, titel in ((ord("e"), "phase ändern"), (ord("t"), "nur am Mi"),
                      (ord("z"), "zeitraum"), (ord("n"), "neue phase"), (ord("d"), "löschen")):
        li = _liste()
        li.i = 1
        assert li.taste(ch) == "fertig"
        dl = li.plan()["weiter"]
        assert titel in dl.titel or titel in getattr(dl, "zeile", lambda: "")()
        assert dl.bei_abbruch() == "LISTE"            # Esc führt in die Liste
    li = _liste()
    assert li.taste(27) == "abbruch"


def test_leere_liste():
    li = _liste(())
    assert li.taste(ord("e")) == "weiter" and "n legt" in li.fehler
    assert li.taste(ord("n")) == "fertig"


# ── Formular: neu / ab jetzt ───────────────────────────────────────────
def test_neue_phase_ueber_mitternacht():
    f = kp.formular_phase(None, MOTIVE, HEUTE)
    _feld(f, "label").text = "Schlaf"
    _waehle(f, "motiv", "Schlaf")
    _feld(f, "von").text = "23"
    _feld(f, "bis").text = "7"
    assert f.taste(10) == "fertig"
    (m, pfad, body), = f.plan()["aufrufe"]
    assert (m, pfad) == ("POST", "/api/calendar/phase")
    assert body == {"label": "Schlaf", "motiv": "schlaf", "time": "23:00", "ende": "07:00",
                    "von": "2026-10-10", "rrule": "FREQ=DAILY"}


def test_phase_ab_jetzt_aendern():
    f = kp.formular_phase(DOWN, MOTIVE, HEUTE)
    assert _feld(f, "wied").roh() == "werktags" and _feld(f, "bis_tag").text == "31.12.2026"
    _feld(f, "von").text = "21:00"
    _waehle(f, "wied", "an tagen")
    _feld(f, "wtage").text = "mo mi fr"
    _feld(f, "bis_tag").text = ""
    assert f.taste(10) == "fertig"
    plan = f.plan()
    (m, pfad, body), = plan["aufrufe"]
    assert (m, pfad) == ("PUT", "/api/calendar/phase")
    assert body["kennung"] == "u-down" and body["time"] == "21:00"
    assert body["rrule"] == "FREQ=WEEKLY;BYDAY=MO,WE,FR" and body["bis"] == ""
    assert body["von"] == "2026-10-01"


def test_an_tagen_ohne_tage_wird_abgelehnt():
    f = kp.formular_phase(DOWN, MOTIVE, HEUTE)
    _waehle(f, "wied", "an tagen")
    assert f.taste(10) == "weiter" and "welche tage" in f.fehler


def test_unbekannte_regel_bleibt_unangetastet():
    p = dict(DOWN, rrule="FREQ=MONTHLY;BYMONTHDAY=1")
    f = kp.formular_phase(p, MOTIVE, HEUTE)
    assert _feld(f, "wied").roh() == "wie bisher"
    assert f.taste(10) == "fertig"
    assert "rrule" not in f.plan()["aufrufe"][0][2]


# ── nur heute / Zeitraum ───────────────────────────────────────────────
def test_nur_an_einem_tag():
    f = kp.formular_tag(SCHLAF, TAG)
    assert _feld(f, "von").text == "02:00"            # die Abweichung des Tages
    _feld(f, "von").text = "21:30"
    _feld(f, "bis").text = ""
    assert f.taste(10) == "fertig"
    (m, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/routine/zeitraum"
    assert body == {"kennung": "u-schlaf", "von": "2026-10-14", "bis": "2026-10-14",
                    "time": "21:30"}


def test_drei_tage_um_zwei_ins_bett():
    f = kp.formular_zeitraum(SCHLAF, TAG, HEUTE)
    assert _feld(f, "letzter").text == "16.10.2026"
    _feld(f, "von").text = "2"
    _feld(f, "bis").text = "10"
    assert f.taste(10) == "fertig"
    body = f.plan()["aufrufe"][0][2]
    assert (body["von"], body["bis"], body["time"], body["ende"]) == (
        "2026-10-14", "2026-10-16", "02:00", "10:00")


def test_zeitraum_wieder_wie_die_regel():
    f = kp.formular_zeitraum(SCHLAF, TAG, HEUTE)
    _waehle(f, "regel", "ja")
    assert f.taste(10) == "fertig"
    body = f.plan()["aufrufe"][0][2]
    assert (body["time"], body["ende"]) == ("", "")


def test_zeitraum_verdreht():
    f = kp.formular_zeitraum(SCHLAF, TAG, HEUTE)
    _feld(f, "letzter").text = "01.10.2026"
    assert f.taste(10) == "weiter" and "vor dem ersten" in f.fehler


def test_loeschen():
    d = kp.dialog_loeschen(SCHLAF, zurueck=lambda: "LISTE")
    d.taste(ord("j"))
    plan = d.plan()
    assert plan["aufrufe"] == [("DELETE", "/api/calendar/phase", {"kennung": "u-schlaf"})]
    assert plan["zurueck"]() == "LISTE"
