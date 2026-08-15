# KI — Index

Alles über den denkenden Teil von ZENTRALE: welches Modell wo läuft, wie das
Gedächtnis gebaut ist, wie die KI spricht und hört, und was an Plänen und
Messungen dazu existiert.

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Wie der Chat läuft: lokal (Ollama) und Cloud, Tools, Erlaubnis-Gate, Konzept-Graph, System-Prompt-Reihenfolge, Prompt-Cache, Backend-Wahl | [ki_system.md](ki_system.md) |
| Wie die KI hört und spricht: Whisper-STT + TTS als eigene Services, sprachneutral | [audio_system.md](audio_system.md) |
| Warum das Memory so aussieht, wie es aussieht — Historie der Phasen A–G, verworfene Ansätze | [ki_memory_plan.md](ki_memory_plan.md) |
| Wohin die Persönlichkeit soll: vom System-Prompt zum eigenen Modell (Fine-Tuning-Plan) | [ki_personality_plan.md](ki_personality_plan.md) |
| Warum die KI nicht raten soll, sondern nachschaut — Recherche zum Grounding | [grounding_recherche.md](grounding_recherche.md) |
| Dialogischer Action-Scaffold fürs lokale 9b (WIP, geparkt) | [logic_loop_plan.md](logic_loop_plan.md) |
| Gemessenes statt Gefühltes: Benchmark-Protokolle, Sampling, Modell-Vergleiche | [bench_history.md](bench_history.md) |

## Wo sonst noch KI drinsteckt

- Der **Sprach-Tutor** ist ein eigenes Projekt mit eigenem Ordner →
  [../tutor/INDEX.md](../tutor/INDEX.md)
- Was die KI im Dashboard **anzeigt** (Kern, Reflexion, Knöpfe) →
  [../system/dashboard.md](../system/dashboard.md)
- Was sie **nicht** sehen darf und was rausgeht →
  [../betrieb/sicherheit.md](../betrieb/sicherheit.md),
  [../betrieb/datei_zugriffe.md](../betrieb/datei_zugriffe.md)
