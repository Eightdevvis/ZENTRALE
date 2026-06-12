"""Doppel-Pane-tmux-Kassette: gezielte Szenarien + großer Fuzz-Lauf.

Deckt genau das ab, was die Python-TUI-Fuzzer NICHT anfassen: die tmux-Schicht
des Launchers (switchen, resizen, Detach-Schutz). Siehe tests/_tmux_fuzz.py.

Großlauf (der „300-Tests"-Wunsch):
    ZTMUX_FUZZ_SESSIONS=300 venv/bin/python -m pytest tests/test_tmux_panes.py -q
"""
import os
import pytest

from _tmux_fuzz import (
    PaneSession, run_fuzz_session, tmux_supported,
    PREFIX, UP, DOWN, C_UP, C_DOWN,
)

pytestmark = pytest.mark.skipif(
    not tmux_supported(), reason="braucht tmux + PTY")

SESSIONS = int(os.environ.get("ZTMUX_FUZZ_SESSIONS", "12"))
ACTIONS = int(os.environ.get("ZTMUX_FUZZ_ACTIONS", "30"))


def _switch_to(ps, payload, want, tries=20):
    """Payload feuern und warten, bis die aktive Pane == want (oder Timeout)."""
    ps.feed(payload)
    for _ in range(tries):
        ps.settle(0.03)
        if ps.state()["active"] == want:
            return True
    return False


# ── Wiring: apply-keys setzt GENAU die erwartete Belegung ────────────────────
def test_apply_keys_sets_switch_and_resize_binds():
    with PaneSession(seed=9001) as ps:
        prefix = ps._tmux("list-keys", "-T", "prefix").stdout
        root = ps._tmux("list-keys", "-T", "root").stdout
        # Switchen: Up/Down UND C-Up/C-Down liegen unter dem Prefix auf select-pane
        for key in ("Up", "Down", "C-Up", "C-Down"):
            assert any(f" {key} " in ln and "select-pane" in ln
                       for ln in prefix.splitlines()), f"prefix {key}→select-pane fehlt"
        # Resizen: C-Up/C-Down in der root-Tabelle auf resize-pane
        for key in ("C-Up", "C-Down"):
            assert any(f" {key} " in ln and "resize-pane" in ln
                       for ln in root.splitlines()), f"root {key}→resize-pane fehlt"


def test_apply_keys_disables_detach():
    with PaneSession(seed=9002) as ps:
        prefix = ps._tmux("list-keys", "-T", "prefix").stdout
        assert not any(" d " in ln and "detach" in ln for ln in prefix.splitlines())
        assert not any(" D " in ln and "detach" in ln for ln in prefix.splitlines())


def test_prefix_table_locked_down_to_switching_only():
    """Appliance-Härtung: die Prefix-Tabelle enthält AUSSCHLIESSLICH die 4
    select-pane-Binds — sonst nichts. Damit kann 'Ctrl-b <X>' nichts mehr."""
    with PaneSession(seed=9003) as ps:
        lines = [ln for ln in ps._tmux("list-keys", "-T", "prefix").stdout.splitlines()
                 if ln.strip()]
        assert len(lines) == 4, f"Prefix-Tabelle hat {len(lines)} Binds (erwartet 4):\n" \
                                + "\n".join(lines)
        assert all("select-pane" in ln for ln in lines), "\n".join(lines)


# ── Destruktive Default-Prefix-Tasten sind tot (Fat-Finger-Schutz) ───────────
def test_prefix_x_does_not_kill_pane():
    """Ctrl-b x (+ y) = tmux-Default kill-pane. Darf die TUI-Pane NICHT killen."""
    with PaneSession(seed=11) as ps:
        assert ps.wait_attached()
        ps.feed(PREFIX + b"x"); ps.settle(0.1)
        ps.feed(b"y"); ps.settle(0.1)           # ein evtl. confirm-before bestätigen
        st = ps.state()
        assert st["exists"] and st["npanes"] == 2, "Ctrl-b x hat eine Pane gekillt"


def test_prefix_quote_does_not_split():
    """Ctrl-b " / % = tmux-Default split. Darf KEINEN dritten Pane aufmachen."""
    with PaneSession(seed=12) as ps:
        assert ps.wait_attached()
        ps.feed(PREFIX + b'"'); ps.settle(0.1)
        ps.feed(PREFIX + b'%'); ps.settle(0.1)
        assert ps.state()["npanes"] == 2, "Ctrl-b \"/% hat gesplittet (Drei-Pane-Chaos)"


def test_prefix_c_does_not_create_window():
    """Ctrl-b c = tmux-Default new-window. Darf die TUI nicht hinter ein
    zweites Fenster schieben."""
    with PaneSession(seed=13) as ps:
        assert ps.wait_attached()
        before = ps._tmux("display-message", "-p", "-t", "s",
                          "-F", "#{session_windows}").stdout.strip()
        ps.feed(PREFIX + b"c"); ps.settle(0.15)
        after = ps._tmux("display-message", "-p", "-t", "s",
                         "-F", "#{session_windows}").stdout.strip()
        assert after == before, f"Ctrl-b c hat ein Fenster erzeugt ({before}→{after})"


