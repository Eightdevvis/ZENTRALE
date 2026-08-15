# Logic-Loop — dialogischer Action-Scaffold fürs lokale 9b (WIP)

> **STATUS: WIP / nur Sketch — NICHT implementiert.** Konzept-Diskussion vom
> 2026-06-14, geparkt bis Sasha daheim an der echten lokalen KI sitzt. Hier
> steht der ganze Denkstand, damit wir nahtlos weitermachen, statt neu
> anzufangen. Vor Implementierung: die offenen Entscheidungsgabeln unten mit
> Sasha klären (kein Alleingang, siehe [[sasha-drives-ux-decisions]]).

## Auslöser

Sashas Beobachtung: das lokale 9b (qwen3.5:9b) „rafft nichts von alleine" —
nutzt Tools schlecht, versteht Kontext schlecht, alles wirkt chaotisch. Kam
auf beim Anschauen von **Observer AI** (github.com/Roy3838/Observer). Befund
dazu: Observer ist architektonisch fast ein Spiegel von ZENTRALE (Sensoren →
Modell → Tools) und macht das Modell **nicht** schlauer — es läuft auf
denselben lokalen Modellen. Löst Sashas Problem also nicht. Der Engpass ist
das **Modell**, nicht die Orchestrierung.

## Die Idee (Sashas Sketch)

Der KI im Kontext eine Notiz geben, dass sie **zwei Gesprächsströme** sieht:

- **`sasha:`** — der Mensch draußen. Seine Antworten sind so gekennzeichnet.
- **`logic:`** — ihr eigenes „Logikverständnis", interner Partner. Robotischer
  als Sasha gekennzeichnet. `logic` fragt die KI, was sie tun will, und lässt
  sie immer ihre nächste mögliche Handlung machen.

Die Pipe ist **hartverdrahtet wie ein Schienensystem** (nicht modellgetrieben):

```
sasha-antwort
   -> ZENTRALE liest sasha-antwort
   -> logic fragt die KI: "was willst du machen?"
   -> KI darf NUR logic antworten (gebundene Wahl)
   -> forced action
```

`logic`-Actions enthalten z.B.: **„sasha antwort geben"**, **„nochmal neu
nachdenken"**, **„kalender-action"**, usw. Dockt bewusst an die alte
`think`-Idee an.

## Einordnung (Claudes Lesart — zur Diskussion, nicht gesetzt)

- **Das ist ein ReAct-Loop mit erzwungenem Action-Space** plus dialogischem
  Framing (`logic:` als zweite Stimme).
- **Strukturell existiert der Loop schon:** `chat_stream` in `core/ai.py` ist
  bereits eine Handlungs-Schleife (`max_rounds=5`); die Tools *sind* der
  Action-Space, ein Tool-Call *ist* die erzwungene Handlung. Heute nur
  implizit.
- **Der eigentliche Hebel ist nicht die zweite Stimme, sondern: eine Sache pro
  Schritt.** Aktuell muss das 9b in EINEM Call gleichzeitig: Kontext verstehen
  + entscheiden ob Tool nötig + Call korrekt formen + Persona halten +
  ASCII-Marker setzen + knapp bleiben + nur Deutsch. Zu viel auf einmal. Der
  `logic`-Schritt ist im Kern ein **Planner/Executor-Split in einem Modell**:
  erst NUR entscheiden, dann NUR ausführen/antworten. Deckt sich mit der
  dokumentierten Lehre „kleine Modelle gut in eng definierten Tasks, schlecht
  im selbst-raffen".
- **`logic` ≠ qwens natives `think`.** `think` = freies, unbegrenztes
  Reasoning. `logic` = **gebundene** Wahl aus einem Menü. Das ist *sicherer*
  als think (s.u. Messlage), weil der Output-Raum klein ist — das 9b kann
  nicht zerdenken, wenn es nur ein Label aus N wählt.

## Think-Stand im Code (Ist-Zustand, belegt aus core/ai.py)

- **Produktiv läuft `think` komplett AUS.** `_think_opts()` (Z. 59) gibt für
  qwen3* hart `{"think": False}` und wird in jeden Chat-Call gespreadt
  (`chat_stream` Z. 1510, `chat` Z. 1400, Warmup Z. 1181). Grund: qwen3.5
  denkt sonst 30–80 s pro Turn → für Voice tödlich.
