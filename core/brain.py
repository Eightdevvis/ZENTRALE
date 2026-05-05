# core/brain.py

from events import (
    TIME_REACHED, MORNING_WAKEUP, BUTTON_PRESS,
    LIGHT_SENSOR_TRIGGER, PRESENCE_DETECTED, TUTOR_START,
)
import tutor_session  # Session-State für den Sprachtutor


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
        # Jemand ist in der Nähe – Tutor starten wenn noch keine Session läuft.
        # Cooldown verhindert dass jede Bewegung eine neue Session startet.
        if not tutor_session.is_active():
            print("Brain: Presence erkannt → Tutor wird gestartet")
            new_events.append(TUTOR_START)

    elif event == TUTOR_START:
        # Tutor-Session aktivieren – die KI schickt die erste Nachricht
        # über den /api/tutor/start Endpoint, ausgelöst vom Dashboard via SSE.
        # Hier nur State setzen; die KI-Kommunikation läuft über Flask.
        tutor_session.activate()
        print("Brain: Tutor-Session aktiviert")

    return new_events