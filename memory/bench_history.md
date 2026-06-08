# Bench-History — ZENTRALE Testdaten

Zentrale Sammelstelle für **alle** Mess-Läufe. Zweck: Fortschritt über Zeit
nachvollziehbar machen, Doppel-Messungen vermeiden, Hypothesen gegen echte Zahlen
prüfen statt aus Vibes ([[messen-nicht-vibes]]). **Neue Läufe hier unten anhängen**,
nicht überschreiben — auch (gerade!) die Negativ-Ergebnisse.

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

qwen3.5:9b, Ollama 0.17.7, sofern nicht anders vermerkt. Quoten in % (N variiert).

| Datum | Konfig | N | T1 ok | T2 Zuordn. | T3 keine-Entw. | **Episode** | s/Turn | Notiz |
|-------|--------|---|-------|-----------|----------------|-------------|--------|-------|
| 06-07 | Baseline (think aus, keine Dashboard-Sicht) | 10 | 90 % | **30 %** | 90 % | **20 %** | 3,0 | Bug lokalisiert: nicht Löschen/Ehrlichkeit, sondern Alarm-Zuordnung |
| 06-07 | **+ABSAGEN-Zeile umformuliert** | 20 | ~90 % | **60 %** | 95 % | **45 %** | 3,0 | Daten-Präsentation: Zuordnung verdoppelt. ✅ live |
| 06-07 | +ABSAGEN +KONFLIKT-Zeile umgebaut | 20 | 80 % | 50 % | 95 % | 25 % | 3,5 | KONFLIKT-Umbau ❌ schadet T1 → **revertet** |
| 06-07 | +Re-Grounding-Gate AN | 20 | 85 % | 45 % | 95 % | 25 % | 3,4 | A/B-Gate |
| 06-07 | +Re-Grounding-Gate AUS | 20 | 85 % | 55 % | 100 % | 35 % | 3,6 | Gate bringt nichts → ❌ revertet |
| 06-07 | **qwen2.5:14b** (Modellwechsel-Test) | 15 | 100 % | 67 % | 100 % | 47 % | 14,5 | 14B ≈ 9B, 5× langsamer → Modell NICHT der Hebel |
| 06-08 | think GLOBAL + Dashboard-Sicht | 12 | **25 %** | **8 %** | 100 % | **0 %** | 16,3 | Thinking global ❌ zerdenkt Aktions-Turns |
| 06-08 | **ADAPTIV-think + Dashboard-Sicht** | 12 | **92 %** | **92 %** | 100 % | **67 %** | 5,8 | ✅ **bester Stand, live (RELEASE 30)** |

**Trajektorie T2-Zuordnung: 30 → 60 → 92 %. Episode: 20 → 45 → 67 %.** Drei Hebel,
alle „bessere Eingaben / gezielte Reflexion", keine globalen Tricks:
1. ABSAGEN-Zeile (Daten-Präsentation), 2. Dashboard-Sicht (KI kennt ihr UI),
3. adaptive Reflexion (think nur auf Verständnisfragen).

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

| Test | Ollama 0.17.7 | Notiz |
|------|---------------|-------|
| `tool_choice: "required"` erzwingt Tool | ❌ ignoriert | Tool-Forcing über API geht nicht |
| DRY-Sampler (`dry_multiplier` …) | ❌ ignoriert | greift eh nur within-turn |
| `format` = JSON-**Schema-Objekt** erzwingt Felder | ❌ erfindet eigene | nur `format:"json"` greift |
| think=ON, **kein** Tool → content | ✅ 0/3 leer | genereller content-loss-Bug WEG |
| think=ON, Synthese **nach** Tool → content | ❌ **3/3 leer** | Bug #10976 (Template schließt `</think>` nicht) |
| think→OFF nach Tool (Workaround) | ✅ 0/3 leer | rettet die Antwort |

> **OFFEN:** Ollama-Update 0.17.7 → **0.30.6** läuft (2026-06-08). Danach Tabelle 5
> Zeile „think+Tool" neu messen — wenn ✅, kann adaptive Reflexion think auf ALLEN
> Runden lassen (kein Workaround). Latest-Version: 0.30.6 (release 2026-06-05).

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

---

## Wie ergänzen

Nach jedem Bench: passende Tabelle oben um eine Zeile erweitern (Datum, Konfig, N,
Quoten, Ollama-Version). Bench-Skripte schreiben Voll-JSONs nach `scripts/
bench_*_<stamp>.json` — Kernzahlen hierher übertragen, das JSON kann weg (oder als
Audit-Spur bleiben). Negativ-Ergebnisse SIND Daten — mit rein. Tiefen-Analysen +
das „Warum" stehen in [[grounding_recherche.md]].
