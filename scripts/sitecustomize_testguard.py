"""
sitecustomize — der Riegel, den kein Arbeitsverzeichnis umgehen kann.

WARUM DIESE DATEI AUSSERHALB DER TESTS LIEGT
--------------------------------------------
Der TUI-Fuzzer (tests/test_tui_fuzz.py) startet die echte TUI im Pseudo-Terminal
und drueckt zufaellige Tasten — darunter 't', das Theme-Zykeln. Schreibt die TUI
dabei in Sashas echte ~/.config/zentrale/theme, zieht die halbe Maschine nach:
Terminal, nvim, Browser, Desktop, bat. Im Betrieb sieht das aus wie ein
zufaelliger Glitch.

Dagegen stand der Schutz zuerst in tests/conftest.py. Das war die falsche
Stelle, und zwar aus einem Grund, der sich nicht durch Sorgfalt beheben laesst:
eine Datei IM REPO wird von jedem Worktree KOPIERT. Wer aus einem aelteren
Arbeitsverzeichnis testet, bringt die alte conftest mit — und die kennt den
Schutz nicht. Genau so ist es am 2026-08-18 um 12:58 passiert: 126 Wechsel in
19 Sekunden, ausgeloest aus einem Worktree, der ansonsten sauber isoliert war.

Das GETEILTE ist nicht das Repo, sondern der Interpreter: alle Arbeits-
verzeichnisse benutzen dasselbe venv des Haupt-Checkouts (keines hat ein
eigenes). Deshalb haengt der Riegel hier — an site-packages/sitecustomize.py,
das Python bei JEDEM Start aus diesem venv laedt, egal aus welchem Verzeichnis
und egal, wie alt dessen tests/ sind. Installiert wird er als SYMLINK auf diese
Datei (scripts/zentrale-venv-guard), damit immer der Stand aus main gilt.

Der zweite Riegel sitzt in core/theme.py (`ist_arbeitskopie`) und faengt den
Fall ab, dass jemand ohne dieses venv arbeitet.

VORSICHT BEIM AENDERN
---------------------
Dieses Modul laeuft bei JEDEM Python-Start aus dem venv — auch bei der echten
TUI, dem Backend, dem Theme-Dienst. Eine Exception hier legt alles lahm.
Deshalb: keine Importe ausser os/sys/tempfile, und der ganze Rumpf in einem
try/except, das im Zweifel schweigend nichts tut.

Getestet in tests/test_keine_seiteneffekte.py.
"""

#: Die Variablen, die einen Testlauf von der echten Maschine fernhalten.
#: Deckungsgleich mit tests/conftest.py — beide Seiten benutzen setdefault,
#: also gewinnt, wer zuerst da ist, und einzelne Tests duerfen weiterhin per
#: monkeypatch auf ihr eigenes tmp_path biegen.
_UMLENKUNG = ("ZENTRALE_THEME_FILE", "ZENTRALE_THEME_NOW",
              "XDG_CACHE_HOME", "ZENTRALE_USAGE_FILE")


def _ist_testlauf(argv0, umgebung):
    """Laeuft dieser Interpreter gerade unter pytest?

    Zwei Wege, weil beide vorkommen: `venv/bin/pytest` (argv[0] ist das
    Skript) und `python -m pytest` (argv[0] ist der Modulpfad). pytest selbst
    setzt PYTEST_VERSION erst spaeter — fuer KINDprozesse eines Testlaufs ist
    das aber schon gesetzt und der zuverlaessigere Hinweis.
    """
    if umgebung.get("PYTEST_VERSION") or umgebung.get("PYTEST_CURRENT_TEST"):
        return True
    return "pytest" in (argv0 or "")


def _wegwerf_verzeichnis(tempdir, pid):
    return tempdir + "/zentrale_testguard_%d" % pid


def anwenden(umgebung, argv0, tempdir, pid):
    """Umgebung eines Testlaufs umbiegen. → das Verzeichnis, oder None.

    Getrennt von der Ausfuehrung unten, damit der Test sie mit erfundenen
    Werten aufrufen kann, ohne einen echten Interpreter zu starten.
    """
    if not _ist_testlauf(argv0, umgebung):
        return None
    if umgebung.get("ZENTRALE_TESTLAUF"):
        # Schon umgebogen — wir sind ein KIND des Testlaufs (etwa die vom
        # Fuzzer gestartete TUI) und haben die fertigen Pfade geerbt. Ein
        # eigenes Verzeichnis waere hier nur Muell mit fremder pid im Namen.
        return None
    ziel = _wegwerf_verzeichnis(tempdir, pid)
    umgebung.setdefault("ZENTRALE_THEME_FILE", ziel + "/theme")
    umgebung.setdefault("ZENTRALE_THEME_NOW", ziel + "/theme.now")
    umgebung.setdefault("XDG_CACHE_HOME", ziel + "/cache")
    umgebung.setdefault("ZENTRALE_USAGE_FILE", ziel + "/ai_usage.json")
    # Marker: daran erkennt core/theme.py (und ein Mensch im Protokoll), dass
    # dieser Prozess zu einem Testlauf gehoert.
    umgebung["ZENTRALE_TESTLAUF"] = "1"
    return ziel


try:
    import os
    import sys
    import tempfile

    # os.environ, nicht eine Kopie: die Fuzz-TUI wird in tests/_tui_fuzz.py mit
    # env=dict(os.environ, …) gestartet und erbt die Umlenkung nur so.
    _ziel = anwenden(os.environ, sys.argv[0] if sys.argv else "",
                     tempfile.gettempdir(), os.getpid())
    if _ziel:
        os.makedirs(_ziel, exist_ok=True)

        import atexit
        import shutil

        # Nur der Prozess, der es angelegt hat, raeumt es weg — Kinder haben
        # oben schon None bekommen und fassen es nicht an.
        atexit.register(lambda: shutil.rmtree(_ziel, ignore_errors=True))
except Exception:      # noqa: BLE001 — hier ist Schweigen die richtige Antwort
    pass
