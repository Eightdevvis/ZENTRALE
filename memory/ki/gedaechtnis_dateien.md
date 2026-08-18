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

## Die Speicher

| Speicher | Wo | Wer pflegt |
|---|---|---|
| **Steckbrief** | `data/gedaechtnis/sasha.md` | **Sasha.** Die stabilen Regeln über ihn. Zu wichtig für einen Extraktor. |
| **Ziele** | `data/gedaechtnis/ziele.md` | Sasha; die KI darf vorschlagen. |
| **Dossiers** | `dossiers/*.md` | Prosa über EINE Sache, die er ernsthaft verfolgt. KI schreibt fort, Sasha korrigiert im Text. |
| **Kataloge** | `kataloge/*.md` | Viele gleichförmige Einträge mit Attributen. Der Ideenpool, die Module, das Material. |
| **Quellen** | `quellen/*.md` (+ `quellen/dateien/`) | Abgelegte Dokumente, aus PDF/HTML extrahiert. |
| **Tagebuch** | `tagebuch/YYYY-MM-DD.md` | Die KI. Was gesagt und getan wurde, in SEINEN Worten. |
| **Messreihen** | `data/g_*.json` (Zyklus-Werkzeug) | Zahlen über Zeit — Schlaf, Stimmung, Spagat in cm. |

### Dossier oder Katalog?

**Was man lesen will, wird Prosa. Was man durchsehen will, wird Katalog.**

Der Ideenpool ist der Fall, an dem das kippt: Sasha hat tausende Maker- und
Hacker-Ideen. Pro Idee ein Dossier wäre unlesbar, und Prosa lässt sich nicht
überfliegen. Ein Katalog-Eintrag ist in zwanzig Sekunden getippt und in einem
Rutsch zu scannen:

```
## Fourier-Visualisierer aufm Oszi
- thema:     fourier, frequenzen, signale
- equipment: arduino, dac, loetkolben
- aufwand:   klein
- status:    idee
- dossier:   -
```

Wird eine Sache **ernst**, bekommt sie ein Dossier, und der Katalog-Eintrag
zeigt darauf. Das gilt nicht nur für Elektronik: auch den Spagat lernt man
strategisch — wo genau die Beweglichkeit blockiert, welche Muskelgruppen
Unterstützung brauchen. Mehr, als in einen Katalog-Eintrag passt; weniger als
ein Elektronikprojekt.

Status-Vokabular (Sashas Schnitt): `idee`, `priorisiert`, `queued`,
`in_schedule`, `abgeschlossen`, `pausiert`. Es unterscheidet, was bloß Einfall
ist, was ihm wirklich wichtig wäre, was für bald angestellt ist und was
tatsächlich schon im Stundenplan steht.

### Messreihen werden im DOSSIER verlinkt

Bewusst nicht im Katalog-Eintrag. **Was nur als Idee notiert und morgen
vergessen ist, wird nicht vermessen** — weder der aktuelle Stand noch ein
Trend. Gemessen wird, was man wirklich verfolgt, und genau das ist die
Schwelle, ab der ein Dossier existiert.

### Wie das Schemen daraus Verbindungen zieht

Über **geteilte Stichworte**, nicht über Kanten. Die Idee sagt `thema: fourier`,
das Modul im Katalog sagt `thema: signalverarbeitung, fourier`, die
Interessens-Spur von heute Morgen sagt `fourier`. »Welche Idee passt jetzt« ist
damit eine Schnittmenge, die `search_memory` beantwortet — ohne dass irgendwo
ein Extraktor Beziehungen erfindet. Genau daran ist der Graph gescheitert: er
dachte sich die Vokabeln selbst aus. Hier kommen sie aus Sashas Katalogen,
sichtbar und korrigierbar.

### Fertigkeiten werden abgeleitet, nicht gepflegt

Es gibt bewusst **keine** handgepflegte Fertigkeitsliste. Was Sasha kann, steht
in den Dossiers abgeschlossener Projekte (`gelernt:`-Zeilen) — wer drei Dinge
mit I2C gebaut hat, kann I2C. Eine Liste, die man von Hand nachführt, ist am
Tag nach dem Anlegen veraltet.

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
| `create_series(name, typ, einheit)` | neue Kurve anlegen | **ja** |
| `fetch_document(url, name)` | etwas aus dem Netz holen und ablegen | **ja** |

**`fetch_document` ist die Werkzeugkette, die Sasha wollte:** sie sucht das
Modulhandbuch, zieht es, legt es richtig ab und kann es danach lesen — ohne
dass er eine Datei anfasst. PDF wird per `pdftotext` zu Text (ein PDF ist
binär, und ein hundertseitiges Handbuch will ohnehin niemand pro Frage im
Kontext haben), HTML wird entrümpelt, Binäres landet als Datei in
`quellen/dateien/` — **immer mit einem Markdown-Vermerk daneben**, was es ist
und wo es herkam. Es entsteht nie eine Datei ohne Eintrag; sonst liegt in einem
halben Jahr ein Ordner voller namenloser Downloads herum.

Unterschied zu `fetch_url`: das holt etwas, um es *jetzt* zu lesen, und
vergisst es danach. `fetch_document` legt ab, um es *später* wiederzufinden.

`create_series` ist gegatet, weil `log_series` bewusst nichts von selbst
anlegt — sonst würde aus jedem Tippfehler eine weitere halbtote Kurve in
Sashas Übersicht.

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
