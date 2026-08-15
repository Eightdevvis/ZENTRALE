"""
nvim-Theme-Kopplung (nvim/lua/zentrale_theme/, siehe memory/system/dashboard.md).

Getestet wird gegen ein ECHTES nvim (headless, eigene Wegwerf-Theme-Datei —
Sashas ~/.config/zentrale/theme wird nie angefasst):

  * auflösen: day → zentrale-paper, night → zentrale-cyber, auto → nach Uhrzeit
    (dieselbe 05/21-Regel wie TUI, monolith.html und der Bash-Applier)
  * LIVE-Umschalten: ein SCHON LAUFENDES nvim zieht nach, wenn sich die Datei
    ändert — das ist der ganze Zweck der Übung (nvims eigene OSC-11-Erkennung
    läuft nur beim Start)
  * Paletten-Hygiene: beide Paletten haben dieselben Schlüssel, alle Farben
    sind gültige Hex-Werte, day/night sind klar vom Terminal abgesetzt
"""
import json
import os
import shutil
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RTP = os.path.join(ROOT, "nvim")
NVIM = shutil.which("nvim")

pytestmark = pytest.mark.skipif(NVIM is None, reason="nvim nicht installiert")

# Terminal-Töne (scripts/zentrale-term-theme) — nvim soll sich davon ABSETZEN.
TERM_DAY_BG = "#fdf6e3"
TERM_NIGHT_BG = "#002b36"


def _probe(theme_file, expr):
    """nvim headless starten, setup() laufen lassen, `expr` als JSON zurück."""
    lua = (
        'local t = require("zentrale_theme"); t.setup(); '
        "io.write(vim.json.encode(%s))" % expr
    )
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    out = subprocess.run(
        [NVIM, "--headless", "-u", "NONE", "--cmd", "set rtp+=%s" % RTP,
         "-c", "lua " + lua, "-c", "q"],
        capture_output=True, text=True, env=env, timeout=30,
    ).stdout
    return json.loads(out)


def _write(path, mode):
    path.write_text(mode + "\n")


@pytest.fixture
def theme_file(tmp_path):
    f = tmp_path / "theme"
    _write(f, "auto")
    return f


# ── Auflösen ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode,scheme,bg", [
    ("day", "zentrale-paper", "light"),
    ("night", "zentrale-cyber", "dark"),
])
def test_mode_selects_scheme(theme_file, mode, scheme, bg):
    _write(theme_file, mode)
    got = _probe(theme_file, '{t.current, vim.g.colors_name, vim.o.background}')
    assert got == [mode, scheme, bg]


def test_auto_follows_clock(theme_file):
    _write(theme_file, "auto")
    expected = "day" if 5 <= time.localtime().tm_hour < 21 else "night"
    assert _probe(theme_file, "t.current") == expected


def test_missing_file_is_auto_not_crash(tmp_path):
    missing = tmp_path / "gibt-es-nicht"
    assert _probe(missing, "t.current") in ("day", "night")


def test_garbage_file_is_auto_not_crash(theme_file):
    _write(theme_file, "voelliger-muell")
    assert _probe(theme_file, "t.current") in ("day", "night")


