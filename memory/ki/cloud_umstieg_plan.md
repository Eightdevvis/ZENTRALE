> **Historisch, Stand 10.08.2026.** Das Dokument, mit dem der Umstieg auf ein
> Cloud-Modell entschieden wurde — Befund, Begründung, Reihenfolge. Es ist
> seither umgesetzt; was daraus wirklich geworden ist, steht in
> [ki_system.md](ki_system.md) und [cloud_bericht.md](cloud_bericht.md). Hier
> wird nichts mehr nachgezogen: der Wert liegt darin, WARUM so entschieden
> wurde, nicht darin, was heute gilt.

# ZENTRALE — Umstieg auf Cloud

Stand: 10. August 2026. Grundlage: Durchsicht von `Eightdevvis/ZENTRALE` (main),
125 Python-Dateien, ~45k Zeilen.

---

## 1. Die Entscheidung

Der Assistant läuft erstmal auf einem Cloud-Modell, damit er überhaupt da ist.
Lokal wird später nachgezogen — das braucht länger und eventuell Hardware.
Das lokale Ziel ist nicht gestrichen, nur verschoben.

**Warum das jetzt Sinn ergibt:** Das Projekt hing nicht an der Architektur,
sondern daran, dass ein 9B nicht klug genug war und immer mehr Prompt-Absicherung
brauchte. Der Wechsel löst genau dieses Problem.

---

## 2. Befund: Was steht, was fehlt

### Steht schon

- **`tutor/cloud.py`** — vollständiger Anthropic-Pfad. Tool-Use-Loop,
  Schema-Übersetzung OpenAI→Anthropic, Streaming, Tool-Tiefen-Limit.
  Drop-in für `ai.chat_stream()` mit identischer Signatur.
- **`tutor/providers.py`** — `claude` steht auf `enabled: True` mit `ANTHROPIC_API_KEY`.
- **`core/ai_backends.py`** — Backend-Erkennung, Kill-Switches für local und cloud,
  Multi-Backend-Struktur (`MODULE_BACKENDS`) bereits vorbereitet.
- **Erlaubnis-Gate** (`PERMISSION_REQUIRED_TOOLS`) — Python-seitig, nicht
  modellgetrieben. Trägt unverändert rüber.

### Fehlt

Der **Kern** hat keinen Cloud-Pfad:

```python
MODULE_BACKENDS = {"chat": (LOCAL,), "news": (LOCAL,), "tutor": (LOCAL, CLOUD)}
```

`core/providers.py` sagt es selbst: der Kern redet mit keiner Cloud.

Der Grund ist ein echter Unterschied, kein Versäumnis:

| | `core/ai.chat_stream()` | `tutor/cloud.py` |
|---|---|---|
| Yield | Events: `{"reflect":…}`, `{"ascii":…}`, `{"permission":…}`, `{"cinema":…}` | nur Text-Strings |
| Tools | 13 Kern-Tools, teils gegatet | geschlossene Vokabel-Allowlist |
| Memory | Graph im System-Prompt | bewusst keiner |

**Zu bauen:** ein `core/cloud.py` nach Vorbild von `tutor/cloud.py`, aber mit
vollem Event-Protokoll und Erlaubnis-Gate.

**Nicht anzufassen:** `_execute_tool` / `_dispatch_tool`, der ganze Tool-Body,
die Memory-Schicht.

---

## 3. Memory

### Grundsatz

Der Graph bleibt. Die Begründung im Docstring stimmt: Top-K-Embedding-Retrieval
versagt bei breiten Fragen ("was weißt du über mich") und bei konzeptuell
verwandten, sprachlich unähnlichen Dingen. Aktivierungs-Spread löst das.
Datum als eigener Knoten löst "wann hab ich was gesagt".

`core/embeddings.py` läuft lokal (Ollama) und ist vom Chat-Modell unabhängig.

> **Wichtig:** Cloud-Chat heißt *nicht*, dass Ollama abgeschaltet werden kann.
> Das Memory braucht es weiter.

### Zwei Ergänzungen

**Wörtliche Transkripte unter den Graph legen.**
Ein Graph aus Labels und Kanten speichert, *dass* eine Beziehung besteht, nicht
*was* gesagt wurde — Zahlen, Daten, genaue Formulierungen sind nach der
Extraktion weg. Für "extensiv **und** genau" braucht es beides: Graph als
assoziativer Index, Knoten zeigen auf append-only gespeicherten Originaltext.

