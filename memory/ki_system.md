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
| `read_calendar` / `add_calendar_*` / `delete_calendar_entry` | Kalender lesen/schreiben/löschen (s. kalender_system.md) |
| `web_suche`   | Im Internet suchen (gegatet, s. „Internet-Pipe")    |
| `hole_url`    | Webseite laden + Text holen (gegatet)               |
| `lies_news`   | Weltpolitik-Briefing lesen (persönliche Tagesschau, s. `news_system.md`) |
| `antwort`     | Finale Antwort über Tool-Kanal (Framing-Effekt)     |
| `frage_knopf` | Sasha eine Frage mit Knöpfen stellen (s. unten)     |

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

### Internet-Pipe – `web_suche` + `hole_url` (seit 2026-06-07)

ZENTRALE war bis hierhin vollständig offline (außer lokalem Ollama). Diese
zwei Tools sind das einzige, was bewusst nach draußen telefoniert:

- **`web_suche(query)`** – sucht im Internet, liefert die Top-Treffer als
  Liste (Titel, URL, Snippet). Für aktuelles Wissen, News, Wetter, Fakten,
  die nicht im Graphen/in Dateien stehen.
- **`hole_url(url)`** – lädt eine konkrete Seite und gibt den Textinhalt
  zurück (HTML→Text, gekürzt auf ~4000 Zeichen, damit `num_ctx=8192` nicht
  überläuft). Typischer Ablauf: erst `web_suche`, dann `hole_url` auf einen
  Treffer.

**Implementation:** [`core/web.py`](../core/web.py). Die eigentliche Such-
Quelle steckt bewusst in **einer** Funktion: seit 2026-06-08 ist das primär
**SearXNG self-hosted** (`_searxng_search`, lokaler Docker-Container auf
`localhost:8888`, JSON-Modus). SearXNG ist ein Meta-Such-Aggregator – ER
fragt im Hintergrund Google/Bing/DDG/… ab und liefert uns sauberes JSON.
Vorteil gegenüber dem alten Scraping: stabiles Format statt fragiler HTML-
Regexe, keine Anti-Bot-Landingpage (DDG hatte uns geblockt), Upstream-Suchen
laufen unter SearXNGs Identität. **Fallback:** läuft der Container nicht,
fällt `suche()` automatisch auf das alte `_ddg_search` zurück (DuckDuckGo
keyless, HTML-Endpoint gescraped, mit Ad-Filter gegen `y.js`-Werbung) –
dann ist wenigstens nichts komplett tot. Quelle wechseln = weiterhin nur
diese eine Funktion tauschen, `suche()`/`hole()`/`ai.py` bleiben unangetastet.

> **SearXNG-Container:** `sudo docker run -d --name searxng --restart
> unless-stopped -p 8888:8080 -v ~/searxng:/etc/searxng searxng/searxng`.
> Konfig in `~/searxng/settings.yml` (`use_default_settings: true`,
> `secret_key`, `limiter: false`, `formats: [html, json]`). `docker` braucht
> `sudo` (Sasha nicht in der docker-Gruppe). Test:
> `curl 'localhost:8888/search?q=test&format=json'`.

**Gating:** beide Tools stehen in `PERMISSION_REQUIRED_TOOLS` → **jeder**
Call löst den JA/NEIN-Knopf-Dialog aus (Sasha sieht die Suchanfrage / die
URL, bevor das Paket rausgeht). Konsequent zur Transparenz-Philosophie.
Frage-Vorlagen in `_permission_question` (z.B. »Soll ich im Internet nach
"…" suchen?«).

**Transparenz:** Aller HTTP-Verkehr läuft durch `core/net.py`. `hole_url` und
der DDG-Fallback treffen echte Internet-Ziele → leuchten **automatisch** im
orangen Internet-Panel auf. **SearXNG ist der Sonderfall:** der Call geht an
`localhost:8888`, also stuft `net._is_internet` ihn als lokal ein und das
Panel bliebe leer – OBWOHL SearXNG dahinter echtes Internet anfasst. Damit
die Tripwire-Linie hält, loggt `_searxng_search` die Suchanfrage **explizit**
in den Internet-Channel (`state.push_internet_log("NET → SUCHE „…" (via
SearXNG)")`). Man sieht im Panel also weiterhin, dass + wonach gesucht wurde.

**KI-Selbstbild:** Die Internet-Limits im Identity-Graphen (»auf das Internet
zugreifen«, »Web-Suche durchführen«, »Echtzeit-News/Wetter abrufen«) wurden
zu Fähigkeiten (»im Internet suchen«, »Webseiten abrufen«). Code:
`graph._SEED_CAPABILITIES`/`_SEED_LIMITS` (frische Installs) +
`graph.migrate_internet_access()` (zieht bereits geseedete Graphen nach,
idempotent, hängt in `ai._ensure_seed_once` → self-healing bei jedem Boot).

### Knopf-Dialog: Auto-Gate + `frage_knopf`

Das Dashboard kann die Konsolen-Eingabe gegen **2–4 Knöpfe** tauschen
(navigierbar per Pfeiltasten + Enter, Kiosk ohne Maus). Zwei Auslöser, ein
geteilter Mechanismus (blockierender `state.wait_permission`):

**(A) Auto-Gate für sensible Tools** — bestätigungspflichtige Tools
(`PERMISSION_REQUIRED_TOOLS` in `core/ai.py`: die Kalender-Schreiber
`add_calendar_entry`, `add_calendar_routine`, `add_calendar_pause`,
`delete_calendar_entry` **plus** die Internet-Pipe `web_suche`, `hole_url`) fängt das Backend **vor der
Ausführung** ab und zeigt **JA / NEIN**. Nur bei „ja" läuft das Tool, bei
„nein"/Timeout wird es übersprungen. Lokales Lesen/Auskunft (`read_calendar`,
`read_file`, …) bleibt ungated; alles was Daten schreibt oder das LAN verlässt
ist gegatet.

