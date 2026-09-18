"""
'q' legt weg statt zu beenden — die TUI bleibt warm.

Sasha, 18.09.2026: „zentrale fängt erst an hochzufahren bzw 'abgleich mit
pc' und blumenwind zu zeigen wenn man das erste mal sie öffnet mit cmd z,
ich will dass sie von anfang an wach ist damit ich nicht warten muss."

Gemessen: das Login-Fenster lief von 20:52 bis 22:26 — bis 'q'. Dann war
das Terminal zu, und $mod+z am naechsten Tag zog alles kalt hoch. Jetzt
entscheidet weglegen_statt_beenden(), ob nach einem sauberen run_ui-Ende
weitergemacht wird (Fenster versteckt, Prozess warm) oder Schluss ist.
"""

import subprocess

import pytest

from tui import zentrale_tui as z


@pytest.fixture(autouse=True)
def _frisch(monkeypatch):
    monkeypatch.setitem(z.ENDE, "echt", False)
    monkeypatch.setitem(z.NEUSTART, "an", False)
    monkeypatch.setenv("ZENTRALE_TUI_SUPERVISED", "1")


def _fenster_antwortet(monkeypatch, rc):
    gerufen = []
    def fake_run(cmd, **kw):
        gerufen.append(cmd)
        return subprocess.CompletedProcess(cmd, rc)
    monkeypatch.setattr(z.subprocess, "run", fake_run)
    return gerufen


def test_q_unter_der_systemeinheit_legt_weg(monkeypatch):
    gerufen = _fenster_antwortet(monkeypatch, 0)
    assert z.weglegen_statt_beenden() is True
    assert gerufen and gerufen[0][:2] == ["zentrale-fenster", "--weglegen"]


def test_quit_beendet_wirklich(monkeypatch):
    """/quit setzt ENDE['echt'] — dann wird nicht einmal gefragt."""
    gerufen = _fenster_antwortet(monkeypatch, 0)
    z.ENDE["echt"] = True
    assert z.weglegen_statt_beenden() is False
    assert gerufen == []


def test_reboot_hat_vorrang(monkeypatch):
    gerufen = _fenster_antwortet(monkeypatch, 0)
    z.NEUSTART["an"] = True
    assert z.weglegen_statt_beenden() is False
    assert gerufen == []


def test_ohne_start_skript_beendet_q(monkeypatch):
    """Standalone (kein start_tui.sh) gibt es niemanden, der das Fenster
    kennt — 'q' beendet wie frueher."""
    gerufen = _fenster_antwortet(monkeypatch, 0)
    monkeypatch.delenv("ZENTRALE_TUI_SUPERVISED")
    assert z.weglegen_statt_beenden() is False
    assert gerufen == []


def test_kein_fokussiertes_fenster_heisst_beenden(monkeypatch):
    """zentrale-fenster meldet 1 (gewoehnliches Terminal, kein i3): dann
    darf die TUI nicht unsichtbar weiterlaufen."""
    _fenster_antwortet(monkeypatch, 1)
    assert z.weglegen_statt_beenden() is False


def test_fehlender_umschalter_beendet(monkeypatch):
    def kaputt(cmd, **kw):
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(z.subprocess, "run", kaputt)
    assert z.weglegen_statt_beenden() is False


def test_slash_quit_ist_das_echte_ende():
    action, _mode, _msg = z.parse_command("/quit", "auto")
    assert action == "QUIT"
