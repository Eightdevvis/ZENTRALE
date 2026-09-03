# Hardware (Raspberry Pi)

Für den vollen Voice-Betrieb auf dem Pi brauchst du Mikrofon, Speaker
und einen Bewegungs-/Geräuschsensor. Mikro, Lautsprecher und ein
Geräuschsensor sind **bereits angeschlossen** (Stand 2026-06-02),
aber noch nicht voll integriert – Details unter „GPIO – aktueller
Stand". (Der Sprach-Tutor, der diese Hardware ursprünglich am stärksten
brauchte, **läuft** – siehe `memory/tutor/tutor_system.md`. Was fehlt, ist nicht der Tutor,
sondern der Sensor: `PRESENCE_DETECTED` löst nur einen **nonverbalen** Ping in
eine bereits laufende Session aus, kein Auto-Start.)

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
- Anbindung eines Sensors = drei Stellen (siehe `memory/system/topologie.md`):
  `_ALLOWED_SENSORS` + `_SENSOR_TO_EVENT` (PC) und die Lese-/Map-Logik
  in `pi_sensor_bridge.py` (Pi).

Solange das nicht steht, bleibt die Tastatur-Simulation der
produktive Trigger-Weg (siehe `memory/system/tastatur.md`).

## Audio am Pi (gemessen 2026-09-03)

Der Pi ist der Ausgabe- und Aufnahme-Knoten für das Persona-Zimmer: er
**spielt ab und nimmt auf**, synthetisiert und erkennt aber nichts selbst.
`tutor/room.py` schickt Text an `<pc>/api/speak` und bekommt WAV-Bytes zurück,
und schickt Mikro-WAVs an `<pc>/api/transcribe` — Whisper und TTS laufen auf
dem PC.

Was der Pi an Karten sieht (`/proc/asound/cards`):

| Karte | Gerät | Richtung |
|---|---|---|
| 0 | `bcm2835 HDMI 1` (onboard) | Ausgabe |
| 1 | `bcm2835 Headphones` (onboard, Klinke) | Ausgabe |
| 2 | `UACDemoV1.0` (Jieli, USB-Lautsprecher) | Ausgabe |
| 3 | `USB PnP Sound Device` (C-Media, USB-Mikro) | **Aufnahme** |

**Ein Pi 3 hat keinen eigenen Audio-Eingang.** HDMI und Klinke sind beides
Ausgänge; ohne USB-Gerät ist `arecord -l` leer und das „Immer-Zuhören" im
Zimmer kann gar nicht anlaufen. Das USB-Mikro ist also Pflicht-Hardware, keine
Einstellung.

**Kein Sound-Server nötig:** Auf dem Pi läuft weder PulseAudio noch PipeWire.
Das ist unkritisch, weil Wiedergabe und Aufnahme auf **verschiedenen Karten**
liegen (USB-Lautsprecher bzw. HDMI zum Fernseher = Ausgabe, USB-Mikro =
Aufnahme). Die klassische ALSA-Falle „device busy" trifft nur zu, wenn zwei
Prozesse dasselbe Gerät exklusiv wollen. Ab Werk zeigt der Pi allerdings auf
die Klinke — die gewünschte Ausgabekarte muss gesetzt werden.

Das Zimmer importiert `sounddevice` und `webrtcvad` erst **im Mikro-Thread**.
Fehlen sie, läuft das Fenster normal weiter und hört nur nicht zu — der Drill
vor der Freischaltung braucht ohnehin nur Ausgabe und Tastatur.
