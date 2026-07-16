# Dateizugriffe

## Whitelist – was die KI lesen darf

`core/context.py` definiert die Whitelist. Nur was hier steht, kann
die KI über die Tools `read_file` und `list_files` öffnen.

```
data/*.json
tutor/vocab_mandarin.json
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
| `data/ai_graph.json`  | Konzept-Graph (primary memory), lokal & privat                |
| `data/ai_ltm.json`    | Legacy LTM (save_memory-Tool)                                 |
| `data/ai_stm.json`    | Legacy STM (Session-Turns)                                    |
| `data/tts_model/`     | Modelldateien, viel zu groß für Git                           |
| `venv/`               | Python-Virtualenv (lokal); auf dem Pi heißt der Ordner `.venv` |
| `core/__pycache__/`   | Python-Bytecode                                               |

Diese Pfade gehören in `.gitignore`. Falls dort noch nicht drin: ergänzen.

`data/photos/` (Test-Fotos für den ASCII-Bild-Filter) ist ebenfalls
ignoriert – lokaler Inhalt, kein Repo-Material.

## Was committet WIRD (data-Ausnahme)

| Pfad           | Grund                                                       |
|----------------|-------------------------------------------------------------|
| `data/ascii/`  | handgepflegte ASCII-Bibliothek für den Bild-Marker `[[bild: name]]` – Inhalt, kein Privatkram. `.txt` (`# tags:`-Zeile + Art). Ordner per Env `ZENTRALE_ASCII_DIR` überschreibbar. Siehe `ki_system.md`. |

## Auto-erstellte Files

`core/main.py` und Companion-Module legen folgendes an, wenn nicht
vorhanden:

- `data/sleep_quality.json` (sobald der erste Eintrag geloggt wird)
- `data/ai_graph.json` (sobald der erste Turn in den Graphen extrahiert wird)
- `data/ai_ltm.json` (sobald die KI das erste Mal `save_memory` aufruft)
- `data/ai_stm.json` (sobald der erste Chat-Turn passiert)
- `data/<kategorie>.json` (für jede neue Data-Collection-Kategorie)
