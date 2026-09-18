# Hardware (Raspberry Pi)

**Stand 2026-09-18:** Der Pi 3 ist Ausgabe-, Aufnahme- und Sensor-Knoten
für das Persona-Zimmer. Angeschlossen und in Betrieb: USB-Mikro (C-Media,
Aufnahme — Pflicht, der Pi hat keinen eigenen Eingang), USB-Lautsprecher
(Jieli) bzw. HDMI zum Fernseher (Ausgabe). **Ein PIR ist NICHT
angeschlossen** — nur vorbereitet (Sasha, 2026-09-15: »Sensor später«): die
Bridge `pi_sensor_bridge.py` liest seit 2026-09-14 GPIO4 (BCM) = Board-Pin 7
per gpiozero und würde Bewegung als `motion` an den PC melden; das Zimmer
würde den Treffer als Anwesenheit werten (`presence_age` in `room_state`).
Solange kein Sensor dranhängt, passiert davon nichts. Whisper und TTS laufen
auf dem PC, der Pi rechnet nichts.
Kein Sound-Server nötig. ⚠ prüfen: der 2026-06-02 erwähnte Geräuschsensor
(damals Board-Pin 7) — heute sitzt dort der PIR; ob der Geräuschsensor noch
angeschlossen ist, ist aus Code/Commits nicht erkennbar.

## Empfohlene Komponenten

| Hardware       | Wofür             | Empfehlung                    |
|----------------|-------------------|-------------------------------|
| USB-Mikrofon   | Spracheingabe     | Fifine K053 o. ä. (~15 €)     |
| Lautsprecher   | TTS-Ausgabe       | USB oder 3,5 mm Klinke am Pi-Audio-Jack |
| PIR-Sensor     | Motion Detection  | HC-SR501 (~2 €), an GPIO-Pin   |

## Was geht ohne diese Hardware?

- Auf dem **Linux-PC** funktioniert alles – eingebautes Mikrofon und
  Speaker reichen für Whisper und TTS.
- Auf dem **Pi ohne USB-Mikro/Speaker**: Voice-Pipeline (STT/TTS) geht
  nicht, das Zimmer hört nicht zu. Alles andere (Dashboard, Chat, Data
  Collection) läuft normal.

## GPIO – PIR an der Bridge

- Library: **gpiozero** (`MotionSensor(PIR_GPIO)`, `when_motion`-Callback),
  braucht `gpiozero` + `lgpio` im Pi-venv. Fehlt eins oder ist der Pin nicht
  zu kriegen: Hinweis im Log, die Bridge läuft ohne PIR weiter.
- Verdrahtung: DOUT → GPIO4 (BCM) = Board-Pin 7, VCC 5 V, GND.
- Env: `PI_PIR_GPIO` (Default 4, `0` schaltet ab), `PI_PIR_MIN_GAP`
  (Default 5 s — der Sensor hält selbst ein paar Sekunden hoch).
- Warum PIR statt Mikro-Pegel: Geräusche als Anwesenheit lieferten zu viel
  Falsches (Commit 933a2be); Geräusche melden dem Kern seither nur noch
  Anwesenheit, wecken die Persona aber nicht (Commit e46f419,
  `memory/system/audio_strasse.md`).
- **Pin-Nummerierung:** „Pin 7" ist mehrdeutig. Physischer Board-Pin 7 = BCM
  **GPIO4**. gpiozero zählt BCM. Modus und Nummer müssen zusammenpassen,
  sonst liest man den falschen Pin.
- Anbindung eines weiteren Sensors = drei Stellen (siehe
  `memory/system/topologie.md`): `_ALLOWED_SENSORS` (`ui/app.py`) +
  `_SENSOR_TO_EVENT` (`core/main.py`) und die Lese-Logik in
  `pi_sensor_bridge.py`. Ein `_poll_gpio()`-Skelett für weitere
  Sensoren (Reed-Kontakt an der Tür, Buttons) liegt dort, ist aber nicht
  aktiv.
- Die Tastatur-Simulation (`memory/system/tastatur.md`) bleibt der
  Test-Weg am PC; auf dem Pi braucht die Bridge kein `sudo`.

## Audio am Pi (gemessen 2026-09-03)

Der Pi **spielt ab und nimmt auf**, synthetisiert und erkennt aber nichts
selbst. `tutor/room.py` schickt Text an `<pc>/api/speak` und bekommt
WAV-Bytes zurück, und schickt Mikro-WAVs an `<pc>/api/transcribe` — Whisper
und TTS laufen auf dem PC.

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
braucht ohnehin nur Ausgabe und Tastatur. Systempakete dafür (libSDL2,
PortAudio): `deploy/aussenposten-system.txt`. Wie das Mikro-Signal weiter
verarbeitet wird (VAD, Gating während die Stimme spricht):
`memory/system/audio_strasse.md`.

## Historie

- **2026-06-02** — Mikro, Lautsprecher und ein Geräuschsensor angeschlossen,
  aber nichts davon integriert: Geräuschsensor (Board-Pin 7) nur im Test,
  Mikro funktionierte noch nicht, `sensors.py` simulierte alles über die
  Tastatur; geplant war `RPi.GPIO` mit User in Gruppe `gpio`.
- **2026-09-03** — Audio am Pi vermessen (Tabelle oben); das Zimmer hört
  und spricht über den Pi.
- **2026-09-14** — PIR an der Bridge per gpiozero, weil Mikro-Pegel als
  Anwesenheit zu viel Falsches lieferte. Erster echter GPIO-Sensor im
  Event-System.
