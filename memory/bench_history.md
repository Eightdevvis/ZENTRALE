# Bench-History — ZENTRALE Testdaten

Zentrale Sammelstelle für **alle** Mess-Läufe. Zweck: Fortschritt über Zeit
nachvollziehbar machen, Doppel-Messungen vermeiden, Hypothesen gegen echte Zahlen
prüfen statt aus Vibes ([[messen-nicht-vibes]]). **Neue Läufe hier unten anhängen**,
nicht überschreiben — auch (gerade!) die Negativ-Ergebnisse.

> ## ⚠ SAMPLING-KORREKTUR (2026-06-08) — wichtig für ALLE Zahlen unten
> Bis 2026-06-08 sendete `bench_calendar_delete.py`/`probe_*` nur `num_ctx` und lief
> damit auf den **Modell-Defaults von qwen3.5:9b: temperature 1, presence_penalty
> 1.5, top_p 0.95** — NICHT auf dem Prod-Sampling. Prod (`chat_stream`) sendet
> `QWEN_SAMPLING` (**temp 0.7**/top_p 0.8/top_k 20/min_p 0/rp 1.05). **Folge:** alle
> Läufe VOR diesem Datum sind temp-1 → viel rauschiger und NICHT prod-treu. Die
> *relativen* Vergleiche innerhalb gleicher Bedingung halten meist; die *absoluten*
> Zahlen sind zu pessimistisch. Beispiel: dieselbe Baseline (think aus, 0.30.6)
> ergab **temp 1 → 42 % Episode, temp 0.7 → 87 % Episode**. Ab 2026-06-08 nutzen
> Bench+Probe `QWEN_SAMPLING` (prod-treu). Zeilen mit „temp1" markiert.

## Test-Umgebung

- PC, RTX 4070 (~12 GB VRAM), Ollama, Default-Modell **qwen3.5:9b** (`num_ctx=8192`,
  Qwen-Sampling). Ollama-Version pro Lauf notieren (Verhalten versionsabhängig!).
- **Bench-Skripte** (`scripts/`):
  - `bench_calendar_delete.py` — 3-Turn-Lösch-/Alarm-Episode (Hauptbench dieser
    Runde). Flags: `--think`, `--adaptive-think`, `--dump`, `--models`,
    `--repeats`; Env `ZENTRALE_DASHVIEW=0/1`.
  - `probe_structured_alarm.py` — Alarm-Verständnisfrage isoliert: Freitext vs.
    JSON-Struktur vs. think.
  - `bench_calendar.py` — Lese-Pfad (read_calendar feuert + Fakten korrekt).
  - `bench_models.py` / `bench_results_*.json` — Modell-Vergleich (Tool-Reliab.,
    tps, VRAM).
  - `bench_ascii.py`, `bench_reasoning.py` — ASCII-Marker bzw. Reasoning.
- Metriken Lösch-Episode: **T1** löschen feuert/ehrlich/ok · **T2** Alarm richtig
  zugeordnet (Geige-Absage, nicht 10-Uhr) · **T3** keine Fehlentwarnung · **Episode**
  alle 3 Turns sauber. Bias-frei (include/forbid), keine temp-Fixierung (echte
  Varianz). Isolierte Fixture, Live-Daten unberührt.

---

## 1. Lösch-/Alarm-Episode (`bench_calendar_delete.py`) — die Hauptstory

qwen3.5:9b. **Sampling** + Ollama-Version je Zeile vermerkt — `temp1` = alte
unfaithfule Modell-Defaults (s. Korrektur oben), `prod` = QWEN_SAMPLING temp 0.7.

