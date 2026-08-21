# Cloud-KI und ihre Umgebung — Bericht vom 21.08.2026

Ein Zwischenstand, kein Handbuch: was der Umstieg auf die Cloud gebracht hat,
woran es hakte, was dagegen unternommen wurde und was offen ist. Die
technischen Einzelheiten stehen in [ki_system.md](ki_system.md) und
[gedaechtnis_dateien.md](gedaechtnis_dateien.md); hier steht der Verlauf.

## Wo es steht

Der Chat denkt seit dem 15.08.2026 **cloud-only** (`chat_backend: cloud`,
bewusst gesetzt, daheim wie unterwegs). Chat auf Sonnet 5, Verdichtung auf
Haiku 4.5.

**August bis zum 21.: 1,86 € auf 175 Aufrufe** (`data/ai_usage.json`), bei
einem Monatsdeckel von 5 € und einem Ziel von höchstens 20 €. Der teuerste Tag
war der 18.08. mit 1,14 € auf 105 Aufrufen — ein Bau-Tag, kein Nutzungstag.

## Was gebaut wurde

**Der Kern.** `core/cloud.py` ist ein Drop-in für `ai.chat_stream()` — gleiche
Signatur, gleiches Event-Protokoll, gleiches Erlaubnis-Gate. Getauscht wurde
genau eine Sache: **wer entscheidet, welches Werkzeug läuft.** Ausgeführt wird
weiter lokal; Whisper, TTS, Kalender, Mail bleiben unberührt. Dazu ein zweiter
Dialekt (`core/cloud_openai.py`) für qwen/openai/mistral. Die *Bedeutung* eines
Tool-Calls — was terminal ist, was durchs Gate muss — steht genau einmal, in
`cloud.run_tool()`; die beiden Loops unterscheiden sich nur in der Verpackung.

**Isolation.** Der Cloud-Pfad hat einen eigenen Graphen. Lokal sieht alles von
Cloud, Cloud nichts von lokal. Live bestätigt: 23 neue Knoten cloud-seitig, der
Kern-Graph mit 168 Knoten unangetastet.

**Der Prompt-Cache** — der mit Abstand größte Kostenhebel. Vorher saß die
Uhrzeit im `system`-Feld und invalidierte damit alles dahinter; gemessen
`in=7236 cache_read=0` für eine Drei-Wort-Antwort. Jetzt: Statisches vorn mit
Breakpoint, Wechselndes als letzter Block der neuesten User-Nachricht. Gemessen
danach über drei Turns: **3,09 ct → 0,24 ct → 0,25 ct.**

**Zwei Prompt-Schienen** (`core/profil/`). Ein 9B und ein Frontier-Modell
teilten sich einen Prompt, und jede Anpassung für das eine war Ballast für das
andere — bei jedem Turn und jeder Tool-Runde. Jetzt hat jedes seine eigene,
zurückzutauschen per Konfigurationszeile.

**Das Gedächtnis wurde ersetzt.** Der Konzept-Graph zerhackte Sprache in
Tripel; an seiner Stelle stehen Markdown-Dateien in drei Sorten — Dossiers
(Prosa), Kataloge (kurze Einträge mit Status), Quellen. Der Kopf-Block liegt im
gecachten Prompt, Inhalte nur auf Abruf. Prompt jetzt graph-frei: 817 Token,
gecachter Kopf 1.724.

**Sichtbarkeit.** Das Devtools-Terminal (`scripts/ai_devtools.py`) zeigt live,
was wirklich rausgeht — voller Prompt, Tool-Schemata *mit* Beschreibungen, wo
die Cache-Breakpoints sitzen, `cache_read`/`cache_write` pro Runde. Seit dem
20.08. stehen Tool-Calls und Denken zusätzlich **im Chat selbst**.

**Der Takt.** Sie erinnert von selbst an Termine, 60 und 30 Minuten vorher, mit
Nachtruhe und Mindestabstand, jeder Anstoß genau einmal — überlebt einen
Neustart. Zustellung in die TUI inklusive Punkt im Kasten-Titel, wenn der
Kasten zu ist.

**Anwesenheit.** Drei Lagen per Code gemessen (Leerlaufzeit + Bildschirmsperre):
ZENTRALE offen / zu, aber er ist da / niemand da. Das entscheidet Ton **und**
Kanal. Die KI bekommt daraus einen Satz, keine Sensordaten.

**Prüfstand.** `scripts/pruefstand.py`, 17 Live-Prüfungen gegen das echte
Modell, vollständig isoliert (per SHA1 belegt, kein Byte unter `data/`
angefasst). Abnahme 18.08.: 17/17, 0,19 €.

## Die Schwierigkeiten — und was dagegen lief

