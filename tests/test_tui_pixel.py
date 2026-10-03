"""Pixel-Baustein (tui/pixel.py): Zeichenwahl, Bernstein-Bauregel, Leiste."""
import pytest

from tui import pixel
from tui.pixel import (GEM, bernstein_zellen, gem, rgb_256, sextant, xterm_rgb,
                       zelle)

SCHWARZ, WEISS = (0, 0, 0), (255, 255, 255)


def test_sextanten_liegen_im_unicode_block_und_luecken_stimmen():
    assert sextant(1) == "\U0001FB00"
    assert sextant(20) == "\U0001FB13"
    assert sextant(22) == "\U0001FB14"            # 21 (= ▌) übersprungen
    assert sextant(62) == "\U0001FB3B"
    assert (sextant(0), sextant(21), sextant(42), sextant(63)) == (" ", "▌", "▐", "█")
    assert len({sextant(b) for b in range(64)}) == 64


def test_halbblock_bei_glatter_teilung():
    oben, unten = (255, 200, 0), (200, 80, 0)
    fine = [oben] * 6 + [unten] * 6               # obere 3 Zeilen / untere 3 Zeilen
    ch, fg, bg = zelle(fine)
    assert ch in ("▀", "▄")
    assert {fg, bg} == {oben, unten}


def test_feine_kante_nimmt_sextant_im_mix_aber_nie_im_half_modus():
    a, b = (255, 200, 0), SCHWARZ
    fine = [a, b, a, b, a, b, b, b, b, b, b, b]   # oben-links-Spalte 3 hoch
    assert zelle(fine)[0] not in ("▀", "▄", "█", " ")
    assert zelle(fine, "half")[0] in ("▀", "▄", "█", " ")


def test_einfarbige_zelle_ist_leer_mit_hintergrund():
    assert zelle([WEISS] * 12) == (" ", WEISS, WEISS)


def test_stein_gross_und_klein_hat_rand_tafel_und_glanz():
    g16 = gem(16, 16)
    assert g16[0][0] is None and g16[0][3] == GEM["out"]          # runde Ecke + Rand
    flat = [c for row in g16 for c in row]
    for teil in ("tabL", "tabD", "edge", "spark", "top", "right"):
        assert GEM[teil] in flat
    g8 = gem(8, 12, pixel.AY)                                      # Leistengröße im Mix
    flat8 = [c for row in g8 for c in row]
    assert GEM["spark"] in flat8 and GEM["tabD"] in flat8
    assert g8[0][0] is None


@pytest.mark.parametrize("total,breite", [(5, 40), (13, 46), (40, 46), (90, 46), (1, 3)])
def test_leiste_hat_zwei_zeilen_in_voller_breite(total, breite):
    rows = bernstein_zellen(total // 2, total, breite, SCHWARZ)
    assert len(rows) == 2 and all(len(r) == breite for r in rows)
    for r in rows:
        for ch, fg, bg in r:
            assert len(ch) == 1 and len(fg) == 3 and len(bg) == 3


def test_abgehakte_leuchten_offene_sind_blass():
    voll = bernstein_zellen(5, 5, 40, SCHWARZ)
    leer = bernstein_zellen(0, 5, 40, SCHWARZ)
    hell = lambda rows: max(sum(c[1]) + sum(c[2]) for r in rows for c in r)
    assert hell(voll) > 2 * hell(leer)


def test_leiste_ist_robust():
    assert bernstein_zellen(0, 0, 40, SCHWARZ) == []
    assert bernstein_zellen(3, 5, 0, SCHWARZ) == []
    assert bernstein_zellen("x", 5, 10, SCHWARZ) == []
    assert len(bernstein_zellen(99, 5, 30, SCHWARZ)) == 2           # done > total


def test_farbpaare_reichen_fuer_eine_leiste_in_256_farben():
    """Paare über 255 gehen nicht ins curses-Attribut — eine Leiste (inkl.
    aller Glimm-Phasen) muss mit deutlich unter 150 Paaren auskommen."""
    for bg in (SCHWARZ, WEISS):
        paare = set()
        for g in range(8):
            for r in bernstein_zellen(7, 13, 46, bg, g):
                for _ch, fg, b in r:
                    paare.add((rgb_256(fg), rgb_256(b)))
        assert len(paare) < 150


def test_xterm_hin_und_zurueck():
    for n in (16, 21, 196, 214, 231, 232, 255):
        assert rgb_256(xterm_rgb(n)) == n


# ── Elektronik-Symbol ──────────────────────────────────────────────────────
def test_elektronik_hat_feste_groesse_und_schrift_wenn_offen():
    zeilen, schrift = pixel.elektronik_zellen(1.0, 3000, "nacht")
    assert len(zeilen) == pixel.EL_H and all(len(z) == pixel.EL_W for z in zeilen)
    assert "".join(ch for _c, ch, _fg, _bg in schrift) == "ELEKTRONIK"
    platte = zeilen[pixel.EL_LABEL_ZEILE]
    for c, _ch, _fg, bg in schrift:                 # Schrift sitzt auf der Plattenfarbe
        assert platte[c] is not None and platte[c][2] == bg


def test_elektronik_zu_ist_nur_eine_linie_und_ohne_schrift():
    zeilen, schrift = pixel.elektronik_zellen(0.0, 0, "nacht")
    belegt = [r for r, z in enumerate(zeilen) if any(z)]
    assert belegt == [pixel.EL_LABEL_ZEILE] and schrift == []


def test_elektronik_klappt_von_der_mitte_auf():
    def hoehe(o):
        px = pixel.elektronik_pixel(o, 0, "nacht")
        ys = [y for y, r in enumerate(px) if any(r)]
        return ys[-1] - ys[0]
    assert hoehe(0.1) < hoehe(0.4) < hoehe(0.7) <= hoehe(1.0)


def test_elektronik_leere_zellen_bleiben_leer():
    zeilen, _ = pixel.elektronik_zellen(1.0, 3000, "tag")
    assert any(z is None for line in zeilen for z in line)     # Rad bleibt dort sichtbar
