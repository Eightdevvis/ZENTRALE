"""
Desktop-Benachrichtigungen — ZENTRALE meldet sich ausserhalb ihres Fensters.

Seit dem Takt kann sie von sich aus sprechen; bis zum 19.08.2026 endete
diese Initiative aber an der Fensterkante. Eine Terminerinnerung, die man
erst nach dem Termin liest, ist keine.

Getestet wird die Entscheidungslogik gegen NACHGEBAUTE i3-Antworten. Der
echte Baum ist auf Sashas Maschine geprueft worden (offen / im Scratchpad /
eingeblendet); hier geht es darum, dass die Faelle nicht wieder verrutschen
— vor allem der stille: `visible` steht NICHT im Baum, ein Blick dorthin
liefert None und haette dauerhaft "unsichtbar" bedeutet.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import melden


def _fenster(rolle="zentrale"):
    return {"type": "con", "name": "ZENTRALE",
            "window_properties": {"window_role": rolle},
            "nodes": [], "floating_nodes": []}


def _baum(*, im_scratchpad=False, ws="1"):
    fenster = _fenster()
    arbeitsflaeche = {"type": "workspace", "name": ws,
                      "nodes": [] if im_scratchpad else [fenster],
                      "floating_nodes": []}
    scratch = {"type": "workspace", "name": "__i3_scratch",
               "nodes": [fenster] if im_scratchpad else [],
               "floating_nodes": []}
    return {"type": "root", "name": "root",
            "nodes": [arbeitsflaeche, scratch], "floating_nodes": []}


@pytest.fixture
def i3(monkeypatch):
    """i3-msg nachbauen. `stellen` setzt, was die beiden Abfragen liefern."""
    zustand = {}

    class Antwort:
        returncode = 0
        def __init__(self, text): self.stdout = text

    def fake_run(cmd, **kw):
        was = cmd[-1]
        return Antwort(json.dumps(zustand[was]))

    monkeypatch.setattr(melden.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(melden.subprocess, "run", fake_run)

    def stellen(*, im_scratchpad=False, ws="1", sichtbare=("1",)):
        zustand["get_tree"] = _baum(im_scratchpad=im_scratchpad, ws=ws)
        zustand["get_workspaces"] = [
            {"name": n, "visible": n in sichtbare} for n in ("1", "2")]
    return stellen


# ── Sichtbarkeit ──────────────────────────────────────────────────────

def test_offen_auf_dem_aktuellen_workspace(i3):
    i3()
    assert melden.sichtbar() is True


def test_im_scratchpad_ist_versteckt(i3):
    i3(im_scratchpad=True)
    assert melden.sichtbar() is False


def test_auf_einem_anderen_workspace_ist_auch_versteckt(i3):
    """Eingeblendet, aber auf einem Workspace, den er verlassen hat — das
    sieht er genauso wenig wie ein weggelegtes Fenster."""
    i3(ws="2", sichtbare=("1",))
    assert melden.sichtbar() is False


def test_kein_fenster_heisst_unbekannt(i3, monkeypatch):
    i3()
    leer = {"type": "root", "name": "root", "nodes": [], "floating_nodes": []}
    monkeypatch.setattr(melden.subprocess, "run",
                        lambda cmd, **kw: type("A", (), {
                            "returncode": 0,
                            "stdout": json.dumps(
                                leer if cmd[-1] == "get_tree"
                                else [{"name": "1", "visible": True}])})())
    assert melden.sichtbar() is None


def test_ohne_i3_keine_behauptung(monkeypatch):
    """None heisst 'weiss ich nicht' und ist etwas anderes als False. Wer
    nicht weiss, ob der Benutzer hinschaut, soll ihn benachrichtigen — eine
    verpasste Erinnerung ist teurer als ein ueberfluessiges Popup."""
    monkeypatch.setattr(melden.shutil, "which", lambda n: None)
    assert melden.sichtbar() is None


def test_ein_kaputtes_i3_wirft_nicht(monkeypatch):
    monkeypatch.setattr(melden.shutil, "which", lambda n: "/usr/bin/i3-msg")
    def kaputt(*a, **k):
        raise OSError("weg")
    monkeypatch.setattr(melden.subprocess, "run", kaputt)
    assert melden.sichtbar() is None


# ── Die Meldung selbst ────────────────────────────────────────────────

def test_meldung_geht_raus_wenn_versteckt(monkeypatch):
    monkeypatch.setattr(melden, "sichtbar", lambda: False)
    monkeypatch.setattr(melden.shutil, "which", lambda n: "/usr/bin/" + n)
    geschickt = []
    monkeypatch.setattr(melden.subprocess, "run",
                        lambda cmd, **kw: geschickt.append(cmd))

    assert melden.desktop("Geige gleich.") is True
    assert geschickt[0][0] == "notify-send"
    assert "Geige gleich." in geschickt[0]
    assert "ZENTRALE" in geschickt[0]


def test_die_meldung_kennt_die_sitzung(monkeypatch):
    """Als systemd-Benutzerdienst ist DISPLAY nicht gesetzt. Ohne Ruecksetzer
    faellt notify-send stumm auf die Nase — und zwar genau dann, wenn
    ZENTRALE als Systemeinheit laeuft, also immer."""
    monkeypatch.setattr(melden, "sichtbar", lambda: False)
    monkeypatch.setattr(melden.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.delenv("DISPLAY", raising=False)
    gesehen = {}
    monkeypatch.setattr(melden.subprocess, "run",
                        lambda cmd, **kw: gesehen.update(kw))
    melden.desktop("Geige gleich.")
    assert gesehen["env"].get("DISPLAY") == ":0"


def test_keine_meldung_wenn_sie_ohnehin_dasteht(i3, monkeypatch):
    """Ein Popup, waehrend er auf ZENTRALE schaut, ist reine Stoerung."""
    i3()
    monkeypatch.setattr(melden, "sichtbar", lambda: True)
    assert melden.desktop("Geige gleich.") is False


def test_bei_unbekannter_sichtbarkeit_wird_gemeldet(monkeypatch):
    monkeypatch.setattr(melden, "sichtbar", lambda: None)
    monkeypatch.setattr(melden.shutil, "which", lambda n: "/usr/bin/" + n)
    gesendet = []
    monkeypatch.setattr(melden.subprocess, "run",
                        lambda cmd, **kw: gesendet.append(cmd))
    assert melden.desktop("Geige gleich.") is True
    assert gesendet


def test_leerer_text_meldet_nichts(monkeypatch):
    monkeypatch.setattr(melden, "sichtbar", lambda: False)
    assert melden.desktop("   ") is False


def test_langer_text_wird_gekuerzt():
    """Ein Popup ist kein Textfenster."""
    gekuerzt = melden._kuerzen("wort " * 200)
    assert len(gekuerzt) <= melden._MAX
    assert gekuerzt.endswith("…")


def test_abschaltbar(monkeypatch):
    monkeypatch.setattr(melden, "AN", False)
    assert melden.desktop("egal") is False


def test_ohne_notify_send_kein_absturz(monkeypatch):
    monkeypatch.setattr(melden, "sichtbar", lambda: False)
    monkeypatch.setattr(melden.shutil, "which", lambda n: None)
    assert melden.desktop("Geige gleich.") is False
