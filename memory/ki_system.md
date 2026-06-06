# KI-System

## Architektur

```
Browser ──POST /api/chat──▶ ui/app.py ──▶ core/ai.py ──▶ Ollama (qwen3.5:9b)
                                             │
                                             ├─▶ graph.py        (Konzept-Graph, primary memory)
                                             ├─▶ embeddings.py   (bge-m3, Alias-Resolution + Entry-Points)
                                             ├─▶ consolidation.py (async Fakt-Extraktion in den Graphen)
                                             └─▶ context.py      (Datei-Whitelist)
```

`ai.py` ist der einzige Ollama-Client für Chat-Calls. `embeddings.py` und
`consolidation.py` reden ebenfalls direkt mit Ollama (Embeddings bzw.
Extraktor-LLM), aber alle gehen durch `core/net.py` – damit landet jeder
Request im Terminal (siehe Network-Transparenz unten).

**Modell-Update (2026-06-06):** Default ist jetzt **qwen3.5:9b** (vorher
qwen2.5:14b). Begründung: Reasoning-Bench (`scripts/bench_reasoning.py`)
zeigte es gleichstark zu qwen3:14b (10/11 ohne Thinking), aber schneller
(68 vs 47 tok/s) und kleiner (8.8 statt 11 GB VRAM → ~3 GB frei für
Browser/Desktop, behebt die VRAM-Contention-Crashes). Tool-Calling 100%,
kein Leak (`scripts/bench_models.py`). **Wichtig:** qwen3/qwen3.5 denken
per Default vor jeder Antwort (30–80 s Latenz!) → `ai.py` und
`consolidation.py` schicken `think=false` (nur für qwen3*, siehe
`_think_opts` / `SUPPORTS_THINK`). Per Env `OLLAMA_MODEL` umstellbar
(Fallback qwen3:14b / qwen2.5:14b).

## Memory-Architektur (Phase G – Konzept-Graph)

Aktiver Stand: **Graph ist primary** und einzige Memory-Schicht. Was
die KI bei jedem Turn "sieht", kommt komplett aus dem Graphen
(plus `_now_prompt`-Zeitstempel, plus optional Kalender-Layer wenn
das System hochgefahren ist).

### `core/graph.py` – Konzept-Graph (primary)

- **Knoten:** Konzepte als Labels (Entitäten, Zustände, Orte, Zeitpunkte).
- **Edges:** typisierte, gewichtete Relationen.
- **Speichert nur Sashas konkrete Realität**, kein generisches Weltwissen.
- **Embeddings drei Rollen:**
  1. Alias-Resolution beim Schreiben ("der Pi" == "mein Raspberry"),
     Cosinus + Token-Overlap-Bonus, Schwelle `ALIAS_THRESHOLD=0.78`.
  2. Fuzzy Entry-Point beim Lesen (Query → nächste Knoten finden).
  3. **Kein** Top-K-Retrieval – das macht Aktivierungs-Spread (`DEFAULT_HOPS=2`,
     `DEFAULT_DECAY=0.5`).
- **Zeit als Knoten:** Tage/Monate/Jahre sind eigene Knoten. Jedes
  erwähnte Konzept kriegt automatisch eine `erwähnt-am`-Kante zum
  heutigen Datum-Knoten. "heute"/"gestern" werden NIE als Knoten
  gespeichert – immer zu ISO-Dates aufgelöst.
- **Datei:** `data/ai_graph.json`.
- **Public API:** `context_for_query(query)`, `add_turn_extraction(nodes, edges)`,
  `ensure_seed()`, `stats()`, `dump()`.

### `core/consolidation.py` – async Extraktor

Läuft nach jedem Chat-Turn als Daemon-Thread:

1. Strenger JSON-Extraktor-Prompt (Anti-Halluzination) gegen den letzten
   User-Turn + AI-Antwort.