> **Nicht modellgetrieben – Absicht.** Die KI ruft ihr Schreib-Tool ganz
> normal; das Gate kommt automatisch davor. Frühere Idee war ein Tool
> `frage_erlaubnis`, das die KI von sich aus ruft – verworfen, weil ein 9b
> das **nicht zuverlässig** vor jedem Eingriff täte ([[feedback_permission_gate_backend]],
> [[project_history_vergiftung]]). Ein hart verdrahtetes Gate auf der Tool-
> Liste ist robust statt vom Modellverhalten abhängig.

**(B) `frage_knopf` – KI-initiiert** — braucht die KI mitten in einer Aufgabe
eine knappe diskrete Entscheidung (statt auf freien Text zu warten), ruft sie
**selbst** `frage_knopf(frage, optionen=[…])`. Ohne `optionen` = Ja/Nein, sonst
2–4 eigene Labels (z.B. `["Deutsch","Englisch"]`). Das gewählte Label kommt als
`tool`-Result zurück, die KI macht im selben Zug weiter. Anders als das Gate ist
das bewusst modellgetrieben – es ist kein Sicherheits-Riegel, sondern ein
Rückfrage-Werkzeug, das die KI gezielt einsetzt.

**Mechanik – blockierend, nahtlos (ein Zug):**

