"""Bildschirm-Wahl auf einem Aussenposten: Modus und Seitenverhaeltnis.

Am Pi stand X auf 1024x768 (4:3) an einem 21:9-Panel — das Bild wurde auf die
volle Breite gezogen und sah gestreckt aus. Zwei getrennte Fragen stecken
darin: welcher Modus ist der beste, und was tun, wenn KEIN angebotener Modus
zum Panel passt.

Gerechnet wird hier ohne X: die beiden Entscheidungen sind reine Mathematik
gegen die Werte, die der Monitor per EDID meldet.
"""

import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "aussenposten_bildschirm",
    os.path.join(ROOT, "scripts", "aussenposten_bildschirm.py"))
bs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bs)

# Was der Pi wirklich angeboten bekommt (xrandr auf dem Wand-Knoten).
PI_MODI = [(1920, 1080), (1680, 1050), (1280, 1024), (1440, 900),
           (1280, 720), (1024, 768), (832, 624), (800, 600), (640, 480)]
PI_PANEL = (797, 334)          # 21:9-Ultrawide, wie er sich meldet


def test_waehlt_1080p_statt_mehr_pixel_pro_zeile():
    """1280x1024 haette mehr Pixel pro Zeile als 1280x720 — aber 5:4 an einem
    21:9-Panel sieht schlimmer aus. Seitenverhaeltnis schlaegt Pixelzahl."""
    assert bs.bester(PI_MODI, *PI_PANEL) == (1920, 1080)


def test_ohne_physische_groesse_entscheidet_die_pixelzahl():
    """Meldet der Monitor keine Masse, kann man nur noch nach Groesse gehen."""
    assert bs.bester(PI_MODI, 0, 0) == (1920, 1080)


def test_4_zu_3_panel_bekommt_4_zu_3():
    modi = [(1920, 1080), (1024, 768), (800, 600)]
    assert bs.bester(modi, 304, 228) == (1024, 768)     # 4:3-Monitor


def test_korrektur_staucht_auf_die_panelbreite():
    """Der Monitor zieht 16:9 auf 21:9 auseinander; wir stauchen vorher genau
    so weit, dass es hinterher stimmt — der Rest bleibt schwarz."""
    faktor, matrix = bs.korrektur_matrix((1920, 1080), *PI_PANEL)
    assert 0.74 < faktor < 0.75
    assert round(1920 * faktor) == 1430                 # sichtbare Breite
    assert matrix and matrix.count(",") == 8            # 3x3-Matrix
    # Die Matrix bildet Ausgabe- auf Framebuffer-Koordinaten ab: der linke
    # Rand des sichtbaren Bereichs muss auf Framebuffer-x=0 fallen.
    teile = [float(x) for x in matrix.split(",")]
    rand = 1920 * (1 - faktor) / 2
    assert abs(teile[0] * rand + teile[2]) < 1.0


def test_passendes_panel_bekommt_keine_korrektur():
    """Ein 16:9-Monitor darf nicht angefasst werden — sonst baut man die
    schwarzen Balken dort ein, wo gar nichts verzerrt war."""
    assert bs.korrektur_matrix((1920, 1080), 527, 296) == (1.0, None)


@pytest.mark.parametrize("mm", [(0, 0), (797, 0), (0, 334)])
def test_ohne_masse_keine_korrektur(mm):
    """Ohne physische Groesse laesst sich nichts ausrechnen — dann lieber
    nichts tun als raten."""
    assert bs.korrektur_matrix((1920, 1080), *mm) == (1.0, None)
