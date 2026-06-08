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
| `embedding`         | bge-m3-**Centroid** des Clusters (Mittel der Stimmen-Vektoren, fürs Cross-Poll-Matching) |
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
_cluster_poll()  Poll-Meldungen → bge-m3 Embed → Python Average-Linkage clustert → LLM labelt → Bausteine {thema, kategorie, wichtigkeit, stimmen, centroid}
_integriere()    je Baustein: per Centroid-Embedding an bestehenden Stein andocken (merge) ODER neu
_decay_…()       Steine unter dem Boden archivieren
baue_sendung()   ungesehene/bewegte Steine wählen → LLM-Moderation → data/news_digest.json
wochenrueckblick(tage)  Steine der letzten N Tage (nach BASIS-Wichtigkeit, ohne Decay) → Rückblick
aktualisiere()   = ein Poll-Lauf: ankündigen → collect → cluster → integrate → decay → baue_sendung
lies(tage)       KI-Tool: tage=0 Tagessendung (markiert gesehen), tage>0 Wochenrückblick (markiert nichts)
start_fetcher()  Daemon-Thread: periodisch + laut angekündigt (aus main.py)
```

## Clustering: bge-m3 gruppiert, LLM labelt nur (Umbau 2026-06-08)

**Vorher** gruppierte das **LLM** alle ~60 Meldungen auf einen Schlag
(`_cluster_poll`, JSON). Das war der Grund für „Informationshaufen statt
Quellen-Kontrast": gemessen lumpte das 9B ganze Regionen zu **Mülleimer-
Bausteinen** (Nigeria landete unter „Terroranschlag Israel") und ließ
zugleich Geschwister als **Singletons** stehen (52/78 Einzelquelle). Kein
Prompt-Tweak fixt das zuverlässig ([[feedback_data_vs_model]]).

**Jetzt** macht das Gruppieren **Python deterministisch** (Sashas Insight:
nicht aufs variable Framing matchen, sondern auf die geteilten Fakten):

1. **bge-m3** bettet jede Meldung ein (`embeddings.embed_document`, Titel +
   Anriss). Mehrsprachig — de/en/ar derselben Story landen nah.
2. **Greedy-Average-Linkage** (`_cluster_items`, Schwelle `NEWS_CLUSTER_SIM`
   = 0.64): eine Meldung kommt nur in einen Cluster, wenn ihre MITTLERE
   cosine-Ähnlichkeit zu ALLEN Mitgliedern über der Schwelle liegt. Das
   „zu allen" bricht Single-Link-Ketten → ein Gaza-Artikel rutscht NICHT
   in den Beirut-Cluster, nur weil beide „Israel/strikes" sagen. So trennen
   sich ort-verschiedene Ereignisse von selbst (gemessen: der alte 23er-
   Nahost-Blob zerfällt in Beirut / Iran-Raketen / Terror / Gaza, je sauber).
3. **LLM labelt nur** die fertigen Cluster (`_label_clusters`,
   `_LABEL_PROMPT`): thema/kategorie/wichtigkeit — leichte Aufgabe vs.
   Gruppieren. **Gebatcht** (`LABEL_BATCH`=20), weil alle Cluster in EINEM
   Call den JSON-Output abreißen lassen (im Test passiert → ALLE Labels
   fielen auf die Heuristik zurück). Fallback pro Cluster: erste Schlagzeile
   als thema, `sonstiges`, Wichtigkeit grob aus der Quellenzahl.

`T=0.64` und der Batch-Bug wurden empirisch an 137 echten Meldungen
ermittelt ([[feedback_messen_nicht_vibes]]).

**Cross-Poll-Identität** (`_integriere`): ob ein neuer Baustein zu einer
bestehenden laufenden Story gehört, entscheidet Python per **Centroid**
(Mittel der Stimmen-Embeddings, robuster Fakten-Anker statt des früheren
losen `thema`-String-Matches): Cosinus gegen alle aktiven Steine, über
`MATCH_THRESHOLD` (0.66) → mergen (Stimmen rein, Wichtigkeit = max, bei
echter neuer Stimme `zuletzt_bewegt` auffrischen). Sonst neuer Stein. So
wächst die Ukraine-Story über Polls zu EINEM Stein.

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
- `0`/weglassen → **Tagessendung** (aktuelle Top-Themen). Liefert **IMMER** die
  volle Sendung (auch beim Wiederholen/Replay) und markiert die Steine als
  gesehen (das steuert nur die proaktive Frische-Logik, NICHT was geliefert
  wird). Ist der gecachte Digest leer/alt → baut on-demand frisch. Nicht-
  blockierend bei fehlendem Digest: async Lauf + "frag gleich nochmal".
  **WICHTIG (Fix 2026-06-07):** früher klebte ein „(nichts Wichtiges Neues…)"-
  Vorspann davor wenn alles gesehen war → das 9b plapperte genau das nach
  statt die Sendung zu lesen, und es gab keinen Replay. Beides raus: kein
  Freshness-Framing mehr im Tool-Output, `_waehle_sendung` fällt auf einen
  Recap der wichtigsten aktiven Themen zurück wenn nichts „frisch" ist.
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

## Sendungs-/Cinema-Modus (Frontend, monolith.html)

Liest die KI eine Sendung vor, schaltet das Dashboard in einen
**Sendungs-Modus**: dunkler Vorhang über alles, großer zentraler Untertitel,
der den **gerade gesprochenen Satz** zeigt (statt der ganzen Textwand).

- **Trigger:** `ai.chat_stream` yieldet `{"cinema": True}`, sobald `lies_news`
  läuft (vor der Ausführung). `app.py` reicht es als SSE-Event `cinema` durch.
  Das Frontend ruft `enterCinema()`.
- **Untertitel-Sync (geschenkt durch die Satz-TTS):** Die Sprachausgabe läuft
  eh Satz für Satz (`enqueueSpeak`/`drainSpeakQueue`, wartet auf `audio.onended`).
  Pro abgespieltem Satz setzt `drainSpeakQueue` den Untertitel auf genau
  diesen Satz. `speakQueue` trägt jetzt `{speak, display}` (TTS-Fassung +
  lesbarer Originalsatz).
- **Layout (korrigiert 2026-06-07 — KEIN schwarzer Vollvorhang!):** der erste
  Bau legte einen opaken Overlay über ALLES (auch den Kern) → kein Platz für
  Animationen/Bilder. Jetzt: `#stage[data-cinema="on"]` dimmt nur die SEITEN
  (`.body > .col:not(#col-mid)`) + Header sanft (opacity .3), die **Mittelspalte
  (`#col-mid`) bleibt hell** und der **Kern (#core) voll sichtbar** (Animationen/
  Phase-4-Bilder laufen weiter). Der Untertitel ist ein **Lower-Third** (`#cinema-sub`
  absolut unten in `.core-wrap`, dunkler Verlauf für Lesbarkeit, große Schrift)
  über dem Kern. `#minilog` (letzte User-Zeile) faded raus = macht Platz. Konsole
  schrumpft + dimmt, klart beim Tippen auf. `enterCinema`/`exitCinema` toggeln
  nur `data-cinema` aufs Stage; `setSubtitle` schreibt pro Satz ins Lower-Third.
