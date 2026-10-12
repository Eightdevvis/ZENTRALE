"""
Die Browser-Front unter /zentrale (ui/routen/browser.py, 2026-10-12).

Geprüft: Seite, Weiterleitung von /, Dateien unter /zentrale/static, die
KI-Grenze per ki_aus (Tests aus der Zeit vor dem Archiv, auf /zentrale
umgestellt) und dass jede Wiederholung im verdeckten Tab ruht.
"""
import os
import re

import pytest

from ui.app import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_wurzel_leitet_auf_zentrale(client):
    r = client.get("/")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/zentrale")


def test_seite_und_ihre_dateien(client):
    r = client.get("/zentrale")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    html = r.get_data(as_text=True)
    pfade = re.findall(r'(?:src|href)="(/zentrale/static/[^"]+)"', html)
    assert len(pfade) == 4, pfade             # fonts.css, engine, viz, ascii
    for p in pfade:
        assert client.get(p).status_code == 200, p
    css = client.get("/zentrale/static/fonts/fonts.css").get_data(as_text=True)
    schriften = re.findall(r"url\(([^)]+)\)", css)
    assert schriften and all("/" not in s for s in schriften)   # relativ zu fonts/
    assert client.get("/zentrale/static/fonts/" + schriften[0]).status_code == 200
    assert client.get("/static/engine.js").status_code == 404   # nur ein Weg


def test_ki_frei_ohne_lokale_ki(client):
    # conftest fährt ZENTRALE_LOKALE_KI=aus → ki_aus=True.
    html = client.get("/zentrale").get_data(as_text=True)
    assert "window.KI_AUS = true" in html
    assert 'id="chat-input"' not in html
    assert 'id="ai-state"' not in html
    assert 'id="core"' in html
    assert 'class="box shortcuts"' in html
    for tab in ('data-ex="listen"', 'data-ex="mail"', 'data-ex="klavier"'):
        assert tab in html


def test_ki_front_mit_lokaler_ki(client, monkeypatch):
    monkeypatch.setenv("ZENTRALE_LOKALE_KI", "an")
    html = client.get("/zentrale").get_data(as_text=True)
    assert "window.KI_AUS = false" in html
    assert 'id="chat-input"' in html
    assert 'class="box shortcuts"' not in html


def test_fotos_ohne_ordner_leer(client):
    r = client.get("/api/photos")
    assert r.status_code == 200 and isinstance(r.get_json(), list)


def test_wiederholungen_ruhen_im_verdeckten_tab():
    """Polling und Animation laufen über wiederholen() (engine.js), nie über
    ein nacktes setInterval — sonst pollt ein verdeckter Tab weiter."""
    with open(os.path.join(ROOT, "ui", "static", "engine.js"), encoding="utf-8") as f:
        engine = f.read()
    assert "visibilitychange" in engine and "document.hidden" in engine
    with open(os.path.join(ROOT, "ui", "templates", "monolith.html"), encoding="utf-8") as f:
        html = f.read()
    # Einzige Ausnahme: die Laufzeit-Anzeige während einer Aufnahme.
    nackt = [z for z in html.splitlines() if re.search(r"(?<![\w.])setInterval\(", z)
             and "recTick" not in z and not z.strip().startswith("//")]
    assert nackt == []
    nackt_engine = [z for z in engine.splitlines() if re.search(r"(?<![\w.])setInterval\(", z)
                    and "w.id = setInterval" not in z]
    assert nackt_engine == []
