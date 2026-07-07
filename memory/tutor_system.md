# Sprach-Tutor (Persona-Portal)

> **Status (2026-07-07): PERSONA-PORTAL + EIGENE MEMORY gebaut.** Der Tutor ist
> vom Lehrer zum **chilligen Mitbewohner** umgestellt: pro Sprache eine benannte
> **Persona** (Ling Ling/zh, Jacqueline/fr, …) mit eigenem Charakter, eigenem
> Land und eigenem AI-Anbieter. Sie ist **kein Fake-Mensch** (keine erfundene
> Vergangenheit, ehrlich KI), aber **vernarrt in ihr Land** (nerdet Geschichte/
> Politik/Kultur, dreht dir Nationalgerichte an). Sie **quatscht direkt los**
> (TUI-Taste `u` startet die Session sofort, kein „Stunde starten"-Enter mehr).
> Jede Persona hat ein **eigenes Gedächtnis** (`data/persona_mem_<lang>.json`,
> gleiche `graph.py`-Mechanik) + **persistente History** (`persona_hist_<lang>.json`)
> → erinnert sich session-übergreifend an dich. **Einzige echte Grenze:** dieses
> Persona-Gedächtnis und die lokale **Core-KI-Memory** (`ai_graph.json`) fassen
> sich **nie** an. Die Verdichtung läuft **kapazitätsbasiert** (Ollama daheim
> erreichbar → lokal, sonst Cloud). Details unten unter „Persona-Portal" und
> „Persona-Memory".
>
> **Noch offen:** Presence-Auto-Start (Sensor → Persona spricht dich an) ist
> weiter **bewusst nicht** verkabelt (`brain.py`, Sequencing). Voice pro Sprache
> und ein eigenes Tutor-Exhibit fehlen weiter.
>
> **Reaktivierungs-Stand (2026-06-30, gilt weiter):**
>
> Der Tutor wurde am 2026-05-14 weich deaktiviert. Grund war **nicht** der
> schlechte Auto-Trigger (das war nur der Anlass), sondern Sequencing:
> erst die Core-KI sauber aufstellen, ohne den KI-Layer mit dem Tutor-Addon
> zu vermischen. Jetzt wird er wieder angeschaltet.
>
> **Reaktivierungs-Stand:**
> - `ui/app.py`: `/api/tutor/{status,start,respond,stop}` **wieder aktiv**,
>   `tutor_session` wird importiert. Audio läuft über die generische
>   Voice-API (`/api/transcribe`, `/api/speak`) mit `lang='zh'` – keine
>   eigenen Tutor-Audio-Aliase mehr nötig.
> - Start ist **rein manuell**. **`Alt+T` ist LIVE** (Toggle, beide Richtungen):
>   schaltet im Dashboard den Tutorkanal an/aus (`toggleTutor` → `startTutor`/
>   `stopTutor`). Nacktes `T` ginge nicht – es landet im immer fokussierten
>   Chat-Input. Zusätzlich weiter per `/tutor` / `/tutorstop`. KEIN Presence-
>   Auto-Start in `brain.py` (bewusst, siehe Sequencing oben).
> - **Frontend (`monolith.html`) – Kanalwechsel gebaut, Exhibit noch offen:**
>   der sichtbare **Kanalwechsel** ist da: bei aktivem Tutor legt `body.tutor-mode`
>   einen **prägnanten roten Rahmen** um die ganze Mittelspalte (`#col-mid` =
>   Kern-Canvas + Konsole drunter, CSS-Var `--tutor`), Reiter „● TUTOR", roter
>   Prompt-Pfeil, Eingaben gehen an `/api/tutor/respond`. Das ist der „erstmal
>   nur umschalten"-Schritt. **Noch offen:** ein eigenes Tutor-**Exhibit** im
>   AI-Canvas (neben `gesicht`/`graph`, wie `graph-panel`); aktuell läuft der
>   Tutor text-first im Minilog. Drumherum nicht anfassen.
> - **Backend-Wahl per `TUTOR_BACKEND`:** `cloud` → Claude (Anthropic),
>   `local` (Default) → Ollama. Siehe „Cloud-Backend" unten.
> - `core/tutor.py`, `core/tutor_session.py`, `core/tutor_cloud.py`,
>   `vocab_mandarin.json` (Repo-Root) und die Audio-Modelle sind aktiv/intakt.
> - **Fronten (»alle Kassetten«-Regel):** der Tutorkanal ist bisher **nur im
>   Browser** (`monolith.html`) gebaut. In die **TUI** ist davon erst der
>   `/cloud`-Kill-Switch + die EXTERNAL-Backend-Box gewandert – ein Tutor-Start/
>   -Kanal in der TUI fehlt noch komplett (offener Punkt).
>
> Der Rest dieses Files beschreibt das Design; Abweichungen sind oben vermerkt.

## Persona-Portal: eine Figur pro Sprache

Der Tutor ist ein **Persona-Portal**: jede Sprache = eine benannte **Persona**
mit eigenem Charakter, eigenem Land und eigenem AI-Anbieter (Provider/Modell
entkoppelt). Definiert in **`core/tutor_langs.py`** (`PROFILES`), pro Eintrag u.a.
`persona_name`, `country`, `vocab_file`, `provider`/`model`, `system_prompt`.
**LIVE: `zh` → Ling Ling (China, qwen).** Skizzen (`enabled=False`): `fr`
Jacqueline, `ru` Ludmila, `ar` Amira, `es` Lucía.

**Charakter (`_build_prompt`)** — die Ansage von Sasha, festgehalten:
- **Kein Lehrer, kein Kurs, keine „Stunde".** Chilliger, gesprächiger, leicht
  nerviger, aber endlos geduldiger Mitbewohner. Fängt **von selbst** Smalltalk
  an, quatscht dich an.
- **Kein Fake-Mensch:** spielt keinen Menschen mit erfundener Vergangenheit,
  war nie wirklich im Land, erfindet keine persönlichen Erlebnisse — ehrlich
  eine KI, die ein Land „kachelt".
- **Aber vernarrt ins Land:** nerdet Geschichte, verfolgt/diskutiert Politik
  (mit Meinung), hat Kultur/Essen im Hinterkopf und webt es in den Alltag
  („ich koch was" → dreht Nationalgericht an; „hab was Politisches gehört" →
  taucht rein).
- **Sprach-Mix bleibt:** 80 % Zielsprache (kurze Anfänger-Sätze), Deutsch bei
  Verständnisproblemen. Vokabel-Mechanik unverändert (Tools, 80/20, siehe unten).

**Direkt-Start (kein Enter):** TUI-Taste `u` (`zentrale_tui.tutor_open`) holt den
Status und lässt die Persona **sofort** loslegen, wenn das Backend da ist und
keine Session läuft. Der Browser (`monolith.html`) startet über `Alt+T` schon
immer direkt. `/api/tutor/config` liefert jetzt `persona_name`/`country` fürs UI.

## Persona-Memory: der Mitbewohner erinnert sich an dich

Jede Persona hat ein **eigenes Gedächtnis**, getrennt von Sashas privatem
Core-Graphen — **Modul `core/persona_memory.py`**:
- **Store:** `data/persona_mem_<lang>.json`, gebaut mit derselben `graph.py`-
  Mechanik (Multi-Store: `graph.add_turn_extraction(..., store=pfad)`,
  `graph.context_for_persona(query, store=pfad)`). Enthält nur Wissen **über
  Sasha** aus euren Chats — **keine** erfundene Persona-Biografie.
- **Persistente History:** `data/persona_hist_<lang>.json`. `activate()` lädt
  sie statt zu flushen → die Persona knüpft session-übergreifend an.
- **Loop (`tutor_session.respond_stream`):** vor der Antwort wird der Persona-
  Kontext („## Was du über Sasha weißt") an den System-Prompt gehängt; nach der
  Antwort werden History persistiert und der Turn im Hintergrund verdichtet.
- **Verdichtungs-Backend kapazitätsbasiert** (`persona_memory.remember` via
  `ai_backends.status()`): ist **Ollama erreichbar** (daheim, oder Laptop→PC per
  `zentrale-remote`) → **lokaler** Extraktor; sonst → **Cloud** (der Anbieter,
  der eh gerade redet, z.B. qwen); **kein Backend** → Turn übersprungen. So baut
  die Memory auch, wenn der Laptop unterwegs kein Ollama hat.

- **Was hier NICHT stimmt (ehrliche Grenze — kein Marketing):** Läuft die
  Persona über die Cloud, liegt ihr **Gesprächs- und Memory-Inhalt beim Cloud-
  Anbieter** — unvermeidbar, das Reden läuft ja dort, und der Kontext-Block wird
  jede Session wieder mitgeschickt (wächst sogar an). Die lokale Verdichtung ist
  **kein** Privacy-Schutz fürs Tutor-Material (das war beim Reden längst beim
  Anbieter); sie ist nur billiger + hält alles offline, **wenn** Ollama da ist.
  Die **einzige** harte Garantie: die **Core-KI-Memory** (`ai_graph.json`, das
  was du dem lokalen Chat offline erzählst) wird der Tutor-Persona **nie**
  gefüttert — die Stores fassen sich nicht an, die Sandbox aus `core/tutor.py`
  bleibt intakt. Persona-Turns werden zudem **nicht** in Sashas gemeinsamen
  Kalender gespiegelt.

Tests ohne Ollama: `scripts/test_persona_memory.py` (Store-Isolation, Kontext,
History, Portal — Embeddings gestubbt). Der Extraktor-Pfad braucht Ollama und
läuft über `scripts/test_graph_memory.py`.

## Framework: Sprachen + Provider (austauschbar)

Der Tutor ist ein **Sprach-Framework**: Sprachen werden als **Personas**
draufgelegt, der **Anbieter/das Modell ist davon entkoppelt**. Beides wird zur
Laufzeit aufgelöst (`tutor_session._resolve`): Sprache → Profil → Provider →
Modell.

**Module:**
- `core/tutor_langs.py` – **LanguageProfile** pro Sprache: System-Prompt,
  Vokabel-Datei, `reading` (zh=Pinyin, ru=Betonung, ar=Translit, es=—),
  `script` (ar=RTL), STT/TTS-Lang, Default-Provider+Modell.
  **LIVE: `zh` (Chinesisch).** Skizzen (enabled=False, stückweise reinziehen):
  `ru`, `ar`, `es`.
- `core/tutor_providers.py` – **Provider-Registry**. Pro Eintrag: `kind`
  (`ollama` | `anthropic` | `openai_compat`), `base_url`, `key_env`,
  `default_model`, **`trains_on_data`**, `jurisdiction`, `enabled`.
  **LIVE:** `local` (Ollama), `claude` (Sashas Pfad), `qwen` (Verteil-Default).
  Skizzen: `openai`, `mistral`, `groq`, `deepseek`, `gemini`.
- `core/tutor_openai_compat.py` – **Drop-in für `ai.chat_stream()`**, bedient
  JEDEN OpenAI-`/v1`-kompatiblen Provider (Qwen/DeepSeek/Mistral/OpenAI/Groq/
  Gemini) durch Tausch von base_url+Key+Modell. `TUTOR_TOOLS` sind schon
  OpenAI-Schema → ohne Übersetzung. Streaming-Tool-Loop.
- `core/tutor_cloud.py` – **Anthropic-SDK-Pfad** (Claude), Sashas persönliche
  Verifikation. Übersetzt `TUTOR_TOOLS` ins Anthropic-Format.

**Steuerung – lokale Config-Datei (kein `export` nötig):**
- `data/tutor_config.json` (`core/tutor_config.py`) hält `lang` / `provider` /
  `model` / `history_window` **und die API-Keys**. Modell durchprobieren =
  `provider`/`model` dort ändern, neu starten. Vorlage:
  `data/tutor_config.json.example`.
- **Sicherheit:** `data/*.json` ist in `.gitignore` → die echte Config (mit
  Keys) wandert NIE ins Repo (verifiziert via `git check-ignore`). Keys aus der
  Config werden beim Import in `os.environ` injiziert, damit die SDKs sie finden.
- **Precedence:** Env-Var > Config-Datei > Profil-Default. D.h. `TUTOR_LANG` /
  `TUTOR_PROVIDER` / `TUTOR_MODEL` / `TUTOR_HISTORY_WINDOW` im Terminal
  übersteuern die Config für ein schnelles Einzel-Experiment.
- `history_window` (Default 30) = wieviele letzte Turns gesendet werden
  (Kosten-Hebel: zustandslose API sendet History sonst komplett neu).
- **Caching:** noch NICHT explizit gesetzt. OpenAI-kompatible Provider mit
  Auto-Cache (OpenAI/DeepSeek) profitieren schon vom cache-freundlichen Aufbau
  (stabiler System-Prompt zuerst, History nur angehängt); Qwen-Context-Cache
  noch zu verifizieren. → offener Punkt.

**Default pro Sprache (verifiziert, billig × gut × Privacy):**
zh → Qwen (Singapur, no-train) · es → Mistral (EU) · ru → Qwen · ar →
gpt-4o-mini (ALLaM/Groq als Option, Policy noch prüfen).

**Privacy-Flag (HART):** Provider mit `trains_on_data=True` (deepseek, gemini-
free) **oder unverifiziert** (`None`, z.B. groq) werden NICHT verboten, aber bei
Session-Start **laut geflaggt**: `tutor_session.activate()` setzt eine Warnung
(Log + `privacy_notice()`), die `/api/tutor/status` als `privacy_warning`
liefert → UI muss sie deutlich anzeigen.

**Offline-Prinzip:** Default bleibt `local` (Ollama, offline). Cloud-Provider
sind bewusster Opt-in. **Dependencies:** `openai` ist seit 2026-06-26 im venv +
in `requirements.txt` – der **qwen-Cloud-Pfad** (openai_compat) lief vorher gar
nicht, `import openai` knallte. `anthropic` ist **inzwischen ebenfalls im venv
installiert** (für den Claude-Verifikations-Pfad `core/tutor_cloud.py`), bleibt
aber **policy-mäßig Opt-in**: in `requirements.txt` bewusst auskommentiert, also
kein Pflicht-Dep für die Verteilung (`venv/bin/pip install anthropic` bei Bedarf).
**Cloud-Live steht:** `DASHSCOPE_API_KEY` ist in `data/tutor_config.json`
(`keys`-Block) **gesetzt** (Secret, gitignored) → der qwen-Pfad ist startklar
(`provider=qwen`, `model=qwen-plus`, `lang=zh`). Provider/Modell/Prompt stehen;
**offen bleibt nur ein echter End-to-End-Call** zur Auth-Verifikation – der ist
noch nicht protokolliert.

## Position in der Architektur

Tutor ist ein **Addon** auf der Core-AI, nicht der Owner der
Voice-Pipeline. STT (Whisper) und TTS (sherpa-onnx / Piper) leben
zentral in `services/whisper_service.py` und `services/tts_service.py`
und sind sprachneutral nutzbar via `/api/transcribe` und `/api/speak`
(siehe `audio_system.md`). Der Tutor ruft diese Endpoints **als
Aufrufer** mit `lang='zh'` auf – er besitzt sie nicht.

Die alten Pfade `/api/tutor/transcribe` und `/api/tutor/speak` existieren
als dünne Aliase mit `lang='zh'`-Default, damit das Tutor-Frontend ohne
Änderung weiterläuft.

## Idee

Smalltalk auf Mandarin mit der KI – mit Spracheingabe (Whisper-STT)
und Sprachausgabe (sherpa-onnx-TTS, Modell `vits-zh-aishell3`).
Vokabeln kommen aus `vocab_mandarin.json`. Die KI nutzt 80 % bekannte
Vokabeln (zur Festigung) und 20 % neue (zum Erweitern).

## Vokabel-Daten-Modell

Jeder Eintrag in `vocab_mandarin.json` hat:

```json
{ "word": "你好", "pinyin": "nǐ hǎo", "correct_use": 0, "confirmed": false }
```

- `confirmed: false` → **Testing-Pool** (20 % der Konversation)
- `confirmed: true`  → **Confirmed-Pool** (80 % der Konversation)
- `correct_use` zählt korrekte Verwendungen. Bei
  `correct_use ≥ CONFIRM_THRESHOLD` (= 5, in `tutor.py`) flippt
  `confirmed` automatisch auf `true`.

## Aufbau

### `core/tutor.py`
- Definiert den System-Prompt für den Tutor-Modus.
- Definiert `TUTOR_TOOLS` – die Liste der Tools, die nur im Tutor-Modus
  verfügbar sind.

### `core/tutor_session.py`
- Verwaltet eine laufende Session: Zustand, History, Audio-Aufrufe.
- History ist **getrennt** von der Chat-History (sonst vermischen sich
  Lernkontext und allgemeine Konversation).

### Verhältnis zum Chat-Modus

Tutor und Chat nutzen dieselbe `ai.chat_stream()`-Infrastruktur.
Der Unterschied liegt nur in:

- **System-Prompt** (Tutor: „Du bist Mandarin-Sprachtutor für Sasha …")
- **Tool-Set** – im Tutor-Modus sind die Standard-Tools (`save_memory`,
  `read_file`, `list_files`) **deaktiviert** und durch die
  Tutor-spezifischen Vokabel-Tools ersetzt (siehe unten).

Das hält den Code DRY – kein doppelter Streaming-Mechanismus.

## Tutor-Tools

Aktiv nur während einer Tutor-Session (`TUTOR_TOOLS` in `core/tutor.py`).
Diese **ersetzen** die Standard-Tools (save_memory, read_file, list_files)
während des Tutor-Modus.

| Tool                      | Argumente              | Funktion                                                                        |
|---------------------------|------------------------|---------------------------------------------------------------------------------|
| `get_confirmed_vocab`     | –                      | Liefert alle Vokabeln mit `confirmed: true` als Prompt-formatierten String      |
| `get_testing_vocab`       | –                      | Liefert alle Vokabeln mit `confirmed: false` + `count`                          |
| `increment_correct_use`   | `word`                 | +1 auf `correct_use`. Bei ≥ 5 → auto-confirmed                                  |
| `introduce_new`           | `word`, `pinyin`       | **Neues** Wort in `vocab_mandarin.json` hinzufügen (nicht aus einem Pool wählen) |

Logik (laut System-Prompt): wenn `get_testing_vocab` `count < 10`
zurückmeldet → KI soll `introduce_new(word, pinyin)` aufrufen mit einem
selbstgewählten neuen Wort. Es gibt keinen vorgefertigten Pool.

Zusätzlich existiert in `tutor.py` die Hilfsfunktion `get_vocab_stats()`
(„total / confirmed / testing"). Sie ist **kein** AI-Tool, sondern für
Dashboard-Anzeige gedacht.

## Bedienung – Konsolen-Commands

Gesteuert wird über die **Dashboard-Konsole** (das immer fokussierte Chat-
Eingabefeld in `monolith.html`). Kein Hotkey-Konflikt, passt zum „Terminal"-
Charakter. Befehle (Handler in der Chat-IIFE, `handleConsoleCommand`):

| Command | Wirkung |
|---|---|
| `/tutor` | Tutor starten; Begrüßung streamt in den Minilog. Danach gehen Eingaben an `/api/tutor/respond` statt an den Chat. |
| `/tutorstop` | Tutor beenden (`/api/tutor/stop`). |
| `/provider <name>` | Anbieter **live** umschalten (qwen, deepseek, mistral, …). |
| `/model <id>` | Modell live umschalten (z.B. qwen-turbo). |
| `/lang <code>` | Sprache umschalten (zh, ru, ar, es). |
| `/models` | Aktuelle Wahl + wählbare Provider mit Jurisdiktion + Privacy-Flag. |
| `/cloud on\|off` | **Cloud-Kill-Switch** (Datenschutz/Kosten). Aus → kein Cloud-Backend, EXTERNAL zeigt „gedrosselt". Auch in der TUI. |

Backend dahinter: `POST/GET /api/tutor/config` (Live-Override in
`tutor_config`, optional `persist`) für Sprache/Provider/Modell;
`POST /api/ai/backends {cloud_enabled}` für die Cloud-Drossel. Schaltet ohne
Neustart. Privacy-Warnung (`trains_on_data`) erscheint beim Start im Minilog
und über `/api/tutor/status` (`privacy_warning`).

**Verfügbarkeit (kapazitätsbasiert, nicht kassetten-hart):** Der Tutor wird
nicht mehr per `kassette.ki_aus()` gegated, sondern per
`tutor_session.available()` — er läuft, sobald das Backend seines aufgelösten
Providers da ist (lokal ODER cloud, siehe `core/ai_backends.py` +
`memory/`-Doku zur AI-Backend-Verfügbarkeit). Damit nutzbar auf laptop/tui,
sobald cloud (oder via SSH lokal) erreichbar ist. Fehlt das Backend (oder Cloud
gedrosselt): `/api/tutor/{start,respond}` → 503 „backend not here".

**Noch offen / Skizze:** das **zentrale Tutor-Exhibit** (eigene Ansicht im
AI-Canvas statt nur Minilog) und **Voice** für den Tutor (Mic→`/api/transcribe`
+ TTS→`/api/speak`, beides mit der Profil-`lang`, nicht dem `de`-Default) sind
noch nicht gebaut – aktuell läuft der Tutor **text-first** im Minilog. Der
generische Voice-Stack (siehe „Audio-Pipeline") existiert, muss aber pro
Sprache verkabelt werden.

## Vokabel-Datei

`vocab_mandarin.json` – flache JSON-Liste mit den vier Feldern
`word`, `pinyin`, `correct_use`, `confirmed` (vollständiges Schema
siehe „Vokabel-Daten-Modell" oben). Die KI darf hier lesen und über
`introduce_new` / `increment_correct_use` auch schreiben.

## Audio-Pipeline

Siehe `audio_system.md` – das ist der ganze STT/TTS-Stack, der hier
mit dranhängt.
