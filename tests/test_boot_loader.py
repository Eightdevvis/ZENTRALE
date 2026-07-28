"""Tests der PUREN Blumenwind-Render-Funktionen (tui/boot_loader.py).

Kein TTY, kein Sync, kein Timing — nur die reinen Funktionen flower_field /
status_line: Feldgröße, Determinismus, Animation, Robustheit. Dazu die zwei
Eigenschaften, um die es beim Umbau ging und die man sonst nur »sieht«:
der Wind treibt LANGSAM (pro Tick wechseln nur wenige Zellen) und das Feld
bleibt LUFTIG (nicht zusammengedetscht).
"""
import re

import pytest

from tui.boot_loader import (
    flower_field, status_line, FLOWERS, SMALL_FLOWERS, PETALS,
)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
strip = lambda s: _ANSI.sub("", s)


def plain(width, height, tick, fade=1.0):
    """Feld ohne ANSI, als eine flache Zeichenkette (für Zell-Statistik)."""
    return "".join(strip(r) for r in flower_field(width, height, tick, fade))


@pytest.mark.parametrize("width", [1, 5, 20, 46, 70, 200])
@pytest.mark.parametrize("height", [1, 3, 6, 9])
def test_feldgroesse(width, height):
    # height Zeilen, jede sichtbar exakt width Spalten (jedes Zeichen 1 Spalte).
    rows = flower_field(width, height, 3)
    assert len(rows) == height
    assert all(len(strip(r)) == width for r in rows)


def test_breite_null_ist_leer():
    assert all(strip(r) == "" for r in flower_field(0, 5, 7))


def test_hoehe_null_ist_kein_feld():
    assert flower_field(40, 0, 7) == []


def test_enthaelt_farbcodes_und_glyphen():
    rows = flower_field(70, 6, 5)
    assert any("38;5;" in r for r in rows)                  # 256-Farben
    glyphs = set(FLOWERS) | set(SMALL_FLOWERS) | set(PETALS)
    assert any(g in r for r in rows for g in glyphs)        # mind. eine Blüte


def test_deterministisch():
    assert flower_field(70, 6, 11) == flower_field(70, 6, 11)
    assert status_line("x", 4) == status_line("x", 4)


def test_animiert_ueber_ticks():
    # Über 20 Ticks muss sich das Feld bewegen (nicht eingefroren).
    frames = {tuple(flower_field(70, 6, t)) for t in range(20)}
    assert len(frames) >= 10


@pytest.mark.parametrize("tick", [0, 17, 40, 123])
def test_wind_driftet_langsam(tick):
    # Kernpunkt des Umbaus: die Blüten GLEITEN (Bruchteile einer Spalte pro
    # Tick). Wechselten viele Zellen gleichzeitig, wäre es wieder das alte
    # hektische Spalten-Rauschen.
    a, b = plain(70, 6, tick), plain(70, 6, tick + 1)
    wechsel = sum(1 for x, y in zip(a, b) if (x == " ") != (y == " "))
    assert wechsel < 0.12 * len(a)


@pytest.mark.parametrize("tick", [0, 30, 90])
def test_feld_ist_luftig(tick):
    # Nicht zusammengedetscht (und auch nicht leer): grob ein Zehntel bis
    # knapp ein Drittel der Zellen trägt eine Blüte.
    a = plain(70, 6, tick)
    fill = sum(1 for ch in a if ch != " ") / float(len(a))
    assert 0.06 <= fill <= 0.30


def _maske(tick, width=70, height=6):
    """Belegungsraster (True = da sitzt eine Blüte) ohne Farben."""
    return [[ch != " " for ch in strip(r)]
            for r in flower_field(width, height, tick)]


@pytest.mark.parametrize("tick", [0, 17, 40, 123])
def test_wind_weht_nach_links(tick):
    # Richtung per Kreuzkorrelation: schiebt man das SPÄTERE Bild wieder nach
    # rechts, muss es bei einer POSITIVEN Verschiebung am besten aufs frühere
    # passen — die Blüten sind also nach links gewandert. (Der Schwerpunkt
    # taugt dafür nicht: die Blüten laufen am Rand um, er schwankt nur.)
    width, height, abstand = 70, 6, 15
    a, b = _maske(tick, width, height), _maske(tick + abstand, width, height)
    def treffer(s):
        return sum(1 for r in range(height) for c in range(width)
                   if a[r][c] and 0 <= c - s < width and b[r][c - s])
    bestes = max(range(-6, 7), key=treffer)
    assert bestes > 0


def test_fade_blendet_ein_und_aus():
    voll = plain(70, 6, 9, 1.0)
    halb = plain(70, 6, 9, 0.5)
    leer = plain(70, 6, 9, 0.0)
    zaehl = lambda s: sum(1 for ch in s if ch != " ")
    assert zaehl(leer) == 0
    assert 0 < zaehl(halb) < zaehl(voll)


def test_status_line_zeigt_label_und_bluemchen():
    st = status_line("Abgleich mit PC", 2)
    assert "Abgleich mit PC" in strip(st)
    assert "✿" in st


@pytest.mark.parametrize("bad", [None, "", 0, 1, -1, 1.5, "ünî 🌸", "—" * 80])
def test_status_line_robust(bad):
    # Darf bei gemeinen Labels/Ticks nie werfen und gibt immer str zurück.
    assert isinstance(status_line(bad, 0), str)


@pytest.mark.parametrize("width", [-9, -1, 0, 1, 3, 47, 500])
@pytest.mark.parametrize("height", [-2, 0, 1, 7])
@pytest.mark.parametrize("tick", [-3, 0, 1, 7, 123456])
@pytest.mark.parametrize("fade", [-1.0, 0.0, 0.5, 1.0, 2.0, None, "x"])
def test_render_wirft_nie(width, height, tick, fade):
    # Property: keine Argument-Kombination bringt die Render-Funktionen zu Fall.
    flower_field(width, height, tick, fade)
    status_line("Abgleich", tick)
