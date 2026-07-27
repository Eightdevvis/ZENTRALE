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
    PIANO_CHORD_MS, PIANO_HOLLOW_MS, PIANO_BEAT_DEFAULT, PIANO_REST_GLYPH,
    piano_dia, piano_note_name, piano_midi, piano_keyboard, piano_columns,
    piano_staff, piano_beat, piano_flow,
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
    """Voll = kurz (achtel/viertel), hohl = lang (halbe/ganze). Die Länge kommt
    aus dem Abstand zum NÄCHSTEN Anschlag — das Terminal kennt kein Loslassen,
    `d` sagt darüber nichts."""
    def kopf(gap):
        seq = [{"n": 64, "t": 0, "d": 420}, {"n": 64, "t": gap, "d": 420}]
        return piano_staff(seq, PIANO_STAFF_ROWS, 40)[1][0][2]
    assert kopf(200) == "●" and kopf(600) == "●"
    assert kopf(1000) == "○" and kopf(2500) == "○"
    # die letzte Note hat noch keinen Nachfolger → offen, also hohl
    _r, offen = piano_staff([{"n": 64, "t": 0, "d": 420}], PIANO_STAFF_ROWS, 40)
    assert offen[0][2] == "○"


# ── 2b2. Grober Rhythmus: Notenlängen und Pausen ────────────────────────────
def test_notenwert_stufen_sind_grob_und_monoton():
    assert piano_beat(0) == 0 and piano_beat(100) == 0
    assert piano_beat(500) == 1
    assert piano_beat(1000) == 2
    assert piano_beat(5000) == 3
    stufen = [piano_beat(ms) for ms in range(0, 4000, 25)]
    assert stufen == sorted(stufen)                 # nie rückwärts
    for muell in (None, "x", [], {}, float("nan")):
        assert 0 <= piano_beat(muell) <= 3          # wirft nie


def test_lange_luecke_wird_zur_pause_kurze_nicht():
    schnell = piano_flow([{"n": 64, "t": 0}, {"n": 65, "t": 300}])
    assert [i[0] for i in schnell] == ["n", "n"]     # kein Pausenzeichen
    lang = piano_flow([{"n": 64, "t": 0}, {"n": 65, "t": 3000}])
    assert [i[0] for i in lang] == ["n", "p", "n"]
    # die Pause steht zwischen den beiden Noten, nicht davor oder dahinter
    assert lang[1][0] == "p" and 0 <= lang[1][1] <= 3


def test_vor_der_ersten_note_gibt_es_nie_eine_pause():
    """Auch wenn die erste Note spät kommt (t ist die Zeit seit Panel-Start)."""
    for t0 in (0, 5000, 120000):
        flow = piano_flow([{"n": 64, "t": t0}])
        assert [i[0] for i in flow] == ["n"]


def test_nach_dem_loeschen_wird_keine_pause_geschrieben():
    """Die Bedenkzeit nach der Rücktaste ist keine Musik: die Note danach trägt
    `np`, und dann entsteht aus der Lücke KEINE Pause."""
    mit = piano_flow([{"n": 64, "t": 0}, {"n": 65, "t": 9000}])
    ohne = piano_flow([{"n": 64, "t": 0}, {"n": 65, "t": 9000, "np": 1}])
    assert [i[0] for i in mit] == ["n", "p", "n"]
    assert [i[0] for i in ohne] == ["n", "n"]
    # und die Note davor wird mit der Ersatzlänge geschlossen, nicht gemessen
    assert ohne[0][2] == PIANO_BEAT_DEFAULT


def test_letzte_note_bleibt_offen_und_kriegt_ihre_laenge_erst_danach():
    eine = piano_flow([{"n": 64, "t": 0}])
    assert eine[0][2] is None                        # offen
    zwei = piano_flow([{"n": 64, "t": 0}, {"n": 65, "t": 500}])
    assert zwei[0][2] == 1 and zwei[1][2] is None    # erste geschlossen, zweite offen