**Merges nicht automatisch.**
Alias-Auflösung bei 0.85 + Token-Bonus ist ein destruktiver Schreibpfad. Ein
Fehlmerge passiert still, ist in `data/ai_graph.json` praktisch nicht reparierbar
und fällt nie auf. Besser: beide Knoten behalten, `alias-von`-Kante ziehen.
(Das Pi/Pizza-Beispiel steht nicht umsonst im Kommentar.)

### Isolations-Invariante

**Lokal sieht alles von Cloud. Cloud sieht nichts von lokal.**

Konsequenz für den Kern: `core/ai.chat_stream()` schiebt
`graph.context_for_query()` in den System-Prompt. Ein Cloud-Kern mit Memory
schickt also den Graphen an die API. Beides gleichzeitig geht nicht.

**Auflösung:** Der Cloud-Pfad kriegt einen eigenen Graphen —
`data/ai_graph_cloud.json`, nicht `data/ai_graph.json`. Das lokale Modell liest
den Cloud-Graphen später und baut einen zweiten Layer darauf; es schreibt nie
hinein. Derselbe Graph, nur erweitert.

> Jetzt eine Zeile Konfiguration. In einem Jahr ein Entwirrungs-Albtraum.

---

## 4. Die Schemen-Mechanik

> **Was hier entstehen soll:** ein Assistent, der zwei Dinge gleichzeitig tut.
> Er hält einen Plan über alle Lebensbereiche hinweg lebendig — nicht als
> Kalender, sondern mit einem Urteil darüber, was wann dran ist und was zu viel
> ist. Und er sorgt nebenbei dafür, dass der Nutzer permanent von Stoff umgeben
> ist, der an das andockt, woran er gerade arbeitet — ohne dass sich das nach
> Unterricht anfühlt.
>
> Zwei Seiten derselben Medaille, ein gemeinsamer Speicher. Dieser Abschnitt
> beschreibt die Mechanik konzeptuell; die persönlichen Konkreta (Module,
> Projektliste, Niveau, Vorlieben) werden separat übergeben — siehe 4.11.

### 4.1 Die vier Ebenen

```
1. Privater + Uni-Schedule      nicht verhandelbar, wird nur VERWALTET
2. Uni-erweiternde Projekte     ein POOL, nichts davon Pflicht
3. Ein Freizeitprojekt          ein besetzbarer Fokuspunkt, optional
4. Alles andere                 wartet, ohne verloren zu gehen
```

Ebene 1 fällt von selbst an — Termine, Abgaben, Klausuren, Pflichten. Die KI
verwaltet, was eingegeben wurde, und plant dort nichts.

Ebene 2 ist **kein Plan, sondern ein Angebot**: was gerade zum laufenden Stoff
passen würde. Nichts darin ist verpflichtend.

Ebene 3 ist ein einzelner Slot für das Projekt, das gerade im Vordergrund steht.
Auch optional, auch einplanbar — er ist nur einer statt vieler. Mehr Bedeutung
hat er nicht.

Mit allem auf Ebene 2 und 3 sind drei Umgangsweisen vorgesehen, alle
gleichwertig:

- **schedulen lassen und buchen** — die KI legt es in den Plan
- **auf Impuls selbst verfolgen** — ohne Termin, wenn danach ist
- **nicht annehmen** — folgenlos, kein Nachfassen

### 4.2 Fenster und Kapazität

Der entscheidende Unterschied zwischen den Ebenen 2 und 3 ist nicht Wichtigkeit,
sondern **Datierbarkeit**.

Uni-erweiternde Projekte hängen am Vorlesungsstoff und sind damit datierbar:
jedes hat ein Fenster, in dem es sinnvoll ist, und außerhalb ist es deutlich
weniger wert. Weil mehrere Fächer parallel laufen, sind auch mehrere Fenster
gleichzeitig offen — das ist der Normalfall, nicht die Ausnahme.

Freizeitprojekte haben gar keine Uhr. Sie sind beliebig verschiebbar.

