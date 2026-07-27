"""Tests fürs Klavier-Werkzeug der TUI (die curses-freien Teile).

Drei Ebenen:
  1. Die BELEGUNG — sie muss zur Browser-Klaviatur passen (dieselben Tasten,
     dieselben Halbtöne) und die Shortcut-Lücken 'f'/'k' freilassen.
  2. Die GEOMETRIE — Notensystem und gezeichnete Klaviatur: Tonhöhe landet auf
     der richtigen Zeile, Akkorde in einer Spalte, Hilfslinien dort, wo sie
     hingehören.
  3. „Darf NIE werfen" — dieselbe Robustheits-Eigenschaft wie bei den anderen
     TUI-Helfern: gemeine Argumente dürfen die Zeichenschleife nicht killen.
"""
import random

import pytest

from tui.zentrale_tui import (
    PIANO_WHITE, PIANO_BLACK, PIANO_KEYMAP, PIANO_NAMES, PIANO_OCT_MIN,
    PIANO_OCT_MAX, PIANO_STAFF_ROWS, PIANO_TOP_DIA, PIANO_BOT_DIA,
    PIANO_CHORD_MS, PIANO_HOLLOW_MS,
    piano_dia, piano_note_name, piano_midi, piano_keyboard, piano_columns,
    piano_staff,
)


# ── 1. Belegung ─────────────────────────────────────────────────────────────
def test_klaviatur_ist_die_des_browsers():
    """Dieselben Tasten wie ui/templates/monolith.html — sonst spielt sich das
    Klavier in den zwei Fronten unterschiedlich."""
    assert [k for k, _s in PIANO_WHITE] == list("yxcvbnm,.-")
    assert [k for k, _s, _w in PIANO_BLACK] == list("sdghjlö")
    assert [s for _k, s in PIANO_WHITE] == [0, 2, 4, 5, 7, 9, 11, 12, 14, 16]
    assert [s for _k, s, _w in PIANO_BLACK] == [1, 3, 6, 8, 10, 13, 15]


def test_shortcut_luecken_bleiben_frei():
    """'f' und 'k' fallen in die Lücken E–F und H–C, wo es keine schwarze Taste
    gibt — sie müssen für Fokus bzw. Klavier-zu frei bleiben."""
    assert "f" not in PIANO_KEYMAP
    assert "k" not in PIANO_KEYMAP
    assert " " not in PIANO_KEYMAP and "r" not in PIANO_KEYMAP


def test_keine_taste_doppelt_belegt():
    tasten = [k for k, _s in PIANO_WHITE] + [k for k, _s, _w in PIANO_BLACK]
    assert len(tasten) == len(set(tasten))
    halbtoene = [s for _k, s in PIANO_WHITE] + [s for _k, s, _w in PIANO_BLACK]
    assert len(halbtoene) == len(set(halbtoene))


def test_schwarze_tasten_sitzen_zwischen_den_richtigen_weissen():
    """Die schwarze Taste mit Anker w muss genau einen Halbton über der weißen
    Taste w liegen (und einen unter deren Nachbarin)."""
    weiss = [s for _k, s in PIANO_WHITE]
    for _k, s, w in PIANO_BLACK:
        assert s == weiss[w] + 1
        assert s == weiss[w + 1] - 1


def test_alle_halbtoene_liegen_in_zwei_oktaven():
    assert min(PIANO_KEYMAP.values()) == 0
    assert max(PIANO_KEYMAP.values()) == 16


# ── 2a. Tonhöhen-Rechnung ───────────────────────────────────────────────────
@pytest.mark.parametrize("okt,semi,midi", [
    (4, 0, 60),     # mittleres C
    (4, 16, 76),    # oberste weiße Taste ('-') = E5
    (3, 0, 48), (5, 0, 72), (6, 0, 84),
])
def test_piano_midi(okt, semi, midi):
    assert piano_midi(okt, semi) == midi


@pytest.mark.parametrize("midi,name", [
    (60, "C4"), (61, "C♯4"), (69, "A4"), (71, "H4"), (72, "C5"), (48, "C3"),
])
def test_notennamen_deutsch(midi, name):
    """H statt B — Sasha liest die Zeile, nicht ein Programm."""
    assert piano_note_name(midi) == name


def test_dia_zaehlt_weisse_tasten():
    """Eine diatonische Stufe pro weißer Taste; Halbtöne teilen sich eine."""
    assert piano_dia(61) == piano_dia(60)          # C♯ sitzt auf der C-Stufe
    assert piano_dia(62) == piano_dia(60) + 1      # D eine drüber
    assert piano_dia(72) == piano_dia(60) + 7      # Oktave = 7 Stufen
    assert piano_dia(64) == PIANO_BOT_DIA          # E4 = unterste Linie
    assert piano_dia(77) == PIANO_TOP_DIA          # F5 = oberste Linie


