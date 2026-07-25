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
import re
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


# ── Desktop-Applier (scripts/zentrale-desktop-theme) ──────────────────────
DESKTOP = os.path.join(ROOT, "scripts", "zentrale-desktop-theme")


def run_desktop(theme_file, *args):
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    return subprocess.run(["bash", DESKTOP, *args], capture_output=True,
                          text=True, env=env, timeout=20, check=True).stdout.strip()


@pytest.mark.parametrize("mode,gtk,wm,icons", [
    ("night", "Mint-L-Darker-Aqua", "Mint-L-Dark-Aqua", "ZENTRALE-Cyber"),
    ("day", "Mint-L-Sand", "Mint-L-Sand", "ZENTRALE-Paper"),
])
def test_desktop_theme_pair(theme_file, mode, gtk, wm, icons):
    """night = dunkelste Variante + kühler Akzent (cyber-nah),
    day = warmer Ocker (Sepia/Papier). "Darker" bringt kein xfwm4 mit,
    deshalb nachts Dark für den Rahmen. Icons: die abgeleiteten Papirus-Sets."""
    theme_file.write_text(mode + "\n")
    assert run_desktop(theme_file, "--dry-run") == \
        "%s gtk=%s wm=%s icons=%s" % (mode, gtk, wm, icons)


def test_desktop_pair_is_overridable(theme_file):
    theme_file.write_text("night\n")
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file),
               ZENTRALE_GTK_NIGHT="Eigenes-Theme", ZENTRALE_WM_NIGHT="Eigener-Rahmen")
    out = subprocess.run(["bash", DESKTOP, "--dry-run"], capture_output=True,
                         text=True, env=env, timeout=20, check=True).stdout.strip()
    assert out.startswith("night gtk=Eigenes-Theme wm=Eigener-Rahmen")


def test_desktop_themes_are_installed(theme_file):
    """Die gewählten Themes müssen es auf dieser Maschine wirklich geben —
    sonst fiele GTK stumm auf Adwaita zurück."""
    for mode in ("day", "night"):
        theme_file.write_text(mode + "\n")
        parts = dict(p.split("=", 1) for p in
                     run_desktop(theme_file, "--dry-run").split()[1:])
        assert os.path.isdir("/usr/share/themes/%s" % parts["gtk"]), parts["gtk"]
        assert os.path.isdir("/usr/share/themes/%s/xfwm4" % parts["wm"]), parts["wm"]


def test_desktop_all_appliers_share_the_clock_rule(theme_file):
    rule_files = ["zentrale-term-theme", "zentrale-browser-theme", "zentrale-desktop-theme"]
    for f in rule_files:
        src = open(os.path.join(ROOT, "scripts", f)).read()
        assert "-ge 5" in src and "-lt 21" in src, "05/21-Regel fehlt in %s" % f


# ── Terminal-Palette (scripts/zentrale-term-theme) ────────────────────────
TERM = os.path.join(ROOT, "scripts", "zentrale-term-theme")


def _term_palette(mode):
    """Die 16er-Palette + Hintergrund für einen Modus aus dem Skript ziehen."""
    src = open(TERM).read()
    block = src.split('if [ "$resolved" = "night" ]; then')[1]
    night, day = block.split("else")[0], block.split("else")[1]
    part = night if mode == "night" else day
    bg = re.search(r'BG="(#[0-9a-f]{6})"', part).group(1)
    pal = re.search(r'PALETTE="([^"]+)"', part).group(1).split(";")
    assert len(pal) == 16, "Palette muss 16 Farben haben, hat %d" % len(pal)
    return bg, pal


def _ratio(fg, bg):
    def lum(h):
        p = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        p = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in p]
        return 0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2]
    a, b = lum(fg), lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


@pytest.mark.parametrize("mode", ["night", "day"])
def test_terminal_text_colors_are_legible(mode):
    """Die echten Textfarben (1-6, 9-14) müssen auf dem eigenen Grund lesbar
    sein. Die Slots 0/7/8/15 sind Struktur (schwarz/weiß/grau) und bleiben
    per Konvention außen vor — sonst wäre "weiß auf hell" ein Fehlalarm."""
    bg, pal = _term_palette(mode)
    weak = ["%d=%s (%.2f:1)" % (i, pal[i], _ratio(pal[i], bg))
            for i in list(range(1, 7)) + list(range(9, 15))
            if _ratio(pal[i], bg) < 4.5]
    assert not weak, "zu blass in %s: %s" % (mode, ", ".join(weak))


def test_bright_colors_stand_out_more_than_normal():
    """Auf Papier muss "hell" DUNKLER sein als normal — auf hellem Grund hebt
    nur mehr Tiefe hervor. Aufgehellt lag die Reihe bei 3.1–4.2:1."""
    bg, pal = _term_palette("day")
    for i in range(1, 7):
        normal, bright = _ratio(pal[i], bg), _ratio(pal[i + 8], bg)
        assert bright > normal, \
            "Slot %d: hell %s (%.2f) hebt sich nicht ab von normal %s (%.2f)" \
            % (i + 8, pal[i + 8], bright, pal[i], normal)


def test_terminal_and_nvim_share_the_same_world():
    """Terminal und nvim gehören zur selben Welt, sind aber NICHT identisch:
    das Terminal ist die hellere Fläche, nvims Blatt die tiefere. Vollflächig
    war das nvim-Sepia im Terminal zu schwer — und der Sprung zeigt, wo der
    Editor anfängt. Nachts dagegen exakt dasselbe Schwarz."""
    nvim_pal = open(os.path.join(ROOT, "nvim", "lua", "zentrale_theme",
                                 "palettes.lua")).read()
    for mode, key in (("night", "cyber"), ("day", "paper")):
        bg, _ = _term_palette(mode)
        block = nvim_pal.split("M.%s = {" % key)[1].split("}")[0]
        nvim_bg = re.search(r'bg\s*=\s*"(#[0-9a-f]{6})"', block).group(1)
        if mode == "night":
            assert bg == nvim_bg, "night: Terminal %s vs nvim %s" % (bg, nvim_bg)
        else:
            t = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
            n = [int(nvim_bg[i:i + 2], 16) for i in (1, 3, 5)]
            assert sum(t) > sum(n), "Terminal soll heller sein als nvims Blatt"
            assert t[0] > t[2] and n[0] > n[2], "beide bleiben warm (R > B)"
