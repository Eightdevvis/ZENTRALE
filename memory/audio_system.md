# Audio-System

## Position: Core, sprachneutral

Die Voice-Pipeline (STT + TTS) gehört zur **Core-AI**. Sprache ist ein
Parameter:

| Aufrufer       | Endpoint              | `lang`-Default                 |
|----------------|-----------------------|--------------------------------|
| Haupt-Chat     | `POST /api/speak`     | `de` (Piper / thorsten-medium) |
| Haupt-Chat     | `POST /api/transcribe`| `de` (Whisper)                 |

> Die früheren Tutor-Aliase `/api/tutor/speak` und `/api/tutor/transcribe`
> (hardcoded `lang='zh'`) sind raus. Tutor pausiert, siehe
> `tutor_system.md`. Wer Mandarin sprechen will, ruft die generischen
> Endpoints mit `lang='zh'` auf – die Modelle (`vits-zh-aishell3`,
> Whisper) liegen weiter auf der Platte.

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

## Spracheingabe im Chat-Modus

> **Pi-Kiosk-Hinweis:** Der Kiosk laedt das Backend ueber die LAN-IP
> (`http://192.168.50.1:5000`), also keine secure origin und kein
> sichtbarer Permission-Dialog. Mic-Permission wird stattdessen via
> `policies.json` + Profil-`user.js` pre-konfiguriert — Details in
> `deployment.md` → "Mikrofon-Berechtigung im Kiosk".

Im Chat-Modus liegt neben dem Text-Input ein **Mic-Button**
(`#chat-mic-btn`). Toggle-Verhalten:

1. Click 1 → `getUserMedia` + MediaRecorder.start(1000), Button rot/blinkt.
2. Click 2 → UI sofort auf "transcribing" (orange), `MediaRecorder.stop()`,
   Blob → POST `/api/transcribe`. **Wichtig:** UI-State wird beim Click
   sofort umgestellt, nicht erst in `onstop` – `onstop` kann je nach
   Browser-Audio-Backend hunderte ms verzögern, sonst wirkt's wie „Click
   hat nicht funktioniert".
3. Zurückgekommener Text landet im Input-Feld (kein Auto-Send).
   Sasha kann editieren, mit Enter senden oder ESC abbrechen.

**Audio-Format:** Browser-MediaRecorder liefert in Chromium/Firefox
**WebM/Opus**, nicht WAV (kein Browser kann live PCM-WAV erzeugen).
Frontend setzt den MIME-Type explizit auf `audio/webm;codecs=opus`
und benennt die Datei `speech.webm`. faster-whisper liest WebM via
ffmpeg-Backend transparent – kein extra Konvertierungsschritt nötig.

`MediaRecorder.start(1000)` mit 1-s-Timeslice statt `start()` ohne
Argument: `ondataavailable` feuert jede Sekunde mit einem Chunk, statt
beim `stop()` alles auf einmal zu encodieren. Garantiert dass `onstop`
zuverlässig kurz nach `stop()` durchkommt – Bug-Fix gegen verzögerte
Transkription (Aufnahme erschien erst beim nächsten Start).

**Qualitäts-Hinweis:** WebM/Opus mit Browser-Default-Bitrate ist
kompressionsbehafteter als das WAV aus `scripts/test_audio.py`
(sounddevice → PCM_16, 16 kHz). Erwartung: leicht schlechtere Whisper-
Erkennung im Browser-Pfad als im Smoke-Test, vor allem bei seltenen
Wörtern. Wenn das Ärger macht: ffmpeg-Konvertierung server-seitig oder
höhere Bitrate per `audioBitsPerSecond` im MediaRecorder-Constructor.

**`via_mic`-Flag-Tracking** (Frontend):
- `chatViaMic = true` nach erfolgreicher Transkription.
- `chatViaMic = false` sobald der User tippt (`input`-Event ändert den
  Text) oder die Nachricht gesendet wurde.
- Beim POST an `/api/chat` wird der Flag als `via_mic` mitgesendet, was
  serverseitig den `_MIC_INPUT_HINT` im System-Prompt aktiviert.

Backend-Reaktion: siehe `ki_system.md` → System-Prompt-Komposition.

## Sprachausgabe im Chat-Modus (Auto-Speak)

Die KI-Antwort wird im Chat **automatisch gesprochen**, sobald sie kommt –
nicht erst auf Knopfdruck. Weil Piper pro Request einen ganzen Satz auf
einmal synthetisiert (kein Token-Streaming), läuft das **satzweise
während des SSE-Streamings**:

