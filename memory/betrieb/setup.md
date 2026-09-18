# Setup & Installation

**Stand 2026-09-18:** Ein Backend-Knoten (der PC) braucht venv +
`requirements.txt` + Test-Riegel (`scripts/zentrale-venv-guard`), Ollama mit
`qwen3.5:9b`, Whisper (lädt sich beim ersten Start selbst) und die TTS-Modelle
für **drei** Sprachen (`zh` sherpa-onnx, `de` Piper, `es` Piper) unter
`data/tts_model/`. Der Pi bekommt nichts davon — er ist Aussenposten (siehe
`memory/betrieb/deployment.md`). Der Riegel hängt sich beim TUI-Start selbst
ein, falls er fehlt.

## Python-Umgebung

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
scripts/zentrale-venv-guard
```

Der dritte Schritt hängt den Test-Riegel ins venv (Symlink auf
`scripts/zentrale_testguard.py` plus `.pth`-Zeile) und **gehört nach jedem
venv-Neubau dazu**: ohne ihn schaltet ein Testlauf aus einer älteren
Arbeitskopie Sashas echtes Theme um — die Erklärung steht in
`memory/system/dashboard.md` („Warum das Theme trotzdem noch sprang"). Der
Aufruf ist idempotent.

**Auf JEDEM Knoten nötig, und deshalb automatisiert.** Der Riegel lebt im venv,
das venv liegt nicht in git — ein `git pull` bringt ihn also nicht mit.
`start_tui.sh` hängt ihn deshalb beim Start selbst ein, falls er fehlt (still,
idempotent) — der TUI-Start ist die eine Stelle, die auf jedem Knoten läuft.
Der Aufruf oben bleibt für Maschinen, die die TUI nie starten. (Warum das
nötig wurde: siehe Historie.)

## Ollama + Modell

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:9b
```

Standardmäßig erwartet ZENTRALE Ollama unter `http://localhost:11434`
und greift auf das Modell `qwen3.5:9b` zu (siehe `memory/betrieb/starten.md` für
Env-Override `OLLAMA_MODEL`). Andere Tool-Use-fähige Ollama-Modelle
funktionieren ohne Code-Änderung, einfach pullen und Env-Var setzen.

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

Eine Engine je Sprache, alle werden parallel von `tts_service.py` geladen
(Engine-Registry `_engines[<code>]`):

- `zh` – sherpa-onnx, Stimme der Persona Ling Ling. `_try_load_sherpa_zh` lädt das
  beste vorhandene Modell: **`matcha-icefall-zh-baker` (22 kHz) > MeloTTS
  `vits-melo-tts-zh_en` (44.1 kHz) > `vits-zh-aishell3` (~120 MB, 8 kHz, Fallback)**.
- `es` – Piper, Stimme der Persona Lucía, Voice via Env `TUTOR_ES_VOICE`
  (Default `vits-piper-es_ES-sharvard-medium-int8`).
- `de` – Piper, Voice via Env `PIPER_DE_VOICE` (Default `de_DE-kerstin-low`,
  ~20 MB; Haupt-Chat und die Persona Lena).

Einmaliger Download nach `data/tts_model/<voice>/`:

```bash
sudo chown -R $USER:$USER data/   # falls data/ root gehört
venv/bin/python services/download_tts_model.py        # alle laden
# oder gezielt:
venv/bin/python services/download_tts_model.py zh
venv/bin/python services/download_tts_model.py de
venv/bin/python services/download_tts_model.py es
```

Neue Sprache hinzufügen: Modell-Loader in `services/tts_service.py`
ergänzen (`_try_load_<lang>()`) und in `download_tts_model.py` einen
neuen `download_<lang>()` anlegen. Was sonst noch zu einer neuen
Tutor-Sprache gehört: `memory/tutor/bauplan.md` (Checkliste).

## System-Pakete (für Pi)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync firefox-esr
```

Für Audio-Output am Pi: siehe `memory/betrieb/hardware.md` (Audio am Pi).

## Historie

- **2026-08-18** — Test-Riegel fehlte auf dem Laptop (venv nicht in git):
  auf einem Knoten scharf, auf dem anderen sprang das Theme weiter, während
  die erste Maschine „bewiesen ruhig" war. Seither hängt `start_tui.sh` ihn
  selbst ein.
- **2026-07-23** — `es` (Piper es_ES-sharvard, weiblich) als Stimme für
  Lucía; bis dahin gab es nur `zh` + `de`.
- **2026-09-18** — `de` auch als Tutor-Sprache (Lena), nutzt die
  Haupt-Chat-Stimme.
