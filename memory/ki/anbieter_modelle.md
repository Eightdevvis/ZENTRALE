# Anbieter, Modelle, Backend-Wahl — und die Fallen der API

**Stand 2026-10-11:** Der Chat denkt über `ai_backends.pick("chat")`, Vorwahl
`chat_backend` (seit 2026-08-15 bewusst `cloud`). Cloud spricht zwei Dialekte:
`core/cloud.py` (Anthropic, Code-Default `claude-sonnet-5`, Denk-Tiefe `low`) und
`core/cloud_openai.py` (OpenAI-kompatibel). Lokal: Ollama `qwen3.5:9b` mit
`think=false`. Werkzeuge laufen immer lokal. Lokal sieht alles von Cloud, Cloud
nichts von lokal. Gestoppte Züge werden geschätzt gebucht.

**Warum:** Das Projekt hing nie an der Architektur, sondern daran, dass ein 9B
nicht klug genug war ([cloud_umstieg_plan.md](cloud_umstieg_plan.md)). Eine
ausdrückliche Backend-Wahl fällt nie still zurück: der Unterschied ist, ob Daten
das Haus verlassen. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Cloud-Kern – `core/cloud.py` (Anthropic)

Zweiter Denk-Pfad für den Kern, **Drop-in für `ai.chat_stream()`**: gleiche
Signatur, gleiches Event-Protokoll (`reflect` / `ascii` / `permission` /
`cinema` / `werkzeug` / `fehler` / Text), gleiches Erlaubnis-Gate. Grund für den Umstieg: das Projekt
hing nie an der Architektur, sondern daran, dass ein 9B nicht klug genug war
und immer mehr Prompt-Absicherung brauchte.

**Was sich ändert, ist WER DENKT — nicht wer ausführt.** `_dispatch_tool` /
`_execute_tool` in `core/ai.py` bleiben unangetastet und laufen weiter lokal;
`core/cloud.py` übersetzt nur zwischen zwei Tool-Dialekten (geparste
Ollama-Textblöcke ↔ native `tool_use`-Blöcke). Whisper, TTS, Kalender, Mail,
News und **Ollama für die Embeddings** laufen unverändert lokal weiter — der
Wechsel tauscht genau eine Komponente aus.

| | lokal | Cloud |
|---|---|---|
| Modell **entscheidet**, welches Tool | Ollama | Anthropic |
| Aufruf wird **geparst** | Text-Parsing | native `tool_use`-Blocks |
| Tool **läuft** | lokal | **weiterhin lokal** |

### Isolations-Invariante

**Lokal sieht alles von Cloud. Cloud sieht nichts von lokal.**

Der Cloud-Pfad hat einen **eigenen Graphen**: `data/ai_graph_cloud.json`
(`cloud.CLOUD_GRAPH`). Würde er `graph.context_for_query()` ohne `store`
rufen, ginge Sashas kompletter Konzept-Graph mit jedem Turn an die API.
Getragen wird das vom Multi-Store in `core/graph.py` (`store`-Parameter, war
schon da) plus `store`-Durchreichung in `ki_antwort.mit_bildern` →
`consolidation.zug_vormerken` → `consolidation.extract_turn_into_graph`. Der Extraktor
selbst läuft weiterhin lokal — er schreibt nur in DEN Graphen, aus dem der
Turn kam. Das lokale Modell darf den Cloud-Graphen später lesen und einen
zweiten Layer darauf bauen; es schreibt nie hinein.

> **Was die Cloud trotzdem sieht:** Tool-*Ergebnisse* gehen zurück ans Modell
> — Dateiinhalte aus `read_file`, Kalendereinträge, Mail-Betreffzeilen,
> News-Texte. Nicht nur die Frage. Der Erlaubnis-Dialog begrenzt schreibende
> Aktionen, nicht den Abfluss lesender. Bewusst so, siehe `memory/betrieb/sicherheit.md`.

## Zweiter Dialekt – `core/cloud_openai.py`

Der Kern spricht **zwei** Cloud-Dialekte. Welchen, sagt `kind` in
`core/providers.py`:

| `kind` | Modul | Provider |
|---|---|---|
| `anthropic` | `core/cloud.py` | claude |
| `openai_compat` | `core/cloud_openai.py` | qwen (DashScope), openai, mistral |

