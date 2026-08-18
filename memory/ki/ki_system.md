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
- **Embeddings zwei Rollen:**
  1. Fuzzy Entry-Point beim Lesen (Query → nächste Knoten finden).
  2. Ähnlichkeits-Vorschlag beim Schreiben — als **Kante**, nicht als Merge
     (siehe unten).
  3. **Kein** Top-K-Retrieval – das macht Aktivierungs-Spread (`DEFAULT_HOPS=2`,
     `DEFAULT_DECAY=0.5`).
- **Zeit als Knoten:** Tage/Monate/Jahre sind eigene Knoten. Jedes
  erwähnte Konzept kriegt automatisch eine `erwähnt-am`-Kante zum
  heutigen Datum-Knoten. "heute"/"gestern" werden NIE als Knoten
  gespeichert – immer zu ISO-Dates aufgelöst.
- **Datei:** `data/ai_graph.json`.
- **Public API:** `context_for_query(query)`, `add_turn_extraction(nodes, edges)`,
  `ensure_seed()`, `stats()`, `dump()`.

> **⚠ Der Konzept-Graph ist seit 18.08.2026 abgeschaltet.** Er liefert weder
> Kontext in den Prompt (`ai.GRAPH_KONTEXT`) noch nimmt er neue Extraktionen auf
> (`consolidation.GRAPH_EXTRAKTION`) — beides per Env wieder einschaltbar. An
> seiner Stelle steht das Datei-Gedächtnis, siehe
> [gedaechtnis_dateien.md](gedaechtnis_dateien.md). Der folgende Abschnitt
> beschreibt weiterhin korrekt, WIE der Graph arbeitet, wenn man ihn anschaltet.

#### Zeit: der Erzähltag ist nicht der Ereignistag (seit 08/2026)

Am 17.08.2026 fragte Sasha „kann ich heute wieder Sport machen?" und bekam
eine Antwort, in der drei Fehler ineinandergriffen. Der Extraktor stempelte
aus der **Frage** `{Sport ─[geschah-am]─► 2026-08-17}`, der Kalender-Spiegel
machte daraus einen `erlebt`-Eintrag, und der nächste Turn las per
`read_calendar` genau diesen Eintrag als **Beleg** zurück. Eine Frage war
binnen einer Minute Kalender-Wahrheit. Dasselbe Muster hatte vorher schon
„ich hatte vor ein paar Tagen Schüttelfrost" auf den Tag des Erzählens
datiert — woraus die KI dann „du hattest bis gestern Fieber" ableitete.

Drei Stellen tragen die Regel jetzt:

