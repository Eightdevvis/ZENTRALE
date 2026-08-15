# KI-Memory-System v2 – Plan (HISTORIE, Phasen A–F)

> ⚠️ **Status: archiviert.** Phasen A–F sind durch, Phase G (Konzept-Graph)
> hat das LTM/STM-Setup als *primary memory* abgelöst. Aktueller Stand:
> → `memory/ki/ki_system.md`.
>
> Dieses File bleibt als Entscheidungs-Historie liegen – die Begründungen
> (warum `bge-m3`, warum `who_said`, warum `recency`-Enum, warum Tool-Set
> so geschnitten) sind weiterhin gültig und haben das Graph-Design
> mitgeformt. Der Abschnitt "Designprinzipien" enthält bewusst die alte
> Festlegung "Kein Graph (für Single-User-Chat overengineered)" – die
> wurde nach Stresstests im Mai 2026 verworfen, weil flaches Top-K bei
> assoziativen Queries ("was weißt du über mich") und zeitbasierten
> Fragen versagt hat. Siehe Commits `9b76766` (Phase G) und `9023407`
> (Stresstest-Findings).

## System-Prompt-Komposition

Reihenfolge im System-Prompt (in `core/ai.py`):

1. `_SYSTEM_PROMPT` – Charakter (entspannt, direkt, deutsch).
2. `_CAPABILITIES_PROMPT` – Statisches Selbstbild der KI: was sie über
   ihre Tools kann, was sie definitiv NICHT kann (kein Internet, keine
   Mails, keine Hardware-Steuerung, kein Code-Eval, etc.). Wird IMMER
   injiziert, nicht über Retrieval geholt - Kernwissen über sich selbst
   darf nicht von einem Such-Treffer abhängen.
3. `memory.format_for_prompt(query)` – Top-K LTM-Einträge zur aktuellen
   User-Frage. Kann leer sein.

