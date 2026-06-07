# core/main.py

import threading
import sys
import os
import time
import json

from brain import process_event
from actions import handle_action
from clock import check_time
from sensors import read_light_sensor, read_button, read_motion_sensor
from events import (
    LIGHT_SENSOR_TRIGGER, BUTTON_PRESS, SYSTEM_BOOT, PRESENCE_DETECTED,
    DOOR_TOGGLE,
)
import state
import kalender


# Mapping: Sensor-Name aus dem Webhook -> intern verwendeter Event-Name.
# Lokal definiert (nicht in events.py), weil es eine Adapter-Schicht ist:
# physikalischer Eingang -> logisches Ereignis. Die Webhook-Whitelist in
# ui/app.py muss synchron bleiben.
_SENSOR_TO_EVENT = {
    "button": BUTTON_PRESS,
    "light":  LIGHT_SENSOR_TRIGGER,
    "motion": PRESENCE_DETECTED,
    "door":   DOOR_TOGGLE,
}


def log(msg: str):
    print(msg)
    state.push_log(msg)

# ZENTRALE-Root auf den Pfad legen damit wir ui importieren können
_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, _root)


def _load_vocab():
    """Lädt das erste Wort aus vocab_mandarin.json. Gibt None zurück bei Fehler."""
    try:
        vocab_path = os.path.join(_root, 'vocab_mandarin.json')
        with open(vocab_path, 'r', encoding='utf-8') as f:
            vocab = json.load(f)
        if vocab:
            return {"word": vocab[0]['word'], "pinyin": vocab[0].get('pinyin', '')}
    except Exception:
        pass
    return None


def main():
    # Flask UI als Background-Thread starten
    from ui.app import start_ui
    ui_thread = threading.Thread(target=start_ui, daemon=True)
    ui_thread.start()

    # KI-Modelle im Hintergrund ins Ollama-RAM ziehen, damit der erste
    # echte User-Chat nicht den Cold-Load von qwen2.5:14b (~9 GB) zahlen
    # muss. Daemon-Thread, blockiert nichts - während der Warmup läuft
    # kann der User schon das Dashboard bedienen.
    import ai
    ai.warmup_async()

    # Persönliche Tagesschau: periodischer Hintergrund-Fetcher zieht
    # Weltpolitik aus vielen RSS-Quellen und lässt die KI daraus ein
    # Briefing bauen (core/news.py). Eigener Daemon-Thread, vom Chat
    # entkoppelt; jeder Lauf kündigt sich laut im Log + Internet-Panel an.
    import news
    news.start_fetcher()

    event_queue = [SYSTEM_BOOT]

    # Initiale Vokabel laden
    state.set_vocab(_load_vocab())

    # Alarm-Kanal initial befüllen: beim Boot einmal alle offenen Kalender-
    # Alarme rechnen, damit die Dashboard-Ecke + der KI-Prompt sofort Bescheid
    # wissen (sonst erst nach der ersten Kalender-Mutation). Danach hält
    # kalender._save_raw das Set nach jeder Änderung frisch; der periodische
    # Recompute unten fängt zeitrelative Alarme ab (Reise rückt näher).
    try:
        state.set_alarms(kalender.open_alarms())
    except Exception as e:
        log(f"Alarm-Init fehlgeschlagen: {e}")

    log("ZENTRALE SYSTEM STARTED")
    log("UI erreichbar unter http://localhost:5000")

    _alarm_tick = 0
    while True:
        # 1️⃣ Sensoren abfragen + State updaten
        button = read_button()
        light = read_light_sensor()
        state.set_sensor("button", button)
        state.set_sensor("light", light)

        motion = read_motion_sensor()
        state.set_sensor("motion", motion)

        if light:
            event_queue.append(LIGHT_SENSOR_TRIGGER)
        if button:
            event_queue.append(BUTTON_PRESS)
        if motion:
            event_queue.append(PRESENCE_DETECTED)

        # 1b️⃣ Externe Sensor-Trigger einsammeln (vom Webhook).
        # Damit kann die Pi-Sensor-Bridge (oder ein anderer LAN-Client)
        # via POST /api/sensor/<name> Events feuern, ohne dass main.py
        # selbst am GPIO haengt. Adapter-Mapping in _SENSOR_TO_EVENT.
        for sensor_name in state.drain_sensor_queue():
            mapped = _SENSOR_TO_EVENT.get(sensor_name)
            if mapped:
                event_queue.append(mapped)

        # 2️⃣ Clock prüfen
        now = check_time(7, 0)
        if now:
            event_queue.append(now)

        # 3️⃣ Event-Loop
        while event_queue:
            event = event_queue.pop(0)
            log(f"EVENT IN : {event}")
            state.push_event(event)

            new_events = process_event(event)
            handle_action(event)

            for new_event in new_events:
                log(f"EVENT OUT: {new_event}")
                event_queue.append(new_event)

        # 3b️⃣ Alarm-Kanal periodisch neu rechnen (alle ~300 Ticks ≈ 5 min).
        # Fängt zeitrelative Alarme ab, die OHNE Kalender-Edit relevant werden
        # (eine Reise rückt in den Horizont). Kalender-Edits selbst aktualisieren
        # das Set schon sofort über kalender._save_raw - das hier ist nur der
        # langsame Heartbeat gegen Zeit-Drift.
        _alarm_tick += 1
        if _alarm_tick % 300 == 0:
            try:
                state.set_alarms(kalender.open_alarms())
            except Exception as e:
                log(f"Alarm-Recompute fehlgeschlagen: {e}")

        # 4️⃣ Kleine Pause um CPU zu schonen
        time.sleep(1)


if __name__ == "__main__":
    main()