- **Es gab „adaptive Denk-Tiefe"** (`_should_think`, Z. 230): think nur auf
  Verständnis-/Verifikationsfragen, aus bei Aktions-Befehlen. Code lebt noch,
  ist aber **bewusst nicht verdrahtet** (Z. 1505). Messung 2026-06-08: bei
  korrektem Sampling (`QWEN_SAMPLING`, temp 0.7) **kein** Mehrwert — Baseline
  schon bei 93 % (T2-Zuordnung) / 87 % (Episode), siehe `memory/ki/bench_history.md`.
  Der frühere „adaptive Gewinn" war ein temp-1-Mess-Artefakt.
- **Zwei gemessene Fakten, die direkt auf den Sketch zielen:**
  1. `think=ON global auf Aktions-Turns = Desaster` — das 9b **zerdenkt**
     Lösch-/Schreib-Aktionen (Episode 0 %, `bench_calendar_delete.py`).
     `think=ON isoliert auf einer Verständnisfrage = stark` (+40pp mit
     Dashboard-Sicht). → spricht FÜR Sashas gebundene Variante statt freies think.
  2. **`think+Tool-Template-Bug`** — think und Tool-Calls zusammen ist kaputt
     im Template (Z. 1506). **Konsequenz:** der `logic`-Kanal darf NICHT qwens
     natives `think` benutzen, wenn er Tools auslöst.

## Offene Entscheidungsgabeln (mit Sasha klären, BEVOR Code)

1. **logic-Mechanik:** eigener Mini-LLM-Call (sauberer Split, +1 Round-Trip
   Latenz) **vs.** Framing im selben Call (billig, aber 9b muss zwei Rollen
   selbst trennen — fehleranfälliger bei genau einem schwachen Modell).
2. **Action-Space:** enges festes Enum (der eigentliche Robustheits-Gewinn,
   „antworten / neu nachdenken / kalender / datei lesen / web-suche") **vs.**
   die bestehende `TOOLS`-Liste (weniger Neubau, näher am Status quo, Gewinn
   unsicherer).
3. **Scope erster Schritt:** Prototyp NEBEN dem jetzigen Pfad + A/B-Bench gegen
   die 93/87-Baseline (reversibel, erst messen) **vs.** `chat_stream` direkt
   umbauen (schneller, aber riskiert die stabile Baseline ohne Messung).

> Claudes Tendenz (nicht entschieden): eigener Mini-Call + enges Enum +
> Prototyp-mit-Bench-zuerst. Begründung: maximiert den Stage-Split-Gewinn fürs
> 9b und ist reversibel/messbar. Sasha entscheidet.

## Risiken (konkret in diesem Code)

- **Latenz:** jeder sasha-Turn wird ≥2 LLM-Calls. Für Voice *die* sensible
  Achse. logic-Call winzig halten (`num_predict` klein, kein Streaming).
- **8k-Kontext:** zwei Streams interleaved fressen Tokens. logic-Turns
  vermutlich aus der sichtbaren History droppen/zusammenfassen — sonst
  verdrängen sie die Sprach-Regel (das „Chinesisch blutet durch"-Problem,
  s. `memory/ki/ki_system.md` / `OLLAMA_NUM_CTX`).
- **Persona-Bleed:** zwei Sprecher in einem Fenster → Risiko, dass der KI
  `logic`s robotischer Ton an Sasha durchrutscht oder sie verwechselt wer was
  sagte. Dieser Codebase kämpft schon dokumentiert gegen Identity-Bleed /
  Subjekt-Grenze (`_CAPABILITIES_PROMPT`, Graph nach Subjekt getrennt).
- **Reinvention-Falle:** nutzt logic einfach die freie Tool-Liste, ist es der
  jetzige Loop mit Extra-Schritten. Gewinn kommt NUR bei engem, explizitem
  Action-Space.
- **Muss gemessen werden:** „hilft das logic-Framing dem 9b?" ist empirisch.
  Ohne A/B gegen 93/87 wissen wir nicht, ob besser ODER schlechter. Bench-
  Kultur ist da (`scripts/bench_*.py`, `memory/ki/bench_history.md`) — nutzen.

## Nächster Schritt (wenn Sasha daheim ist)

1. Die drei Gabeln oben entscheiden.
2. Je nach Scope: Prototyp-Funktion neben `chat_stream` ODER Umbau planen.
3. Bench-Harness gegen die bestehende Baseline aufsetzen, dann erst breit.
