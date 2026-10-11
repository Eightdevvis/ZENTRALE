# Das Datei-Gedächtnis

**Stand 2026-10-11:** Das Gedächtnis der Kern-KI sind **Markdown-Dateien**
unter `data/gedaechtnis/`, seit dem 11.10. **nach Thema** und im Format von
Claudes Datei-Gedächtnis (Kopf, Index) — Aufbau, Werkzeuge, Umzug:
[gedaechtnis.md](gedaechtnis.md). Diese Datei hält das Warum fest: warum der
Konzept-Graph ging, Notiz/Dossier/Katalog, Skills, Import, die TUI.

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

## Die Arten — und woher der Default „Notiz" kommt

Seit dem 11.10.2026 ist die Art (`notiz`, `dossier`, `katalog`, `quelle`,
`ziel`, `projekt` …) ein Feld im Datei-Kopf, kein Ordner mehr
([gedaechtnis.md](gedaechtnis.md)). Was davor gelernt wurde, gilt weiter:

**Die Notiz ist der Default, wegen eines Fehlgriffs (18.08.2026).** Sasha
fragte, ob sie sich Wegzeiten merken kann. Die KI überlegte richtig („eine
kurze Notiz 'wegzeiten'") und schrieb die Fahrzeit dann ins Umzugs-Dossier —
weil ein unbekannter Name damals ein Dossier wurde und ein Dossier ein
Vorhaben ist (mit `thema`, `aufwand`, `status`). Seitdem: ein neuer Name wird
eine formlose Notiz; ein Vorhaben entsteht absichtlich, indem die Vorlage
ausgefüllt wird — **die Vorlage entscheidet die Art**. Schreibt sie einen
Katalog-Kopf in eine Notiz, wird daraus ein Dossier (seit dem 11.10. bleibt
die Datei dabei liegen, nur die Art im Kopf wechselt).

**Steckbrief und Hausregeln gehören Sasha** (18.08. bzw. 06.10.2026: *„hausregeln
und steckbrief mit meiner bestätigung ja nur"*). `write_note` auf Hausregeln,
Steckbrief oder Ziele geht nur über den Ja/Nein-Knopf
(`gedaechtnis.schreibt_kernakte`); ohne konnte das Modell sich selbst
Vorrang-Regeln geben.

### Der Nachprüf-Schritt steht im Werkzeug-Ergebnis

Sasha, 20.08.2026: *„nachprüfschritt natürlich also kosten niedrig wie möglich
aber nich auf kosten von qualität in diesem ausmaß!"*

Eine zweite Modellrunde zum Kontrollieren kostet einen vollen Aufruf. Das
Tool-**Ergebnis** geht aber ohnehin ans Modell zurück — steht dort der Beweis
statt „OK", **hat sie nachgesehen, ohne dass ein Aufruf mehr anfällt.**

| statt | jetzt |
|---|---|
| `Notiert in kataloge/ideen.` | `Neu in kataloge/ideen: 'Fraktal-Rendering'. Der Katalog hat jetzt 2 Einträge.` |
| `OK, eingetragen.` | `Steht jetzt am 2026-08-21: Zahnarzt (09:00). Der Tag hat 2 Einträge.` |
| `OK, Routine eingetragen.` | `Eingetragen — ABER es gibt jetzt 2 Regeln namens 'Geige' (17:45, 18:00). Wollte er eine ÄNDERN?` |

Der wichtigste Fall ist der, in dem der Beweis **nicht** aufgeht: dann steht das
ausdrücklich im Ergebnis, statt dass sie einen Erfolg meldet, den es nicht gab.

Dazu drei Sperren, die alle aus demselben Vorfall stammen:

- **Katalog-Einträge werden geupsertet, nicht angehängt.** Zwei Einträge mit
  demselben Titel sind das schlechteste Ergebnis: dieselbe Sache steht doppelt
  und niemand weiß, welche Fassung gilt. Ein Status-Wechsel ersetzt jetzt.
- **Wörtlich Gleiches wird nicht zweimal angehängt** — es wird gesagt.
- **Dieselbe Sache nicht an zwei Orten.** Schreibt sie eine Notiz zu etwas, das
  schon als Katalog-Eintrag existiert, wird abgelehnt und der vorhandene Ort
  genannt. Das ist die letzte offene Gabel im Modell: eine Idee kann als Notiz
  **oder** als Eintrag festgehalten werden, beides ist für sich richtig — falsch
  war, **beides** zu tun. Entscheiden kann der Code das nicht; merken, dass es
  die Sache schon gibt, sehr wohl.

Der Test im Prompt, wenn sie schwankt: **könnte es einen Status haben, also
etwas sein, das er tun könnte? Dann Katalog-Eintrag, sonst Notiz.**

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

### Der Katalog-Eintrag steckt IM Dossier

Ein Dossier **beginnt mit seinem Katalog-Eintrag**, und der Code trägt ihn
von dort in den Katalog ein:

```
## Küche fertig bauen
- katalog:   vorhaben
- thema:     umzug, wohnung, küche, bad
- equipment: -
- aufwand:   gross
- status:    in_schedule

## Ziel
Eine benutzbare Küche.
```

**Warum nicht zwei getrennte Artefakte:** weil zwei Dinge, die man synchron
halten muss, auf Dauer immer auseinanderlaufen. Vorher war die Kopplung eine
Anweisung im Prompt — und Anweisungen werden übergangen. Sasha hat gemeldet,
dass beim Schreiben eines Dossiers nicht verlässlich ein Katalog-Eintrag
auftauchte. Jetzt kann eine Wahrheit von sich selbst nicht abweichen.

- `gedaechtnis.kopf_lesen(text)` parst den führenden Block. Kein Kopf →
  nichts passiert; ein Dossier ohne Kopf ist erlaubt (Übersichts-Dossiers
  über einen ganzen Bereich, etwa `training`, haben absichtlich keinen).
- `gedaechtnis.katalog_abgleichen(name)` setzt `dossier:` **selbst** — nie
  aus dem Text, denn genau dieser Teil ging bisher verloren — und
  **upsertet** den Eintrag: ändert sich der Status im Dossier, wird der
  Eintrag ersetzt statt gedoppelt.
- `gedaechtnis.konsistenz()` meldet beide Waisen-Arten. Kein Prompt-Anteil.

**Die Vorlagen** (`vorlagen/dossier.md`, `vorlagen/katalog.md`) sind
gewöhnliche Dateien, über `read_note("vorlagen/dossier")` erreichbar und von
Sasha änderbar; beim ersten Zugriff werden sie aus dem Code angelegt. Die
Dossier-Vorlage **enthält die Katalog-Vorlage als Kopf** — die KI füllt eine
Vorlage aus und muss an keine Kopplung denken.

**Die Kollision, die dabei zu lösen war:** `dossier_notieren` hängte jeden
Eintrag unter eine `## <Datum>`-Überschrift. Der Katalog-Kopf beginnt
ebenfalls mit `##`. Wäre er da durchgelaufen, hätte `kopf_lesen` das Datum
als Titel gelesen, keine Felder gefunden und **stillschweigend nichts**
eingetragen — der schlimmste Fehlertyp, weil nichts kaputtgeht, sondern nur
etwas ausbleibt. Unterschieden werden beide deshalb nicht am `##`, sondern
an den **Feldzeilen darunter**: was keine hat, ist eine gewöhnliche Notiz
und landet unter ihrem Datum. Das Fehlverhalten fällt damit auf die sichere
Seite.

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

Die Messreihen behalten ihr eigenes Format (das Zyklus-Werkzeug zeigt sie);
seit dem 11.10.2026 liegen sie nur unter ihrem Thema im Gedächtnis
([gedaechtnis.md](gedaechtnis.md), „Messreihen").

## Was in den Prompt geht — und was nicht

`gedaechtnis.kopf_block()` liefert **Hausregeln + Steckbrief + den Index**
(Namen und Haken, seit 11.10.2026), mehr nicht, und sitzt im **gecachten**
Kopf (`cloud._static_system`). Alles Weitere holt die KI per Werkzeug.

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

Die Tabelle aller Gedächtnis-Werkzeuge mit Gate: [gedaechtnis.md](gedaechtnis.md).

**`fetch_document` ist die Werkzeugkette, die Sasha wollte:** sie sucht das
Modulhandbuch, zieht es, legt es richtig ab und kann es danach lesen — ohne
dass er eine Datei anfasst. PDF wird per `pdftotext` zu Text (ein PDF ist
binär, und ein hundertseitiges Handbuch will ohnehin niemand pro Frage im
Kontext haben), HTML wird entrümpelt, Binäres landet als Datei in
`themen/<thema>/dateien/` — **immer mit einem Markdown-Vermerk daneben**, was es ist
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

Sie stehen im Werkzeug-Register (`core/werkzeug_register.py`) nur mit
einer `gross`-Beschreibung, also **nicht** in `klein.TOOLS`: der lokale Pfad ist gerade nicht testbar, und ein 9B bezahlt
jedes zusätzliche Schema mit. Sobald lokal wieder läuft, bekommen sie dort
eine `klein`-Beschreibung — ausgeführt werden sie ohnehin schon (`ki_werkzeuge`).

## Skills (seit 2026-10-07)

Phase 4 des [Claude-Web-Plans](claude_web_plan.md); Werkzeuge und Prompt:
[skills.md](skills.md). Hier steht, wie sie als
Dateien liegen.

**Was ein Skill ist:** eine Anleitung für eine bestimmte Art Aufgabe. Die
Abgrenzung, an der es kippt: **Hausregeln gelten immer** („antworte kürzer"),
ein **Skill nur für seine Aufgabe** („wenn er eine Woche planen will: …").
Sasha, 07.10.2026: „ki soll sogar welche vorschlagen totally, damit sie später
wenn sie gut aufgestellt ist sich von alleine weiterentwickeln kann." Und am
selben Abend: „skills sind eher komplexere abläufe" — eine Stil-Regel wie
„kurz" ist keine.

### Das Format — das von Claude (seit 2026-10-07 abends)

Sasha: Claudes Skill-Format übernehmen, damit echte Claude-Skills sich
**ohne Umbau hineinkopieren** lassen. Ein Skill ist ein Ordner
`data/gedaechtnis/ki/skills/<name>/` (vor dem Umzug vom 11.10.2026: `skills/<name>/`):

```
wochenplan/
├── SKILL.md         ---
│                    name: wochenplan
│                    description: "Sasha will wissen, was diese oder nächste Woche ansteht …"
│                    ---
│
│                    1. Kalender lesen …
├── _zentrale.json   {"status": "aktiv", "herkunft": "sasha", "erstellt": "2026-10-07"}
├── scripts/         optional — laufen NUR in der Sandbox (run_code skill=…)
├── references/      optional — liest die KI per load_skill(name, datei=…)
└── assets/          optional — Vorlagen, Schriften, Bilder für Ausgaben
```

- **`SKILL.md`** ist Wort für Wort Claudes Format: YAML-Kopf mit `name`
  (Kleinbuchstaben, Ziffern, Bindestrich, ≤ 64, = Ordnername) und
  `description` (der Auslöser: wann der Skill passt, ≤ 1.024 Zeichen, kein
  `<` `>`), optional `license`, `compatibility`, `allowed-tools`, `metadata`
  — fremde Felder stören nicht und bleiben beim Ändern erhalten
  (`core/skill_format.py`; liest mit PyYAML, ohne PyYAML mit einem eigenen
  kleinen Leser für die flachen Felder).
- **`_zentrale.json`** — was nur ZENTRALE wissen muss, **nicht** in der
  SKILL.md (sonst wäre sie nicht mehr Claude-tauglich): `status` (`aktiv` |
  `vorgeschlagen` | `aus`), `herkunft` (`sasha` | `ki` | `anthropic` |
  `zentrale` — mitgeliefert, von ZENTRALE selbst geschrieben),
  `erstellt`, optional `braucht` (was ZENTRALE dafür fehlt, sichtbar in der
  TUI und in `/api/skills`), `vermerk`, `quelle`. **Eine Datei pro Skill**
  statt einer gemeinsamen Statusdatei: der Sync ist „neueste Datei
  gewinnt" — schaltet Sasha am PC einen Skill und am Laptop einen anderen,
  überleben beide Schalter.
- **Ohne `_zentrale.json`** (von Hand hineinkopierter Claude-Skill) gilt der
  Skill als **an**. Ohne `description` oder ohne gültigen Kopf zählt er als
  aus (er rutschte sonst leer in den Prompt). Ordner mit ungültigem Namen und
  solche, die mit `_` oder `.` beginnen (`_alt/`), sind keine Skills.
- **Abschalten statt löschen.** Der Sync ist additiv; ein gelöschter Ordner
  käme vom anderen Rechner zurück.
- `edit_skill` lässt die alte Fassung als `SKILL.md.bak` daneben.

**Die Liste im Prompt** (`skills.prompt_block`, Details in
[skills.md](skills.md)): je aktivem Skill Name + volle
Beschreibung, höchstens 6.000 Zeichen. Wird sie länger (seit 2026-10-08):
Hinweis in Customize → Skills („Liste zu lang …") — Sasha schaltet aus, was
er nicht braucht; nur als letzte Rettung werden die längsten Beschreibungen
gekürzt (erster Satz), dann die längsten nur mit Namen genannt. Die kurzen
bleiben immer ganz.

**Warum nicht in `BEREICHE`:** Skills liegen unter derselben Wurzel (gleiche
Test-Umlenkung `ZENTRALE_GEDAECHTNIS_DIR`, gleicher Sync), aber
`write_note`/`read_note`/`search_memory` erreichen sie bewusst nicht. Ein
Skill ist eine Anweisung der KI an sich selbst; geschrieben wird er nur über
die gegateten Werkzeuge. Zugriff von außen: `gedaechtnis.bereich_ordner()`.

### Umzug aus dem alten Format (`core/skill_umzug.py`)

Bis 07.10. abends war ein Skill eine Datei `skills/<name>.md` mit Kopf im
Katalog-Schema (`## name`, `- beschreibung/erstellt/herkunft/status`). Bei
**jedem** Zugriff auf den Skill-Ordner (`skills.ordner()`) zieht jede solche
Datei um: `<name>/SKILL.md` (Kopf aus `beschreibung`) + `_zentrale.json`
(status, herkunft, erstellt aus dem alten Kopf). Die alte Datei wird **nicht
gelöscht**, sondern wandert nach `skills/_alt/` (alte `.md.bak` ebenso). Die
neuen Dateien tragen die Änderungszeit der alten — zieht der zweite Rechner
später selbst um, überschreibt er so keinen Schalter, den Sasha auf dem
ersten schon umgelegt hat. Bringt der Sync eine alte Datei zurück (der
andere Rechner ist noch nicht umgezogen), wird sie nur wieder beiseitegelegt
(gleiche Fassung ersetzt die gleiche, eine andere bekommt `.2`, `.3` …).

Sonderfälle (Sasha, 07.10.):
- **`kurz`** ist kein Skill. Ihr Inhalt wird **eine Hausregel** in Sashas Ton
  („Bin ich im Stress, unterwegs oder sag „kurz": Antwort zuerst …"),
  angehängt über `gedaechtnis.kernakte_schreiben` (atomar, `.bak`), nur
  einmal (steht sie schon da, passiert nichts) und nur, wenn `kurz` an war.
  Der Skill selbst zieht um und ist **aus**, mit Vermerk — gelöscht wird er
  nicht.
- **`recherche`** zieht um, mit Vermerk „Kandidat zum Ersetzen — Claude im
  Web recherchiert selbst".

### Erstbefüllung (eigene + Anthropic)

Mitgelieferte Skills liegen im Repo unter `core/skill_vorlagen/`: eigene
(`wochenplan/`, `recherche/`, `import-memory/`, seit 08.10. `pdf/` und `word/` — [pdf_word.md](pdf_word.md); `kurz` ist raus) direkt dort, die von
Anthropic unter `anthropic/` (14 Skills, nur Apache 2.0, je mit
`LICENSE.txt`; Herkunft, Commit und Lizenz in `anthropic/README.md`, dazu
`THIRD_PARTY_NOTICES.md`). Welche davon an oder aus sind und was einem
fehlt, steht in `anthropic/zentrale.json` — nur dort Eingetragenes wird
ausgeliefert, und daraus entsteht je Skill die `_zentrale.json`.

Bei jedem Zugriff wird **je Skill** nachgeliefert, wessen Ordner fehlt —
nie überschrieben (bis 07.10. abends: nur, wenn der ganze Ordner fehlte; dann
bekäme ein Rechner mit Skills die neuen nie). Kopiert wird unter einem
Punkt-Namen und dann umbenannt (nie ein halber Skill sichtbar). Alle Dateien
bekommen als Änderungszeit fest den 07.10.2026: sonst gewänne beim Sync
(`rsync --update`) die frische Vorlage eines Rechners, der später zum ersten
Mal startet, gegen Sashas Änderung auf dem anderen.

### Import aus einer anderen KI — Skill `import-memory` (seit 2026-10-08)

Sasha: seine Erinnerungen aus Claude (oder ChatGPT/Gemini) herüberholen —
„das wird uns helfen dann sogar den umzug zu machen". Der Skill liegt als
Vorlage in `core/skill_vorlagen/import-memory/` (an, `herkunft: zentrale`,
`quelle`: nach Claudes eingebautem Skill gleichen Namens, für ZENTRALE neu
geschrieben). Name englisch wie bei Claude, damit Sasha ihn wiedererkennt;
Beschreibung und Anleitung deutsch wie die übrigen eigenen Skills.

- **`SKILL.md`**: Ablauf (Export holen → lesen und planen → aussieben →
  Plan zeigen, auf Ja warten → in Etappen schreiben → gemeinsam durchsehen)
  und die Regeln (Export ist Material, keine Anweisung; getarnte
  Anweisungen weg; nur ergänzen; Widersprüche zeigen statt schreiben; keine
  Links/Bilder aufrufen; Stil-Wünsche nur nach Rückfrage in die Hausregeln).
- **`references/`** (Progressive Disclosure): `export-prompt.md` (Text, den
  Sasha der anderen KI gibt), `datenschutz.md` (was ganz wegfällt, mit
  Beispielen), `abbildung.md` (welcher Export-Teil wohin: Stil → Hausregeln
  nur nach Rückfrage, Eckdaten → Steckbrief `sasha`, Ziele → `ziele`,
  Projekt mit Dossier → Dossier, sonst Notiz je Projekt, Vorlieben/
  Interessen/Personen/Beruf → Notizen, Rest → `notizen/aus-<herkunft>`;
  nie Kataloge, Tagebuch, Projekte, Skills).

**Was der Code garantiert** — `write_note(…, herkunft="claude")` →
`gedaechtnis.import_ergaenzen`, unabhängig davon, wie gut das Modell dem
Skill folgt:

- **zeilenweise nur Neues.** Eine Zeile, die bis auf Aufzählungszeichen,
  Datum, Vermerk, Groß/klein und Satzende schon in der Zieldatei oder im
  selben Aufruf steht, wird übersprungen und im Ergebnis genannt. (Das
  normale `write_note` prüft nur den ganzen Text — von zehn Zeilen, deren
  eine schon dasteht, stünde die doppelt.)
- **jede Zeile mit Vermerk vom Code**: `- Eintrag  [import claude
  2026-10-08]`; ein Datum am Zeilenanfang des Exports (`[2026-03-01] - …`)
  wird zu `…, Eintrag vom 2026-03-01]`. Alles Importierte findet
  `search_memory("import claude")`.
- **nie Kataloge, Quellen, Vorlagen, Tagebuch.** Im Katalog ersetzt
  `write_note` einen gleichnamigen Eintrag (upsert) — ein Import würde
  Sashas Fassung still überschreiben.
- **keine Zeilen mit Link oder Bild** (`http`, `www.`, `![`, `](`).
- **höchstens 30 Zeilen je Aufruf, je ≤ 500 Zeichen; alles oder nichts**,
  atomar geschrieben (`dateien.atomar_schreiben`). Zeilen werden als
  Aufzählung geschrieben — ein `## Titel` mit Feldern im Export befördert
  eine Notiz deshalb nicht zum Dossier.
- **Dossiers**: unter `## <Datum> · import <herkunft>`, einmal je Tag und
  Herkunft. **Notizen**: dieselbe Sperre wie sonst gegen eine Notiz, zu der
  es schon einen Katalog-Eintrag gibt.
- **Kernakten** (Steckbrief `sasha`, Ziele, Hausregeln): dasselbe Gate wie
  `write_note`, jedes Mal, nie „immer"; die Frage nennt Herkunft und
  Zeilen („Soll ich aus dem Import von claude 2 Zeile(n) in Steckbrief
  ergänzen: …?").

**Warum ein Parameter statt eines eigenen Werkzeugs:** jedes Schema reist in
jedem Zug im gecachten Präfix mit, ein Import kommt selten vor. Der Parameter
kostet ~220 Zeichen (Deckel < 200 für seine Beschreibung in
`tests/test_profil.py`), nutzt das vorhandene Gate samt Frage und
`immer_erlaubbar=False` — ein eigenes Werkzeug hätte das alles doppelt
gebraucht. Die Beschreibung von `write_note` selbst blieb unverändert; wie
ein Import läuft, steht im Skill.

**Nicht gebaut (optional):** ein „Import-Modus", der `rewrite_note` und
`edit_skill` während eines Imports ganz verweigert. Bräuchte Zustand je
Gespräch; beide fragen ohnehin jedes Mal (ohne „immer"), und der Skill
verbietet sie. Kandidat, falls ein Modell sie im Import doch ruft.

Probelauf ohne echte Daten: `tests/fixtures/import_memory_beispiel.txt`
(erfunden: Heikles, eingeschmuggelte und getarnte Anweisung, Link, Dublette,
Widerspruch, Stil-Wunsch), gefahren mit gefälschtem Modell in
`tests/test_import_memory.py`.

## Für Sasha sichtbar und änderbar (seit 2026-10-07)

Phase 3 des [Claude-Web-Plans](claude_web_plan.md). Vorher lag das
Gedächtnis nur als Dateien da — Sasha hätte seine Hausregeln im Dateisystem
suchen müssen. Jetzt im TUI-Chat `/gedaechtnis` (oder `/skills`): eine
Überlagerung mit fünf Abschnitten — Hausregeln, Steckbrief, Ziele (ganzer
Text), Themen (Dateien mit Art und Haken, seit 11.10.2026), Skills (Name, an/aus/vorgeschlagen, von dir /
von der ki). Tasten und Aufbau: [../system/tui_bauplan.md](../system/tui_bauplan.md),
„Chat: Gedächtnis".

- **Kernakte ändern:** `e` (oder Enter) öffnet sie im Editor (`$VISUAL`,
  `$EDITOR`, sonst nano, sonst vi). Nach dem Speichern geht der Text über
  `PUT /api/gedaechtnis/<akte>` zurück (`hausregeln`, `steckbrief`, `ziele`
  — sonst 404). `gedaechtnis.kernakte_schreiben` schreibt atomar
  (`dateien.atomar_schreiben`), legt die alte Fassung als `.bak` daneben (wie
  `rewrite_note`) und stößt den Sync an. Mit geschickt wird der `stand`
  (Fingerabdruck) vom Öffnen: hat die KI die Akte inzwischen per
  `write_note` ergänzt, antwortet das Backend 409, statt ihre Zeile
  stillschweigend zu überschreiben; Sashas Text bleibt dann in der
  Zwischendatei liegen, die Meldung nennt den Pfad. Obergrenze 20.000
  Zeichen (`MAX_KERNAKTE`, nur gegen Versehen — die Akte steht ganz im
  gecachten Kopf).
- **Skill an/aus:** Enter oder Leertaste; `skills.status_setzen` ändert nur
  `_zentrale.json` (die SKILL.md bleibt unberührt), über
  `POST /api/skills/<name>/status`. Ein `vorgeschlagen`er Skill wird damit
  freigegeben. Die KI hat dafür kein Werkzeug: was Sasha abschaltet, bleibt
  aus. Unter jedem Skill steht, falls vorhanden, „braucht: …" (warum ein
  Anthropic-Skill aus ist) und „hinweis: …" (Vermerk, z. B. bei recherche).

Die TUI kann auf dem Laptop gegen das PC-Backend laufen; deshalb geht der
Text über HTTP und die Zwischendatei liegt auf dem Rechner der TUI.

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
