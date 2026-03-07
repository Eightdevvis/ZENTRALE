# core/sensors.py

import keyboard  # pip3 install keyboard

def read_button():
    """
    Taste 'b' simuliert Button Press
    """
    if keyboard.is_pressed('b'):
        return True
    return False

def read_light_sensor():
    """
    Taste 'l' simuliert Light Sensor Trigger
    """
    if keyboard.is_pressed('l'):
        return True
    return False