1. **Gate (A):** Im Tool-Loop (`chat_stream`) greift VOR `active_exec` der
   Check `fn_name in PERMISSION_REQUIRED_TOOLS`; `_permission_question(name,
   args)` baut die Frage („Soll ich »Zahnarzt« am … eintragen?"), Optionen =
   Default Ja/Nein. **`frage_knopf` (B):** eigener Branch baut Frage + Optionen
   aus den Call-Args (sanitisiert: ≥2, max 4). Beide rufen
   `state.request_permission(options, timeout_default)`, yielden ein
   **permission-Event** (`{"permission": {"frage", "optionen"}}`) und
   **blockieren** in `state.wait_permission()`.
2. `app.py` macht ein SSE `permission` daraus; das Frontend zeigt die Frage als
   KI-Zeile (+ TTS) und baut die Knopf-Leiste dynamisch aus `optionen` (fehlt →
   JA/NEIN). Der SSE-Reader läuft **nicht** zu Ende – die Verbindung bleibt offen.
3. Klick → `POST /api/permission_answer {answer}` (eigener Thread), gegen die
   angebotenen Labels validiert (case-insensitiv, kanonisches Label zurück) →
   `state.answer_permission()` setzt das `threading.Event` → der blockierte
   `chat_stream` wacht auf. Gate: bei „ja" durchfallen zur Ausführung, sonst
   abschlägiger `tool`-Result. `frage_knopf`: gewähltes Label als `tool`-Result.
   Beides im **selben Zug**.

Das funktioniert nur, weil Flask **multi-threaded** läuft
(`app.run(threaded=True)`, explizit) – sonst käme der Antwort-Request am
blockierten Stream nicht vorbei → Deadlock. `wait_permission` (180 s Timeout)
gibt den bei `request_permission` gesetzten `timeout_default` zurück: beim Gate
**„nein"** (sicher – keine Antwort erlaubt nie eine Schreib-Aktion), bei
`frage_knopf` ein neutrales `(keine Antwort)`. Log: `AI → ERLAUBNIS?`/`FRAGE …`
bzw. `AI ← ERLAUBNIS:`/`WAHL: …`. Frontend-Details (perm-bar, N-Knopf-Nav):
[dashboard.md](dashboard.md). Tutor-Modus: beides aus (fremdes Tool-Set). Neues
Tool gaten = Name in `PERMISSION_REQUIRED_TOOLS` + ggf. Vorlage in
`_permission_question`.

`save_memory` ist mit dem Legacy-Pfad rausgeflogen – der Graph-Extraktor
läuft eh nach jedem Turn automatisch. Kalender-Tools (`read_calendar`,
`add_entry`, `add_routine`) kommen mit dem Kalender-System (siehe
[kalender_system.md](kalender_system.md)).

**Sicherheitsnetz:** `chat_stream` hat ein hartes `max_rounds = 5` für
die Tool-Loop – verhindert Endlosschleifen bei kaputten Tool-Calls.

**Streaming-Detail:** Tool-Calls kommen im **letzten** Streaming-Chunk
(`done=true`) im Feld `tool_calls`. Heißt: erst auf das Ende des Streams
warten, dann Tools auflösen.

## System-Prompt-Komposition

Reihenfolge im System-Prompt (siehe `_PROMPT_ORDER` in `core/ai.py`):
**erst alles Statische, dann alles, was sich pro Turn ändert.** Zwei Gründe
für diesen Schnitt, ein Handgriff — Prompt-Cache (ein Treffer braucht ein
byte-identisches Präfix, und der Jetzt-Block enthält die Uhrzeit) und Recency
(was zuletzt steht, sitzt am dichtesten an der User-Message).

1. **`_SYSTEM_PROMPT`** – Persona (entspannt, direkt, deutsch).
2. **`_CAPABILITIES_PROMPT`** – Meta-Regeln: nicht lügen über Memory;
   nicht erfinden über Sasha; **Subjekt-Grenze** (Sashas Gefühle/Zustände
   NIE als eigene ausgeben → Anti-Identity-Bleed, mit konkretem Beispiel);
   nicht erfinden über eigene Fähigkeiten (was unter „Das kannst DU NICHT"
   steht, nie behaupten zu können); lateinische Schrift; reale Wörter.
   Bei jedem Turn injiziert.
3. **`graph.context_for_query(user_query)`** – aktiviertes Wissen aus
   dem Graphen (Spread-Aktivierung von Entry-Points aus). Kann leer
   sein → KI sagt dann "noch nichts gespeichert" statt zu raten
   (Anti-Konfabulation). **Seit 2026-06-06 nach SUBJEKT getrennt
   gerendert** – drei Abschnitte „Über SASHA" / „Das kannst DU" / „Das
   kannst DU NICHT" statt flacher Liste. Verhindert dass das Modell
   Sashas Zustände („einsam") als eigenes Gefühl oder Limit-Knoten
   („Bilder generieren") als eigene Fähigkeit liest. Nötig mit qwen3.5
   (weniger guarded als qwen2.5). Trennung nur per `type`-Feld
   (self/capability/limit), siehe Render-Block in `core/graph.py`.
4. **`_now_prompt()`** – dynamisch pro Turn: heutiges Datum, Wochentag,
   Uhrzeit. Schließt das Zeit-Loch: vorher lebte das Datum nur als
   Aktivierungs-Anker im Graphen – die KI konnte Time-Knoten sehen, aber
   nicht wissen welcher davon "heute" ist, und hat dann aus den aktivierten
   alten Tagen geraten (Symptom: "die letzte Konversation war am 19.5., die
   am 21.5. war bereits danach"-Logik-Quatsch). Steht **direkt hinter dem
   Graph-Kontext**, weil er genau dessen Datums-Knoten korrigiert – und
   hinten ist er nicht schwächer als vorne, sondern präsenter.
5. **`_alarm_prompt()`** – *konditional*, offene Kalender-Erinnerungen.
6. **`_MIC_INPUT_HINT`** – *konditional*, nur wenn die letzte
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

## Cloud-Kern – `core/cloud.py` (Anthropic)

Zweiter Denk-Pfad für den Kern, **Drop-in für `ai.chat_stream()`**: gleiche
Signatur, gleiches Event-Protokoll (`reflect` / `ascii` / `permission` /
`cinema` / Text), gleiches Erlaubnis-Gate. Grund für den Umstieg: das Projekt
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
schon da) plus `store`-Durchreichung in `ai._answer_with_images` →
`ai._async_save_turn` → `consolidation.extract_turn_into_graph`. Der Extraktor
selbst läuft weiterhin lokal — er schreibt nur in DEN Graphen, aus dem der
Turn kam. Das lokale Modell darf den Cloud-Graphen später lesen und einen
zweiten Layer darauf bauen; es schreibt nie hinein.

> **Was die Cloud trotzdem sieht:** Tool-*Ergebnisse* gehen zurück ans Modell
> — Dateiinhalte aus `read_file`, Kalendereinträge, Mail-Betreffzeilen,
> News-Texte. Nicht nur die Frage. Der Erlaubnis-Dialog begrenzt schreibende
> Aktionen, nicht den Abfluss lesender. Bewusst so, siehe `sicherheit.md`.

### Prompt-Cache

Der System-Prompt geht als **zwei Blöcke** raus: `[0]` statisch mit
`cache_control: ephemeral`, `[1]` wechselnd (Graph, Jetzt, Alarme, Mic).
Gerendert wird `tools → system → messages`, ein Breakpoint auf dem letzten
statischen Block cacht also **Tool-Schema und statischen Prompt zusammen** —
die ~8.000 Token, die sonst bei jedem Turn UND jeder Tool-Runde voll bezahlt
würden. Cache-Treffer kosten 10 % des Input-Preises; das ist der mit Abstand
größte Kostenhebel (~45 €/Monat → ~18 €/Monat bei 30 Austauschen/Tag).

**Kontrolle:** jede Runde loggt `CLOUD ← in=… cache_read=… cache_write=…
out=…` ins Dashboard-Terminal. Bleibt `cache_read` über mehrere Turns 0, hat
sich etwas im statischen Block verändert — ein kaputter Cache fällt sonst nur
auf der Monatsrechnung auf.

### Zweiter Dialekt – `core/cloud_openai.py`

Der Kern spricht **zwei** Cloud-Dialekte. Welchen, sagt `kind` in
`core/providers.py`:

| `kind` | Modul | Provider |
|---|---|---|
| `anthropic` | `core/cloud.py` | claude |
| `openai_compat` | `core/cloud_openai.py` | qwen (DashScope), openai, mistral |

Beide sind Drop-ins für `ai.chat_stream()` mit identischem Event-Protokoll.
Die **Bedeutung** eines Tool-Calls — was terminal ist (`antwort`, `lies_news`),
was durchs Gate muss — steht genau einmal, in `cloud.run_tool()`; die beiden
Loops unterscheiden sich nur darin, wie sie das Ergebnis verpacken
(`tool_result`-Block vs. `role: "tool"`-Message). Auch der System-Prompt kommt
aus derselben Funktion (`cloud._system_blocks`), der OpenAI-Pfad faltet die
zwei Blöcke nur zu einem String.

Der OpenAI-Pfad existiert vor allem, weil er die Struktur **prüfbar** macht,
ohne dass ein Anthropic-Key da sein muss: Routing, getrennter Cloud-Graph,
Gate, SSE bis in den Browser sind providerunabhängig. Ein zweiter echter
Provider ist der ehrlichere Test der Naht als ein zweiter Mock — erst wenn ein
fremdes Modell durch dieselbe Naht passt, ist es wirklich eine.

Was er **nicht** kann: `cache_control` (Anthropic-spezifisch; DashScope cacht
implizit und ohne messbares Signal), `thinking`/`effort`, `is_error` auf
Tool-Ergebnissen. `temperature` ist hier dagegen erlaubt und wird genutzt.
Liefert ein Modell `reasoning_content`, wird es als `reflect`-Event gespiegelt.

**Beide Provider teilen sich denselben Cloud-Graphen.** Die Grenze verläuft
zwischen „im Haus" und „draußen", nicht zwischen zwei Anbietern.

### Memory unterwegs – zwei Embedder, zwei Extraktoren

**Ollama läuft nur daheim.** Ohne Embeddings findet der Graph keine
Entry-Points und ohne Extraktor kommen keine Fakten rein — die Cloud-KI wäre
ausgerechnet unterwegs gedächtnislos, also dort, wo sie gebraucht wird.
Deshalb kann der **Cloud-Graph** über Cloud-Dienste laufen:

| | lokaler Graph | Cloud-Graph |
|---|---|---|
| Embedder | Ollama (`bge-m3`) — **immer** | Cloud (`text-embedding-v3`), sonst Ollama |
| Extraktor | Ollama — **immer** | Ollama; ohne Ollama Cloud-Rückfall |

**Der lokale Graph verlässt das Haus nie** — weder als Embedding- noch als
Extraktions-Auftrag. Ohne Ollama wird er eben nicht verdichtet, Punkt. Der
Rückfall gilt nur für den Cloud-Graphen, dessen Turn ohnehin schon durch die
Cloud gelaufen ist.

> ⚠ **Vektorräume nie mischen.** `bge-m3` und `text-embedding-v3` haben beide
> 1024 Dimensionen und liegen in völlig verschiedenen Räumen. Vergleicht man
> sie, kracht **nichts** — die Suche liefert einfach Rauschen. Deshalb steht
> der Embedder **in der Graph-Datei** (`embedder` / `embed_model`), und **die
> Datei gewinnt gegen die Konfiguration**: was mit bge-m3 gebaut wurde, bleibt
> bge-m3. Auch der Query-Cache hat den Embedder im Schlüssel.

`graph.register_store(pfad, "cloud"|"local")` meldet einen Store an (macht
`cloud.prepare_store()`); die Anmeldung greift nur für **neue** Dateien.

`graph.reembed_missing(store)` zieht Knoten nach, die ohne erreichbaren
Embedder angelegt wurden — die haben gar keinen Vektor und wären für die Suche
**dauerhaft** unsichtbar, weil `ensure_seed` idempotent ist und sie nie wieder
anfasst. Genau das war dem Cloud-Graphen passiert (23 Knoten ohne Vektor).
Idempotent; bei nicht erreichbarem Embedder wird **nichts** geschrieben.

Anthropic hat keine Embeddings-API — dort fällt der Cloud-Graph auf Ollama
zurück und hat unterwegs eben kein Gedächtnis.

### Backend-Wahl

`ai_backends.pick("chat")` entscheidet pro Turn, wer denkt. Reihenfolge aus
`MODULE_BACKENDS["chat"] = (LOCAL, CLOUD)`, **aber** mit ausdrücklicher
Vorwahl `chat_backend()` (`auto` | `local` | `cloud`, in
`data/ai_config.json`, per `ZENTRALE_CHAT_BACKEND` übersteuerbar):

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

### Kassetten-Regel (seit 2026-08-15)

Der Chat ist **nicht mehr kassetten-hart** gegatet. `ai_backends.chat_available()`
ist die eine Frage, die alle Chat-Endpoints stellen:

- Eine ki-freie Kassette (**laptop/tui**) bringt **keine eigene KI** mit →
  `local` bleibt dort aus, auch wenn Ollama erreichbar wäre.
- Eine **Cloud**-KI ist nicht die KI dieser Kassette, sondern eine externe
  Leitung → die darf sie nutzen. Das ist der Unterwegs-Fall: Laptop ohne
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

### Modell-Parameter (Stand 2026-08)

`claude-opus-5` (`ZENTRALE_CLOUD_MODEL`), `effort: medium`
(`ZENTRALE_CLOUD_EFFORT`), `max_tokens 16000` (`ZENTRALE_CLOUD_MAX_TOKENS`),
`thinking: adaptive` mit `display: summarized` → die Denk-Tokens werden live
als `reflect`-Event ins HUD gespiegelt, genau wie Ollamas `thinking`-Feld.

**Fallen der aktuellen API** (gelten auch für `tutor/cloud.py`):
- `temperature` / `top_p` / `top_k` → **400**. Kürze/Reproduzierbarkeit
  kommen nur noch aus dem Prompt.
- `thinking: {budget_tokens: N}` → **400**. Steuerung läuft über `effort`.
- `max_tokens` deckelt **Denken UND Antwort zusammen** — zu knapp heißt, die
  Antwort bricht ab, nachdem das Denken das Budget aufgefressen hat.
- `thinking: disabled` schreibt Tool-Calls gelegentlich als Fließtext statt
  als `tool_use`-Block; der Call läuft dann nie, ohne Fehler. Deshalb bleibt
  Denken überall an, notfalls auf `effort: low`.

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

### Zwei stdout-Channels: Voll-Stream vs. Internet-Monitor

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

**Philosophie-Update 2026-06-07:** Das rechte Panel sollte ursprünglich
**leer** bleiben (Alarm-der-nie-feuern-darf), weil ZENTRALE vollständig
offline war. Seit der Internet-Pipe (`web_suche`/`hole_url`) ist es bewusst
ein **Transparenz-Monitor**: es zeigt **genau, was rein- und rausgeht**.
Jeder gegatete Such-/Lade-Call leuchtet hier auf – das ist jetzt der
erwartete, gewollte Beleg „Paket hat das LAN verlassen", nicht mehr ein
Alarm. (Nicht-gegateter Internet-Traffic hier wäre weiterhin verdächtig.)
Implementation: `core/net.py` (`_is_internet`, plus Spiegel-Calls in
`_log_out/_log_in/_log_err`), `core/state.py` (`_internet_logs`,
`push_internet_log`), `ui/templates/index.html` (`.terminal-row` +
`.terminal-net` mit orangefarbenem Akzent).

Tests: `scripts/test_net_internet.py` (48 Cases, untracked).

## Chat-Modus

- KI-Chat mit qwen3.5:9b (oder via `OLLAMA_MODEL`), tokenweise gestreamt.
- KI hat Zugriff auf Whitelist-Dateien + Graph-Memory.
- Slash-Commands im Chat:
  - `/clear` – Chat-History leeren
  - (`/memory` und `/forget N` sind mit dem Legacy-LTM-Pfad entfallen.)
- ESC – zurück zum Haupt-Dashboard.

## Voice-Pipeline (Core, sprachneutral)

STT und TTS hängen nicht mehr am Tutor, sondern an der Core-AI:

- `POST /api/transcribe` – Audio → Text (Whisper, `lang`-Param)
- `POST /api/speak` – Text → WAV (Piper für `de`, sherpa-onnx für `zh`)

Der Tutor ist ein Konsument dieser Pipeline — die Sprache kommt aus dem aktiven
Sprach-Profil (`stt_lang`/`tts_lang`), `zh` ist nur der heutige Default, kein
Festwert. Details: `audio_system.md` und `api_endpoints.md`.
