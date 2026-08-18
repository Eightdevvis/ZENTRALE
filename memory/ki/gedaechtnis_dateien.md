# Das Datei-Gedächtnis (seit 18.08.2026)

Nachfolger des Konzept-Graphen als Gedächtnis der Kern-KI. Modul:
`core/gedaechtnis.py`.

## Warum der Graph abgelöst wurde

Nicht aus Prinzip, sondern nach Messung. Der Zustand des Cloud-Graphen nach
Wochen Betrieb (62 Knoten, 104 Kanten):

- **42 von 104 Kanten waren `erwähnt-am`** — reine Buchhaltung darüber, WANN
  geredet wurde. Die drei bestverbundenen Knoten waren ein Datum (25 Kanten),
  `KI` (22) und `Sasha` (22). Die Struktur wurde also von Zeitstempeln und
  Sprecher-Ankern dominiert, nicht von Sashas Leben.
- **22 der 62 Knoten waren die Selbstbeschreibung der KI** (`capability` /
  `limit` aus dem Seed). Vom Rest war genau **ein** Knoten eine Person: Sasha.
- **Derselbe Fakt lag doppelt in zwei Formen**: `Krankheit hat Fieber` *und*
  `Sasha zustand Fieber`.
- **Die Typen waren keine Taxonomie, sondern ein Rateergebnis pro Turn.**
  `Fahrradfahren` (eine Fähigkeit) war ein `project`; `MPI`, `MicroOrganoLab`,
  `Praktikum` und `brain organoids` waren *alle vier* `project`.
- **Schlicht falsch:** `Sasha wohnt-in Universität des Saarlandes`.
- **Aus Interesse wurde Arbeit:** `Sasha arbeitet-an brain organoids`.

**Die Ursache war das fehlende Schema.** Der Extraktor erfand pro Turn, welcher
Typ und welches Verb passt — 15 Verben und 8 Typen ohne eine Regel, welche
Kombination zulässig ist, ohne Identität (»ist das derselbe Fakt nochmal?«) und
ohne Gültigkeit. Ein Wissensgraph ohne Ontologie ist ein Haufen Sätze, denen man
die Wörter weggenommen hat.

**Und das ist der tiefere Punkt: weggenommen.** `Sasha zustand Fieber` ist das,
was von »ich lag drei Tage flach und hab die Vorlesung verpasst« übrig bleibt.
Alles, was ein guter Assistent daran bemerken würde — Ursache, Folge, Ton — ist
genau das, was der Extraktor löscht. Der Graph war eine verlustbehaftete
Kompression, die ausgerechnet das wegwarf, worin das Modell gut ist: Sprache.
Deshalb fühlte sich ZENTRALE dümmer an als dasselbe Modell im nackten Chat.

