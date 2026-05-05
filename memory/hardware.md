# Hardware (Raspberry Pi)

Für den vollen Tutor-Betrieb auf dem Pi brauchst du Mikrofon, Speaker
und (geplant) einen PIR-Sensor.

## Empfohlene Komponenten

| Hardware       | Wofür             | Empfehlung                    |
|----------------|-------------------|-------------------------------|
| USB-Mikrofon   | Spracheingabe     | Fifine K053 o. ä. (~15 €)     |
| Lautsprecher   | TTS-Ausgabe       | 3,5 mm Klinke am Pi-Audio-Jack |
| PIR-Sensor     | Motion Detection  | HC-SR501 (~2 €), an GPIO-Pin   |

## Was geht ohne diese Hardware?

- Auf dem **Linux-PC** funktioniert alles – eingebautes Mikrofon und
  Speaker reichen für Whisper und TTS.
- Auf dem **Pi ohne USB-Mikro/Speaker**: Tutor-Audio geht nicht. Alles
  andere (Dashboard, Chat, Data Collection) läuft normal.

## GPIO – aktueller Stand

`sensors.py` simuliert aktuell alle Sensoren über die Tastatur. Der
echte GPIO-Pfad ist **noch nicht angebunden**.

## GPIO – geplante Anbindung

- Library: `RPi.GPIO`.
- Damit kein `sudo` nötig wird: User in die Gruppe `gpio` aufnehmen.
- Pin-Belegung wird dann hier dokumentiert, sobald angebunden.

Solange das nicht steht, bleibt die Tastatur-Simulation der einzige
Trigger-Weg (siehe `tastatur.md`).