2. Sanity-Filter (`_sanitize_extracted`) wirft Müll raus bevor er in
   den Graphen kommt:
   - **Edge-Verb-Whitelist** (`_ALLOWED_EDGE_VERBS`, 16 Verben): alles
     außerhalb wird gedroppt. Killt halluzinierte Relations wie
     `wohlbehalten`, `kennet`, `aktuelles-Datum`, `definiert` die der
     Extraktor trotz Prompt-Disziplin erfindet.
   - **Datum-als-Subjekt**: Edges deren `from` ein YYYY-MM-DD-Knoten
     ist fliegen raus. Korrekte Richtung ist immer `<konzept>
     ─[erwähnt-am/geschah-am]─► <datum>`, nicht andersrum.
   - **KI↔Sasha Subjekt-Tausch**: Edges wie `KI ─[arbeitet-an]─► Sasha`
     bei eigenschafts-richtigen Relations (`arbeitet-an`, `hat`, `mag`,
     `fühlt`, `zustand`, `kann`, `kann-nicht`, `besitzt`, `wohnt-in`,
     `macht`) sind immer Müll. `ist` und `kommuniziert-mit` sind
     ausgenommen.
   Drops werden ins UI-Terminal geloggt (`GRAPH-SANITY verworfen: …`).
3. Saubere Knoten/Edges via `graph.add_turn_extraction()` in den
   Graphen merged (Alias-Resolution greift hier).
4. Trivialer Smalltalk wird übersprungen (Skip-Regel im Extraktor-Prompt).

Trigger: nach jedem vollständigen Chat-Turn (`_async_save_turn` in
`ai.py`). Das alte STM/LTM-Konsolidierungs-Pattern (Trigger `/sleep` oder
Inaktivität) ist nicht mehr aktiv – Graph wächst inkrementell.

**One-shot Cleanup für Altbestand:** `scripts/graph_cleanup.py` läuft
dieselbe Sanity gegen `data/ai_graph.json` (dry-run by default,
`--apply` schreibt mit Timestamp-Backup). Beim Einführen der Whitelist
fielen ~15% der Edges weg (22 Verb-Halluzinationen, 6 Datum-Subjekte,
1 KI↔Sasha-Tausch).

### `core/embeddings.py` – bge-m3 via Ollama

- Modell: `bge-m3` (BAAI, 1024-dim, ~570 MB), multilingual.
- Frühere Wahl `nomic-embed-text` war zu englischlastig – deutsche
  Queries fanden den Bezug schlecht.
- Per `OLLAMA_EMBED_MODEL` umstellbar; pro Modell eigene Prefix-Logik
  in `_PREFIXES_BY_MODEL`.
- API: `embed(text)`, `embed_query(text)`, `cosine_similarity(a, b)`,
  `top_k(query_vec, entries, k)`.
- Kleiner LRU-Cache für wiederkehrende Texte.
- **bge-m3 läuft auf der CPU** (`options={"num_gpu": 0}` im `/api/embed`-Call).
  **Warum (2026-06-01):** qwen @ `num_ctx=8192` (~10,5 GB) füllt die 12-GB-
  RTX-4070 schon allein bis zum Rand (lief `6%/94% CPU/GPU`). Lag bge-m3
  zusätzlich auf der GPU, warf Ollama bei *jedem* Embed-Call qwen komplett
  raus (Ollama entlädt ganze Modelle, statt zu quetschen) und lud es danach
  9 GB neu von der Platte → **30–50 s bis zum ersten Wort**. Diagnose-Kette:
  blankes Modell flott (340 ms) → TTS unschuldig → Retrieval billig (~100 ms)
  → `ollama ps` zeigte qwen rausgeflogen, nur bge-m3 geladen. Embed ist ein
  kleiner (560M) Job, **1× pro Frage, vor der Generierung** → CPU kostet nur
  ~100–300 ms (warm) bzw. ~2 s (Kaltstart), tut nicht weh und lässt qwen
  dauerhaft auf der GPU. iGPU als Plan B verworfen (Ollama-Multi-Backend-
  Gefrickel, kaum schneller).

### Entfernt: Legacy LTM/STM (Phase D/E)

`core/memory.py`, `consolidate_stm()`, `maybe_consolidate_due_to_inactivity()`,
`note_user_turn()`, das `save_memory`-Tool und die `/sleep`/`/forget`/
`/memory`-Slash-Commands sind komplett raus. Begründung:

- Phase G las das LTM nicht mehr (nur der Graph wird in den
  System-Prompt injiziert). Schreib- und Lese-Pfad waren asymmetrisch –
  die KI füllte fleißig `ai_ltm.json` (>200 KB), bekam davon aber im
  nächsten Turn nichts mehr zu sehen.