Beide sind Drop-ins für `ai.chat_stream()` mit identischem Event-Protokoll.
Der statische System-Prompt kommt aus derselben Funktion
(`cloud._static_system()`), die ihn bei der aktiven Schiene holt.

**Gestoppt = geschätzt gebucht (seit 2026-10-07).** Der OpenAI-Dialekt
schickt die Zahlen erst im letzten Stück (`stream_options.include_usage` ist
gesetzt, hilft beim Abbruch also nicht). Wird gestoppt, bevor sie da sind,
bucht `cloud_openai._geschaetzt_buchen`: Eingabe = Länge der gesendeten
Nachrichten + Werkzeug-Liste / 3,5 Zeichen je Token, Ausgabe = empfangener
Text + Denken + halbe Werkzeug-Aufrufe / 3,5. `usage.buchen(…,
geschaetzt=True)` zählt normal mit (Budget-Deckel) und zusätzlich im Topf
`geschaetzt` pro Monat; Log „CLOUD ← … gestoppt, … geschätzt in≈ out≈".
**Seit 2026-10-08 auch bei Claude** (Sasha ok): `cloud._gestoppt_buchen`
bucht Eingabe + Cache aus `message_start`, die Ausgabe aus dem letzten
`message_delta` (Anthropic meldet sie kumuliert, in der Praxis nur einmal
am Ende) und schätzt den Rest — was seit dieser Zahl kam: Text + Denken +
halbe Werkzeug-Aufrufe (Name aus `content_block_start`, `input_json_delta`)
/ 3,5 (`usage.ZEICHEN_JE_TOKEN`, eine Regel für beide Wege).
`usage.buchen(…, output_geschaetzt=N)` legt nur den Preis dieser N Token in
den Topf `geschaetzt`; Log „CLOUD ← … gestoppt … out=gemeldet+≈N (geschätzt)".

**Modelle, die nicht in `prices.py` stehen** (seit `/modell` alles zeigt):
Datums-Fassungen und `models/…` finden ihren Grundnamen, `opus`/`fable` im
Namen bekommen den teuersten Preis ihrer Familie, sonst `UNBEKANNT`
(Sonnet-Preis). Nie 0 €; einmal je Lauf steht „PREIS ? <modell>: nicht in
der Preistabelle …" im Log (`usage.buchen`).

Der OpenAI-Pfad existiert vor allem, weil er die Struktur **prüfbar** macht,
ohne dass ein Anthropic-Key da sein muss: Routing, getrennter Cloud-Graph,
Gate, SSE bis in die TUI sind providerunabhängig. Ein zweiter echter
Provider ist der ehrlichere Test der Naht als ein zweiter Mock — erst wenn ein
fremdes Modell durch dieselbe Naht passt, ist es wirklich eine.

Was er **nicht** kann: `cache_control` (Anthropic-spezifisch; DashScope cacht
implizit und ohne messbares Signal), `thinking`/`effort`, `is_error` auf
Tool-Ergebnissen. `temperature` ist hier dagegen erlaubt und wird genutzt.
Liefert ein Modell `reasoning_content`, wird es als `reflect`-Event gespiegelt.

**Beide Provider teilen sich denselben Cloud-Graphen.** Die Grenze verläuft
zwischen „im Haus" und „draußen", nicht zwischen zwei Anbietern.

## Backend-Wahl

`ai_backends.pick("chat")` entscheidet pro Turn, wer denkt. Reihenfolge aus
`MODULE_BACKENDS["chat"] = (LOCAL, CLOUD)`, **aber** mit ausdrücklicher
Vorwahl `chat_backend()` (`auto` | `local` | `cloud`, in
`data/ai_config.json`, per `ZENTRALE_CHAT_BACKEND` übersteuerbar, im
TUI-Chat per `/lokal`, `/cloud`, `/auto`):

- **Stand 2026-08-15: `cloud`.** Sasha fährt daheim wie unterwegs bewusst
  cloud-only. `auto` ist die Zielform für später: sobald lokal wieder
  dazukommt, schaltet `auto` von selbst auf lokal, sobald Ollama da ist, und
  drosselt die Cloud. Der Umbau dafür ist dann eine Config-Zeile, kein Code.