Begründung für #2 separat: ohne diesen Block improvisieren 14B-Modelle
zuverlässig Fähigkeiten zusammen ("ich kann dir das mailen", "ich rufe
die API auf"). Mit klarer Aufzählung bleibt die KI ehrlich. Erlernte
Begrenzungen ("user hat mich korrigiert, das geht nicht") landen als
LTM-Typ `limit` zusätzlich im retrievten Kontext.

## Designprinzipien

- **Speichern by default, prune später.** 7–14B-Modelle sind miese
  Relevanz-Klassifizierer. Lieber alles ins STM und in der
  Konsolidierung dedupen.
- **Beide Konversationsseiten speichern.** Nicht nur User-Aussagen,
  sondern auch was die KI selbst gesagt hat (`who_said`-Feld). Das
  ist der wichtigste Hebel gegen Widerspruchs-Bullshit moderner LLMs.
- **Zeit ist Metadaten, nicht Prompt-Inhalt.** Timestamps auf den
  Einträgen, kein „heute ist …" pro Call. Tool `get_current_time()`
  für Bedarfsfälle.
- **Asynchron statt synchron.** Klassifier-Call läuft NACH der
  AI-Response in einem Hintergrund-Task. Wahrgenommene Latenz = 0.
- **Embeddings für Assoziation, Schubladen für Strukturierung.** Kein
  Graph (für Single-User-Chat overengineered, siehe Diskussion
  2026-05-15). Wenn Multi-Hop-Reasoning irgendwann mal wirklich
  klemmt, baut man den Graph dann nachträglich auf die Statements.
- **Embedding-Modell ist multilingual.** Aktuell `bge-m3` (BAAI,
  1024-dim, ~569 MB). Frühere Wahl `nomic-embed-text` war zu
  englischlastig - deutsche Queries fanden den Bezug schlecht. Modell
  ist per `OLLAMA_EMBED_MODEL` umstellbar, prefix-Logik in
  `core/embeddings.py:_PREFIXES_BY_MODEL` erweitern wenn nötig.

## Architektur

```
┌─ STM (volatil, pro Session) ──────────────────────────────┐
│  data/ai_stm.json                                          │
│                                                            │
│  list:    [{ts, role, text, tags}]                        │
│            role ∈ {user, ai}                              │
│  summary: rollender Text, beide Seiten zusammen           │
└────────────────────────┬───────────────────────────────────┘
                         │ Konsolidierung
                         │ Trigger: /sleep ODER Inaktivität > X Min
                         ▼
┌─ LTM (persistent, durchsuchbar) ──────────────────────────┐
│  data/ai_ltm.json                                          │
│                                                            │
│  entries: [{                                               │
│    id, content, embedding,                                 │
│    type:      'fact'|'preference'|'commitment'|'technical',│
│    who_said:  'user' | 'ai',                               │
│    created_at, tags[]                                      │
│  }]                                                        │
│                                                            │
│  Suche: Cosinus-Distanz auf nomic-embed-text-Vektoren     │
└────────────────────────────────────────────────────────────┘

Pro Turn:
  1) User-Query → Embedding → Top-K LTM-Einträge holen
  2) System-Prompt-Inject: stm_summary + letzte N stm_list +
     Top-K LTM (gefiltert auf relevante Tags/Types)
  3) Model generiert Antwort + ggf. Tool-Calls
  4) ASYNCHRON nach Stream-Ende:
       - Turn (User + AI) in stm_list ablegen
       - Klassifier-Call: Update stm_summary
       - Klassifier-Call: hat irgendwas LTM-Würde? → vormerken
```

## Datenmodelle

### `data/ai_stm.json`

```json
{
  "schema_version": 1,
  "list": [
    {
      "ts": "2026-05-15T14:32:11",
      "role": "user",
      "text": "Mein Pi hat nur 1 GB RAM",
      "tags": ["hardware", "pi"]
    },
    {
      "ts": "2026-05-15T14:32:18",
      "role": "ai",
      "text": "Verstanden – das ist ein Pi 3, kein Pi 4.",
      "tags": ["hardware", "pi"]
    }
  ],
  "summary": "Sasha klärt gerade die Hardware-Specs des Pi. ..."
}
```

### `data/ai_ltm.json`

```json
{
  "schema_version": 2,
  "next_id": 0,
  "entries": [
    {
      "id": 0,
      "content": "Sashas Pi ist ein Raspberry Pi 3 Model B mit 1 GB RAM.",
      "embedding": [0.123, -0.456, ...],
      "type": "fact",
      "who_said": "user",
      "created_at": "2026-05-15T14:32:11",
      "tags": ["hardware", "pi"]
    }
  ]
}
```

Erlaubte `type`-Werte:
- `fact` – objektive Information über User, System, Welt.
- `preference` – wie der User Dinge mag (Stil, Reaktionsart).
- `commitment` – was die AI versprochen hat / offenes TODO.
- `technical` – Configs, Code-Details, Internals.
- `capability` – was die AI nachweislich kann (gelernt im Gespräch).
- `limit` – was die AI NICHT kann (vom User korrigiert), damit sie's
  bei verwandten Themen über Retrieval wiederfindet und nicht erneut
  fälschlich anbietet.

`next_id` zählt nur hoch, IDs werden **nicht** wiederverwendet – sonst
könnten alte AI-Referenzen auf eine andere Aussage zeigen.

## Migration aus v1

Bestehende `data/ai_memory.json` (Schema v1, flat) muss auf v2 gemappt
werden:

| v1-Feld    | v2-Feld         | Mapping                                    |
|------------|-----------------|--------------------------------------------|
| `id`       | `id`            | übernehmen                                 |
| `type`     | `type`          | `summary` → `fact`, `todo` → `commitment` |
| `content`  | `content`       | übernehmen                                 |
| `saved_at` | `created_at`    | umbenennen                                 |
| –          | `embedding`     | `null` (Phase B backfilled das)            |
| –          | `who_said`      | default `"user"` (alte Einträge stammen   |
|            |                 | aus User-Aussagen via AI-Tool)             |
| –          | `tags`          | `[]`                                       |

Migration läuft beim ersten Boot mit neuem Schema, einmalig. Alte
Datei wird zu `data/ai_memory.v1.json.bak` umbenannt.

## Memory-Tools (für die AI)

| Tool                       | Zweck                                             |
|----------------------------|---------------------------------------------------|
| `search_memory(...)`       | Semantische Suche mit strikten Filter-Enums      |
| `get_current_time()`       | NUR für Such-Anfragen (s.u.), nicht zum Datieren |
| `promote_to_ltm(stm_id)`   | „Das war jetzt wichtig" – manuelle Promotion     |
| `update_memory(id, c)`     | Korrektur eines bestehenden LTM-Eintrags         |
| `forget(id)`               | LTM-Eintrag löschen                              |

Diese ersetzen das aktuelle `save_memory` – das wird obsolet, weil
Auto-Save den Job übernimmt.

### `get_current_time()` – strikte Semantik

Die AI bekommt das aktuelle Datum/Uhrzeit **NICHT** in den System-Prompt
injiziert (sonst Token-Verschwendung pro Call). `created_at` wird beim
Speichern automatisch dran getackert – die AI muss da auch nicht selbst
manuell ein Datum dranhängen.

`get_current_time()` ist ausschließlich dann nützlich, wenn die AI eine
**Zeit-Filter-Suche** machen will und dafür den heutigen Bezug braucht
(„was war gestern" → erst current_time, dann recency-filtered search).

### `search_memory` – Lookup-Schema (verbindlich, keine freie Form)

Damit die AI nicht halluziniert („zeig mir Einträge von ungefähr letzter
Woche" → wer-weiß-was kommt zurück), läuft Zeitfilter über ein
**festes Enum**, nicht über Freitext-Datumsangaben:

```python
search_memory(
    query:    str,                  # semantische Anfrage
    recency:  Literal['today', 'yesterday', 'last_7_days',
                      'last_30_days', 'this_year', 'all'] = 'all',
    who_said: Literal['user', 'ai', 'any'] = 'any',
    type:     Literal['fact', 'preference', 'commitment',
                      'technical', 'any']    = 'any',
    top_k:    int                  = 5,
) -> list[entry]
```

Die Date-Range wird **deterministisch im Backend** aus dem `recency`-
Enum berechnet, nicht von der AI gerechnet. Die AI wählt nur ein Label.

Wenn die AI eine sehr spezifische Datums-Abfrage braucht
(„zwischen März und April"), muss ein zusätzliches Tool dafür kommen –
aber bewusst eigenständig, nicht versteckt im `recency`-Param. Dann
auch mit explizitem ISO-Date-Format und Backend-Validierung.

## Konsolidierung

Trigger:
- `/sleep` als User-Command im Chat.
- Inaktivitäts-Timer (X = 30 Min initial, anpassbar).

Ablauf:
1. STM-Liste in zusammenhängende Themen-Cluster gruppieren (LLM-Call).
2. Pro Cluster: dedupen, in den passenden LTM-Typ promoten,
   Embedding generieren.
3. Promovierte STM-Einträge löschen, Summary leeren.
4. Übrig gebliebene STM-Einträge bleiben für die nächste Session.

## Bau-Reihenfolge (Phasen) – alle durch

- [x] **A** – Datenmodell + Migration v1 → v2.
- [x] **B** – Embeddings beim Speichern, später Wechsel von
      `nomic-embed-text` → `bge-m3` (multilingual).
- [x] **C** – Retrieval (Top-K Cosinus-Suche) + Prompt-Injection-Pfad.
- [x] **D** – Async Auto-Save nach Stream-Ende.
- [x] **E** – Konsolidierung (STM → LTM) + Anti-Lügen-Schraube.
- [x] **F** – `_CAPABILITIES_PROMPT` als Selbstbild + Anti-Konfabulation
      bei leerem LTM.
- [x] **G** – **Konzept-Graph ersetzt LTM/STM/Profil-Schichten als
      primary memory.** Siehe `memory/ki/ki_system.md`.

Phase G hat die Designprinzipien-Festlegung "Kein Graph" umgeworfen –
in der Praxis sind assoziative und zeitbasierte Queries der Hauptfall,
genau dort versagt flaches Top-K. LTM/STM laufen noch parallel mit
(`save_memory`-Tool), sind aber nicht mehr der primäre Antwortpfad.

## Offene Detail-Fragen (zur Bau-Zeit zu klären)

- Top-K – wie viele Einträge in den Prompt? (Start: K=5, justieren)
- Tag-Extraktion automatisch oder vom Modell? (Start: vom Modell
  über `save_memory`-Argumente, später eventuell heuristisch.)
- Inaktivitäts-Timer – wie messen ohne Polling? (vermutlich
  letzter-Turn-Timestamp + Lazy-Check beim nächsten Turn).
- Was passiert mit nicht-promotierbarem STM bei Konsolidierung?
  Verfallen lassen oder als "low-confidence" in LTM aufnehmen?

## Verwandte Doku

- `memory/ki/ki_system.md` – wie's aktuell läuft (wird nach Phase C/D angepasst)
- `memory/betrieb/datei_zugriffe.md` – Whitelist für `read_file`-Tool, unverändert
- `claude_hinweise.md` – Tool-Use-Conventions
