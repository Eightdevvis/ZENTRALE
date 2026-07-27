"""
Zyklus-Tönung in der Zeitachse der Graph-Überlagerung (TUI).

Geprüft wird die reine Regel (cycle_axis): WELCHE Tage markiert werden.
Das Zeichnen selbst braucht ein Terminal — die Rechnung nicht.

Wichtig ist vor allem, was cycle_axis NICHT tut: es fasst die Achse nicht an.
Die endet weiter heute und rollt tageweise weiter; getönt wird nur, was
gerade im Bild ist.

Die Vorhersage selbst kommt aus core/cycle.py (tests/test_cycle.py); hier
zählt nur, was die TUI daraus für ihre x-Achse macht.
"""
from tui.zentrale_tui import cycle_axis


def _pred(next_start, pms_from, pms_to):
    return {"graph_id": "g_periode", "next_start": next_start,
            "pms_from": pms_from, "pms_to": pms_to}


# Sashas echter Stand am 27.07.: nächste Periode 02.08., PMS 26.07.–01.08.
LIVE = _pred("2026-08-02", "2026-07-26", "2026-08-01")


def test_ohne_vorhersage_wird_nichts_markiert():
    assert cycle_axis({}) == {}
    assert cycle_axis(None) == {}


def test_muell_daten_kippen_nichts_um():
    assert cycle_axis({"next_start": "nope"}) == {}
    assert cycle_axis({"next_start": None, "pms_from": 5}) == {}


def test_alle_pms_tage_und_der_start_sind_markiert():
    marks = cycle_axis(LIVE)
    assert marks["2026-08-02"] == "next"
    assert [d for d, m in sorted(marks.items()) if m == "pms"] == [
        "2026-07-26", "2026-07-27", "2026-07-28", "2026-07-29",
        "2026-07-30", "2026-07-31", "2026-08-01"]


def test_ueberfaelliges_fenster_bleibt_markiert():
    # start lag schon → die tage liegen links von heute, werden aber getönt
    past = _pred("2026-07-20", "2026-07-13", "2026-07-19")
    marks = cycle_axis(past)
    assert marks["2026-07-20"] == "next"
    assert marks["2026-07-13"] == "pms"


def test_kaputtes_pms_fenster_laeuft_nicht_endlos():
    # pms_to weit hinter pms_from (Datenmüll) → gedeckelt, kein Hänger
    broken = _pred("2026-08-02", "2026-07-26", "2030-01-01")
    assert len(cycle_axis(broken)) <= 61