- `auto` → lokal zuerst, solange Ollama läuft. Ohne die ausdrückliche Vorwahl
  gewinnt das lokale 9b jeden Turn, einfach weil es erreichbar ist.
- Eine ausdrückliche Wahl fällt **nicht still** auf das andere Backend zurück.
  Der Unterschied ist, ob Daten das Haus verlassen; das darf nicht aus
  Versehen passieren.
- Erreichbar heißt nicht bedienbar: ein Provider ohne `kind` in der Registry
  zählt für den Chat nicht, auch wenn ein Key gesetzt ist.

## Lokal-Regel (seit 2026-08-15, Schalter seit 2026-10-04)

Der Chat ist **nicht hart** gegatet. `ai_backends.chat_available()`
ist die eine Frage, die alle Chat-Endpoints stellen:

- Ein Knoten ohne lokale KI (`ai_backends.lokale_ki_aus()`, Env
  `ZENTRALE_LOKALE_KI=aus`, z. B. der Laptop) bringt **keine eigene KI** mit →
  `local` bleibt dort aus, auch wenn Ollama erreichbar wäre.
- Eine **Cloud**-KI ist nicht die KI dieses Knotens, sondern eine externe
  Leitung → die darf er nutzen. Das ist der Unterwegs-Fall: Laptop ohne
  Ollama, Chat trotzdem da.

Vier Endpoints hängen daran: `/api/chat`, `/api/chat/history`,
`/api/permission_answer` (sonst hängt ein Gate-Dialog für immer, weil niemand
die Antwort loswerden kann) und `/api/ai/status`.

`/api/ai/status` sagt seither nicht mehr „läuft Ollama", sondern „kann ich
chatten — und über welchen Kern": `backend: local|cloud|null` plus Modell und
Provider. Die **TUI ist ein Thin Client** (kein eigenes Modell, kein Memory —
nur HTTP gegen `/api/chat`) und schreibt das in ihren Kasten-Titel:
„ki-chat · cloud (qwen)". Beim Testen soll ohne Rätselraten sichtbar sein,
wer denkt.

## Modell-Parameter (Stand 2026-10-04, aus dem Code)

- **Modell:** `cloud._model()` = `ai_backends.chat_model("claude")` →
  `data/ai_config.json` `chat_models.claude` → Code-Default `claude-sonnet-5`
  (`providers.py`). Umstellen per Config (`set_chat_model`); eine Env
  dafür gibt es nicht (das frühere `ZENTRALE_CLOUD_MODEL` griff nie und ist
  seit 10/2026 raus).
- **Rundengrenze:** `ai_backends.runden_grenze(modell)` — `runden_grenzen`
  in der Config (`{"qwen3.5:9b": 5}`), sonst `STANDARD_RUNDEN = 100`
  (seit 09.10., nur Notbremse gegen Endlosschleifen). Gilt für alle Wege.
- **Denk-Tiefe:** `ai_backends.chat_effort()`, Default `low` —
  `ZENTRALE_CHAT_EFFORT` oder `chat_effort` in der Config.
- `max_tokens 16000` (`ZENTRALE_CLOUD_MAX_TOKENS`).
- `thinking: adaptive` mit `display: summarized`, nur für Modelle in
  `cloud._DENKT_ADAPTIV` → die Denk-Tokens werden live als `reflect`-Event in
  die TUI gespiegelt, genau wie Ollamas `thinking`-Feld.

(Bis 08/2026 stand hier `claude-opus-5` / `effort: medium` /
`ZENTRALE_CLOUD_EFFORT` — die Env-Variable gibt es nicht mehr.)

**Fallen der aktuellen API** (gelten auch für den Tutor — Repo `language-tutor`,
`tutor/modell/weg_anthropic.py`, dort `docs/tutor_system.md`):
- `temperature` / `top_p` / `top_k` → **400**. Kürze/Reproduzierbarkeit
  kommen nur noch aus dem Prompt.
- `thinking: {budget_tokens: N}` → **400**. Steuerung läuft über `effort`.
- `max_tokens` deckelt **Denken UND Antwort zusammen** — zu knapp heißt, die
  Antwort bricht ab, nachdem das Denken das Budget aufgefressen hat.