**Projekte laufen nebeneinander, nicht in einer Schlange.** Ein angenommenes
Poolprojekt bedeutet nicht, dass es den Vordergrund besetzt, bis es fertig ist —
es bedeutet ein paar Stunden, über ein paar Tage verteilt. Solange an denselben
Tagen daneben Platz bleibt, läuft das Freizeitprojekt normal weiter.

Die Planungsfrage lautet deshalb nicht „was kommt als Nächstes dran", sondern:

> **Wie viele Stunden pro Tag fordern die laufenden Projekte zusammen — und wie
> viele sind an diesen Tagen überhaupt da?**

Ein Fenster ist ein Zeitraum, in dem ein Projekt sinnvoll ist, kein Slot, der
belegt wird. Mehrere offene Fenster sind kein Stau. Was die Fenster steuern,
ist der **Zeitpunkt** — was ein Projekt kostet, steuert die Kapazität.

**Deadlines fallen bei Ebene 2 von selbst an.** Aus Fenster und geschätztem
Aufwand ergibt sich die Zeit pro Tag — und damit ein Enddatum, das niemand
setzen muss. Das ist auch die Rechnung, mit der sich vorab sagen lässt, ob ein
Projekt überhaupt reinpasst.

**Ebene 3 hat keine Deadline und ist elastisch.** Das Fokusprojekt hat kein
Enddatum, sondern nimmt den Raum ein, der übrig bleibt. Ist wenig los, wächst
es; ist viel los, schrumpft es, ohne dass etwas verletzt wird. Es ist der
Puffer im System, nicht ein weiterer Posten mit Anspruch.

Daraus folgt die einzige harte Grenze: **Die Summe der terminierten Projekte
muss in die Tage passen, die nach Abzug von Ebene 1 übrig sind.** Ist die Summe
zu groß, wird etwas gestrichen oder verschoben — nicht eingereiht.

Ein uhrenloses Projekt muss also nicht in eine Pause zwischen Uni-Projekte
passen. Es füllt, was die anderen übrig lassen.

### 4.3 Zuschnitt: schlank, aber nicht fade

Poolprojekte sind **unterstützend** — Demonstration und ein Stück Praxis, nicht
Produktion. Der Standardzuschnitt ist deshalb dünn: kleiner Aufwand, schnell
durch. Das ist keine Sparsamkeit, sondern die Bedingung dafür, dass überhaupt
mehrere gleichzeitig laufen können.

Zwei Kriterien ziehen dabei gegeneinander:

- **Je schlanker, desto besser** — mehr passt rein, weniger blockiert.
- **Je interessanter, desto besser** — was reizt, wird tatsächlich gemacht.

Die Auflösung ist kein Kompromiss in der Mitte, sondern eine Wechselkurs-Regel:

> **Je stärker eine Idee bekannte Vorlieben und Interessen trifft, desto mehr
> Aufwand darf ihr angerechnet werden.**

Ein zusätzlicher Bauschritt, der ein Projekt von „interessant" auf „das will ich
wirklich machen" hebt, ist die Stunden wert. Derselbe Aufwand für etwas bloß
Korrektes ist es nicht.

Wichtig: Das ist eine Regel für den **Vorschlag**, keine Annahme. Ein
aufwendigeres Projekt kommt in den Pool, weil es sich lohnen könnte — die
Entscheidung bleibt beim Nutzer, und ein Nein kostet nichts.

**Der Deckel darüber ist hart und nicht verhandelbar: Das Projekt muss ins
Zeitfenster des Stoffs passen.** Diese Fenster sind kurz — typisch Tage, selten
mehr als ein bis zwei Wochen. Der Wechselkurs oben regelt, wie viel Aufwand
innerhalb des Fensters vertretbar ist; er kann das Fenster nicht dehnen.

### Stufenbau statt Alles-oder-nichts

Ein Poolprojekt wird deshalb nicht als eine feste Größe konzipiert, sondern als
**Kern plus Ausbaustufen**:

```
Kern      passt garantiert ins Fenster, in sich abgeschlossen
Stufe 1   naheliegende Erweiterung, falls Zeit bleibt
Stufe 2   die reizvolle Version, wenn viel Zeit da ist
```

Der Kern ist die Zusage: klein genug, um sicher zu passen, und für sich
vollständig — kein Torso, wenn nichts nachkommt. Jede Stufe darüber ist optional
und wird erst gebaut, wenn der Kern steht und Kapazität übrig ist.

