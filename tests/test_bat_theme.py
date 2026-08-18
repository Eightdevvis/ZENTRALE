"""
bat-Kopplung (bat/themes/, scripts/build_bat_themes.py, scripts/zentrale-bat-theme).

Getestet wird:
  * die eingecheckten .tmTheme-Dateien sind aktuell zur Palette (Drift-Waechter —
    die Farben leben in nvim/lua/zentrale_theme/palettes.lua, nicht im XML)
  * gueltiges plist, erwartete Namen, Farben wirklich aus der Palette
  * die Flaeche kommt vom TERMINAL, nicht von nvim (bewusster Unterschied:
    bat soll nahtlos in die Terminalausgabe fliessen, nvim setzt sich ab)
  * Kontrast-Waechter: jede Syntaxrolle ist auf der Terminalflaeche lesbar
  * der Applier schreibt die --theme-Zeile richtig, ersetzt statt zu doppeln,
    laesst fremde bat-Optionen in Ruhe und fasst nichts an, wenn nichts anders ist
  * echtes bat schluckt die Themes (uebersprungen, wenn bat nicht installiert)
"""
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEME_DIR = os.path.join(ROOT, "bat", "themes")
APPLIER = os.path.join(ROOT, "scripts", "zentrale-bat-theme")
BUILDER = os.path.join(ROOT, "scripts", "build_bat_themes.py")
BAT = shutil.which("batcat") or shutil.which("bat")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_bat_themes as B  # noqa: E402

# Modus → (Datei, Palette-Schluessel, Terminal-Zweig)
CASES = [("night", "zentrale-cyber.tmTheme", "cyber"),
         ("day", "zentrale-paper.tmTheme", "paper")]


def _plist(fname):
    with open(os.path.join(THEME_DIR, fname), "rb") as fh:
        return plistlib.load(fh)


def _rules(data):
    """{scope-string: settings-dict} aller Regeln mit scope."""
    return {r["scope"]: r["settings"] for r in data["settings"] if "scope" in r}


def _base(data):
    """Die eine Regel OHNE scope — Flaeche, Grundtext, Gutter."""
    for r in data["settings"]:
        if "scope" not in r:
            return r["settings"]
    raise AssertionError("keine Grundeinstellungen im Theme")


def _scope_settings(data, scope_part):
    """Settings der Regel, deren scope-Liste `scope_part` als Eintrag enthaelt."""
    for scope, settings in _rules(data).items():
        if scope_part in [s.strip() for s in scope.split(",")]:
            return settings
    raise AssertionError("scope %r in keiner Regel" % scope_part)


