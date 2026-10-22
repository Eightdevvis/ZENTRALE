# KI-Bibel — Werkzeuge: Beschreibungen, Suche, Ergebnisse

**Stand 2026-10-22:** Vierzehn Einträge (W-01 bis W-14). W-14 (Kalender-Felder
nur aus Sashas Angaben) ist umgesetzt. Die Werkzeug-Suche
ist gebaut, aber ausgeschaltet; Beschreibungen und Fehlertexte sind teilweise
umgestellt. Offen sind vor allem Beispiele, knappe Ergebnisse, Schritt 9 und
10 der Suche und die Großbuchstaben. Wie die Werkzeuge heute gebaut sind:
`memory/ki/werkzeuge.md`, die Suche: `memory/ki/werkzeug_suche.md`.
Legende und Pflegeregeln: [README.md](README.md).

---

### W-01 Werkzeug-Beschreibungen sind der wichtigste Hebel

- **Regel:** Jede Beschreibung hat mindestens 3–4 Sätze: was das Werkzeug
  tut, wann man es benutzt, wann nicht, und was es nicht liefert. Eine Regel,
  die nur ein Werkzeug betrifft, steht in dessen Beschreibung, nicht im Prompt.
- **Zitat:** „by far the most important factor“; „can yield dramatic improvements“
- **Quelle:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools,
  https://www.anthropic.com/engineering/writing-tools-for-agents — offiziell,
  erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — `core/werkzeug_register.py` (cb8c662); nicht jede
  Beschreibung geprüft
- **Heute bei ZENTRALE:** Seit 14.10. die Leitlinie
  (`memory/ki/prompt_aufbau.md`, „Prompt-Budget und Werkzeug-Beschreibungen“).
  Ob alle 71 Werkzeuge sie erfüllen, ist nicht gezählt.

### W-02 Fehlermeldungen sagen, was als Nächstes zu tun ist

- **Regel:** Ein Fehler im Werkzeug-Ergebnis nennt nicht nur das Problem,
  sondern den nächsten sinnvollen Schritt.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/writing-tools-for-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — K-Codes mit „Was tun“-Texten in
  `core/fehlercodes.py`; Deadline- und uncommitted-Felder (7b37c4c, 4cabae0);
  K-TITEL-WOCHENTAG mit „Was tun“ im Abbruch (c3955c0)
- **Heute bei ZENTRALE:** Die Kalender-Werkzeuge haben Fehlercodes mit
  Handlungstext. Andere Werkzeuge geben oft nur den Fehler zurück.

### W-03 Freigabe-Texte stimmen mit dem echten Freigabestand überein

- **Regel:** Ein Werkzeug-Text sagt nur „muss Sasha bestätigen“, wenn das
  gerade wirklich gilt. Der Satz hängt am echten Freigabestand.
- **Zitat:** —
- **Quelle:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
  (Beschreibung muss stimmen) — offiziell; Befund Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** offen — `core/werkzeug_register.py` ~562–597 (web_search,
  fetch_url: „Jede Suche muss Sasha bestätigen“)
- **Heute bei ZENTRALE:** Suche und Abruf sind freigegeben, die Texte sagen
  trotzdem „bestätigen, also sparsam“. Das bremst die Recherche.

### W-04 Keine Werkzeuge, die sich überschneiden

- **Regel:** Für jede Lage ist genau ein Werkzeug das richtige. Überschneiden
  sich zwei, wird eins gestrichen oder klar abgegrenzt.
- **Zitat:** „If a human engineer can't definitively say which tool should be
  used in a given situation, an AI agent can't be expected to do better.“
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** 71 Werkzeuge auf gross; eine Prüfung auf
  Überschneidung gab es nicht.

### W-05 Beispiele in den Werkzeugen

- **Regel:** Werkzeuge bekommen wenige typische Aufruf-Beispiele
  (`input_examples`), statt Sonderfälle im Text aufzuzählen.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/advanced-tool-use —
  offiziell, nur aus einem Extrakt (Trefferquote 72 % → 90 %), erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen — kein `input_examples` im Code