| Datum | Konfig | Sampling/Ollama | N | T1 ok | T2 | Episode | Notiz |
|-------|--------|-----------------|---|-------|----|---------|-------|
| 06-07 | Baseline (keine Dashboard-Sicht) | temp1 / 0.17.7 | 10 | 90 % | 30 % | 20 % | Bug lokalisiert (Alarm-Zuordnung) |
| 06-07 | **+ABSAGEN-Zeile** | temp1 / 0.17.7 | 20 | ~90 % | 60 % | 45 % | Daten-Präsentation. ✅ live |
| 06-07 | +KONFLIKT-Zeile umgebaut | temp1 / 0.17.7 | 20 | 80 % | 50 % | 25 % | ❌ schadet T1 → revertet |
| 06-07 | Re-Grounding AN / AUS | temp1 / 0.17.7 | 20 | 85 % | 45/55 % | 25/35 % | Gate ❌ kein Nutzen → revertet |
| 06-07 | qwen2.5:14b | temp1 / 0.17.7 | 15 | 100 % | 67 % | 47 % | 14B≈9B, 5× langsamer |
| 06-08 | think GLOBAL +Sicht | temp1 / 0.30.6 | 12 | 25 % | 8 % | 0 % | global ❌ zerdenkt Aktion |
| 06-08 | ADAPTIV +Sicht | temp1 / 0.30.6 | 12 | 92 % | 92 % | 67 % | sah top aus — aber temp1! |
| 06-08 | ADAPTIV +Sicht (Wdh.) | temp1 / 0.30.6 | 12 | 58 % | 67 % | 25 % | dieselbe Config, halb so gut → **temp-1-Rauschen entlarvt** |
| 06-08 | Baseline +Sicht | temp1 / 0.30.6 | 12 | 67 % | 75 % | 42 % | temp1-Baseline |
| **06-08** | **Baseline +Sicht (think aus)** | **prod / 0.30.6** | 15 | **93 %** | **93 %** | **87 %** | ✅ **prod-treu — Modell viel besser als temp1 zeigte** |
| 06-08 | ADAPTIV +Sicht | prod / 0.30.6 | 15 | 80 % | **93 %** | 73 % | T2 = Baseline (93 %) → **think bringt NICHTS**, Episode-Diff ist T1-Rauschen → **revertet** |

**LEHRE (Kern der Untersuchung 06-08):**
1. Die scheinbare 67→25-„Regression" war **temp-1-Rauschen** (dieselbe Config schwankte
   67↔25), KEIN Ollama-Regress, KEIN kaputtes Thinking. Ursache: Bench maß auf
   Modell-Default temp 1 statt Prod temp 0.7 (s. Korrektur oben).
2. Mit prod-treuem temp 0.7 ist die **Baseline (think aus) schon bei 87 % Episode /
   93 % T2.** Die echten Hebel sind **bessere Daten/Info** (ABSAGEN-Zeile +
   Dashboard-Sicht), nicht Thinking.
3. **Adaptive-think war ein Phantom-Gewinn** aus temp-1-Rauschen — bei korrektem
   Sampling kein Mehrwert (T2 93 % = Baseline) → aus Prod **revertet** (RELEASE folgt).
   `ai._should_think` bleibt als Bench-Helfer, in chat_stream NICHT verdrahtet.
4. Was das Ollama-Update WIRKLICH änderte: native `RENDERER/PARSER qwen3.5` (0.30.6)
   statt Template-Fallback (0.17.7); der think+Tool-Template-Bug (Antwort im
   thinking-Feld) blieb. Aber nichts davon war die „Regression" — das war Sampling.

Die alten temp1-Absolutzahlen (30/60/67…) NICHT für bare Münze nehmen.

### 1b. Hebel-Isolation — sauberes A/B, EIN Rädchen (2026-06-08, prod-treu)

Endgültiger wissenschaftlicher Test: tragen die Hebel bei prod-treuem Sampling
wirklich, oder ist „temp 0.7 eh gut"? Alle Bedingungen **bit-identisch** (qwen3.5:9b,
Ollama 0.30.6, temp 0.7/QWEN_SAMPLING, think aus, num_ctx 8192, Szenario 06-08,
N=20) — pro Variante GENAU ein Rädchen anders. Protokoll P5.

| Lauf | dashview | ABSAGEN | T2 Zuordnung | **Episode** |
|------|----------|---------|--------------|-------------|
| **A** Referenz | AN | neu | **100 %** | **85 %** |
| **B** −Dashboard-Sicht | **AUS** | neu | 75 % | 60 % |
| **C** −ABSAGEN-Umbau | AN | **alt** | 80 % | 60 % |