# ── Der eigentliche Zweck: laufendes nvim zieht nach ──────────────────────
def test_running_nvim_follows_file_change(theme_file, tmp_path):
    """nvim läuft, DANN kippt das Theme — der fs_event-Watcher muss greifen."""
    sock = str(tmp_path / "nvim.sock")
    _write(theme_file, "night")
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    proc = subprocess.Popen(
        [NVIM, "--headless", "--listen", sock, "-u", "NONE",
         "--cmd", "set rtp+=%s" % RTP,
         "-c", 'lua require("zentrale_theme").setup()'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    def remote(expr):
        return subprocess.run(
            [NVIM, "--headless", "--server", sock, "--remote-expr", expr],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()

    try:
        for _ in range(50):                      # auf den Serverstart warten
            if os.path.exists(sock) and remote('luaeval("1")') == "1":
                break
            time.sleep(0.1)
        assert remote('luaeval(\'require("zentrale_theme").current\')') == "night"

        _write(theme_file, "day")                # ← der Moduswechsel in der TUI
        got = None
        for _ in range(50):                      # Watcher darf kurz brauchen
            got = remote('luaeval(\'require("zentrale_theme").current\')')
            if got == "day":
                break
            time.sleep(0.1)
        assert got == "day", "laufendes nvim hat den Wechsel nicht mitbekommen"
        # und die Farben hängen wirklich um (nicht nur die Variable)
        bg = remote('luaeval(\'string.format("#%06x",'
                    ' vim.api.nvim_get_hl(0,{name="Normal"}).bg)\')')
        assert bg == _palettes(theme_file)["paper"]["bg"]
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_timer_catches_change_without_watcher(tmp_path):
    """Fallback-Tick: fängt den Wechsel auch, wenn der Watcher nichts sieht.

    Die Theme-Datei existiert beim Start NICHT → fs_event kann sich gar nicht
    bewaffnen. Nur der periodische Tick kann den Wechsel dann noch bemerken —
    genau die Rolle, die er im auto-Modus um 05/21 Uhr spielt (da ändert sich
    der Dateiinhalt nämlich nie).
    """
    sock = str(tmp_path / "nvim.sock")
    later = tmp_path / "spaeter"                  # existiert noch nicht
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(later))
    proc = subprocess.Popen(
        [NVIM, "--headless", "--listen", sock, "-u", "NONE",
         "--cmd", "set rtp+=%s" % RTP,
         "-c", 'lua require("zentrale_theme").setup({interval_ms = 200})'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    def remote(expr):
        return subprocess.run(
            [NVIM, "--headless", "--server", sock, "--remote-expr", expr],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()

    try:
        for _ in range(50):
            if os.path.exists(sock) and remote('luaeval("1")') == "1":
                break
            time.sleep(0.1)
        # Ohne Datei: auto → nach Uhrzeit. Jetzt das Gegenteil erzwingen.
        start = remote('luaeval(\'require("zentrale_theme").current\')')
        _write(later, "night" if start == "day" else "day")
        got = None
        for _ in range(50):
            got = remote('luaeval(\'require("zentrale_theme").current\')')
            if got != start:
                break
            time.sleep(0.1)
        assert got != start, "Tick hat den Wechsel nicht nachgezogen"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_survives_foreign_background_change(theme_file, tmp_path):
    """nvims OSC-11-Erkennung stellt 'background' nach uns um — wir holen zurück.

    Ein Wert-Wechsel von 'background' LÖSCHT in nvim alle Highlights samt
    colors_name (verifiziert). Real passiert das beim Öffnen in einem echten
    Terminal, weil die Erkennung erst nach plugin/ greift. Hier simuliert per
    :set background=… gegen ein voll gestartetes nvim (nur da feuert OptionSet).
    """
    sock = str(tmp_path / "nvim.sock")
    _write(theme_file, "night")
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    proc = subprocess.Popen(
        [NVIM, "--headless", "--listen", sock, "-u", "NONE",
         "--cmd", "set rtp+=%s" % RTP,
         "-c", 'lua require("zentrale_theme").setup()'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    def remote(expr):
        return subprocess.run(
            [NVIM, "--headless", "--server", sock, "--remote-expr", expr],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()

    try:
        for _ in range(50):
            if os.path.exists(sock) and remote('luaeval("1")') == "1":
                break
            time.sleep(0.1)
        remote('luaeval(\'vim.o.background = "light"\')')     # der Fremdeingriff
        state = None
        for _ in range(30):
            state = remote(
                'luaeval(\'vim.g.colors_name .. " " .. vim.o.background .. " "'
                ' .. string.format("#%06x",'
                ' vim.api.nvim_get_hl(0,{name="Normal"}).bg)\')')
            if state == "zentrale-cyber dark #000000":
                break
            time.sleep(0.1)
        assert state == "zentrale-cyber dark #000000"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_session_override_ignores_file(theme_file):
    """:ZentraleTheme night erzwingt für die Sitzung, schreibt aber NICHT."""
    _write(theme_file, "day")
    lua = ('local t = require("zentrale_theme"); t.setup(); '
           'vim.cmd("ZentraleTheme night"); '
           'io.write(vim.json.encode({t.current, t.override}))')
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    out = subprocess.run(
        [NVIM, "--headless", "-u", "NONE", "--cmd", "set rtp+=%s" % RTP,
         "-c", "lua " + lua, "-c", "q"],
        capture_output=True, text=True, env=env, timeout=30,
    ).stdout
    assert json.loads(out) == ["night", "night"]
    assert theme_file.read_text().strip() == "day"   # Datei unangetastet


def test_colorscheme_command_works(theme_file):
    """:colorscheme zentrale-cyber (manuell) darf nicht in Rekursion laufen."""
    got = _probe(theme_file,
                 '(function() vim.cmd("colorscheme zentrale-cyber") '
                 'return {vim.g.colors_name, vim.o.background} end)()')
    assert got == ["zentrale-cyber", "dark"]


# ── Paletten-Hygiene ──────────────────────────────────────────────────────
def _palettes(theme_file):
    return _probe(theme_file, 'require("zentrale_theme.palettes")')


def test_both_palettes_have_same_roles(theme_file):
    p = _palettes(theme_file)
    assert set(p["cyber"]) == set(p["paper"]), "Rollen-Schlüssel driften auseinander"


def test_all_colors_are_hex(theme_file):
    p = _palettes(theme_file)
    for pal in ("cyber", "paper"):
        for key, val in p[pal].items():
            if key in ("name", "background", "comment_italic"):
                continue
            assert isinstance(val, str) and len(val) == 7 and val[0] == "#", \
                "%s.%s ist kein Hex: %r" % (pal, key, val)
            int(val[1:], 16)


def test_every_highlight_group_resolves(theme_file):
    """Keine Gruppe darf auf eine fehlende Palette-Rolle zeigen (→ leeres hl)."""
    empty = _probe(theme_file, (
        '(function() local h = require("zentrale_theme.highlights")'
        ' local p = require("zentrale_theme.palettes").cyber'
        ' local bad = {} for g, a in pairs(h.build(p)) do'
        ' if next(a) == nil then table.insert(bad, g) end end return bad end)()'))
    assert empty == {} or empty == [], "Gruppen ohne Attribute: %s" % (empty,)


def test_no_color_hint_outside_tmux(theme_file):
    """Ohne tmux gibt es nichts zu meckern — und NIE beim Start (Enter-Prompt).

    Die Farbtiefe-Warnung (tmux rundet 24-bit auf 256 → Papier wird grau) läuft
    absichtlich nur auf Abruf: eine mehrzeilige Startmeldung erzeugt in nvim
    einen "Press ENTER"-Prompt, den man bei JEDEM Öffnen wegklicken müsste.
    """
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    env.pop("TMUX", None)
    out = subprocess.run(
        [NVIM, "--headless", "-u", "NONE", "--cmd", "set rtp+=%s" % RTP,
         "-c", 'lua local t = require("zentrale_theme"); t.setup(); '
               'io.write(vim.json.encode({tostring(t.truecolor_ok()), '
               'tostring(t.color_hint()), '
               'vim.trim(vim.api.nvim_exec2("messages", {output=true}).output)}))',
         "-c", "q"],
        capture_output=True, text=True, env=env, timeout=30,
    ).stdout
    assert json.loads(out) == ["nil", "nil", ""]


def test_health_check_runs(theme_file):
    ":checkhealth zentrale_theme darf nicht selbst kaputtgehen."
    env = dict(os.environ, ZENTRALE_THEME_FILE=str(theme_file))
    r = subprocess.run(
        [NVIM, "--headless", "-u", "NORC", "--cmd", "set rtp+=%s" % RTP,
         "-c", 'lua require("zentrale_theme").setup()',
         "-c", "checkhealth zentrale_theme",
         "-c", 'lua io.write(table.concat('
               'vim.api.nvim_buf_get_lines(0, 0, -1, false), "\\n"))',
         "-c", "qa!"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert "ZENTRALE-Theme-Kopplung" in r.stdout
    assert "colorscheme zentrale-" in r.stdout


def _contrast(fg, bg):
    """WCAG-Kontrastverhältnis zweier Hex-Farben (1.0 = identisch, 21 = max)."""
    def lum(h):
        parts = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                 for c in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]
    a, b = lum(fg), lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# Code-Text muss lesbar sein (4.5:1 = WCAG AA). Kommentare dürfen zurücktreten,
# Zeilennummern noch weiter — aber nicht ins Unsichtbare. Der erste Wurf der
# Papier-Palette lag bei 2.9–4.1:1 (Blattgrün/Pollen/Moos) und war zu blass;
# dieser Test hält die Korrektur fest.
_MIN_CONTRAST = {
    "line_nr": 2.2,      # nur Orientierung, bewusst leise
    "fg_faint": 4.0,     # Kommentare: zurückgenommen, aber lesbar
    "fg_dim": 4.5,       # Operatoren, Klammern
}
_TEXT_ROLES = ("fg", "fg_dim", "fg_faint", "line_nr", "accent", "keyword",
               "string", "number", "type", "constant", "property", "special",
               "title", "error", "warn", "info", "hint", "ok")


@pytest.mark.parametrize("pal_name", ["cyber", "paper"])
def test_all_roles_are_legible_on_their_surface(theme_file, pal_name):
    pal = _palettes(theme_file)[pal_name]
    weak = []
    for role in _TEXT_ROLES:
        got = _contrast(pal[role], pal["bg"])
        need = _MIN_CONTRAST.get(role, 4.5)
        if got < need:
            weak.append("%s %s: %.2f:1 (< %.1f)" % (role, pal[role], got, need))
    assert not weak, "zu blass in %s: %s" % (pal_name, "; ".join(weak))


@pytest.mark.parametrize("pal_name", ["cyber", "paper"])
def test_text_stays_legible_on_secondary_surfaces(theme_file, pal_name):
    """Floats, CursorLine, Visual, Statuszeile: Text darf dort nicht absaufen."""
    pal = _palettes(theme_file)[pal_name]
    for surface in ("bg_alt", "bg_dim", "bg_sel", "status_bg"):
        got = _contrast(pal["fg"], pal[surface])
        assert got >= 4.5, "%s: Text auf %s nur %.2f:1" % (pal_name, surface, got)


def test_editor_surface_differs_from_terminal(theme_file):
    """Man soll SEHEN, dass man im Editor ist — nvim-Fläche ≠ Terminal-Fläche."""
    p = _palettes(theme_file)
    assert p["paper"]["bg"].lower() != TERM_DAY_BG
    assert p["cyber"]["bg"].lower() != TERM_NIGHT_BG
    assert p["cyber"]["bg"] == "#000000"          # cyber = ECHTES Schwarz
