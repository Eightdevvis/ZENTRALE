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


def test_api_calendar_week_shape(client):
    # /api/calendar ist die geteilte Quelle für die Kalender-Mitte ALLER
    # Kassetten (TUI, Monolith, Laptop) — nicht KI-gegatet, läuft also auch in
    # der ki-freien tui-Kassette. Default ist die laufende Woche.
    r = client.get("/api/calendar")
    assert r.status_code == 200
    d = r.get_json()
    assert isinstance(d, dict)
    for key in ("view", "ref", "today", "label", "start", "end", "days", "alarms"):
        assert key in d, f"/api/calendar fehlt der Key '{key}'"
    assert d["view"] == "week"
    assert isinstance(d["days"], dict)
    # Woche ist Mo-So → genau 7 Tage Spanne.
    from datetime import date
    assert (date.fromisoformat(d["end"]) - date.fromisoformat(d["start"])).days == 6


def test_api_calendar_month_grid(client):
    # Monatsansicht: volle Mo-So-Wochenzeilen, first/last grenzen den echten
    # Monat im Gitter ab. ref fixiert, damit der Test datumsunabhängig ist.
    r = client.get("/api/calendar?view=month&ref=2026-06-15")
    assert r.status_code == 200
    d = r.get_json()
    assert d["view"] == "month"
    assert d["month"] == "2026-06"
    assert d["first"] == "2026-06-01" and d["last"] == "2026-06-30"
    from datetime import date
    # Gitter startet Montag, endet Sonntag, Länge ist ein Vielfaches von 7.
    start, end = date.fromisoformat(d["start"]), date.fromisoformat(d["end"])
    assert start.weekday() == 0 and end.weekday() == 6
    assert (end - start).days % 7 == 6


def test_api_calendar_bad_ref(client):
    # Müll-Datum → 400, nicht 500 (Front darf nie einen Server-Crash auslösen).
    r = client.get("/api/calendar?ref=kaputt")
    assert r.status_code == 400


def test_api_calendar_add_and_delete(client, tmp_path, monkeypatch):
    # Direktes Anlegen/Löschen aus der Kalender-Mitte (TUI/Browser). Auf eine
    # TEMP-Datei umgebogen, damit der echte data/ai_calendar.json unberührt
    # bleibt. NICHT KI-gegatet → muss auch in der tui-Kassette durchgehen.
    import kalender
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.ensure_init()

    r = client.post("/api/calendar/entry",
                    json={"day": "2026-06-20", "label": "Zahnarzt", "time": "09:30", "ort": "Praxis"})
    assert r.status_code == 200 and r.get_json()["ok"] is True

    r = client.get("/api/calendar?view=week&ref=2026-06-20")
    day = r.get_json()["days"].get("2026-06-20", [])
    assert any(e.get("label") == "Zahnarzt" and e.get("ort") == "Praxis" for e in day)

    r = client.delete("/api/calendar/entry", json={"day": "2026-06-20", "label": "Zahnarzt"})
    assert r.get_json()["deleted"] == 1
    r = client.get("/api/calendar?view=week&ref=2026-06-20")
    assert not r.get_json()["days"].get("2026-06-20")


def test_api_calendar_add_validation(client):
    # Pflichtfelder/Format: 400 VOR jedem Schreibzugriff (keine Mutation, daher
    # kein TEMP-Datei-Setup nötig — diese Fälle schreiben nie).
    assert client.post("/api/calendar/entry", json={"day": "2026-06-20", "label": ""}).status_code == 400
    assert client.post("/api/calendar/entry", json={"day": "kaputt", "label": "X"}).status_code == 400
    assert client.delete("/api/calendar/entry", json={"day": "2026-06-20"}).status_code == 400