→ **Beide Hebel tragen echt:** Dashboard-Sicht raus = −25pp Episode, alte ABSAGEN-
Zeile = −25pp Episode. Mit beiden zusammen: **T2-Zuordnung 100 % (20/20).** Die
Sorge „temp 0.7 ist eh nur gut" ist widerlegt — Wegnehmen eines Hebels fällt von
85 % auf 60 %. **Saubere Endbilanz: ABSAGEN-Zeile ✅, Dashboard-Sicht ✅ (beide
isoliert belegt, je ~+25pp); adaptive-think ❌ (Phantom).**

## 2. Alarm-Verständnis isoliert (`probe_structured_alarm.py`)

Nur die T2-Frage „was ist diese Warnung?" mit realistischer (think-aus) Vorantwort,
qwen3.5:9b / 0.17.7, N=15. Misst Freitext vs. JSON-Struktur vs. think.

| Datum | Dashboard-Sicht | Freitext | Struktur (JSON) | think=ON |
|-------|-----------------|----------|------------------|----------|
| 06-07 | aus | 93 % | 53 % | 53 % |
| 06-08 | **an** | 73 % | 67 % | **93 %** |

→ **Dashboard-Sicht entriegelt Thinking (53→93 %).** Struktur (Ollama `format`)
durchweg schlechter als Freitext. (Achtung: isoliert; auf der vollen Episode
zerstört globales Thinking die Aktions-Turns — siehe Tabelle 1.)

## 3. Lese-Pfad Kalender (`bench_calendar.py`, 06-06)

KORREKT = Tool gefeuert + geantwortet + Fakten stimmen.

| Lauf | Konfig | Tool | Antwort | **KORREKT** | s |
|------|--------|------|---------|-------------|---|
| 183825 | qwen3.5:9b think=F | 94 % | 100 % | 68 % | 2,1 |
| 183825 | qwen3.5:9b think=T | 100 % | 42 % | 42 % | 5,5 |
| 183825 | qwen2.5:14b | 100 % | 100 % | 80 % | 8,0 |
| 183825 | qwen3:14b think=F | 100 % | 100 % | 52 % | 2,2 |
| 183825 | qwen3:14b think=T | 100 % | 100 % | 78 % | 18,4 |
| 185537 | qwen3.5:9b think=F **+antwort-tool** | 100 % | 100 % | **78 %** | 2,0 |
| 185537 | qwen3.5:9b think=T +antwort-tool | 100 % | 66 % | 50 % | 5,7 |
| 185537 | qwen2.5:14b +antwort-tool | 92 % | 100 % | 72 % | 7,4 |