Das löst gleich mehrere Spannungen auf einmal:

- **Schlank und interessant** sind kein Kompromiss mehr, sondern zwei Enden
  derselben Idee.
- Die Entscheidung fällt **später und besser** — nicht bei der Planung, sondern
  wenn sichtbar ist, wie viel Zeit tatsächlich da war und ob das Thema trägt.
- Ein Projekt, das **einschlägt**, hat einen definierten Weg nach oben, statt
  entweder abzubrechen oder ungeplant auszuufern.
- Ein Projekt, das **nicht zündet**, endet nach dem Kern ohne schlechtes Gewissen.

Wächst ein Projekt über seine Stufen hinaus und interessiert weiter, obwohl das
Stofffenster längst zu ist, ist das kein Problem — dann ist es kein Poolprojekt
mehr, sondern ein Kandidat für den Fokusslot auf Ebene 3. Dasselbe gilt für
Ideen, deren Kern von vornherein nicht ins Fenster passt.

### 4.4 Wie der Pool befüllt wird

Das ist der Teil, an dem das System steht oder fällt. Ein Pool, der nur aus dem
Vorlesungsstoff abgeleitet wird, produziert Schulaufgaben.

Ein Poolprojekt entsteht aus einer **Schnittmenge**:

1. **Material** — was steht gerade im Stoff an
2. **Ideenbestand** — die eigenen Listen für Tüfteln, Experimentieren, Lernen,
   private Interessen
3. **Vorlieben** — bekannte Andockpunkte, Arbeitsweisen, Sachen, die reizen

Das Muster ist: nicht „Thema X braucht eine Übung, hier ist eine", sondern
„Thema X braucht eine Messung, und er arbeitet gern mit Laborgerät — also ein
Projekt, das beides zugleich ist". Wenn eine gemerkte Vorliebe sich mit dem
Stoff verbinden lässt, ist das der Anlass, sie einzubauen — gezielt, nicht
zufällig.

Zwei Bedingungen dafür, dass der Pool funktioniert:

- **Klein halten.** Ein Pool mit dreißig Vorschlägen ist keine Auswahl, sondern
  Überforderung — und erzeugt genau die Lähmung, gegen die geplant wird. Wenige
  Optionen zur Zeit, dafür passende.
- **Ablehnung ist Information, kein Fehler.** Was liegen bleibt, sagt etwas über
  Timing, Niveau oder Zuschnitt. Das gehört in die Agenda, nicht in einen
  Nachfass-Zyklus.

### 4.5 Rollenverteilung

| Bereich | Wer bestimmt | Was die KI tut |
|---|---|---|
| Schedule (1) | fällt von selbst an | verwaltet **nur**, was eingegeben wurde |
| Pool (2) | KI stellt zusammen, Nutzer greift zu | konzipiert, schlägt vor, terminiert auf Zuruf |
| Fokusprojekt (3) | Nutzer besetzt den Slot | plant es ein, wenn gewünscht |
| Freiraum | Nutzer | lässt Platz, plant nicht zu |

Die KI verschiebt keine Pflichten und erfindet keine. Sie plant um sie herum.

### 4.6 Routinen sind nicht eine Kategorie

Zwei Sorten mit gegensätzlicher Behandlung:

- **Frei.** Wird gemacht, wenn danach ist. Null Planung, keine Erinnerung,
  kein Tracking. Antasten macht sie kaputt.
- **Schiebe-anfällig.** Wird chronisch aufgeschoben, soll aber passieren.
  Hier ist Drängen ausdrücklich erwünscht — erinnern, nachfassen, „mach das
  jetzt".

Welche Sorte eine Routine ist, sagt der Nutzer. Das ist keine Einschätzung, die
die KI selbst treffen sollte — sie liegt zu nah an „ich weiß besser, was gut
für dich ist".

> **Das Drängen braucht eine Abbruchbedingung.** Ohne sie wird es Hintergrund-
> rauschen, das man wegzuklicken lernt — und dann ist der Kanal für alles
> andere auch verbrannt. Eskalieren, dann quittieren und Ruhe geben.

### 4.7 Die vier Planungs-Urteile

Das Entscheidende ist nicht Kalender-Tetris, sondern:

