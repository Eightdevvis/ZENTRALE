# Dateizugriffe

## Whitelist – was die KI lesen darf

`core/context.py` (`_WHITELIST_PATTERNS`) definiert die Whitelist. Nur was hier
steht, kann die **lokale** KI über die Tools `read_file` und `list_files` öffnen.
**Wortlaut aus dem Code** (2026-07-17 nachgemessen, nicht abgeschrieben):

```
data/*.json
vocab_mandarin.json     ← TOTER EINTRAG: die Datei gibt es seit dem
                          Sprach-Framework nicht mehr, matcht nichts
core/*.py
ui/app.py
notes.md
```

> **Achtung, zwei Dinge stehen hier falschherum** (Stand 2026-07-17, ungelöst):
>
> 1. **`data/*.json` deckt den API-Key-Store mit ab.** `data/ai_config.json` und
>    `data/tutor_config.json` enthalten den `keys`-Block mit dem echten
>    `DASHSCOPE_API_KEY` — die lokale KI darf sie per `read_file` im Klartext
>    lesen (nachgestellt, sie liefert den Key aus). Das ist keine Folge des
>    Infra-Schnitts: die Keys lagen vorher in `data/tutor_config.json`, also
>    ebenfalls unter `data/*.json`. Das Muster stammt aus der Zeit, als in `data/`
>    nur Schlaf-Logs lagen. **Sasha entscheidet**, ob der Key-Store aus der
>    Whitelist ausgenommen wird — bis dahin: die Whitelist ist kein Secret-Schutz.
> 2. **Die Vokabeldatei ist NICHT lesbar.** Diese Datei behauptete
>    `tutor/data/<lang>/vocab.json` stünde in der Whitelist — steht sie nie, und
>    der Zugriff wird verweigert. Der Lernstand des Tutors ist der lokalen KI
>    also unsichtbar (was zur Tutor-Sandbox passt, aber nicht das war, was hier
>    stand).

Die Whitelist gilt für die **lokale Core-KI**. Der Tutor hat eine **eigene,
strengere** Sandbox (`tutor.tools._ALLOWED`) und kann gar keine Dateien lesen —
nur seine 15 Tools aufrufen. Siehe `tutor_system.md`.

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
| `data/ai_config.json` | **API-Keys** + Kill-Switches (`core/ai_config.py`)             |
| `data/*.enc`          | verschlüsselter Mail-Zugangsdaten-Blob (`core/mail_secrets.py`)|
| `data/tts_model/`     | Modelldateien, viel zu groß für Git                           |
| `tutor/data/**/*.json`| Lernstand des Tutors pro Sprache (vocab, structures, persona_mem, persona_hist) + lokale Sprach-/Provider-Wahl |
| `tutor/data/**/vocab_images/`, `tutor/data/**/persona_music/` | Persona-Medien, lokal |
| `venv/`               | Python-Virtualenv (lokal); auf dem Pi heißt der Ordner `.venv` |
| `core/__pycache__/`   | Python-Bytecode                                               |

Diese Pfade gehören in `.gitignore`. Falls dort noch nicht drin: ergänzen.

`data/photos/` (Test-Fotos für den ASCII-Bild-Filter) ist ebenfalls
ignoriert – lokaler Inhalt, kein Repo-Material.

## Was committet WIRD (data-Ausnahme)

| Pfad           | Grund                                                       |
|----------------|-------------------------------------------------------------|
| `data/ascii/`  | handgepflegte ASCII-Bibliothek für den Bild-Marker `[[bild: name]]` – Inhalt, kein Privatkram. `.txt` (`# tags:`-Zeile + Art). Ordner per Env `ZENTRALE_ASCII_DIR` überschreibbar. Siehe `ki_system.md`. |
| `tutor/langs/<lang>/` | die **Sprache** selbst (prompt.md, prompt.de.md, tool_texts.json, expect.json, vocab_hint.md, seeds/) – Inhalt, kein Lernstand. Trennlinie: `langs/` = Sprache (getrackt), `tutor/data/` = Fortschritt (ignoriert). |
| `*.example`    | `data/ai_config.json.example`, `tutor/data/tutor_config.json.example` – Vorlagen ohne Secrets. |

## Auto-erstellte Files

`core/main.py` und Companion-Module legen folgendes an, wenn nicht
vorhanden:

- `data/sleep_quality.json` (sobald der erste Eintrag geloggt wird)
- `data/ai_graph.json` (sobald der erste Turn in den Graphen extrahiert wird)
- `data/ai_ltm.json` (sobald die KI das erste Mal `save_memory` aufruft)
- `data/ai_stm.json` (sobald der erste Chat-Turn passiert)
- `data/<kategorie>.json` (für jede neue Data-Collection-Kategorie)
