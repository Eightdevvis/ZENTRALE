"""Die Weltkarte ist seit 2026-10-22 eine App (Repo zentrale-karte,
memory/maps/INDEX.md). ZENTRALE behält nur dünne Adapter: /api/map/* reicht
der Hub weiter, das Fenster öffnet scripts/open_app_window.py. In den Tests
ist die App die Test-App tests/fixtures/app_karte (Adresse ins Leere).

Dass die Antworten durch die Weiterleitung Byte für Byte dieselben sind wie
vorher, prüft das Karten-Repo gegen seine Aufnahme
(tests/aufnahme_vor_umzug.json); die Weiterleitung selbst
tests/test_hub_grundlagen.py.
"""
import os
import sys

import apps
import app_weiterleitung

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import open_app_window   # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "app_karte")


def test_karte_ist_eine_bekannte_app_mit_routen():
    m = apps.manifest("karte")
    assert m["_pfad"] == FIXTURE and apps.routen(m) == ["/api/map"]
    assert apps.BEKANNT["karte"] == "zentrale-karte"
    app_weiterleitung.vergessen()
    assert app_weiterleitung.besitzer("/api/map/base")["name"] == "karte"


def test_kein_kartencode_mehr_im_hub():
    for weg in ("core/map", "core/glossary.py", "ui/routen/karte.py", "scripts/map_window.py"):
        assert not os.path.exists(os.path.join(ROOT, weg)), weg


def test_karte_aus_heisst_aus_nicht_rueckfall():
    from ui.app import app
    app_weiterleitung.vergessen()
    r = app.test_client().get("/api/map/braille?cx=0&cy=20&zoom=0&cols=80&rows=30")
    assert r.status_code == 503 and r.get_json()["fehler"] == "aus"


def test_fenster_starter_findet_die_app(monkeypatch, capsys):
    assert open_app_window.main(["karte", "--pruefen"]) == 0
    gerufen = {}
    monkeypatch.setattr(open_app_window.subprocess, "call",
                        lambda cmd, cwd=None: gerufen.update(cmd=cmd, cwd=cwd) or 0)
    assert open_app_window.main(["karte", "--cx", "10.00000", "--zoom", "3.00"]) == 0
    assert gerufen["cwd"] == FIXTURE
    assert gerufen["cmd"][1:] == ["-m", "karte.fenster", "--cx", "10.00000", "--zoom", "3.00"]
    assert "python" in os.path.basename(gerufen["cmd"][0])


def test_fenster_starter_ohne_app(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ZENTRALE_APP_PFAD_KARTE", str(tmp_path / "weg"))
    monkeypatch.setattr(open_app_window, "ROOT", str(tmp_path))     # kein Nachbar-Repo
    assert open_app_window.main(["karte", "--pruefen"]) == 2
    assert "nicht installiert" in capsys.readouterr().err


def test_taste_w_ruft_den_starter_mit_dem_ausschnitt(monkeypatch):
    from tui.ansichten import karte

    class Z:
        pass
    k = karte.Karte(Z())
    k.M.update(cx=10.0, cy=50.0, zoom=3.0)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("ZENTRALE_MAP_WINDOW_LOG", os.devnull)
    gestartet = {}

    class Proc:
        def poll(self):
            return None
    monkeypatch.setattr(karte.subprocess, "Popen",
                        lambda cmd, **kw: gestartet.update(cmd=cmd) or Proc())
    k.m_window()
    cmd = gestartet["cmd"]
    assert cmd[1].endswith(os.path.join("scripts", "open_app_window.py")) and cmd[2] == "karte"
    assert cmd[3:] == ["--cx", "10.00000", "--cy", "50.00000", "--zoom", "3.00"]