1. **Kapazität** — was bleibt übrig, nachdem der Schedule abgezogen ist.
   Ein Umzug frisst eine Woche; dann ist diese Woche keine Projektwoche.
2. **Reife** — passt das Projekt zum aktuellen Stand. Projekte haben eine
   Reihenfolge, in der jedes das nächste erst zugänglich macht.
3. **Empfänglichkeit** — wann ist er wofür offen. Vorerst bewusst simpel
   (Tageszeit, Kontext). **Dynamisch, nicht fest:** nach einer Klausur kann
   die Antwort „zu gar nichts" sein oder auch nicht. Später soll die KI das
   selbst modellieren — die Agenda (4.9) sammelt schon jetzt die Daten dafür,
   indem sie festhält, worauf er angesprungen ist und was verpufft ist.
4. **Gate** — manche Projekte hängen an einem fehlenden Input, nicht an Zeit.
   Sie warten nicht auf einen freien Nachmittag, sondern auf eine Messung,
   ein Bauteil, eine Auskunft.

Und eine fünfte Fähigkeit, ohne die der Rest kippt: **streichen können.**
Ein Planer, der nur hinzufügt, erzeugt exakt die Überforderung, gegen die er
gebaut wurde.

### 4.8 Layer B — Der Horizont

Nicht Fakten hinstellen. Das Gefühl soll sein: von jemandem mit mehr Weitblick
umgeben zu sein, der Dinge tiefer verknüpfen kann.

Drei Regeln, die das von einem Fakten-Zufallsgenerator unterscheiden:

- **Anlass statt Lehrplan.** Es dockt an etwas an, das gerade passiert — an
  einem laufenden Projekt, einer Frage, einer Beobachtung. Nicht „Wusstest du
  schon…".
- **Die Verknüpfung ist der Inhalt, nicht der Fakt.** Ein einzelner Fakt ist
  eine Trivia-App. Eine Brücke zwischen zwei Dingen, die er kennt, ist Weitblick.
- **Ring statt Silo.** Der dichtere Teil hat mindestens eine Kante zu etwas
  Aktivem; ein fester Anteil ist völlig frei — Politik, Geschichte, Psychologie,
  ohne Rechtfertigung. Ohne den freien Anteil wird es Nachhilfe. Ohne den Ring
  verwässert der Fokus.

**Der Mechanismus dafür ist bereits gebaut.** „Gehört zum Ring" heißt konkret:
Graph-Distanz zum aktiven Set. Distanz 1–2 ist der dichte Ring, weiter draußen
das freie Feld. Rechenbar, kein Bauchgefühl.

**Die Kopplung:** Der Planer definiert das aktive Set, der Horizont liest es.
Was auf Stufe 1 und 2 liegt, ist das Zentrum des Rings — und verschiebt ihn
automatisch mit, sobald sich der Plan ändert.

### 4.9 Agenda — im Graphen

Die Agenda lebt in **derselben Graph-Datei, mit eigenen Knotentypen.**

Agenda-Einträge sind Knoten vom Typ `vorhaben` / `beobachtung` mit Kanten in
die bestehenden Konzeptknoten:

```
[vorhaben: Fourier über das Harmonograph-Projekt anfüttern]
    --betrifft--> [Fourierreihen]
    --nutzt-->    [Harmonograph]
    --status-->   [angefüttert am 2026-08-14]
```

Was das löst:

- **Keine divergierenden Lanes.** Es gibt keine zweite Kopie von
  „Fourierreihen", die auseinanderlaufen könnte.
- **„Was habe ich zu X schon eingefüttert?"** wird eine Graph-Abfrage statt
  eines separaten Nachschlagens.
- **Das aktive Set fällt ab.** Es ist genau die Menge der Knoten, auf die
  Vorhaben zeigen — womit 4.5 ohne Zusatzarbeit funktioniert.

Die Trennung Fakten ↔ Pläne läuft dann nicht über getrennte Dateien, sondern
über **Knotentyp plus gefiltertes Lesen**: `context_for_query()` liefert für
normale Antworten nur Faktenknoten; nur der Planer-Pfad sieht auch die
Vorhaben.

