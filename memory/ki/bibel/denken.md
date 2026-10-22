# KI-Bibel — Denken, effort, parallele Aufrufe

**Stand 2026-10-22:** Fünf Einträge (D-01 bis D-05). Umgesetzt: effort statt
Denkbudget. Offen: Nachdenken nach Werkzeug-Ergebnissen, parallele Aufrufe,
Selbstcheck. Legende und Pflegeregeln: [README.md](README.md).

---

### D-01 Nach Werkzeug-Ergebnissen nachdenken

- **Regel:** Nach jedem Werkzeug-Ergebnis prüft die KI, wie gut es ist, und
  plant den nächsten Schritt, bevor sie weitermacht (interleaved thinking).
- **Zitat:** „After receiving tool results, carefully reflect on their quality
  and determine optimal next steps before proceeding.“
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices —
  offiziell, erfasst 22.10.2026; dazu
  https://www.anthropic.com/engineering/multi-agent-research-system
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Kein solcher Satz im Prompt.

### D-02 effort statt Denkbudget

- **Regel:** Ab Modellen 4.6 denkt Claude adaptiv. `budget_tokens` ist ab 4.7
  ein Fehler; gesteuert wird über `effort`.
- **Zitat:** —
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices —
  offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** umgesetzt — `core/cloud.py` ~93–104 (`output_config.effort`),
  kein `budget_tokens` im Kern gefunden
- **Heute bei ZENTRALE:** effort kommt aus `ai_backends.chat_effort()`.

### D-03 Parallele Werkzeug-Aufrufe

- **Regel:** Unabhängige Aufrufe (mehrere Suchen, mehrere Seiten) gehen
  gleichzeitig raus. Ein kurzer Prompt-Block bringt das auf fast 100 %.
- **Zitat:** —
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
  (`<use_parallel_tool_calls>`) — offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — kein solcher Satz in `core/profil/gross.py`
- **Heute bei ZENTRALE:** Nicht angewiesen; ob die Schleife mehrere Aufrufe
  einer Runde gleichzeitig ausführt, ist hier nicht geprüft.

### D-04 Selbstcheck vor dem Abschluss

- **Regel:** Vor dem Ende prüft die KI ihr Ergebnis im selben Lauf
  („Before you finish, verify…“). Bei Opus 5 kann das übereifrig werden.
- **Zitat:** „Before you finish, verify…“
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Geprüft wird von außen (Python-Prüfer,
  [pruefung.md](pruefung.md)), nicht vom Modell selbst.

### D-05 Niedriger effort heißt mehr Rückfragen und früheres Aufhören

- **Regel:** Bei niedrigem effort fragt Sonnet 5.5 öfter zurück und hört
  früher auf. Für Recherche und Aufträge effort nicht zu niedrig setzen.
- **Zitat:** —
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5 —
  offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen
- **Heute bei ZENTRALE:** Ein effort für alle Züge; passt zu H-05 in
  [handeln.md](handeln.md).

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
