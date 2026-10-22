# Die id von /api/data/<id> und /api/log wird zum Dateinamen in data/.
# Nur bekannte Kategorien und Graphen dürfen durch (Inventur 2026-10-22).

import os

import pytest

from ui.app import app
from ui.routen.gemeinsam import _DATA_DIR


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_schluesseldatei_nicht_lesbar(client):
    for cid in ("ai_config", "lists", "features", "mail_state"):
        r = client.get("/api/data/" + cid)
        assert r.status_code == 404, cid
        assert r.get_json() == {"fehler": "unbekannt"}


def test_log_schreibt_nicht_aus_data_heraus(client):
    ziel = os.path.normpath(os.path.join(_DATA_DIR, "..", "ausbruch_test.json"))
    for cid in ("../ausbruch_test", "ai_config", "", None, 5):
        r = client.post("/api/log", json={"category": cid, "data": {"x": 1}})
        assert r.status_code == 400, cid
    assert not os.path.exists(ziel)


def test_log_ohne_json(client):
    r = client.post("/api/log", data="kaputt", content_type="text/plain")
    assert r.status_code == 400


def test_bekannte_kategorie_lesbar(client):
    r = client.get("/api/data/sleep_quality")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