> **Der Preis, den man dafür zahlt:** Der Schreibpfad muss getrennt bleiben.
> Der Konsolidierungs-Extraktor darf Vorhaben-Knoten niemals als „Fakten über
> den Nutzer" einsammeln, sonst wird aus „ich will ihn an Fourier heranführen"
> irgendwann „er interessiert sich für Fourier". Gemeinsamer Speicher, getrennte
> Schreibwege.

Damit bleiben zwei Speicher statt drei: **der Graph** (mit typisierten Ebenen)
und **das Transkript-Archiv** (append-only, wird nur über Knoten referenziert,
nie selbst durchsucht).

### 4.10 Die Linie

**Planung darf verdeckt sein, Auskunft nicht.**

Unbemerkt in eine Richtung schieben: dafür ist das Ding gebaut.
Auf eine direkte Frage nach dem eigenen Stand beschönigen: dann ist das
Instrument kaputt, mit dem geprüft wird, ob es überhaupt funktioniert.

Verdeckt heißt *standardmäßig nicht gezeigt*, nicht *unzugänglich* — die
Agenda muss einsehbar bleiben, sonst sind Fehlurteile nicht auffindbar.
Bei Themen ohne Prüfung gilt das doppelt: dort gibt es keinen externen
Abgleich, die Agenda ist die einzige Rückmeldung.

### 4.11 Was noch zu übergeben ist

Der Abschnitt oben ist bewusst frei von persönlichen Details. Damit der
Assistent arbeiten kann, kommt separat dazu:

- die aktuellen Uni-Module mit Stoffplan und Terminen
- die Liste der laufenden und wartenden Projekte, mit Reifeordnung
- das aktuelle zentrale Freizeitprojekt (Stufe 2)
- welche Routinen frei und welche schiebe-anfällig sind
- Lernvorlieben: welche Zugänge greifen, welche abstoßen
- bekannte Andockpunkte und Interessen für den Horizont-Layer

## 5. Tools, Sprache und was lokal bleibt

Der Modellwechsel betrifft **wer denkt**, nicht **wer ausführt**. Alles unterhalb
der Modellschicht bleibt unverändert lokal.

### Tool-Ausführung

Die Tools sind bereits sauber getrennt: `_dispatch_tool()` ist eine reine
Fallunterscheidung nach Tool-Namen, die in lokale Module verzweigt (Kalender,
Kontext, Mail, News, Web). Es steckt nichts Modellspezifisches darin.

Was sich ändert:

| | lokal | Cloud |
|---|---|---|
| Modell **entscheidet**, welches Tool | Ollama | Anthropic API |
| Aufruf wird **geparst** | Text-Parsing | native `tool_use`-Blocks |
| Tool **läuft** | lokal | **weiterhin lokal** |
| Ergebnis geht **zurück** ans Modell | Ollama | Anthropic API |

`_dispatch_tool` und `_execute_tool` werden **nicht angefasst**. Der einzige
Umbau betrifft die Schicht darüber: aus geparsten Textblöcken werden strukturierte
`tool_use`-Blocks, und die Rückgabe wird als `tool_result` formatiert.

> **Was dabei die Cloud sieht:** Tool-Ergebnisse gehen zurück ans Modell — also
> Dateiinhalte aus `read_file`, Kalendereinträge, Mail-Betreffzeilen, News-Texte.
> Nicht nur die Anfrage. Das ist derselbe Punkt wie beim Graphen (Abschnitt 3),
> nur über einen zweiten Weg. Der Erlaubnis-Dialog begrenzt hier schreibende
> Aktionen, nicht den Abfluss lesender.

### STT und TTS bleiben komplett lokal

Zwei eigenständige HTTP-Services, die vom Chatmodell völlig unabhängig sind:

- **Whisper** (`services/whisper_service.py`, Port 5050) — faster-whisper,
  Transkription mit Sprach-Hint
- **TTS** (`services/tts_service.py`, Port 5051) — Multi-Engine, Piper für
  Deutsch, sherpa-onnx für Mandarin

`core/audio.py` ist ein dünner HTTP-Client dazu und enthält keinerlei Bezug zum
Sprachmodell. **Am Sprach-Ein- und -Ausgang ändert sich durch den Cloud-Wechsel
nichts.**

