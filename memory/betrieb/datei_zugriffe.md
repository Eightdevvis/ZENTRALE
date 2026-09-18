# Dateizugriffe

**Stand 2026-09-18:** `core/context.py` entscheidet in einer Funktion
(`erlaubt(abs_pfad)`), was die lokale Core-KI lesen darf: **Secret-Sperre
gewinnt immer** (Basenames wie `ai_config.json`, Suffixe `.enc/.key/.pem`,
Muster wie `.env`, `token`), darunter zwei Wurzeln — ZENTRALE per Whitelist
(`data/*.json`, `core/*.py`, `ui/app.py`, `notes.md`) und `~/codicus`
komplett, minus gesperrte Ordner (`.git`, `venv`, `worktrees`, … und
`learning`). Gelesenes wird nach 8000 Zeichen abgeschnitten, die Liste bei
300 Einträgen gedeckelt. Der Tutor hat keine Dateisicht, nur seine
12 Tools (`tutor.tools._ALLOWED`). Nicht in git: `data/*.json`, `data/*.enc`,
Modelle, `tutor/data/**` (Lernstand), venv.

## Whitelist – was die KI lesen darf

`core/context.py` regelt den Dateizugriff der **lokalen** KI in zwei Stufen:
eine **Secret-Sperre** (Denylist, gewinnt immer) und darunter die **Whitelist**.
**Wortlaut aus dem Code** (nachgemessen, nicht abgeschrieben):

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

> **Sicherheit — der Key-Store ist gesperrt.** Die Whitelist `data/*.json`
> deckt `data/ai_config.json` (mit dem echten `DASHSCOPE_API_KEY`) mit ab — die
> KI konnte ihn bis 2026-07-17 per `read_file` im Klartext lesen (Historie).
> Die **Secret-Sperre** fängt das ab: sie greift VOR der Whitelist und matcht nach Basename,
> also ortsunabhängig (ein Verschieben oder Unterordner hebelt sie nicht aus, und
> auch der `..`-Umweg nicht). `list_files` verrät den Key-Store nicht mal.
> Regressionstest: `tests/test_context_secrets.py`. **Deny-by-default für Secrets:**
> neue Secret-Dateien in `_SECRET_BASENAMES`/`_SECRET_SUFFIXES` eintragen, nicht
> darauf hoffen, dass die Whitelist sie zufällig verfehlt.
>
> Der Lernstand des Tutors (`tutor/data/staende/<id>/<lang>/vocab.json`, siehe
> `memory/tutor/bauplan.md`) stand nie in der Whitelist und ist der lokalen
> KI unsichtbar — das passt zur Tutor-Sandbox.

## Zweite Wurzel: `~/codicus`

Sasha (18.08.2026): *"die ai brauch zugriff auf alles unter /codicus/"*. Seitdem hat
`core/context.py` **zwei Wurzeln** — ZENTRALE selbst (weiter über die
Whitelist oben) und `~/codicus` (per `ZENTRALE_CODICUS` umstellbar), dort
**alles**, was nicht ausdrücklich gesperrt ist.

Eine einzige Instanz entscheidet: **`erlaubt(abs_pfad) -> str`**, leerer
String heißt ja, sonst steht der Grund drin. `read_file` fragt sie, und
`gedaechtnis.dokument_holen` (das jetzt auch lokale Pfade ablegt, nicht nur
URLs) fragt dieselbe. Zwei Antworten auf „was darf sie sehen" wären die
Sorte Lücke, die niemand bemerkt: eine Ablage-Funktion, die weiter reicht
als die Lese-Funktion, ist ein Umweg um die Sperre.

Gesperrt bleiben, **egal in welcher Wurzel**:

- **Ordner** (`_GESPERRTE_ORDNER`, greift auf jedem Pfad-Segment): `.git`,
  `.hg`, `.svn`, `node_modules`, `venv`, `.venv`, `__pycache__`,
  `.mypy_cache`, `.pytest_cache`, `site-packages`, `dist`, `build`,
  `.cache`, `worktrees` — Innereien und Arbeitskopien, also dieselben
  Dateien ein zweites Mal — **und `learning`**.
