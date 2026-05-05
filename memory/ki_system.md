# KI-System

## Architektur

```
Browser  ──POST /api/chat──▶  app.py  ──▶  ai.py  ──▶  Ollama (Mistral)
                                              │
                                         memory.py  (data/ai_memory.json)
                                         context.py (Datei-Whitelist)
```

`ai.py` ist der einzige Ollama-Client. Alle anderen Module gehen durch
`ai.py` – kein direkter HTTP-Call zu Ollama von woanders. Das macht
Caching, Logging und spätere Modell-Wechsel trivial.

## Module

### `core/ai.py`
- Ollama-Client. Methoden für Chat, Streaming-Chat, Tool-Use.
- Verwendet `core/net.py` für HTTP – damit landet jeder Request im
  Terminal (siehe Network-Transparenz unten).
- Tool-Calls kommen im **letzten** Streaming-Chunk (`done=true`) im
  Feld `tool_calls`. Heißt: erst auf das Ende des Streams warten,
  dann Tools auflösen.

### `core/net.py`
- Wrapt jeden HTTP-Call (zu Ollama, Whisper, TTS).
- Gibt Request/Response ins Terminal aus.
- Sinn: Niemand muss raten, was die ZENTRALE gerade übers Netz schickt.

### `core/memory.py`
- Persistente KI-Memory in `data/ai_memory.json`.
- Bei AI-Calls **im Chat-Modus** wird die Memory in den System-Prompt
  injiziert (`format_for_prompt()`). Im **Tutor-Modus** wird sie
  bewusst NICHT injiziert – der Tutor-Prompt ist eigenständig
  (`ai.chat_stream` Zeile 192: nur wenn `tools is None`).
- Eintrags-Typen: `fact`, `summary`, `todo`, `technical`.
- Schreibzugriff für die KI über das Tool `save_memory`.
- User-Löschung über `/forget N` im Chat → `memory.forget(index)`.

### `core/context.py`
- Whitelist-basierter Dateizugriff. Die KI kann **nur** Dateien
  lesen, die hier explizit freigeschaltet sind.
- Größenbegrenzung: gelesene Dateien werden nach `_MAX_CHARS = 8000`
  Zeichen abgeschnitten (Schutz vor Context-Window-Überlauf).
- Path-Traversal-Schutz: Dateien außerhalb des Projekt-Roots werden
  rejected (`..`-Tricks fangen leer).
- Aktuelle Whitelist: siehe `datei_zugriffe.md`.

## Tool-Use

Mistral kann Tools „aufrufen" – ZENTRALE führt sie aus und schickt das
Ergebnis zurück in den Kontext. Die KI ruft Tools nur wenn nötig.

| Tool          | Funktion                                            |
|---------------|-----------------------------------------------------|
| `save_memory` | Eintrag persistent in `ai_memory.json` speichern    |
| `read_file`   | Datei aus der Whitelist lesen                       |
| `list_files`  | Verfügbare lesbare Dateien auflisten                |

Im Tutor-Modus werden diese Tools durch die Tutor-Tools **ersetzt**
(nicht ergänzt), via `tools=`/`tool_executor=`-Parameter an
`ai.chat_stream()`. Siehe `tutor_system.md`.

**Sicherheitsnetz**: `chat_stream` hat ein hartes `max_rounds = 5` für
die Tool-Loop – verhindert Endlosschleifen bei kaputten Tool-Calls.

## Network-Transparenz

Alle HTTP-Requests werden im Terminal sichtbar geloggt:

```
NET →  POST http://localhost:11434/api/chat
NET ←  200 http://localhost:11434/api/chat (2341 B)
STT →  POST http://localhost:5050/transcribe (48 KB)
STT ←  '我很好' (Konfidenz: 94%)
TTS →  POST http://localhost:5051/speak '你好！'
TTS ←  62 KB WAV
```

So sieht man bei jedem Run live, was die KI tut – kein Black-Box-Gefühl.

## Chat-Modus

- KI-Chat mit Mistral, Antworten werden token-weise gestreamt.
- KI hat Zugriff auf Whitelist-Dateien und persistente Memory.
- Slash-Commands im Chat:
  - `/memory` – gespeicherte Memory-Einträge anzeigen
  - `/forget N` – Eintrag Nr. N aus der Memory löschen
  - `/clear` – Chat-History leeren
- ESC – zurück zum Haupt-Dashboard.
