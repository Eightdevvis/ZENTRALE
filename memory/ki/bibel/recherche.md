# KI-Bibel — Recherche: suchen, Seiten lesen, mehrere Runden, Fazit

**Stand 2026-10-22:** Achtzehn Einträge (R-01 bis R-18). Fast alles ist offen.
Anlass war das Jeans-Gespräch vom 14.10.: vier Suchen, keine Seite gelesen,
dann „gibt es wohl nicht“. Der Ablauf, den die Einträge zusammen ergeben:
**breit suchen → die besten Treffer lesen → bei Lücken oder Widersprüchen
weitere Runden → Fazit mit Rechenschaft.** Wie Suche und Abruf technisch
laufen: `memory/ki/internet_netz.md`. Legende und Pflegeregeln: [README.md](README.md).

---

### R-01 Seiten lesen muss angewiesen werden

- **Regel:** Nach der Suche werden die besten Treffer mit fetch_url gelesen.
  Das muss im Prompt oder Werkzeug stehen, von allein tut das Modell es nicht.
  „Laut Suchtreffer“ ist kein Ausweg statt Lesen.
- **Zitat:** „For security reasons, the web fetch tool can only fetch URLs
  that have previously appeared in the conversation context. This includes:
  URLs in user messages; URLs in client-side tool results; URLs from previous
  web search or web fetch results.“ / „Claude does not fetch for
  general-knowledge or open-ended questions that don't reference a specific page.“
- **Quelle:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool —
  offiziell, erfasst 22.10.2026; Anlass: Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** offen — `core/web.py` ~188 erlaubt „laut Suchtreffer, nicht
  nachgelesen“ als Kennzeichnung; Lesen ist nirgends Pflicht
- **Heute bei ZENTRALE:** Das Modell darf aus Schnipseln antworten, wenn es
  das kennzeichnet. Im Jeans-Gespräch hat es keine Seite gelesen.

### R-02 Ablauf: suchen, auswählen, lesen

- **Regel:** 1. Suchen. 2. Die vielversprechendsten Treffer auswählen.
  3. Diese ganz lesen.
- **Zitat:** „Claude: 1. Uses web search to find relevant articles. 2. Selects
  the most promising results. 3. Uses web fetch to retrieve full content.“
- **Quelle:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — Recherche-Skill Schritt 3 (`data/gedaechtnis/ki/skills/recherche/SKILL.md`,
  ungetrackt): „die ein, zwei vielversprechendsten Treffer mit fetch_url lesen“,
  aber nur bei „Zahlen, Daten oder Regeln“
- **Heute bei ZENTRALE:** Steht nur im Skill, und nur für einen Teil der
  Fragen. Siehe R-13.

### R-03 Erst breit und kurz, dann eingrenzen

- **Regel:** Suchanfragen kurz (1–6 Wörter). Mit 1–2 Wörtern breit anfangen,
  dann eingrenzen. Zu lange Suchanfragen sind ein bekanntes Fehlerbild.
- **Zitat:** „Queries short and specific, 1-6 words. Start broad (1-2 words),
  then narrow.“
- **Quelle:** https://www.anthropic.com/engineering/multi-agent-research-system —
  offiziell, erfasst 22.10.2026; Zitat aus dem **inoffiziellen** Leak des
  claude.ai-Prompts Sonnet 5.5, https://github.com/asgeirtj/system_prompts_leaks,
  29.09.2026, unbestätigt
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Keine Vorgabe zur Länge der Suchanfragen.

### R-04 Anzahl der Werkzeug-Aufrufe nach Schwierigkeit

- **Regel:** Ein Fakt: 1 Aufruf. Mittlere Aufgabe: 3–8. Tiefere oder breitere
  Frage: 8–20. Nicht früh aufhören, keine nötige Suche auslassen. Fertig ist
  man erst, wenn jeder Teil der Antwort auf etwas Abgerufenem steht.
- **Zitat:** „Scale tool calls to complexity: 1 for a single fact; 3–8 for
  medium tasks; 8–20 for deeper or broader questions … Don't stop early and
  don't skip searches the answer needs. Stop when every part of the answer is
  grounded in something you retrieved.“
