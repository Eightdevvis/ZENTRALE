# KI-Personality-Plan – vom System-Prompt zum eigenen Modell

> **Status: aktiv, Phase 0 erster Pass durch.** Phasen 1–3 noch nicht angefangen.
>
> Ziel-Doppelhorizont: kurzfristig pragmatisch die Persönlichkeit der
> ZENTRALE-KI schärfen; mittelfristig als Vehikel dienen, um echtes
> Hands-On-ML zu lernen (Fine-Tuning, LoRA, DPO). Phasen sind so
> geschnitten, dass jede für sich Wert liefert – aufhören kann man
> nach jeder Phase.

## Was hier nicht steht

- Memory-System: → `memory/ki/ki_memory_plan.md` (archiviert) und `memory/ki/ki_system.md`.
- Tool-Use, Capabilities-Prompt: → `memory/ki/ki_system.md`.
- Persona-Inhalt selbst (Tonfall, Vorlieben): wird im Code in
  `core/ai.py:_SYSTEM_PROMPT` gepflegt, nicht hier.

## Designprinzipien

- **Erst System-Prompt maximieren, dann erst trainieren.** qwen2.5:14b
  reagiert stark auf In-Context-Examples. Wenn ohne Training schon 80%
  des Zielstils erreicht sind, ist FT Overkill.
- **Stimme/Stil ist FT-freundlich, Fakten sind es nicht.** LoRA prägt
  Voice gut ein. Faktenwissen reinzutrainieren ist unzuverlässig und
  riskiert Halluzination. Fakten bleiben im Graphen.
- **Eigene Chat-Logs sind nicht 1:1 Trainingsdaten.** Auf den eigenen
  alten Output zu trainieren = Feedback-Schleife mit aktuellen
  Schwächen. Datensatz muss den **Wunsch**-Stil zeigen, nicht den
  Ist-Stil. (Häufigster Anfänger-Fehler beim DIY-FT.)
- **Klein anfangen, hochskalieren.** 7B lokal als Proof-of-Concept,
  bevor 14B in der Cloud Geld kostet. Wenn der Stil-Shift auf 7B nicht
  funktioniert, funktioniert er auf 14B auch nicht – also lieber
  früh herausfinden.
- **Pragmatisches Cloud-Off-Loading ist okay.** ZENTRALE-Runtime
  bleibt lokal-only (Privacy, Autonomie). Aber Training für 2 Stunden
  in der Cloud verletzt das Privacy-Modell nicht – Modell kommt als
  Datei zurück, läuft danach wieder offline.

## Glossar – die drei Verfahren

| Begriff | Was es ist | Wann sinnvoll |
|---------|-----------|---------------|
| **SFT** (Supervised Fine-Tuning) | Standard-FT mit `(input, gewünschte_antwort)`-Paaren. Cross-Entropy-Loss. | Grundverfahren für „Modell soll anders klingen / antworten". 95% aller FT-Anwendungen. |
| **DPO** (Direct Preference Optimization) | Training auf Paaren „A besser als B". Kein separates Reward-Modell. | Feinschliff *nach* SFT. Wenn man Anti-Patterns rausziehen will („sag NIE 'Aber gerne!'"). |
| **RLHF** (Reinforcement Learning from Human Feedback) | SFT → Reward-Modell → PPO. Drei Stufen, instabil. | Nur wenn man Anthropic/OpenAI baut. Für Single-User-Projekte Overkill. |

LoRA / QLoRA sind keine eigenen Verfahren, sondern **effiziente
Implementierungen** von SFT/DPO: statt alle Parameter zu trainieren
nur kleine Adapter-Matrizen. Senkt VRAM-Bedarf um Größenordnungen.

## Phasen

### Phase 0 – System-Prompt-Aufbohrung (kein Training)

**Ziel:** Den größten Stil-Shift ohne FT herausholen.

