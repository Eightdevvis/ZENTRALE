"""
Browser-Theme-Applier (scripts/zentrale-browser-theme).

Getestet wird die ECHTE Skript-Logik über die seiteneffektfreien Subcommands
`--resolve` (welcher Modus gilt) und `--dry-run` (welches Portal-Farbschema
würde gesetzt) — kein gsettings, kein Portal, keine Desktop-Änderung.

Kernzusagen: dieselbe 05/21-Regel wie überall sonst im Projekt, und night/day
landen auf prefer-dark/prefer-light (das, was Brave als Flatpak über
org.freedesktop.appearance liest).
"""
import os
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPLIER = os.path.join(ROOT, "scripts", "zentrale-browser-theme")


def run(theme_file, *args):
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    return subprocess.run(["bash", APPLIER, *args], capture_output=True,
                          text=True, env=env, timeout=20, check=True).stdout.strip()


@pytest.fixture
def theme_file(tmp_path):
    f = tmp_path / "theme"
    f.write_text("auto\n")
    return f


@pytest.mark.parametrize("mode,scheme", [
    ("night", "prefer-dark"),
    ("day", "prefer-light"),
])
def test_mode_maps_to_portal_scheme(theme_file, mode, scheme):
    theme_file.write_text(mode + "\n")
    assert run(theme_file, "--resolve") == mode
    assert run(theme_file, "--dry-run") == "%s %s" % (mode, scheme)


def test_auto_follows_clock(theme_file):
    theme_file.write_text("auto\n")
    expected = "day" if 5 <= time.localtime().tm_hour < 21 else "night"
    assert run(theme_file, "--resolve") == expected


def test_missing_file_is_auto(tmp_path):
    assert run(tmp_path / "gibt-es-nicht", "--resolve") in ("day", "night")


def test_garbage_is_auto(theme_file):
    theme_file.write_text("voelliger-muell\n")
    assert run(theme_file, "--resolve") in ("day", "night")


def test_whitespace_is_tolerated(theme_file):
    theme_file.write_text("  night  \n")
    assert run(theme_file, "--resolve") == "night"


def test_dry_run_touches_nothing(theme_file):
    """--dry-run/--resolve dürfen die Desktop-Einstellung NICHT anfassen."""
    before = subprocess.run(
        ["gsettings", "get", "org.x.apps.portal", "color-scheme"],
        capture_output=True, text=True)
    if before.returncode != 0:
        pytest.skip("kein org.x.apps.portal-Schema (kein Mint-Portal)")
    theme_file.write_text("night\n")
    run(theme_file, "--dry-run")
    run(theme_file, "--resolve")
    after = subprocess.run(
        ["gsettings", "get", "org.x.apps.portal", "color-scheme"],
        capture_output=True, text=True)
    assert after.stdout == before.stdout


def test_same_resolve_rule_as_terminal_applier(theme_file):
    """Browser- und Terminal-Applier müssen IMMER denselben Modus sehen.

    Der Terminal-Applier hat keinen --resolve-Schalter; wir vergleichen darum
    die Regel selbst: beide Skripte tragen dieselbe 05/21-Grenze im Code.
    """
    term = open(os.path.join(ROOT, "scripts", "zentrale-term-theme")).read()
    brow = open(APPLIER).read()
    for rule in ('-ge 5', '-lt 21'):
        assert rule in term and rule in brow, "05/21-Regel driftet: %s" % rule