def test_akkord_bleibt_eine_spalte_und_kriegt_eine_laenge():
    seq = [{"n": 60, "t": 0}, {"n": 64, "t": 20}, {"n": 67, "t": 30},
           {"n": 72, "t": 900}]
    flow = piano_flow(seq)
    assert [i[0] for i in flow] == ["n", "n"]
    assert len(flow[0][1]) == 3 and flow[0][2] == 2  # zusammen, halbe lang


def test_pause_wird_im_system_gezeichnet():
    rows, marks = piano_staff([{"n": 64, "t": 0}, {"n": 65, "t": 4000}],
                              PIANO_STAFF_ROWS, 40)
    assert any(g in "".join(rows) for g in PIANO_REST_GLYPH)
    # sie sitzt zwischen den beiden Notenköpfen
    xs = [m[1] for m in marks]
    assert xs == sorted(xs) and len(marks) == 3


def test_flow_wirft_bei_muell_nie():
    rnd = random.Random(99)
    muell = [None, "x", 5, {}, {"n": None}, {"n": 60, "t": "spät"},
             {"n": 60, "t": -10 ** 9}, {"n": 60, "t": 10 ** 9, "np": "ja"}]
    for _ in range(2000):
        seq = [rnd.choice(muell) for _ in range(rnd.randint(0, 6))]
        piano_flow(seq, max_cols=rnd.choice([0, 1, 8, 64]))


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
def test_klaviatur_beschriftet_jede_taste_mit_ihrem_buchstaben():
    rows, _zones = piano_keyboard(101, 13)
    text = "\n".join(rows)
    for k, _s in PIANO_WHITE:
        assert text.count(k) == 1
    for k, _s, _w in PIANO_BLACK:
        assert text.count(k) == 1
    # Weiße Buchstaben stehen vorne (unterste Innenzeile), schwarze weiter oben.
    weiss_zeile = max(i for i, r in enumerate(rows) if "y" in r)
    schwarz_zeile = max(i for i, r in enumerate(rows) if "s" in r)
    assert schwarz_zeile < weiss_zeile == len(rows) - 2


def test_klaviatur_zeilen_sind_alle_gleich_lang():
    for w, h in ((101, 13), (61, 9), (41, 6), (31, 5)):
        rows, _z = piano_keyboard(w, h)
        assert len(rows) == h
        assert len(set(len(r) for r in rows)) == 1


def test_klaviatur_zonen_decken_jede_taste_ab():
    _rows, zones = piano_keyboard(101, 13)
    weiss = {s for _r, _x, _w, s, black, _a in zones if not black}
    schwarz = {s for _r, _x, _w, s, black, _a in zones if black}
    assert weiss == {s for _k, s in PIANO_WHITE}
    assert schwarz == {s for _k, s, _w in PIANO_BLACK}


def test_schwarze_taste_sitzt_oben_auf_der_kante_zwischen_ihren_weissen():
    rows, zones = piano_keyboard(101, 13)
    # linke Kante jeder Taste über alle ihre Zonen
    links = {}
    rechts = {}
    for _r, x, w, s, _b, _a in zones:
        links[s] = min(links.get(s, x), x)
        rechts[s] = max(rechts.get(s, x + w), x + w)
    for _k, s, _w in PIANO_BLACK:
        # zwischen den beiden Nachbarn — und in BEIDE hineinragend, sonst säße
        # sie nicht auf der Kante, sondern daneben
        assert links[s - 1] < links[s] < links[s + 1]
        assert links[s] < rechts[s - 1] and rechts[s] > links[s + 1]
    for _k, s, _w in PIANO_BLACK:                  # reicht bis an die Hinterkante
        assert 0 in [r for r, _x, _w, ss, b, _a in zones if b and ss == s]


def test_keine_spalte_gehoert_zwei_tasten_gleichzeitig():
    for w, h in ((101, 13), (61, 9), (41, 6), (31, 5)):
        belegt = {}
        for r, x, kw, s, _b, _a in piano_keyboard(w, h)[1]:
            for c in range(x, x + kw):
                assert belegt.setdefault((r, c), s) == s
        assert belegt                              # und es ist überhaupt was da


