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
    assert client.put("/api/calendar/entry",
                      json={"day": "2026-06-20", "label": "X", "new": {"day": "zz", "label": "Y"}}).status_code == 400
    assert client.post("/api/calendar/routine/skip", json={"label": "", "day": "2026-06-20"}).status_code == 400


def test_api_calendar_edit_entry(client, tmp_path, monkeypatch):
    # Bestehenden Einmal-Termin ändern (PUT = delete alt + add neu).
    import kalender
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.ensure_init()
    client.post("/api/calendar/entry", json={"day": "2026-06-20", "label": "Arzt", "time": "10:00"})
    r = client.put("/api/calendar/entry", json={
        "day": "2026-06-20", "label": "Arzt",
        "new": {"day": "2026-06-21", "label": "Hausarzt", "time": "11:30", "ort": "Praxis"}})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    days = client.get("/api/calendar?view=week&ref=2026-06-20").get_json()["days"]
    assert not days.get("2026-06-20")                       # alter weg
    new = days.get("2026-06-21", [])
    assert any(e.get("label") == "Hausarzt" and e.get("ort") == "Praxis" for e in new)


def test_api_calendar_routine_skip(client, tmp_path, monkeypatch):
    # Einzelnes Routine-Vorkommen deaktivieren/aktivieren — reversibel, ohne die
    # Routine zu zerstören. Andere Vorkommen bleiben aktiv.
    import kalender
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.ensure_init()
    kalender.add_routine("routinen", "Geige", "FREQ=WEEKLY;BYDAY=TU", time="17:45", ende="18:30")
    # zwei Dienstage im Bereich finden
    days = client.get("/api/calendar?view=week&ref=2026-06-16").get_json()["days"]
    tue = "2026-06-16"
    assert any(e.get("label") == "Geige" for e in days.get(tue, []))

    r = client.post("/api/calendar/routine/skip", json={"layer": "routinen", "label": "Geige", "day": tue, "off": True})
    assert r.get_json()["changed"] is True
    days = client.get("/api/calendar?view=week&ref=2026-06-16").get_json()["days"]
    geige = [e for e in days.get(tue, []) if e.get("label") == "Geige"][0]
    assert geige.get("deaktiviert") is True
    # nächster Dienstag bleibt aktiv
    nxt = client.get("/api/calendar?view=week&ref=2026-06-23").get_json()["days"]
    g2 = [e for e in nxt.get("2026-06-23", []) if e.get("label") == "Geige"][0]
    assert not g2.get("deaktiviert")
    # wieder aktivieren
    r = client.post("/api/calendar/routine/skip", json={"layer": "routinen", "label": "Geige", "day": tue, "off": False})
    assert r.get_json()["changed"] is True
    days = client.get("/api/calendar?view=week&ref=2026-06-16").get_json()["days"]
    geige = [e for e in days.get(tue, []) if e.get("label") == "Geige"][0]
    assert not geige.get("deaktiviert")


def test_api_calendar_routine_skip_same_label_diff_weekday(client, tmp_path, monkeypatch):
    # Regression: ZWEI gleichnamige Routinen an verschiedenen Wochentagen
    # (z.B. zwei 'Parkour' Mi+Fr). Deaktivieren des Fr-Vorkommens darf NUR die
    # Fr-Routine treffen — Label-Match allein landete früher auf der ersten
    # (Mi-)Routine und bewirkte sichtbar nichts.
    import kalender
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.ensure_init()
    kalender.add_routine("routinen", "Parkour", "FREQ=WEEKLY;BYDAY=WE", time="18:00")
    kalender.add_routine("routinen", "Parkour", "FREQ=WEEKLY;BYDAY=FR", time="20:00")
    fri = "2026-06-19"   # Freitag
    r = client.post("/api/calendar/routine/skip",
                    json={"layer": "routinen", "label": "Parkour", "day": fri, "off": True, "time": "20:00"})
    assert r.get_json()["changed"] is True
    week = client.get("/api/calendar?view=week&ref=2026-06-15").get_json()["days"]
    fr = [e for e in week.get(fri, []) if e.get("label") == "Parkour"][0]
    assert fr.get("deaktiviert") is True                      # Fr deaktiviert
    wed = [e for e in week.get("2026-06-17", []) if e.get("label") == "Parkour"][0]
    assert not wed.get("deaktiviert")                         # Mi unberührt


