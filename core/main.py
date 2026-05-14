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

    event_queue = [SYSTEM_BOOT]

    # Initiale Vokabel laden
    state.set_vocab(_load_vocab())

    log("ZENTRALE SYSTEM STARTED")
    log("UI erreichbar unter http://localhost:5000")

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

        # 4️⃣ Kleine Pause um CPU zu schonen
        time.sleep(1)


if __name__ == "__main__":
    main()