→ antwort-Tool hebt 9B think=F 68→78 %. think=T verliert hier die Antwort (alter
content-loss + #10976).

## 4. Modell-Vergleich (`bench_results_*.json`, 06-06)

| Modell | think | VRAM | Tool-Reliab. | Leak | False-Pos | gen tps |
|--------|-------|------|--------------|------|-----------|---------|
| qwen3.5:9b | False | 8,8 GB | 1.0 | 0 | 0 | **68** |
| qwen3:14b | False | 10 GB | 1.0 | 0 | 0 | 47 |
| qwen2.5:14b | – | 10–11 GB | 1.0 | 0 | 0 | 48 |

→ Alle drei tool-reliabel; 9B am schnellsten + sparsamsten → Default-Entscheidung
qwen3.5:9b ([[project_modell_benchmark]]).

## 5. Ollama-Capability-Tests (empirisch, keine JSON)

Was die laufende Ollama-Version kann/nicht kann — versionsabhängig, drum dokumentiert.

| Test | 0.17.7 | 0.30.6 | Notiz |
|------|--------|--------|-------|
| `tool_choice: "required"` erzwingt Tool | ❌ ignoriert | – | Tool-Forcing über API geht nicht |
| DRY-Sampler (`dry_multiplier` …) | ❌ ignoriert | – | greift eh nur within-turn |
| `format` = JSON-**Schema-Objekt** erzwingt Felder | ❌ erfindet eigene | – | nur `format:"json"` greift |
| think=ON, **kein** Tool → content | ✅ 0/3 leer | ✅ 0/3 leer | genereller content-loss WEG |
| think=ON, Synthese **nach** Tool → content | ❌ 3/3 leer | ❌ **3/3 leer** | bleibt kaputt — **Modell-Template**, NICHT Ollama |
| think→OFF nach Tool (Workaround) | ✅ 0/3 leer | ✅ 0/3 leer | rettet die Antwort, in Prod |

> **GEKLÄRT 2026-06-08:** Ollama 0.17.7 → **0.30.6** geupdatet (war 13 Versionen
> zurück). Der think+Tool-Bug bleibt: bei der Synthese-Runde nach einem Tool-Call
> landet die GANZE Antwort im `thinking`-Feld (gemessen: content len 0, thinking
> len 418, `done_reason:stop`), content leer — Streaming wie non-streaming. Das ist
> ein **qwen3.5:9b-Template-Problem** (schließt `</think>` nach Tool nicht), das ein
> Ollama-Update nicht tauscht. **Fix in Prod (commit folgt):** `chat_stream` +
> `run_turn` denken nur BIS zum ersten Tool-Call, danach `think=OFF` für die
> Synthese (`tool_used`-Flag). Reine Verständnis-Turns (kein Tool, z.B. Alarm-Frage)
> denken voll → Boost bleibt; Tool-Verständnisfragen („was steht diese Woche an?")
> bekommen eine nicht-leere Antwort (verifiziert). Echter Template-Fix per Modelfile
> = später, falls Tool-Synthese-Reflexion gebraucht wird.

---

## Protokolle (exakte, reproduzierbare Test-Definitionen)

Damit jede Zahl oben reproduzierbar ist und **alle Parameter übereinstimmen**.

### P1 — Lösch-/Alarm-Episode (`bench_calendar_delete.py`)

**Modell/Sampling:** qwen3.5:9b, `options={num_ctx:8192}` — KEINE temperature (Prod-
Default → echte Varianz, NICHT temp=0). `think` je Konfig (s.u.). Tools = `ai.TOOLS`
(echt ausgeführt via `ai._dispatch_tool`, inkl. antwort/frage_knopf-Handling).

**System-Prompt (1:1 Prod-Pfad, regulärer Chat):** `_now_prompt` + `_SYSTEM_PROMPT`
+ `_CAPABILITIES_PROMPT` + `ANTWORT_SUFFIX` + `_ASCII_MARKER_PROMPT`
+ `_DASHBOARD_VIEW` (nur wenn `ZENTRALE_DASHVIEW≠0`) + Alarm-Block (`_alarm_prompt`).
Graph-`mem_ctx` BEWUSST weg (privat + tool-irrelevant). Pro Turn neu gebaut.

**Fixture** (relativ zu `date.today()` = T, daher datums-robust), isolierte Temp-
Datei, Live-Daten unberührt:
- `termine` an **T+1**: `Flixbus nach Ungarn (Nachtfahrt)`; `Ungarn-Reise` (`bis`=T+5,
  `ort`=Ungarn); `Termin um 10 Uhr` (`time` 10:00).
- `routinen`: `Geigenstunde` (rrule `FREQ=WEEKLY;BYDAY=TU`, 17:45–18:30,
  @Geigenschule, `absage_noetig`); `Fahrschule` (TU,TH 19:00, @Fahrschule).
- `reisezeiten {Geigenschule:{Fahrschule:10}}`, `puffer_min 15`.
- → Initial-Alarme: **KONFLIKT** (10-Uhr-Termin in Reise) + **ABSAGEN** (Geige in Reise).

**Ablauf (3 Turns, History echt = Vergiftung wirkt):**
1. **T1** User: `„lösch bitte den termin um 10 uhr morgen."` → voller Tool-Loop.
2. *Normalisierung* (deterministisch, NICHT vom Modell): `delete_entry(T+1,"Termin um
   10 Uhr")` + Alarme neu → nur noch **ABSAGEN Geige**. (Welt kontrolliert, History
   bleibt echt → Turn 2/3 immer gegen denselben bekannten Alarm.)
3. **T2** User: `„und was ist diese warnung da im dashboard?"`
4. **T3** User: `„den 10-uhr-termin haben wir doch grad gelöscht. wieso steht da noch ne warnung?"`

**Scoring (bias-frei, Substring, case-insensitiv):**
- `GEIGE = [geige, geigenstunde]` · `ABSAGE = [absag, abzusagen, absage, abgesagt]`
- `MISATTRIB = [10 uhr, 10-uhr, 10uhr, lokaler/lokalen/lokale termin]`
- `ALLCLEAR = [alles reibungslos, alles klar, kein konflikt mehr, existiert nicht
  mehr, keine warnung mehr, nichts mehr offen, passt alles, alles gut, läuft alles,
  neustart, alles korrekt, alles in ordnung]`
- **T1 fired** = `delete_calendar_entry` gefeuert. **T1 done** = 10-Uhr weg UND
  Ungarn-Reise+Flixbus noch da. **T1 honest** = NICHT (Erfolg behauptet
  [gelösch/entfern/ist weg/ist raus] UND Termin steht noch). **T1 ok** = fired∧done∧honest.
- **T2 Zuordnung** = `has_all([GEIGE,ABSAGE])` ∧ NICHT `has_any(MISATTRIB)`.
- **T3 keine-Entw.** = NICHT `has_any(ALLCLEAR)`. **T3 surfaces** = `has_all([GEIGE,ABSAGE])`.
- **Episode** = T1-ok ∧ T2-Zuordnung ∧ (T3-surfaces ∧ T3-keine-Entw.).

**Konfig → Befehl → Code-Stand (Git):**
| Zeile (Tab.1) | Befehl | Code-Stand |
|---|---|---|
| Baseline | `python scripts/bench_calendar_delete.py --repeats 10` | vor ABSAGEN-Fix, vor Dashboard-Sicht |
| +ABSAGEN | `… --repeats 20` | `_absage_alarms` umformuliert (commit `898e372`) |
| +KONFLIKT (revert) | `… --repeats 20` | zusätzl. `_conflict_lines`-Umbau (verworfen) |
| Re-Grounding AN/AUS | `…` / `… --no-reground` | `_reground`-Gate (verworfen, nicht im Repo) |
| qwen2.5:14b | `… --models qwen2.5:14b --repeats 15` | wie ABSAGEN |
| think GLOBAL | `ZENTRALE_DASHVIEW=1 … --repeats 12 --think` | + Dashboard-Sicht (commit `20507bd`) |
| ADAPTIV | `ZENTRALE_DASHVIEW=1 … --repeats 12 --adaptive-think` | adaptive `_should_think` (commit `20507bd`) |

### P2 — Alarm-Verständnis-Probe (`probe_structured_alarm.py`)

Pro Durchlauf: Fixture (wie P1) → **echte T1-Löschantwort** via `run_turn(think=False)`
auf `„lösch bitte den termin um 10 uhr morgen."` → als History. Normalisieren
(10-Uhr weg, Alarm = nur Geige-ABSAGE). Dann **T2** `„und was ist diese warnung da
im dashboard?"` in 3 Varianten, gleicher Kontext:
- **Freitext:** normaler Call; Score = `has_all([GEIGE,ABSAGE]) ∧ ¬MISATTRIB` auf content.
- **Struktur:** User-Zusatz „Antworte AUSSCHLIESSLICH als JSON mit Feldern
  welche_aktivitaet/warum/was_du_tun_musst", `format:"json"`; Score = Feld
  `welche_aktivitaet` enthält GEIGE ∧ ¬MISATTRIB, und irgendein Feld enthält ABSAGE.
- **think:** `think:true`; Score wie Freitext auf content (thinking-Feld ignoriert).
Env `ZENTRALE_DASHVIEW=0/1` schaltet die Dashboard-Sicht im System-Prompt. N=15.

### P3 — Lese-Pfad & Modell-Bench

`bench_calendar.py` (Szenarien + Ground-Truth fest im Skript, Stand HEUTE=Sa 06.06.;
KORREKT = Tool gefeuert ∧ nicht-leer geantwortet ∧ Fakten ∧ kein Forbid).
`bench_models.py`/`bench_results` = Tool-Reliabilität über Testfälle + tps/VRAM via
`ollama ps`. Exakte Cases in den jeweiligen Skripten.

### P4 — Ollama-Capability-Tests

Direkte `/api/chat`-Requests, qwen3.5:9b, `num_ctx` klein. Je 3 Läufe, gezählt wird
„content nach Strip leer". think+Tool-Fall: Runde 1 (`think:true`, `tools=ai.TOOLS`,
Frage `„was steht diese woche an?"`) → read_calendar-Call; Tool-Ergebnis anhängen;
Runde 2 (`think:true` = Bug-Fall / `think:false` = Workaround) → content prüfen.
Vergleichs-Fall ohne Tool: `„hauptstadt von frankreich?"`, `think:true`.

### P5 — Hebel-Isolation (ein Rädchen, Tabelle 1b)

Drei Läufe `bench_calendar_delete.py --repeats 20`, alles bit-identisch außer EINEM
Rädchen. Fix für alle: qwen3.5:9b, Ollama 0.30.6, `QWEN_SAMPLING` (temp 0.7),
think aus, num_ctx 8192, Szenario heute (06-08), Scoring wie P1.
- **A (Referenz):** `ZENTRALE_DASHVIEW=1`, ABSAGEN-Zeile neu (Default-Code).
- **B (Knopf Dashboard-Sicht):** `ZENTRALE_DASHVIEW=0` — sonst = A.
- **C (Knopf ABSAGEN-Zeile):** `ZENTRALE_DASHVIEW=1 ZENTRALE_OLD_ABSAGEN=1` — der
  temporäre Mess-Toggle in `_absage_alarms` erzeugte die alte „Routine 'X' liegt in
  Reise Y - Pflicht-Absage"-Zeile; **nach dem Experiment wieder entfernt** (kein
  Prod-Feature). Sonst = A.
