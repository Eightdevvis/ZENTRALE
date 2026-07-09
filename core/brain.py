# core/brain.py

import os

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
        # Tutor-Auto-START bleibt bewusst pausiert (memory/tutor_system.md,
        # Sequencing). NUR wenn TUTOR_PRESENCE_REACT=1 gesetzt ist, reicht der
        # Presence-Event einen NONVERBALEN Ping an die Persona weiter — und der
        # wirkt auch dann nur, wenn die Tutor-Session bereits LÄUFT (er startet
        # nie eine). Default (Flag aus) = unverändert kein Trigger.
        if os.getenv("TUTOR_PRESENCE_REACT") == "1":
            try:
                import tutor_session
                reacted = tutor_session.presence_ping()
                print("Brain: Presence → Persona "
                      + ("reagiert" if reacted else "ruht (Session inaktiv/Cooldown)"))
            except Exception as e:
                print(f"Brain: Presence-Reaktion fehlgeschlagen: {e}")
        else:
            print("Brain: Presence erkannt (kein Trigger aktiv)")

    return new_events