- **Ende:** `done` setzt `cinemaExitPending`; sobald der letzte Satz
  durchgesprochen ist, schließt `drainSpeakQueue` den Vorhang sanft.
  `stopSpeaking` (Abbruch / neue Nachricht / `/clear`) schließt sofort.
- **Gemutet:** `enterCinema` no-op bei `chatMuted` (ohne Stimme kein
  Satz-Takt) → normaler Minilog. Code: `monolith.html` (`#cinema`-CSS +
  `enterCinema`/`exitCinema`/`setSubtitle` + Hooks in SSE-Reader/Drain).

## Env-Variablen

| Var                  | Default | Wirkung                        |
|----------------------|---------|--------------------------------|
| `NEWS_INTERVAL_MIN`  | 180     | Fetch-Intervall (Minuten)      |
| `NEWS_START_DELAY_S` | 90      | Verzögerung des ersten Laufs   |
| `OLLAMA_*`           | s. ai   | Modell/URL/num_ctx (geteilt)   |

Tuning-Konstanten: `NEWS_CLUSTER_SIM=0.64` (Average-Linkage, gemessen),
`LABEL_BATCH=20`, `MATCH_THRESHOLD=0.66` (Centroid-Cross-Poll),
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
- **Clustering-Umbau LIVE + gemessen (2026-06-08):** Sashas Befund „Sendung
  = Informationshaufen, Quellen nicht geltend gemacht" → Ursache war NICHT
  der Moderations-Prompt (der fordert den Kontrast schon), sondern das
  LLM-Clustering (Mülleimer-Bausteine + Singletons). Fix = bge-m3 Average-
  Linkage gruppiert, LLM labelt nur (s.o. „Clustering"-Sektion). An 137
  echten Meldungen verifiziert: Nahost-Blob zerfällt sauber, Multi-Quellen-
  Cluster erhalten (Armenien trägt TASS), Sendung kontrastiert jetzt
  namentlich („Tagesschau betont X, TASS stellt es als Y dar").
- **OFFEN — 9B fabuliert in der Moderation:** in der Test-Sendung erfand das
  Modell Details, die NICHT in den Snippets stehen („Flughafen Chornobyl",
  „Operation Epic Fury", „7.000 Tote") — trotz „NICHTS erfinden"-Regel.
  Separates Problem (Modell-Ehrlichkeit), nicht das Clustering. Wahrscheinl.
  Ursache: der Moderator sieht pro Stimme nur `CORPUS_DESC`=160 Zeichen →
  zu dünn → stopft Lücken mit Erfindung. **Daten-Hebel** ([[feedback_data_vs_model]]):
  mehr echten Snippet-Text geben (volle 300 gespeicherte Zeichen, oder
  Artikel-Body per `hole_url` nachladen) statt Prompt-Regeln stapeln. Nächster Schritt.
- **Qualität sonst ungebencht:** qwen3.5:9b hat Deutsch-Patzer
  („Isreal"/„Zverew"). Tuning-Konstanten gegen Ground-Truth zu benchen
  ([[feedback_messen_nicht_vibes]]).
- **Offen / nächste Bausteine:**
  - **Offline-Aufholmodus LIVE seit 2026-06-08.** `wochenrueckblick(tage)`
    erkennt per `poll_historie` eine Poll-Lücke im Fenster
    (`_groesste_pollluecke_tage` ≥ `GAP_SCHWELLE_TAGE` 1.5) → schaltet auf
    `aufholmodus(tage)`: rückblickende **Web-Suche** (`web.suche`, themen-
    geseedet aus den dicksten Store-Steinen + generisch) → LLM-Aufhol-
    Rückblick. Mechanik getestet + korrekt: Lücken-Erkennung greift beidseitig,
    der Ehrlichkeits-Guard im `_AUFHOL_PROMPT` verhindert Halluzination.
    **War blockiert** weil DuckDuckGo den Scraper geblockt hat — **gelöst durch
    Such-Backend-Swap auf SearXNG** (self-hosted, `localhost:8888`, JSON;
    Implementierung + Container-Befehl siehe [ki_system.md](ki_system.md)).
    End-to-End-Lauf 2026-06-08 verifiziert: 7 SearXNG-Suchen → LLM →
    4187-Zeichen-Rückblick, alle Calls im Internet-Panel sichtbar (expliziter
    `push_internet_log`, da localhost-Hop sonst unsichtbar wäre).
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
