"""Zyklus-/PMS-Rechner (core/cycle.py).

Der Rechner hat keinen eigenen Speicher — er liest die Werte des »periode«-
Graphen. Getestet wird deshalb gegen eingespeiste Tage (Graph-Zugriff
gepatcht), nicht gegen echte data/-Dateien:

  1. Blockbildung: mehrere Blutungstage hintereinander sind EINE Periode
     (sonst wäre jeder Tag ein Zyklus); eine kleine Log-Lücke zerreißt sie nicht.
  2. Zykluslänge kommt aus den ECHTEN Abständen, 28 nur als Fallback.
  3. Das PMS-Fenster liegt in der Woche VOR der Vorhersage.
"""
from datetime import date

import cycle


def _days(*isos):
    return [date.fromisoformat(s) for s in isos]


def _patch(monkeypatch, days, name="periode"):
    """cycle so verdrahten, dass es genau `days` als Log-Tage sieht."""
    monkeypatch.setattr(cycle, "_find_graph",
                        lambda: {"id": "g_test", "name": name})
    monkeypatch.setattr(cycle, "_logged_days", lambda gid: sorted(days))


# ── Blockbildung ───────────────────────────────────────────────────────
def test_block_starts_faengt_nur_den_ersten_tag():
    """5 Tage am Stück = EIN Block mit einem Start."""
    d = _days("2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-11")
    assert cycle.block_starts(d) == [date(2026, 7, 7)]


def test_block_starts_trennt_zwei_perioden():
    d = _days("2026-06-11", "2026-06-12", "2026-07-07", "2026-07-08")
    assert cycle.block_starts(d) == [date(2026, 6, 11), date(2026, 7, 7)]


def test_kleine_luecke_zerreisst_den_block_nicht():
    """Ein vergessener Eintrag mitten in der Blutung (2 Tage Lücke) darf keine
    zweite Periode erfinden — BLOCK_GAP toleriert bis zu 3 Tage."""
    d = _days("2026-07-07", "2026-07-08", "2026-07-11")
    assert cycle.block_starts(d) == [date(2026, 7, 7)]


def test_grosse_luecke_ist_ein_neuer_block():
    d = _days("2026-07-07", "2026-07-12")       # 5 Tage Lücke > BLOCK_GAP
    assert cycle.block_starts(d) == [date(2026, 7, 7), date(2026, 7, 12)]


# ── Vorhersage ─────────────────────────────────────────────────────────
def test_ohne_werte_keine_vorhersage(monkeypatch):
    _patch(monkeypatch, [])
    assert cycle.predict(today=date(2026, 7, 27)) is None


def test_ohne_periode_graph_keine_vorhersage(monkeypatch):
    monkeypatch.setattr(cycle, "_find_graph", lambda: None)
    assert cycle.predict(today=date(2026, 7, 27)) is None


def test_ein_block_faellt_auf_28_zurueck(monkeypatch):
    """Noch kein echter Abstand messbar → Default-Länge, klar als solche
    gekennzeichnet (len_source), damit die Front nicht so tut, als wüsste sie's."""
    _patch(monkeypatch, _days("2026-07-07", "2026-07-08"))
    p = cycle.predict(today=date(2026, 7, 20))
    assert p["cycle_len"] == 28
    assert p["len_source"] == "default"
    assert p["next_start"] == "2026-08-04"      # 07.07. + 28


def test_laenge_kommt_aus_echten_abstaenden(monkeypatch):
    """11.06. → 07.07. = 26 Tage; die Vorhersage nimmt 26, nicht 28."""
    _patch(monkeypatch, _days("2026-06-11", "2026-06-12", "2026-07-07", "2026-07-08"))
    p = cycle.predict(today=date(2026, 7, 27))
    assert (p["cycle_len"], p["len_source"], p["n_cycles"]) == (26, "avg", 1)
    assert p["last_start"] == "2026-07-07"
    assert p["next_start"] == "2026-08-02"      # 07.07. + 26


def test_mehrere_abstaende_werden_gemittelt(monkeypatch):
    """Abstände 28 und 26 → Schnitt 27, spread nennt die Schwankung."""
    _patch(monkeypatch, _days("2026-05-14", "2026-06-11", "2026-07-07"))
    p = cycle.predict(today=date(2026, 7, 27))
    assert p["cycle_len"] == 27
    assert p["spread"] == 2
    assert p["n_cycles"] == 2