- **Quelle:** **inoffiziell** — Leak Sonnet 5.5, https://github.com/asgeirtj/system_prompts_leaks,
  29.09.2026, unbestätigt. Offiziell passend: einfache Fragen 3–10
  Aufrufe, https://www.anthropic.com/engineering/multi-agent-research-system.
  Älter, **inoffiziell**: Claude-4-Leak Mai 2025 „Research category need 2-20
  tool calls“ (https://simonwillison.net/2025/May/25/claude-4-system-prompt/)
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Keine Vorgabe; die Werkzeug-Texte sagen eher
  „sparsam“ (siehe W-03 in [werkzeuge.md](werkzeuge.md)).

### R-05 Gibt Sasha eine Adresse, wird sie gelesen

- **Regel:** Nennt Sasha eine URL oder Website, ruft die KI sie immer ab.
- **Zitat:** „When the person gives a URL or site, ALWAYS web_fetch it“
- **Quelle:** **inoffiziell** — Leak Sonnet 5.5, https://github.com/asgeirtj/system_prompts_leaks,
  29.09.2026, unbestätigt
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Nicht geregelt. (Großbuchstaben beim Übernehmen
  weglassen, siehe P-02 in [prompt.md](prompt.md).)

### R-06 Schnipsel reichen nicht, ganze Seite lesen

- **Regel:** Suchschnipsel sind oft zu kurz. Für den Inhalt die Seite lesen,
  zum Beispiel nach einer News-Suche den Artikel.
- **Zitat:** „Use web_fetch for full page content, since search snippets are
  often too brief (e.g. after searching news, web_fetch the article).“
- **Quelle:** **inoffiziell** — Leak Sonnet 5.5, https://github.com/asgeirtj/system_prompts_leaks,
  29.09.2026, unbestätigt
- **Gilt für:** alle
- **Status:** offen — siehe R-01
- **Heute bei ZENTRALE:** Antworten aus Schnipseln sind erlaubt.

### R-07 Widersprüche oder Lücken: weitersuchen, mehrere Quellen

- **Regel:** Widersprechen sich Ergebnisse oder fehlt etwas, folgen weitere
  Suchen. Wichtige Angaben werden an mehreren Quellen geprüft.
- **Zitat:** „When results conflict or seem incomplete, run more searches.“ /
  „Encourage source verification: Ask Claude to verify information across
  multiple sources.“
- **Quelle:** **inoffiziell** — Leak Sonnet 5.5 (erstes Zitat),
  https://github.com/asgeirtj/system_prompts_leaks, 29.09.2026;
  offiziell (zweites Zitat) https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices,
  erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Nicht geregelt.

### R-08 Klare Erfolgskriterien

- **Regel:** Bei einer Recherche steht fest, wann sie fertig ist und was
  herauskommen soll.
- **Zitat:** „Provide clear success criteria“
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Keine Erfolgskriterien für Recherche.

### R-09 Strukturiert vorgehen: Hypothesen, Sicherheit, Notizen

- **Regel:** Bei größeren Recherchen mehrere Hypothesen verfolgen, die eigene
  Sicherheit festhalten, den Weg selbst kritisch prüfen und Notizen führen.
- **Zitat:** „Search for this information in a structured way. As you gather
  data, develop several competing hypotheses. Track your confidence levels in
  your progress notes to improve calibration. Regularly self-critique your
  approach and plan. Update a hypothesis tree or research notes file to
  persist information and provide transparency. Break down this complex
  research task systematically.“
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Nicht geregelt.

### R-10 Erst nachsehen, dann antworten

- **Regel:** Nie über eine Seite, Notiz oder Datei spekulieren, die nicht
  geöffnet wurde. Nennt Sasha eine bestimmte Quelle, wird sie vor der Antwort
  gelesen. (Anthropic sagt das für Code, ZENTRALE überträgt es auf Webseiten
  und Notizen.)
- **Zitat:** „Never speculate about code you have not opened. If the user
  references a specific file, you MUST read the file before answering. Make
  sure to investigate and read relevant files BEFORE answering questions about
  the codebase. Never make any claims about code before investigating unless
  you are certain of the correct answer - give grounded and hallucination-free
  answers.“
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
  (`<investigate_before_answering>`) — offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — für Notizen: Meta-Regel 1 in `core/profil/gross.py`
  ~248 („nachlesen (read_note) oder suchen“); für Webseiten offen
- **Heute bei ZENTRALE:** Bei Notizen gilt „nachlesen statt raten“, bei
  Webseiten nicht.

### R-11 Nicht endlos nach Nicht-Existentem suchen

- **Regel:** Wer nach mehreren sinnvollen Runden nichts findet, hört auf und
  sagt das mit Rechenschaft (R-14). Endloses Suchen ist ein bekanntes
  Fehlerbild, genau wie zu frühes Aufgeben.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/multi-agent-research-system —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Nur die Rundengrenze der Werkzeug-Schleife
  begrenzt (`memory/ki/werkzeug_schleife.md`).

### R-12 Aktuelles nachprüfen statt aus dem Training antworten

- **Regel:** Den Satz „nur wenn unbedingt nötig Werkzeuge nutzen“ gibt es
  nicht. Was sich seit dem Training geändert haben kann (erlaubt, Pflicht,
  Preis), wird nachgesehen, auch wenn die KI sich sicher fühlt. Berichte und
  Vergleiche entstehen aus aktuellen Quellen.
- **Zitat:** „Use the search tool to check specifics that may have changed
  since your training, such as what is allowed, required or charged, even when
  you feel confident. For researched work such as a report or a comparison,
  gather current sources rather than writing from your training knowledge.“
  (statt „only use tools when strictly necessary“)
- **Quelle:** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5 —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen — Satz nicht im gross-Prompt gefunden
- **Heute bei ZENTRALE:** web_search sagt „sparsam“ (siehe W-03 in
  [werkzeuge.md](werkzeuge.md)).

### R-13 Recherche-Skill passt nicht zu „finde etwas in der Welt“

- **Regel:** Der Recherche-Skill muss auch Suchaufträge abdecken („finde mir
  eine Jeans, die …“), nicht nur Wissenslücken. Lesen gilt immer, nicht nur bei
  Zahlen, Daten, Regeln.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** offen — `data/gedaechtnis/ki/skills/recherche/SKILL.md` (ungetrackt):
  Beschreibung „…das du nicht sicher weißt“, fetch_url nur bei „Zahlen,
  Daten oder Regeln“
- **Heute bei ZENTRALE:** Der Skill greift bei Wissensfragen, nicht bei
  Suchaufträgen.

### R-14 Rechenschaft statt Pauschalverneinung

- **Regel:** Am Ende sagt die KI, was sie wie recherchiert hat („3 Seiten
  gelesen, nichts gefunden“) und was daraus folgt. Kein „gibt es wohl nicht“
  ohne Grundlage. Auswege (andere Läden, selbst suchen) erst nach echter
  Recherche.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Nicht geregelt; der Prüfer sieht es nicht
  (PR-04 in [pruefung.md](pruefung.md)).

### R-15 Mehrere Runden: länger, dafür klüger

- **Regel:** Lieber mehrere Such- und Leserunden und eine gute Antwort als
  eine schnelle schlechte.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026; passt zu R-04
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Nicht geregelt.

### R-16 Schnelle Suche zuerst (web_search_fast)

- **Regel:** Im geleakten Prompt gibt es ein schnelles Suchwerkzeug, das
  zuerst benutzt wird. Zu prüfen, ob ZENTRALE eine schnelle und eine
  gründliche Suche braucht.
- **Zitat:** —
- **Quelle:** **inoffiziell** — Leak Sonnet 5.5, https://github.com/asgeirtj/system_prompts_leaks,
  29.09.2026, unbestätigt
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Eine Suche (SearXNG).

### R-17 Suchanweisungen bekommen Platz

- **Regel:** Anthropic gibt der Suche viel Prompt-Platz. Das steht in
  Spannung zum Budget (P-01 in [prompt.md](prompt.md)): Suchregeln eher in die
  Werkzeug-Beschreibungen oder den Recherche-Skill legen.
- **Zitat:** —
- **Quelle:** **inoffiziell** — Claude-4-Leak Mai 2025 (Pliny/CL4R1T4S),
  Suchanweisungen ~6.471 Tokens, https://simonwillison.net/2025/May/25/claude-4-system-prompt/;
  Claude-4.6-Leak gesamt ~15.000 Tokens laut Adversa AI,
  https://adversa.ai/blog/revealing-claude-4-6-system-prompt-using-a-chain-of-partial-to-full-prompt-leak-attack;
  Leak Sonnet 5.5 ~481.000 Zeichen inkl. Werkzeug-Schemas,
  https://github.com/asgeirtj/system_prompts_leaks, 29.09.2026. Alle unbestätigt.
- **Gilt für:** claude-gross
- **Status:** offen
- **Heute bei ZENTRALE:** Zur Suche gibt es nur die Werkzeug-Texte und den
  Skill.

### R-18 Vorbilder für mehrstufige Recherche

- **Regel:** Zum Nachschauen, wie andere es bauen: OpenAI Deep Research
  (mehrstufiges Browsen, mit RL trainiert), Perplexity Pro Search (Plan, Suche
  je Schritt, Treffer filtern und ranken). Anthropic: Mehr-Agenten-Recherche
  braucht ~15× so viele Tokens wie ein Chat, ein einzelner Agent ~4×.
- **Zitat:** —
- **Quelle:** **inoffiziell** — OpenAI Deep Research über Sekundärquelle
  maginative.com; Perplexity: https://www.langchain.com/breakoutagents/perplexity.
  Offiziell (Token-Faktoren): https://www.anthropic.com/engineering/multi-agent-research-system,
  erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen
- **Heute bei ZENTRALE:** Ein Agent, keine Unter-Agenten.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
