# KI-Bibel — Prompt: Länge, Aufbau, Ton

**Stand 2026-10-22:** Sechs Einträge (P-01 bis P-06). Umgesetzt ist nur die
Länge (Budget-Wächter). Ton und Aufbau sind auf gross teilweise umgestellt,
der Rest ist offen. Wie der Prompt heute gebaut ist, steht in
`memory/ki/prompt_aufbau.md`; hier steht, wonach er gebaut werden soll.
Legende und Pflegeregeln: [README.md](README.md).

---

### P-01 Der feste Prompt bleibt so lang wie Anthropics eigener

- **Regel:** Der feste System-Prompt (ohne Werkzeuge) bleibt bei der Länge
  des claude.ai-Prompts. Was dazukommt, muss anderswo raus.
- **Zitat:** —
- **Quelle:** https://platform.claude.com/docs/en/release-notes/system-prompts/claude-sonnet-5-5 —
  offiziell, Stand 28.09.2026 (~20.300 Zeichen ohne Werkzeuge). Dazu Sasha,
  14.10.2026: „Prompt-Länge an Anthropic halten (Wächter).“
- **Gilt für:** claude-gross
- **Status:** umgesetzt — `tests/test_prompt_budget.py`
  (`PROMPT_BUDGET_ZEICHEN = 21_000`), cb8c662
- **Heute bei ZENTRALE:** Budget 21.000 Zeichen, mit Sashas echtem Gedächtnis
  am 14.10. gemessen 19.017. Die Werkzeug-Schemas zählen nicht mit.

### P-02 Normale Sprache statt Großbuchstaben-Befehle

- **Regel:** Keine „CRITICAL / MUSST / JEDE“-Befehle. Neue Modelle befolgen
  sie überzogen und rufen Werkzeuge zu oft. Normal formuliert reicht.
- **Zitat:** Anthropic rät von „CRITICAL: You MUST…“ ab; neue Modelle lösen
  damit Werkzeuge zu oft aus.
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices —
  offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross (klein bleibt in Großbuchstaben, so ist das
  lokale qwen gemessen)
- **Status:** teilweise — Prompt der Schiene gross umgestellt (cb8c662);
  Werkzeug-Texte ([W-11](werkzeuge.md#w-11-großbuchstaben-raus-aus-den-werkzeug-beschreibungen))
  und Alarm-Block auf gross ([B-03](baustellen.md#b-03-alarm-block-passt-nicht-zu-gross))
  seit 0446ae5. Offen: der Jetzt-Block `ki_prompt._now_prompt` (NICHT, UHRZEIT,
  „NICHT im Kopf“), geteilt mit klein; für gross bräuchte er eine eigene
  Fassung wie der Alarm-Block (hängt mit [P-06](#p-06-keine-kalender-schlagseite) zusammen).
- **Heute bei ZENTRALE:** Persona, Meta-Regeln, Imprint, Umschlag, Werkzeug-
  Texte und Alarm-Block auf gross sind normal geschrieben. Großbuchstaben
  stehen noch im Jetzt-Block.

### P-03 Richtige Flughöhe, klare Abschnitte, knapp anfangen

- **Regel:** Der Prompt ist weder Wenn-dann-Liste noch vage Floskel. Er ist in
  Abschnitte gegliedert (XML-Tags oder Überschriften). Er startet knapp und
  wird erst ergänzt, wenn ein Test zeigt, dass etwas fehlt.
- **Zitat:** „find the smallest set of high-signal tokens that maximize the
  likelihood of your desired outcome“; „minimal does not necessarily mean short“
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — Abschnitte mit `##` und Umschlag
  `<kontext_automatisch>` (`core/cloud.py` ~414). „Erst nach Tests ergänzen“
  ist keine feste Regel.
- **Heute bei ZENTRALE:** Der Prompt ist in Abschnitte geteilt. Regeln kamen
  bisher oft als Reaktion auf einen Einzelfall dazu, nicht nach einem Test.

### P-04 Wenige typische Beispiele statt Sonderfall-Listen

- **Regel:** Statt jeden Sonderfall als Regel aufzuzählen: 3–5 verschiedene,
  typische Beispiele.
- **Zitat:** „curate a set of diverse, canonical examples“
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
  und https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
  (3–5 Beispiele) — offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Die Meta-Regeln und Werkzeug-Texte zählen viele
  Sonderfälle auf. Beispiele in Werkzeugen: [W-05](werkzeuge.md#w-05-beispiele-in-den-werkzeugen).

### P-05 Anthropic nachahmen, eigene Ergänzungen erst bei Bedarf

- **Regel:** Aufbau und Wortlaut von Anthropics Prompt übernehmen. Eigene
  Regeln kommen erst dazu, wenn ein Fall zeigt, dass sie nötig sind.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026
- **Gilt für:** claude-gross
- **Status:** offen
- **Heute bei ZENTRALE:** Der gross-Prompt ist aus dem klein-Prompt
  abgeleitet, nicht aus Anthropics Prompt. Am 14.10. wurde Ballast entfernt
  (cb8c662), nachgebaut ist noch nichts.

### P-06 Keine Kalender-Schlagseite

- **Regel:** Die Kalender-Regel hängt nicht bei jeder Nachricht ganz hinten.
  Was zuletzt steht, wirkt am stärksten. Deshalb denkt die KI sonst bei allem
  zuerst an den Kalender.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** offen — `core/ki_prompt.py` ~127–133 (Satz „Kalender/Termine: …
  hast du NICHT im Kopf“ im Jetzt-Block)
- **Heute bei ZENTRALE:** Der Jetzt-Block mit der Kalender-Regel hängt im
  Umschlag hinten an jeder Nutzernachricht.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
- **2026-10-22** — P-02 nachgezogen (Durchgang Werkzeuge, 0446ae5).
