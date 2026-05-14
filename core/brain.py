# core/brain.py

from events import (
    TIME_REACHED, MORNING_WAKEUP, BUTTON_PRESS,
    LIGHT_SENSOR_TRIGGER, PRESENCE_DETECTED,
)


def process_event(event, data=None):
    """
    Nimmt ein Event entgegen und gibt neue Events zurück.

    Hier sitzt die zentrale Logik: welches Event löst was aus?
    Jeder elif-Block ist ein Zustandsübergang des Systems.
    """
    new_events = []

    if event == TIME_REACHED:
        new_events.append(MORNING_WAKEUP)

    elif event == BUTTON_PRESS:
        print("Brain: Button pressed")

    elif event == LIGHT_SENSOR_TRIGGER:
        print("Brain: Light sensor triggered")

    elif event == PRESENCE_DETECTED:
        # Presence wird zwar weiter ge-queued (main.py + Webhook), aber
        # aktuell ohne Folgewirkung. Tutor-Auto-Start ist pausiert
        # (siehe memory/tutor_system.md).
        print("Brain: Presence erkannt (kein Trigger aktiv)")

    return new_events