def test_oktavgrenzen_decken_die_klaviatur_ab():
    assert PIANO_OCT_MIN < PIANO_OCT_MAX
    assert piano_midi(PIANO_OCT_MIN, 0) >= 21      # A0
    assert piano_midi(PIANO_OCT_MAX, 16) <= 108    # C8
    assert len(PIANO_NAMES) == 12


# ── 2b. Notensystem ─────────────────────────────────────────────────────────
def test_spalten_fassen_gleichzeitiges_zusammen():
    seq = [{"n": 60, "t": 0, "d": 100}, {"n": 64, "t": 20, "d": 100},
           {"n": 67, "t": 50, "d": 100}, {"n": 72, "t": 900, "d": 100}]
    cols = piano_columns(seq)
    assert [[e["n"] for e in c] for c in cols] == [[60, 64, 67], [72]]


def test_spalten_trennen_ab_der_akkord_toleranz():
    seq = [{"n": 60, "t": 0, "d": 10},
           {"n": 62, "t": PIANO_CHORD_MS + 1, "d": 10}]
    assert len(piano_columns(seq)) == 2


def test_spalten_sind_gedeckelt_und_zeigen_das_neueste():
    seq = [{"n": 60 + (i % 12), "t": i * 1000, "d": 10} for i in range(200)]
    cols = piano_columns(seq, max_cols=8)
    assert len(cols) == 8
    assert cols[-1][0]["n"] == seq[-1]["n"]


def test_spalten_ignorieren_muell():
    assert piano_columns([None, "x", {"n": None}, {"t": "spät"}, 5]) == []


def test_notensystem_hat_fuenf_linien():
    rows, _marks = piano_staff([], PIANO_STAFF_ROWS, 40)
    linien = [i for i, r in enumerate(rows) if "─" in r]
    assert len(linien) == 5
    assert linien == [0, 2, 4, 6, 8]               # jede zweite Zeile


def test_zu_flach_oder_zu_schmal_gibt_nichts_zurueck():
    assert piano_staff([], PIANO_STAFF_ROWS - 1, 40) == ([], [])
    assert piano_staff([], PIANO_STAFF_ROWS, 3) == ([], [])


def test_note_landet_auf_ihrer_zeile():
    """E4 = unterste Linie, F5 = oberste; höher = weiter oben."""
    _rows, marks = piano_staff([{"n": 64, "t": 0, "d": 100}], PIANO_STAFF_ROWS, 40)
    assert marks[0][0] == 8                        # unterste Linie
    _rows, marks = piano_staff([{"n": 77, "t": 0, "d": 100}], PIANO_STAFF_ROWS, 40)
    assert marks[0][0] == 0                        # oberste Linie


def test_hoehere_note_steht_weiter_oben():
    seq = [{"n": n, "t": 0, "d": 100} for n in (64, 67, 71)]
    _rows, marks = piano_staff(seq, PIANO_STAFF_ROWS, 40)
    zeilen = [m[0] for m in marks]
    assert zeilen == sorted(zeilen, reverse=True)  # Akkord von unten nach oben


def test_akkord_steht_in_einer_spalte():
    seq = [{"n": n, "t": 0, "d": 100} for n in (60, 64, 67)]
    _rows, marks = piano_staff(seq, 13, 40)
    assert len({m[1] for m in marks}) == 1         # eine gemeinsame x-Position
    assert len({m[0] for m in marks}) == 3         # drei verschiedene Zeilen


def test_hilfslinie_unter_dem_system_fuer_c4():
    """C4 liegt eine Stufe unter der untersten Linie → braucht eine Hilfslinie."""
    rows, marks = piano_staff([{"n": 60, "t": 0, "d": 100}], 13, 40)
    r, x, _c, _on = marks[0]
    assert rows[r][x - 1] == "─" and rows[r][x + 1] == "─"


def test_note_ausserhalb_wird_geklemmt_und_markiert():
    """Bei Oktave 3/6 liegt das Gespielte weit außerhalb des Violinschlüssels —
    dann lieber am Rand mit eigenem Kopf (◇) als unsichtbar."""
    _rows, marks = piano_staff([{"n": 24, "t": 0, "d": 100}], PIANO_STAFF_ROWS, 40)
    assert marks[0][0] == PIANO_STAFF_ROWS - 1
    assert marks[0][2] == "◇"
    _rows, marks = piano_staff([{"n": 100, "t": 0, "d": 100}], PIANO_STAFF_ROWS, 40)
    assert marks[0][0] == 0
    assert marks[0][2] == "◇"