**Die API hat Fallen.** `temperature`/`top_p`/`top_k` → 400.
`thinking: {budget_tokens}` → 400, Steuerung nur über `effort`. `max_tokens`
deckelt Denken **und** Antwort zusammen. Und der teuerste: `thinking: disabled`
schreibt Tool-Calls gelegentlich als Fließtext statt als `tool_use`-Block — der
Call läuft dann nie, **ohne Fehler**. Deshalb bleibt Denken überall an,
notfalls auf `effort: low`. Haiku quittierte `effort` mit 400; die
Budget-Rückfallebene wäre kaputt statt billig gewesen.

**Haiku bleibt nach einem `write_note` stumm** (2 Token), Sonnet antwortet
richtig. Die Billigstufe taugt für Mechanik, nicht für Gespräch — das begrenzt,
was sich aus Kostengründen nach unten schieben lässt.

**Sie nervte.** Sie zählte alle paar Minuten runter, wie lange es noch bis zum
Termin ist. Die Ursache war nicht der Ton, sondern dass die **Uhrzeit im Prompt
stand**: wer eine Uhr vor sich hat, rechnet. Uhr raus, `read_time` als Werkzeug
rein — das Verhalten war weg, ohne eine einzige Ermahnung im Prompt.

**Sie legte dieselbe Sache doppelt ab.** Erst ein sauberer Katalog-Eintrag,
dann Prosa in dieselbe Datei, beide Male nur „steht drin". Von außen sah der
erste Satz aus wie eine Lüge. Dagegen: Katalog-Einträge upserten statt
anzuhängen, Prosa wird vom Katalog abgewiesen, wörtlich Gleiches wird gemeldet
statt geschrieben, und eine Sperre gegen dieselbe Sache an zwei Orten.

**Sie meldete Erfolge ohne Deckung.** Dagegen der Nachprüf-Schritt vom 20.08.:
der Beweis steht im **Werkzeug-Ergebnis**, das ohnehin ans Modell zurückgeht —
Nachprüfung ohne einen einzigen zusätzlichen Aufruf.

**Der Erzähltag war nicht der Ereignistag** — die Frage nach Sport erzeugte
„Sport hat heute stattgefunden". Der Kalender-Spiegel wurde ersatzlos gelöscht
(er war ein Schreibweg am Erlaubnis-Gate vorbei), die Zeit bekam vier Stufen
(Tag/Woche/Monat/Jahr), falsch datierte Kanten wurden aus den echten Daten
entfernt.

**Das Muster über alle diese Fälle:** eine Prompt-Anweisung ist eine **Bitte**,
Code ist eine **Tatsache**. Jedes Mal, wenn eine Regel durch eine Garantie
ersetzt wurde, wurde das Verhalten besser — und der Prompt kürzer.

## Was offen ist

- **Anwesenheitspings** — Morgengruß beim ersten Kontakt, Check-in nach
  längerer Abwesenheit. Das Signal steht (`anwesenheit.da()`), die Auslöser
  nicht.
- **Kosten mit Takt gegen ohne halten** — jeder Anstoß ist ein Modellaufruf;
  gemessen ist das noch nicht.
- **Opus gegen Sonnet vergleichen**, jetzt wo die Kosten unten sind.
- **Cache-TTL entscheiden** (1 h schreibt zu 2×, 5 min zu 1,25×) — braucht eine
  Woche echte Nutzung, dann anhand `data/ai_usage.json` entscheiden.
- **qwen-Krücken aus `core/ai.py` raus** (`SUPPORTS_THINK`, `ADAPTIVE_THINK`,
  Template-Workaround, `QWEN_SAMPLING`) — sie machen ein starkes Modell dümmer.
- **Der lokale Pfad sendet keine `werkzeug`-Ereignisse** — die Transparenz im
  Chat gibt es bisher nur cloud-seitig.
- **Modulhandbuch und Stundenplan fehlen**, `kataloge/module` bleibt bis dahin
  leer. Dazu: `fetch_document` nimmt nur http(s) — ein lokal hingelegtes PDF
  kann sie **nicht** lesen.
- **Schemen** (Wochenpläne, gezogen aus Kalender, Dossiers, Ideen, Pflichten) —
  der nächste große Schritt; wartet bewusst auf Daten aus dem Takt.
- Die Systemeinheit ist auf PC und Pi noch nicht eingerichtet.

## Kurz

Der Umstieg auf die Cloud hat das Projekt nicht an der Architektur
weitergebracht, sondern daran, dass die ganze Absicherung gegen ein zu
schwaches Modell wegfallen konnte. Was danach übrig blieb, waren keine
Modellprobleme mehr, sondern **Umgebungsprobleme**: Uhrzeit an der falschen
Stelle, mehrdeutige Ablage, unsichtbare Schritte, unbewiesene
Erfolgsmeldungen. Genau die sind vom 18. bis 20.08. der Reihe nach geschlossen
worden.

Die Kosten sind dabei kein Thema mehr.
