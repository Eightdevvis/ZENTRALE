# core/main.py

from brain import process_event
from actions import handle_action
from clock import check_time
from sensors import read_light_sensor, read_button
from events import TIME_REACHED, LIGHT_SENSOR_TRIGGER, BUTTON_PRESS

def main():
    event_queue = []

    # Optional: initialer Start
    print("ZENTRALE SYSTEM STARTED")

    while True:
        # 1️⃣ Sensoren abfragen
        if read_light_sensor():
            event_queue.append(LIGHT_SENSOR_TRIGGER)
        if read_button():
            event_queue.append(BUTTON_PRESS)

        # 2️⃣ Clock prüfen (nur stündlich oder minütlich)
        # Für Test: jede Minute 07:00 simulieren
        now = check_time(7, 0)
        event_queue.append(now)

        # 3️⃣ Event-Loop
        while event_queue:
            event = event_queue.pop(0)
            print("EVENT IN :", event)

            new_events = process_event(event)
            handle_action(event)

            for new_event in new_events:
                print("EVENT OUT:", new_event)
                event_queue.append(new_event)

        # 4️⃣ Kleine Pause um CPU zu schonen
        import time
        time.sleep(1)

if __name__ == "__main__":
    main()