**Status:** Dritter Pass (`_SYSTEM_PROMPT` in `core/ai.py`, sechs Sektionen:
Stimme / Länge / Floskel-Stopliste / So endet ein Turn (Beispiel) / Substanz
statt Pflichtprogramm / Text-Effekte). 2026-06-06: Stimme auf eine echte
Charakter-Richtung umgestellt (Sasha gewählt: exzentrisch/Feuilleton > trocken-
lakonisch > frech/sarkastisch, nicht ernst), bewusst erlaubend statt geknebelt
formuliert (Verbote/Einschränkungen primen & produzieren Verweigerung). Neue
Text-Effekte-Sektion (`[[effekt: text]]`, großzügig statt sparsam). Inhalt im
Code, hier nur Status. Adressiert die drei beobachteten Probleme aus der
Bestandsaufnahme:
- *Robotisch* → konkrete Stimm-Beschreibung mit Wortwahl-Erlaubnis
- *„Soll ich noch X für dich tun?" als Reflex* → **2026-05-31 nachgeschärft.**
  Erster Pass hatte das per Negativ-Liste verboten („häng NICHT 'Soll ich
  noch…' an") — half nicht: der Reflex kam bei jeder Antwort. Zwei
  Ursachen: (a) 14B-Instruct-Modelle prallen an Verboten ab, der
  RLHF-Helpfulness-Default gewinnt; (b) die wörtlich genannte Floskel
  *primt* das Modell, sie auszugeben. Fix: Verbot → positive Regel
  („Beende den Turn mit dem letzten inhaltlichen Satz"), wörtliche Floskel
  raus, plus Few-shot-Beispiel das ein sauberes Turn-Ende vormacht.
- *Trocken, predictable, keine Insights* → Substanz-Sektion verlangt
  proaktiv nicht-offensichtliche Beobachtungen

**Noch offen in Phase 0:**

1. **Beobachtungs-Phase** – prüfen, ob der Service-Nachklapp mit
   positiver Regel + Few-shot tatsächlich verschwindet, oder ob neue
   Floskeln einfallen. Ebenso: bleibt die Länge knapp, wirkt der
   Substanz-Push echt?
2. ~~**Optional: Few-Shot-Beispiel**~~ → **2026-05-31 gezogen.** Der
   Trigger („nur ziehen, wenn die reine Instruction-Version unzureichend
   bleibt") trat ein: der Nachklapp-Reflex überlebte die reine Stopliste.
   Vorerst nur EIN knappes Beispiel (Turn-Ende), nicht 3–5 — Token-Kosten
   pro Turn niedrig halten, eskalieren falls ein Beispiel nicht reicht.
3. **Iterations-Loop** – konkrete Floskeln/Tics die der Model trotz
   Regel noch produziert, werden nachgetragen (positiv formuliert bzw.
   per zusätzlichem Beispiel, nicht als wörtliches Verbot).

Wenn nach Iteration ≥80% des Zielstils erreicht → Phase 1 sparen.

### Phase 1 – QLoRA auf qwen2.5:7b lokal (Proof-of-Concept)

**Ziel:** Verifizieren, dass der gewünschte Stil-Shift überhaupt
durch Training erreichbar ist – auf dem kleineren Modell, weil:
- Passt locker auf RTX 4070 (12 GB VRAM).
- Training 2–3x schneller als 14B.
- Wenn auf 7B kein klarer Shift sichtbar wird, liegt das Problem im
  Datensatz, nicht in der Modellgröße. Geld für 14B-Cloud sparen.

Schritte:

1. **Trainingsdatensatz aufbauen** (siehe Datensatz-Strategien unten),
   Ziel: 300–800 Beispiele.
2. **Unsloth installieren** (`pip install unsloth`), Notebook oder
   Skript anlegen unter `ml/finetune_7b.py`.
3. **QLoRA-Config** (Standard-Defaults von Unsloth für qwen2.5-7b):
   - 4-bit Base, 16-bit LoRA-Adapter
   - Rank r=16, alpha=32
   - Batch-Size 2, Gradient-Accumulation 4 (effektive Batch 8)
   - Lernrate 2e-4, 1–3 Epochen
4. **Trainieren** (~30–90 Min auf RTX 4070).
5. **Adapter mergen** und zu GGUF konvertieren (`llama.cpp` Skripte),
   in Ollama importieren via `ollama create`.
6. **A/B-Vergleich** mit Base-Modell auf einem Test-Set von 20 Fragen.
   Wenn Shift klar erkennbar → Phase 2.

Output: `data/models/qwen-7b-sasha-v1.gguf` (oder ähnlich), als
optionaler `OLLAMA_MODEL`-Wert nutzbar zum Testen.

### Phase 2 – QLoRA auf qwen2.5:14b in der Cloud

**Ziel:** Das richtige Modell, mit dem ZENTRALE produktiv läuft, in
den Wunsch-Stil ziehen.

Schritte:

1. **Dataset von Phase 1 wiederverwenden** (eventuell anreichern auf
   500–1500 Beispiele wenn Phase 1 Schwachstellen sichtbar gemacht
   hat).
2. **Cloud-GPU buchen:** RunPod oder Vast.ai, RTX 4090 (24 GB) oder
   A100 (40 GB). Kosten: 30–50¢/h × 2–4 h = **$1–$2 pro Training**.
3. **Selbes Unsloth-Skript** wie in Phase 1, nur Base-Modell auf
   qwen2.5-14b umstellen, Hyperparameter ggf. nach unten korrigieren
   (Rank r=8 reicht meist, niedriger ist robuster).
4. **Resultat als GGUF** runterladen, lokal in Ollama importieren.
5. **`OLLAMA_MODEL`-Env in ZENTRALE umstellen** auf das neue Modell.
   Default-Modell wechselt damit projektweit.

Daten-Schutz-Hinweis: Die Cloud-GPU sieht nur das Trainingsdatenset
und gibt das Modell zurück. Wenn das Dataset nichts Sensibles
enthält (was es bei Stil-FT nicht muss), ist das ok. ZENTRALE selbst
läuft danach wieder vollständig offline.

### Phase 3 – DPO-Feinschliff (optional)

**Ziel:** Spezifische Anti-Patterns rausziehen, die SFT nicht ganz
weggekriegt hat.

Schritte:

1. **Preference-Paare sammeln:** während des normalen ZENTRALE-Betriebs
   in der UI einen „besser/schlechter"-Button einbauen. Jeder Klick
   speichert das aktuelle Turn-Pair als `(prompt, chosen, rejected)`.
2. **Ab ~100 Paaren** macht DPO Sinn. Drunter zu wenig Signal.
3. **DPO-Training** mit Unsloth (unterstützt DPO direkt), nochmal
   1–2 Stunden Cloud-GPU.
4. **Resultat ersetzt** das Phase-2-Modell.

Phase 3 ist klassisches ML-Hands-On: Reward-Signal sammeln, Modell
darauf optimieren, evaluieren. Gute Gelegenheit, das Verfahren
wirklich zu verstehen.

## Datensatz-Strategien

Drei Wege, ein Trainingsset für Phase 1/2 zu bauen:

### Strategie A – Hand-kuratiert (höchste Qualität)

ZENTRALE-Chat-Logs öffnen, **nur die User-Turns** als Inputs nehmen,
die KI-Antworten **selbst neu schreiben** im Zielstil.

- Aufwand: ~1–3 Min pro Beispiel, also 10–30 h für 300–800 Beispiele.
- Qualität: höchste. Genau dein Stil, keine fremden Fingerprints.
- Beste Option, wenn Zeit > Geld.

### Strategie B – Synthese durch größeres Modell

Claude oder GPT-4o ein detailliertes Stil-Briefing geben („antworte
wie ein deutscher Feuilletonist, locker, mit Hut, Sarkasmus erlaubt,
nie 'Aber gerne'…") und damit gegen ZENTRALE-User-Turns Antworten
generieren lassen. Dann hand-kuratieren (~30% verwerfen).

- Aufwand: 2–4 h Generieren + 5–10 h Kuratieren.
- Qualität: gut, aber dein Modell klingt am Ende leicht nach dem
  Synthese-Modell (Claude-Fingerprint, GPT-Fingerprint).
- Pragmatisch sinnvoll. Wenn der Synthese-Stil ohnehin nah am
  Wunschziel liegt, kaum Nachteil.

### Strategie C – Filter aus ZENTRALE-Logs

Bestehende Logs durchgehen, nur die KI-Turns behalten, die zufällig
schon gut klangen. Erfahrungswert: <10% verwertbar.

- Aufwand: niedrig zum Filtern.
- Qualität: bewahrt Status quo. Kein Stil-**Shift**, sondern Stil-
  **Verstärkung**. Nicht das, was wir wollen.
- Höchstens als Ergänzung zu A oder B.

**Empfehlung:** B als Haupt-Strategie, A für die ~50 wichtigsten
Beispiele (deine Lieblingsfragen, schwierige Edge-Cases).

## Hardware-Notizen

- **Lokal (RTX 4070, 12 GB):** qwen2.5-7b-QLoRA passt komfortabel.
  qwen2.5-14b-QLoRA passt knapp mit aggressiver Quantisierung,
  Gradient-Checkpointing, Batch-Size 1, max-seq-len ≤ 2048 – aber
  jede zweite Hyperparameter-Änderung produziert OOM.
- **Cloud (RTX 4090 / A100):** 14B-QLoRA stressfrei. RunPod, Vast.ai,
  Lambda. Aktuelle Preise checken vor Buchung.
- **Inferenz** bleibt lokal in beiden Fällen, läuft ja schon stabil
  unter Ollama.

## Tooling

| Tool | Zweck | Notiz |
|------|-------|-------|
| **Unsloth** | QLoRA/DPO-Training, schnellster Weg | Default-Empfehlung. Hat Pre-built Configs für qwen2.5. |
| **Axolotl** | Alternative zu Unsloth | Mehr Flexibilität, etwas mehr Konfigurations-Aufwand. |
| **llama.cpp** | GGUF-Konvertierung & Quantisierung | Für Ollama-Import nötig. |
| **Ollama** | Inferenz (haben wir schon) | `ollama create -f Modelfile` importiert custom-GGUF. |
| **Weights & Biases** (optional) | Training-Metriken-Tracking | Nice-to-have ab Phase 1, Pflicht ab Phase 3. |

## Verzeichnis-Struktur (Vorschlag)

Wenn Phase 1 startet, neuer Top-Level-Ordner in ZENTRALE:

```
ml/
├── finetune_7b.py            # Unsloth-Skript Phase 1
├── finetune_14b.py           # Unsloth-Skript Phase 2 (cloud)
├── dpo.py                    # DPO-Skript Phase 3
├── datasets/
│   ├── sasha_voice_v1.jsonl  # Trainingsset SFT
│   └── preferences_v1.jsonl  # Trainingsset DPO
└── README.md                 # Was wo läuft
```

Sollte `data/models/` analog für die fertigen GGUF-Files bekommen, mit
.gitignore-Eintrag (Modelle sind Binär-Blobs, nicht ins Repo).

## Verwandte Doku

- `memory/ki/ki_system.md` – aktuelle KI-Architektur (Ollama, Graph, Tools)
- `memory/ki/ki_memory_plan.md` – Memory-System-Historie und -Designprinzipien
- `claude_hinweise.md` – Tool-Use-Konventionen
- `memory/betrieb/setup.md` – wenn `ml/`-Dependencies dazukommen, dort dokumentieren