def test_pms_fenster_liegt_in_der_woche_davor(monkeypatch):
    _patch(monkeypatch, _days("2026-06-11", "2026-07-07"))
    p = cycle.predict(today=date(2026, 7, 27))
    assert p["next_start"] == "2026-08-02"
    assert p["pms_from"] == "2026-07-26"        # 7 Tage vor der Vorhersage
    assert p["pms_to"] == "2026-08-01"          # bis zum Tag davor
    assert p["phase"] == "pms"                  # 27.07. liegt drin


def test_phase_ruhig_ausserhalb_des_fensters(monkeypatch):
    _patch(monkeypatch, _days("2026-06-11", "2026-07-07"))
    assert cycle.predict(today=date(2026, 7, 20))["phase"] == "ruhig"


def test_phase_periode_waehrend_der_blutung(monkeypatch):
    _patch(monkeypatch, _days("2026-06-11", "2026-07-07", "2026-07-08"))
    assert cycle.predict(today=date(2026, 7, 8))["phase"] == "periode"


def test_ueberfaellig_wird_als_solches_gemeldet(monkeypatch):
    """Vorhersage verstrichen, nichts geloggt → negative Restzeit + Flag,
    keine stillschweigend weitergedrehte Zahl."""
    _patch(monkeypatch, _days("2026-06-11", "2026-07-07"))
    p = cycle.predict(today=date(2026, 8, 6))
    assert p["overdue"] is True
    assert p["days_to_next"] == -4
    assert p["phase"] == "ueberfaellig"
    assert "überfällig" in cycle.summary(p)


def test_unsinnige_abstaende_fliegen_raus(monkeypatch):
    """Ein Fehl-Log Jahre daneben darf die Länge nicht kapern (PLAUSIBLE)."""
    _patch(monkeypatch, _days("2019-01-01", "2026-06-11", "2026-07-07"))
    p = cycle.predict(today=date(2026, 7, 27))
    assert p["cycle_len"] == 26


# ── Tages-Marker für die Kalender-Fronten ──────────────────────────────
def test_day_marks_faerbt_pms_und_den_starttag(monkeypatch):
    _patch(monkeypatch, _days("2026-06-11", "2026-07-07"))
    p = cycle.predict(today=date(2026, 7, 27))
    marks = cycle.day_marks(date(2026, 7, 20), date(2026, 8, 10), p)
    assert marks["2026-08-02"] == "next"
    assert marks["2026-07-26"] == "pms" and marks["2026-08-01"] == "pms"
    assert "2026-07-25" not in marks             # ein Tag vor dem Fenster
    assert sum(1 for v in marks.values() if v == "pms") == 7


def test_day_marks_ausserhalb_des_zeitraums_leer(monkeypatch):
    _patch(monkeypatch, _days("2026-06-11", "2026-07-07"))
    p = cycle.predict(today=date(2026, 7, 27))
    assert cycle.day_marks(date(2026, 9, 1), date(2026, 9, 30), p) == {}


def test_day_marks_ohne_vorhersage_leer(monkeypatch):
    _patch(monkeypatch, [])
    assert cycle.day_marks(date(2026, 7, 1), date(2026, 7, 31)) == {}


# ── Einzeiler für die Fronten ──────────────────────────────────────────
def test_summary_sagt_je_phase_das_wichtigste_zuerst(monkeypatch):
    """Der Text wiederholt sich nicht (läuft PMS schon, braucht niemand mehr
    »pms ab …«) und bleibt kurz genug für die schmale TUI-Box."""
    _patch(monkeypatch, _days("2026-06-11", "2026-07-07", "2026-07-08"))
    erwartet = {
        date(2026, 7, 20): ("nächste periode 02.08.", "pms ab 26.07."),
        date(2026, 7, 27): ("pms läuft seit 26.07.", "periode ab 02.08."),
        date(2026, 7, 8): ("periode läuft seit 07.07.", "nächste ~02.08."),
        date(2026, 8, 6): ("periode überfällig seit 02.08.", "(4 t)"),
    }
    for tag, teile in erwartet.items():
        s = cycle.summary(cycle.predict(today=tag))
        for teil in teile:
            assert teil in s, (tag, s)
        assert "ø 26 t" in s                     # Länge steht immer dabei
        assert len(s) <= 60, (tag, len(s), s)    # passt in die TUI-Box
