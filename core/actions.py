# core/actions.py

from events import MORNING_WAKEUP, BUTTON_PRESS, LIGHT_SENSOR_TRIGGER

def handle_action(event):
    if event == MORNING_WAKEUP:
        print("ACTION: Good Morning ☀️")
    elif event == BUTTON_PRESS:
        print("ACTION: Button pressed - trigger something")
    elif event == LIGHT_SENSOR_TRIGGER:
        print("ACTION: Light sensor activated")