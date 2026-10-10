"""
Farbrollen (2026-10-10, memory/system/hub_bauplan.md „Farbrollen"): die App
sagt die Bedeutung (core/farbrollen.py), jede Oberfläche die Farbe. Die TUI
muss JEDE Rolle abbilden — auf eine Rolle ihrer eigenen Palette.
"""
import farbrollen
from tui.ansichten import desk_kacheln
from tui.ansichten.farben import FARBROLLEN, ROLES, THEMES


def test_woerterbuch_hat_namen_und_eine_zeile_bedeutung():
    assert farbrollen.RUECKFALL in farbrollen.ROLLEN
    for name, bedeutung in farbrollen.ROLLEN.items():
        assert name.isidentifier() and name == name.lower()
        assert isinstance(bedeutung, str) and bedeutung and "\n" not in bedeutung


def test_tui_bildet_jede_rolle_ab_und_nur_diese():
    assert set(FARBROLLEN) == set(farbrollen.ROLLEN)
    for name, tui in FARBROLLEN.items():
        assert tui in ROLES, name
        for theme in THEMES.values():
            assert tui in theme, (name, tui)


def test_unbekannte_rolle_faellt_auf_text_zurueck():
    assert farbrollen.rolle("erfunden") == "text" and farbrollen.rolle("heute") == "heute"
    assert desk_kacheln.farbe("erfunden") == FARBROLLEN["text"]
    assert desk_kacheln.farbe("#ff0000") == FARBROLLEN["text"]       # keine Farben von Apps
