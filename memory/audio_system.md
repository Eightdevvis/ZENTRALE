# Audio-System

## Position: Core, nicht Tutor

Die Voice-Pipeline (STT + TTS) gehört zur **Core-AI**, nicht zum
Tutor. Sprache ist ein Parameter:

| Aufrufer       | Endpoint              | `lang`-Default                 |
|----------------|-----------------------|--------------------------------|
| Haupt-Chat     | `POST /api/speak`     | `de` (Piper / thorsten-medium) |
| Haupt-Chat     | `POST /api/transcribe`| `de` (Whisper)                 |
| Tutor (Alias)  | `POST /api/tutor/speak`      | `zh` (sherpa-onnx / vits-zh-aishell3) |
| Tutor (Alias)  | `POST /api/tutor/transcribe` | `zh` (Whisper)                 |

Was eigentlich passiert: beide Tutor-Endpoints sind dünne Wrapper, die
auf den Core-Endpoints mit hartkodiertem `lang='zh'` aufsetzen. Frontend
kann den Tutor-Pfad ohne Anpassung weiternutzen.

## Grundprinzip: nichts auf dem Pi direkt

Audio läuft **nicht** durch Python-Audio-Libraries auf dem Pi. Stattdessen:

- **Aufnahme**: Browser-MediaRecorder API. Heißt – das Mikrofon wird vom
  Frontend angesprochen, nicht von Python. Spart uns das Hantieren mit
  ALSA/PulseAudio auf dem Pi.
- **Wiedergabe**: Browser spielt die WAV-Bytes ab, die der TTS-Service
  liefert.

Das hat zwei Vorteile:
1. Keine Audio-Treiber-Hölle in Python.
2. Funktioniert sofort sowohl auf dem Linux-PC als auch auf dem Pi,
   weil der Browser den Krempel macht.

## Pipeline

```
Browser MediaRecorder
   │  WAV (Browser sendet als multipart 'audio' + 'lang')
   ▼
POST /api/transcribe   (oder /api/tutor/transcribe → lang='zh')
   │
   ▼
audio.py  ──HTTP──▶  whisper_service.py  (Port 5050)
                          │
                          ▼ faster-whisper, language=<lang> (Form-Field)
                       Text + Konfidenz
   ◀──────────────────────┘
   │
   ▼ KI-Antwort generieren (Mistral)
   │
POST /api/speak   (oder /api/tutor/speak → lang='zh')
   │  Body: {text, lang, speed, speaker}
   ▼
audio.py  ──HTTP──▶  tts_service.py  (Port 5051)
                          │
                          ▼ Engine-Registry, eine Engine pro Sprache:
                          ▼   zh → sherpa-onnx vits-zh-aishell3 (174 Sprecher)
                          ▼   de → piper de_DE-thorsten-medium  (1 Sprecher)
                          ▼   andere → 503 + Hinweis
                       WAV-Bytes (audio/wav)
   ◀──────────────────────┘
   │
   ▼ Browser spielt das WAV ab
```

## Module

### `core/audio.py`
- Reiner HTTP-Client. Kein Mikro-Handling, kein Sprecher-Handling.
- Funktionen:
  - `transcribe(audio_bytes, filename, lang=None)` → Text via Whisper.
  - `synthesize(text, lang=None, speed=0.9, speaker=0)` → WAV via TTS.
  - `whisper_available()` / `tts_available()` – Health-Checks gegen
    `/health`.
- `lang=None` → fällt auf `DEFAULT_LANG` (env-Variable, default `de`).
- Loggt direkt in `state.push_log` (`STT →` / `STT ←` / `TTS →` /
  `TTS ←`) – nutzt **nicht** `net.py`, weil multipart-Upload
  Sonderbehandlung braucht.

### `services/whisper_service.py`
- Eigenständiger Flask-Service, Port 5050.
- Verwendet `faster-whisper` (CTranslate2-Backend, schnell genug auf
  CPU). Modellgröße einstellbar via `WHISPER_MODEL` (Default: `small`,
  ca. 500 MB). Andere Optionen: `tiny`, `base`, `medium`.
- **Sprache parametrisch** über das Multipart-Feld `lang`. Default
  über `WHISPER_LANG`-env (default `de`). Tutor schickt explizit
  `lang=zh`, Haupt-Chat lässt Default greifen.
- Endpoints: `POST /transcribe` (Felder: `audio`, `lang`), `GET /health`.

### `services/tts_service.py`
- Eigenständiger Flask-Service, Port 5051.
- **Engine-Registry**: pro Sprache ein eigenes Modell, alle parallel
  geladen:
  - `zh` – sherpa-onnx mit `vits-zh-aishell3` (174 Sprecher, Apache-2.0)
  - `de` – Piper mit `de_DE-thorsten-medium` (1 Sprecher, MIT)
  - andere `lang`-Werte → 503 mit Liste der verfügbaren Sprachen.
- `TTS_DEFAULT_LANG` env-Variable (default `de`).
- Endpoints: `POST /speak` (`{text, lang, speed, speaker}` → `audio/wav`
  oder 503), `GET /health` (zeigt geladene Engines).

### `services/download_tts_model.py`
- Lädt die TTS-Modelle herunter. CLI:
  - `python services/download_tts_model.py` → beide Sprachen
  - `python services/download_tts_model.py zh` → nur Mandarin (~120 MB)
  - `python services/download_tts_model.py de` → nur Deutsch (~60 MB)
- Ablage:
  - `data/tts_model/vits-zh-aishell3/` (sherpa-onnx)
  - `data/tts_model/de_DE-thorsten-medium/` (Piper)
- Idempotent: schon vorhandene Modelle werden übersprungen.

## Smoke-Test

`scripts/test_audio.py` testet die Pipeline isoliert, ohne dass ZENTRALE
laufen muss. Modi:

```bash
venv/bin/python scripts/test_audio.py                # kompletter Loop: Mic → Whisper → TTS
venv/bin/python scripts/test_audio.py --whisper-only # nur STT
venv/bin/python scripts/test_audio.py --tts-only     # nur TTS
```

Spricht direkt gegen `localhost:5050` und `localhost:5051` – nützlich
zum Debuggen wenn der Tutor-Modus im Dashboard nicht reagiert.

## Warum drei separate Prozesse?

ZENTRALE, Whisper und TTS laufen jeweils als eigener Python-Prozess.
Gründe:

- **Modellladen**: Whisper-Modell hat 500 MB im RAM. Wenn das im selben
  Prozess wie der Event-Loop läge, würde jeder Restart des Cores ein
  Modellreload triggern – nervig.
- **Crash-Isolation**: wenn TTS abkracht, läuft das Dashboard weiter.
- **Skalierbarkeit**: man könnte Whisper/TTS später auf ein anderes
  Gerät auslagern.

Konfiguration der Service-URLs siehe `starten.md`.
