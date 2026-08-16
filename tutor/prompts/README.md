# Prompts des Tutors — Lesefassung

Die Prompts des Tutor-Projekts, auf Deutsch lesbar. **Keine zweite Quelle der
Wahrheit:** live steht jeder Prompt im Code bzw. in den Sprachpaketen; jede
Datei nennt oben ihre Quelle. Änderungen wandern von hier aus **von Hand**
zurück — es gleicht nichts automatisch ab.

Die Prompts der Core-KI liegen getrennt davon in `prompts/`. Der Tutor ist ein
eigenes Projekt und am Stück rausziehbar; seine Prompts gehören dazu.

## ⚠ Chinesische Prompts NICHT ins Deutsche zurückspielen

Ein Teil dieser Prompts steht im Code **absichtlich auf Chinesisch**. Das ist
**verifiziert kein Zufall**: ein Prompt in der Zielsprache hält qwen zuverlässig
in der Zielsprache — ein **deutscher** Prompt ließ qwen zu ~95 % auf **Deutsch**
antworten (Tuning-Log: `memory/tutor/tutor_persona_tuning.md`).

Für jede Datei, die als `Live-Sprache: zh` markiert ist, gilt darum:

- Die **deutsche Fassung** hier ist **nur zum Review** — eine treue Übersetzung,
  damit man versteht, was der Prompt sagt.
- Das **Original** steht daneben im Codeblock. **Nur dieses** gehört live in den
  Code.
- **Nicht die Übersetzung 1:1 zurückspielen**, sonst kippt die Persona-Wirkung.

Dateien mit `Live-Sprache: de` sind wörtlich aus dem Code kopiert und können
direkt gelesen und umgeschrieben werden.

## Wo die Prompts wirklich liegen

Seit dem Umbau zum **Sprach-Framework** ist Mandarin nur noch eine Sprache unter
mehreren. Was früher als chinesische Konstante in `core/` festhing, ist heute
**Paket-Daten pro Sprache**:

| Was | Wo |
|---|---|
| Persona-Prompt einer Sprache | `tutor/langs/<sprache>/prompt.md` (+ `prompt.de.md` als Übersetzung) |
| Vokabel-Block | `tutor/langs/<sprache>/vocab_hint.md` |
| Register-Leiter | `tutor/langs/<sprache>/expect.json` |
| Tool-Texte einer Sprache | `tutor/langs/<sprache>/tool_texts.json` |
| sprach-neutraler Master | `tutor/langs/PROMPT_TEMPLATE.en.md` |
| generischer Fallback (Code) | `tutor/langs/base.py` → `build_prompt(...)` |

## Dateien

| Datei | Was | Live-Sprache |
|-------|-----|--------------|
| [generisch-fallback.md](generisch-fallback.md) | generischer Persona-Prompt für noch nicht hand-getunte Sprachen | de |
| [vokabel-hinweis.md](vokabel-hinweis.md) | Vokabel-Kontext + Register-Bremse ans Prompt-Ende | zh |
| [nudge.md](nudge.md) | Lage-Meldungen: Öffnen und Stille-Anstoß | zh |
| [tools.md](tools.md) | die 12 Tools der Session + Sandbox-Grenze | de |
