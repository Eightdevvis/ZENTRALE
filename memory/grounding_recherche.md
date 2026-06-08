# Grounding-Recherche: „nicht raten, nachschauen"

Warum schreibt sich das hier auf: Die zwei Kalender-Symptome (KI **rät** statt
das Tool zu rufen; KI fällt in **nicht-rettbare Wiederholungs-/Verteidigungs-
Spiralen**) sind Spezialfälle EINER allgemeinen Krankheit kleiner Modelle: sie
wählen den bequemen Pfad (konfabulieren) statt des korrekten (Tool/Daten nutzen),
obwohl der Zugang da ist. Diese Datei sammelt, was die Recherche dazu gefunden
hat — als Grundlage für die nächsten Architektur-Entscheidungen.

> **Status (2026-06-07):** Erster Recherche-Lauf (Deep-Research-Harness, 26
> Quellen, 25 Claims 3-fach adversarial verifiziert, 13 bestätigt). Lief stark
> **paper-/arXiv-lastig** und ist in der Verifikationsphase teils ins API-Rate-
> Limit gelaufen → halber Lösungsraum noch offen (siehe unten). **Zweiter Lauf
> geplant mit MAKER-Fokus** (Praktiker, die ihr lokales 7-9B real zum
> zuverlässigen Tool-Nutzen gebracht haben — r/LocalLLaMA, HN, Indie-Blogs,
> GitHub), nicht Akademik.

## Ursachen (gut belegt)

1. **Raten ist antrainiert, kein Zufallsfehler.** Modelle werden als „gute Test-
   Taker" optimiert. Bei binärer Bewertung (1 richtig / 0 alles andere inkl.
   „weiß nicht") maximiert RATEN den erwarteten Score, solange Trefferchance > 0
   — Abstainen wird systematisch bestraft. Das ist „Bequemlichkeit" auf der
   Trainings-Ebene. *(Kalai et al. arXiv 2509.04664 [OpenAI]; Wu et al.
   2512.19920 — beide 3-0)*

2. **„Knowing-Doing-Gap": sie WEISS, dass ein Tool nötig wäre, tut's aber nicht.**
   Der Fehler sitzt im Übergang **Kognition → Aktion**, nicht im Erkennen.
   Intern ist „hier müsste ich nachschauen" dekodierbar, aber die Token-Schicht,
   die die nächste Aktion treibt, läuft fast orthogonal dazu. Exakt das
   beobachtete „Zugang da, ruft aber nicht". *(Cheng/Feizi et al. arXiv
   2605.14038 — 3-0, medium: frischer Preprint)*

3. **Größenordnung — trifft genau unsere Modellklasse.** Kleine Modelle (3B–8B,
   Qwen/Llama) entscheiden den Tool-Einsatz **26,5–54 %** der Zeit falsch
   (Arithmetik), **30,8–41,8 %** bei Faktenfragen. Qwen3-4B: 41,8 % Fehl bei
   Fakten. *(2605.14038 — 3-0)* → **die wichtigste Zahl für unsere Architektur.**

## Verifizierte Hebel (nach Aufwand)

| Hebel | Wirkung | Aufwand | Grenze |
|---|---|---|---|
| **GBNF/JSON-Schema-Forcing** (llama.cpp/Ollama) | erzwingt das Tool-Call-**Format** deterministisch (nie kaputtes JSON) | 🟢 sofort | nur Format, nicht die *Entscheidung* zu rufen |
| **Semantic Entropy Probes (SEP)** | Halluzinations-Signal aus Hidden States EINER Generation → fast gratis ein Confidence-Score als Nachschau-Trigger | 🟡 mittel | braucht interne Aktivierungen, **nicht** über Ollama-API |
| **Chain-of-Verification (CoVe)** | Draft → Prüffragen → final; senkt Halluzinationen über mehrere Aufgaben | 🟡 mittel (Prompt-Loop) | Detailmechanik unverifiziert |
| **Behaviorally Calibrated RL** | trainiert *stochastisches Abstainen* via proper scoring rules (Gegenentwurf zu Ursache 1) | 🔴 hoch (RL/LoRA) | voller Trainingsaufwand |