- **Heute bei ZENTRALE:** Beispiele stehen, wenn überhaupt, als Fließtext in
  der Beschreibung. Siehe auch [P-04](prompt.md#p-04-wenige-typische-beispiele-statt-sonderfall-listen).

### W-06 Werkzeug-Antworten knapp halten

- **Regel:** Ergebnisse sind knapp: Seiten (Paginierung), Bereich, Filter,
  Kürzen mit Hinweis. Claude Code begrenzt eine Werkzeug-Antwort auf 25.000
  Tokens.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/writing-tools-for-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen — `cloud.kappen()` kürzt nur Verlauf-Nachrichten, keine
  einheitliche Grenze für Werkzeug-Ergebnisse gefunden
- **Heute bei ZENTRALE:** Einzelne Werkzeuge kürzen selbst, eine gemeinsame
  Regel gibt es nicht.

### W-07 Werkzeug-Suche: höchstens fünf geladen, der Rest auf Bedarf

- **Regel:** Nur 3–5 Werkzeuge sind immer geladen, der Rest kommt per Suche
  (`defer_loading`). Lohnt ab etwa 10 Werkzeugen oder 10.000 Tokens. Namen mit
  Präfixen, Kategorien im Prompt nennen. Höchstens fünf (Sasha).
- **Zitat:** „~55k tokens in definitions … reduces this by over 85 percent,
  loading only the 3–5 tools Claude needs“; „Claude's ability to pick the
  right tool degrades once you exceed 30–50 available tools.“
- **Quelle:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool —
  offiziell, erfasst 22.10.2026; Messwerte (Opus 4: 49 → 74 %, Opus 4.5:
  79,5 → 88,1 %) aus https://www.anthropic.com/engineering/advanced-tool-use
  (Extrakt); „max. 5“: Sasha, 14.10.2026
- **Gilt für:** claude-gross, qwen (über die Vorauswahl)
- **Status:** teilweise — gebaut (`core/werkzeug_suche.py`,
  `core/werkzeug_gruppen.py`, Doku f23b556), Schalter `werkzeug_suche` aus
- **Heute bei ZENTRALE:** Kern = antwort, search_tools, web_search,
  fetch_url, read_calendar. Solange der Schalter aus ist, gehen alle 71
  Werkzeuge mit. Einschalten erst nach [W-09](#w-09-prüfstand-ab-für-die-werkzeug-suche).

### W-08 Die Suche im Prompt erklären (Schritt 9)

- **Regel:** Ein Satz im Prompt nennt search_tools und die Kategorien, ein
  Merkmal in `MERKMALE`. Stellen, die zurückgestellte Werkzeuge beim Namen
  nennen, werden angepasst.
- **Zitat:** —
- **Quelle:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
  (Kategorien im Prompt nennen) — offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — Liste der Stellen in `memory/ki/werkzeug_suche.md`
  („Stellen, die zurückgestellte Werkzeuge beim Namen nennen“)
- **Heute bei ZENTRALE:** Nur die Werkzeug-Beschreibung von search_tools
  erklärt die Suche.

### W-09 Prüfstand A/B für die Werkzeug-Suche (Schritt 10)

- **Regel:** Erst messen, dann einschalten: dieselben Fälle mit Schalter aus
  und an, danach Standard an.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  (Werkzeuge per Evals verbessern) — offiziell; Bauplan in
  `memory/ki/werkzeug_suche.md`, Stand 14.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — braucht Sashas Okay für die Kosten (~3,50 € mit
  Sonnet-Richter, ~2,50 € mit Haiku-Richter)
- **Heute bei ZENTRALE:** Nicht gelaufen.

### W-10 Werkzeug-Texte nennen Sashas Wörter

- **Regel:** Eine Beschreibung enthält die Wörter, die Sasha wirklich benutzt,
  nicht nur die Fachbegriffe des Codes.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** teilweise — Beispiel uncommitted / vielleicht / unverbindlich
  (4cabae0)
- **Heute bei ZENTRALE:** Beim Kalender-Feld uncommitted umgesetzt, sonst
  nicht systematisch.

### W-11 Großbuchstaben raus aus den Werkzeug-Beschreibungen

- **Regel:** Wie [P-02](prompt.md#p-02-normale-sprache-statt-großbuchstaben-befehle),
  aber für die Werkzeug-Texte der Schiene gross.
- **Zitat:** —
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices —
  offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — `core/werkzeug_register.py` (antwort ~636 „JEDE
  Antwort“, run_code, save_from_sandbox, Kalender-Phasen/-Routinen ~298–365)
- **Heute bei ZENTRALE:** Die Texte sind mit klein geteilt oder noch nicht
  umgeschrieben.

### W-12 Programmatic Tool Calling

- **Regel:** Werkzeuge per Code aufrufen lassen, wenn viele Aufrufe
  hintereinander kommen. Spart laut Anthropic 37 % Tokens.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/advanced-tool-use —
  offiziell, nur Extrakt, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen
- **Heute bei ZENTRALE:** Nicht gebaut, nicht geplant.

### W-14 Kalender-Felder nur aus dem, was Sasha gesagt hat

- **Regel:** Die Kalender-Schreibwerkzeuge sagen kurz: Felder nur aus Sashas
  Angaben füllen, kein von/bis, kein Ende, keine Ebene erfinden. Der Titel
  bleibt, wie Sasha die Sache nennt, ohne Wochentag oder Uhrzeit. Das Genaue
  steht in den Feldern (Kalender-Deckel 2.620 in `tests/test_profil.py`).
  Was Python prüfen kann, prüft Python danach ([PR-12](pruefung.md#pr-12-kalender-werte-ohne-grundlage),
  [PR-13](pruefung.md#pr-13-wochentag-im-titel-gegen-regel-und-datum)).
- **Zitat:** —
- **Quelle:** Sasha/Kalender-Session, 22.10.2026 — Gespräch
  20261022-111358-dd6127 („der wochentausch ist doch ziemlich böse. können wir
  die qwen etwas aufpeppen?“)
- **Gilt für:** claude-gross, qwen
- **Status:** umgesetzt — `core/werkzeug_kalender.py` (`_TITEL_NEU`, `_ENDE`,
  `_ZEITRAUM_VON/_BIS`, Texte von add_calendar_entry/routine, `neuer_titel`
  der edit-Werkzeuge), qwen-Regel 5 in `core/profil/modelle/qwen.py`; c3955c0
- **Heute bei ZENTRALE:** add_calendar_entry: „Füll nur Felder, die Sasha
  genannt hat — kein Ende, keine Ebene erfinden.“ add_calendar_routine: „Füll
  nur Felder, die Sasha genannt hat — von/bis, Ende, Ebene nie erfinden; fehlt
  das Ende der Serie, frag nach.“ qwen bekommt dieselben Texte (Zuschnitt
  geprüft in `tests/test_kalender_nachpruefung.py`).

### W-13 Claude Code hält ~15 Werkzeuge geladen

- **Regel:** Keine Regel, eine Beobachtung zum Vergleich: Claude Code selbst
  hält ~15 Werkzeuge geladen und ~30 per Suche. Gilt hier nicht, Sasha hat
  höchstens fünf festgelegt ([W-07](#w-07-werkzeug-suche-höchstens-fünf-geladen-der-rest-auf-bedarf)).
- **Zitat:** —
- **Quelle:** **inoffiziell** — Beobachtung in Claude Code, 15.10.2026
- **Gilt für:** claude-gross
- **Status:** offen (nur zum Vergleich)
- **Heute bei ZENTRALE:** Kern mit fünf Werkzeugen.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
- **2026-10-22** — W-14 neu und umgesetzt (c3955c0); W-02 um K-TITEL-WOCHENTAG ergänzt.
