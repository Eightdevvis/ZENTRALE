# Setup & Installation

## Python-Umgebung

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Ollama + Mistral

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
```

Standardmäßig erwartet ZENTRALE Ollama unter `http://localhost:11434`
(siehe `starten.md` für Env-Override).

## Whisper-Modell

Wird beim ersten Start des `whisper_service.py` automatisch geladen
(Default-Größe `small`, ca. 500 MB). Nichts zu tun – aber Geduld beim
ersten Run.

Modellgröße via Env-Var wechseln (Trade-off Größe vs. Qualität):

```bash
WHISPER_MODEL=tiny   venv/bin/python services/whisper_service.py  # ~75 MB
WHISPER_MODEL=base   venv/bin/python services/whisper_service.py  # ~150 MB
WHISPER_MODEL=small  venv/bin/python services/whisper_service.py  # ~500 MB (default)
WHISPER_MODEL=medium venv/bin/python services/whisper_service.py  # ~1.5 GB
```

## TTS-Modelle (sherpa-onnx + Piper)

Zwei Modelle pro Sprache, beide werden parallel von
`tts_service.py` geladen (Engine-Registry):

- `zh` – sherpa-onnx `vits-zh-aishell3` (~120 MB, Tutor-Modus)
- `de` – Piper `de_DE-thorsten-medium` (~60 MB, Haupt-Chat)

Einmaliger Download nach `data/tts_model/<voice>/`:

```bash
sudo chown -R $USER:$USER data/   # falls data/ root gehört
venv/bin/python services/download_tts_model.py        # beide laden
# oder gezielt:
venv/bin/python services/download_tts_model.py zh
venv/bin/python services/download_tts_model.py de
```

Neue Sprache hinzufügen: Modell-Loader in `services/tts_service.py`
ergänzen (`_try_load_<lang>()`) und in `download_tts_model.py` einen
neuen `download_<lang>()` anlegen.

## System-Pakete (für Pi)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync firefox-esr
```

Für Audio-Output am Pi: 3.5 mm-Klinke aktivieren (siehe `hardware.md`).