*(GBNF: llama.cpp grammars-Repo 3-0; SEP: arXiv 2406.15927 3-0; CoVe: 2309.11495
2-0; Behav-RL: 2512.19920 3-0)*

## Synthese für ZENTRALE

**Die 26–54 %-Zahl ist ein Evidenz-Argument FÜR die deterministische Linie** und
validiert das bestehende Auto-Gate ([[feedback_permission_gate_backend]]):

> Wenn ein 9B die *Entscheidung* „brauche ich hier ein Tool?" empirisch jede
> zweite bis vierte Mal verkackt, ist es **kein Knebel, sondern Physik**, ihm
> diese Entscheidung abzunehmen. **Pol B (Python/Router erzwingt den Lookup)** ist
> bei dieser Modellgröße die robustere Wahl — das **Modell formuliert weiterhin
> selbst** ([[feedback_python_model_labor]] bleibt intakt), aber das *ob-
> nachschauen* triggert Python, nicht das Modell.

Gestaffelter Fahrplan:
1. 🟢 **Sofort:** bei zeitlichen/faktischen Fragen `read_calendar` (bzw. das
   passende Tool) **deterministisch erzwingen** (Router/Klassifikator vor dem
   Turn) statt zu hoffen, dass sie selbst greift. Format per GBNF absichern.
2. 🟡 **Mittel:** Confidence-Signal (SEP-artig) als Trigger — braucht direkten
   llama.cpp-Pfad statt Ollama-API. Größere Baustelle.
3. 🔴 **Später:** Abstention/Tool-Use ins Modell fine-tunen
   ([[ki_personality_plan.md]]), wenn der Rest ausgereizt ist.

## Maker-Leads (Lauf 2, 2026-06-07) — UNVERIFIZIERT (Rate-Limit)

Lauf 2 lief mit Maker-Fokus (Docker-Eval, Ollama-Lib/-Blog, Gorilla-BFCL,
oobabooga-DRY-PR, HF-Cookbook) — die Verifikationsphase ist aber komplett ins
API-Rate-Limit gelaufen (alle 25 Claims „0-0 Abstain", NICHT widerlegt, nur
ungeprüft). Die extrahierten Claims sind brauchbare Leads, aber **noch nicht
gegengeprüft** — vor dem Bauen die wichtigen selbst per WebFetch verifizieren.

**Drei richtungsändernde Leads:**

1. **Qwen3 ist schon top für lokales Tool-Calling — Modell-Swap ist vermutlich
   NICHT der Hebel.** Docker-Praxis-Eval (21 Modelle, 3.570 Testfälle): qwen3:14B-
   Q4_K_M = 0,971 F1 (bestes, nahe GPT-4), qwen3:8B F16 = 0,933, Q4_K_M = 0,919.
   Unser qwen3.5:9b ist also eine gute Basis → der Bug ist Architektur/Verhalten,
   nicht „falsches Modell". *(docker.com/blog/local-llm-tool-calling-a-practical-
   evaluation, unverifiziert)*
2. **Spezialisierte Function-Calling-Fine-Tunes waren SCHLECHTER, nicht besser:**
   watt-tool-8B 0,484 F1, xLAM-8B 0,570 — weit unter generischem Qwen3/Llama3.1.
   → die teuren FC-Tunes NICHT hinterherjagen; generalistisches Qwen3 schlägt sie.
   *(gleiche Docker-Eval, unverifiziert)* Widerspricht der naiven „nimm ein FC-
   getuntes Modell"-Intuition — wichtig.
