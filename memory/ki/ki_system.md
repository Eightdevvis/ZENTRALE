# KI-System

**Stand 2026-10-11:** Front ist die TUI (`tui/zentrale_tui.py`, Thin Client
über `/api/chat` als SSE). Der Kern-Chat denkt über `ai_backends.pick("chat")` —
Vorwahl `chat_backend` in `data/ai_config.json` (`auto|local|cloud`; seit
2026-08-15 bewusst **`cloud`**, daheim wie unterwegs). Cloud = `core/cloud.py`
(Anthropic, Drop-in für `ai.chat_stream()`, Code-Default `claude-sonnet-5`,
adaptives Denken, Prompt-Cache statisch vorn) oder `core/cloud_openai.py`
(zweiter Dialekt für qwen/openai/grok/gemini/deepseek/groq/mistral, Liste
`providers.PROVIDERS`); lokal = Ollama `qwen3.5:9b`
(`think=false`, Prompt-Schiene `profil/klein`, Cloud nimmt `profil/gross`;
qwen über die Cloud bekommt darüber sein Modell-Profil `profil/modelle/qwen`,
Einstellung `modell_profile` → [modell_profile.md](modell_profile.md)).
**Tools laufen immer lokal**, nur die Entscheidung wandert. Schreib-Tools
gehen durchs Erlaubnis-Gate (Regel im Werkzeug-Register, nicht
modellgetrieben). **Das Gedächtnis ist das Datei-Gedächtnis**
(`gedaechtnis_dateien.md`, Aufbau nach Themen: `gedaechtnis.md`); der Konzept-Graph war seit 2026-08-18
abgeschaltet und ist seit 2026-10-31 aus dem Code
([../archive/associative_graph/](../archive/associative_graph/README.md)). Der Chat ist
nicht hart gegatet (`chat_available()`: ohne lokale KI —
`ZENTRALE_LOKALE_KI=aus` — Cloud ja, lokal nie). Tool-Calls und Denken stehen im Chat, das Devtools-Terminal
zeigt den vollen Request. Kosten in `data/ai_usage.json` — oben Sashas Chat
(nur das zählen Deckel, Rückfall und Anzeige), der Prüfstand seit 2026-10-09
im eigenen Topf `herkunft.pruefstand` ([pruefstand.md](pruefstand.md),
„Kosten"). **Modell:**
Code-Default ist `claude-sonnet-5` (`providers.py` `default_model`, Rückfall
in `cloud._model()`), Denk-Tiefe `low` (`ai_backends.chat_effort`). Beides
überschreibt `data/ai_config.json` (`chat_models` pro Anbieter,
`chat_effort`) — Daten, nicht im Repo, also pro Knoten nachsehen.
`claude-haiku-4-5` (`cheap_model`) nutzen alle Einmal-Aufrufe über
`core/billig.py`: Gesprächstitel, Datei-Gedächtnis, Klassifikator,
Morgenblick und der (abgeschaltete) Graph-Extraktor. Der Prüfstand-Richter
geht ebenfalls durch `billig.einmal`, nimmt aber bewusst das Chat-Modell.

## Architektur

```
TUI ──POST /api/chat──▶ ui/routen/ki.py ──kern.chat()──────────────┐
                         (ai_backends.chat_available(): WER darf)  │
   cloud ◀─ kern.cloud_modul(): core/cloud.py (Anthropic)       ◀──┤
            | core/cloud_openai.py (OpenAI-kompatibel)             │
            Schiene profil/gross, Kopf mit gedaechtnis.kopf_block  │
   local ◀─ core/ai.py ──▶ Ollama (qwen3.5:9b), Schiene profil/klein ◀┘

alle Wege ─▶ werkzeug_schleife     (die EINE Tool-Schleife, run_tool)
          ─▶ ki_werkzeuge.ausfuehren (Werkzeuge immer lokal, Erlaubnis-Gate)
           ─▶ consolidation.py     (nach dem Turn: Transkript, gebündelt in der Pause)
```

`ai.py` ist der einzige Ollama-Client für Chat-Calls. `embeddings.py` redet
ebenfalls direkt mit Ollama (Embeddings für News und ASCII-Bildsuche), aber
alle gehen durch `core/net.py` – damit landet jeder
Request im Terminal (siehe [internet_netz.md](internet_netz.md), „Network-Transparenz“).

## Wo was steht

`ki_system.md` ist seit 2026-10-11 nur noch der Überblick. Die Themen stehen in
eigenen Dateien (Grenze 600 Zeilen, [../doku_regeln.md](../doku_regeln.md)):

| Thema | Datei |
|---|---|
| Anbieter, Modelle, Backend-Wahl, Lokal-Regel, Isolations-Invariante, Modell-Parameter, **Fallen der API**, lokales Modell, Warmup | [anbieter_modelle.md](anbieter_modelle.md) |
| System-Prompt-Reihenfolge, zwei Schienen `klein`/`gross`, Prompt-Cache, Nutzer im Prompt, `prompt_zeigen.py` | [prompt_aufbau.md](prompt_aufbau.md) |
| Werkzeug-Liste, Werkzeug-Register (neues Werkzeug anlegen), Belegt oder gesagt, Gespräche/Projekte/Ablage/PDF-Werkzeuge | [werkzeuge.md](werkzeuge.md) |
| Die eine Werkzeug-Schleife, Adapter, Fehler, Stoppen, Rundengrenze | [werkzeug_schleife.md](werkzeug_schleife.md) |
| Erlaubnis-Gate, Knopf-Dialog, Geltungsbereiche | [erlaubnis_gate.md](erlaubnis_gate.md) |
| Ehrlichkeit live (Prüfer vor jeder Antwort) | [ehrlichkeit_live.md](ehrlichkeit_live.md) |
| Kalender-Werkzeuge ohne Fallen | [ki_kalender.md](ki_kalender.md) |
| Werkzeuge aus dem Schema | [werkzeug_erzeuger.md](werkzeug_erzeuger.md) |
| Sandbox `run_code` | [sandbox.md](sandbox.md) |
| Skills | [skills.md](skills.md) |
| Dateien der KI (nur die Ablage), Suchen, Claude-Skills übernehmen, Reichweite von gross | [nutzerordner.md](nutzerordner.md) |
| Browser der KI | [browser.md](browser.md) |
| Internet-Pipe, Netz-Transparenz | [internet_netz.md](internet_netz.md) |
| Devtools, Tool-Calls im Chat, Ablauf-Protokoll („trace ›") | [transparenz.md](transparenz.md) |
| Chat-Befehle, Markdown im Terminal, Bild-Marker, Bewertungen | [chat_bedienung.md](chat_bedienung.md) |
| Konzept-Graph (seit 2026-10-31 im Archiv), Extraktor, Embeddings | [../archive/associative_graph/konzept_graph.md](../archive/associative_graph/konzept_graph.md) |

## Voice-Pipeline (Core, sprachneutral)

STT und TTS hängen nicht mehr am Tutor, sondern an der Core-AI:

- `POST /api/transcribe` – Audio → Text (Whisper, `lang`-Param)
- `POST /api/speak` – Text → WAV (Piper für `de`, sherpa-onnx für `zh`)

Der Tutor ist ein Konsument dieser Pipeline — die Sprache kommt aus dem aktiven
Sprach-Profil (`stt_lang`/`tts_lang`), `zh` ist nur der heutige Default, kein
Festwert. Details: `memory/ki/audio_system.md` und `memory/system/api_endpoints.md`.

## Historie

- **2026-05** — Ollama-Chat mit qwen2.5:14b, Legacy LTM/STM (`save_memory`),
  Phasen A–F des Memorys (`ki_memory_plan.md`).
- **2026-06-06** — qwen3.5:9b (Bench), Konzept-Graph als primary Memory
  (Phase G), Subjekt-Trennung im Kontext, `_DASHBOARD_VIEW`-Prompt.
- **2026-06-07** — Internet-Pipe `web_suche`/`hole_url` mit hartem Gate; das
  rechte Panel wird Transparenz-Monitor statt Alarm.
- **2026-07-17** — Key-Store `data/ai_config.json` als einzige Key-Quelle
  (`../betrieb/datei_zugriffe.md`).
- **2026-08-10** — Entscheidung für die Cloud (`cloud_umstieg_plan.md`).
- **2026-08-15** — `core/cloud.py`, `chat_backend: cloud`, Kassetten-Regel
  (Cloud auch in ki-freien Kassetten; heute Lokal-Regel), TUI als Thin Client.
- **2026-08-17/18** — Zeit in vier Auflösungen, Kalender-Spiegel gelöscht,
  Imprint in den Cache; **Datei-Gedächtnis statt Graph**; zwei
  Prompt-Schienen `profil/klein|gross`; Devtools zeigen den vollen Request.
- **2026-08-20** — Tool-Calls und Denken im Chat; Nachprüf-Schritt im
  Werkzeug-Ergebnis. **08-21** Zwischenbericht `cloud_bericht.md`.
- **2026-10-11** — `ki_system.md` war durch angehängte Agenten-Abschnitte auf
  2.065 Zeilen gewachsen; nach Themen in die Dateien oben zerlegt
  ([../doku_regeln.md](../doku_regeln.md), Regel 9).
