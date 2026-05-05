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

## TTS-Modell (sherpa-onnx)

Einmaliger Download nach `data/tts_model/vits-zh-aishell3/` (~120 MB):

```bash
sudo chown -R $USER:$USER data/   # falls data/ root gehört
venv/bin/python services/download_tts_model.py
```

`tts_service.py` ist **hardcoded** auf sherpa-onnx mit diesem Modell –
es gibt aktuell keinen Auto-Switch zu MeloTTS oder anderen Engines.
Wer MeloTTS will, müsste `services/tts_service.py` selbst anpassen.

## System-Pakete (für Pi)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync firefox-esr
```

Für Audio-Output am Pi: 3.5 mm-Klinke aktivieren (siehe `hardware.md`).
