"""
Import-Smoke-Test.

Der häufigste "es startet gar nicht"-Bug ist ein kaputter Import (Tippfehler,
verschobene Datei, zirkulärer Import). py_compile fängt das NICHT — es prüft nur
Syntax. Hier importieren wir jedes echte Modul einmal; ein ModuleNotFoundError
oder ein Fehler beim Modul-Toplevel fliegt sofort auf.

Bewusst NICHT importiert: services/ (zieht schwere Audio-/TTS-Engines) und die
scripts/test_*.py (Hardware-/Integrations-Skripte). Die gehören nicht zum
Startpfad des Dashboards.
"""
import importlib
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _core_modules():
    core = os.path.join(ROOT, "core")
    out = []
    for f in sorted(os.listdir(core)):
        if f.endswith(".py") and f != "__init__.py":
            out.append(f[:-3])
    return out


@pytest.mark.parametrize("mod", _core_modules())
def test_core_module_imports(mod):
    importlib.import_module(mod)


@pytest.mark.parametrize("mod", ["ui.app", "tui.zentrale_tui"])
def test_frontend_module_imports(mod):
    importlib.import_module(mod)