# ── Switchen: beide Richtungen, MIT und OHNE gehaltenem Ctrl ─────────────────
def test_prefix_up_switches_to_top():
    with PaneSession(seed=1) as ps:
        assert ps.wait_attached()
        ps.select_bottom(); ps.settle()
        assert _switch_to(ps, PREFIX + UP, 0), "Ctrl-b ↑ hat nicht nach oben geschaltet"


def test_prefix_down_switches_to_bottom():
    with PaneSession(seed=2) as ps:
        assert ps.wait_attached()
        ps.select_top(); ps.settle()
        assert _switch_to(ps, PREFIX + DOWN, 1), "Ctrl-b ↓ hat nicht nach unten geschaltet"


def test_prefix_cup_switches_even_with_ctrl_held():
    """DER FIX: Ctrl nach dem 'b' weiter gehalten → Ctrl-b Ctrl-↑ muss SWITCHEN
    (oben), nicht resizen. Genau das war vorher kaputt."""
    with PaneSession(seed=3) as ps:
        assert ps.wait_attached()
        ps.select_bottom(); ps.settle()
        assert _switch_to(ps, PREFIX + C_UP, 0), \
            "Ctrl-b Ctrl-↑ schaltet nicht nach oben (alte Ctrl-Timing-Falle!)"


def test_prefix_cdown_switches_even_with_ctrl_held():
    with PaneSession(seed=4) as ps:
        assert ps.wait_attached()
        ps.select_top(); ps.settle()
        assert _switch_to(ps, PREFIX + C_DOWN, 1), \
            "Ctrl-b Ctrl-↓ schaltet nicht nach unten (alte Ctrl-Timing-Falle!)"


# ── Resizen: Ctrl+↑/↓ OHNE Prefix verändert Pane-0-Höhe, Fokus bleibt ────────
# Konvention (siehe start_tui.sh): Ctrl+↑ = bash höher → TUI (Pane 0) SCHRUMPFT;
# Ctrl+↓ = bash niedriger → TUI WÄCHST.
def test_root_cup_shrinks_pane0_without_prefix():
    with PaneSession(seed=5) as ps:
        assert ps.wait_attached()
        ps.select_bottom(); ps.settle()
        h_before = ps.state()["pane0_height"]
        for _ in range(3):
            ps.feed(C_UP); ps.settle()
        st = ps.state()
        assert st["pane0_height"] < h_before, "Ctrl+↑ ohne Prefix hat die TUI nicht verkleinert"
        assert st["active"] == 1, "Resizen darf den Fokus NICHT wechseln"


def test_root_cdown_grows_pane0_without_prefix():
    with PaneSession(seed=6) as ps:
        assert ps.wait_attached()
        ps.select_bottom(); ps.settle()
        for _ in range(4):
            ps.feed(C_UP); ps.settle()          # TUI erst klein machen (bash hoch)
        h_mid = ps.state()["pane0_height"]
        for _ in range(3):
            ps.feed(C_DOWN); ps.settle()
        assert ps.state()["pane0_height"] > h_mid, "Ctrl+↓ ohne Prefix hat die TUI nicht vergrößert"
        assert ps.state()["active"] == 1, "Resizen darf den Fokus NICHT wechseln"


# ── Detach-Schutz: Ctrl-b d / D koppelt NICHT ab ─────────────────────────────
def test_detach_keys_do_not_detach():
    with PaneSession(seed=7) as ps:
        assert ps.wait_attached()
        ps.feed(PREFIX + b"d"); ps.settle(0.1)
        assert ps.state()["attached"], "Ctrl-b d hat abgekoppelt — Detach-Schutz versagt"
        ps.feed(PREFIX + b"D"); ps.settle(0.1)
        assert ps.state()["attached"], "Ctrl-b D hat abgekoppelt — Detach-Schutz versagt"


# ── Resize-Extrem: viele Schritte runter dürfen weder Pane killen noch crashen ─
def test_extreme_resize_keeps_two_panes_alive():
    with PaneSession(seed=8) as ps:
        assert ps.wait_attached()
        for _ in range(60):                     # bash maximal hoch → TUI ganz klein
            ps.feed(C_DOWN); ps.settle(0.0)
        ps.settle(0.1)
        st = ps.state()
        assert st["exists"] and st["npanes"] == 2, "Extrem-Resize hat eine Pane verloren"
        assert st["pane0_height"] >= 1, "Pane 0 unter 1 Zeile gedrückt"
        for _ in range(60):                     # wieder ganz hoch
            ps.feed(C_UP); ps.settle(0.0)
        ps.settle(0.1)
        st = ps.state()
        assert st["exists"] and st["npanes"] == 2
        assert st["attached"]


# ── Großer Fuzz: zufällige Tastenfolgen, Invarianten nach JEDER Aktion ───────
@pytest.mark.parametrize("seed", list(range(SESSIONS)))
def test_pane_fuzz(seed):
    res = run_fuzz_session(seed, n_actions=ACTIONS)
    assert res.ok, res.msg