Damit bleibt die Pipeline hybrid: Sprache rein → lokal transkribiert → Text an
die Cloud → Antwort zurück → lokal gesprochen. Nur der Textkanal in der Mitte
verlässt das Haus.

### Was lokal laufen muss, auch nach dem Wechsel

- **Ollama** — für Embeddings (`bge-m3`), unverzichtbar fürs Memory
- **Whisper-Service** — Spracheingabe
- **TTS-Service** — Sprachausgabe
- **Alle Tool-Backends** — Kalender, Dateien, Mail, News, Sensorik

Cloud-Chat heißt also **nicht**, dass die lokale Infrastruktur abgeschaltet
werden kann. Es tauscht genau eine Komponente aus.

## 6. Kosten

### Preise (Stand August 2026)

| Modell | Input | Output |
|---|---|---|
| Sonnet 5 | 2 $/MTok bis 31.08., danach 3 $ | 10 $ → 15 $ |
| Opus 5 | 5 $ | 25 $ |
| Haiku 4.5 | 1 $ | 5 $ |

Cache-Treffer: 10 % des Input-Preises. Batch: −50 %.

### Gemessener Ist-Zustand

- Statische Prompt-Blöcke: ~3.500 Zeichen (+ Capabilities ~2.900)
- **Tool-Schema: 21.384 Zeichen** — davon `read_calendar` allein 4.791
- Systemblock gesamt: **~8.000 Token**, bei jedem Turn und jeder Tool-Runde

### Szenarien

Annahme: 30 Austausche/Tag, 1,4 API-Calls je Austausch, ~3.500 Token variabler
Input (Graph-Kontext + Verlauf), 400 Token Antwort, Standardpreise ab September.

| | Input/Monat | Kosten |
|---|---|---|
| heute, ohne Cache | 14,5 M | ~45 € |
| aufgeräumt, ohne Cache | 8,2 M | ~28 € |
| heute, mit Cache | 5,4 M | ~20 € |
| **aufgeräumt + Cache** | 4,8 M | **~18 €** |

Nach Nutzungsumfang (aufgeräumt + Cache): 10/Tag → ~6 €, 20 → ~12 €,
30 → ~18 €, 50 → ~30 €.

### Die Lehre

**Caching bringt fast alles, Aufräumen fast nichts** — sobald der Systemblock
gecacht ist, kostet er nur noch 10 %, und ob 8k oder 3k Token gecacht werden,
macht am Monatsende ~5 € aus.

Aufräumen trotzdem machen: **wegen der Antwortqualität**, nicht wegen der
Rechnung. Die 9B-Krücken kosten mehr Qualität als Geld.

### Cache-Killer

Der Jetzt-Block (`_now_prompt()`, enthält die Uhrzeit) steht **ganz vorne** im
System-Prompt. Damit ist der Cache bei jedem Turn kaputt.

→ **Statisches nach vorn, Jetzt-Block und Graph-Kontext ans Ende.**

### Weitere Hebel

- **Konsolidierung auf Haiku** statt Sonnet: 2–3 €/Monat statt ~10 €.
  Konzepte und Kanten extrahieren ist Fleißarbeit, kein Denken.
- Nach dem Caching dominiert der variable Teil — wie viel
  `context_for_query()` ausschüttet und wie lang der Verlauf mitläuft.
- **Opus-Dazuschalten ist billig:** ein paar Dutzend echte Analyse-Aufrufe
  im Monat sind 3–6 €. Die Basislast ist das Problem, nicht die Spitzen.

### Abo vs. API

Abo und API sind getrennte Systeme. Das Max-Abo deckt Claude.ai, Claude Code
und die Desktop-Apps ab — **nicht** ZENTRALE. OAuth-Tokens aus Abos sind seit
April 2026 in Drittanwendungen blockiert. ZENTRALE kommt also oben drauf:
Max + ~18 € API ≈ 118 €/Monat.

**Wofür Max sehr wohl taugt:** der ganze Umbau via Claude Code, ohne Zusatzkosten.

> **Falle:** Sobald `ANTHROPIC_API_KEY` in der Umgebung steht, rechnet Claude
> Code still über die API ab statt über das Abo. Den Key also **nicht** global
> in `.bashrc`, sondern nur im ZENTRALE-Prozess — was ohnehin sauberer ist,
> weil er laut Doku aus `data/ai_config.json` kommen soll.

