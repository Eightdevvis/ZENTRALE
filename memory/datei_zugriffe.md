# Dateizugriffe

## Whitelist – was die KI lesen darf

`core/context.py` regelt den Dateizugriff der **lokalen** KI in zwei Stufen:
eine **Secret-Sperre** (Denylist, gewinnt immer) und darunter die **Whitelist**.
**Wortlaut aus dem Code** (2026-07-17 nachgemessen, nicht abgeschrieben):

```
# SECRET-SPERRE (vor der Whitelist, matcht nach Basename):
#   ai_config.json, tutor_config.json           ← Key-Store / Legacy-Keys
#   *.enc, *.key, *.pem                          ← Blobs, Schlüssel, Zertifikate
# WHITELIST (nur was NICHT gesperrt ist):
data/*.json
core/*.py
ui/app.py
notes.md
```

> **Sicherheit — der Key-Store ist gesperrt (Fix 2026-07-17).** Die Whitelist
> `data/*.json` deckte `data/ai_config.json` (mit dem echten `DASHSCOPE_API_KEY`)
> mit ab — die KI konnte ihn per `read_file` im Klartext lesen. Jetzt fängt die
> **Secret-Sperre** das ab: sie greift VOR der Whitelist und matcht nach Basename,
> also ortsunabhängig (ein Verschieben oder Unterordner hebelt sie nicht aus, und
> auch der `..`-Umweg nicht). `list_files` verrät den Key-Store nicht mal.
> Regressionstest: `tests/test_context_secrets.py`. **Deny-by-default für Secrets:**
> neue Secret-Dateien in `_SECRET_BASENAMES`/`_SECRET_SUFFIXES` eintragen, nicht
> darauf hoffen, dass die Whitelist sie zufällig verfehlt.
>
> Der frühere Eintrag `vocab_mandarin.json` in der Whitelist ist **raus** (tote
> Datei seit dem Sprach-Framework). Der Lernstand des Tutors
> (`tutor/data/<lang>/vocab.json`) stand nie in der Whitelist und ist der lokalen
> KI unsichtbar — das passt zur Tutor-Sandbox.

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
