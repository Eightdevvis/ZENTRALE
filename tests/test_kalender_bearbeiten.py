"""
Bearbeiten wie calcurse und der Handy-Kalender (core/kalender_bearbeiten.py).

Sasha, 07.10.2026: „generell übernehm so viel du kannst von den anderen
programmen". Geprüft wird der Mechanismus hinter den Tasten — Wiederholung
mit Typ/Intervall/Ende (calcurse „r"), „nur dieser Tag" (Handy), Spannen mit
Uhrzeit pro Tag — gegen BEIDE Speicher (alte JSON und .ics).
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_bearbeiten as kb

pytestmark = pytest.mark.kalender_beide


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return kalender


def _tag(iso):
    return kalender.entries_in_range(date.fromisoformat(iso), date.fromisoformat(iso)).get(iso, [])


def _labels(iso):
    return [(e.get("label"), e.get("time"), e.get("ende")) for e in _tag(iso)
            if not e.get("deaktiviert")]


# ── Regel bauen (calcurse „r": Typ, alle wie viele, Ende) ──────────────
def test_regel_typen():
    d = date(2026, 10, 7)                                  # Mittwoch
    assert kb.regel_bauen("t", d) == "FREQ=DAILY"
    assert kb.regel_bauen("t", d, 2) == "FREQ=DAILY;INTERVAL=2"
    assert kb.regel_bauen("w", d) == "FREQ=WEEKLY;BYDAY=WE"
    assert kb.regel_bauen("w", d, wochentage=["TH", "TU"]) == "FREQ=WEEKLY;BYDAY=TU,TH"
    assert kb.regel_bauen("m", d) == "FREQ=MONTHLY;BYMONTHDAY=7"
    assert kb.regel_bauen("j", d) == "FREQ=YEARLY;BYMONTH=10;BYMONTHDAY=7"
    assert kb.regel_bauen("t", d, bis=date(2026, 10, 9)).endswith("UNTIL=20261009T235959")
    assert kb.regel_bauen("x", d) is None
    assert kb.regel_bauen("t", d, bis=date(2026, 10, 1)) is None   # Ende vor Anfang


def test_alle_zwei_tage_ab_dem_gewaehlten_tag_bis_ende(cal):
    assert kb.routine_neu("routinen", "Gießen", "2026-10-07", "t", 2,
                          bis="2026-10-13", time="08:00")
    tage = kalender.entries_in_range(date(2026, 10, 5), date(2026, 10, 20))
    an = sorted(iso for iso, es in tage.items() if any(e["label"] == "Gießen" for e in es))
    assert an == ["2026-10-07", "2026-10-09", "2026-10-11", "2026-10-13"]


def test_woechentlich_an_mehreren_tagen(cal):
    kb.routine_neu("routinen", "Geige", "2026-10-06", "w", wochentage=["TU", "TH"],
                   time="10:00", ende="11:00")
    assert ("Geige", "10:00", "11:00") in _labels("2026-10-08")
    assert ("Geige", "10:00", "11:00") in _labels("2026-10-13")
    assert not any(l == "Geige" for l, *_ in _labels("2026-10-07"))


def test_routine_traegt_ihre_regel_fuer_die_ansicht(cal):
    kb.routine_neu("routinen", "Miete", "2026-10-01", "m")
    e = _tag("2026-11-01")[0]
    assert e["recurring"] and e["rrule"] == "FREQ=MONTHLY;BYMONTHDAY=1"


# ── Routine gezielt ändern (alle Vorkommen) ────────────────────────────
@pytest.fixture
def parkour(cal):
    kb.routine_neu("routinen", "Parkour", "2026-10-07", "w", time="18:00")   # Mi
    kb.routine_neu("routinen", "Parkour", "2026-10-09", "w", time="20:00")   # Fr
    return cal


def test_aendern_trifft_nur_die_gemeinte_gleichnamige(parkour):
    assert kb.routine_bearbeiten("routinen", "Parkour", "2026-10-09", "20:00",
                                 {"time": "19:00"})
    assert ("Parkour", "19:00", None) in _labels("2026-10-16")      # Fr geändert
    assert ("Parkour", "18:00", None) in _labels("2026-10-14")      # Mi unberührt


def test_kein_teilstring_treffer(parkour):
    kb.routine_neu("routinen", "Parkour-Training", "2026-10-07", "w", time="07:00")
    kb.routine_bearbeiten("routinen", "Parkour", "2026-10-07", "18:00", {"label": "Park"})
    assert ("Parkour-Training", "07:00", None) in _labels("2026-10-14")


def test_wiederholung_aendern(parkour):
    assert kb.routine_bearbeiten("routinen", "Parkour", "2026-10-07", "18:00",
                                 {"wiederholung": {"freq": "t", "intervall": 1,
                                                   "bis": "2026-10-09"}})
    assert ("Parkour", "18:00", None) in _labels("2026-10-08")
    assert not any(t == "18:00" for _l, t, _e in _labels("2026-10-14"))


# ── Nur dieser Tag (Handy-Kalender) ────────────────────────────────────
def test_nur_dieser_tag_aendert_nur_diesen(parkour):
    assert kb.routine_abweichung("routinen", "Parkour", "2026-10-14", "18:00",
                                 {"time": "17:00", "ende": "18:30"})
    assert ("Parkour", "17:00", "18:30") in _labels("2026-10-14")
    assert ("Parkour", "18:00", None) in _labels("2026-10-21")


def test_nur_dieser_tag_verschieben(parkour):
    assert kb.routine_abweichung("routinen", "Parkour", "2026-10-14", "18:00",
                                 {"tag": "2026-10-15"})
    assert not any(t == "18:00" for _l, t, _e in _labels("2026-10-14"))
    # Ein verschobenes Vorkommen erscheint, solange sein Ursprungstag im
    # abgefragten Zeitraum liegt (Woche/Monat) — Kern-Verhalten, nicht neu.
    zwei = kalender.entries_in_range(date(2026, 10, 14), date(2026, 10, 15))
    assert any(e["label"] == "Parkour" for e in zwei.get("2026-10-15", []))
    # und das verschobene Vorkommen lässt sich am neuen Tag wieder anfassen
    assert kb.routine_abweichung("routinen", "Parkour", "2026-10-15", "18:00",
                                 {"time": "19:00"})
    zwei = kalender.entries_in_range(date(2026, 10, 14), date(2026, 10, 15))
    assert [e["time"] for e in zwei["2026-10-15"] if e["label"] == "Parkour"] == ["19:00"]


# ── Spannen ────────────────────────────────────────────────────────────
def test_durchgehende_spanne_fr_18_bis_so_14(cal):
    assert kb.spanne_neu("termine", "2026-10-09", "2026-10-11", "Berlin",
                         start_zeit="18:00", end_zeit="14:00")
    fr, sa, so = _tag("2026-10-09")[0], _tag("2026-10-10")[0], _tag("2026-10-11")[0]
    assert fr["time"] == "18:00" and fr["span_first"]
    assert "time" not in sa
    assert so["time"] == "14:00" and so["span_last"]


def test_spanne_mit_tageszeit_und_einzelnem_tag(cal):
    assert kb.spanne_neu("termine", "2026-10-07", "2026-10-09", "Messe",
                         tageszeit=("10:00", "18:00"))
    assert ("Messe", "10:00", "18:00") in _labels("2026-10-08")
    assert kb.spanne_tag("termine", "2026-10-07", "Messe", "2026-10-08", "09:00", "17:00")
    assert ("Messe", "09:00", "17:00") in _labels("2026-10-08")
    assert ("Messe", "10:00", "18:00") in _labels("2026-10-09")
    e = _tag("2026-10-08")[0]
    assert e["spanning"] and e["von"] == "2026-10-07"


def test_spanne_verschieben_nimmt_die_tageszeiten_mit(cal):
    kb.spanne_neu("termine", "2026-10-07", "2026-10-09", "Messe", tageszeit=("10:00", "18:00"))
    kb.spanne_tag("termine", "2026-10-07", "Messe", "2026-10-08", "09:00", "17:00")
    assert kb.spanne_aendern("termine", "2026-10-07", "Messe", verschieben=7)
    assert _labels("2026-10-08") == []
    assert ("Messe", "09:00", "17:00") in _labels("2026-10-15")
    assert ("Messe", "10:00", "18:00") in _labels("2026-10-16")


def test_spanne_kuerzen_wirft_ueberzaehlige_tageszeiten_weg(cal):
    kb.spanne_neu("termine", "2026-10-07", "2026-10-09", "Messe", tageszeit=("10:00", "18:00"))
    assert kb.spanne_aendern("termine", "2026-10-07", "Messe", neu_bis="2026-10-08")
    assert _labels("2026-10-09") == []
    assert ("Messe", "10:00", "18:00") in _labels("2026-10-08")


def test_unsinn_wird_abgelehnt(cal):
    assert not kb.spanne_neu("termine", "2026-10-09", "2026-10-07", "X")
    assert not kb.routine_neu("routinen", "", "2026-10-07", "t")
    assert not kb.routine_bearbeiten("routinen", "Gibtsnicht", "2026-10-07", None, {"time": "10:00"})
    assert not kb.spanne_tag("termine", "2026-10-07", "Gibtsnicht", "2026-10-07", "10:00", None)


# ── Routen ─────────────────────────────────────────────────────────────
@pytest.fixture
def client(cal):
    from ui.app import app
    app.config["TESTING"] = True
    return app.test_client()


def test_routen_wiederholung_und_konflikt(client):
    r = client.post("/api/calendar/routine", json={
        "label": "Geige", "freq": "w", "seit": "2026-10-06",
        "wochentage": ["TU", "TH"], "time": "10:00", "ende": "11:00"})
    assert r.get_json() == {"ok": True}
    k = client.post("/api/calendar/konflikte", json={
        "day": "2026-10-08", "label": "Zahnarzt", "time": "10:30", "ende": "11:30"}).get_json()
    assert k["konflikte"], "Zahnarzt 10:30–11:30 kollidiert mit Geige 10–11"
    r = client.post("/api/calendar/routine/abweichung", json={
        "label": "Geige", "day": "2026-10-08", "time": "10:00", "new": {"time": "12:00"}})
    assert r.get_json() == {"ok": True}
    k = client.post("/api/calendar/konflikte", json={
        "day": "2026-10-08", "label": "Zahnarzt", "time": "10:30", "ende": "11:30"}).get_json()
    assert k["konflikte"] == []


def test_routen_spanne(client):
    assert client.post("/api/calendar/spanne", json={
        "von": "2026-10-07", "bis": "2026-10-09", "label": "Messe",
        "tageszeit": ["10:00", "18:00"]}).get_json() == {"ok": True}
    assert client.post("/api/calendar/spanne/tag", json={
        "von": "2026-10-07", "label": "Messe", "day": "2026-10-08",
        "time": "09:00", "ende": "17:00"}).get_json() == {"ok": True}
    assert client.put("/api/calendar/spanne", json={
        "von": "2026-10-07", "label": "Messe", "new": {"label": "Buchmesse"}}).get_json() == {"ok": True}
    assert ("Buchmesse", "09:00", "17:00") in _labels("2026-10-08")
    assert client.put("/api/calendar/spanne", json={
        "von": "2026-10-07", "label": "Messe", "new": {"verschieben": "x"}}).status_code == 400