**Offen:** Nutzung mal messen. Mit Pro schon nach einer halben Stunde am Limit
spricht klar für Max — aber es ist noch nicht gegengerechnet.

---

## 7. Konkrete Fundstellen

### Bugs / zu korrigieren

| Was | Wo | Problem |
|---|---|---|
| `claude-opus-4-8` | `tutor/cloud.py`, `tutor/providers.py` | Modell existiert nicht. Aktuell: `claude-opus-5`, `claude-sonnet-5` |
| Provider-Reihenfolge | `core/providers.py: configured()` | Gibt den **ersten** Provider mit Key zurück; `qwen` steht vor `claude`. Bei gesetztem `DASHSCOPE_API_KEY` greift Qwen |
| Jetzt-Block vorne | `core/ai.py: chat_stream()` | Zerstört den Prompt-Cache (siehe oben) |

### Doku-Drifts

| Was | Datei sagt | Code sagt |
|---|---|---|
| Embedding-Modell | `nomic-embed-text` (768 Dim) — Docstring `core/embeddings.py` | `bge-m3` (Default in `EMBED_MODEL`) |
| Chat-Modell | `qwen2.5:14b` — README | `qwen3.5:9b` (`OLLAMA_MODEL`); CLAUDE.md sagt ebenfalls 9b |

### Zum bewussten Entscheiden

- **README, Zeile 5:** „vollständig offline, keine Daten verlassen das Heimnetz".
  Ein Cloud-Kern bricht das. Der Kern hat `read_file`, `list_files`, `lies_mail`,
  `web_suche`, Kalender — plus Graph im System-Prompt. Es gibt ein
  `memory/betrieb/sicherheit.md`; der Satz gehört bewusst angepasst, nicht stillschweigend.
- **Doppelte Provider-Tabellen** (`core/providers.py` / `tutor/providers.py`) sind
  eine bewusste Entscheidung (2026-07-16), damit `tutor/` rausziehbar bleibt.
  Preis: `base_url`/`key_env` stehen an zwei Stellen. Bei Endpunkt-Änderungen beide prüfen.

---

## 8. Zu löschen beim Umbau

Alles, was gegen Qwen 9B abgesichert hat, macht mit einem starken Modell die
Qualität **schlechter**:

- `SUPPORTS_THINK`, `ADAPTIVE_THINK`, `_should_think()`
- Der qwen3.5-Template-Bug-Workaround (#10976): „nach dem ersten Tool-Call
  think aus, sonst kippt die Antwort ins `thinking`-Feld"
- `QWEN_SAMPLING`, `num_ctx`, `keep_alive`
- Der Großteil der Tool-Beschreibungen. Beispiel `read_calendar`: ~1.700 Zeichen
  Beschreibung, davon fast alles Hand-Holding („Du hast KEINE Termine im
  Gedächtnis", „nie aus dem Kopf raten") plus die komplette Choreografie für
  jeden ⚠-Marker inklusive Eskalations-Knöpfe.

> Die Eskalations-Sequenz gehört ohnehin nach Python, nicht in eine
> Tool-Beschreibung.

Realistisches Ziel: Tool-Schema 21k → 7–8k Zeichen, statische Blöcke 7k → 4k.
Systemblock ~8.000 → ~3.000 Token.

---

## 9. Reihenfolge

1. **Prompt-Cache einrichten** — Systemblock byte-identisch, Jetzt-Block und
   Graph-Kontext ans Ende. Größter Kostenhebel, kleinste Änderung.
2. **`data/ai_graph_cloud.json`** als getrennten Graph anlegen, bevor der erste
   Cloud-Turn läuft.
3. **`core/cloud.py`** schreiben — Event-Protokoll + Erlaubnis-Gate.
4. **`MODULE_BACKENDS["chat"]`** auf `(LOCAL, CLOUD)`.
5. **Aufräumen** — Qwen-Krücken raus, Tool-Beschreibungen eindampfen.
6. **Transkript-Layer** unter den Graph.
7. **Agenda-Store** für die Schemen-Mechanik.
8. Konsolidierung auf Haiku umstellen.
9. Doku-Drifts und README-Offline-Satz nachziehen.

Schritte 1–4 sind das Minimum für „läuft". Der Rest ist Ausbau.
