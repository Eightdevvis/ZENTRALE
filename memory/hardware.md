# Hardware (Raspberry Pi)

Für den vollen Voice-Betrieb auf dem Pi brauchst du Mikrofon, Speaker
und einen Bewegungs-/Geräuschsensor. Mikro, Lautsprecher und ein
Geräuschsensor sind **bereits angeschlossen** (Stand 2026-06-02),
aber noch nicht voll integriert – Details unter „GPIO – aktueller
Stand". (Der Mandarin-Tutor, der diese Hardware ursprünglich am
stärksten brauchte, ist aktuell pausiert – siehe `tutor_system.md`.)

## Empfohlene Komponenten

| Hardware       | Wofür             | Empfehlung                    |
|----------------|-------------------|-------------------------------|
| USB-Mikrofon   | Spracheingabe     | Fifine K053 o. ä. (~15 €)     |
| Lautsprecher   | TTS-Ausgabe       | 3,5 mm Klinke am Pi-Audio-Jack |
| PIR-Sensor     | Motion Detection  | HC-SR501 (~2 €), an GPIO-Pin   |

## Was geht ohne diese Hardware?

- Auf dem **Linux-PC** funktioniert alles – eingebautes Mikrofon und
  Speaker reichen für Whisper und TTS.
- Auf dem **Pi ohne USB-Mikro/Speaker**: Voice-Pipeline (STT/TTS) geht
  nicht. Alles andere (Dashboard, Chat, Data Collection) läuft normal.

## GPIO – aktueller Stand (2026-06-02)

- **Geräuschsensor**: physisch am Pi, an **Board-Pin 7** (laut Sasha,
  noch zu verifizieren). Erst im **Test**, **noch nicht ins Event-
  System verkabelt** — der Sensorwert fließt noch nicht über
  `pi_sensor_bridge.py` → `POST /api/sensor/<name>` in die Event-Loop.
- **Mikrofon**: angeschlossen, **funktioniert aber noch nicht**
  (offenes To-do, separat zu debuggen).
- **Lautsprecher**: angeschlossen (3,5-mm-Klinke).
- Der Rest: `sensors.py` simuliert weiterhin alle Sensoren über die
  Tastatur. Der echte GPIO-Lesepfad ist also **noch nicht produktiv
  angebunden**, der Geräuschsensor ist der erste Kandidat dafür.

## GPIO – geplante Anbindung

- Library: `RPi.GPIO`.
- Damit kein `sudo` nötig wird: User in die Gruppe `gpio` aufnehmen.
- **Pin-Nummerierung klären, BEVOR Code geschrieben wird:** „Pin 7"
  ist mehrdeutig. Physischer Board-Pin 7 = BCM **GPIO4**. RPi.GPIO
  kann beides adressieren (`GPIO.setmode(GPIO.BOARD)` vs `GPIO.BCM`)
  — Modus und Nummer müssen zusammenpassen, sonst liest man den
  falschen Pin.
- Anbindung eines Sensors = drei Stellen (siehe `topologie.md`):
  `_ALLOWED_SENSORS` + `_SENSOR_TO_EVENT` (PC) und die Lese-/Map-Logik
  in `pi_sensor_bridge.py` (Pi).

Solange das nicht steht, bleibt die Tastatur-Simulation der
produktive Trigger-Weg (siehe `tastatur.md`).
