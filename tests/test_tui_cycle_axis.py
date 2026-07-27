"""
Zyklus-Tönung in der Zeitachse der Graph-Überlagerung (TUI).

Geprüft wird die reine Regel (cycle_axis): WIE WEIT die Achse für die
Vorhersage in die Zukunft wachsen darf und WELCHE Tage markiert werden.
Das Zeichnen selbst braucht ein Terminal — die Rechnung nicht.

Die Vorhersage selbst kommt aus core/cycle.py (tests/test_cycle.py); hier
zählt nur, was die TUI daraus für ihre x-Achse macht.
"""
from datetime import date

from tui.zentrale_tui import cycle_axis


def _pred(next_start, pms_from, pms_to):
    return {"graph_id": "g_periode", "next_start": next_start,
            "pms_from": pms_from, "pms_to": pms_to}


TODAY = date(2026, 7, 27)
# Sashas echter Stand am 27.07.: nächste Periode 02.08., PMS 26.07.–01.08.
LIVE = _pred("2026-08-02", "2026-07-26", "2026-08-01")


def test_ohne_vorhersage_bleibt_die_achse_wie_sie_war():
    assert cycle_axis({}, TODAY, 60) == (0, {})
    assert cycle_axis(None, TODAY, 60) == (0, {})


def test_muell_daten_kippen_nichts_um():
    assert cycle_axis({"next_start": "nope"}, TODAY, 60) == (0, {})
    assert cycle_axis({"next_start": None, "pms_from": 5}, TODAY, 60) == (0, {})


def test_alle_pms_tage_und_der_start_sind_markiert():
    fut, marks = cycle_axis(LIVE, TODAY, 60)
    assert marks["2026-08-02"] == "next"
    assert [d for d, m in sorted(marks.items()) if m == "pms"] == [
        "2026-07-26", "2026-07-27", "2026-07-28", "2026-07-29",
        "2026-07-30", "2026-07-31", "2026-08-01"]


def test_breite_achse_reicht_bis_zum_erwarteten_start():
    # 6 tage voraus, ein drittel von 60 = 20 → passt
    assert cycle_axis(LIVE, TODAY, 60)[0] == 6


def test_schmale_achse_zeigt_lieber_nichts_als_ein_halbes_fenster():
    # ein drittel von 12 = 4 < 6 → gar nicht wachsen (ganz oder gar nicht)
    assert cycle_axis(LIVE, TODAY, 12)[0] == 0
    # die marken bleiben trotzdem stehen: was schon im fenster liegt (heute,
    # gestern) wird getönt, nur die zukunft fehlt.
    assert cycle_axis(LIVE, TODAY, 12)[1]["2026-07-27"] == "pms"


def test_genau_passend_zaehlt_noch_als_passend():
    assert cycle_axis(LIVE, TODAY, 18)[0] == 6      # 18 // 3 == 6


def test_ueberfaellig_braucht_keinen_platz():
    # start lag schon → liegt links von heute, die achse wächst nicht
    past = _pred("2026-07-20", "2026-07-13", "2026-07-19")
    fut, marks = cycle_axis(past, TODAY, 60)
    assert fut == 0
    assert marks["2026-07-20"] == "next"


def test_start_heute_waechst_nicht():
    now = _pred("2026-07-27", "2026-07-20", "2026-07-26")
    assert cycle_axis(now, TODAY, 60)[0] == 0


def test_kaputtes_pms_fenster_laeuft_nicht_endlos():
    # pms_to weit hinter pms_from (Datenmüll) → gedeckelt, kein Hänger
    broken = _pred("2026-08-02", "2026-07-26", "2030-01-01")
    _fut, marks = cycle_axis(broken, TODAY, 60)
    assert len(marks) <= 61
