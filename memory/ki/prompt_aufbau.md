# System-Prompt, Schienen und Prompt-Cache

**Stand 2026-10-11:** Zwei Prompt-Schienen (`core/profil/`): `klein` für das
lokale qwen (Kanon, unverändert gemessen), `gross` für Frontier-Modelle (Persona
aus `klein` abgeleitet, eigene Meta-Regeln). Reihenfolge: erst alles Statische
(gecacht, Breakpoint `ttl: 1h`), das Wechselnde (Jetzt, Imprint, Alarme, Mic,
offene Zusagen) im Umschlag `<kontext_automatisch>` hinten an der neuesten
Nachricht. Der Nutzer steht als Platzhalter im Prompt (`nutzer_name`,
`nutzer_pronomen`). Prompt ansehen: `scripts/prompt_zeigen.py`.
Wonach der Prompt gebaut werden soll (Länge, Aufbau, Ton): KI-Bibel
[bibel/prompt.md](bibel/prompt.md).

**Warum:** Cache-Treffer kosten 10 % — der größte Kostenhebel; die Uhrzeit vorn
hatte den ganzen Verlauf ungecacht gemacht. Ein Prompt für 9B und Frontier war
für beide Ballast. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

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
   2026-08-18** (nur mit `ZENTRALE_GRAPH_KONTEXT=1`, `ki_prompt.GRAPH_KONTEXT`); der
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

## Prompt-Cache

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

## Prompt-Cache: statisch vorn, Wechselndes ganz hinten

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

## Zwei Schienen: `core/profil/`

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
Werkzeug-Register (siehe „Das Werkzeug-Register" in [werkzeuge.md](werkzeuge.md)); die Schiene sagt nur
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

### Den Prompt einer Schiene ansehen — `scripts/prompt_zeigen.py`

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

## Prompt-Budget und Werkzeug-Beschreibungen (seit 2026-10-14)

**Budget:** der feste System-Prompt der großen Schiene (`cloud._static_system`:
Schiene `gross` + Gedächtnis-Kopf + Skill-Liste + Imprint) darf höchstens
**21.000 Zeichen** lang sein (`PROMPT_BUDGET_ZEICHEN` in
`tests/test_prompt_budget.py`). Maßstab ist Anthropics eigener
claude.ai-Prompt für Sonnet 5.5: ~20.300 Zeichen ohne Werkzeuge (Stand
28.09.2026). Ein Assistent für einen Menschen braucht keinen längeren Prompt
als eine Chat-App für alle. Die Werkzeuge zählen nicht mit — der Test gibt
ihren Umfang nur aus (`pytest -s tests/test_prompt_budget.py`), denn sie
sollen später über einen Index kommen (nur die passenden im Kopf).

Gemessen am 14.10.2026 (mit Sashas echtem Gedächtnis, Imprint 1.110 Zeichen):

| | vorher | nachher |
|---|---|---|
| Schiene `gross.system()` | 4.966 | 4.775 |
| Gedächtnis-Kopf (Steckbrief, Ziele, Index, Regeln) | 7.645 | 7.353 |
| Skill-Liste | 5.773 | 5.773 |
| **fester Prompt gesamt** | **19.500** | **19.017** |
| Werkzeug-Schema (71 Werkzeuge, JSON) | 47.180 | 47.180 |

In der Test-Umgebung (leeres Gedächtnis, leerer Kalender) sind es ~11.700
Zeichen — der Test greift also erst, wenn der Code-Anteil um ~9.000 Zeichen
wächst; Sashas Notizen kommen im Betrieb obendrauf.

**Werkzeug-Beschreibungen sind laut Anthropic der wichtigste Hebel** für gutes
Werkzeug-Verhalten — wichtiger als Regeln im Prompt. Jede Beschreibung hat
3–4 Sätze: was das Werkzeug tut, wann man es benutzt und wann nicht, und was
es *nicht* liefert. Eine Regel, die nur ein Werkzeug betrifft, gehört in
dessen Beschreibung, nicht in den Prompt (Beispiel: „Jede Antwort über
`antwort`" stand bis 14.10. doppelt — in Meta-Regel 2 und in der
Beschreibung; jetzt nur noch dort).

**Aufgeräumt am 14.10.2026** (Ballast raus):
- doppelt: „Kein Dienstbotentum" stand in der Persona und im Steckbrief →
  nur noch in der Persona (vollständiger, für beide Schienen, getestet);
  „Jede Antwort über antwort … in auftrag abgerechnet" → nur im Werkzeug.
- veraltet: Satz über Linux-PC und Wand-Monitor (Pi 3) → aus `gross`
  geschnitten (`_ohne_satz`), `klein` behält ihn (Turn-Beispiel hängt
  daran); „Morgens: Schlafdaten" im Steckbrief (Morgen-Messenger seit 14.09.
  weg); Meta-Regel 2 „mit Titel, Tag und Uhrzeit" → allgemein „woran er es
  wiedererkennt"; Imprint-Text mit Platzhaltern statt „Sasha".
- Großbuchstaben-Befehle auf `gross` in normale Schreibung (EINE, WO, im
  Imprint NUR/EINMAL/KEIN über `imprint_for_prompt(betont=False)`, im
  Umschlag `<kontext_automatisch>` NICHT) — Anthropic rät davon ab, aktuelle
  Modelle befolgen sie überzogen. `klein` bleibt in Großbuchstaben (so ist
  das qwen gemessen). Noch offen: Großbuchstaben in einigen gross-
  Werkzeug-Beschreibungen (antwort, run_code, save_from_sandbox, Kalender-
  Phasen/Routinen) und im Alarm-Block (`ki_prompt._alarm_prompt`, geteilt
  mit klein, verweist dazu noch aufs Dashboard und `[[bild: alarm]]`).
- Steckbrief: der Satz „…der Grund, warum eine Antwort manchmal gegen den
  spontanen Wunsch geht" ist raus (Idee dahinter: [zukunftsvisionen.md](zukunftsvisionen.md)).

## Der Nutzer im Prompt — `core/nutzer_angaben.py` (seit 2026-10-09)

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
(Pi 3)" und das Turn-Beispiel beschreiben Sashas Geräte — seit 2026-10-14
nur noch auf `klein` (dort gemessen, unverändert).

## Historie

- **2026-05-31** — `num_ctx` explizit (Ursache des „Chinesisch-Durchblutens").
- **2026-06-06** — Graph-Kontext nach Subjekt getrennt gerendert.
- **2026-08** — Prompt-Cache statisch vorn, Wechselndes hinten; zwei Schienen
  (Präfix 4.630 → 2.587 Token).
- **2026-10-06** — `klein` bekommt Meta-Regeln ohne Graph.
- **2026-10-08** — Umschlag `<kontext_automatisch>`.
- **2026-10-09** — Werkzeug-Spur im Verlauf; Nutzer als Platzhalter.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
- **2026-10-14** — Ballast raus (Doppeltes, Veraltetes, Großbuchstaben auf
  gross), Prompt-Budget 21.000 Zeichen mit Wächter-Test.
