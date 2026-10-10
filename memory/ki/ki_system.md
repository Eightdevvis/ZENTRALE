# KI-System

**Stand 2026-10-04:** Front ist die TUI (`tui/zentrale_tui.py`, Thin Client
über `/api/chat` als SSE). Der Kern-Chat denkt über `ai_backends.pick("chat")` —
Vorwahl `chat_backend` in `data/ai_config.json` (`auto|local|cloud`; seit
2026-08-15 bewusst **`cloud`**, daheim wie unterwegs). Cloud = `core/cloud.py`
(Anthropic, Drop-in für `ai.chat_stream()`, Code-Default `claude-sonnet-5`,
adaptives Denken, Prompt-Cache statisch vorn) oder `core/cloud_openai.py`
(zweiter Dialekt für qwen/openai/mistral); lokal = Ollama `qwen3.5:9b`
(`think=false`, Prompt-Schiene `profil/klein`, Cloud nimmt `profil/gross`;
qwen über die Cloud bekommt darüber sein Modell-Profil `profil/modelle/qwen`,
Einstellung `modell_profile` → [modell_profile.md](modell_profile.md)).
**Tools laufen immer lokal**, nur die Entscheidung wandert. Schreib-Tools
gehen durchs Erlaubnis-Gate (Regel im Werkzeug-Register, nicht
modellgetrieben). **Das Gedächtnis ist das Datei-Gedächtnis**
(`gedaechtnis_dateien.md`); der Konzept-Graph ist seit 2026-08-18
abgeschaltet (`ZENTRALE_GRAPH_KONTEXT`/`_EXTRAKTION` holen ihn zurück), sein
Abschnitt unten beschreibt, wie er arbeitet, wenn er an ist. Der Chat ist
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
`claude-haiku-4-5` (`cheap_model`) nutzt nur der Cloud-Graph-Extraktor, der
mit dem Graphen aus ist.

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
           ─▶ consolidation.py     (nach dem Turn: Transkript; Graph-Extraktion aus)
           ─▶ graph.py             (nur Identity-Seed; Kontext aus, GRAPH_KONTEXT)
```

`ai.py` ist der einzige Ollama-Client für Chat-Calls. `embeddings.py` und
`consolidation.py` reden ebenfalls direkt mit Ollama (Embeddings bzw.
Extraktor-LLM), aber alle gehen durch `core/net.py` – damit landet jeder
Request im Terminal (siehe Network-Transparenz unten).

**Lokales Modell qwen3.5:9b — warum (2026-06-06, vorher qwen2.5:14b):** Reasoning-Bench (`scripts/bench_reasoning.py`)
zeigte es gleichstark zu qwen3:14b (10/11 ohne Thinking), aber schneller
(68 vs 47 tok/s) und kleiner (8.8 statt 11 GB VRAM → ~3 GB frei für
Browser/Desktop, behebt die VRAM-Contention-Crashes). Tool-Calling 100%,
kein Leak (`scripts/bench_models.py`). **Wichtig:** qwen3/qwen3.5 denken
per Default vor jeder Antwort (30–80 s Latenz!) → `ai.py` und
`consolidation.py` schicken `think=false` (nur für qwen3*, siehe
`_think_opts` / `SUPPORTS_THINK`). Per Env `OLLAMA_MODEL` umstellbar
(Fallback qwen3:14b / qwen2.5:14b).

## Memory-Architektur (Phase G – Konzept-Graph, abgeschaltet)

Bis 2026-08-18 war der **Graph primary** und einzige Memory-Schicht: was die
KI bei jedem Turn „sah", kam komplett aus dem Graphen (plus
`_now_prompt`-Zeitstempel, plus Kalender-Layer). Heute: `gedaechtnis_dateien.md`.

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

**Das ist kein zweiter Suchindex:** nie embedded, nie etwas in den Prompt
geladen. Sie ist ein Archiv, auf das der Graph zeigt. Seit 2026-10-07 liest
sie das Werkzeug `search_chats` mit (Abschnitt „Frühere Gespräche" unten) —
als Verlauf von vor den Gesprächen, wörtlich und mit Datum, nicht als
Gedächtnis, das etwas behauptet.

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

Trigger: nach jedem vollständigen Chat-Turn (`consolidation.zug_vormerken`,
bis 2026-10-06 `ai._async_save_turn`). Das alte STM/LTM-Konsolidierungs-Pattern (Trigger `/sleep` oder
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
| `read_file`   | =            | `klein`: Datei aus der Whitelist bzw. ~/codicus lesen. `gross` (seit 2026-10-09): NUR Input/ und Output/ des Nutzerordners (s. „Reichweite von gross") |
| `read_series` | nur `gross`  | Messreihen lesen (Liste mit letztem Wert, oder Werte einer Reihe, Standard letzte 30 Tage) — ersetzt `read_file` auf `data/<reihe>.json` |
| `list_files`  | =            | `klein`: Gesamtliste der lesbaren Dateien (höchstens 300, wie bisher). `gross` (seit 2026-10-09): EINEN Ordner im Nutzerordner wie ls, `ordner` = Input (Standard) / Output / Unterordner |
| `find_files`  | nur `gross`  | Dateien/Ordner nach Namen in Input/ und Output/ suchen, wie find (`*.zip`, `*chefkoch*`, Namensteil) — mit Vollständigkeits-Angabe (s. „Nutzerordner, Suchen, Claude-Skills übernehmen") |
| `search_files` | nur `gross` | Text in Dateien in Input/ und Output/ suchen, wie grep — `pfad:zeile: auszug`, mit Vollständigkeits-Angabe |
| `import_skill` | nur `gross` | Claude-Skill(s) aus .zip oder Ordner in Input/ übernehmen, gegatet |
| `unzip` | nur `gross` | Eine .zip aus Input/ nach Output/<name>/ auspacken (gegatet), `ansehen=true` zeigt nur den Inhalt (frei) |
| `remove_input` | nur `gross` | Datei/Ordner direkt aus Input/ in `.Papierkorb/<Datum>/` legen (gegatet, löscht nie) |
| `read_calendar` / `add_calendar_*` / `edit_calendar_routine` / `delete_calendar_entry` | = | Kalender lesen/schreiben/löschen (s. `memory/werkzeuge/kalender_system.md`); auf `gross` mit Kennungen, Ende/Ort, `nur_am` und Pflicht-Zeitraum `von`/`bis` bei Routinen (s. „Kalender ohne Fallen") |
| `edit_calendar_entry` | nur `gross` | Einen Einzeltermin ändern, nur genannte Felder (gegatet) |
| `read_calendar_warnings` | nur `gross` | Die Kalender-Warnungen frisch, dieselben wie Sashas ⚠ |
| `web_search`  | `web_suche`  | Im Internet suchen (gegatet, s. „Internet-Pipe") |
| `fetch_url`   | `hole_url`   | Webseite laden + Text holen (gegatet) |
| `read_news`   | `lies_news`  | Weltpolitik-Briefing lesen (s. `memory/werkzeuge/news_system.md`) |
| `read_mail`   | `lies_mail`  | Stand der Mail-Triage (s. `memory/werkzeuge/mail_system.md`) |
| `ask_choice`  | `frage_knopf`| Sasha eine Frage mit Knöpfen stellen (s. unten) |
| `antwort`     | = | Finale Antwort über den Tool-Kanal — auf `klein` Framing-Effekt (9B-Krücke), auf `gross` seit 2026-10-10 mit **Selbstauskunft** (`erledigt`, `fragt_erlaubnis`, `schiebt_auf`, `ungeprueft`; s. [ehrlichkeit_live.md](ehrlichkeit_live.md)) |
| `run_code`    | nur `gross`  | Python/Shell abgeschottet ausführen, jeder Lauf gegatet (s. „Sandbox") |
| `load_skill` / `propose_skill` / `edit_skill` | nur `gross` | Skill-Anleitung (oder mit `datei` eine Datei daraus) holen; neuen vorschlagen bzw. bestehenden umschreiben (beide gegatet) (s. „Skills") |
| `search_chats` / `read_chat` | nur `gross` | Frühere Gespräche durchsuchen/nachlesen; `search_chats` mit `projekt` nur in einem Projekt (s. „Frühere Gespräche") |
| `read_project_file` | nur `gross` | Wissensdatei des Projekts dieses Gesprächs lesen (s. „Projekte") |
| `browser_open` / `browser_click` / `browser_type` / `browser_find` / `browser_read` / `browser_back` / `browser_close` / `browser_screenshot` | nur `gross` | Echter Browser ohne Fenster, über Text bedient; gefragt einmal je Host und Gespräch (s. „Browser") |

Gegen das Erlaubnis-Gate wird **nie** direkt geprüft, sondern über
`erlaubnis.braucht_erlaubnis()` — die normalisiert erst. Ein Schreib-Tool, das unter
seinem Alias am Gate vorbeirutscht, würde ungefragt in den Kalender schreiben,
und der Fehler wäre völlig lautlos.

Tool-Calls werden streng ans Dashboard-Terminal geloggt
(`AI → TOOL read_file(...)` / `AI ← TOOL read_file → ok`). Sichtbar
machen ob die KI ein Tool wirklich gerufen hat oder es nur behauptet.

### Das Werkzeug-Register — `core/werkzeug_register.py` (seit 2026-10-07)

Ein Eintrag pro Werkzeug: kanonischer Name, Parameter-Schema (für beide
Schienen gleich), Beschreibung je Schiene (`klein`/`gross`, `None` = dort
nicht angeboten), alter `klein_name`, Erlaubnis-Regel (`False`/`True`/
`f(args)`) mit Frage-Text, `terminal`. Die Reihenfolge der Einträge ist die
Reihenfolge im Prompt. `profil/klein.py`, `profil/gross.py` (`TOOLS`,
`TERMINAL`), `profil.ALIASE`/`kanonisch`, `erlaubnis` und
`ki_werkzeuge._verteilen` holen sich alles von dort. Die Ausführer melden
sich aus `ki_werkzeuge.py` mit `@ausfuehrer("name")` an — so herum, weil
`ki_werkzeuge` im Register nachschlägt und ein Import in die andere Richtung
ein Kreis wäre.

**Ein neues Werkzeug anlegen:**
1. Eintrag in `WERKZEUGE` in `core/werkzeug_register.py`, **hinten** an
   (Umsortieren bricht den Anthropic-Cache). Neue Werkzeuge nur mit
   `gross=` — `klein=None`, das qwen bekommt nur Gemessenes.
2. Schreibt, löscht, geht ins Netz oder kostet Geld → `erlaubnis=True` (oder
   eine Funktion der Argumente) **und** eine eigene `frage=`.
3. Die Funktion in `core/ki_werkzeuge.py` mit `@ausfuehrer("name")`.
   Verändert sie Sashas Daten: `schreibt=True` und `beweis=` (was danach
   nachgelesen wird), und die Funktion gibt einen `werkzeug_befund.Befund`
   mit `beleg` zurück (s. „Belegt oder gesagt"). `tests/test_werkzeug_belege.py`
   führt jedes schreibende Werkzeug einmal echt aus — ein neues muss dort in
   `AUFRUFE`.
4. Schnappschuss neu ziehen (`venv/bin/python tests/test_werkzeug_schnappschuss.py --neu`)
   und den Diff ansehen: nur das neue Werkzeug darf dazukommen.
   `tests/test_werkzeug_register.py` meldet Waisen in beide Richtungen.

### Belegt oder gesagt — Status und Belege (seit 2026-10-08)

Anlass: Sashas Kalender-Testlauf am 08.10. (Gespräch `20261008-132404`). Die
KI meldete „Geige donnerstags 18:10–19:00" als erledigt — gespeichert war
18:10 ohne Ende, das Werkzeug hatte nur „OK, Routine eingetragen" gesagt. Sie
gab ein Ferienende aus dem Vorwissen als Suchergebnis aus, sagte „ohne Login
komm ich nicht tiefer" (geraten) und „die Warnungen sollten verschwinden"
(nie geprüft). Ehrlichkeit war eine Bitte im Prompt; jetzt ist sie Bauweise:

- **Kopfzeile.** Jedes Werkzeug-Ergebnis an die KI beginnt mit
  `[ergebnis: ok|fehlgeschlagen|keine_antwort|abgelehnt]`, gesetzt
  in `werkzeug_schleife.run_tool` (`core/werkzeug_befund.py`). Ein Ausführer
  sagt den Status mit einem `Befund` (ein `str` mit `status` und `beleg`);
  alte Text-Ausführer werden an „[Fehler …]" erkannt. Nie „None": ein leeres
  Ergebnis heißt `fehlgeschlagen`. Der Tutor (fremdes Tool-Set) bekommt
  keinen Kopf. Das `werkzeug`-Event „fertig" trägt `status` mit.
- **Belege.** Jedes schreibende Werkzeug (Register: `schreibt`, `beweis`)
  liest nach dem Schreiben nach und gibt zurück, was **wirklich** dasteht —
  Kalender (Zeit von–bis, Ort, Wiederholung, Pausen, Warnungen dazu),
  Notizen („steht im Tagebuch …"), Messkurven, Skills, Ablage. Steht es nicht
  da: `fehlgeschlagen` und „melde keinen Erfolg".
- **Zwei Ausgänge, feste Codes** (seit 2026-10-09). Ein schreibendes
  Werkzeug ist ERLEDIGT (`ok`, Satz aus dem nachgelesenen Stand: „Notiz in
  den Hausregeln GESPEICHERT — steht jetzt drin: …") oder ABGEBROCHEN
  (`fehlgeschlagen`, nichts geändert): „<was> ABGEBROCHEN – nichts
  eingetragen. Fehler K-ENDE-VOR-BEGINN: …". `teilweise` gibt es nicht mehr
  — es hieß, das Werkzeug tat etwas anderes als verlangt. Erst prüfen, dann
  schreiben, dann nachlesen; steht es nicht so da, wird der alte Stand
  zurückgelegt (`core/schreib_sicherung.py`; der Kalender-Kern kann das per
  Kennung selbst). Codes an EINER Stelle: `core/fehlercodes.py`; die KI
  schlägt sie mit `explain_error` nach (gross, frei). Lesen in Stücken
  (read_pdf/read_docx über 20.000 Zeichen) ist `ok` mit „Seiten 1–20 von 45
  gelesen, weiter mit seiten=21-45". Tests: `tests/test_fehlercodes.py`
  (jeder Code erklärt, kein Abbruch ohne Code, Abbruch nach dem Schreiben
  lässt die Daten Byte für Byte wie vorher).
- **ask_choice ohne Antwort** (Zeit um, gestoppt) → `keine_antwort`: „Sasha
  hat NICHT geantwortet — ändere nichts, was davon abhängt, frag nach".
  `wait_permission` liefert dafür `None` statt des Texts „(keine Antwort)".
  Das Ergebnis geht als `werkzeug`-Event raus und steht im Verlauf (vorher
  fehlte es dort — wer das Gespräch nachlas, sah bei ask_choice nichts und
  hielt es für „None"). Laut Journal hatte Sasha am 08.10. tatsächlich „ja"
  geklickt; gefunden und behoben wurde dabei ein echtes Rennen in der TUI:
  `ai_answer_perm` löschte nach dem POST `AI["perm"]` — auch wenn dort schon
  die NÄCHSTE Frage stand. Jetzt nur noch die beantwortete.
- **Websuche** beginnt mit „Treffer = Hinweise, NICHT gelesen …";
  **fetch_url** warnt (Status `ok`), wenn eine Seite kaum Inhalt hatte
  (unter 80 Wörtern oder 3 ganzen Sätzen: Navigation, Menü, Anmeldung) und
  sagt nur, was zu sehen war.
- **Browser** (seit 2026-10-09): jedes Ergebnis nennt „Adresse: <URL>" und
  darf als „gelesen auf <URL>" angegeben werden — Gegenstück zu den
  Suchtreffern. Abbrüche mit Codes `B-…` (Tabelle in `core/fehlercodes.py`,
  s. „Browser").
- **Prompt (gross), Meta-Regel 2:** „Als Tatsache sagst du nur, was ein
  Werkzeug in diesem Gespräch belegt oder Sasha gesagt hat; alles andere als
  Vermutung oder ‚weiß ich nicht'. Erfolg erst nach dem Beleg." Nach
  Anthropic: „Reduce hallucinations" (weiß-ich-nicht erlauben, an Belege
  binden) und „Writing effective tools for agents" (Ergebnisse mit hohem
  Signal statt „OK", Fehler, die zum richtigen Gebrauch lenken).

### Ehrlichkeit live — Prüfer vor jeder Antwort (seit 2026-10-09)

Auf gross prüft Python jede fertige Antwort gegen das Werkzeug-Protokoll des
Zugs (`core/ehrlichkeit.py`): Erledigt-Behauptung ohne passendes
schreibendes Werkzeug mit ok, oder eine Kalender-Kennung, die nirgends
steht → Korrekturrunden (`<pruefung_automatisch>` als Nutzer-Nachricht),
bis die Antwort besteht, höchstens `pruefer_runden` (5); danach geht sie mit
Warnungen davor raus (Feld `warnungen`). Dazu Erledigt-Zeile aus dem
Protokoll (auch „✗ keine Änderung in diesem Zug") und offene Zusagen im
Kontext-Umschlag. Läuft der Zug im Budget-Rückfall auf einem anderen Modell,
meldet `kern.chat` das am Anfang (`{"modell_wechsel": …}`,
`ai_backends.modell_wechsel`). Einstellung `ehrlichkeit_pruefer`. Seit
2026-10-10 dazu die **Quellen-Zeile** (`core/quellen.py`, Feld `quellen`):
welche Seiten der Zug wirklich gelesen hat — Python, nicht die KI, nennt die
Adresse. Und „frag nicht im Text, ruf das Werkzeug": endet die Antwort mit
„Soll ich im Netz suchen?" o. ä., obwohl Sasha gefragt/beauftragt hat, gibt
es eine Korrekturrunde (alle Modelle, vorher nur qwen); ebenso bei einem
Aufschub („trag ich erst ein, wenn …") eines klaren Auftrags — Sicheres
sofort, nur das Fehlende fragen (auch als Satz im Antwortverhalten). Seit
2026-10-10 sprachfrei: die KI gibt jede Antwort über `antwort` mit festen
Feldern ab (**Selbstauskunft**, `core/selbstauskunft.py`), Python vergleicht
sie mit dem Protokoll; freier Text → Wortlisten wie bisher, Widerspruch →
„unsicher" (`core/klassifikator.py`, Einstellung `klassifikator`, Standard
aus); jede geprüfte Antwort wird ein lokales Beispiel
(`core/klassifikator_beispiele.py`). Alles Weitere:
[ehrlichkeit_live.md](ehrlichkeit_live.md).

### Kalender ohne Fallen — `core/ki_kalender.py`, `ki_kalender_aendern.py` (seit 2026-10-08)

- **Kennungen** (nur `gross`): `read_calendar` zeigt je Zeile `#t…` (Termin)
  bzw. `#r…` (Routine), dazu die Serien mit allen Feldern. Seit 2026-10-09
  abgeleitet aus der FESTEN Kennung des Kalender-Kerns
  (`core/kalender_kennung.py`, UID): 4 Zeichen, bei Kollision länger, und
  dieselbe auch nach Umbenennen, neuer Uhrzeit, neuem Ort. Eine gelöschte
  trifft nichts mehr (`K-KENNUNG-UNBEKANNT`). `klein` liest wie gemessen.
