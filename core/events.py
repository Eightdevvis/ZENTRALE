# core/events.py
#
# Zentraler Ort für alle Event-Namen. Einmal hier definiert, im Rest
# des Codes als Konstante referenziert → Tippfehler unmöglich, alle
# vorhandenen Events auf einen Blick.

TIME_REACHED         = "TIME_REACHED"
MORNING_WAKEUP       = "MORNING_WAKEUP"
BUTTON_PRESS         = "BUTTON_PRESS"
LIGHT_SENSOR_TRIGGER = "LIGHT_SENSOR_TRIGGER"
SYSTEM_BOOT          = "SYSTEM_BOOT"
DATA_COLLECTION      = "DATA_COLLECTION"
PRESENCE_DETECTED    = "PRESENCE_DETECTED"   # Motion-Sensor hat jemanden erkannt
TUTOR_START          = "TUTOR_START"          # Sprachtutor-Session beginnen

# ── Tür-/Heimkehr-Events ──────────────────────────────────────────────
# DOOR_TOGGLE feuert jedes Mal wenn der Türsensor durchgeht (auf ODER zu).
# Den semantischen Übergang home↔away macht brain.py – der Sensor selbst
# weiß nicht, ob die Bewegung „raus" oder „rein" ist.
DOOR_TOGGLE          = "DOOR_TOGGLE"

# HOMECOMING feuert nur dann, wenn brain.py erkannt hat: „User war länger
# als HOMECOMING_THRESHOLD weg und ist jetzt zurück". Erst dieser Event
# triggert die Assistenten-Begrüßung – nicht jeder Tür-Toggle.
HOMECOMING           = "HOMECOMING"