- Pro Turn kosteten die Background-Threads (`maybe_consolidate_…` plus
  eventueller `/sleep`-Trigger) zusätzliche LLM- und Embedding-Calls
  ohne Gegenwert – mitverantwortlich für die langen Antwort-Latenzen.
- Datendateien `data/ai_ltm.json` und `data/ai_stm.json` sind nicht mehr
  Code-relevant und können archiviert werden.

Wenn ein Konzept-Browser im UI wieder gebraucht wird, exponieren wir
`graph.stats()`/`graph.dump()` über einen eigenen `/api/graph/...`-
Endpoint – die alte `/api/memory`-Form ist nicht mehr passend
(Embedding-pro-Eintrag-Schema vs. Knoten+Edges).

## Tool-Use

Das Modell kann Tools "aufrufen" – ZENTRALE führt sie aus und schickt
das Ergebnis zurück in den Kontext. Funktioniert mit jedem Tool-Use-
fähigen Ollama-Modell; Default `qwen3.5:9b` (Env `OLLAMA_MODEL`).

| Tool          | Funktion                                            |
|---------------|-----------------------------------------------------|
| `read_file`   | Datei aus der Whitelist lesen                       |
| `list_files`  | Verfügbare lesbare Dateien auflisten                |

Tool-Calls werden streng ans Dashboard-Terminal geloggt
(`AI → TOOL read_file(...)` / `AI ← TOOL read_file → ok`). Sichtbar
machen ob die KI ein Tool wirklich gerufen hat oder es nur behauptet.

### Visuelle Stimme – Bild-Marker `[[bild: name]]`

Die KI zeigt Mimik/Gesten, *während* sie mit Worten antwortet: ein
passendes ASCII-Bild übernimmt kurz den Dashboard-Kern. Sie **malt nicht
selbst** – ein 9b-Modell ist mies im freien ASCII-Malen (2D-Layout über
1D-Tokenstrom), aber gut im Greppen. Also kuratiert es aus einer hand-
gepflegten Bibliothek (`data/ascii/*.txt`, Modul
[`core/ascii_lib.py`](../core/ascii_lib.py); Ordner per Env
`ZENTRALE_ASCII_DIR`).

**Kein Tool, sondern ein Inline-Marker.** Das war eine bewusste Kehrt-
wende, gemessen mit [`scripts/bench_ascii.py`](../scripts/bench_ascii.py):
als Tool (`zeige_ascii`) feuerte die KI bei impliziten Prompts nur **2,7 %**
(N=200) – und tippte den Aufruf oft als Text-Marker `[[zeige_ascii: name]]`
statt einen echten Tool-Call zu machen (Mimikry vom alten `[[emoji:]]`-
Muster). Lehre aus [[feedback_prompt_no_muzzle]]: nicht gegen das Modell
anprompten, sondern es dort treffen wo es hinwill. Umbau auf einen Inline-
Marker hob die Quote auf **~93 %**. Die KI tippt `[[bild: stichwort]]`
mitten in ihre Antwort; das Backend zieht den Marker raus, sucht das Bild
und feuert es separat. Kein „ich kann dir zeigen…"-Ankündigen mehr (ein
Marker wird getippt, nicht angekündigt).

- **Datei-Format:** optionale erste Zeile `# tags: a, b, c`, danach reine
  ASCII-Art. Fehlt die tags-Zeile → Dateiname ist der einzige Tag. Neue
  Bilder einfach als `.txt` reinlegen (Backend neu starten, damit die
  Stichwort-Liste im Prompt `_ASCII_MARKER_PROMPT` aktuell wird).
- **Matching (Hybrid):** Stufe 1 Tag/Keyword (exakt > Substring >
  Token-Überlappung), schnell + vorhersehbar. Greift nichts → Stufe 2
  Embedding-Fallback (bge-m3, Stichwort=query gegen Tags=document) mit
  Cosinus-Schwellwert `0.55`. Auch darunter → **kein Bild** (lieber keins
  als ein falsches). Verfügbare Stichworte stehen im Prompt (wie
  `RANGE_BUCKETS` beim Kalender), damit die KI nicht blind rät.