- **Secret-Muster** im Dateinamen (`_SECRET_MUSTER`): `.env`, `id_rsa`,
  `id_ed25519`, `id_ecdsa`, `secret`, `token`, `passwor`, `apikey`,
  `api_key` — plus die alte Sperre. Die trug vorher wenig; mit fremden
  Repos in Reichweite trägt sie viel.
- Alles außerhalb der beiden Wurzeln. `..` braucht keine eigene Prüfung:
  wer hinausklettert, fällt aus der Wurzel und damit durch.

**`learning/` ist eine Entscheidung, keine Notwendigkeit** — Sashas
Lernordner, in dem er ohne KI arbeitet (Hausregel 3 gilt auch für mich).
Es ist eine Zeile in `_GESPERRTE_ORDNER`, jederzeit rücknehmbar.

`list_available_files()` listet **ZENTRALE zuerst und vollständig**, füllt
dann bis `_MAX_LISTE` (300) aus `~/codicus` auf und hängt einen Hinweis an,
wenn etwas fehlt. Sonst frisst ein alphabetisch frühes Fremdprojekt den
Deckel auf und ausgerechnet das, was sie täglich braucht, fällt heraus.
`read_file` erreicht auch das Nichtgelistete.

Die Whitelist gilt für die **lokale Core-KI**. Der Tutor hat eine **eigene,
strengere** Sandbox (`tutor.tools._ALLOWED`) und kann gar keine Dateien lesen —
nur seine 12 Tools aufrufen (Liste in `memory/tutor/bauplan.md`, Verhalten in
`memory/tutor/tutor_system.md`).

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
| `tutor/data/**`       | Spielstände des Tutors (`staende/<id>/<lang>/…`: vocab, game, srs, persona_mem …), `tutor_config.json` (Provider-Wahl), Persona-Medien — Pfade in `memory/tutor/bauplan.md` |
| `venv/`               | Python-Virtualenv (lokal); auf dem Pi heißt der Ordner `.venv` |
| `core/__pycache__/`   | Python-Bytecode                                               |

Diese Pfade gehören in `.gitignore`. Falls dort noch nicht drin: ergänzen.

`data/photos/` (Test-Fotos für den ASCII-Bild-Filter) ist ebenfalls
ignoriert – lokaler Inhalt, kein Repo-Material.

## Was committet WIRD (data-Ausnahme)

| Pfad           | Grund                                                       |
|----------------|-------------------------------------------------------------|
| `data/ascii/`  | handgepflegte ASCII-Bibliothek für den Bild-Marker `[[bild: name]]` – Inhalt, kein Privatkram. `.txt` (`# tags:`-Zeile + Art). Ordner per Env `ZENTRALE_ASCII_DIR` überschreibbar. Siehe `memory/ki/ki_system.md`. |
| `tutor/langs/<lang>/` | die **Sprache** selbst (Pflichtdateien in `memory/tutor/bauplan.md`) – Inhalt, kein Lernstand. Trennlinie: `langs/` = Sprache (getrackt), `tutor/data/` = Fortschritt (ignoriert). |
| `*.example`    | `data/ai_config.json.example`, `tutor/data/tutor_config.json.example` – Vorlagen ohne Secrets. |

## Auto-erstellte Files

`core/main.py` und Companion-Module legen folgendes an, wenn nicht
vorhanden:

- `data/sleep_quality.json` (sobald der erste Eintrag geloggt wird)
- `data/ai_graph.json` (sobald der erste Turn in den Graphen extrahiert wird)
- `data/ai_ltm.json` (sobald die KI das erste Mal `save_memory` aufruft)
- `data/ai_stm.json` (sobald der erste Chat-Turn passiert)
- `data/<kategorie>.json` (für jede neue Data-Collection-Kategorie)

## Historie

- **2026-07-17** — Key-Store-Leck: `data/*.json` deckte `ai_config.json` mit
  ab, die KI konnte den DashScope-Key lesen. Secret-Sperre vor die Whitelist
  gesetzt, Regressionstest `tests/test_context_secrets.py`. Gleichzeitig
  `vocab_mandarin.json` aus der Whitelist (tote Datei seit dem
  Sprach-Framework).
- **2026-08-18** — zweite Wurzel `~/codicus` mit gesperrten Ordnern und
  Secret-Mustern; `learning/` als Hausregel-Sperre.