1. Tokens strömen in `sendChatMessage` rein und füllen `fullText`.
2. Nach jedem Token zerlegt `extractSentences(tail)` den noch nicht
   gesprochenen Teil. Satz-Ende = `. ! ? … \n` **gefolgt von Whitespace**
   – das trailing-Whitespace garantiert, dass nach dem Satzzeichen schon
   das nächste Token da ist (sonst würde `3.` in `3.14` mitten im Stream
   fälschlich als Satzende gewertet).
3. Jeder fertige Satz geht via `enqueueSpeak` in die `speakQueue`.
4. `drainSpeakQueue` arbeitet die Queue **seriell** ab: `/api/speak`
   (Piper, `lang=de`) → `<audio>` abspielen → `onended` → nächster Satz.
   Seriell, weil sich sonst mehrere Sätze überlappen würden.
5. Am Stream-Ende wird der Rest ohne abschließendes Satzzeichen
   nachgesprochen (`leftover`).

Effekt: die Stimme beginnt nach dem **ersten** fertigen Satz, nicht erst
wenn die ganze Antwort generiert ist – fühlt sich „live" an.

**Mute per `Alt+S`** (kein Button, der Pi-Kiosk hat keine Maus): toggelt
die Sprachausgabe. Zustand liegt in `localStorage` (`zentraleChatMuted`),
übersteht also Reload und Kiosk-Neustart. Beim Stummschalten bricht
`stopSpeaking()` die laufende Wiedergabe sofort ab und leert die Queue.
`goToMain()` (Chat verlassen) ruft ebenfalls `stopSpeaking()`. Der
state-aware Footer-Hinweis `#chat-mute-hint` zeigt, was Alt+S als
nächstes tut. DOM/JS-Hooks: siehe `ui_hooks.md`, Tasten: `tastatur.md`.

**Lautstärke per `Alt+S` halten + `↑`/`↓`** (Schritt 10%): `chatVolume`
(0..1) liegt in `localStorage` (`zentraleChatVolume`) und wird auf jedes
abgespielte `<audio>` angewandt sowie live auf die laufende Wiedergabe.
Kurzes Feedback „Lautstärke X%" im `#chat-mute-hint`, danach zurück auf
den Mute-Hinweis. Der Trick gegen Kollision mit dem Mute-Toggle: `Alt+S`
markiert beim keydown nur den Chord und feuert das Mute erst beim **keyup**
— aber nur, wenn zwischendurch *keine* Pfeiltaste kam. Tap = Mute,
Halten + Pfeil = Lautstärke.

> **Main-Mode (panel-ai) ist davon getrennt** – dort ist die Voice noch
> nicht verdrahtet (siehe `ui_hooks.md` → Voice-Pipeline).

## Pipeline

```
Browser MediaRecorder
   │  WAV (Browser sendet als multipart 'audio' + 'lang')
   ▼
POST /api/transcribe   (lang='zh' für Mandarin)
   │
   ▼
audio.py  ──HTTP──▶  whisper_service.py  (Port 5050)
                          │
                          ▼ faster-whisper, language=<lang> (Form-Field)
                       Text + Konfidenz
   ◀──────────────────────┘
   │
   ▼ KI-Antwort generieren (Ollama)
   │
POST /api/speak   (lang='zh' für Mandarin)
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
  ca. 500 MB). Andere Optionen: `tiny`, `base`, `medium`. Auf Alltags-
  Deutsch ist `small` erstaunlich gut; bei Tech-Jargon-Diktaten
  („asynchron", „Embeddings", „thread-safe") zeigt es Grenzen – dann
  `medium` (~1.5 GB).
- **Sprache parametrisch** über das Multipart-Feld `lang`. Default
  über `WHISPER_LANG`-env (default `de`). Haupt-Chat lässt Default
  greifen; für Mandarin würde der Aufrufer `lang=zh` mitschicken
  (Tutor pausiert, siehe `tutor_system.md`).
- **VAD-Vorfilter** (Silero VAD über faster-whisper integriert):
  schneidet Stille raus, bevor Whisper transkribiert. Schutz gegen
  YouTube-Halluzinationen aus leeren Aufnahmen („Vielen Dank fürs
  Zuschauen" etc.). Standard: an. Per Env:
  - `WHISPER_VAD=0` deaktiviert komplett (default `1`).
  - `WHISPER_VAD_MIN_SILENCE_MS` (default `500`): Mindest-Stille die
    Silero als Pausen-Ende wertet. Default 500 ms statt faster-whisper-
    default 2000 ms, weil Push-to-Talk-Inputs typischerweise Stottern
    und kurze Pausen enthalten – 2 s würde legitime Sprechpausen als
    Segment-Ende werten und Satzteile abschneiden.
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
zum Debuggen wenn STT oder TTS im Dashboard nicht reagieren.

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