- **Pipeline:** `_extract_ascii_markers` (Regex, tolerant: `[[bild:]]`,
  `[[ascii:]]`, `[[zeige_ascii:]]`) zieht im regulären Chat die Marker aus
  der finalen Antwort, `ascii_lib.pick` matcht, `chat_stream` yieldet pro
  Treffer ein **Inline-Event** (`dict {"ascii","name"}`); `app.py` macht
  daraus ein SSE-Event `ascii`. Der bereinigte Text (ohne Marker) wird
  gesprochen/gespeichert. Tutor-Modus kennt die Marker NICHT. Frontend:
  siehe „ASCII-Kern / Bild-Marker" in [dashboard.md](dashboard.md).
- **Alt-Namen:** die 15 Namen des früheren `[[emoji:]]`-Kanals (shrug,
  happy, flip, …) sind als englische Alias-Tags in der Bibliothek
  hinterlegt, lösen also weiter auf.

`save_memory` ist mit dem Legacy-Pfad rausgeflogen – der Graph-Extraktor
läuft eh nach jedem Turn automatisch. Kalender-Tools (`read_calendar`,
`add_entry`, `add_routine`) kommen mit dem Kalender-System (siehe
[calendar_system.md](calendar_system.md)).

**Sicherheitsnetz:** `chat_stream` hat ein hartes `max_rounds = 5` für
die Tool-Loop – verhindert Endlosschleifen bei kaputten Tool-Calls.

**Streaming-Detail:** Tool-Calls kommen im **letzten** Streaming-Chunk
(`done=true`) im Feld `tool_calls`. Heißt: erst auf das Ende des Streams
warten, dann Tools auflösen.

## System-Prompt-Komposition

Reihenfolge im System-Prompt (siehe `core/ai.py`):

1. **`_now_prompt()`** – dynamisch pro Turn gebaut: heutiges Datum,
   Wochentag, aktuelle Uhrzeit. **Ganz vorne**, damit das LLM bevor es
   irgendetwas anderes liest weiß welcher Tag jetzt ist. Schließt das
   Zeit-Loch: vorher lebte das Datum nur als Aktivierungs-Anker im
   Graphen – die KI konnte Time-Knoten sehen, aber nicht wissen welcher
   davon "heute" ist, und hat dann aus den aktivierten alten Tagen
   geraten. Symptom war "die letzte Konversation war am 19.5., die am
   21.5. war bereits danach"-Logik-Quatsch.
2. **`_SYSTEM_PROMPT`** – Persona (entspannt, direkt, deutsch).
3. **`_CAPABILITIES_PROMPT`** – Meta-Regeln: nicht lügen über Memory;
   nicht erfinden über Sasha; **Subjekt-Grenze** (Sashas Gefühle/Zustände
   NIE als eigene ausgeben → Anti-Identity-Bleed, mit konkretem Beispiel);
   nicht erfinden über eigene Fähigkeiten (was unter „Das kannst DU NICHT"
   steht, nie behaupten zu können); lateinische Schrift; reale Wörter.
   Bei jedem Turn injiziert.
