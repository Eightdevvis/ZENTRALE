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
        # Jemand ist im Raum → als Ereignis „anwesenheit" an die Apps, die es
        # abonniert haben (app.toml, Recht ereignis:anwesenheit). Heute ist das
        # der Sprach-Tutor; ob und wie er reagiert, entscheidet ER (seine
        # Einstellung presence_react). Bis 2026-10-09 rief brain.py hier den
        # Tutor-Code direkt auf (tutor_port.presence_ping) — der Hub kennt
        # keinen App-Code mehr (memory/system/hub_bauplan.md).
        try:
            import hub_ereignisse
            n = hub_ereignisse.senden("anwesenheit")
            print(f"Brain: Presence → Ereignis an {n} App(s)")
        except Exception as e:
            print(f"Brain: Presence-Ereignis fehlgeschlagen: {e}")

    return new_events