# Konzept-Graph — Extraktor, Embeddings, Transkript (abgeschaltet)

**Stand 2026-10-14:** Der Konzept-Graph (`core/graph.py`) ist seit 2026-08-18
**abgeschaltet**: kein Kontext im Prompt (`ki_prompt.GRAPH_KONTEXT`, Env
`ZENTRALE_GRAPH_KONTEXT`), keine neuen Extraktionen
(`consolidation.GRAPH_EXTRAKTION`, Env `ZENTRALE_GRAPH_EXTRAKTION`); es läuft
nur noch der Identity-Seed. Das Gedächtnis ist das Datei-Gedächtnis
([gedaechtnis_dateien.md](../../ki/gedaechtnis_dateien.md)). Weiter in Gebrauch: die
Transkript-Schicht (`core/transkript.py`), die `search_chats` mitliest. Diese
Datei beschreibt, wie der Graph arbeitet, wenn man ihn wieder anschaltet.
Die Graph-Testskripte (Phase-G-Harness, Graph-Fallen der Live-Probe) liegen
seit 2026-10-14 im Archiv: [../archive/associative_graph/](README.md).

**Warum sie bleibt:** Die Entscheidungen hier — Erzähltag ist nicht
Ereignistag, verbinden statt verschmelzen, Vektorräume nie mischen, der lokale
Graph verlässt das Haus nie — gelten für jedes künftige Gedächtnis mit
Embeddings genauso. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

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
> Kontext in den Prompt (`ki_prompt.GRAPH_KONTEXT`) noch nimmt er neue Extraktionen auf
> (`consolidation.GRAPH_EXTRAKTION`) — beides per Env wieder einschaltbar. An
> seiner Stelle steht das Datei-Gedächtnis, siehe
> [gedaechtnis_dateien.md](../../ki/gedaechtnis_dateien.md). Der folgende Abschnitt
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
sie das Werkzeug `search_chats` mit ([werkzeuge.md](../../ki/werkzeuge.md), „Frühere Gespräche") —
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

## Memory unterwegs – zwei Embedder, zwei Extraktoren

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

## Historie

- **2026-05** — Legacy LTM/STM (`save_memory`, `/sleep`), Phasen A–F
  ([ki_memory_plan.md](../../ki/ki_memory_plan.md)).
- **2026-06-01** — bge-m3 auf die CPU (VRAM-Contention mit qwen).
- **2026-06-06** — Graph primary (Phase G), LTM/STM entfernt, Subjekt-Trennung.
- **2026-08** — Zeit in vier Auflösungen, wörtliche Einstiegspunkte, gedämpfte
  Anker, Embedder unabhängig vom Chat-Anbieter, Alias als Kante, Transkript-Schicht,
  zwei Embedder/Extraktoren für unterwegs.
- **2026-08-18** — abgeschaltet zugunsten des Datei-Gedächtnisses.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
- **2026-10-14** — Graph-Testskripte ins Archiv (`archive/associative_graph/`).