def test_api_calendar_add_routine(client, tmp_path, monkeypatch):
    # Neue wöchentliche Routine aus der UI (byday → FREQ=WEEKLY;BYDAY=…).
    import kalender
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.ensure_init()
    r = client.post("/api/calendar/routine",
                    json={"label": "Geige", "byday": ["TU", "FR"], "time": "17:45"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    # erscheint an einem Dienstag
    days = client.get("/api/calendar?view=week&ref=2026-06-16").get_json()["days"]
    geige = [e for e in days.get("2026-06-16", []) if e.get("label") == "Geige"]
    assert geige and geige[0].get("recurring") is True and geige[0].get("time") == "17:45"
    # Validierung
    assert client.post("/api/calendar/routine", json={"label": "", "byday": "TU"}).status_code == 400
    assert client.post("/api/calendar/routine", json={"label": "X", "byday": "XX"}).status_code == 400


def test_api_calendar_delete_routine(client, tmp_path, monkeypatch):
    # Ganze Routine löschen — alle Vorkommen weg, andere Routinen bleiben.
    import kalender
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.ensure_init()
    kalender.add_routine("routinen", "Geige", "FREQ=WEEKLY;BYDAY=TU", time="17:45")
    kalender.add_routine("routinen", "Parkour", "FREQ=WEEKLY;BYDAY=TH", time="19:00")
    r = client.delete("/api/calendar/routine", json={"layer": "routinen", "label": "Geige"})
    assert r.get_json()["deleted"] == 1
    days = client.get("/api/calendar?view=week&ref=2026-06-16").get_json()["days"]
    assert not any(e.get("label") == "Geige" for ents in days.values() for e in ents)
    # Parkour unberührt
    assert any(e.get("label") == "Parkour" for ents in days.values() for e in ents)
    # ohne label → 400
    assert client.delete("/api/calendar/routine", json={"layer": "routinen"}).status_code == 400


# ── Eine Front, KI per Flag ─────────────────────────────────────────────────
# Seit der Template-Vereinigung gibt es nur EIN Browser-Template (monolith.html);
# laptop/tui rendern es mit ki_aus=True (KI-Blöcke weg). Die folgenden Tests
# sichern genau diese Gate-Grenze ab — sie war vorher gar nicht getestet
# (die Route '/' lief in keinem Test).

def test_index_ki_frei_in_tui_kassette(client):
    # conftest fährt ZENTRALE_KASSETTE=tui → ki_aus=True.
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "window.KI_AUS = true" in html        # Flag korrekt durchgereicht
    assert 'id="chat-input"' not in html          # Chat-Konsole gegated
    assert 'id="ai-state"' not in html            # AI-State gegated
    assert "OLLAMA" not in html                   # KI-Header-Status gegated
    # Visualizer + Werkzeuge bleiben für ALLE Fronten:
    assert 'id="core"' in html                    # ASCII-Exhibit
    assert 'id="ai-meta"' in html                 # Direktor-Meta (kein KI)
    assert 'class="box shortcuts"' in html        # Shortcut-Footer statt Chat
    for tab in ('data-ex="listen"', 'data-ex="mail"', 'id="lists-panel"', 'id="mail-panel"'):
        assert tab in html, f"Werkzeug fehlt in der KI-freien Front: {tab}"


def test_index_ki_front_in_monolith_kassette(client, monkeypatch):
    # Monolith-Kassette → ki_aus=False; kassette.name() liest die Env zur
    # Laufzeit (kein Cache), also reicht setenv vor dem Request.
    monkeypatch.setenv("ZENTRALE_KASSETTE", "monolith")
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "window.KI_AUS = false" in html
    assert 'id="chat-input"' in html              # Chat-Konsole da
    assert 'id="ai-state"' in html
    assert "OLLAMA" in html
    assert 'class="box shortcuts"' not in html    # kein Shortcut-Footer
    # Werkzeug-Tabs sind frontübergreifend auch hier vorhanden
    assert 'data-ex="listen"' in html and 'data-ex="mail"' in html


def test_mail_endpoint_no_500_without_key(client):
    # Mail-Panel pollt /api/mail; ohne Key/Config darf das nie 500 werfen
    # (conftest: ZENTRALE_MAIL=off). 200 mit Snapshot ist ok.
    r = client.get("/api/mail")
    assert r.status_code == 200
    assert isinstance(r.get_json(), dict)
