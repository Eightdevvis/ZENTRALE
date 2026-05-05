# Audio-System

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
   │  WAV (Browser sendet als multipart 'audio')
   ▼
POST /api/tutor/transcribe
   │
   ▼
audio.py  ──HTTP──▶  whisper_service.py  (Port 5050)
                          │
                          ▼ faster-whisper, language="zh" (Mandarin erzwungen)
                       Text + Konfidenz
   ◀──────────────────────┘
   │
   ▼ KI-Antwort generieren (Tutor-Modus)
   │
POST /api/tutor/speak  ({text, speed, speaker})
   │
   ▼
audio.py  ──HTTP──▶  tts_service.py  (Port 5051)
                          │
                          ▼ sherpa-onnx mit vits-zh-aishell3 (174 Sprecher)
                       WAV-Bytes (audio/wav)
   ◀──────────────────────┘
   │
   ▼ Browser spielt das WAV ab
```

## Module

### `core/audio.py`
- Reiner HTTP-Client. Kein Mikro-Handling, kein Sprecher-Handling.
- Funktionen:
  - `transcribe(audio_bytes, filename)` → Text via Whisper.
  - `synthesize(text, speed=0.9, speaker=0)` → WAV-Bytes via TTS.
  - `whisper_available()` / `tts_available()` – Health-Checks gegen
    `/health`.
- Loggt direkt in `state.push_log` (`STT →` / `STT ←` / `TTS →` /
  `TTS ←`) – nutzt **nicht** `net.py`, weil multipart-Upload
  Sonderbehandlung braucht.

### `services/whisper_service.py`
- Eigenständiger Flask-Service, Port 5050.
- Verwendet `faster-whisper` (CTranslate2-Backend, schnell genug auf
  CPU). Modellgröße einstellbar via `WHISPER_MODEL` (Default: `small`,
  ca. 500 MB). Andere Optionen: `tiny`, `base`, `medium`.
- `language="zh"` ist hardcoded – Whisper rät die Sprache nicht, sondern
  geht immer von Mandarin aus (sonst zu fehleranfällig bei kurzem Input).
- Endpoints: `POST /transcribe`, `GET /health`.

### `services/tts_service.py`
- Eigenständiger Flask-Service, Port 5051.
- **Hardcoded sherpa-onnx** mit dem Modell `vits-zh-aishell3`
  (174 Sprecher, Apache-2.0). Kein automatischer MeloTTS-Fallback.
- Endpoints: `POST /speak` (`{text, speed, speaker}` → `audio/wav`),
  `GET /health`.

### `services/download_tts_model.py`
- Einmaliger Download des sherpa-onnx-Modells (~120 MB) nach
  `data/tts_model/vits-zh-aishell3/`.

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
