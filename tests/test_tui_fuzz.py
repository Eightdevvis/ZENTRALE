"""Bombproof-Test: die TUI darf unter KEINER Tastenfolge und KEINER
Fenstergröße abstürzen.

Jede Session startet die echte TUI im Pseudo-Terminal und feuert tausende
zufällige Tasten + Resizes rein — einmal gegen ein TOTES Backend (Offline-Pfad)
und einmal gegen ein ADVERSARIALES Backend, das absichtlich kaputte Daten
liefert (Render-Pfad). Ein „Crash" ist, wenn die TUI ihr Crash-Log schreibt;
das tut sie nur bei einer echten unbehandelten Exception.

Skalieren für einen großen Lauf (z.B. ~1000 Sessions):
    ZTUI_FUZZ_SESSIONS=500 ZTUI_FUZZ_KEYS=3000 venv/bin/python -m pytest \\
        tests/test_tui_fuzz.py
(500 Seeds × 2 Backends = 1000 Sessions.)
"""
import os
import pytest

from _tui_fuzz import run_session, AdversarialBackend, pty_supported

pytestmark = pytest.mark.skipif(
    not pty_supported(), reason="braucht Linux-PTY mit Controlling-TTY")

SESSIONS = int(os.environ.get("ZTUI_FUZZ_SESSIONS", "12"))
KEYS = int(os.environ.get("ZTUI_FUZZ_KEYS", "1500"))
SEEDS = list(range(SESSIONS))

DEAD_URL = "http://127.0.0.1:5999"   # garantiert nichts dahinter


def _assert_alive(rc, crash, frame, ctx):
    if crash:
        pytest.fail(f"TUI ABGESTÜRZT ({ctx}):\n{crash.strip()[-1500:]}")


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzz_dead_backend(seed):
    """Backend tot: tausende Tasten/Resizes, TUI muss leben UND fehlerfrei
    bleiben (offline gibt es keine Daten, die den Render stören könnten)."""
    rc, crash, frame = run_session(seed, KEYS, DEAD_URL)
    _assert_alive(rc, crash, frame, f"dead-backend seed={seed}")
    assert frame.strip() == "", \
        f"offline sollte KEINE Frame-Fehler geben, aber:\n{frame.strip()[-1500:]}"


@pytest.fixture(scope="module")
def adv_backend():
    with AdversarialBackend() as be:
        yield be


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzz_adversarial_backend(seed, adv_backend):
    """Backend liefert ~20 % bewusst kaputte Daten: die TUI darf nie sterben.
    Vom Sicherheitsnetz aufgefangene Einzelframes sind erlaubt — entscheidend
    ist, dass die Session NICHT mit einem Crash-Log endet."""
    rc, crash, frame = run_session(seed, KEYS, adv_backend.url)
    _assert_alive(rc, crash, frame, f"adversarial seed={seed}")