- `thinking: disabled` schreibt Tool-Calls gelegentlich als Fließtext statt
  als `tool_use`-Block; der Call läuft dann nie, ohne Fehler. Deshalb bleibt
  Denken überall an, notfalls auf `effort: low`.

## Lokales Modell

**Lokales Modell qwen3.5:9b — warum (2026-06-06, vorher qwen2.5:14b):** Reasoning-Bench (`scripts/bench_reasoning.py`)
zeigte es gleichstark zu qwen3:14b (10/11 ohne Thinking), aber schneller
(68 vs 47 tok/s) und kleiner (8.8 statt 11 GB VRAM → ~3 GB frei für
Browser/Desktop, behebt die VRAM-Contention-Crashes). Tool-Calling 100%,
kein Leak (`scripts/bench_models.py`). **Wichtig:** qwen3/qwen3.5 denken
per Default vor jeder Antwort (30–80 s Latenz!) → `ai.py` und
`consolidation.py` schicken `think=false` (nur für qwen3*, siehe
`_think_opts` / `SUPPORTS_THINK`). Per Env `OLLAMA_MODEL` umstellbar
(Fallback qwen3:14b / qwen2.5:14b).


### Warmup

`ai.warmup_async()` läuft beim Boot in einem Daemon-Thread:

- **Retry-Loop** vor dem Warmup-Chat: 5 Versuche × 3 s Pause, weil
  unser warmup-Thread beim Kalt-Boot oft Sekunden vor `ollama.service`
  ans Netz kommt. Erst nach ~15 s Stille geben wir auf und loggen
  `WARMUP ✗  Ollama nach 5 Versuchen … nicht erreichbar, überspringe`.
  Klappt's beim zweiten Versuch, kommt `WARMUP ✓  Ollama nach 2
  Versuchen erreichbar` ins Log.
- Mini-Chat mit `num_predict=1` (plus `think=false`) zieht qwen3.5:9b
  (~8.8 GB) in den RAM.
- Mini-Embed-Call zieht bge-m3 in den RAM.
- `OLLAMA_KEEP_ALIVE=30m` hält beide Modelle warm (Env-überschreibbar:
  `-1` = ewig, `0` = sofort unloaden für RAM-knappe Setups).
- `OLLAMA_NUM_CTX=8192` setzt das Kontextfenster **explizit** (Env-über-
  schreibbar). Ohne diese Option clampt Ollama auf seinen Mini-Default
  (2048–4096), obwohl qwen2.5 32768 könnte. Beide Chat-Payloads
  (`chat_stream` + `chat`) tragen jetzt `options={"num_ctx": …}`.
  **Hintergrund (2026-05-31):** Das war die Ursache fürs „Chinesisch-
  Durchbluten" mitten im Gespräch. Sobald System-Prompt + Graph-Kontext +
  Chat-History (deque `maxlen=50`) den kleinen Default sprengten, schnitt
  Ollama das Fenster vorne ab — genau wo die „nur lateinische Schrift"-
  Regel (`_CAPABILITIES_PROMPT` #4) sitzt. Regel weg → qwens bilinguale
  zh/en-Ader kam durch. Tutor-Reste wurden als Ursache **ausgeschlossen**
  (Graph CJK-frei, kein aktiver Tutor-Prompt im Chat-Pfad). 8192 hält die
  50er-History + Prompt im Fenster und passt in 12 GB VRAM neben dem ~9 GB
  Modell. Plan B falls's wiederkommt: `maxlen` kleiner (Graph hält ältere
  Fakten eh) oder nicht-bilinguales Modell — beides teurer, daher erst der
  num_ctx-Fix.

## Historie

- **2026-05** — Ollama mit qwen2.5:14b.
- **2026-05-31** — `num_ctx=8192` explizit.
- **2026-06-06** — qwen3.5:9b nach Bench.
- **2026-08-10** — Entscheidung für die Cloud; **08-15** `core/cloud.py`,
  `chat_backend: cloud`, Kassetten-Regel (heute Lokal-Regel), TUI als Thin Client.
- **2026-10-04** — Schalter `ZENTRALE_LOKALE_KI`; Modell-Parameter aus dem Code.
- **2026-10-07** — gestoppt = geschätzt gebucht (OpenAI); **10-08** auch Claude.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
