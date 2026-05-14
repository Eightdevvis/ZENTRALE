# Event-System

Vom Sensor bis zur Action zieht sich eine klare Pipeline. Jedes Modul
hat genau eine Aufgabe – das macht sie austauschbar (z. B. Tastatur-
Simulation gegen echten GPIO-Trigger tauschen ohne `brain.py` anzufassen).

## Module

### `core/sensors.py`
- Erkennt **lokale** Eingaben (auf dem PC) und gibt sie als Events
  an den Event-Loop zurück.
- **Aktuell**: Tastatur-Simulation via `keyboard`-Library
  (deshalb `sudo` nötig zum Starten – Linux gibt nur Root direkten
  Zugriff auf Keyboard-Events).
- **Geplant**: echter PIR-Sensor (HC-SR501) an GPIO-Pin – siehe
  `hardware.md`.

### Externer Sensor-Webhook
- Zweite Quelle für Sensor-Events neben `sensors.py`: HTTP-POST an
  `/api/sensor/<name>` (siehe `api_endpoints.md` und `topologie.md`).
- `ui/app.py` legt den Trigger in `state.queue_sensor()`.
- `main.py` drainet die Queue pro Tick und mappt sie auf den
  jeweiligen internen Event (`_SENSOR_TO_EVENT`).
- Verwendet von `scripts/pi_sensor_bridge.py` (Pi → PC).

### `core/clock.py`
- Erzeugt zeitbasierte Events. Pro Aufruf `check_time(hour, minute)`
  feuert genau **einmal** pro passender Minute den Event `TIME_REACHED`
  (interner Cooldown via `_last_trigger_key`).
- Aktuell ruft `main.py` das mit `(7, 0)` auf – das Mapping
  `TIME_REACHED → MORNING_WAKEUP` macht **`brain.py`**, nicht `clock.py`.

### `core/events.py`
- Reine Konstanten-Datei. Jeder Event-Name ist hier definiert. So
  vermeiden wir Tippfehler und haben einen zentralen Ort.
- Aktuelle Events: `TIME_REACHED`, `MORNING_WAKEUP`, `BUTTON_PRESS`,
  `LIGHT_SENSOR_TRIGGER`, `SYSTEM_BOOT`, `DATA_COLLECTION`,
  `PRESENCE_DETECTED`, `TUTOR_START`, `DOOR_TOGGLE`, `HOMECOMING`.
- `TUTOR_START` existiert als Konstante weiter, hat aber aktuell
  keinen Sender und keinen Handler (Tutor pausiert, siehe
  `tutor_system.md`).
- `DOOR_TOGGLE` feuert jedes Mal wenn der Türsensor durchgeht
  (auf ODER zu). `HOMECOMING` ist die abgeleitete Bedeutung, sobald
  `brain.py` daraus „User war > X Std weg und ist jetzt zurück"
  erkennt (Mapping noch nicht implementiert).

### `core/brain.py`
- **Reine Logik-Schicht**: wandelt Input-Events in neue Events um.
- Aktuelle Mappings:
  - `TIME_REACHED` → `MORNING_WAKEUP`
  - `PRESENCE_DETECTED` → No-Op (loggt nur „Presence erkannt").
    Vor dem Tutor-Pause-Cleanup hat das hier `TUTOR_START` ausgelöst;
    siehe `tutor_system.md` für den Status.
- Macht keine HTTP-Calls oder File-Writes.

### `core/actions.py`
- Bewusst sehr klein gehalten: macht nur `print()`-Side-Effects.
- Aktuell behandelt: `SYSTEM_BOOT` (Hostname + Zeitstempel),
  `MORNING_WAKEUP`, `BUTTON_PRESS`, `LIGHT_SENSOR_TRIGGER`.
- **State-Mutation passiert NICHT hier** – die macht `main.py` direkt
  über `state.set_sensor()` / `state.push_event()`.

### `core/main.py`
- Der eigentliche Event-Loop, 1-Sekunde-Polling.
- Pro Tick: liest Sensoren → setzt `state.set_sensor(...)` → queued
  passende Events → ruft `clock.check_time(7, 0)` → leert die
  Event-Queue und ruft pro Event sowohl `brain.process_event` als
  auch `actions.handle_action` auf.
- Loggt jedes Event via `state.push_log(...)` (sichtbar im Dashboard-
  Terminal als `EVENT IN:` / `EVENT OUT:`).
- Startet den Flask-UI-Thread (`from ui.app import start_ui`) als
  Daemon.

## Warum diese Trennung

Sensoren / Logik / Side-Effects sind drei sehr unterschiedliche
Verantwortlichkeiten. Wenn alles in einer Datei stünde, würde jede
neue Sensorquelle (echter PIR-Sensor, Webhook von Smart-Home, …) den
gesamten Code anfassen. So tauschen wir nur das passende Modul aus.

## Tastatur-Simulation (aktueller Workaround)

Solange kein echter GPIO da ist, simulieren wir Sensoren via Tastatur.
Die Tastenbelegung steht in `tastatur.md`.