- **Extraktor-Prompt, Regel 5** (`core/consolidation.py`): `geschah-am` nur
  mit einem Datum, das im Turn wirklich steht. Ungefähre Vergangenheit
  („vor ein paar Tagen") wird **gröber, nicht falsch** — Monats-Knoten
  (`2026-08`) statt eines erfundenen Tages; das heutige Datum wäre dort die
  schlechteste Wahl. **Gegenwart ist davon nicht betroffen:** „ich hab grad
  Fieber" heißt heute und wird ganz normal auf den Tag datiert. Fragen,
  Vorhaben, Hypothetisches und Verneintes sind **keine** Ereignisse.
  `erwähnt-am` ist das Gegenstück und datiert das Reden.
- **Zeit in vier Auflösungen** (`graph._zeit_typ`): `2026` / `2026-W34` /
  `2026-08` / `2026-08-17` werden am Namen erkannt und als `time-year` /
  `time-week` / `time-month` / `time-day` getypt — egal was der Extraktor
  geraten hat. Vorher stand „2026-08-10" als `event` und „2026-08-09" als
  `concept` im Graphen, und die Filter, die Zeit-Knoten aussortieren, griffen
  nicht.
- **Die Woche ist die wichtigste grobe Stufe.** „vor ein paar Tagen" ist
  wochengenau bekannt; es auf den ganzen Monat zu werfen verschenkt drei
  Wochen Genauigkeit, die man ehrlich hat. Damit das Modell keine ISO-Wochen
  rechnen muss (dieselbe Arithmetik, die beim Wochentag reihenweise
  schiefging), bekommt es beides fertig geliefert: der Extraktor-Body nennt
  die laufende und die vorige Kalenderwoche (`consolidation._wochen_anker`),
  und der Kontext-Renderer schreibt jeden Wochen-Knoten mit seiner Spanne aus
  („2026-W34 [time-week] (17.08.–23.08.2026)").
- **Kontext-Legende** (`graph.context_for_query`): steht eine Datums-Kante im
  Block, erklärt eine Zeile, dass `geschah-am` **genau einen Tag** meint und
  keinen Zeitraum. Ein Zustand hängt an seinem Datum und sagt nichts über
  andere Tage — Sashas Modell, ausdrücklich so gewollt.
- **Kalender-Spiegel gelöscht** — er war ein Schreibweg am Erlaubnis-Gate
  vorbei, in einen Layer, den nur die KI lesen konnte. An seiner Stelle steht
  `kalender.imprint_for_prompt()`: der nahe Horizont (heute/morgen) wird
  **gelesen** statt geschrieben und hängt im wechselnden Prompt-Teil.
  Beides in `memory/werkzeuge/kalender_system.md`.

#### Wovon der Kontext ausgeht: wörtliche Treffer + gedämpfte Anker

Einstiegspunkte waren Embedding-Treffer plus `Sasha` plus heutiges Datum.
Am 17.08. hatten nur 29 von 59 Cloud-Knoten einen Vektor — **nicht** wegen
Ollama, sondern weil **Anthropic keine Embeddings-API hat**: chattet der Kern
auf Claude, liefert `embeddings._cloud_provider()` nichts, und jeder in der
Sitzung entstandene Knoten bleibt vektorlos (`graph.reembed_missing` zieht sie
beim nächsten Start nach — aber nur, wenn dann ein Embedder da ist). Blieben
die zwei größten **Naben** — an `Sasha` hängt alles, an `heute` jedes
`erwähnt-am`. Ergebnis: auf die Frage nach Sport kamen Geige, Spanien und
brain organoids zurück, alle gleichauf, während „Sport" selbst nur über zwei
Ecken mitschwamm.

**Seit 17.08.2026 ist das strukturell gelöst:** `embeddings._cloud_provider()`
nimmt den erstbesten Anbieter, der einen `/v1/embeddings`-Endpoint hat und
dessen Key dasteht — unabhängig davon, wer gerade chattet. Wer redet und wer
sich erinnert, sind zwei Rollen. Bevorzugt wird trotzdem der Chat-Anbieter
(schmalere Datenspur); läuft der Chat auf Claude, embeddet DashScope
(`text-embedding-v3`). `ZENTRALE_CLOUD_EMBED_PROVIDER` übersteuert hart.

`graph.reembed_missing()` füllt beim nächsten Start die Knoten mit
`embedding: null` nach — es rechnet nur die fehlenden Vektoren aus, es erfindet
oder holt keine Inhalte.

- `graph._lexical_entry_points()`: Knoten, deren Name **wörtlich** in der
  Frage vorkommt. Stumpf, aber unabhängig von Ollama. Mehrwortige Knoten
  brauchen alle ihre Wörter; ab 5 Zeichen zählt ein Präfix, damit „krank"
  den Knoten „Krankheit" findet.
- **Anker gedämpft:** `Sasha` und das heutige Datum starten bei
  `graph.ANKER_START` (0.35) statt 1.0, **sobald die Frage eigene
  Einstiegspunkte hatte**. Ohne Treffer tragen sie den Kontext weiterhin
  allein und behalten volle Kraft.
- **Kanten nach Relevanz** statt Datei-Reihenfolge: Rang = Aktivierung des
  schwächeren Endknotens, `erwähnt-am` mit Faktor 0.3 nach hinten. Sonst
  entschied der Zufall der Entstehung, was den 40er-Schnitt und das
  Zeichenbudget überlebt.

#### Alias-Auflösung: verbinden statt verschmelzen (seit 08/2026)

`_find_alias()` macht nur noch die drei **String**-Stufen — exakt,
Groß-/Kleinschreibung, leichtes Stemming (`Hund` == `Hunde`). Das sind
Schreibweisen desselben Wortes, keine Vermutung.

Die vierte Stufe (Embedding-Cosinus ≥ `ALIAS_THRESHOLD=0.78` plus
`ALIAS_TOKEN_BONUS=0.15`) hat früher **automatisch verschmolzen**. Das war die
einzige Operation im ganzen Graphen, die Information vernichtet: nach dem Merge
gibt es keinen zweiten Knoten mehr, den man auseinandernehmen könnte — und ein
Fehlmerge ist völlig still. Keine Meldung, kein Log. „Pi" und „Pizza" standen
nicht umsonst als Warnung im alten Kommentar. Ein Fehler, der still ist UND
nicht reparierbar ist, ist der teuerste, den man bauen kann.

Jetzt schlägt dieselbe Rechnung (`_naechster_verwandter()`) eine **Kante** vor:
der neue Knoten wird angelegt und bekommt `alias-von` zum ähnlichsten
Bestehenden, Gewicht 0.5. Der Aktivierungs-Spread erreicht den Nachbarn
darüber genauso — nur ohne Datenverlust, sichtbar im Kontext-Block, und
falls die Vermutung daneben lag, löscht man eine Kante statt einen Knoten zu
vermissen, von dem man nicht mehr weiß, dass es ihn je gab.

Zeit-Knoten bekommen keine `alias-von`-Kanten (kein Embedding, keine Synonyme).

⚠ **Was vor 08/2026 verschmolzen wurde, ist verschmolzen.** Die Umstellung
wirkt nur nach vorne; alte Fehlmerges lassen sich nicht rekonstruieren.

#### Transkript-Schicht (`core/transkript.py`)

Der Graph merkt sich, **DASS** eine Beziehung besteht, nicht **WAS** gesagt
wurde. `Sasha ─[besitzt]─► Falter` — dass es ein blaues Klapprad ist und woher
der Name kommt, hat der Extraktor beim Destillieren weggeworfen.

Deshalb liegt das Rohmaterial daneben: append-only
`data/ai_transcripts/YYYY-MM.jsonl` (Cloud-Graph: `cloud-YYYY-MM.jsonl`,
getrennt, damit nicht verwischt, welcher Turn zu welchem Gedächtnis gehört).
Eine Zeile pro Turn:

```json
{"id": "2026-08:10", "zeit": "2026-08-16T15:19:06", "user": "…", "ai": "…"}
```

Die id ist Monat + Zeilennummer — ohne Index und ohne Zufallszahl auffindbar.
Jeder berührte Knoten trägt sie in `quellen` (max. `MAX_QUELLEN=20`, ohne
Dubletten).

**Das ist ausdrücklich kein zweiter Suchindex.** Hier wird nie gesucht, nie
embedded, nie etwas in den Prompt geladen. Würde die Datei durchsucht, hätte
ZENTRALE zwei konkurrierende Gedächtnisse mit unterschiedlichen Antworten —
genau das soll der Graph verhindern. Sie ist ein Archiv, auf das der Graph
zeigt.

Gitignored (`data/ai_transcripts/` — `.jsonl` fällt nicht unter `data/*.json`):
noch persönlicher als der Graph, weil roh.

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

Der Kern spricht **ein** Vokabular (englisch, Spalte „kanonisch"). Wie eine
Schiene ihr Tool nennt, ist ihre Sache — `profil.kanonisch()` übersetzt darauf
und nimmt beide Schreibweisen an (siehe „Zwei Schienen" weiter unten).

| kanonisch | in `klein` | Funktion |
|---|---|---|
| `read_file`   | =            | Datei aus der Whitelist lesen |
| `list_files`  | =            | Verfügbare lesbare Dateien auflisten |
| `read_calendar` / `add_calendar_*` / `delete_calendar_entry` | = | Kalender lesen/schreiben/löschen (s. `memory/werkzeuge/kalender_system.md`) |
| `web_search`  | `web_suche`  | Im Internet suchen (gegatet, s. „Internet-Pipe") |
| `fetch_url`   | `hole_url`   | Webseite laden + Text holen (gegatet) |
| `read_news`   | `lies_news`  | Weltpolitik-Briefing lesen (s. `memory/werkzeuge/news_system.md`) |
| `read_mail`   | `lies_mail`  | Stand der Mail-Triage (s. `memory/werkzeuge/mail_system.md`) |
| `ask_choice`  | `frage_knopf`| Sasha eine Frage mit Knöpfen stellen (s. unten) |
| `antwort`     | nur `klein`  | Finale Antwort über den Tool-Kanal (Framing-Effekt, 9B-Krücke) |

Gegen das Erlaubnis-Gate wird **nie** direkt geprüft, sondern über
`ai.braucht_erlaubnis()` — die normalisiert erst. Ein Schreib-Tool, das unter
seinem Alias am Gate vorbeirutscht, würde ungefragt in den Kalender schreiben,
und der Fehler wäre völlig lautlos.

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
  siehe „ASCII-Kern / Bild-Marker" in [memory/system/dashboard.md](memory/system/dashboard.md).
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
`add_calendar_entry`, `add_calendar_routine`, `edit_calendar_routine`,
`add_calendar_pause`, `delete_calendar_entry` **plus** die Internet-Pipe `web_suche`, `hole_url`) fängt das Backend **vor der
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
[memory/system/dashboard.md](memory/system/dashboard.md). Tutor-Modus: beides aus (fremdes Tool-Set). Neues
Tool gaten = Name in `PERMISSION_REQUIRED_TOOLS` + ggf. Vorlage in
`_permission_question`.

`save_memory` ist mit dem Legacy-Pfad rausgeflogen – der Graph-Extraktor
läuft eh nach jedem Turn automatisch. Kalender-Tools (`read_calendar`,
`add_entry`, `add_routine`) kommen mit dem Kalender-System (siehe
[memory/werkzeuge/kalender_system.md](memory/werkzeuge/kalender_system.md)).

**Sicherheitsnetz:** `chat_stream` hat ein hartes `max_rounds = 5` für
die Tool-Loop – verhindert Endlosschleifen bei kaputten Tool-Calls.

**Streaming-Detail:** Tool-Calls kommen im **letzten** Streaming-Chunk
(`done=true`) im Feld `tool_calls`. Heißt: erst auf das Ende des Streams
warten, dann Tools auflösen.

## Wie ihre Antwort im Terminal ankommt

Die KI schreibt Markdown — der Prompt erlaubt ihr Listen ausdrücklich,
Überschriften benutzt sie von selbst. Gezeichnet wurde bis 18.08.2026 der
**Rohtext**: im KI-Kasten stand `**fett**` und `## Titel` als Zeichen.

`tui/zentrale_tui.py::md_zeilen(text, breite)` liefert
`[(zeile, stil)]` mit `stil` aus `{"", "kopf", "code", "liste"}`. Der Stil
ist absichtlich ein **Wort** und keine curses-Konstante: so bleibt die
Funktion rein und ohne Terminal testbar, und über Farben entscheidet allein
der Zeichner (`draw_ai`). Sie liegt auf Modulebene und fällt damit unter
dieselbe „darf NIE werfen"-Eigenschaft wie die übrigen TUI-Helfer.

- Umgesetzt: Überschriften, Aufzählungen (mit **hängendem Einzug** — eine
  umgebrochene Zeile rückt unter den Text, nicht unter das Bullet),
  verschachtelte Listen, Code-Zäune (**nicht** umgebrochen: ein
  umgebrochener Befehl ist ein falscher Befehl), inline `**fett**`,
  `*kursiv*`, `` `code` ``, `[Text](URL)`.
- **Nicht** umgesetzt: Auszeichnung *innerhalb* einer Zeile. Dafür müsste
  eine Zeile in Segmente mit eigenen Attributen zerfallen — quer durch
  `addclip` und jeden Aufrufer. Die Marker werden entfernt, der Text bleibt.
- **Die harte Regel, mit eigenem Test:** es geht nie Inhalt verloren.
  Entfernt werden nur sauber gepaarte Marker; `2 ** 3 = 8`, `snake_case`
  und ein offenes `**` bleiben stehen, bei einem Link bleibt die URL
  erhalten. Ein Renderer, der bei kaputtem Markdown Text verschluckt, ist
  schlimmer als gar keiner — man merkt es nicht.
- Sashas eigene Eingaben laufen **nicht** durch den Renderer: was er tippt,
  soll dastehen, wie er es getippt hat.

Das Browser-Dashboard rendert weiterhin nichts; dort ist gar kein
Markdown-Renderer eingebunden.

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
> Aktionen, nicht den Abfluss lesender. Bewusst so, siehe `memory/betrieb/sicherheit.md`.

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
Die **Bedeutung** eines Tool-Calls — was terminal ist (`read_news`, in `klein`
zusätzlich `antwort`), was durchs Gate muss — steht genau einmal, in
`cloud.run_tool()`; die beiden Loops unterscheiden sich nur darin, wie sie das
Ergebnis verpacken (`tool_result`-Block vs. `role: "tool"`-Message). Auch der
statische System-Prompt kommt aus derselben Funktion
(`cloud._static_system()`), die ihn bei der aktiven Schiene holt.

### Prompt-Cache: statisch vorn, Wechselndes ganz hinten

Anthropic rendert `tools → system → messages` und cacht alles VOR einem
`cache_control`-Breakpoint. Ein Treffer kostet 10 % des Input-Preises.

Bis 08/2026 saß der Graph-Kontext samt Uhrzeit im `system`-Feld, also **vor**
dem gesamten Verlauf. Die Uhr ist jeden Turn eine andere — damit war alles
dahinter mit-invalidiert und der komplette Verlauf ging bei jedem Turn
ungecacht raus. Gemessen: `in=7236 cache_read=0` für eine Drei-Wort-Antwort.

Jetzt:

* `cloud._static_system()` → nur Byte-identisches, ins `system`-Feld, mit
  Breakpoint (`ttl: 1h`, per `ZENTRALE_CACHE_TTL` zurückstellbar).
* `cloud._volatile_text()` → Graph, Jetzt-Block, Imprint (heute/morgen),
  Alarme, Mic-Hinweis. Hängt als
  **letzter Block der neuesten User-Nachricht**, also hinter allem Cachebaren.
  Bewusst nicht als `{"role":"system"}`-Nachricht: das können nur Opus 5/4.8,
  Sonnet 5 quittiert es mit 400.
* Breakpoint Nr. 2 sitzt auf dem User-Text, **vor** dem Wechselnden. Dahinter
  wäre er wertlos — jeder Turn schriebe eine Cache-Zeile, die nie gelesen wird.
* Breakpoint Nr. 3 wandert zwischen den Tool-Runden mit (max. 4 erlaubt).
* `_prepare_messages` normalisiert jeden Text auf Block-Listen-Form; sonst wäre
  der Präfix nicht verlässlich derselbe.

Gemessen nach dem Umbau (Sonnet 5, drei Turns):

```
Turn 1  in=250  cache_read=0     cache_write=5459  ≈3,09 ct
Turn 2  in=250  cache_read=5459  cache_write=20    ≈0,24 ct
Turn 3  in=250  cache_read=5479  cache_write=20    ≈0,25 ct
```

Der Präfix wird einmal geschrieben, danach gelesen; geschrieben wird pro Turn
nur noch das Delta. Die 250 ungecachten Token sind das Wechselnde.

Deckel gegen Aufblähen: `ZENTRALE_CLOUD_CTX_CHARS` (Graph-Kontext, Default
2.500) und `ZENTRALE_CLOUD_MSG_CHARS` (eine einzelne Verlauf-Nachricht,
Default 4.000 — `cloud.kappen()` kürzt in der Mitte, deterministisch, damit
der Präfix byte-stabil bleibt). Das Nachrichten-FENSTER wird bewusst nicht
beschnitten: vorne etwas wegzuwerfen verschiebt den Präfix-Anfang und wirft
genau diesen Cache weg.

### Zwei Schienen: `core/profil/`

Ein 9B-Ollama-Modell und ein Frontier-Modell teilten sich bis 08/2026 EINEN
System-Prompt und EIN Tool-Set. Jede Anpassung für das eine war Ballast oder
Gift für das andere — und jeder Ballast geht bei JEDEM Turn und JEDER
Tool-Runde mit raus.

Der Zug bleibt einer (Tool-Ausführung, Kalender, Graph, Gate, Event-Protokoll,
Loop). Die Schiene — Prompt-Texte, Tool-Set, Beschreibungen, Namen — bekommt
jedes Modell für sich:

| Datei | Für wen |
|---|---|
| `profil/klein.py` | qwen3.5:9b und Verwandte. Wörtlich aus `ai.py` umgezogen, unverändert. |
| `profil/gross.py` | Frontier-Modelle. Der zusammengestrichene Prompt. |
| `profil/__init__.py` | Registry, Auswahl, Alias-Tabelle |

* **Auswahl:** lokal → `klein`, cloud → `gross`. Übersteuerbar per
  `ZENTRALE_PROMPT_PROFIL` oder `chat_profil` in `data/ai_config.json`.
  Zurücktauschen ist eine Zeile — das ist der Sinn der Sache.
* **`klein` ist Kanon.** `ai.py` re-exportiert die Namen (`ai._SYSTEM_PROMPT`,
  `ai.TOOLS` …), deshalb laufen der lokale Pfad, die vier `scripts/bench_*.py`
  und alle alten Tests unverändert. Wer dort aufräumen will, macht das erst,
  wenn er es gegen ein echtes qwen nachmessen kann.
* **Die Persona wird nicht kopiert**, sondern in `gross` aus `klein` abgeleitet
  (`_ohne()` nimmt zwei Abschnitte heraus und wirft, wenn sie nicht genau
  einmal da sind). Zwei Kopien wären zwei Persönlichkeiten, je nachdem welches
  Backend gerade läuft.
* **Parameter-Schemata werden übernommen, nie neu getippt.** Sie sind der
  Vertrag mit Python (`kalender.RANGE_BUCKETS` & Co.); dort auseinanderzulaufen
  wäre ein Bug, kein Feintuning. Getrennt wird nur, was *Anrede* ist.

Was `gross` nicht mitschleppt: das `antwort`-Tool samt `ANTWORT_SUFFIX`, die
Bild-Marker, die Dashboard-Sicht, den `## Text-Effekte`-Block (die TUI rendert
das Markup nicht), das Turn-Ende-Few-Shot, die Anti-Konfabulations-Belehrungen
und die ausbuchstabierte ⚠-Choreografie. Was bleibt, ist Inhalt statt
Modellgröße — vor allem die **Subjekt-Grenze**.

Ergebnis: Präfix **4.630 → 2.587 Token** (−45 %). Untergrenze beachten:
Anthropic cacht erst ab 1.024 Token (Sonnet 5) bzw. 512 (Opus 5) — wer weiter
eindampft, spart Zeichen und verliert den Cache, also unterm Strich teurer.
Ein Test hält das fest.

#### Den Prompt einer Schiene ansehen — `scripts/prompt_zeigen.py`

Weil `gross` die Persona **ableitet**, gibt es von ihm bewusst keine Abschrift
in `prompts/` — eine dritte Fassung würde still wegdriften. Das Skript baut
den Prompt stattdessen aus dem Live-Code:

```
scripts/prompt_zeigen.py                 # der Cloud-Prompt, wie er rausgeht
scripts/prompt_zeigen.py --tools         # dazu das Tool-Schema
scripts/prompt_zeigen.py --diff          # was gross gegenüber klein weglässt
scripts/prompt_zeigen.py --woher         # welchen Regler dreh ich in welcher Datei?
scripts/prompt_zeigen.py --schiene klein # die lokale Fassung
```

`--woher` ist der Griff, den man beim Ändern braucht: die **Persona ist
geteilt** (ein Schnitt in `klein._SYSTEM_PROMPT` trifft beide Schienen), die
**Meta-Regeln sind es nicht** (`gross._CAPABILITIES_PROMPT` ist eigener Text).
Wer das verwechselt, ändert den lokalen Prompt mit, ohne es zu merken.

Unterschied zu `scripts/ai_devtools.py`: das Devtools-Terminal zeigt einen
**echten Turn** samt Graph-Kontext, Verlauf und Cache-Breakpoints, braucht aber
ein laufendes Gespräch. `prompt_zeigen.py` zeigt den **statischen Teil** allein,
jederzeit und ohne Backend.

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

## Devtools-Terminal — `scripts/ai_devtools.py` (seit 08/2026)

Das Dashboard-Log sagt, WAS gekostet hat und DASS ein Tool lief. Was
tatsächlich rausgeht — der vollständige System-Prompt, der Graph-Kontext, das
Tool-Schema, die Reihenfolge der Blöcke, wo die Cache-Breakpoints sitzen —
sah man nirgends. Seit es zwei Prompt-Schienen gibt, ist genau das die Frage,
die man ständig hat.

In einem eigenen Terminal, aus dem Projekt-Root:

```
scripts/ai_devtools.py                    # localhost:5000
scripts/ai_devtools.py --url http://<pc>:5000
scripts/ai_devtools.py --voll             # nichts kürzen
```

Ausgabe pro Turn:

```
→ REQUEST claude-sonnet-5 | Schiene: gross
System-Prompt (1 Block, 2959 Zeichen ≈ 739 Token)
  [0] ◄ CACHE-BREAKPOINT
Messages (1)
  user:
    ◄ CACHE-BREAKPOINT
    was steht heute an?
    ## Aktiviertes Wissen …          ← das Wechselnde, ungecacht dahinter
Tools (20, 5217 Zeichen ≈ 1304 Token)  [339a3b98f42f]
  read_calendar
      Liest Kalender-Einträge: TERMINE und Routinen, also Verabredetes. …
      *zeitraum (string) heute | diese_woche | …
  …
← ANTWORT tool_use in=677 out=54 cache_read=5458
⚙ TOOL read_calendar
⊕ GRAPH (cloud) knoten: Falter, blau, Klapprad
```

**Werkzeuge stehen mit Beschreibung und Parametern da — seit 18.08.2026.**
Vorher schickte `kidebug.request()` nur die NAMEN; damit log das Terminal seinen
eigenen Anspruch, alles zu zeigen, was rausgeht. Ausgerechnet die
Beschreibungen sind das, woraus die KI ableitet, wann sie welches Werkzeug
nimmt — wer verstehen will, warum sie danebengreift, muss genau die lesen. Sie
sind außerdem ein spürbarer Teil des gecachten Präfix.

Ausgeschrieben werden sie nur beim **ersten** Request und danach wieder, wenn
sich der Satz ändert; sonst steht `[Schemata wie oben, <fingerprint>]`. Der
Satz ist statisch, und ihn 500-mal in einen Puffer von 500 Events zu legen
hieße, alles andere daraus zu verdrängen. Beim Verbinden vergisst der Bus, was
er schon gezeigt hat (`subscribe()` setzt `_TOOLS_FP` zurück) — sonst hätte
ausgerechnet eine frisch geöffnete Sitzung die Schemata nie gesehen.

Events: `ai.req` (voller Request), `ai.out` (Roh-Antwort inkl. Denk-Blöcken und
dem Vorgeplänkel vor einem Tool-Call, das der Chat sonst schluckt), `ai.tool`,
`ai.graph` (was der Extraktor geschrieben hat).

- **Bus:** `core/kidebug.py`, Ring-Puffer + Subscriber-Queues, `emit()` schluckt
  jeden Fehler — ein Debug-Kanal, der ein Gespräch abreißen lässt, ist
  schlimmer als keiner.
- **Normalerweise AUS** (`ZENTRALE_AI_DEBUG=0`). Das Terminal schaltet ihn beim
  Verbinden selbst an; den vollen Prompt im Speicher zu halten lohnt nur, wenn
  jemand zuschaut.
- **Endpunkt:** `GET /api/ai/debug/stream` (SSE).
- **Eigener Bus, nicht der des Tutors.** `tutor/debug.py` bleibt getrennt: der
  Tutor ist ein Addon und muss am Stück rausziehbar bleiben, der Kern darf
  nicht aus `tutor/` importieren. Dieselbe Entscheidung wie `providers.py` vs.
  `tutor_providers.py`.

⚠ Hier geht der komplette Prompt raus, inklusive Graph-Kontext — also Sashas
Zustände und Erlebnisse. So privat wie der Graph selbst.

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
Festwert. Details: `memory/ki/audio_system.md` und `memory/system/api_endpoints.md`.
