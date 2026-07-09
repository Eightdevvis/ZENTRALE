# KI-Prompts der ZENTRALE — zentral zum Review

Dieser Ordner sammelt **alle KI-Prompts** des Projekts an einem Ort, auf
Deutsch lesbar, damit sie am Stück durchgesehen und neu geschrieben werden
können. Jede Datei nennt oben ihre **Quelle** (`<datei>:<zeile>`) — dort steht
der Prompt live im Code. Diese Sammlung ist eine **Lese-/Review-Kopie**, keine
zweite Quelle der Wahrheit: Änderungen wandern von hier aus bewusst zurück in
den Code, nicht automatisch.

## ⚠ WICHTIG — chinesische Prompts nicht 1:1 zurückspielen

Ein Teil der Tutor-Prompts (die Persona **Ling Ling**, Mandarin) steht im Code
**absichtlich auf Chinesisch**. Das ist **verifiziert kein Zufall**: ein Prompt
in der Zielsprache hält qwen zuverlässig in der Zielsprache — ein **deutscher**
Prompt ließ qwen zu ~95 % auf **Deutsch** antworten (Tuning-Log:
`memory/tutor_persona_tuning.md`).

Darum gilt für jede Datei, die als `Live-Sprache: zh` markiert ist:

- Die **deutsche Fassung** in dieser Datei ist **nur zum Review** — eine treue
  Übersetzung, damit man versteht, was der Prompt sagt.
- Das **chinesische Original** steht daneben im Codeblock. **Nur dieses** gehört
  live in den Code.
- **Nicht die deutsche Übersetzung 1:1 zurückspielen** — sonst kippt die KI ins
  Deutsche und die ganze Persona-Wirkung bricht.

Deutsche Prompts (`Live-Sprache: de`) sind dagegen **wörtlich aus dem Code
kopiert** und können direkt gelesen/umgeschrieben werden.

## Dateien

### Tutor (Persona-Portal, Sprach-Framework)

| Datei | Was | Live-Sprache |
|-------|-----|--------------|
| [tutor_persona-ling-ling.md](tutor_persona-ling-ling.md) | Ling-Ling-Charakter-Prompt (Mandarin-Persona) | zh |
| [tutor_vokabel-hinweis.md](tutor_vokabel-hinweis.md) | Vokabel-Kontext ans Prompt-Ende | zh |
| [tutor_nudge.md](tutor_nudge.md) | Stille-Anstoß (KI reagiert von selbst) | zh |
| [tutor_tools.md](tutor_tools.md) | Vokabel-Tools + express-Geste | de (express: zh) |
| [tutor_generisch-fallback.md](tutor_generisch-fallback.md) | generischer Persona-Prompt für Skizzen-Sprachen | de |

### Core-KI (die ZENTRALE-KI selbst)

| Datei | Was | Live-Sprache |
|-------|-----|--------------|
| [core-ki_system.md](core-ki_system.md) | Persönlichkeit/Stimme (System-Prompt) | de |
| [core-ki_meta-regeln.md](core-ki_meta-regeln.md) | Meta-Regeln (nicht lügen/erfinden) | de |
| [core-ki_selbstbild.md](core-ki_selbstbild.md) | Selbstbild-Seed (kann / kann-nicht) | de |
| [core-ki_mic-hint.md](core-ki_mic-hint.md) | Spracheingabe-Hinweis + Jetzt-Block | de |

### Hintergrund-KI

| Datei | Was | Live-Sprache |
|-------|-----|--------------|
| [memory-extraktor.md](memory-extraktor.md) | Graph-Extraktor (Turn → Konzepte) | de |
| [news.md](news.md) | News-Prompts (Label, Sendung, Rückblick, Aufholmodus) | de |
