"""
Der Theme-Dienst (scripts/zentrale-themed, core/theme.py ThemeDaemon).

Er ist die EINZIGE Stelle im Projekt, die `auto` nach der Uhrzeit aufloest.
Vorher rechneten acht Stellen dieselbe 05/21-Regel selbst — vier Bash-Applier,
die TUI, nvims Lua, der Morgen-Messenger, das Tutor-Zimmer —, jede mit eigenem
Timing. Genau daran lag die Serie von Theme-Glitches: irgendein Teilnehmer lief
fuer eine Weile gegen den Rest, und jede Reparatur betraf nur die Stelle, an
der es gerade auffiel.

Getestet wird deshalb nicht nur "der Dienst rechnet richtig", sondern auch:
dass er das Ergebnis wirklich hinterlegt, dass er die Applier nur bei echtem
Farbwechsel anwirft, und dass niemand sonst die Regel noch kennt.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
import theme as T  # noqa: E402

DIENST = os.path.join(ROOT, "scripts", "zentrale-themed")


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    """Wegwerf-Dateien; Sashas echter Zustand wird nie angefasst."""
    wunsch = tmp_path / "theme"
    wunsch.write_text("auto\n")
    monkeypatch.setenv("ZENTRALE_THEME_FILE", str(wunsch))
    monkeypatch.setenv("ZENTRALE_THEME_NOW", str(tmp_path / "theme.now"))
    return wunsch, tmp_path / "theme.now"


def _daemon(gestartet):
    """ThemeDaemon, der die Applier nur protokolliert statt sie zu starten."""
    return T.ThemeDaemon(state=T.ThemeState(log_path=None),
                         runner=gestartet.append)


# ── Auflösen ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("wunsch,stunde,erwartet", [
    ("auto", 10, "day"), ("auto", 22, "night"),
    ("auto", 4, "night"), ("auto", 5, "day"),      # Grenzen
    ("auto", 20, "day"), ("auto", 21, "night"),
    ("day", 23, "day"), ("night", 12, "night"),    # feste Wuensche schlagen die Uhr
])
def test_loest_den_wunsch_auf(umgebung, wunsch, stunde, erwartet):
    w, _ = umgebung
    w.write_text(wunsch + "\n")
    assert _daemon([]).effektiv(stunde) == erwartet


def test_schreibt_das_ergebnis(umgebung):
    w, now = umgebung
    w.write_text("night\n")
    assert _daemon([]).tick() == "night"
    assert now.read_text().strip() == "night"


def test_zweiter_tick_ohne_aenderung_tut_nichts(umgebung):
    """Der Dienst wird bei jedem Wunsch geweckt — ohne Farbwechsel kein Umbau."""
    w, _ = umgebung
    w.write_text("night\n")
    gestartet = []
    d = _daemon(gestartet)
    assert d.tick() == "night"
    assert len(gestartet) == len(T.APPLIERS)
    gestartet.clear()
    assert d.tick() is None, "Applier ohne Not erneut angeworfen"
    assert gestartet == []


def test_moduswechsel_ohne_farbwechsel_faesst_nichts_an(umgebung):
    """auto(day) → day ist ein Moduswechsel, aber kein Farbwechsel.

    Das Umfaerben der XFCE-Sitzung ist teuer (jede GTK-App laedt ihre Icons
    neu). Frueher warf `t` den ganzen Desktop auch dann um, wenn die Farbe
    gleich blieb.
    """
    w, _ = umgebung
    w.write_text("day\n")
    gestartet = []
    d = _daemon(gestartet)
    d.tick()
    gestartet.clear()
    w.write_text("auto\n")            # loest tagsueber ebenfalls auf day auf
    if d.effektiv() == "day":
        assert d.tick() is None
        assert gestartet == []


def test_applier_werden_angestossen(umgebung):
    w, _ = umgebung
    w.write_text("night\n")
    gestartet = []
    _daemon(gestartet).tick()
    assert set(gestartet) == set(T.APPLIERS)
    assert "zentrale-bat-theme" in gestartet


# ── Schlafen bis zur Grenze statt pollen ──────────────────────────────────
@pytest.mark.parametrize("stunde,minute,erwartet_h", [
    (10, 0, 11),        # bis 21:00 sind es 11 h
    (22, 0, 7),         # bis 05:00 am naechsten Morgen
    (4, 30, 0),         # kurz vor der Morgen-Grenze
])
def test_schlaeft_bis_zur_naechsten_grenze(stunde, minute, erwartet_h):
    import time as _t
    jetzt = _t.struct_time((2026, 8, 18, stunde, minute, 0, 0, 230, -1))
    assert T.naechster_wechsel(jetzt) // 3600 == erwartet_h


def test_wartet_nie_null_sekunden():
    """Genau auf der Grenze darf keine enge Schleife entstehen."""
    import time as _t
    for h in (T.TAG_START, T.TAG_ENDE):
        jetzt = _t.struct_time((2026, 8, 18, h, 0, 0, 0, 230, -1))
        assert T.naechster_wechsel(jetzt) > 0


# ── Konsumenten lesen nur noch das Ergebnis ───────────────────────────────
def test_read_now_faellt_sauber_zurueck(umgebung):
    _, now = umgebung
    assert T.read_now() == "day"                 # Datei fehlt
    now.write_text("night\n")
    assert T.read_now() == "night"
    now.write_text("quatsch\n")
    assert T.read_now() == "day"
    assert T.read_now(default=None) is None


def test_niemand_sonst_kennt_die_zeitregel_noch():
    """Der eigentliche Fix: die 05/21-Regel steht an GENAU EINER Stelle.

    Frueher acht — und jede Reparatur betraf nur die, an der es gerade auffiel.
    Dieser Test ist der Waechter dagegen, dass wieder eine dazukommt.
    """
    treffer = []
    for wurzel, _, dateien in os.walk(ROOT):
        # RELATIV filtern: absolut wuerde der Test in einem Worktree unter
        # .claude/worktrees/ sein eigenes Repo ausschliessen und nichts finden.
        rel_dir = os.path.relpath(wurzel, ROOT)
        if any(teil in rel_dir.split(os.sep) for teil in
               (".git", "venv", "__pycache__", "node_modules", ".claude", "tests")):
            continue
        for name in dateien:
            if not name.endswith((".py", ".sh", ".lua", "-theme", "-themed")):
                continue
            pfad = os.path.join(wurzel, name)
            try:
                inhalt = open(pfad, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            # Sowohl die rohen Zahlen (so stand es frueher ueberall) als auch
            # die benannten Konstanten — beides darf es nur einmal geben.
            for muster in ("-ge 5 ]", "5 <= int", "h >= 5 and", "5 <= h",
                           "TAG_START"):
                if muster in inhalt:
                    treffer.append(os.path.relpath(pfad, ROOT))
                    break
    assert treffer == ["core/theme.py"], (
        "die Zeitregel steht wieder an mehreren Stellen: %s" % treffer)


# ── Das Skript selbst ─────────────────────────────────────────────────────
def test_once_schreibt_und_meldet(umgebung):
    w, now = umgebung
    w.write_text("night\n")
    r = subprocess.run([sys.executable, DIENST, "--once"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "night" in r.stdout
    assert now.read_text().strip() == "night"


def test_status_zeigt_wunsch_und_ergebnis(umgebung):
    w, _ = umgebung
    w.write_text("day\n")
    subprocess.run([sys.executable, DIENST, "--once"], capture_output=True, timeout=60)
    r = subprocess.run([sys.executable, DIENST, "--status"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert "wunsch" in r.stdout and "day" in r.stdout
    assert "ergebnis" in r.stdout