def test_klaviatur_passt_immer_in_den_platz():
    for w in range(0, 140):
        for h in (0, 4, 5, 9, 13, 40):
            rows, zones = piano_keyboard(w, h)
            assert all(len(r) <= w for r in rows)
            assert len(rows) <= max(h, 0)
            for r, x, kw, _s, _b, _a in zones:
                assert x + kw <= w and 0 <= r < len(rows)


# ── 2d. Tastenbeleuchtung: Rahmen, Buchstaben, Flächen ──────────────────────
def test_jede_taste_hat_genau_eine_buchstaben_zelle():
    for w, h in ((101, 13), (61, 9), (41, 6), (31, 5)):
        rows, zones = piano_keyboard(w, h)
        labels = [z for z in zones if z[5] == "label"]
        assert len(labels) == len(PIANO_WHITE) + len(PIANO_BLACK)
        assert all(b == 1 for _r, _x, b, _s, _bl, _a in labels)
        # jede Buchstaben-Zelle trägt wirklich den Buchstaben dieser Taste
        namen = dict([(s, k) for k, s in PIANO_WHITE] +
                     [(s, k) for k, s, _w in PIANO_BLACK])
        for r, x, _b, s, _bl, _a in labels:
            assert rows[r][x] == namen[s]


def test_schwarze_keycap_hat_einen_rahmen_der_sie_ganz_umschliesst():
    rows, zones = piano_keyboard(101, 13)
    for _k, s, _w in PIANO_BLACK:
        cells = set()
        for r, x, b, ss, _bl, art in zones:
            if ss == s and art == "frame":
                cells |= {(r, c) for c in range(x, x + b)}
        assert cells, "breite Keycap muss einen Rahmen haben"
        rs = [r for r, _c in cells]
        cs = [c for _r, c in cells]
        # oben/unten geschlossen, links/rechts durchgehend
        top, bot, lo, hi = min(rs), max(rs), min(cs), max(cs)
        assert top == 0                                  # bis an die Hinterkante
        for c in range(lo, hi + 1):
            assert (top, c) in cells and (bot, c) in cells
        for r in range(top, bot + 1):
            assert (r, lo) in cells and (r, hi) in cells
        # und der Buchstabe sitzt INNERHALB des Rahmens, nicht darauf
        lbl = [(r, x) for r, x, _b, ss, _bl, a in zones if ss == s and a == "label"]
        assert lbl and all(top < r < bot and lo < c < hi for r, c in lbl)


def test_schmale_klaviatur_hat_keinen_rahmen_aber_alle_tasten():
    rows, zones = piano_keyboard(41, 6)              # schwarze Taste = 1 Spalte
    assert not [z for z in zones if z[5] == "frame"]
    assert {s for _r, _x, _w, s, b, _a in zones if b} == {s for _k, s, _w in PIANO_BLACK}


def test_zonen_kennen_nur_die_drei_arten():
    for w, h in ((101, 13), (61, 9), (41, 6), (31, 5)):
        assert {z[5] for z in piano_keyboard(w, h)[1]} <= {"face", "frame", "label"}


def test_klaviatur_waechst_mit_dem_platz_und_gibt_bei_zu_wenig_auf():
    breit = len(piano_keyboard(101, 9)[0][0])
    schmal = len(piano_keyboard(61, 9)[0][0])
    assert breit > schmal > 31
    assert len(piano_keyboard(101, 13)[0]) > len(piano_keyboard(101, 6)[0])
    assert piano_keyboard(101, 40)[0]                      # Höhe gedeckelt, nicht endlos
    assert len(piano_keyboard(101, 40)[0]) <= 20
    assert piano_keyboard(20, 9) == ([], [])               # zu eng
    assert piano_keyboard(101, 4) == ([], [])              # zu flach


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
        piano_keyboard(w, rnd.choice([0, 1, 5, 9, 13, 40, None, "x"]))


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
