# core/actions.py

from datetime import datetime
import socket

from events import MORNING_WAKEUP, BUTTON_PRESS, LIGHT_SENSOR_TRIGGER, SYSTEM_BOOT

def handle_action(event):
    if event == SYSTEM_BOOT:
        hostname = socket.gethostname()
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"ACTION: ZENTRALE online on {hostname} at {started_at}")
        print("ACTION: First deploy startup message received ✅")
    elif event == MORNING_WAKEUP:
        print("ACTION: Good Morning ☀️")
    elif event == BUTTON_PRESS:
        print("ACTION: Button pressed - trigger something")
    elif event == LIGHT_SENSOR_TRIGGER:
        print("ACTION: Light sensor activated")