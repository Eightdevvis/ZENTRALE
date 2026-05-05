# core/sensors.py

try:
    import keyboard  # pip3 install keyboard
except Exception:
    keyboard = None


def _is_pressed(key):
    if keyboard is None:
        return False
    try:
        return keyboard.is_pressed(key)
    except Exception:
        return False

def read_button():
    """
    Taste 'b' simuliert Button Press
    """
    if _is_pressed('b'):
        return True
    return False

def read_light_sensor():
    """
    Taste 'l' simuliert Light Sensor Trigger
    """
    if _is_pressed('l'):
        return True
    return False

def read_motion_sensor():
    """
    Taste 'm' simuliert Motion Sensor (Presence Detection).
    Später: echter PIR-Sensor via GPIO (z.B. RPi.GPIO).
    """
    if _is_pressed('m'):
        return True
    return False