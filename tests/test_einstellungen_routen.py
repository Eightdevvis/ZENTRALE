"""Die zwei Lese-Routen für „Customize" im TUI-Chat (2026-10-07):
/api/ai/kosten (Usage) und /api/ai/werkzeuge (Capabilities)."""
import pytest

import usage
import werkzeug_register


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    usage.zuruecksetzen()
    yield app.test_client()
    usage.zuruecksetzen()


def test_kosten_mit_geschaetztem_anteil_und_budget(client):
    usage.buchen("claude-sonnet-4-5", input_tokens=1000, output_tokens=1000)
    usage.buchen("claude-sonnet-4-5", input_tokens=1000, geschaetzt=True)
    d = client.get("/api/ai/kosten").get_json()
    assert d["calls_heute"] == 2 and d["monat"] >= d["geschaetzt_monat"] > 0
    assert set(d["budget"]) >= {"status"}
    assert "claude-sonnet-4-5" in d["modelle"]


def test_kosten_leer_ist_null_nicht_fehler(client):
    d = client.get("/api/ai/kosten").get_json()
    assert d["heute"] == 0 and d["geschaetzt_monat"] == 0 and d["calls_heute"] == 0


def test_werkzeuge_aus_dem_register(client):
    d = client.get("/api/ai/werkzeuge").get_json()["werkzeuge"]
    namen = [w["name"] for w in d]
    assert namen == [w.name for w in werkzeug_register.WERKZEUGE]
    nach = {w["name"]: w for w in d}
    assert nach["read_time"]["fragt"] == "nie"
    assert nach["run_code"]["fragt"] in ("immer", "manchmal")
    assert nach["add_calendar_entry"]["alltag"]
    assert all(w["beschreibung"] and len(w["beschreibung"]) <= 160 for w in d)
    assert all(set(w["schienen"]) <= {"klein", "gross"} and w["schienen"] for w in d)