3. **DRY-Sampler gegen die Wiederholungs-Spirale.** Klassische repetition/
   frequency-Penalties verhindern wörtliches Loopen NACHWEISLICH nicht — genau die
   Lücke, die DRY (Don't Repeat Yourself, sequenz-basierte Strafe + sequence-
   breaker-Tokens) schließt. Direkt gegen das „wiederholt denselben Absatz
   wörtlich". *(oobabooga PR 5677, unverifiziert)* **OFFEN: unterstützt Ollama
   DRY?** (llama.cpp ja; Ollama exponiert `repeat_penalty`, DRY-Support prüfen.)

**Weitere Leads:**
- **Ollama Structured Outputs sofort nutzbar:** `format`-Param nimmt ein JSON-
  Schema (Pydantic/Zod), + „return as JSON" im Prompt + temperature 0 →
  deterministisches, well-formed Tool-Arg-Format. *(ollama.com/blog/structured-
  outputs)* — der 🟢-sofort-Hebel für die Format-Komponente.
- **QLoRA möglich, aber eng auf 12 GB:** xLAM-function-calling-60k-Datensatz; HF-
  Cookbook empfiehlt 16 GB+ (24 GB ideal), ein Llama-3.1-8B-QLoRA passt mit Unsloth
  load_in_4bit aber in ~12–14 GB → auf der 4070 grenzwertig machbar.
- **BFCL hat eine „Relevance Detection"-Kategorie** (misst, ob das Modell KEINEN
  Call macht, wenn keine Funktion passt) — ein fertiger Abstention-Benchmark.
- Ollama-`tools`-Label-Modelle in 12-GB-Reichweite: Qwen2.5-7B/14B, Hermes3-8B,
  Command-R7B, Llama3.1-8B (meist-gepullt). Qwen3 trägt zusätzlich `thinking`.

**Noch ECHT offen (auch Lauf 2 nicht geklärt):**
- Self-RAG / FLARE / Adaptive-RAG real bei <14B — Paper-Ware oder nutzbar?
- Pol A vs Pol B konkret (Router-erzwingt vs. Modell-entscheidet) + Hybride aus
  echten lokalen Agent-Setups (LangGraph/LlamaIndex/Eigenbau).
- Anti-Sycophancy-/History-Trimming-Rezepte gegen Antwort-Perseveration.

**Konsequenz für die Richtung:** Lead 1+2 nehmen den „besseres Modell / FC-Tune"-
Pfad vom Tisch (Qwen3 ist schon gut). Bleiben die billigen, hochwirksamen Hebel:
**deterministischer Router (Pol B) + Structured Outputs + DRY-Sampler** — alle drei
ohne Modellwechsel, ohne Training. Das deckt sich mit der Synthese oben.

**Suchklasse Re-Verify/Lauf 3 (wenn Rate-Limit weg):** die 3 Kern-Leads selbst per
WebFetch prüfen (Docker-Eval-Zahlen, Ollama-DRY-Support); dann die echt-offenen
Achsen (Self-RAG-Praxis, Pol-A/B-Trade-offs) bei r/LocalLLaMA / HN / GitHub.

## Empirisch auf UNSEREM Ollama geprüft (2026-06-07, v0.17.7)

Zwei vermeintliche „Ein-Zeilen-Fixes" am laufenden Setup getestet — **beide tot:**

- **`tool_choice:"required"` wird IGNORIERT.** /api/chat antwortet frei weiter,
  ohne den erzwungenen Tool-Call. → Tool-Forcing geht über Ollama NICHT; ein
  Router muss Python-seitig davor (Intent erkennen → Tool selbst dispatchen →
  Ergebnis injizieren). Aufwändiger als gehofft.
- **`dry_multiplier`/`dry_*` werden IGNORIERT.** DRY auf Maximum (allowed_length 1,
  multiplier 10) ändert einen erzwungenen Loop kein bisschen → Ollama 0.17.7
  plumbt den DRY-Sampler nicht durch. (Käme evtl. mit Ollama-Upgrade.)
