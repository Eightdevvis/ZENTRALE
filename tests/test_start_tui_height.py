"""
Boot-Höhe der unteren bash (scripts/start_tui.sh).

Testet die ECHTE Skript-Logik (nicht eine Kopie) über den versteckten
Subcommand `--compute-boot-lines <gemerkt> <terminalhöhe>`, der die pure
Funktion compute_boot_lines() aufruft und das Ergebnis ausgibt.

Kernzusage: nach dem Split bleiben dem TUI (Pane 0) immer ≥14 Zeilen — egal
welcher Mini-/Riesenwert gemerkt wurde. Das war der Bug: ein gemerkter Wert
von 19 ließ dem TUI auf kleineren Terminals zu wenig.
"""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "start_tui.sh")
TUI_MIN = 14  # muss zu TUI_MIN_LINES im Skript / MIN_LINES in der TUI passen


def boot_lines(saved, total, env_override=None):
    env = dict(os.environ)
    env.pop("ZENTRALE_TERM_LINES", None)
    if env_override is not None:
        env["ZENTRALE_TERM_LINES"] = str(env_override)
    out = subprocess.run(
        ["bash", SCRIPT, "--compute-boot-lines", str(saved), str(total)],
        capture_output=True, text=True, env=env, check=True,
    ).stdout.strip()
    return int(out)


def tui_gets(saved, total, env_override=None):
    """Wieviele Zeilen bleiben dem TUI nach dem Split (1 Zeile Trenner)."""
    return total - boot_lines(saved, total, env_override) - 1


# ── Der eigentliche Bug-Fall + Nachbarschaft ──────────────────────────────
@pytest.mark.parametrize("total", [16, 20, 24, 30, 40, 60])
def test_tui_always_keeps_minimum(total):
    # Gemerkter Riesenwert 19 (genau der reale Bug) darf den TUI auf KEINER
    # Terminalgröße unter die Mindesthöhe drücken.
    assert tui_gets(19, total) >= TUI_MIN


def test_bug_case_24_lines():
    # Vorher bekam der TUI hier nur 4 Zeilen → "Terminal zu klein".
    assert boot_lines(19, 24) == 9
    assert tui_gets(19, 24) == TUI_MIN


def test_no_cap_when_it_fits():
    # Auf einem großen Terminal bleibt der gemerkte Wert unangetastet.
    assert boot_lines(19, 40) == 19


# ── Unter-/Obergrenzen ────────────────────────────────────────────────────
def test_lower_bound_floors_tiny_values():
    # Gemerkte 1–2 Zeilen wären beim Boot unbrauchbar → mind. 3.
    assert boot_lines(1, 80) == 3
    assert boot_lines(2, 80) == 3


def test_default_when_nothing_saved():
    assert boot_lines("", 80) == 6


def test_garbage_saved_falls_back_to_default():
    assert boot_lines("kaputt", 80) == 6


def test_huge_saved_capped():
    assert boot_lines(100, 50) == 50 - TUI_MIN - 1


def test_mini_terminal_gives_bash_one_line():
    # Terminal so klein, dass selbst 1 Zeile bash schon eng ist: bash=1.
    assert boot_lines(19, 10) == 1


def test_unknown_terminal_height_skips_cap():
    # Ohne bekannte Terminalhöhe (leer) kein Cap — nur Unter-/Default-Regeln.
    assert boot_lines(19, "") == 19


# ── Env-Override ──────────────────────────────────────────────────────────
def test_env_override_wins_when_it_fits():
    assert boot_lines(19, 80, env_override=25) == 25


def test_env_override_still_capped_for_safety():
    # Auch ein erzwungener Wert darf den TUI nicht verhungern lassen.
    assert tui_gets(19, 30, env_override=99) >= TUI_MIN