# ── Drift: XML muss zur Palette passen ────────────────────────────────────
def test_eingecheckte_themes_sind_aktuell():
    """Wer die Palette aendert, muss den Generator laufen lassen.

    Sonst laeuft bat still hinter nvim her — genau der Fall, fuer den es den
    Generator ueberhaupt gibt.
    """
    r = subprocess.run([sys.executable, BUILDER, "--check"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_generator_ist_deterministisch():
    assert B.render_all() == B.render_all()


# ── Struktur ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mode,fname,pal_key", CASES)
def test_ist_gueltiges_plist_mit_erwartetem_namen(mode, fname, pal_key):
    data = _plist(fname)
    assert data["name"] == fname[:-len(".tmTheme")]
    assert isinstance(data["settings"], list) and len(data["settings"]) > 10


@pytest.mark.parametrize("mode,fname,pal_key", CASES)
def test_alle_farben_sind_hex(mode, fname, pal_key):
    data = _plist(fname)
    for rule in data["settings"]:
        for key, val in rule["settings"].items():
            if key == "fontStyle":
                continue
            assert re.fullmatch(r"#[0-9a-f]{6}", val), \
                "%s: %s=%r ist kein Hex" % (fname, key, val)


@pytest.mark.parametrize("mode,fname,pal_key", CASES)
def test_syntaxfarben_kommen_aus_der_palette(mode, fname, pal_key):
    """Stichproben ueber die Rollen — kein handgemaltes XML, das driftet."""
    pal = B.read_lua_palettes()[pal_key]
    data = _plist(fname)
    for scope, rolle in (("comment", "fg_faint"), ("string", "string"),
                         ("keyword", "keyword"), ("constant.numeric", "number"),
                         ("entity.name.function", "accent"),
                         ("keyword.operator", "fg_dim"),
                         ("entity.name.type", "type")):
        assert _scope_settings(data, scope)["foreground"] == pal[rolle], \
            "%s: scope %s sollte Rolle %s tragen" % (fname, scope, rolle)


@pytest.mark.parametrize("mode,fname,pal_key", CASES)
def test_kommentare_sind_kursiv(mode, fname, pal_key):
    """Wie in nvim (palettes.lua comment_italic) — Terminal ohne Kursiv ignoriert es."""
    assert _scope_settings(_plist(fname), "comment")["fontStyle"] == "italic"


# ── Der bewusste Unterschied zu nvim: die Flaeche ─────────────────────────
@pytest.mark.parametrize("mode,fname,pal_key", CASES)
def test_flaeche_ist_die_des_terminals_nicht_die_von_nvim(mode, fname, pal_key):
    """bat soll NAHTLOS in die Terminalausgabe fliessen.

    nvim setzt sich bewusst ab (Sepia #ece0c0 gegen Terminal-Creme #f3ecd9),
    damit man sieht, dass man im Editor ist. bat ist kein Editor, sondern
    Terminalausgabe — dort waere ein abweichender Ton ein Kasten mitten im
    Scrollback. Also erbt bat Flaeche und Grundtext vom Terminal-Applier.
    """
    term = B.read_term_colors()[mode]
    pal = B.read_lua_palettes()[pal_key]
    base = _base(_plist(fname))
    assert base["background"] == term["BG"]
    assert base["foreground"] == term["FG"]
    if term["BG"] != pal["bg"]:            # im Dunkelmodus sind beide #000000
        assert base["background"] != pal["bg"], \
            "bat haette hier nvims Flaeche geerbt statt der des Terminals"


# ── Lesbarkeit auf DIESER Flaeche ─────────────────────────────────────────
def _contrast(fg, bg):
    """WCAG-Kontrastverhaeltnis zweier Hex-Farben (1.0 = identisch, 21 = max)."""
    def lum(h):
        parts = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                 for c in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]
    a, b = lum(fg), lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# Die Palette ist gegen nvims Flaeche gerechnet; hier steht sie auf der
# Terminalflaeche. Im Hellmodus ist die heller → Kontrast wird besser. Der Test
# haelt fest, dass das so bleibt. Kommentare und Zeilennummern duerfen
# zuruecktreten (wie im nvim-Test), Code-Text nicht.
_MIN = {"gutterForeground": 2.2, "comment": 4.0}


@pytest.mark.parametrize("mode,fname,pal_key", CASES)
def test_alles_ist_auf_der_terminalflaeche_lesbar(mode, fname, pal_key):
    data = _plist(fname)
    bg = _base(data)["background"]
    weak = []

    got = _contrast(_base(data)["gutterForeground"], bg)
    if got < _MIN["gutterForeground"]:
        weak.append("gutterForeground: %.2f:1" % got)

    for scope, settings in _rules(data).items():
        fg = settings.get("foreground")
        if not fg:
            continue
        need = _MIN["comment"] if scope.startswith("comment") else 4.5
        got = _contrast(fg, bg)
        if got < need:
            weak.append("%s %s: %.2f:1 (< %.1f)" % (scope.split(",")[0], fg, got, need))
    assert not weak, "zu blass in %s: %s" % (fname, "; ".join(weak))


# ── Der Applier ───────────────────────────────────────────────────────────
def _run(args, theme_file, bat_cfg):
    env = dict(os.environ, ZENTRALE_THEME_NOW=str(theme_file),
               ZENTRALE_BAT_CONFIG=str(bat_cfg))
    return subprocess.run(["bash", APPLIER] + args, capture_output=True,
                          text=True, env=env, timeout=30)


@pytest.fixture
def paths(tmp_path):
    theme = tmp_path / "theme"
    theme.write_text("auto\n")
    return theme, tmp_path / "bat" / "config"


@pytest.mark.parametrize("mode,theme", [("day", "zentrale-paper"),
                                        ("night", "zentrale-cyber")])
def test_applier_schreibt_das_passende_theme(paths, mode, theme):
    theme_file, cfg = paths
    theme_file.write_text(mode + "\n")
    assert _run([], theme_file, cfg).returncode == 0
    assert '--theme="%s"' % theme in cfg.read_text()


def test_applier_loest_auto_nach_uhrzeit_auf(paths):
    theme_file, cfg = paths
    theme_file.write_text("auto\n")
    erwartet = "day" if 5 <= time.localtime().tm_hour < 21 else "night"
    assert _run(["--resolve"], theme_file, cfg).stdout.strip() == erwartet


def test_applier_ersetzt_statt_zu_doppeln(paths):
    """Zweimal umschalten darf keine zweite --theme-Zeile hinterlassen."""
    theme_file, cfg = paths
    for mode in ("day", "night", "day"):
        theme_file.write_text(mode + "\n")
        _run([], theme_file, cfg)
    text = cfg.read_text()
    assert text.count("--theme=") == 1
    assert '--theme="zentrale-paper"' in text


def test_applier_laesst_fremde_optionen_stehen(paths):
    """Sashas eigene bat-Optionen gehen uns nichts an."""
    theme_file, cfg = paths
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('--style="numbers,changes"\n--theme="Dracula"\n--paging=never\n')
    theme_file.write_text("night\n")
    _run([], theme_file, cfg)
    text = cfg.read_text()
    assert '--style="numbers,changes"' in text
    assert "--paging=never" in text
    assert "Dracula" not in text
    assert '--theme="zentrale-cyber"' in text


def test_applier_fasst_nichts_an_wenn_nichts_anders_ist(paths):
    """Der Minutentimer darf die Datei nicht staendig neu schreiben."""
    theme_file, cfg = paths
    theme_file.write_text("night\n")
    _run([], theme_file, cfg)
    vorher = cfg.stat().st_mtime_ns
    time.sleep(0.01)
    _run([], theme_file, cfg)
    assert cfg.stat().st_mtime_ns == vorher, "Config ohne Moduswechsel neu geschrieben"


def test_applier_dry_run_schreibt_nicht(paths):
    theme_file, cfg = paths
    theme_file.write_text("day\n")
    out = _run(["--dry-run"], theme_file, cfg).stdout
    assert "zentrale-paper" in out
    assert not cfg.exists()


def test_applier_ueberlebt_fehlende_theme_datei(tmp_path):
    fehlt = tmp_path / "gibt-es-nicht"
    cfg = tmp_path / "bat" / "config"
    r = _run(["--resolve"], fehlt, cfg)
    assert r.returncode == 0
    assert r.stdout.strip() in ("day", "night")


# ── Integration: echtes bat ───────────────────────────────────────────────
@pytest.mark.skipif(BAT is None, reason="bat/batcat nicht installiert")
def test_echtes_bat_kennt_und_benutzt_die_themes(tmp_path):
    """Cache aus den eingecheckten Dateien bauen und wirklich faerben lassen.

    Laeuft komplett in tmp_path (BAT_CACHE_PATH) — Sashas bat-Cache wird nicht
    angefasst.
    """
    src, cache = tmp_path / "src", tmp_path / "cache"
    (src / "themes").mkdir(parents=True)
    cache.mkdir()
    for f in os.listdir(THEME_DIR):
        shutil.copy(os.path.join(THEME_DIR, f), src / "themes" / f)
    build = subprocess.run([BAT, "cache", "--build", "--source", str(src),
                            "--target", str(cache)],
                           capture_output=True, text=True, timeout=120)
    assert build.returncode == 0, build.stderr

    env = dict(os.environ, BAT_CACHE_PATH=str(cache))
    themes = subprocess.run([BAT, "--list-themes"], capture_output=True,
                            text=True, env=env, timeout=60).stdout
    assert "zentrale-cyber" in themes and "zentrale-paper" in themes

    probe = tmp_path / "probe.py"
    probe.write_text('# notiz\ndef f():\n    return "hallo"\n')
    pal = B.read_lua_palettes()["paper"]
    out = subprocess.run([BAT, "--color=always", "--theme=zentrale-paper",
                          "--style=plain", str(probe)],
                         capture_output=True, text=True, env=env, timeout=60).stdout

    def ansi(hexcode):
        r, g, b = (int(hexcode[i:i + 2], 16) for i in (1, 3, 5))
        return "38;2;%d;%d;%d" % (r, g, b)

    assert ansi(pal["fg_faint"]) in out, "Kommentarfarbe kam nicht an"
    assert ansi(pal["string"]) in out, "Zeichenkettenfarbe kam nicht an"
    assert ansi(pal["keyword"]) in out, "Schluesselwortfarbe kam nicht an"
