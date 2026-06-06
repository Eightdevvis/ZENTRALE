# REST API Endpoints

Alle Endpoints werden von `ui/app.py` bedient. Streaming-Endpoints
nutzen Server-Sent Events (SSE).

## Dashboard / State

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/`                   | GET     | Dashboard HTML                        |
| `/api/state`          | GET     | Aktueller State (Events, Sensoren, Vokabel, Logs) – wird vom Frontend jede Sekunde gepollt |

## Sensor-Webhook

| Endpoint                  | Methode | Beschreibung                          |
|---------------------------|---------|---------------------------------------|
| `/api/sensor/<name>`      | POST    | Externes Sensor-Signal entgegennehmen und in die Event-Queue legen. Erlaubte `<name>`: `button`, `light`, `motion`, `door` (Whitelist `_ALLOWED_SENSORS` in `ui/app.py`). Body wird aktuell ignoriert. |

Verwendet von `scripts/pi_sensor_bridge.py` (Pi → PC) und kann von
beliebigen LAN-Clients aufgerufen werden (Mikrocontroller, anderer Pi,
manueller curl-Test). Siehe `topologie.md`.

## Telemetrie

Zwei Maschinen: PC liest lokal (`/proc` + `/sys` + `nvidia-smi` via
`core/host_metrics.py` → `core/telemetry.pc_snapshot()`), der Pi POSTet
seine Werte rüber (FS read-only, kann nicht selbst anzeigen). Quelle ist
dependency-frei (kein psutil), voll offline.

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/telemetry`      | GET     | PC + Pi kombiniert: `{pc:{cpu,gpu,vram,temp,ram}, pi:{cpu,temp,ram,disk,age_s}}`. Jede Metrik ist ein `{v, …}`-Objekt; `v=null` = Quelle fehlt. `pi={}` solange der Pi nie gesendet hat, `age_s` = Alter des letzten Pushes (Frontend zeigt Pi ab >90s als stale). Dashboard pollt ~2s. |
| `/api/telemetry/pi`   | POST    | Telemetrie-Push vom Pi. JSON-Body mit Top-Level-Keys aus `{cpu,temp,ram,disk}` (Whitelist `_ALLOWED_PI_METRICS`), gleiche Shape wie ein Meter-Block. Landet via `state.set_pi_telemetry()`. Sender: `scripts/pi_sensor_bridge.py`. |

## Data Collection

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/categories`     | GET     | Verfügbare Kategorien                 |
| `/api/data/<id>`      | GET     | Geloggte Einträge einer Kategorie     |
| `/api/log`            | POST    | Neuen Eintrag speichern               |

## Chat

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/chat`           | POST    | Chat-Nachricht senden (SSE-Stream). JSON-Body: `{message: str, via_mic?: bool}`. `via_mic=true` triggert `_MIC_INPUT_HINT` im System-Prompt (Whisper-Fehler-Awareness, siehe `ki_system.md`). |
| `/api/chat/history`   | GET     | Chat-History                          |
| `/api/chat/clear`     | POST    | Chat-History leeren                   |

## KI-Memory

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/memory`         | GET     | KI-Memory-Einträge auflisten          |
| `/api/memory/<id>`    | DELETE  | Memory-Eintrag löschen                |
| `/api/ai/status`      | GET     | Ollama-Verfügbarkeit                  |

## Voice (sprachneutral, Core)

Die Voice-Pipeline gehört zur Core-AI, nicht zum Tutor. Sprache wird
per Parameter mitgegeben.

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/speak`          | POST    | Text → WAV. JSON-Body: `{text, lang?, speed?, speaker?}`. `lang` Default `de`. Andere Sprachen ohne Modell → 503. |
| `/api/transcribe`     | POST    | Audio → Text. Multipart: `audio` + `lang?`. `lang` Default `de`.  |

Details zu Modellen + Sprachen: `audio_system.md`.

## Tutor

Tutor ist ein Aufrufer der Voice-Pipeline mit `lang='zh'`. Die
Tutor-Endpoints unterhalb sind dünne Aliase mit Hardcode `lang='zh'`
für Rückwärtskompatibilität des Tutor-Frontend.

| Endpoint                     | Methode | Beschreibung                          |
|------------------------------|---------|---------------------------------------|
| `/api/tutor/status`          | GET     | Session-Status + Audio-Service-Status |
| `/api/tutor/start`           | POST    | Session starten, KI-Begrüßung streamen (SSE) |
| `/api/tutor/respond`         | POST    | User-Text → KI-Antwort (SSE)          |
| `/api/tutor/transcribe`      | POST    | Alias für `/api/transcribe` mit `lang='zh'` |
| `/api/tutor/speak`           | POST    | Alias für `/api/speak` mit `lang='zh'` |
| `/api/tutor/stop`            | POST    | Session beenden                       |
