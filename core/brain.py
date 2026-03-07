# core/brain.py

from events import TIME_REACHED, MORNING_WAKEUP, BUTTON_PRESS, LIGHT_SENSOR_TRIGGER


def process_event(event, data=None):
    """
    Takes an event + optional data
    Returns a list of new events
    """
    new_events = []

    if event == TIME_REACHED:
        # später prüfen wir Uhrzeit in data
        new_events.append(MORNING_WAKEUP)
    elif event == BUTTON_PRESS:
        print("Brain: Button pressed")
    elif event == LIGHT_SENSOR_TRIGGER:
        print("Brain: Light sensor triggered")

    return new_events