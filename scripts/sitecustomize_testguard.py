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


def _ist_testlauf(kommandozeile, umgebung):
    """Laeuft dieser Interpreter gerade unter pytest?

    `kommandozeile` ist die VOLLSTAENDIGE Zeile (sys.orig_argv), nicht
    sys.argv. Das ist keine Feinheit, sondern der Punkt, an dem die erste
    Fassung gescheitert ist: sitecustomize laeuft beim Interpreter-START, und
    da steht bei `python -m pytest` in sys.argv[0] noch "-m" — den Modulnamen
    traegt CPython erst danach ein. Die Erkennung lief also genau im
    haeufigsten Fall ins Leere, und ein Fuzz-Lauf aus einem Worktree hat
    prompt wieder das echte Theme umgeschaltet. sys.orig_argv enthaelt die
    Zeile so, wie sie aufgerufen wurde, und deckt beide Formen ab:
    `venv/bin/pytest` wie `python -m pytest`.

    Die Env-Marker stehen trotzdem zuerst: pytest setzt sie in KINDprozessen
    (die vom Fuzzer gestartete TUI), deren eigene Kommandozeile nichts mehr
    von pytest weiss.
    """
    if umgebung.get("PYTEST_VERSION") or umgebung.get("PYTEST_CURRENT_TEST"):
        return True
    return any("pytest" in teil for teil in (kommandozeile or ()))


def _wegwerf_verzeichnis(tempdir, pid):
    return tempdir + "/zentrale_testguard_%d" % pid


def anwenden(umgebung, kommandozeile, tempdir, pid):
    """Umgebung eines Testlaufs umbiegen. → das Verzeichnis, oder None.

    Getrennt von der Ausfuehrung unten, damit der Test sie mit erfundenen
    Werten aufrufen kann, ohne einen echten Interpreter zu starten. Verlass
    dich dabei aber NICHT allein darauf: dass die Erkennung im echten
    Interpreter-Start ueberhaupt zuschlaegt, prueft nur ein Lauf mit echtem
    Subprozess (siehe tests/test_keine_seiteneffekte.py).
    """
    if not _ist_testlauf(kommandozeile, umgebung):
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
    # orig_argv statt argv: siehe _ist_testlauf. Der Fallback auf argv gilt nur
    # fuer Python < 3.10, das es hier nicht gibt.
    _ziel = anwenden(os.environ, getattr(sys, "orig_argv", None) or sys.argv,
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
