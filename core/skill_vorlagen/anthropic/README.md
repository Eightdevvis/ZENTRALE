# Skills von Anthropic — Herkunft und Lizenz

Die Ordner hier sind **unveränderte Kopien** aus dem öffentlichen Repository
von Anthropic:

- Quelle: <https://github.com/anthropics/skills>, Ordner `skills/`
- Stand: Commit `683bc88` („Update claude-api skill: managed-agents-onboard
  from a quickstart name or a URL (#1962)"), übernommen am 2026-10-07
- Lizenz: **Apache License 2.0** — der volle Text liegt in jedem Skill-Ordner
  als `LICENSE.txt` und reist mit dem Skill mit (auch nach
  `data/gedaechtnis/skills/`).
- Hinweise zu Fremdkomponenten des Repositories:
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (unverändert übernommen).
  **Nicht übernommen:** die Schriften in `canvas-design/canvas-fonts/`
  (5,5 MB, SIL Open Font License) — der Skill ist ohnehin aus, und einmal
  gepusht blieben sie für immer in der Git-Historie. Bei Bedarf aus dem
  Anthropic-Repo (Commit 683bc88) nachholen.

Übernommen sind **nur** die Skills mit Apache-2.0-`LICENSE.txt`:
academy-guide, algorithmic-art, brand-guidelines, canvas-design, claude-api,
discernment-nudge, frontend-design, internal-comms, mcp-builder,
skill-creator, slack-gif-creator, theme-factory, webapp-testing,
web-artifacts-builder.

**Nicht** übernommen: `docx`, `pdf`, `pptx`, `xlsx` (eigene, nicht offene
Lizenz von Anthropic — „All rights reserved") und `doc-coauthoring` (ohne
Lizenzdatei, also ohne Erlaubnis zum Weitergeben).

## Änderungen gegenüber dem Original (Apache 2.0, § 4b)

- **Hinzugefügt:** `skill-creator/references/zentrale.md` — was vom
  skill-creator in ZENTRALE geht und was nicht. Sonst ist keine Datei
  verändert; jede `SKILL.md` ist Wort für Wort die von Anthropic.
- ZENTRALE-eigene Angaben (an/aus, Herkunft, „braucht") stehen nicht in den
  Skills, sondern in [zentrale.json](zentrale.json). Beim Ausliefern nach
  `data/gedaechtnis/skills/<name>/` wird daraus je Skill eine
  `_zentrale.json` neben die SKILL.md gelegt (core/skills.py,
  `erstbefuellen`).

## Neue Fassung übernehmen

Ordner aus dem Repository von Anthropic hierher kopieren (nur Skills mit
Apache-2.0-Lizenz), `skill-creator/references/zentrale.md` behalten, Commit
und Datum oben nachtragen, neue Skills in `zentrale.json` eintragen (sonst
werden sie nicht ausgeliefert). Schon ausgelieferte Skills werden NICHT
überschrieben — Sashas Rechner behalten ihre Fassung.