4. **`graph.context_for_query(user_query)`** – aktiviertes Wissen aus
   dem Graphen (Spread-Aktivierung von Entry-Points aus). Kann leer
   sein → KI sagt dann "noch nichts gespeichert" statt zu raten
   (Anti-Konfabulation). **Seit 2026-06-06 nach SUBJEKT getrennt
   gerendert** – drei Abschnitte „Über SASHA" / „Das kannst DU" / „Das
   kannst DU NICHT" statt flacher Liste. Verhindert dass das Modell
   Sashas Zustände („einsam") als eigenes Gefühl oder Limit-Knoten
   („Bilder generieren") als eigene Fähigkeit liest. Nötig mit qwen3.5
   (weniger guarded als qwen2.5). Trennung nur per `type`-Feld
   (self/capability/limit), siehe Render-Block in `core/graph.py`.
5. **`_MIC_INPUT_HINT`** – *konditional*, nur wenn die letzte
   User-Message per Whisper-Spracheingabe kam (`via_mic=True`). Sagt
   der KI: Transkription kann Wörter verfälschen, bei semantischen
   Brüchen lieber nachfragen statt wörtlich antworten. Standard-Chat
   (Tastatur) sieht den Block nicht – Token-Ersparnis. Trigger-Pfad:
   Browser → `/api/chat` mit `via_mic: true` → `chat_stream(via_mic=True)`.

Konkrete Capabilities/Limits leben als Graph-Knoten (`graph.ensure_seed()`)
und kommen via Aktivierungs-Spread in den Wissens-Block, statt fest
ins System-Prompt zu wandern. Das gilt **auch für die Identität der KI
selbst** (Tools, Grenzen, "wer bin ich"): der Graph ist *ihre* Memory,
nicht nur ein Faktenspeicher über Sasha. Deshalb verweist Meta-Regel 4
(Fähigkeiten/Grenzen) auf den Wissens-Block statt feste Tool-Namen
hardzucoden – fügt man der KI einen neuen Knoten "Tool X" hinzu, weiß
sie es ohne Prompt-Änderung. Verhindert auch, dass das Pretraining
(qwen kennt Claude-Code-Skill-Namen wie `update-config` aus öffentlichen
Docs) sich als eigene Fähigkeit ausgibt.

## Warmup

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

## Network-Transparenz

Alle HTTP-Requests werden im Dashboard-Terminal sichtbar geloggt
(via `core/net.py`):

```
NET →  POST http://localhost:11434/api/chat
NET ←  200 http://localhost:11434/api/chat (2341 B)
STT →  POST http://localhost:5050/transcribe (48 KB)
STT ←  '我很好' (Konfidenz: 94%)
TTS →  POST http://localhost:5051/speak '你好！'
TTS ←  62 KB WAV
```

Plus die Tool-Use-Zeilen (`AI → TOOL ...` / `AI ← TOOL ...`).

### Zwei stdout-Channels: Voll-Stream vs. Internet-Tripwire

Der Footer im Dashboard ist in zwei Terminals gesplittet:

- **Links** = voller `state._logs`-Stream (alles oben Gezeigte).
- **Rechts** = nur Internet-Traffic. Quelle: `state._internet_logs`,
  gespiegelt aus `net.py` wenn `net._is_internet(url)` True liefert.

`_is_internet(url)` klassifiziert defensiv:

- localhost / `127.0.0.1` / `::1` / `0.0.0.0` → False (lokal)
- Private-Ranges (`10/8`, `172.16/12`, `192.168/16`) → False (LAN)
- Link-local (`169.254/16`) → False
- `*.local` Hostnames (mDNS) → False
- IPv6-Loopback / -Link-local / -Private → False
- Alles andere (Public-IPs, normale Hostnames) → True

Da ZENTRALE als vollständig offline gedacht ist, soll das rechte Panel
**leer** bleiben. Sobald da was reinläuft, hat tatsächlich ein Paket
das LAN verlassen – sichtbarer Alarm statt versteckt im großen Stream.
Implementation: `core/net.py` (`_is_internet`, plus Spiegel-Calls in
`_log_out/_log_in/_log_err`), `core/state.py` (`_internet_logs`,
`push_internet_log`), `ui/templates/index.html` (`.terminal-row` +
`.terminal-net` mit orangefarbenem Akzent).

Tests: `scripts/test_net_internet.py` (48 Cases, untracked).

## Chat-Modus

- KI-Chat mit qwen3.5:9b (oder via `OLLAMA_MODEL`), tokenweise gestreamt.
- KI hat Zugriff auf Whitelist-Dateien + Graph-Memory.
- Slash-Commands im Chat:
  - `/memory` – Memory-Stats anzeigen (Graph + LTM)
  - `/forget N` – Legacy: LTM-Eintrag Nr. N löschen
  - `/clear` – Chat-History leeren
- ESC – zurück zum Haupt-Dashboard.

## Voice-Pipeline (Core, sprachneutral)

STT und TTS hängen nicht mehr am Tutor, sondern an der Core-AI:

- `POST /api/transcribe` – Audio → Text (Whisper, `lang`-Param)
- `POST /api/speak` – Text → WAV (Piper für `de`, sherpa-onnx für `zh`)

Der Tutor ist ein Konsument dieser Pipeline mit `lang='zh'`. Details:
`audio_system.md` und `api_endpoints.md`.