- **Per Kennung schreiben** (2026-10-09): ändern, löschen, absagen, pausieren
  laufen über die Funktionen von `kalender_kennung` — der Kern prüft vorher
  und schreibt ganz oder gar nicht; seine Ablehnung kommt als `K-<CODE>`
  durch. Neu anlegen: nachlesen, und steht es anders da als verlangt, per
  Kennung wieder löschen (`W-NICHT-GESPEICHERT`). Rückmeldung in fester
  Form aus dem echten Stand: „Kalendereintrag „Geigenstunde" am Do
  08.10.2026 18:10–19:00 @ Geigenschule EINGETRAGEN (#t3f9c)."
- **Genau EIN Eintrag.** Ändern/Löschen per Kennung; per Name nur bei genau
  einem Treffer (genauer Titel vor Teilstring), sonst nichts ändern und die
  Treffer mit Kennungen zurück. Wo der Kalender-Kern per Teilstring trifft,
  wird vorher nachgerechnet, ob er genau das Gemeinte träfe.
- **Nur genannte Felder.** `edit_calendar_routine` (auch `nur_am`: ein Datum
  ändern oder absagen), `edit_calendar_entry` (neu). Ende vor Beginn wird
  abgelehnt statt still verworfen.
- **Nichts annehmen.** `add_calendar_*` haben auf `gross` `ende` und `ort`;
  fehlt das Ende, steht im Ergebnis „ohne Ende — die Ansicht zeichnet eine
  Stunde, frag nach". Kein Pflichtfeld: sonst müsste die KI eins erfinden,
  wenn Sasha keins genannt hat.
- **Serien nur mit Zeitraum** (gross, 2026-10-09): Sashas Uni-Fächer liefen
  „für immer", auch in den Wochen vor Semesterbeginn. `add_calendar_routine`
  verlangt `von`/`bis` (YYYY-MM-DD); gespeichert als `seit` = von und
  `UNTIL=<bis>T235959` in der RRULE (Standard, .ics-tauglich). Abbrüche:
  fehlt eins → `K-ZEITRAUM-FEHLT` (frag Sasha), UNTIL/COUNT schon in der
  rrule → `K-RRULE-MIT-ENDE` (Ende nur über bis), bis < von →
  `K-SPANNE-VERDREHT`. Nachgelesen werden auch seit und UNTIL. Rückmeldung,
  Frage und `read_calendar` nennen den Zeitraum („… vom 12.10.2026 bis
  13.02.2027"); Serien ohne Ende zeigt `read_calendar` als „(ohne
  Enddatum)". `edit_calendar_routine` setzt/ändert ihn mit `von`/`bis`
  (dieselben Prüfungen); eine neue `rrule` behält das bisherige Ende.
  `klein` unverändert (kein Zeitraum).
- **Pausen** hängen seit 09.10. per Kennung fest an GENAU einer Routine;
  heißt keine genau so, bricht es ab (`K-PAUSE-KEINE-ROUTINE`, mit
  Vorschlag, nichts gespeichert) — vorher wurde eine wirkungslose Pause
  gespeichert (am 08.10. traf „Geigenstunde" die Routine „Geigenstunde @
  Geigenschule" nicht).
  Auf `gross` ist `bis` kein Pflichtfeld (2026-10-08): ohne Ende fällt nur
  der Tag `von` aus, und das Ergebnis sagt „Ende noch offen — frag nach".
  Vorher schob die KI bei „fällt jetzt aus, bis wann?" die ganze Pause auf,
  und die Geige am selben Abend blieb stehen.
- **Was beim Löschen verloren geht** (2026-10-09): löscht `edit_calendar_routine`
  eine Routine und bleibt eine gleichnamige, sagt das Ergebnis, welche Felder
  (Ort, Ende) mit der gelöschten weg sind. Beim Ändern nennt es gleichnamige,
  die mehr Felder haben.
- **Termin per Name ohne Tag** (gross): trifft der Name genau einen Termin,
  der noch nicht vorbei ist, ist er gemeint; sonst die Liste.
- **Warnungen:** `read_calendar_warnings` rechnet sie frisch
  (`kalender.open_alarms`, dieselben wie Sashas ⚠); jeder Beleg nennt die
  Warnungen zum Titel.
- Die Fragen an Sasha nennen bei einer Kennung den Termin („"Geigenstunde"
  (wöchentlich do 18:10–19:10)"), bei Routinen auch Uhrzeit, Ende, Ort.
- Was der Kalender-Kern dafür noch können müsste: `claude_web_plan.md` §7.

### Sandbox — `run_code` und `core/sandbox.py` (seit 2026-10-07)

Grundlage dafür, dass der Assistent später „wie ein Coder" arbeitet (Phase 7,
[claude_web_plan.md](claude_web_plan.md)). Das Werkzeug `run_code` (nur
`gross`, Parameter `code`, `sprache` python|shell, `zeitlimit`, `skill`) ist
**immer** gegatet; die Frage zeigt Sprache und die ersten vier Zeilen.
Ausgeführt wird über `sandbox.ausfuehren(code, sprache, zeitlimit_s, dateien,
lauf_id, abbruch, skill_ordner)` mit **bubblewrap** (`/usr/bin/bwrap`, unprivilegiert).

**Skill-Skripte (seit 2026-10-07):** mit `skill="<name>"` hängt die Sandbox
den Ordner dieses Skills **nur lesend** unter `/skills/<name>` ein (wie
Claudes `/mnt/skills/…`) — die einzige Ausnahme von „nichts von Sasha", und
nur für einen **aktiven** Skill (`skills.skript_ordner`); sonst läuft nichts.
Die Frage nennt den Skill („… dazu sieht es den Skill „x" (nur lesen)").
Geschrieben wird weiter nur nach `/arbeit`. Geprobt mit `quick_validate.py`
und `package_skill.py` des skill-creator (`tests/test_skill_skripte.py`).

**Zeitlimit (seit 2026-10-07, Sasha):** Standard 30 s, bis 120 s mit dem
normalen Ja (auch „immer"/„für dieses Gespräch"). Länger (bis 30 min,
`ZEITLIMIT_MAX_S`) nur nach **eigener** Frage mit der Dauer im Text („… und
darf bis zu 10 Minuten laufen"), die NUR „ja, nur dieses mal" anbietet —
Register-Feld `nur_einmal`; ein altes „immer" deckt das nicht.

**Stoppen (seit 2026-10-07):** das Stopp-Signal des Zugs geht über
`core/zug.py` (`zug.beginnen(gid, abbruch=…)`, `zug.abbruch()`) an
`run_code`; `sandbox._warten` schaut alle 0,1 s nach und tötet dann die ganze
Prozessgruppe (SIGKILL). Ergebnis: „[Abgebrochen: vom Nutzer gestoppt.]",
Kopf „VOM NUTZER GESTOPPT", Feld `gestoppt`.

**Abgeschottet:**
- Dateisystem: nur `/usr` (+ `/bin` `/lib` … als Verweise) nur-lesend, eigenes
  `/proc` `/dev`, `/tmp` im Speicher (64 MB, wo bwrap `--size` kann), die
  Wurzel nur-lesend, `/etc/localtime` (Zeitzone). Beschreibbar ist **nur**
  `/arbeit` = der Arbeitsordner des Laufs. **Nicht sichtbar:** `/home` (Repo,
  `data/`, `~/.ssh`, Keys), `/etc`, `/var`, `/run`, `/root`.
- Netz: `--unshare-all` → nur ein eigenes, totes loopback.
- Umgebung: leer bis auf `PATH`, `HOME=/arbeit`, `LANG` — keine API-Keys.
- Prozesse: eigener PID-Namensraum, `--die-with-parent`, `--new-session`
  (kein Terminal-Einschleusen), keine weiteren Benutzer-Namensräume.
- Grenzen: Zeitlimit (Standard 30 s, s. o.; danach SIGKILL an die ganze
  Gruppe, der PID-Namensraum nimmt alles mit), 512 MB Adressraum, 64 Prozesse
  (in der Sandbox gesetzt — vor bwrap ließe RLIMIT_NPROC schon die
  Namensräume scheitern), 50 MB je Datei, nice 10, Ausgabe je Strom 20.000
  Zeichen (Kopf + Schwanz, beim Lesen gekappt).
- **Nie ohne Sandbox:** fehlt bwrap oder startet es nicht (bwrap meldet kein
  `child-pid` über `--json-status-fd`), kommt `rc=None` + Klartext-Fehler;
  das Programm läuft dann gar nicht.

**Nicht abgeschottet / bewusst offen:**
- CPU-Last bis zum Zeitlimit (nur nice), und `/arbeit` hat keine
  Gesamtgröße (nur je Datei 50 MB).
- Was in `/usr` liegt, ist lesbar und ausführbar — also auch System-Pakete
  unter `/usr/lib/python3/dist-packages` (hier PIL, bs4, lxml, yaml;
  **kein** numpy/pandas). Seit 2026-10-07 sagt die Beschreibung von
  `run_code` dem Modell genau das (vorher „nur Standardbibliothek").
  Die venv des Projekts liegt im Repo und ist NICHT drin.

**Arbeitsordner:** `~/.cache/zentrale/sandbox/<lauf-id>/` (Einstellung
`sandbox_dir`, Env `ZENTRALE_SANDBOX_DIR`; Tests → tmp). Bewusst NICHT
`data/sandbox/`: `zentrale-sync` spiegelt alles Ungetrackte unter dem Repo
(auch `data/`), additiv — KI-Erzeugnisse wanderten sonst auf den anderen
Rechner und kämen nach dem Aufräumen zurück. Jeder `run_code`-Lauf bekommt
einen frischen Ordner; Ordner älter als 7 Tage löscht `aufraeumen()` vor
jedem Lauf. Neue Dateien meldet das Ergebnis mit Name und Größe (Verweise
werden nicht verfolgt). Das Modell sieht nie den echten Pfad, nur `/arbeit`.
Behalten über 7 Tage hinaus = `save_from_sandbox` in die Ablage — seit
2026-10-07 **gegatet** und nur auf Sashas Wunsch (steht so in der
Beschreibung; „immer" wird dafür nicht angeboten).

### Skills — `load_skill`, `propose_skill`, `edit_skill` (seit 2026-10-07)

Phase 4 des [Claude-Web-Plans](claude_web_plan.md); seit dem Abend des
07.10. im **Format von Claude** (Sasha: echte Claude-Skills sollen ohne
Umbau hineinpassen). Ein Skill ist eine **Anleitung für eine Art Aufgabe**
(„Woche planen", „einen Skill bauen"), keine Regel: was immer gilt, sind
Hausregeln. Module `core/skills.py`, `core/skill_format.py`,
`core/skill_umzug.py` (Schicht 2), Ordner `data/gedaechtnis/skills/<name>/`
mit `SKILL.md` — Aufbau, Status, Umzug und Erstbefüllung in
[gedaechtnis_dateien.md](gedaechtnis_dateien.md), Abschnitt „Skills".

**Drei Stufen wie bei Claude („Progressive Disclosure"):**
1. **Liste im Kopf.** `skills.prompt_block()` steht im festen, gecachten
   Kopf (`cloud._static_system`, hinter dem Gedächtnis-Kopf, nur wenn die
   Schiene `MERKMALE["skills"]` hat — `gross` ja, `klein` nicht): eine
   Zeile `- name — description` je **aktivem** Skill, nach Name sortiert,
   ohne Datum oder Zähler. Die `description` ist Claudes Auslöser und darf
   bis 1.024 Zeichen lang sein. **Deckel für die ganze Liste: 6.000
   Zeichen** (`LISTE_MAX`, ≈ 1.700 Token, gecacht ≈ 0,05 Cent je Zug; nicht
   größer als der übrige feste Kopf). Die Start-Skills brauchen ~4.300.
   **Seit 2026-10-08 nicht mehr gleichmäßig gekürzt** (Sasha: das
   verschlechtert alle Beschreibungen): sie bleiben vollständig, und
   Customize → Skills zeigt „Liste zu lang: N von 6 000 Zeichen — schalte
   Skills aus, die du nicht brauchst" (`skills.liste_lage()`, in
   `/api/skills` und `/api/gedaechtnis` als `skill_liste`). Nur als letzte
   Rettung bekommen die **längsten** nacheinander eine Kurzfassung
   (`skills.kurzfassung`: erster Satz, 160–320 Zeichen), bis es passt; die
   kurzen bleiben unangetastet. Reicht das nicht, stehen die längsten nur mit
   Namen da. Reihenfolge (Länge absteigend, Name) — deterministisch.
2. **Anleitung per `load_skill(name)`** als Werkzeug-Ergebnis (wandert mit
   dem Verlauf, berührt den Cache-Anfang nicht): der Text der SKILL.md ohne
   Kopf, je Aufruf 20.000 Zeichen (weiter mit `ab`), dazu die Liste seiner
   Dateien (ohne Lizenz und `_zentrale.json`). Liegt `references/zentrale.md`
   im Skill (ZENTRALEs Zusatz zu einem fremden Skill), steht vorne der
   Hinweis, sie zuerst zu lesen.
3. **Dateien per `load_skill(name, datei=…)`** (references/, assets/,
   scripts/ lesen); kein Weg aus dem Skill-Ordner (echter Pfad muss drin
   liegen, Verweise aufgelöst), Binärdateien nur als Hinweis. **Skripte
   laufen nur über `run_code(skill=…)`** in der Sandbox (s. „Sandbox").

Wann laden, wann vorschlagen: Meta-Regel 6 in `profil/gross.py`.

| Werkzeug | Was | Gate |
|---|---|---|
| `load_skill(name, datei?, ab?)` | Anleitung bzw. Datei eines aktiven Skills; ausgeschaltete/vorgeschlagene geben nichts heraus | nein |
| `propose_skill(name, beschreibung, inhalt)` | neuen Skill anlegen: `SKILL.md` (Kopf nur `name` + `description`) + `_zentrale.json` (`herkunft: ki`, `status: aktiv`); bestehender Name → Fehler | **ja** — Frage zeigt Name, Beschreibung, erste drei Zeilen |
| `edit_skill(name, inhalt)` | Anleitung ersetzen; der YAML-Kopf bleibt Zeichen für Zeichen (auch fremde Felder), alte Fassung als `SKILL.md.bak` | **ja** |

Sagt Sasha nein, läuft der Ausführer gar nicht: die Schleife meldet dem
Modell „abgelehnt — nichts ausführen" (`werkzeug_schleife.run_tool`), es
entsteht keine Datei. Ein vom Modell mitgeschickter Kopf (mit `name` oder
`description`) wird bei `edit_skill` verworfen: Name und Beschreibung ändert
nur Sasha, Status und Herkunft stehen ohnehin in `_zentrale.json`. Grenzen:
Beschreibung ≤ 1.024 Zeichen ohne `<` `>` (Claudes Regeln), Anleitung ≤
20.000. Die KI kann nur die SKILL.md schreiben, keine weiteren Dateien.
Text-Budget der drei Beschreibungen: eigener Deckel < 600 Zeichen in
`tests/test_profil.py`. Anzeige: `GET /api/skills` mit `braucht` und
`vermerk` ([api_endpoints.md](../system/api_endpoints.md)). Sasha sieht und
schaltet Skills in der TUI (`/skills` im Chat, Gedächtnis-Ansicht;
`POST /api/skills/<name>/status`) — die KI kann keinen Skill abschalten.

**Skills von Anthropic** (seit 2026-10-07): 14 Skills aus
github.com/anthropics/skills (Commit 683bc88, nur Apache 2.0) liegen als
Vorlagen in `core/skill_vorlagen/anthropic/` (Herkunft und Lizenz:
`README.md` dort). An: skill-creator, academy-guide, claude-api,
discernment-nudge, frontend-design, internal-comms. Aus mit „braucht: …"
(Browser, Bildausgabe, Node/npm, MCP, Slack): die übrigen acht. Der
skill-creator bekam `references/zentrale.md` dazu — was davon hier geht
(Testläufe selbst ausführen, Ergebnisse in die Ablage, kein `claude -p`,
kein Browser).

**`import-memory`** (seit 2026-10-08, `herkunft: zentrale`): Erinnerungen aus
einer anderen KI übernehmen, nach Claudes Skill gleichen Namens neu
geschrieben. Geschrieben wird nur über `write_note(…, herkunft="claude")` —
zeilenweise, nur Neues, mit Herkunftsvermerk, nie Kataloge/Tagebuch
([gedaechtnis_dateien.md](gedaechtnis_dateien.md), „Import aus einer
anderen KI").

#### Nutzerordner, Suchen, Claude-Skills übernehmen (seit 2026-10-09)

Anlass: Gespräch 20261009-155510. Sasha legte „Chefkoch ai-v1.zip" in den
ZENTRALE-Ordner; `list_files` war bei 300 von ~5.000 Dateien gekappt (Hinweis
nur am Ende), die KI sagte „ich seh keine chefkoch-Datei", und übernehmen
konnte sie ohnehin nicht. Sasha danach: Dateien findet man durch Suchen, nicht
durch Listen — und der Assistent bekommt keinen Zugriff mehr auf den
Code-Dschungel unter ~/codicus (das wird eine eigene Coder-App).

**Der Nutzerordner** (`core/nutzer_ordner.py`, Einstellung `nutzer_ordner`,
Env `ZENTRALE_NUTZER_ORDNER`, Standard `~/Zentrale`): zwei Unterordner,
`Input/` (was Sasha der KI hineinlegt) und `Output/` (was die KI Sasha gibt),
beim ersten Zugriff angelegt. Pfade wie „x.zip", „Input/x.zip" oder absolut;
was (Verweise aufgelöst) hinausführt, gilt nicht. `read_file` liest dort auch
(„Input/notiz.md"; Secrets und Verstecktes gesperrt). Tests lenken ihn per
conftest um (Wächter in `tests/test_keine_seiteneffekte.py`).

**Suchen** (`core/nutzer_suche.py`, nur gross, frei), NUR in Input/ und
Output/ (oder einem Ordner darin), ohne Verstecktes und Secret-Namen:
- `find_files(muster, ordner?)` — wie find: `*.zip`, `*chefkoch*`; ohne
  Platzhalter ein Namensteil (Groß/Klein und Trenner egal: „chefkoch-ai" trifft
  „Chefkoch ai-v1.zip"). Zählt alle, zeigt 50, flache zuerst.
- `search_files(text, ordner?, muster?)` — wie `grep -i -F`: `pfad:zeile:
  auszug`, höchstens 100 Treffer, Binärdateien übersprungen, Dateien über 2 MB
  nicht durchsucht.
- `list_files(ordner?)` auf gross — EIN Ordner wie ls (Unterordner mit `/`).
- **Jede Suche sagt, wie vollständig sie war**, in der ersten Zeile und in
  fester Form: „Suche vollständig: N Treffer — durchsucht: Input/, Output/
  (K Dateien)." oder „Suche NICHT vollständig: abgebrochen nach 100 Treffern
  …" / „… 2 Dateien über 2 MB oder unlesbar, nicht durchsucht …".
  Maschinenlesbar zusätzlich `Befund.vollstaendig` (core/werkzeug_befund.py).
  Der Prüfer „nicht da" ([ehrlichkeit_live.md](ehrlichkeit_live.md)) lässt
  „gibt es nicht" nur nach „Suche vollständig: 0 Treffer" durch.
- Die Ablage (core/ablage.py) durchsuchen die Werkzeuge noch nicht (offen).

**`import_skill(pfad)`** (gegatet, kein „immer"): `core/skill_import.py`.
So importiert man einen Claude-Skill: Zip oder Ordner in `~/Zentrale/Input/`
legen, der KI sagen „übernimm den Skill" — sie sucht mit `find_files`, Sasha
bestätigt „Skill „chefkoch-ai“ aus „Chefkoch ai-v1.zip“ übernehmen?" (die
Frage packt vorab aus und nennt die echten Namen).
- **Nur aus Input/**; alles andere → `S-QUELLE-AUSSERHALB`.
- **Formen:** Plugin (`.claude-plugin/plugin.json` + `skills/<name>/SKILL.md`,
  auch eigene Skill-Pfade aus plugin.json), Skill-Ordner (`<name>/SKILL.md`,
  auch mehrere), Zip mit `SKILL.md` in der Wurzel, die `SKILL.md` selbst. Ein
  einzelner Hüllordner in der Zip wird übersprungen.
- **Sicher:** erst alle Einträge prüfen — absolute Pfade, `..`, Symlinks →
  `S-UNSICHER`; > 20 MB entpackt oder > 500 Dateien → `S-ZU-GROSS` (beim
  Auspacken mitgezählt, die Angabe der Zip kann lügen). Versteckte Dateien,
  `__MACOSX`, `__pycache__` und Schlüssel-Namen bleiben draußen (gezählt).
- **Prüfen** wie Claude: `name` (Claudes Regeln) und `description` (≤ 1.024,
  ohne `<` `>`) im Kopf, Anleitung nicht leer, kein Name doppelt → sonst
  `S-SKILL-UNGUELTIG`; keine SKILL.md → `S-KEIN-SKILL`.
- **Gibt es den Namen schon:** `S-SKILL-GIBT-ES`, nichts geschrieben — die KI
  fragt Sasha, statt umzubenennen oder zu überschreiben.
- **Ablegen:** ausgepackt in einen versteckten Arbeitsordner IM Skill-Ordner,
  dann je Skill `os.rename` nach `skills/<name>/` (atomar). `_zentrale.json`:
  `status: aktiv`, `herkunft: sasha`, `quelle`: „Chefkoch ai-v1.zip (Plugin
  chefkoch-ai 1.0.0, Autor …, Lizenz …)" — keine Mail-Adressen. Nachgelesen in
  `skills.aktive()`; fehlt einer, sind ALLE neuen Ordner wieder weg
  (`W-NICHT-GESPEICHERT`). Mehrere Skills: ganz oder gar nicht.
- **Ergebnis:** „Skill „chefkoch-ai“ ÜBERNOMMEN (aktiv): SKILL.md + 2
  Referenzen." Skripte (`scripts/`) kommen mit und werden genannt — sie laufen
  nur in der Sandbox (`run_code(skill=…)`).
- **Wann er in der Liste steht:** der feste Kopf wird je Nachricht neu gebaut
  (`cloud._static_system` → `skills.prompt_block()`), also ab Sashas nächster
  Nachricht (der Cache-Anfang ändert sich dabei einmal); `load_skill` sofort.

Fehlercodes: `S-QUELLE-FEHLT`, `S-QUELLE-AUSSERHALB`, `S-QUELLE-GESPERRT`,
`S-ZIP-KAPUTT`, `S-UNSICHER`, `S-ZU-GROSS`, `S-KEIN-SKILL`,
`S-SKILL-UNGUELTIG`, `S-SKILL-GIBT-ES` (`core/fehlercodes.py`). Einträge in
`core/werkzeug_nutzer_ordner.py`, Ausführer in `core/ki_nutzer_ordner.py`
(list_files: `ki_werkzeuge`, nach Schiene). Text-Budget der drei
Beschreibungen: Deckel < 550 in `tests/test_profil.py`. Tests:
`tests/test_skill_import.py`, „nicht da" in `tests/test_ehrlichkeit.py`.

**`unzip(datei, ansehen?)`** (`core/input_dateien.py`, seit 2026-10-09): Zips,
die kein Skill sind. Nur aus Input/. `ansehen=true` (frei): Pfade, Größen,
Anzahl, was ausgelassen würde, ob Auspacken ginge — nichts ausgepackt. Sonst
gegatet: „„Fotos.zip“ nach Output/Fotos/ auspacken? 2 Dateien, 1 KB, 3
ausgelassen." Dieselben Regeln wie import_skill aus `core/zip_sicher.py`
(geteilt, nicht kopiert): `..`/absolut/Symlink → `Z-UNSICHER`, > 20 MB oder
> 500 Dateien → `Z-ZU-GROSS`, Verstecktes/Ballast/Schlüssel-Namen ausgelassen
und im Ergebnis genannt. Ziel `Output/<name ohne .zip>/`; gibt es das schon →
`Z-ZIEL-GIBT-ES`, nichts überschrieben. Ganz oder gar nicht: ausgepackt in
einen versteckten Ordner in Output/, nachgezählt, dann `os.rename`. Ergebnis:
„„Fotos.zip“ AUSGEPACKT nach Output/Fotos/: N Dateien (…)". Die Zip bleibt in
Input/.

**`remove_input(datei)`** (gegatet: „„x“ aus Input entfernen? (kommt in den
Papierkorb)"): VERSCHIEBT einen Eintrag direkt aus Input/ nach
`<nutzer_ordner>/.Papierkorb/<YYYY-MM-DD>/` — Namenskonflikt → „x (2).pdf";
gelöscht wird nie (der Abgleich ist additiv). Unterordner → `Z-NICHT-DIREKT`.
Nachgesehen: am neuen Ort da, am alten weg — sonst zurückgelegt
(`W-NICHT-GESPEICHERT`). Der Papierkorb ist versteckt, also für Suchen und
`read_file` unsichtbar.

**Input aufräumen** (`core/input_aufraeumen.py`; Sasha: „damit der ordner nich
zur halde wird"): Hat ein Werkzeug eine Datei DIREKT aus Input/ fertig
verarbeitet — `import_skill`, `unzip`, `read_pdf` (alle Seiten), `read_docx`
(letztes Stück), `read_file`, `fetch_document` mit Input-Pfad —, hängt an sein
Ergebnis die feste Zeile „Frag Sasha jetzt, ob <datei> aus Input weg soll
(remove_input)." und im Gespräch steht eine offene Zusage (`core/zusagen.py`,
Feld `art: "input_aufraeumen: <datei>"`). Sie steht in jedem Zug im
Kontext-Umschlag („Noch offen von dir zugesagt"), bis `remove_input` für die
Datei lief, die Datei sonst weg ist, oder Sasha nein sagte — am Gate von
`remove_input` oder in einem `ask_choice`, dessen Frage die Datei nennt
(Wahl „Nein"/„behalten"/…). Werkzeug-Zusagen verfallen nicht und werden nicht
von irgendeinem anderen Werkzeug abgehakt (`zusagen.nachfuehren` lässt Einträge
mit `art` in Ruhe; abgehakt in `ehrlichkeit.Pruefer` →
`input_aufraeumen.nachfuehren`). Nicht nach Lesefehlern/Abbrüchen, nicht für
Dateien in Unterordnern, nur auf gross.

Fehlercodes `Z-…` (Vorsilbe Z = Nutzerordner ~/Zentrale): `Z-QUELLE-FEHLT`,
`Z-QUELLE-AUSSERHALB`, `Z-QUELLE-GESPERRT`, `Z-KEINE-ZIP`, `Z-ZIP-KAPUTT`,
`Z-UNSICHER`, `Z-ZU-GROSS`, `Z-LEER`, `Z-ZIEL-GIBT-ES`, `Z-NICHT-DIREKT`,
`Z-VERSCHIEBEN`. Text-Budget der beiden Beschreibungen: Deckel < 300 in
`tests/test_profil.py`. Tests: `tests/test_input_aufraeumen.py`.

Relative Pfade lösen `read_file`, `read_pdf`/`read_docx` und `fetch_document`
seit 2026-10-09 an EINER Stelle auf (`context.pfad_aufloesen`) — vorher kannte
nur `read_file` „Input/…".

#### Reichweite von gross: nur der Nutzerordner (Rückbau 2026-10-09)

Sasha: der Assistent arbeitet nur mit `~/Zentrale` (Input/, Output/) und
seinem Gedächtnis; Datei- und Code-Zugriff auf ~/codicus gehört später zur
Coder-App „Codicus". Umgesetzt an der einen Stelle, die alle fragen
(`context.erlaubt`, `context.pfad_aufloesen`), abhängig von der Schiene des
laufenden Werkzeug-Aufrufs (`werkzeug_befund.schiene()`):

- **gross:** `read_file`, `read_pdf`/`read_docx` (Dateipfad) und
  `fetch_document` (lokal) lesen NUR in Input/ und Output/; relativ heißt im
  Nutzerordner, ein bloßer Name meint Input/ („[Datei nicht gefunden:
  Input/core/x.py]" sagt, wo gesucht wurde). Absolut oder per Verweis hinaus →
  `Z-AUSSERHALB` (read_file, fetch_document) bzw. `P-QUELLE-AUSSERHALB`
  (read_pdf/read_docx). Ablage-ids (Anhänge, eigene Dokumente) gehen weiter.
  `unzip`/`import_skill`/`remove_input` waren schon auf Input/ begrenzt.
- **klein:** unverändert (Whitelist + ~/codicus, Gesamtliste in `list_files`);
  das qwen ist auf die Texte gemessen. Zieht später nach.
- **Was wegfällt und wodurch ersetzt:** `data/*.json` (Schlaf, Messreihen) →
  `read_series`; `notes.md` → das Gedächtnis (`read_note`/`write_note`,
  Bereich `notizen`; die Datei war nur noch die leere Vorlage);
  `core/*.py`, `ui/app.py`, ~/codicus → nichts (Coder-App). Kalender, Notizen,
  Mail, News lesen ohnehin ihre eigenen Werkzeuge.
- Tests: `tests/test_reichweite_gross.py`.

### Frühere Gespräche — `search_chats`, `read_chat` (seit 2026-10-07)

Phase 3 des [Claude-Web-Plans](claude_web_plan.md). Sasha orientiert sich
nach Thema, nicht nach Datum; seit es viele Gespräche gibt
([gespraeche.md](gespraeche.md)), muss die KI aus jedem Gespräch heraus
finden, was in einem anderen gesagt wurde. Modul `core/chat_suche.py`
(Schicht 2), beide Werkzeuge nur `gross`, **ungegatet** (nur lesen).

| Werkzeug | Was |
|---|---|
| `search_chats(query)` | höchstens 8 Treffer: Titel, id, Datum, Zahl der Stellen, ein Ausschnitt (~220 Zeichen, Sasha oder KI) |
| `read_chat(id, query?, anzahl?)` | ein Gespräch nachlesen: die letzten `anzahl` (20, max 40) Nachrichten, mit `query` das Fenster um die beste Fundstelle; jede Nachricht ≤ 1.500 Zeichen |

Durchsucht werden alle Gespräche (auch archivierte, „Erinnerungen") und das
alte Transkript, nach Tag gruppiert (id `transkript:JJJJ-MM-TT`). Wie
gesucht wird, was ausgelassen wird (Denken, versteckte Aufträge, das
laufende Fenster, Doppeltes aus dem Transkript): [gespraeche.md](gespraeche.md),
Abschnitt „Suche". Wann suchen: Meta-Regel 7 in `profil/gross.py` („bezieht
sich Sasha auf Früheres … erst search_chats"). Text-Budget der zwei
Beschreibungen: eigener Deckel < 450 Zeichen in `tests/test_profil.py`.

Zwei Werkzeuge statt eines mit Modus: jedes Schema bleibt klein und
eindeutig, und das Modell muss keinen Modus-Parameter richtig setzen.

Seit Phase 6 hat `search_chats` einen optionalen Parameter `projekt` (Name
oder id): dann nur die Gespräche dieses Projekts, ohne das alte Transkript.

### Projekte — Projekt-Block und `read_project_file` (seit 2026-10-07)

Phase 6 des [Claude-Web-Plans](claude_web_plan.md), ausführlich
[projekte.md](projekte.md). Ein Gespräch kann zu einem Projekt gehören
(eigene Anweisungen + Wissensdateien). Dann steht `projekte.prompt_block(id)`
im **festen, gecachten Kopf** (`cloud._static_system(…, projekt=)`, hinter
Gedächtnis-Kopf und Skill-Liste, vor dem Imprint; nur mit
`MERKMALE["projekte"]`, also `gross`): Name, Anweisungen (≤ 4.000 Zeichen,
sonst gekürzt) und die LISTE der Wissensdateien mit Größe. Byte-stabil, solange
Sasha am Projekt nichts ändert — der Cache gilt pro Projekt; ein Gespräch ohne
Projekt sieht keinen Block, sein Kopf bleibt wie vorher.

Das Projekt reist als **Parameter**: Chat-Route (`gespraeche.projekt_von`) →
`kern.chat(projekt=)` → `cloud.chat_stream` / `cloud_openai.chat_stream`
(`projekt=`) → `_static_system` und `ki_werkzeuge.mit_projekt(projekt)`. Kein
globaler Zustand; der lokale Weg und der Erinnerungs-Takt bekommen keins.

| Werkzeug | Was | Gate |
|---|---|---|
| `read_project_file(name, ab?)` | Wissensdatei des Projekts DIESES Gesprächs (≤ 20.000 Zeichen ab `ab`); „anweisungen" → die ungekürzten Anweisungen | nein |

Das Projekt bekommt der Ausführer von `ki_werkzeuge._verteilen` (markiert mit
`@braucht_projekt`), nie aus den Argumenten des Modells; gefunden wird nur
über die Dateiliste des Projekts — kein Pfad-Ausbruch, kein fremdes Projekt.
Keine neue Meta-Regel (der Kopf von `gross.system()` steht bei ~4.974 von
5.000 Zeichen); der Block erklärt sich selbst. Text-Budget: eigener Deckel
< 200 Zeichen in `tests/test_profil.py`.

### Ablage und Anhänge — `create_document` & Co. (seit 2026-10-07)

Phase 5 des [Claude-Web-Plans](claude_web_plan.md), ausführlich in
[ablage.md](ablage.md). Die KI legt Dokumente in `data/ablage/` ab
(`core/ablage.py`), Sasha gibt ihr Dateien mit (`core/anhang.py`).

| Werkzeug | Was | Gate |
|---|---|---|
| `create_document(titel, inhalt, art?, sprache?)` | neues Dokument (markdown/text/code/csv) | nein |
| `read_document(id)` | Inhalt lesen | nein |
| `update_document(id, inhalt)` | neue Fassung, alte bleibt | nein |
| `save_from_sandbox(lauf, datei, titel?)` | Datei aus einem `run_code`-Lauf dieses Gesprächs — nur auf Sashas Wunsch | **ja** (seit 2026-10-07, ohne „immer") |

Die ersten drei ungegatet, weil nur in den eigenen Ordner geschrieben, nie überschrieben,
nie gelöscht wird und nichts nach draußen geht. Ein Werkzeug meldet ein neues
Dokument über **`core/zug.py`** (der laufende Zug, Schicht 1): die Chat-Route
öffnet ihn mit der Gesprächs-id, holt nach jedem `werkzeug`-Event die
Meldungen ab und schickt sie als SSE `ablage`; so musste die Schleife nicht
umgebaut werden. Über denselben Zug bekommt `run_code` die Gesprächs-id für
seinen Arbeitsordner (`<gespräch>--<zeit>-<hex>`). Text-Budget der vier
Beschreibungen: eigener Deckel < 650 Zeichen in `tests/test_profil.py`.

**Anhänge** gehen als eigene Blöcke an die Cloud (Anthropic: `image`
base64 + `text`; OpenAI-kompatibel: Inhalt als Liste mit `image_url`); im
Gespräch steht nur ein Verweis, der Inhalt kommt beim Bauen des Verlaufs
dazu (`anhang.verlauf_einsetzen`). Lokal: Text ja, Bilder nein (400 mit
Hinweis auf `/cloud`).

### PDF und Word — `read_pdf` & Co. (seit 2026-10-08)

Sechs Werkzeuge nur auf `gross`, hinten an (Einträge in
`core/werkzeug_pdf_word.py`, Ausführer in `core/ki_pdf_word.py`):
`read_pdf`, `read_docx` frei; `create_pdf`, `combine_pdf`, `create_docx`,
`edit_docx` gefragt („immer" möglich — es entsteht nur eine neue Datei in der
Ablage, nie wird etwas überschrieben). Jede neue Datei wird aus der Ablage
nachgelesen (Seitenzahl/Text bzw. Überschriften/ersetzter Text) und als Beleg
zurückgegeben. Die Anleitung steht in den Skills `pdf` und `word`. Text-Budget
der Beschreibungen: eigener Deckel < 800 in `tests/test_profil.py`.
Ausführlich: [pdf_word.md](pdf_word.md).

### Browser — `browser_open` & Co. (seit 2026-10-09)

**Wozu:** Das Vorlesungsverzeichnis der Uni (LSF, QIS/HIS) ist ein Baum, der
sich erst durch Klicken aufbaut, teils in Rahmen. `fetch_url` bekam am 08.10.
nur den Navigationsbaum. Jetzt steuert die KI einen echten Chromium ohne
Fenster über Text — keine Bilder, keine Koordinaten.

**Aufbau:** `core/browser_sitzung.py` (Schicht 2) ist der Browser: Playwright
in **einem** eigenen Thread (Playwright hängt an seinem Thread; die Werkzeuge
laufen im Thread des Zugs und reichen Aufträge hinein), **ein**
Chromium-Prozess, darin je Gespräch ein eigener Kontext (eigene Cookies),
höchstens drei. 10 Minuten nichts getan → Sitzung zu; keine mehr → Prozess
beendet. `core/werkzeug_browser.py` hat die Einträge und Fragen (hinten ans
Register), `core/ki_browser.py` die Ausführer und die Textform.

**Werkzeuge** (nur gross, ~700 Zeichen, eigener Deckel < 800 in
`tests/test_profil.py`; die Anleitung steht im Skill `browser`):

| Werkzeug | tut |
|---|---|
| `browser_open(url)` | Seite laden → Titel, Adresse, Text (bis 4.000 Zeichen, sonst „weiter mit browser_read(ab=…)"), nummerierte Liste (Links, Knöpfe, Felder, Auswahlen; höchstens 60, Rest per `browser_find`) — seit 09.10. kürzer (Kosten, s. u. „Eindampfen") |
| `browser_click(nr)` | Element klicken (auch Skript-Bäume ohne Navigation), danach wie open |
| `browser_type(nr, text, enter)` | ins Feld tippen bzw. in einer Auswahl wählen; nachgelesen, was drinsteht; `enter` schickt ab |
| `browser_find(text)` | Elemente nach Text, mit Nummern |
| `browser_read(ab)` | weiterer Seitentext |
| `browser_back`, `browser_close` | zurück, schließen |
| `browser_screenshot(titel)` | PNG der Seite in die Ablage (`schreibt`, nachgelesen) — **für Sasha**: Bilder erreichen die Cloud nur als Anhang einer Nachricht von Sasha, nicht aus einem Werkzeug-Ergebnis, also sieht die KI es nicht und sagt das |

**Eindampfen (2026-10-09, Kosten):** ein LSF-Durchklicken kostete ~1 €, weil
jede Runde den ganzen Zug neu schickt. Ist im laufenden Zug eine neuere Seite
geladen (open/click/type mit Enter/back), ersetzt die Schleife ältere
Browser-Ergebnisse DIESES Zugs durch eine Zeile „[Seite „Titel“ Adresse —
gelesen, ersetzt durch spätere Seite]" (`werkzeug_schleife._seiten_eindampfen`,
`ki_browser.eindampfen`, Adapter-Methode `ergebnis_eindampfen` in beiden
Wegen). Der Prompt-Cache-Anfang bleibt: fester Kopf und Verlauf bis zu
Sashas Nachricht (Breakpoint vor dem Umschlag) werden nicht berührt —
`tool_result` gibt es nur im laufenden Zug. Test: 10 Seiten in einem Zug
gehen mit ~33 % der Zeichen raus (`tests/test_ehrlichkeit_runden.py`).

**Rahmen:** alle Rahmen einer Seite werden gelesen (Text mit Kopf „Rahmen:
…"), die Nummern laufen über alle Rahmen durch.

**Erlaubnis:** einmal je **Host** und Gespräch. Die Regel (`erlaubnis=f(args)`)
fragt nur, wenn der Host noch nicht erlaubt ist; das Ja ist „nur dieses mal"
(`nur_einmal`), denn „für dieses Gespräch" des Gates gilt pro Werkzeug — nach
einem Ja zu einer Seite wäre jede andere frei gewesen. Gemerkt wird der Host
in `browser_sitzung` (nur im Arbeitsspeicher), und zwar vom Ausführer: der
läuft nur nach einem Ja. Klicks und Tippen auf erlaubten Hosts sind frei; ein
Link zu einem anderen Host fragt; ein Knopf eines Formulars mit Passwortfeld
(und Enter darin) fragt immer.

**Sicherheit:**
- nur http/https; nie das eigene Netz (localhost, 10./172.16./192.168.,
  `.local`, IPv6 lokal; Namen werden aufgelöst) — außer Einstellung
  `browser_lokal_erlaubt` (nur für Tests mit eigenem Server);
- jede Anfrage der Seite läuft durch einen Abfang-Haken: Seiten (auch in
  Rahmen) nur von erlaubten Hosts; Bilder/Skripte von anderswo ja, aus dem
  eigenen Netz nie. **Weiterleitungen** holt der Haken selbst, ohne ihnen zu
  folgen, und prüft das Ziel — Playwright ruft ihn nur für die erste Adresse
  einer Weiterleitung auf, so käme eine erlaubte Seite per 302 an localhost
  vorbei. Erlaubtes Ziel → kleine Zwischenseite, die es neu lädt (geht dann
  wieder durch den Haken). Fremder Host → `B-ANDERE-SEITE`, nichts geladen;
- keine Downloads (Dateien statt Seiten werden gar nicht erst an den Browser
  gegeben → `B-DOWNLOAD`, Hinweis auf `fetch_document`), keine Service-Worker;
- 20 s je Schritt (`B-ZEIT`);
- JavaScript nur das der Seite; unser eigenes Skript (Liste, Text) ist fest
  im Code, aus dem Text der KI wird nie etwas ausgeführt;
- **Seiteninhalt ist Daten:** jedes Ergebnis trägt den Hinweis, dass
  Anweisungen auf der Seite nicht befolgt werden (Prompt-Injection);
- **Passwörter tippt die KI nicht** (`B-PASSWORT`): die Argumente eines
  Werkzeugs stehen im Verlauf, im Log und bei der Cloud. Anmelden über den
  Browser der KI geht deshalb (noch) nicht.
- Chromium startet erst mit seiner eigenen Abschottung; erlaubt das System
  die nicht, ohne (Zeile im Log).

**Fehlt der Browser** (Paket oder Chromium, z. B. auf dem Pi): Abbruch
`B-NICHT-EINGERICHTET` mit „Browser nicht eingerichtet: … Bis dahin fetch_url
nehmen" — nichts stürzt. Einrichten: [../betrieb/ki_browser.md](../betrieb/ki_browser.md).

**Tests:** `tests/test_browser.py` — ohne Chromium (Adressen, Erlaubnis je
Host/Gespräch, Host-Wechsel fragt neu, Nein öffnet nichts, Passwort, Form des
Ergebnisses, Bild in der Ablage per Attrappe, „nicht eingerichtet") und mit
echtem Chromium gegen einen eigenen Server auf 127.0.0.1 (nachgebauter
LSF-Baum mit Skript-Ästen, Rahmen, Formular mit Auswahl, Anmeldeformular,
Weiterleitung gleicher/anderer Host/eigenes Netz, Download, Bild,
Leerlauf). „localhost" und „127.0.0.1" sind dabei zwei Hosts. Fehlt Chromium,
wird der zweite Teil mit Meldung übersprungen. `tests/conftest.py` setzt
`PLAYWRIGHT_BROWSERS_PATH` auf das echte `~/.cache/ms-playwright`, weil HOME
und XDG_CACHE_HOME im Testlauf umgebogen sind.

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
  Treffer ein **Inline-Event** (`dict {"ascii","name"}`); `ui/routen/ki.py` macht
  daraus ein SSE-Event `ascii`. Der bereinigte Text (ohne Marker) wird
  gesprochen/gespeichert. Tutor-Modus kennt die Marker NICHT. Frontend:
  siehe „ASCII-Kern / Bild-Marker" in [memory/system/dashboard.md](../system/dashboard.md).
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
idempotent, hängt in `graph.einmal_seeden` → self-healing bei jedem Boot).

### Knopf-Dialog: Auto-Gate + `frage_knopf`

Das Dashboard kann die Konsolen-Eingabe gegen **2–4 Knöpfe** tauschen
(navigierbar per Pfeiltasten + Enter, Kiosk ohne Maus). Zwei Auslöser, ein
geteilter Mechanismus (blockierender `state.wait_permission`):

**(A) Auto-Gate für sensible Tools** — bestätigungspflichtige Tools
(Feld `erlaubnis` im Werkzeug-Register, z. B. die Kalender-Schreiber
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
   Check `erlaubnis.braucht_erlaubnis(name, args)`; `erlaubnis.frage(name,
   args)` baut die Frage („Soll ich »Zahnarzt« am … eintragen?"), Optionen =
   Default Ja/Nein. **`frage_knopf` (B):** eigener Branch baut Frage + Optionen
   aus den Call-Args (sanitisiert: ≥2, max 4). Beide rufen
   `state.request_permission(options, timeout_default)`, yielden ein
   **permission-Event** (`{"permission": {"frage", "optionen"}}`) und
   **blockieren** in `state.wait_permission()`.
2. `ui/routen/ki.py` macht ein SSE `permission` daraus; das Frontend zeigt die Frage als
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
`frage_knopf` `None` → Ergebnis `[ergebnis: keine_antwort]` (seit 2026-10-08,
s. „Belegt oder gesagt"). Log: `AI → ERLAUBNIS?`/`FRAGE …`
bzw. `AI ← ERLAUBNIS:`/`WAHL: …`. Frontend-Details (perm-bar, N-Knopf-Nav):
[memory/system/dashboard.md](../system/dashboard.md). Tutor-Modus: beides aus (fremdes Tool-Set). Neues
Tool gaten = `erlaubnis=` + `frage=` + `alltag=` in seinem Eintrag im Werkzeug-Register.

#### Geltungsbereiche: einmal / dieses Gespräch / immer (seit 2026-10-07)

Sasha: „beides einstellbar machen" (wie bei Claude Code). Die Gate-Frage hat
seitdem Knöpfe statt Ja/Nein: **„ja, nur dieses mal"**, **„ja, für dieses
gespräch"**, **„ja, immer"**, **„nein"** (das permission-Event trägt
`optionen`, `erlaubnis: true` und `geltung: [einmal, gespraech, immer,
nein]`; j = erster Ja-Knopf, n/Esc = nein wie bisher). Logik in
`core/erlaubnis.py` (`optionen`, `deuten`, `vorab`, `merken`,
`zuruecknehmen`), aufgerufen in `werkzeug_schleife._ask_permission`:

- **einmal** — das alte Ja. Ein Client, der nur „ja" schickt, bekommt das
  (`/api/permission_answer` übersetzt).
- **für dieses Gespräch** — nur im Arbeitsspeicher, an die Gesprächs-id des
  Zugs (`core/zug.py`) gebunden. Aufgehoben, sobald ein anderes Gespräch
  dran ist: `erlaubnis.gespraech_beginnt(gid)` in `/api/chat`,
  `/api/gespraeche` (neu), `/api/gespraeche/aktiv`, `/api/chat/clear`. Ohne
  Gespräch (Erinnerungen vom Takt) kein Knopf dafür. Neustart = weg.
- **immer** — `ai_config` Schlüssel `immer_erlaubt` (Liste kanonischer
  Namen, `data/ai_config.json`, synct mit den anderen Einstellungen).
  Zurücknehmen: `/erlaubnis` im Chat (`GET /api/erlaubnis`,
  `POST /api/erlaubnis/zuruecknehmen`).
- **Kein „immer"** (Register `immer_erlaubbar=False`): Kernakten
  (`write_note` auf Hausregeln/Steckbrief/Ziele — steuern die KI auf Dauer),
  alles was löscht oder überschreibt (`delete_calendar_entry`,
  `edit_calendar_routine`, `rewrite_note`, `edit_skill`, `fetch_document`
  bei gleichem Namen) und `save_from_sandbox` (nur auf Sashas Initiative).
  Auch beim Prüfen: steht so ein Werkzeug von Hand in der Liste, wird
  trotzdem gefragt.
- **Nur „einmal"** (Register `nur_einmal(args)`): `run_code` über 120 s.
- Pro Werkzeug, nicht pro Argument („run_code immer" = jedes Programm bis
  2 Minuten). Erlaubt ohne Frage steht als `AI ✓ ERLAUBT (immer|gespraech)`
  im Log.

`save_memory` ist mit dem Legacy-Pfad rausgeflogen – der Graph-Extraktor
läuft eh nach jedem Turn automatisch. Kalender-Tools (`read_calendar`,
`add_entry`, `add_routine`) kommen mit dem Kalender-System (siehe
[memory/werkzeuge/kalender_system.md](../werkzeuge/kalender_system.md)).

**Sicherheitsnetz:** `chat_stream` hat ein hartes `max_rounds = 5` für
die Tool-Loop – verhindert Endlosschleifen bei kaputten Tool-Calls.

**Streaming-Detail:** Tool-Calls kommen im **letzten** Streaming-Chunk
(`done=true`) im Feld `tool_calls`. Heißt: erst auf das Ende des Streams
warten, dann Tools auflösen.

## Wie ihre Antwort im Terminal ankommt

Die KI schreibt Markdown — der Prompt erlaubt ihr Listen ausdrücklich,
Überschriften benutzt sie von selbst. Gezeichnet wurde bis 18.08.2026 der
**Rohtext**: im KI-Kasten stand `**fett**` und `## Titel` als Zeichen.

`tui/ansichten/text.py::md_zeilen(text, breite)` liefert
`[(zeile, stil)]` mit `stil` aus `{"", "kopf", "code", "liste"}`. Der Stil
ist absichtlich ein **Wort** und keine curses-Konstante: so bleibt die
Funktion rein und ohne Terminal testbar, und über Farben entscheidet allein
der Zeichner (`Chat.draw_ai` in `tui/ansichten/chat.py`). Sie liegt auf Modulebene und fällt damit unter
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

Das (geparkte) Browser-Dashboard rendert nichts; dort ist gar kein
Markdown-Renderer eingebunden.

## System-Prompt-Komposition

Reihenfolge im System-Prompt (siehe `_PROMPT_ORDER` in `core/ki_prompt.py`):
**erst alles Statische, dann alles, was sich pro Turn ändert.** Zwei Gründe
für diesen Schnitt, ein Handgriff — Prompt-Cache (ein Treffer braucht ein
byte-identisches Präfix, und der Jetzt-Block enthält die Uhrzeit) und Recency
(was zuletzt steht, sitzt am dichtesten an der User-Message).

Die Liste beschreibt den **lokalen** Pfad (`ai.chat_stream`, Schiene `klein`;
zwischen 2 und 3 stehen dort noch Antwort-Suffix, Bild-Marker, Dashboard-Block
und `kalender.imprint_for_prompt()`). Der Cloud-Pfad baut seinen Kopf in
`cloud._static_system` (Schiene `gross` + `gedaechtnis.kopf_block()` +
Skill-Liste + Projekt-Block, wenn das Gespräch zu einem Projekt gehört +
Imprint) und hängt das Wechselnde (4–6) hinten an die neueste User-Nachricht,
siehe „Prompt-Cache: statisch vorn, Wechselndes ganz hinten".

1. **`_SYSTEM_PROMPT`** – Persona (entspannt, direkt, deutsch).
2. **`_CAPABILITIES_PROMPT`** – Meta-Regeln: nicht lügen über Memory;
   nicht erfinden über Sasha; **Subjekt-Grenze** (Sashas Gefühle/Zustände
   NIE als eigene ausgeben → Anti-Identity-Bleed, mit konkretem Beispiel);
   nicht erfinden über eigene Fähigkeiten (was unter „Das kannst DU NICHT"
   steht, nie behaupten zu können); lateinische Schrift; reale Wörter.
   Bei jedem Turn injiziert.
3. **`graph.context_for_query(user_query)`** – **per Default AUS seit
   2026-08-18** (nur mit `ZENTRALE_GRAPH_KONTEXT=1`, `ai.GRAPH_KONTEXT`); der
   Block fehlt dann ganz. Wenn an: aktiviertes Wissen aus
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
   Client → `/api/chat` mit `via_mic: true` → `chat_stream(via_mic=True)`.

> **Solange der Graph-Kontext aus ist, gilt der folgende Absatz nicht:** die
> Seed-Knoten werden zwar angelegt, kommen aber nicht in den Prompt. Seit
> 2026-10-06 bekommt die `klein`-Schiene dann auch die passende Fassung der
> Meta-Regeln (`_META_REGELN_OHNE_GRAPH`, gewählt über `klein.system(graph=…)`
> aus `ki_prompt.GRAPH_KONTEXT`): ohne Verweis auf den Wissens-Block und ohne
> die frühere Erlaubnis, „notiert, läuft in den Graphen" zu sagen.

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

### Eine Werkzeug-Schleife – `core/werkzeug_schleife.py` (seit 10/2026)

Bis Oktober 2026 stand die Tool-Schleife **dreimal** da (lokal, Anthropic,
OpenAI). Die lokale Kopie war auseinandergelaufen: keine `werkzeug`-Events,
ein krachendes Tool riss den Zug ab, eigener Ablehnungstext. Jetzt gibt es
eine Schleife (`laufen`), die Runden, Gate, terminale Tools (`antwort`,
`read_news`, `ask_choice`), Antwort und Fehler besitzt, und **drei Adapter**,
die nur ihren Dialekt kennen:

| Adapter | Datei | Eigenheit |
|---|---|---|
| `_OllamaAdapter` | `core/ai.py` | think aus nach dem ersten Tool (qwen-Template-Bug) |
| `_AnthropicAdapter` | `core/cloud.py` | `tool_result`-Blöcke in EINER user-Message, wandernder Cache-Breakpoint |
| `_OpenAIAdapter` | `core/cloud_openai.py` | Tool-Calls stückweise aus dem Stream, `role: "tool"` |

Jeder Adapter hat `runde()` (ein Modell-Aufruf → `Runde(text, calls)`),
`assistent_anhaengen()` und `ergebnisse_anhaengen()`. Den Prompt baut weiter
jeder Weg selbst. Was ein Tool-Call **bedeutet**, steht genau einmal, in
`werkzeug_schleife.run_tool()`.

**Sonderwege nach Register (seit 2026-10-07, Phase 3).** `run_tool` nennt
keinen Werkzeug-Namen mehr: `in_der_schleife` → der Weg aus
`werkzeug_schleife.SELBST` (`antwort` = Text ist die Antwort, `ask_choice` =
Knopf-Dialog); `terminal` mit Ausführer → `_terminal_ausgeben` (heute nur
`read_news`: `cinema`-Event, Kopf „Sendung (Stand …)" weg, direkt als
Antwort, nicht gemerkt). Im Tutor greift beides nicht.
`tests/test_werkzeug_schleife_register.py` hält Register und `SELBST`
deckungsgleich und beweist gleiches Verhalten (lief auch gegen den alten
Code grün).

**Fehler sind keine Antwort.** API-Fehler, Cloud-Ablehnung (`refusal`) und
die Rundengrenze kommen als `{"fehler": …}`. `ui/routen/ki.py` reicht das als SSE
`fehler` an die TUI und schreibt es NICHT als ihren Text ins Gespräch.
Vorher stand `[Cloud-Fehler: …]` als KI-Antwort im Verlauf, und der Takt
konnte es sogar als „Initiative“ melden. Seit 2026-10-09 wird der
abgebrochene Zug trotzdem gespeichert — als Antwort mit Feld `fehler`, den
Werkzeugen und dem Ablauf, Text meist leer (bis dahin war er ganz weg, und
die KI wusste im nächsten Zug nichts davon). `gespraeche.fehler_hinweis`
gibt ihn ihr im Verlauf als „[System, nicht deine Worte: Dein letzter Zug
brach ab — <Meldung>. Bis dahin gelaufen: …]" (höchstens 12 Schritte, Args
gekürzt); der feste Kopf bleibt (Prompt-Cache). Gestoppt ohne Text zählt
genauso („von Sasha gestoppt"). Die TUI zeigt „✗ abgebrochen: …" mit
„retry" daran (SSE `{antwort, abbruch}`).

**Eine Regel für alle (Sasha, 05.10.2026):** Die Rundengrenze hängt am
Modell, nicht am Weg (`ai_backends.runden_grenze`, Standard 100 (bis 09.10.: 8), pro Modell in
`runden_grenzen` der Config kleiner). Der Ablehnungstext verlangt überall die
Richtigstellung, falls sie im selben Zug schon notiert hat, es sei passiert —
vorher bekam nur der lokale Weg diesen Satz.

**Stoppen (seit 2026-10-07).** `laufen(…, abbruch=)` nimmt ein
`threading.Event` und prüft es vor jeder Runde und vor jedem Werkzeug; die
Adapter prüfen es bei jedem Stück ihres Stroms, schließen ihn, buchen, was
der Anbieter bis dahin gemeldet hat, und werfen `Gestoppt(text)`. Heraus
kommt der halbe Text (roh, nicht gemerkt) und `{"gestoppt": True}`. Das
Event legt `/api/chat` pro Zug an (`state.chat_zug_beginnen`),
`/api/chat/stop` setzt es. Takt und Tutor übergeben keins und sind nicht
stoppbar. Ausführlich: [claude_web_plan.md](claude_web_plan.md) Abschnitt 7.

Der Tutor hat seit 2026-10-08 keine eigenen Schleifen mehr: er fährt über
`kern.fahrzeug()`/`kern.fahren()` dieselben Wege (`tutor/anbieter.py`,
[../tutor/INDEX.md](../tutor/INDEX.md)).

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
  Seit 2026-10-08 in einem festen Umschlag `<kontext_automatisch>…`, der sagt,
  dass Sasha den Block nicht geschrieben hat — ohne ihn hielt die KI im
  Prüfstand (f01 Zug 3) das „## Jetzt" für etwas, das Sasha geschickt hatte.
* **Werkzeug-Spur im Verlauf** (2026-10-09, nur Cloud): an jede frühere
  Antwort hängt `anhang.verlauf_einsetzen` eine Zeile mit den schreibenden
  (und schiefgegangenen) Werkzeugen des Zugs, Status und Ergebnis-Anfang
  (`werkzeug_befund.spur_zeile`, Daten aus `gespraeche` → `werkzeuge`, gemerkt
  in `ui/routen/ki._werkzeug_merken`). Vorher sah die KI nur ihren Text: hatte
  der ein Löschen nicht erwähnt, behauptete sie im nächsten Zug, da sei nie
  etwas gewesen. Aus Gespeichertem gebaut → gleiche Bytes, Cache bleibt.
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
2.500) und die Länge einer einzelnen Verlauf-Nachricht — `cloud.kappen()`
kürzt in der Mitte, deterministisch, damit der Präfix byte-stabil bleibt, mit
dem Vermerk „[… N Zeichen gekürzt …]" (seit 2026-10-07; vorher nur
„[gekürzt]"). Seit 2026-10-07 zwei Grenzen über `ai_config.setting`:
`nutzer_msg_chars` (Sashas eigene Nachrichten, Standard **20.000** — sie
kommen vollständig an; `/api/chat` lehnt Längeres mit Klartext ab und
verweist auf `/anhang`) und `cloud_msg_chars` (alles andere: alte
KI-Antworten, News-Sendungen; Standard 4.000 — die reiten 50 Züge mit, und
Anfang + Fazit reichen der KI). Beide Dialekte (Anthropic, OpenAI-kompatibel)
nutzen dieselbe Funktion. Lokal (Ollama) wird nicht gekappt; dort begrenzt
`num_ctx` (8.192 Token) — eine 20.000-Zeichen-Nachricht passt knapp, mit
langem Verlauf schneidet Ollama vorne ab. Das Nachrichten-FENSTER wird bewusst nicht
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
| `profil/__init__.py` | Registry, Auswahl, Durchreiche der Alias-Tabelle |

Die Werkzeug-Liste jeder Schiene kommt seit 2026-10-07 aus dem
Werkzeug-Register (siehe „Das Werkzeug-Register" oben); die Schiene sagt nur
noch `werkzeug_register.schema(NAME)`.

* **Auswahl:** lokal → `klein`, cloud → `gross`. Übersteuerbar per
  `chat_profil` in `data/ai_config.json` bzw. `ZENTRALE_CHAT_PROFIL`.
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
Gate, SSE bis in die TUI sind providerunabhängig. Ein zweiter echter
Provider ist der ehrlichere Test der Naht als ein zweiter Mock — erst wenn ein
fremdes Modell durch dieselbe Naht passt, ist es wirklich eine.

Was er **nicht** kann: `cache_control` (Anthropic-spezifisch; DashScope cacht
implizit und ohne messbares Signal), `thinking`/`effort`, `is_error` auf
Tool-Ergebnissen. `temperature` ist hier dagegen erlaubt und wird genutzt.
Liefert ein Modell `reasoning_content`, wird es als `reflect`-Event gespiegelt.

**Beide Provider teilen sich denselben Cloud-Graphen.** Die Grenze verläuft
zwischen „im Haus" und „draußen", nicht zwischen zwei Anbietern.

### Der Nutzer im Prompt — `core/nutzer_angaben.py` (seit 2026-10-09)

Leerer Erststart (Produkt-Inventur Punkt 1): Persona, Antwortverhalten,
Meta-Regeln (`core/profil/klein.py`, `gross.py`) und die Bausteine Jetzt-Block
und Offene Erinnerungen (`core/ki_prompt.py`) tragen Platzhalter statt
„Sasha": `{nutzer}`, `{nutzers}` (Genitiv), `{NUTZER}`/`{NUTZERS}`, dazu die
Pronomen `{er}` `{Er}` `{ihn}` `{ihm}` `{sein}` `{seine}` `{seinen}`
`{seinem}` `{seiner}` und `{ein_muendiger_erwachsener}`. Gefüllt aus den
Einstellungen `nutzer_name` (Standard „Sasha") und `nutzer_pronomen` („er",
Standard — so sprachen die Prompts von Sasha; oder „sie"). Mit den
Standardwerten ist der Prompt byte-gleich wie vorher (Schnappschuss
`tests/fixtures/prompt_schnappschuss.json`, `tests/test_prompt_nutzer.py`).

Die Vorlagen heißen `_…_VORLAGE`; die alten Namen (`_SYSTEM_PROMPT` …) sind
beim Import gefüllt (ai.*, bench-Skripte), `system()` füllt bei jedem Aufruf
neu — pro Installation stabil, der Cache bleibt warm. Bewusst unverändert:
„meint sie" (Dashboard-Sicht, Alarm-Block) meinte schon vorher den Nutzer.

**Noch fest auf Sasha (offen):** Werkzeug-Beschreibungen und Fragen
(`core/werkzeug_*.py`), Fehlercode-Texte (`core/fehlercodes.py`),
Werkzeug-Ergebnisse (z. B. `input_aufraeumen`, `ehrlichkeit`), der
Gedächtnis-Kopf. Persönliche Fakten im Prompt: „Linux-PC, Wand-Monitor
(Pi 3)" und das Turn-Beispiel (klein) beschreiben Sashas Geräte — gehört in
eine Einstellung oder ins Gedächtnis.

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

### Lokal-Regel (seit 2026-08-15, Schalter seit 2026-10-04)

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

### Modell-Parameter (Stand 2026-10-04, aus dem Code)

- **Modell:** `cloud._model()` = `ai_backends.chat_model("claude")` →
  `data/ai_config.json` `chat_models.claude` → Code-Default `claude-sonnet-5`
  (`providers.py`). Umstellen per Config (`set_chat_model`); eine Env
  dafür gibt es nicht (das frühere `ZENTRALE_CLOUD_MODEL` griff nie und ist
  seit 10/2026 raus).
- **Rundengrenze:** `ai_backends.runden_grenze(modell)` — `runden_grenzen`
  in der Config (`{"qwen3.5:9b": 5}`), sonst 8. Gilt für alle Wege.
- **Denk-Tiefe:** `ai_backends.chat_effort()`, Default `low` —
  `ZENTRALE_CHAT_EFFORT` oder `chat_effort` in der Config.
- `max_tokens 16000` (`ZENTRALE_CLOUD_MAX_TOKENS`).
- `thinking: adaptive` mit `display: summarized`, nur für Modelle in
  `cloud._DENKT_ADAPTIV` → die Denk-Tokens werden live als `reflect`-Event in
  die TUI gespiegelt, genau wie Ollamas `thinking`-Feld.

(Bis 08/2026 stand hier `claude-opus-5` / `effort: medium` /
`ZENTRALE_CLOUD_EFFORT` — die Env-Variable gibt es nicht mehr.)

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

## Tool-Calls und Denken stehen IM CHAT (seit 20.08.2026)

Sasha nach einem Turn, den niemand nachvollziehen konnte:

> *„machen wir im normalen chat einfach die tool calls usw details was sie macht
> wie tool call, thinking, usw einfach alle transparent und sichtbar, so wie man
> es bei dir claude sieht! … weil keine ahnung was sie hier fabriziert hat."*

Der Anlass: sie schrieb dieselbe Idee **zweimal** weg — erst als sauberen
Katalog-Eintrag, dann als Prosa in dieselbe Katalogdatei — und sagte beide Male
nur „steht drin" bzw. „jetzt steht's wirklich drin". Von außen sah das aus wie
eine Lüge beim ersten Mal. Ein sichtbares `write_note(name=ideen, text=…)` hätte
die Frage in einer Zeile beantwortet.

- **Emittiert** wird in `werkzeug_schleife.run_tool` — der einzigen Stelle,
  durch die **alle drei** Wege gehen (lokal erst seit 10/2026). Drei Phasen:
  `start` (Name + Argumente), `fertig` (Ergebnis), `fehler`. Mehrfach
  gepflegt hieße, dass die Anzeige auf einer Schiene irgendwann fehlt.
- **Durchgereicht** als eigenes SSE-Event `werkzeug` (`ui/routen/ki.py`), kein
  Antworttext — es landet also nicht im gespeicherten Verlauf.
- **Gezeigt** in der TUI als eigene Zeilen im Chat: `⚙ write_note(name=ideen,
  …)` und darunter `↳ Notiert in kataloge/ideen.` Zurückgenommen in der Farbe,
  ein Werkzeug-**Fehler** dagegen in Warnfarbe — das ist der Fall, in dem sie
  hinterher behauptet, es habe geklappt.
- **Denken** wird gesammelt und in den Verlauf gelegt, sobald etwas anderes
  passiert (ein Werkzeug, Text, eine Rückfrage). Erst am Turn-Ende anzuhängen
  hieße, den Gedankengang hinter die Taten zu stellen, die aus ihm folgten.

Die `werkzeug`-Ereignisse sind ein reiner **Anzeige-Kanal**: die Tests des
Tool-Protokolls (`test_cloud_loop.py`, `test_cloud_openai.py`) filtern sie in
ihrem `_lauf()` heraus, geprüft werden sie in `test_transparenz.py`.

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
  nicht aus `tutor/` importieren. (Die Anbieter-Liste dagegen ist seit
  2026-10-08 nur noch eine: `core/providers.py`.)

⚠ Hier geht der komplette Prompt raus, inklusive Graph-Kontext — also Sashas
Zustände und Erlebnisse. So privat wie der Graph selbst.

## Ablauf-Protokoll — „trace ›" unter jeder Antwort (seit 2026-10-09)

Sasha: wie bei „Used …" nicht nur sehen, welches Werkzeug lief, sondern was
es zurückgab und wie die Antwort darauf weiterging — der ganze Zug von seiner
Nachricht bis zur fertigen Antwort, in Reihenfolge, ohne Auslassungen. Die
Devtools (oben) zeigen das live; das Protokoll bleibt mit der Antwort
gespeichert und ist in der TUI nachzulesen.

- **Nur mitschreiben** (`core/zug_ablauf.py`, Schicht 1, contextvar wie
  `core/zug.py`). Nichts davon ändert, was ans Modell geht — der Prompt-Cache
  bleibt, wie er ist (`tests/test_zug_ablauf.py` vergleicht den Request mit
  und ohne Protokoll byte für byte).
- **Nur Cloud, Schiene gross.** `/api/chat` öffnet das Protokoll, wenn die
  Cloud denkt; scharf wird es erst, wenn der Weg `system()` meldet
  (`cloud.ablauf_melden`, beide Cloud-Wege, nur gross). Lokal/klein bleibt
  alles, wie es gemessen ist — dort gibt es kein `ablauf`.
- **Wer meldet was:** `cloud.ablauf_melden` → `system` (nur Fingerabdruck
  sha256[:16] + Länge, der feste Kopf ist jeden Zug derselbe) und `kontext`
  (der Umschlag `<kontext_automatisch>` voll: Jetzt, Alarme, offene Zusagen;
  dazu Titel/Größe der Anhänge der neuesten Nachricht). `werkzeug_schleife.laufen`
  → `text` (Vorgeplänkel vor/zwischen Werkzeugen, das der Chat nicht zeigt),
  `werkzeug` (Name, Argumente, Ergebnis **wie an die Schleife zurück**, also
  mit Kopfzeile `[ergebnis: …]`, Status, Dauer), `pruefung` (Befunde, Hinweis
  an die KI, die erste verworfene Antwort — danach folgt die zweite),
  `fehler`/`gestoppt`. `_ask_permission`/`_ask_buttons` → `frage` (Frage,
  Knöpfe, Sashas Antwort; „schon erlaubt (…)" bei Geltungsbereich).
  Die Buchungen (`_log_usage` & Co.) zählen in `kosten` mit. Die Route hängt
  zum Schluss `antwort` (wie gespeichert) und `kosten` an.
- **Denken** bleibt, wie es war (eigenes Feld `denken`), nicht im Ablauf.
- **Obergrenze** 50.000 Zeichen je Eintrag (`EINTRAG_MAX`): das längste Feld
  wird hinten gekürzt, mit Vermerk und `gekuerzt: <Zeichen>`. Sonst wird
  nichts gekürzt (anders als `werkzeuge[].ergebnis`, 8.000).
- **Gespeichert** als Feld `ablauf` der Antwort (`core/gespraeche.py`).
  `/api/chat/history` und `GET /api/gespraeche/<id>` liefern nur
  `ablauf_n`; den Inhalt `GET /api/gespraeche/<id>/ablauf/<nachricht>`
  (`letzte` = die letzte Antwort mit Protokoll). SSE: nach dem Speichern
  `{antwort: id, ablauf: n}`.
- **Export:** `/trace` im Chat → `POST …/ablauf/letzte/ablage` legt den Ablauf
  als Textdatei in die Ablage (Herkunft `ablauf`, bis 2.000.000 Zeichen,
  `zug_ablauf.als_text`).
- Fehlt: ein Zug, der an einem Fehler ohne jeden Text scheitert, wird nicht
  gespeichert (wie bisher) — sein Protokoll also auch nicht.

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
`push_internet_log`), die archivierte Browser-Front (`memory/archive/browser_front.md`, `#term-net`, Box »outbound · tripwire«; damals `index.html` mit `.terminal-row` +
`.terminal-net` mit orangefarbenem Akzent).

Tests: `scripts/test_net_internet.py` (48 Cases, untracked).

## Chat-Modus

- KI-Chat mit qwen3.5:9b (oder via `OLLAMA_MODEL`), tokenweise gestreamt.
- KI hat Zugriff auf Whitelist-Dateien + Graph-Memory.
- Slash-Befehle im TUI-Chat (seit 2026-10-07, `tui/ansichten/chat_befehle.py`):
  `/neu` (neues Gespräch, früher `/clear` — geht weiter), `/modell [name]`,
  `/anbieter [name|auto]`, `/effort [stufe]`, `/budget [euro|aus]`,
  `/lokal` `/cloud` `/auto`, `/hilfe`, `/erlaubnis` (was ohne Frage
  erlaubt ist, zurücknehmen); seit Phase 2 auch `/liste`,
  `/titel [text]`, `/archiv`, `/wiederholen`, `/bearbeiten`, `/denken`. `//` am Anfang = wörtlicher
  Schrägstrich. Die Einstellungen laufen über `/api/ai/einstellungen`
  (`core/ki_einstellungen.py`). `/modell` zeigt seit 2026-10-07 **alle**
  Chat-Modelle jedes Anbieters mit Schlüssel (`core/modell_liste.py`: vom
  Anbieter geholt — Anthropic `GET /v1/models`, sonst `GET {base_url}/models`
  —, 24 h gecacht in `~/.cache/zentrale/modelle.json` pro Rechner, Fehler
  10 min gemerkt, Rückfall auf `providers.py`; Embedding/Audio/Bild/
  Moderation per Wortliste im Namen herausgefiltert); in der Auswahl filtert
  Tippen. Budget: 0–100 € im Monat (Sasha).
  (`/memory` und `/forget N` sind mit dem Legacy-LTM-Pfad entfallen.)
- ESC – stoppt eine laufende Antwort, sonst zurück zum Haupt-Dashboard.
- **Gespräche** (seit 2026-10-07, Claude-Web-Plan Phase 2): der Verlauf
  lebt nicht mehr im RAM (`state._chat_history` ist weg), sondern in
  `core/gespraeche.py` — viele Gespräche, Ordner pro Gespräch, Datei pro
  Rechner, synchron auf allen Knoten. An `kern.chat` gehen die letzten 50
  Nachrichten des aktiven Gesprächs; die Antwort wird mit allem Denken des
  Zugs, den Werkzeugen, Anbieter und Modell gespeichert. Kalender-
  Erinnerungen landen im eigenen Gespräch „Erinnerungen". Titel: erst die
  ersten Wörter, dann das billige Modell (`core/billig.py`). Alles Weitere:
  [gespraeche.md](gespraeche.md).

## Bewertungen (seit 2026-10-08)

Unter jeder Antwort im TUI-Chat: „good · bad", optional mit Kommentar
(Bedienung: [../system/tui_bauplan.md](../system/tui_bauplan.md) „Bewerten").
**Wofür:** Sasha und Claude gehen sie gemeinsam durch, um Prompt (`profil/`),
Skills und Werkzeug-Beschreibungen zu verbessern — „bewertungen für uns um
unser eigenes system zu verbessern" (Sasha, 08.10.). Deshalb steht bei jeder
Bewertung, wer geantwortet hat (Anbieter, Modell) und welche Werkzeuge und
Skills die Antwort benutzt hat. **Sie gehen nirgendwohin raus:** kein
Anbieter bekommt sie, sie stehen in keinem Prompt, kein Werkzeug liest sie;
sie liegen nur in `data/rueckmeldungen/<rechner>.jsonl` (gitignored, in der
Datensicherung, synct wie die Gespräche — eine Datei pro Rechner, nur
anhängen, das letzte Ereignis je Antwort gilt). Speicher
`core/rueckmeldungen.py`, Routen `POST /api/rueckmeldung`,
`GET /api/rueckmeldungen` ([../system/api_endpoints.md](../system/api_endpoints.md)).

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