- **WICHTIGER: Sampler sind ohnehin das falsche Werkzeug für UNSERE Spirale.**
  DRY/`repeat_penalty` wirken INNERHALB einer Generierung gegen Token-Loops. Die
  beobachtete Spirale ist ÜBER Turns: jede Antwort ist eine frische Generierung,
  die die vergiftete History neu liest und die Falschaussage *semantisch* neu
  beschließt. → Hebel ist **Re-Grounding / History-Hygiene** (frischen Tool-Read
  erzwingen + vergiftete Assistant-Turns trimmen bei User-Widerspruch), NICHT ein
  Sampler. Deckt sich mit [[project_history_vergiftung]] (Regel-7-Reflex reicht
  messbar nicht).

**Konsequenz für „einfachster + wertvollster Fix":** Die beiden Silberkugeln sind
weg. Der real gelandete simpelste Gewinn bleibt die **Daten-Präsentation**
(ABSAGEN-Zeile, 30→60 %, [[kalender_system.md]]).

## Re-Grounding-Gate — GETESTET, bringt nichts, ZURÜCKGEROLLT (2026-06-07)

Hypothese: bei User-Widerspruch („haben wir doch gelöscht", „wieso noch") die
ASSISTANT-Vorantworten aus dem Kontext nehmen, damit das 9b nicht seine
Falschaussage verteidigt, sondern frisch herleitet (Recency statt tool_choice,
das auf Ollama eh tot ist). Als `ai._reground` gebaut, in `chat_stream` + Bench
verdrahtet, **A/B gemessen** (N=20, Gate nur in T3 aktiv):

| Metrik | Gate AN | Gate AUS |
|---|---|---|
| T3 nennt Geige | 50 % | 60 % |
| T3 keine Fehlentwarnung | 95 % | 100 % |
| Episode sauber | 25 % | 35 % |

Gate-AUS ist auf JEDER Metrik gleich oder besser → **kein Funke Evidenz, eher
minimal schlechter.** Grund (aus den Transkripten): die „10-Uhr"-Verankerung
steckt in den **USER-Turns** (T1+T3 sagen beide „10 Uhr", Geige nennt der User
nie) — Assistant-Turns rauswerfen entfernt das Gift nicht, weil es nicht dort
sitzt. Und T2 scheitert mit 55 % OHNE jede Vorantwort zum Verteidigen → der Kern
ist **Lese-Verständnis pro Generierung**, nicht Turn-Perseveration. Komplett
revertet (ai.py + Bench). Nicht auf Hoffnung shippen ([[messen-nicht-vibes]]).

## Modellgröße ist NICHT der Hebel — GEMESSEN (2026-06-07)

