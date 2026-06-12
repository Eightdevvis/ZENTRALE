# REST API Endpoints

Alle Endpoints werden von `ui/app.py` bedient. Streaming-Endpoints
nutzen Server-Sent Events (SSE).

## Dashboard / State

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/`                   | GET     | Monolith-Dashboard (monolith.html) – die einzige UI |
| `/monolith`           | GET     | Alias auf `/` (Kiosk/Bookmark-Kompat), liefert dieselbe monolith.html |
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
| `/api/debug`          | POST    | Debug-Log-Zeile ins Terminal (temporäre Dev-Hilfe) |

## Chat

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/chat`           | POST    | Chat-Nachricht senden (SSE-Stream). JSON-Body: `{message: str, via_mic?: bool}`. `via_mic=true` triggert `_MIC_INPUT_HINT` im System-Prompt (Whisper-Fehler-Awareness, siehe `ki_system.md`). |
| `/api/chat/history`   | GET     | Chat-History                          |
| `/api/chat/clear`     | POST    | Chat-History leeren                   |

## KI-Status & Erlaubnis

| Endpoint                 | Methode | Beschreibung                          |
|--------------------------|---------|---------------------------------------|
| `/api/ai/status`         | GET     | Ollama-Verfügbarkeit + Modell-Name    |
| `/api/permission_answer` | POST    | Antwort auf eine `frage_knopf`-/Internet-Erlaubnis-Frage (JSON `{answer}`). Entsperrt den wartenden Chat-Stream. Siehe `ki_system.md` → Permission-Gate. |

> `/api/memory` + `/api/memory/<id>` (Legacy-LTM) sind entfallen – Memory
> läuft jetzt über den Konzept-Graphen (siehe `ki_system.md`).

## Fotos (ASCII-Bild-Filter)

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/photos`         | GET     | Liste der Bild-Dateinamen aus `data/photos/` (Quelle für den Canvas-Bild→ASCII-Filter im Monolith). |
| `/api/photos/<name>`  | GET     | Einzelnes Bild (same-origin, damit der Canvas `getImageData` darf). Path-Traversal-geschützt. |

## Maps (Karten-System)

Front-agnostisch: jede Front schickt ihren Viewport (`cx,cy,zoom`) + ihr
Zielraster (`cols,rows,aspect`); die Engine in `core/map/` projiziert fertig.
**Nicht** KI-gegatet (Karte gibt es in allen Kassetten). Architektur +
drei Achsen: `maps_system.md`; Quellen/Lizenzen: `maps_quellen.md`.

| Endpoint                 | Methode | Beschreibung                          |
|--------------------------|---------|---------------------------------------|
| `/api/map/base`          | GET     | Basiskarte (Küsten, Achse-1-LOD nach Zoom) als projizierte Linien fürs Zellraster. Query: `cx,cy,zoom,cols,rows,aspect`. |
| `/api/map/braille`       | GET     | Basiskarte als gefülltes Land in Braille (2×4 Subpixel/Zelle), fertige Zeilen. Query: `cx,cy,zoom,cols,rows`. |
| `/api/map/layers`        | GET     | Registry der thematischen Overlays (Achse 2): Layer + Sub-Layer + Quelle (Provenienz) + ob zeitfähig (Achse 3). |
| `/api/map/layer/<id>`    | GET     | Features eines Overlays, projiziert. Query wie `/base` + `sub` (Sub-Layer, z.B. `chokepoints`) + `at` (Zeitpunkt, Achse 3). Antwort trägt `source/vintage/retrieved_at`. 404 bei unbekanntem Layer. |

Live: `trade/chokepoints` (IMF PortWatch, täglicher Schiffsverkehr an den
maritimen Engstellen). Lizenziert → lokal gecacht, nicht committet; Refresh
per `python -m map.layers.portwatch`.

## Voice (sprachneutral, Core)

Die Voice-Pipeline gehört zur Core-AI, nicht zum Tutor. Sprache wird
per Parameter mitgegeben.

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/speak`          | POST    | Text → WAV. JSON-Body: `{text, lang?, speed?, speaker?}`. `lang` Default `de`. Andere Sprachen ohne Modell → 503. |
| `/api/transcribe`     | POST    | Audio → Text. Multipart: `audio` + `lang?`. `lang` Default `de`.  |

Details zu Modellen + Sprachen: `audio_system.md`.

## Tutor (entfernt)

Alle `/api/tutor/*`-Endpoints (status/start/respond/transcribe/speak/stop)
sind entfallen – der Mandarin-Tutor ist pausiert (siehe `tutor_system.md`).
Voice läuft über die sprachneutralen Core-Endpoints `/api/speak` +
`/api/transcribe` mit `lang`-Parameter.