Audit vor dem Lauf: effektives `options`-Dict ausgedruckt + verifiziert
(temp 0.7 etc. geht wirklich raus), think False, Szenario-Alarme gecheckt.

---

## Methodik-Standard (WISSENSCHAFTLICH, seit 2026-06-08)

Pflicht für jeden Vergleich (sonst misst man Artefakte — siehe Sampling-Korrektur
oben, [[feedback_messen_nicht_vibes im Memory]]):

1. **Nur EIN Rädchen pro Vergleich.** A vs B unterscheiden sich in GENAU einer
   Variable, alles andere bit-identisch. Nie zwei Knöpfe gleichzeitig.
2. **ALLE Parameter vorher verifizieren** (Audit): das effektive `options`-Dict
   ausdrucken, das WIRKLICH rausgeht — Sampling, num_ctx, think, Modell, Ollama-
   Version, Szenario/Datum, N, Scoring. Nachsehen, nicht annehmen.
3. **Prod-treu sampeln:** EXAKT `ai.QWEN_SAMPLING` (temp 0.7). NICHT temp 0
   (versteckt Varianz), NICHT Modell-Default temp 1 (= nicht Prod).
4. **Datum/Szenario:** die Fixture ist datums-relativ → nur INNERHALB desselben
   Tages vergleichen (an anderem Tag ist das Szenario anders = Confound).
5. **Gleiches N** für alle Bedingungen, hoch genug; Roh-JSON als Audit.

## Wie ergänzen

Nach jedem Bench: passende Tabelle oben um eine Zeile erweitern (Datum, Konfig, N,
Quoten, **Sampling**, Ollama-Version). Bench-Skripte schreiben Voll-JSONs nach
`scripts/bench_*_<stamp>.json` (gitignored) — Kernzahlen hierher übertragen.
Negativ-Ergebnisse SIND Daten — mit rein. Tiefen-Analysen + das „Warum" stehen in
[[grounding_recherche.md]].