Lead ① („Modell ist gut, Hebel = Architektur") direkt auf unserem Bug falsifiziert:
**qwen2.5:14b vs qwen3.5:9b auf der Alarm-Episode (N=15 bzw. N=20):** T2-Zuordnung
67 % vs ~60 %, Episode 47 % vs ~45 % — **praktisch gleich, aber 14B ist 5× langsamer**
(14,5 vs 3 s/Turn) und brächte die alten VRAM-Crashes zurück
([[project_modell_benchmark]]). → Mehr Modellgröße hebt das Lese-Verständnis NICHT.
① bestätigt: Modellwechsel ist vom Tisch.

## Structured Outputs — GETESTET, schlechter (2026-06-07)

Letzter ①-konformer Maker-Lead (`scripts/probe_structured_alarm.py`): Ollama
`format`/JSON erzwingen, damit das Modell ein Feld „welche_aktivitaet" füllen MUSS
statt frei zu driften. Zwei Befunde:
- **0.17.7 erzwingt KEIN Schema-Objekt** (erfindet eigene Felder) — nur
  `format:"json"` (generischer JSON-Mode) greift; Felder muss man im Prompt nennen.
- **Mit realistischer T1-Vergiftung: Struktur 60 % vs Freitext 80 % (N=15) →
  STRUKTUR IST SCHLECHTER.** Bei vergiftetem Kontext committet das JSON-Zwingen auf
  ein falsches Feld oder `null`; Freitext kann zum Richtigen hedgen. Verworfen.

## DER gating-Faktor: die eigene T1-Vorantwort (quer durch alle Experimente)

Re-Grounding UND Structured-Probe zeigen dasselbe: **sobald die T1-Antwort des
Modells das „KONFLIKT/Reise-überlappt"-Narrativ trägt, erben T2/T3 es, und KEIN
nachgelagerter Fix (Vorantwort entfernen, Struktur erzwingen) rettet es.** Ist die
T1-Antwort sauber, liest das 9B den Alarm korrekt (isoliert ~100 %). Das Gift ist
also nicht „schlechte Lesefähigkeit", sondern **das Modell rahmt in T1 falsch und
schleppt den Frame mit.** Downstream dagegen anzukämpfen ist verloren — der Hebel
sitzt VOR/IN der ersten Antwort (welche Daten/Alarme das Modell pre-delete sieht).

## DURCHBRUCH: Dashboard-Sicht entriegelt Thinking (2026-06-08)

Sashas These: dem 9b den Reflexions-Schritt geben („warte, ergibt das Sinn?").
Erst-Test: think=ON roh war SCHLECHTER (67 % vs 93 % Freitext) — der Denkblock
verriet WARUM: das Modell zerdachte sich in „ich kenne dein Dashboard nicht, das
wäre Lügen" und verband „Warnung im Dashboard" NIE mit dem Alarm-Block. **War
epistemisch korrekt** — es hatte NULL Sicht aufs Dashboard-Layout (verifiziert:
kein Prompt-Baustein beschrieb es; der Alarm-Block hieß „Offene Erinnerungen", nie
„Warnung").

Fix (Sashas Idee): eine knappe **Dashboard-Sicht** in den System-Prompt
(`ai._DASHBOARD_VIEW`, gegated `ZENTRALE_DASHVIEW`, Default AN) + Alarm-Block-Header
umbenannt auf „= die ⚠ Warnsymbole unten links". Quelle: das ECHTE UI
(`monolith.html`/`engine.js`) — NICHT die veraltete `dashboard.md` (die beschrieb
noch Orb + 3-Spalten + Tutor; reingefallen, dann aus dem Code korrigiert).

**A/B (probe_structured_alarm.py, N=15):**
| Variante | Sicht AUS | Sicht AN |
|---|---|---|
| Freitext | 93 % | 73 % |
| Struktur | 53 % | 67 % |
| **think=ON** | **53 %** | **93 %** |

→ Auf der ISOLIERTEN Verständnisfrage entriegelt die Sicht Thinking (+40pp).

**ABER: think=ON auf der VOLLEN Episode ist ein Desaster (GEMESSEN N=12,
+Sicht):** T1-löschen 25 %, **T2-Zuordnung 8 %**, Episode **0 %**, 16 s/Turn. Das
Modell zerdenkt die AKTIONS-Turns (Löschen) und die ganze Mehrturn-Kette. Die
Probe-93 % galten nur, weil dort NUR auf der Verständnisfrage gedacht wurde (mit
sauberer think=OFF-Vorantwort). **Lehre: „Thinking global einschalten" ist RAUS.**
Reflexion hilft nur als GEZIELTER Einzelschritt auf reinen Verständnisfragen, nie
auf Aktions-/Multiturn-Flows → exakt [[project_adaptiver_aufwand]] (adaptiv, kein
globaler Schalter), nicht trivial zu bauen. (think=ON-content-loss-Bug ist auf
0.17.7 zwar weg, aber das nützt hier nichts.)

**Stand Dashboard-Sicht (`_DASHBOARD_VIEW`, Default AN):** bleibt drin, weil es
KORREKTE Info ist und die reale „ich kenne dein Dashboard nicht"-Abstain-Falle
schließt. Quelle ist das ECHTE UI, nicht die (jetzt bereinigte) dashboard.md.

## ADAPTIVE THINK (2026-06-08) — DER GEWINN, in Prod

Auflösung der „Thinking global = Desaster, aber isoliert top"-Spannung:
**think PRO TURN entscheiden.** `ai._should_think(messages)` (Heuristik auf die
letzte User-Message): think AN bei Verständnis-/Verifikationsfragen (was/warum/
wieso/stimmt/ergibt Sinn/Pushback), AUS bei Aktions-/Schreib-Befehlen (lösch/trag
ein/…). Reihenfolge: Frage ZUERST prüfen, damit „… haben wir doch gelöscht, WIESO?"
als Frage zählt, nicht als Befehl.

**Gemessen (N=12, volle Episode, Dashboard-Sicht an):**
| Konfig | T1 löschen | T2-Zuordnung | Episode | Tempo |
|---|---|---|---|---|
| Baseline (think aus) | ~90 % | ~60 % | ~45 % | 3 s |
| think GLOBAL | 25 % | 8 % | 0 % | 16 s |
| **ADAPTIV** | **92 %** | **92 %** | **67 %** | 5,8 s |

→ Adaptiv schlägt BEIDE Pole klar. Warum es geht: Aktions-Turns think-aus halten die
History sauber (kein Denk-Gerede) → die Verständnis-Turns reflektieren auf sauberem
Kontext (nahe die 93 % der isolierten Probe), ohne den Löschen-Turn zu zerdenken.
Das ist [[project_adaptiver_aufwand]] in real + Sashas „warte, ergibt das Sinn?"-
Reflex, in der Form die FUNKTIONIERT.

**In Prod gewired:** `chat_stream` setzt `think` adaptiv pro Turn (nur regulärer
Chat, Tutor denkt nicht). Streaming ist think-safe verifiziert: bei think=ON kommen
Denk-Tokens im `thinking`-Feld (vom Reader ignoriert), die Antwort im `content`-Feld
(der alte content-loss-Bug ist auf Ollama 0.17.7 weg). Dashboard-Sicht bleibt AN
(macht die Reflexion erst sinnvoll — ohne sie zerdenkt sich Think in „kenne dein
Dashboard nicht").

**FAZIT der ganzen Runde (alle Hebel durch):**
- ✅ **Daten-Präsentation** (ABSAGEN-Zeile 30→60 %; Dashboard-Sicht) — bessere
  Eingaben schlagen jeden nachgelagerten Trick.
- ✅ **Adaptive Reflexion** (think pro Turn) — der GROSSE Gewinn: T2 60→92 %,
  Episode 45→67 %. In Prod.
- ❌ Modellwechsel (14B ≈ 9B), ❌ tool_choice (Ollama tot), ❌ DRY (Ollama tot +
  falsch), ❌ Re-Grounding (wirkungslos), ❌ Structured Outputs (schlechter),
  ❌ think GLOBAL (Episode 0 %).
- Roter Faden: das 9B rahmt auf Aktions-/ersten Turns leicht falsch; was hilft, sind
  (a) sauberere Eingaben und (b) ein gezielter Reflexions-Schritt NUR dort, wo
  Verstehen zählt — nicht globale Tricks. Weitere Stufe (offen): Fine-Tune
  ([[ki_personality_plan.md]]) für den Rest-Schwanz; `_should_think`-Heuristik bei
  Bedarf verfeinern (mehr Fragetypen / Mehrdeutigkeiten).

**Quellen Lauf 1 (alle Primär):** arXiv 2509.04664, 2512.19920, 2605.14038,
2406.15927, 2309.11495 + llama.cpp grammars-Repo.
