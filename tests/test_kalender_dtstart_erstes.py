"""
DTSTART einer Routine = ihr erstes echtes Vorkommen (Anlass 22.10.2026).

Routinen wurden mit einem Anfang (`seit`) gespeichert, der kein Regel-Tag
ist — z. B. seit Do 22.10. bei FREQ=WEEKLY;BYDAY=MO. ZENTRALE rechnet mit
dateutil, das einen solchen Anfang stillschweigend übergeht; nach RFC 5545
ist DTSTART aber IMMER ein Vorkommen. Google und das Handy zeigten deshalb
einen Phantom-Termin am Starttag, den ZENTRALE selbst nie zeigte.

Fix in der Abbildung: DTSTART = erstes Vorkommen ab `seit`, `seit` bleibt
verlustfrei (X-ZENTRALE-SEIT, nur wenn es abweicht).
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest
from icalendar import Calendar

import kalender
import kalender_ics_abbildung as A
import kalender_regel
import kalender_speicher


def _master(kal):
    return [ev for ev in kal.walk("VEVENT") if ev.get("RECURRENCE-ID") is None][0]


def _rund(r):
    kal = A.routine_kalender(r, "u-dt")
    zurueck = A.lesen(Calendar.from_ical(kal.to_ical()))
    assert zurueck[0]["daten"] == r          # Hin und zurück verlustfrei
    return _master(kal)


# ── Abbildung ─────────────────────────────────────────────────────────

def test_woechentlich_dtstart_auf_erstem_regeltag():
    ev = _rund({"label": "ExPhy", "rrule": "FREQ=WEEKLY;BYDAY=MO", "time": "13:00",
                "ende": "14:00", "seit": "2026-10-22"})                     # Do
    assert ev["DTSTART"].dt.date() == date(2026, 10, 26)                    # Mo
    assert ev["DTSTART"].dt.hour == 13
    assert str(ev["DTSTART"].dt.tzinfo) == "Europe/Berlin"
    assert ev["DTEND"].dt.date() == date(2026, 10, 26)
    assert str(ev[A.X_SEIT]) == "2026-10-22"


def test_monatlich_dtstart_auf_erstem_regeltag():
    ev = _rund({"label": "Miete", "rrule": "FREQ=MONTHLY;BYMONTHDAY=5",
                "seit": "2026-10-22"})
    assert ev["DTSTART"].dt == date(2026, 11, 5)


def test_taeglich_mit_intervall_bleibt_auf_dem_anfang():
    # Ohne BY-Teil ist der Anfang selbst immer ein Vorkommen.
    ev = _rund({"label": "Gießen", "rrule": "FREQ=DAILY;INTERVAL=3", "time": "08:00",
                "seit": "2026-10-22"})
    assert ev["DTSTART"].dt.date() == date(2026, 10, 22)
    assert A.X_SEIT not in ev


def test_taeglich_nur_werktags():
    ev = _rund({"label": "Pendeln", "rrule": "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR",
                "time": "07:30", "seit": "2026-10-24"})                     # Sa
    assert ev["DTSTART"].dt.date() == date(2026, 10, 26)


def test_seit_auf_regeltag_unveraendert():
    ev = _rund({"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45",
                "seit": "2026-10-20"})                                      # Di
    assert ev["DTSTART"].dt.date() == date(2026, 10, 20)
    assert A.X_SEIT not in ev


def test_zweiwoechentlich_bleibt_im_selben_takt():
    r = {"label": "Tut", "rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO", "time": "10:00",
         "seit": "2026-10-22"}                                              # Do
    ev = _rund(r)
    erstes = ev["DTSTART"].dt.date()
    # dateutil (ZENTRALE) und die verschobene Regel treffen dieselben Tage
    vorher = kalender_regel.vorkommen(r, date(2026, 10, 1), date(2027, 3, 1))
    nachher = kalender_regel.vorkommen({**r, "seit": erstes.isoformat()},
                                       date(2026, 10, 1), date(2027, 3, 1))
    assert vorher == nachher and vorher[0].date() == erstes


def test_abweichungen_und_aus_bleiben():
    r = {"label": "ExPhy", "rrule": "FREQ=WEEKLY;BYDAY=FR", "time": "12:00",
         "seit": "2026-10-15", "aus": ["2026-10-30"],
         "abweichungen": {"2026-11-06": {"tag": "2026-11-05", "time": "09:00"},
                          "2026-11-13": {"entfaellt": True}}}
    kal = A.routine_kalender(r, "u-dt")
    ev = _master(kal)
    assert ev["DTSTART"].dt.date() == date(2026, 10, 16)
    rids = sorted(k["RECURRENCE-ID"].dt.date() for k in kal.walk("VEVENT")
                  if k.get("RECURRENCE-ID") is not None)
    assert rids == [date(2026, 11, 6), date(2026, 11, 13)]
    ex = [v.dt.date() for liste in A._liste(ev.get("EXDATE")) for v in liste.dts]
    assert ex == [date(2026, 10, 30)]
    assert A.lesen(Calendar.from_ical(kal.to_ical()))[0]["daten"] == r


def test_fremd_verschobene_serie_vergisst_alten_anfang():
    """Wird die Serie außerhalb verschoben (DTSTART passt nicht mehr zu
    X-ZENTRALE-SEIT), gilt DTSTART."""
    kal = A.routine_kalender({"label": "X", "rrule": "FREQ=WEEKLY;BYDAY=MO",
                              "time": "13:00", "seit": "2026-10-22"}, "u-dt")
    roh = kal.to_ical().replace(b"20261026T13", b"20261102T13")
    daten = A.lesen(Calendar.from_ical(roh))[0]["daten"]
    assert daten["seit"] == "2026-11-02"


# ── Speicher: ZENTRALE-Ansicht unverändert ────────────────────────────

@pytest.mark.kalender_beide
def test_ansicht_identisch_und_seit_bleibt(tmp_path, monkeypatch,
                                           _kalender_speicher_art):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    assert kalender.add_routine("termine", "ExPhy Tutorium", "FREQ=WEEKLY;BYDAY=FR",
                                time="12:00", ende="14:00", seit="2026-10-15")
    tage = kalender.entries_in_range(date(2026, 10, 12), date(2026, 11, 8))
    assert sorted(tage) == ["2026-10-16", "2026-10-23", "2026-10-30", "2026-11-06"]
    _l, _i, r = kalender.routine_finden("ExPhy")[0]
    assert r["seit"] == "2026-10-15"
    if _kalender_speicher_art == "ics":
        vdir = kalender_speicher.pfade(kalender.CAL_PATH)["vdir"]
        (datei,) = list(vdir.rglob("*.ics"))
        ev = _master(Calendar.from_ical(datei.read_bytes()))
        assert ev["DTSTART"].dt.date() == date(2026, 10, 16)


@pytest.mark.kalender_beide
def test_regel_aendern_rechnet_vom_echten_anfang(tmp_path, monkeypatch):
    """`seit` bleibt der gewählte Tag: wird die Regel auf Donnerstag geändert,
    ist der Do 15.10. das erste Vorkommen."""
    import kalender_kennung
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_routine("termine", "Tut", "FREQ=WEEKLY;BYDAY=FR",
                         time="12:00", seit="2026-10-15")
    (k,) = [e["kennung"] for e in kalender_kennung.alle_eintraege() if e.get("label") == "Tut"]
    kalender_kennung.routine_aendern(k, rrule="FREQ=WEEKLY;BYDAY=TH")
    tage = kalender.entries_in_range(date(2026, 10, 12), date(2026, 10, 25))
    assert sorted(tage) == ["2026-10-15", "2026-10-22"]
