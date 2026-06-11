"""
Backend-Smoke-Test über Flasks Test-Client.

Wir booten NICHT den ganzen main.py (Endlos-Event-Loop, Sensor-Threads, das
keyboard-Modul will sudo) und binden auch keinen echten Port :5000. Stattdessen
reden wir direkt mit der Flask-App (`ui.app.app`) über ihren Test-Client — das
testet die HTTP-Schicht deterministisch und in Millisekunden.

Geprüft wird das, was beim Start real kaputt war / kaputt gehen könnte:
  - /api/state antwortet überhaupt und liefert die erwartete JSON-Shape,
  - die KI-Endpoints sind in der tui-Kassette hart abgeriegelt (503),
  - ein unbekannter Sensor-Webhook wird abgewiesen (kein Querschuss aus dem LAN).
"""
import pytest

from ui.app import app


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_api_state_shape(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, dict)
    # Die Keys, auf die sowohl Browser- als auch TUI-Front bauen.
    for key in ("events", "sensors", "logs", "internet_logs", "uptime_s", "time"):
        assert key in data, f"/api/state fehlt der Key '{key}'"
    assert isinstance(data["uptime_s"], int)


def test_ki_endpoint_locked_in_tui_kassette(client):
    # In der tui-Kassette (conftest setzt ZENTRALE_KASSETTE=tui) darf der Chat
    # NIE durchkommen — sonst spräche eine ki-freie Front doch Ollama an.
    r = client.post("/api/chat", json={"message": "hallo"})
    assert r.status_code == 503


def test_unknown_sensor_rejected(client):
    # Nur Sensoren aus der Whitelist (button/light/motion/door) sind erlaubt.
    r = client.post("/api/sensor/raketenstart")
    assert r.status_code != 200
