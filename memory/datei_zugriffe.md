# Dateizugriffe

## Whitelist – was die KI lesen darf

`core/context.py` definiert die Whitelist. Nur was hier steht, kann
die KI über die Tools `read_file` und `list_files` öffnen.

```
data/*.json
vocab_mandarin.json
core/*.py
ui/app.py
notes.md
```

`notes.md` ist explizit zum freien Reinschreiben gedacht – alles dort
landet beim nächsten KI-Call im Kontext (sofern die KI das File liest).
Praktisch als „Schmierzettel" für Hinweise an die KI.

**Größenbegrenzung**: gelesene Dateien werden nach `_MAX_CHARS = 8000`
Zeichen abgeschnitten (`core/context.py`). Wer der KI längere Texte
geben will: aufteilen oder das Limit dort hochsetzen – aber bitte mit
Bedacht, damit das Context-Window des Modells nicht überläuft.

## Was NICHT committet werden soll

| Pfad                  | Grund                                                         |
|-----------------------|---------------------------------------------------------------|
| `data/*.json`         | persönliche Daten / Logs                                      |
| `data/ai_memory.json` | KI-Memory, lokal & privat                                     |
| `data/tts_model/`     | Modelldateien, viel zu groß für Git                           |
| `venv/`               | Python-Virtualenv (lokal); auf dem Pi heißt der Ordner `.venv` |
| `core/__pycache__/`   | Python-Bytecode                                               |

Diese Pfade gehören in `.gitignore`. Falls dort noch nicht drin: ergänzen.

## Auto-erstellte Files

`core/main.py` und Companion-Module legen folgendes an, wenn nicht
vorhanden:

- `data/sleep_quality.json` (sobald der erste Eintrag geloggt wird)
- `data/ai_memory.json` (sobald die KI das erste Mal `save_memory` aufruft)
- `data/<kategorie>.json` (für jede neue Data-Collection-Kategorie)
