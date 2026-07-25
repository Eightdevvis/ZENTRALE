"""
TUI-Größencheck.

Unter dem Schwellwert (min 60x14) rendert die TUI nur den "zu klein"-Hinweis
statt des Dashboards. Dieser Test nagelt das Verhalten fest.
"""
from tui.zentrale_tui import terminal_too_small, MIN_LINES, MIN_COLS


def test_exact_minimum_is_ok():
    assert terminal_too_small(MIN_LINES, MIN_COLS) is False


def test_one_row_too_short_is_too_small():
    assert terminal_too_small(MIN_LINES - 1, MIN_COLS) is True


def test_one_col_too_narrow_is_too_small():
    assert terminal_too_small(MIN_LINES, MIN_COLS - 1) is True


def test_comfortably_large_is_ok():
    assert terminal_too_small(50, 200) is False


def test_one_line_terminal_is_too_small():
    # Der ursprüngliche Bug: bash über fast den ganzen Schirm → TUI auf 1 Zeile.
    assert terminal_too_small(1, 80) is True
