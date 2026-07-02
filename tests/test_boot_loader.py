"""Tests der PUREN Blumenrauschen-Render-Funktionen (tui/boot_loader.py).

Kein TTY, kein Sync, kein Timing — nur die reinen Funktionen flower_strip /
status_line: sichtbare Breite, Determinismus, Animation, Robustheit.
"""
import re

import pytest

from tui.boot_loader import (
    flower_strip, status_line, FLOWERS, PETALS,
)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
strip = lambda s: _ANSI.sub("", s)


@pytest.mark.parametrize("width", [1, 5, 20, 40, 46, 200])
def test_sichtbare_breite_gleich_width(width):
    # Jedes gerenderte Zeichen belegt genau eine Spalte → sichtbare Länge == width.
    assert len(strip(flower_strip(width, 3))) == width


def test_breite_null_ist_leer():
    assert strip(flower_strip(0, 7)) == ""


def test_enthaelt_farbcodes_und_glyphen():
    frame = flower_strip(40, 5)
    assert "38;5;" in frame                       # 256-Farben
    glyphs = set(FLOWERS) | set(PETALS)
    assert any(g in frame for g in glyphs)        # mind. eine Blume/Blütenstaub


def test_deterministisch():
    assert flower_strip(40, 11) == flower_strip(40, 11)
    assert status_line("x", 4) == status_line("x", 4)


def test_animiert_ueber_ticks():
    # Über eine Handvoll Ticks muss sich der Streifen bewegen (nicht eingefroren).
    frames = {flower_strip(40, t) for t in range(6)}
    assert len(frames) >= 4


def test_status_line_zeigt_label_und_bluemchen():
    st = status_line("Abgleich mit PC", 2)
    assert "Abgleich mit PC" in strip(st)
    assert "✿" in st


@pytest.mark.parametrize("bad", [None, "", 0, 1, -1, 1.5, "ünî 🌸", "—" * 80])
def test_status_line_robust(bad):
    # Darf bei gemeinen Labels/Ticks nie werfen und gibt immer str zurück.
    assert isinstance(status_line(bad, 0), str)


@pytest.mark.parametrize("width", [-9, -1, 0, 1, 3, 47, 500])
@pytest.mark.parametrize("tick", [-3, 0, 1, 7, 123456])
def test_render_wirft_nie(width, tick):
    # Property: keine Argument-Kombination bringt die Render-Funktionen zu Fall.
    flower_strip(width, tick)
    status_line("Abgleich", tick)
