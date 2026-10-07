"""Die Denk-Animation des Chats (tui/ansichten/denkadern.py, 2026-10-07):
reine Funktion (t, dauer, breite, hoehe, thema) → Zeichenfelder, ohne
Bildschirm geprüft."""
import time

from tui import pixel
from tui.ansichten import denkadern as D


def _lit(zeilen):
    return sum(1 for z in zeilen for f in z if f)


def _weiteste(zeilen, breite, hoehe):
    """Größter Abstand eines leuchtenden Feldes von der Mitte (in Feldern)."""
    cy, cx = hoehe / 2, breite / 2
    return max((abs(c + .5 - cx) + abs(r + .5 - cy) * 2
                for r, z in enumerate(zeilen) for c, f in enumerate(z) if f), default=0)


def test_form_und_zellen():
    z = D.adern_zellen(5.0, 5.0, 60, 12, "nacht")
    assert len(z) == 12 and all(len(r) == 60 for r in z)
    zeichen = {f[0] for r in z for f in r if f}
    assert zeichen
    # nur Sextanten/Blöcke, eine Leuchtfarbe auf dem Grund des Themas
    erlaubt = {pixel.sextant(b) for b in range(1, 64)}
    assert zeichen <= erlaubt
    assert all(f[2] == pixel.AUGE_FARBEN["nacht"]["bg"] for r in z for f in r if f)


def test_waechst_mit_der_denkdauer():
    werte = [_weiteste(D.adern_zellen(1.0, d, 80, 13), 80, 13) for d in (0.2, 3, 10, 30)]
    assert werte == sorted(werte) and werte[-1] > werte[0] * 3
    flaechen = [_lit(D.adern_zellen(1.0, d, 80, 13)) for d in (0.2, 3, 10, 30)]
    assert flaechen == sorted(flaechen)


def test_am_anfang_nur_der_kern():
    z = D.adern_zellen(0.0, 0.0, 40, 10)
    assert 0 < _lit(z) <= 4                      # ein Kern, keine Arme
    assert D.reichweite(0, 30) == 2.0 and D.reichweite(1000, 30) <= 30


def test_bleibt_in_der_flaeche():
    for b, h in ((10, 3), (30, 8), (120, 13)):
        z = D.adern_zellen(9.0, 120.0, b, h)
        assert len(z) == h and all(len(r) == b for r in z)
    assert D.adern_zellen(1, 1, 0, 0) == ()


def test_puls_wandert_und_ist_deterministisch():
    a = D.adern_zellen(20.0, 20.0, 70, 13)
    b = D.adern_zellen(21.3, 20.0, 70, 13)        # halbe Welle später
    assert a != b
    D._bild.cache_clear()
    assert D.adern_zellen(20.0, 20.0, 70, 13) == a


def test_zieht_sich_zurueck_und_verblasst():
    voll = _lit(D.adern_zellen(20.0, 20.0, 70, 13))
    halb = _lit(D.adern_zellen(20.0, 20.0, 70, 13, ausklang=0.5))
    weg = _lit(D.adern_zellen(20.0, 20.0, 70, 13, ausklang=1.0))
    assert voll > halb > weg == 0


def test_tag_und_nacht_haben_eigene_farben():
    n = {f[1] for r in D.adern_zellen(9, 9, 60, 12, "nacht") for f in r if f}
    t = {f[1] for r in D.adern_zellen(9, 9, 60, 12, "tag") for f in r if f}
    assert n and t and not (n & t)
    # wenige Farben (Pixelstil): höchstens STUFEN je Thema
    assert len(n) <= D.STUFEN and len(t) <= D.STUFEN


def test_rechnet_schnell_genug():
    """Ein Bild auf einer breiten Fläche in deutlich unter 40 ms (es wird
    höchstens BILDER_JE_S mal pro Sekunde gerechnet)."""
    t0 = time.perf_counter()
    for i in range(10):
        D._bild.cache_clear()
        D.adern_zellen(30 + i * .1, 60.0, 110, 13)
    assert (time.perf_counter() - t0) / 10 < 0.04


def test_hoehe_fuer_den_verlauf():
    assert D.hoehe_fuer(5) == 0 and D.hoehe_fuer(10) == 5 and D.hoehe_fuer(60) == 13