Der Graph ist **nicht gelöscht**: `data/ai_graph*.json` bleibt liegen,
`core/graph.py` bleibt im Baum, und zwei Schalter holen ihn zurück
(`ZENTRALE_GRAPH_KONTEXT=1`, `ZENTRALE_GRAPH_EXTRAKTION=1`). Wenn er je
wiederkommt, dann mit einem Schema — [Graphiti](https://github.com/getzep/graphiti)
(Apache 2.0) hat genau die drei fehlenden Stücke: eigene Entity-Typen als
Pydantic-Schema, bi-temporale Gültigkeit mit Invalidierung, und Episoden-Knoten,
die den Rohtext am Graphen halten.

## Die fünf Speicher

| Speicher | Wo | Wer pflegt |
|---|---|---|
| **Steckbrief** | `data/gedaechtnis/sasha.md` | **Sasha.** Die stabilen Regeln über ihn. Zu wichtig für einen Extraktor. |
| **Ziele** | `data/gedaechtnis/ziele.md` | Sasha; die KI darf vorschlagen. |
| **Dossiers** | `data/gedaechtnis/dossiers/*.md` | Die KI schreibt fort, Sasha korrigiert direkt im Text. Weltzustand pro laufender Sache. |
| **Tagebuch** | `data/gedaechtnis/tagebuch/YYYY-MM-DD.md` | Die KI. Was gesagt und getan wurde, in SEINEN Worten. |
| **Messreihen** | `data/g_*.json` (Zyklus-Werkzeug, `core/graphs.py`) | Die KI trägt ein. Zahlen über Zeit — Schlaf, Stimmung, Training. |

Die Messreihen liegen bewusst **nicht** im Gedächtnis-Ordner: Kurven über Zeit
kann das Zyklus-Werkzeug längst, samt Anzeige in der TUI. Sie hier nochmal als
Text abzulegen hieße, zwei Wahrheiten über denselben Wert zu führen.

## Was in den Prompt geht — und was nicht

`gedaechtnis.kopf_block()` liefert **Steckbrief + Ziele + die Dossier-TITEL**,
mehr nicht, und sitzt im **gecachten** Kopf (`cloud._static_system`). Alles
Weitere holt die KI per Werkzeug.

Das ist der eigentliche Unterschied zum Graph-Block, und er ist ökonomisch:

- Der Graph-Block änderte sich mit **jeder Frage** und ging deshalb bei jedem
  Turn **ungecacht** raus — bis zu 2.500 Zeichen (~625 Token), voll bezahlt.
- Der Kopf-Block ändert sich nur, wenn sich die Dateien ändern. Er wird einmal
  geschrieben und danach zu 10 % gelesen.
- Dazu entfiel die **Extraktion**: ein eigener LLM-Call pro Turn (gemessen
  0,0028 €), bei 30 Kontakten am Tag rund **2,70 € im Monat** — bei einem
  20-Euro-Budget ein Achtel, ausgegeben für das Herstellen des Matschs.

Die fünf Werkzeuge kosten dafür ~760 Token mehr im Tool-Schema. Die stehen im
gecachten Präfix und sind damit der billigere Handel.

## Die Werkzeuge (`gross`-Schiene)

| Werkzeug | Was | Gate |
|---|---|---|
| `read_note(name)` | Dossier am Stück lesen; auch `sasha` / `ziele` / `tagebuch` | nein |
| `write_note(name, text)` | anhängen — `name="tagebuch"` oder ein Dossier-Titel | **nein** |
| `search_memory(query)` | Volltextsuche über Tagebuch und Dossiers | nein |
| `rewrite_note(name, content)` | Dossier komplett neu schreiben (Aufräumen) | **ja** |
| `log_series(series, value)` | Messwert in eine bestehende Kurve | nein |

**Warum `write_note` nicht gegatet ist:** eine KI, die vor jeder Notiz fragt,
ist kein Sekretär, sondern eine Zumutung. Sie soll mitschreiben wie jemand, der
danebensitzt. Gegatet ist nur der destruktive Weg — und selbst der legt eine
`.bak` an, weil Aufräumen die Tätigkeit ist, bei der man am ehesten etwas
verliert.

Sie stehen in `core/profil/gross.py::_GEDAECHTNIS` und **nicht** in
`klein.TOOLS`: der lokale Pfad ist gerade nicht testbar, und ein 9B bezahlt
jedes zusätzliche Schema mit. Sobald lokal wieder läuft, wandern sie hinüber —
`ai._dispatch_tool` kennt sie ohnehin unter denselben Namen.

## Grenzen, die absichtlich drin sind

- **Anhängen statt Ersetzen.** Ein Modell, das eine Datei neu schreibt, löscht
  still alles, was es beim Schreiben nicht im Kopf hatte.
- **Slug statt Pfadprüfung.** `../../data/ai_config` wird zu `data-ai-config`;
  ein Pfad-Ausbruch ist damit nicht möglich, statt ihn hinterher abzufangen.
- **Stumpfe Substring-Suche.** Braucht keinen Embedder, kein Netz, keine
  Datenbank, und findet Eigennamen zuverlässiger als jede Ähnlichkeitssuche.
  Wird sie zu grob, kommt ein Index **darüber** — nicht darunter.
- **Kappungen** (`MAX_NOTIZ` 4.000 Zeichen, Warnung ab `MAX_DOSSIER` 20.000).
  Ein Dossier, das ein Modell vollschreibt, bis es den halben Kontext frisst,
  wäre derselbe Fehler in Grün.

## Was hier NICHT gelöst ist

Der Takt (Morgenritual, Anstupsen, Wecker) und der Planer (Schemen: Ziele,
Kapazität, echte Zeitfenster) sind eigene Schichten und stehen noch aus. Das
Gedächtnis ist ihre Grundlage, nicht ihr Ersatz.
