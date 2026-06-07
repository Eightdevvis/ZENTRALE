# News-System – Persönliche Tagesschau (Baustein-Modell)

Periodisch gefetchte, KI-moderierte Weltpolitik-Sendung. Kern-Modul:
`core/news.py`. KI-Tool: `lies_news`. Eingeführt 2026-06-07.

## Idee

Weltpolitik aus vielen RSS-Quellen ziehen (**breit gestreut, inkl.
Staatsmedien** verschiedener Blöcke), zu **Themen-Bausteinen** bündeln,
und die lokale KI daraus eine **gesprochene Sendung** bauen lassen, die
dieselbe Story über mehrere Quellen **gegenüberstellt** ("wer behauptet
was"). Der Perspektiven-Kontrast ist der Sinn. Sashas eigene
zusammengeschnittene Tagesschau.

## Baustein-Modell (Sashas Lego-Wand)

**Ein Baustein (Stein) = ein Thema** + die beteiligten **Stimmen**
(Quellen mit ihren divergierenden Aussagen). Jeder Stein im Store trägt
Status-Aufkleber, aus denen sich die Feinheiten ergeben:

| Feld                | Rolle                                                  |
|---------------------|--------------------------------------------------------|
| `wichtigkeit`       | Basis-Gewicht 0-100 (LLM bewertet weltpol. Tragweite)  |
| `zuletzt_bewegt`    | wann zuletzt eine neue Stimme dazukam → Anker fürs Decay|
| `gesehen_von_sasha` | Haken, sobald in einer Sendung ausgeliefert            |
| `status`            | neu / aktualisiert / ruht / archiviert                 |
| `embedding`         | bge-m3-Vektor des Themas (fürs Cross-Poll-Matching)    |
| `stimmen[]`         | die Quellen-Meldungen (quelle, herkunft, titel, text, link, datum) |

Daraus folgt automatisch, was Sasha wollte:

- **Decay** (`_aktuelle_wichtigkeit`): Basis halbiert sich alle
  `HALBWERTSZEIT_H` (48 h) seit der letzten Bewegung. Leichte Steine
  (Kunstausstellung, Basis ~20) fallen schnell unter `ARCHIV_FLOOR` (8)
  → archiviert. Schwere (Annexion, Basis ~90) überleben tagelang → Sasha
  erfährt sie auch spät noch.
- **Keine Wiederholung**: Gesehene Steine kommen nur zurück, wenn sie
  sich **bewegt** haben (neue Stimme → `status=aktualisiert`, in der
  Sendung mit `[UPDATE]` markiert).
- **Sendung** = schwerste *ungesehene/bewegte* Steine zuerst, gedeckelt
  (`SENDUNG_MAX`=7, über `SENDUNG_MIN_WICHTIGKEIT`=15) → Aufmerksamkeit
  bleibt vorne.

## Pipeline (`core/news.py`)

```
collect()        Feeds holen (net.get) → parsen → putzen → dedup → Liste[dict]   (unverändert)
_cluster_poll()  Poll-Meldungen → LLM → Bausteine {thema, kategorie, wichtigkeit, stimmen}
_integriere()    je Baustein: per Embedding an bestehenden Stein andocken (merge) ODER neu
_decay_…()       Steine unter dem Boden archivieren
baue_sendung()   ungesehene/bewegte Steine wählen → LLM-Moderation → data/news_digest.json
wochenrueckblick(tage)  Steine der letzten N Tage (nach BASIS-Wichtigkeit, ohne Decay) → Rückblick
aktualisiere()   = ein Poll-Lauf: ankündigen → collect → cluster → integrate → decay → baue_sendung
lies(tage)       KI-Tool: tage=0 Tagessendung (markiert gesehen), tage>0 Wochenrückblick (markiert nichts)
start_fetcher()  Daemon-Thread: periodisch + laut angekündigt (aus main.py)
```

## Cross-Poll-Identität (hier verdient bge-m3 sein Geld)

Pro Poll clustert das **LLM** die frischen Meldungen (`_cluster_poll`,
JSON-Output, Item-Indizes → echte Stimmen, Müll-Indizes verworfen). Ob
ein neuer Baustein zu einer **bestehenden laufenden Story** gehört,
entscheidet **Python per Embedding** (`_integriere`): Thema einbetten
(`embeddings.embed_document`), Cosinus gegen alle aktiven Steine, über
`MATCH_THRESHOLD` (0.60) → mergen (Stimmen rein, Wichtigkeit = max, bei
echter neuer Stimme `zuletzt_bewegt` auffrischen). Sonst neuer Stein. So
wächst die Ukraine-Story über Polls zu EINEM Stein, statt jeden Poll neu
aufzutauchen. (Das LLM kann das nicht selbst, es kennt die alten Steine
nicht.)

## Graph-Kopplung: bewusst KEINE (separater Store + spätere Lese-Brücke)

News leben in **eigenem Store** (`data/news_stories.json`), **nicht** im
Konzept-Graphen. Begründung: der Graph speichert nur Sashas Realität,
kein Weltwissen — News reinzukippen würde ihn zumüllen und bei jedem Chat
mit-aktivieren (Spread). Entschieden mit Sasha 2026-06-07. Die
Personalisierung ("das kennst du schon") kommt **später als reine
LESE-Brücke** beim Sendung-Bauen (KI schaut lesend in den Graphen, baut
Brücken). Was Sasha wirklich aufgreift, landet eh über den
Konsolidierungs-Extraktor automatisch im Graphen.

## Quellen (`FEEDS`)

12 Feeds, davon 11 live (Tagesschau, DW, BBC, Guardian, France 24, NPR,
Al Jazeera, Times of Israel, Times of India, **CGTN/CN Staat**,
**TASS/RU Staat**). **RT** fällt auf Sashas Hotspot per DNS aus (EU-Block)
→ wird übersprungen. `herkunft` = Einordnungs-Kontext für die KI, keine
technische Angabe.

## Parser (robust, format-agnostisch)

`_parse_feed` sucht über den **Local-Name** des Tags: `<item>` (RSS
2.0/RDF) oder `<entry>` (Atom), egal welcher Namespace (`root.iter()` +
`_local()`). `_child_text` fällt für `<link>` aufs `href`-Attribut zurück
(Atom). HTML in Anrisstexten → `_strip_html` (Tags raus, Entities auf,
gekürzt). Getestet: 11/12 Feeds, alle Formate sauber geparst.

## Trigger + Transparenz

Periodischer Daemon-Thread (`start_fetcher`, aus `main.py` nach
`ai.warmup_async`), Intervall `NEWS_INTERVAL_MIN` (Default 180 min),
erster Lauf nach `NEWS_START_DELAY_S` (90 s). **Bewusst NICHT pro-Call
gegatet** wie `web_suche` — "periodisch, aber sichtbar": jeder Lauf
kündigt sich laut an (`push_log` + `push_internet_log` → orangenes
Internet-Panel). Der Fetcher **akkumuliert nur** in den Store; die
Sendung wird mitgebaut + gecacht, aber erst bei `lies()` als gesehen
markiert (Auslieferung = gesehen).

## Persistenz (zwei Dateien, beide auto-generiert, nicht committen)

- `data/news_stories.json` — der **Store**: `{stories[], naechste_id,
  letzte_sendung}`. Die Lego-Wand inkl. Embeddings + Status. Wächst/decayt
  über Polls.
- `data/news_digest.json` — die **zuletzt gebaute Sendung**:
  `{erstellt, text, story_ids}`. `lies()` liefert `text` und markiert die
  `story_ids` als gesehen.

## Tool `lies_news` (`core/ai.py`)

Read-only + lokal → **nicht** in `PERMISSION_REQUIRED_TOOLS`. Dispatch →
`news.lies(args.get("tage", 0))`. Optionaler Param **`tage`**:
- `0`/weglassen → **Tagessendung** (aktuelle Top-Themen). Liefert die Sendung
  **und markiert die Steine als gesehen** (→ nächster Poll lässt sie weg, außer
  sie bewegen sich). Nicht-blockierend: noch keine Sendung gebaut → async Lauf +
  "frag gleich nochmal". Zweiter Aufruf ohne Bewegung → "schon gehört".
- `7` (o.ä.) → **Wochenrückblick** ("was war diese Woche / seit ich weg war"):
  Steine der letzten N Tage nach BASIS-Wichtigkeit (ohne Decay-Strafe), markiert
  **nichts** als gesehen. Ist der Store für das Fenster leer (ZENTRALE war
  offline) → ehrlicher Hinweis statt Erfindung (Offline-Aufholmodus = nächster Baustein).

## KI muss WISSEN, dass sie das Tool hat (sonst Konfabulation)

Live-Test 2026-06-07: auf „hast du news für mich" rief das 9b `lies_news`
**nicht** — es fabulierte ein plausibles News-Update aus dem (veralteten)
Trainingswissen. Ursache: das Modell greift kein Tool, von dem es nicht weiß
dass es das braucht. Fix an zwei Hebeln:
1. **Graph-Capability** „dir die aktuellen Nachrichten und die Weltlage holen"
   (`graph._SEED_CAPABILITIES` + `migrate_internet_access`-`new_caps`) → die KI
   weiß jetzt, dass sie die Fähigkeit hat.
2. **Anti-Konfabulations-Regel** (`_CAPABILITIES_PROMPT` Regel 8): aktuelles
   Weltgeschehen kennt sie NICHT aus sich selbst → für News/Weltlage/Politik
   IMMER `lies_news` (tage=7 für Wochenrückblick), nie aus dem Gedächtnis erfinden.
Greift erst nach **Restart** (Migration läuft beim Boot, Prompt lädt beim Boot).
Zuverlässigkeit ungemessen — bei weiterem Tool-Ignorieren eskalieren (stärkere
Regel / Few-Shot), nicht in Python templaten ([[feedback_python_model_labor]]).

## Env-Variablen

| Var                  | Default | Wirkung                        |
|----------------------|---------|--------------------------------|
| `NEWS_INTERVAL_MIN`  | 180     | Fetch-Intervall (Minuten)      |
| `NEWS_START_DELAY_S` | 90      | Verzögerung des ersten Laufs   |
| `OLLAMA_*`           | s. ai   | Modell/URL/num_ctx (geteilt)   |

Tuning-Konstanten (grob, gehören gebencht): `MATCH_THRESHOLD=0.60`,
`HALBWERTSZEIT_H=48`, `ARCHIV_FLOOR=8`, `SENDUNG_MAX=7`,
`SENDUNG_MIN_WICHTIGKEIT=15`.

## Status / offen

- **Baustein-Kern live + end-to-end getestet** (2026-06-07): 66 Meldungen
  → 23 Steine geclustert, Embedding-Merge (Israel/Libanon-Stein bündelte
  9 Stimmen aus 6 Quellen), Wichtigkeits-Sortierung, `[UPDATE]`-Marker,
  Decay-Funktion, `gesehen`-Status + "schon gehört" über zwei Sendungen.
- **Wochenrückblick (`lies(tage=7)`) gebaut + getestet** (2026-06-07): zieht
  die schwersten Steine der letzten N Tage aus dem Store, "Willkommen
  zurück"-Framing, schwerste zuerst, Trivia raus. Gilt für den Fall **du
  warst zuhause** (Store hat die Woche). Für **du warst weg** (ZENTRALE
  offline) fehlt der Store-Inhalt → siehe Offline-Aufholmodus unten.
- **Qualität ungebencht:** qwen3.5:9b clustert + kontrastiert sinnvoll,
  hat aber Deutsch-Patzer + gelegentliche Übersetzungs-/Faktenwackler.
  Mechanik steht, Qualität braucht objektive Messung
  ([[feedback_messen_nicht_vibes]]). Auch die Tuning-Konstanten
  (Decay-Halbwertszeit, Match-Schwelle, Wichtigkeits-Floor) sind geraten.
- **Offen / nächste Bausteine:**
  - **Offline-Aufholmodus GEBAUT (2026-06-07), aber auf Such-Backend
    blockiert.** `wochenrueckblick(tage)` erkennt per `poll_historie` eine
    Poll-Lücke im Fenster (`_groesste_pollluecke_tage` ≥ `GAP_SCHWELLE_TAGE`
    1.5) → schaltet auf `aufholmodus(tage)`: rückblickende **Web-Suche**
    (`web.suche`, themen-geseedet aus den dicksten Store-Steinen + generisch)
    → LLM-Aufhol-Rückblick. Mechanik getestet + korrekt: Lücken-Erkennung
    greift beidseitig, der Ehrlichkeits-Guard im `_AUFHOL_PROMPT` verhindert
    Halluzination. **ABER:** `web.suche` liefert aktuell NICHTS — DuckDuckGo
    serviert dem Scraper (`web._ddg_search`) eine Anti-Bot-Landingpage statt
    Ergebnissen (html- UND lite-Endpoint, GET+POST, ~14 KB ohne `result__a`/
    `uddg`). Das betrifft die **ganze Internet-Pipe** (auch das `web_suche`-
    Tool). Könnte temporäres Rate-Limit (durch Test-Hämmern) ODER harter
    Block sein — jedenfalls ist DDG-keyless zu fragil für ein automatisches,
    periodisches Feature. **Echter Fix = `web._ddg_search` tauschen** (laut
    Doku der vorgesehene Swap-Punkt): SearXNG self-hosted (passt zur
    Offline/Kontroll-Linie) oder eine News-/Such-API mit Key. Eigener
    Baustein, Backend-Entscheidung offen.
  - **Eilmeldung/Live-Push**: neuer Stein über hoher Schwelle → sofort
    raushauen (reuse Alarm-Kanal-Muster vom Kalender), statt auf die
    Sendung zu warten.
  - **Graph-Lese-Brücke**: Sendung gegen Sashas Graph personalisieren
    ("wie du schon weißt …").
  - **Restart + Live-Test** im laufenden System (Tool im Chat, Fetcher
    über mehrere Intervalle, Cross-Poll-Merge real beobachten).
  - **Phase 4 (visuell)**: Lead-Bilder/Videos pro Story auf den
    `monolith`-Canvas während die KI vorliest. Roh-Stimmen halten `link`
    dafür vor.