def test_kopf_zeigt_die_laenge():
    """Voll = kurz angeschlagen, hohl = lang gehalten oder klingt noch."""
    _r, kurz = piano_staff([{"n": 64, "t": 0, "d": 100}], PIANO_STAFF_ROWS, 40)
    _r, lang = piano_staff([{"n": 64, "t": 0, "d": PIANO_HOLLOW_MS}], PIANO_STAFF_ROWS, 40)
    _r, offen = piano_staff([{"n": 64, "t": 0, "d": 0}], PIANO_STAFF_ROWS, 40)
    assert kurz[0][2] == "●"
    assert lang[0][2] == "○" and offen[0][2] == "○"


def test_kreuz_steht_vor_der_note():
    rows, marks = piano_staff([{"n": 61, "t": 0, "d": 100}], 13, 40)
    r, x, _c, _on = marks[0]
    assert rows[r][x - 1] == "♯"


def test_klingende_note_ist_markiert():
    seq = [{"n": 64, "t": 0, "d": 100}, {"n": 67, "t": 500, "d": 100}]
    _rows, marks = piano_staff(seq, PIANO_STAFF_ROWS, 40, lit={67: 1})
    an = {m[2]: m[3] for m in marks}
    assert marks[0][3] is False and marks[1][3] is True
    assert an  # (Kopf-Zeichen vorhanden)


def test_notensystem_passt_in_die_vorgegebene_flaeche():
    for h in range(PIANO_STAFF_ROWS, PIANO_STAFF_ROWS + 9):
        for w in (12, 40, 200):
            rows, marks = piano_staff([{"n": 60 + i, "t": i * 200, "d": 100}
                                       for i in range(40)], h, w)
            assert len(rows) == h
            assert all(len(r) == w for r in rows)
            assert all(0 <= r < h and 0 <= x < w for r, x, _c, _o in marks)


# ── 2c. Gezeichnete Klaviatur ───────────────────────────────────────────────
def test_klaviatur_zeichnet_alle_zehn_weissen_tasten():
    rows, zones = piano_keyboard(40)
    assert len(rows) == 5
    beschriftung = rows[3]
    for k, _s in PIANO_WHITE:
        assert k in beschriftung
    for k, _s, _w in PIANO_BLACK:
        assert k in rows[0]                        # schwarze Reihe ganz oben


def test_klaviatur_zonen_decken_jede_taste_ab():
    _rows, zones = piano_keyboard(40)
    weiss = {s for _r, _x, _w, s, black in zones if not black}
    schwarz = {s for _r, _x, _w, s, black in zones if black}
    assert weiss == {s for _k, s in PIANO_WHITE}
    assert schwarz == {s for _k, s, _w in PIANO_BLACK}


def test_schwarze_zone_liegt_zwischen_ihren_weissen():
    rows, zones = piano_keyboard(40)
    weiss = {s: x for _r, x, _w, s, black in zones if not black}
    for _r, xb, _w, s, black in zones:
        if black:
            assert weiss[s - 1] < xb <= weiss[s + 1]


def test_klaviatur_passt_immer_in_die_breite():
    for w in range(0, 120):
        rows, zones = piano_keyboard(w)
        assert all(len(r) <= w for r in rows)
        for _r, x, kw, _s, _b in zones:
            assert x + kw <= w


def test_klaviatur_schrumpft_und_gibt_bei_zu_wenig_platz_auf():
    assert piano_keyboard(41)[0] and len(piano_keyboard(41)[0][1]) == 41   # 3 breit
    assert piano_keyboard(31)[0] and len(piano_keyboard(31)[0][1]) == 31   # 2 breit
    assert piano_keyboard(20) == ([], [])                                   # zu eng


# ── 3. Darf NIE werfen ──────────────────────────────────────────────────────
NASTY = [None, True, False, 0, -1, 3, 9, 40, 10 ** 9, -10 ** 9, 0.5,
         float("nan"), float("inf"), "", "x", [], {}, b"b"]


def test_helfer_werfen_nie():
    rnd = random.Random(4711)
    muell_seq = [None, "x", 5, {}, {"n": None}, {"n": "x", "t": "y"},
                 {"n": 60}, {"n": 10 ** 9, "t": -5, "d": -1},
                 {"n": 60, "t": float("nan"), "d": None}]
    for _ in range(3000):
        seq = [rnd.choice(muell_seq) for _ in range(rnd.randint(0, 6))]
        h = rnd.choice([0, 1, 8, 9, 13, 17, 40])
        w = rnd.choice([0, 1, 5, 12, 40, 200])
        piano_staff(seq, h, w)
        piano_columns(seq, max_cols=rnd.choice([0, 1, 8, 64]))
        piano_keyboard(w)


def test_tonhoehen_helfer_werfen_bei_ganzzahlen_nie():
    for n in range(0, 128):
        piano_dia(n); piano_note_name(n)
    for okt in range(-1, 10):
        for semi in range(0, 17):
            piano_midi(okt, semi)


def test_piano_staff_ohne_noten_ist_ein_leeres_system():
    rows, marks = piano_staff([], 13, 40)
    assert marks == []
    assert any("─" in r for r in rows)
