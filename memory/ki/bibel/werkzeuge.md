# KI-Bibel — Werkzeuge: Beschreibungen, Suche, Ergebnisse

**Stand 2026-10-22 (spät):** Vierzehn Einträge (W-01 bis W-14). Umgesetzt:
W-08 (Suche im Prompt, hinter dem Schalter), W-11 (Großbuchstaben), W-14.
Die Werkzeug-Suche ist gebaut, aber ausgeschaltet; der Prüfstand (W-09) steht
aus. Beschreibungen, Abgrenzung, Beispiele und knappe Ergebnisse sind
teilweise umgestellt (Durchgang Werkzeuge, 0446ae5). Wie die Werkzeuge heute gebaut sind:
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
- **Status:** teilweise — `core/werkzeug_register.py` (cb8c662); web_search
  und fetch_url seit 9cce25a mit was / wann ja / wann nein / was nicht (je
  ~430–530 Zeichen, eigener Deckel in `tests/test_profil.py`). Seit 0446ae5 auch
  die übrigen Kern-Werkzeuge: read_calendar (~530), antwort (~295, Deckel 300),
  search_tools (`core/werkzeug_nachschlagen.py`), dazu read_time, read_note,
  search_memory, search_chats, write_note, read_document, update_document,
  read_file. Offen: die übrigen ~55 Werkzeuge (meist ein, zwei Sätze) und die
  Skill-Werkzeuge, deren Deckel (600) keinen Platz lässt.
- **Heute bei ZENTRALE:** Seit 14.10. die Leitlinie
  (`memory/ki/prompt_aufbau.md`, „Prompt-Budget und Werkzeug-Beschreibungen“).
  Die fünf immer geladenen erfüllen sie; Beschreibungen gesamt auf gross
  12.706 → 13.198 Zeichen. Die Konflikt-Regel stand in read_calendar, das
  keine Warnungen zeigt; sie steht jetzt im Alarm-Block.

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
- **Status:** teilweise — gross umgesetzt (9cce25a): Feld `freigabe_im_text`
  (`core/werkzeug_eintrag.py`), `erlaubnis.mit_freigabe` hängt beim Senden
  (`cloud.run`, `cloud_openai.chat_stream`) den Satz zum Stand an, der für den
  nächsten Aufruf gilt (`erlaubnis.vorab`: „immer“ in `ai_config`
  `immer_erlaubt` oder „für dieses Gespräch“): „Freigegeben: läuft ohne
  Rückfrage an Sasha.“ bzw. „Vor dem Aufruf fragt ZENTRALE Sasha selbst per
  Knopf; frag nicht vorher im Text.“ Offen: die klein-Texte (web_suche,
  hole_url) sagen weiter „muss Sasha bestätigen“ — bewusst so gelassen
  (22.10., Durchgang Werkzeuge): klein ist gemessener Kanon und bleibt
  byte-gleich, ändern erst mit einer Nachmessung gegen das lokale qwen.
  Andere gegatete Werkzeuge auf gross sagen „Wird bestätigt“ fest im Text
  (create_series, run_code, rewrite_note, PDF/Word …) — stimmt, solange sie
  nicht auf „immer“ stehen; nicht an den Freigabestand gehängt.
- **Heute bei ZENTRALE:** Auf gross stimmt der Satz mit dem echten Stand
  überein (Sasha: beide auf „immer“); ändert er den Stand, ändert sich der
  Text einmal (kostet einmal den Prompt-Cache).

### W-04 Keine Werkzeuge, die sich überschneiden

- **Regel:** Für jede Lage ist genau ein Werkzeug das richtige. Überschneiden
  sich zwei, wird eins gestrichen oder klar abgegrenzt.
- **Zitat:** „If a human engineer can't definitively say which tool should be
  used in a given situation, an AI agent can't be expected to do better.“
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — Paare benannt und Beschreibungen geschärft (0446ae5,
  `core/werkzeug_register.py`, `core/werkzeug_dateien.py`); nichts gelöscht
  oder zusammengelegt.
- **Heute bei ZENTRALE:** Paare, bei denen ein Mensch nicht sicher sagen
  konnte, welches passt (Stand 22.10.):
  1. read_file / read_document — beide lesen ein Ablage-Dokument. Jetzt:
     read_file liest jedes (auch PDF/Word/Excel, per Titel), read_document
     Text per id in Stücken, zum Neufassen mit update_document.
  2. update_document / replace_document — beide machen eine neue Fassung.
     Jetzt: update für Text (alte Fassung bleibt), replace für PDF/Word.
  3. write_note / create_document — „halt das fest“ gegen „leg mir das an“.
     write_note sagt jetzt: Text zum Lesen oder Mitnehmen ist create_document.
  4. search_memory / search_chats / search_files — drei Suchen, drei
     Speicher; jede nennt jetzt die beiden anderen.
  5. add_calendar_pause / edit_calendar_routine (loeschen + nur_am) — beides
     lässt einen Tag einer Serie ausfallen. Noch nicht geschärft
     (Kalender-Deckel).
  6. fetch_url / fetch_document / browser_open — war schon abgegrenzt.
  Vorschläge zum Zusammenlegen (nicht gebaut, Sasha entscheidet):
  read_document in read_file aufgehen lassen; update_document und
  replace_document zu einem Werkzeug „neue Fassung“; einen Tag absagen nur
  noch über edit_calendar_routine (nur_am), Pause nur für Zeiträume.

### W-05 Beispiele in den Werkzeugen

- **Regel:** Werkzeuge bekommen wenige typische Aufruf-Beispiele
  (`input_examples`), statt Sonderfälle im Text aufzuzählen.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/advanced-tool-use —
  offiziell, nur aus einem Extrakt (Trefferquote 72 % → 90 %), erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — `core/werkzeug_beispiele.py`, eingehängt in
  `cloud._to_anthropic_tools(beispiele=True)`; 0446ae5. Je zwei Beispiele für
  read_calendar, add_calendar_routine, edit_calendar_routine.
- **Heute bei ZENTRALE:** Anthropic nimmt `input_examples` ohne Beta-Header
  (Doku define-tools, abgerufen 22.10.2026); jedes Beispiel muss zum
  input_schema passen, sonst 400. Deshalb prüft der Code jedes Beispiel mit
  jsonschema gegen das Schema des laufenden Prozesses und lässt unpassende
  weg. Nur gross, nur Anthropic, nur an Werkzeugen ohne `defer_loading`
  (ob beides zusammen geht, sagt die Doku nicht). Die OpenAI-Seite (qwen)
  bekommt das Feld nicht: das Funktions-Schema dort kennt es nicht, und ob
  DashScope ein unbekanntes Feld ablehnt, ist ungeprüft. Gegen echte API
  nicht gelaufen (kostet). Weitere Werkzeuge erst nach dem Prüfstand.
  Siehe auch [P-04](prompt.md#p-04-wenige-typische-beispiele-statt-sonderfall-listen).

### W-06 Werkzeug-Antworten knapp halten

- **Regel:** Ergebnisse sind knapp: Seiten (Paginierung), Bereich, Filter,
  Kürzen mit Hinweis. Claude Code begrenzt eine Werkzeug-Antwort auf 25.000
  Tokens.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/writing-tools-for-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — read_document liest lange Texte in Stücken zu
  30.000 Zeichen mit „weiter mit … ab=“ (`core/ki_werkzeuge.py`
  `_stueck`, 0446ae5); vorher ging ein Dokument bis 400.000 Zeichen am Stück
  zurück. Eine gemeinsame Grenze gibt es weiter nicht.
- **Heute bei ZENTRALE:** Geprüft am 22.10.: gekürzt bzw. in Seiten sind
  fetch_url, read_file (30.000), read_project_file (20.000, ab), run_code
  (20.000 je Strom), find_files/search_files/list_files (Trefferzahl),
  search_chats (8), search_memory (12), read_chat (≤ 40 Nachrichten),
  read_xlsx (Bereich), read_docx/read_pdf (ab bzw. Seiten). Offen: read_note
  liest eine Datei ganz (Dossiers ab 20.000 Zeichen werden nur beim
  Schreiben gewarnt), read_calendar mit langem Zeitraum, read_chat mit sehr
  langen Nachrichten.

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
- **Status:** umgesetzt (hinter dem Schalter, Standard aus) — 0446ae5:
  `profil.gross.SUCHE` + `MERKMALE["werkzeug_suche"]`,
  `cloud._suche_im_prompt`/`_static_system`, `gedaechtnis._REGELN_SUCHE`,
  `ki_prompt._now_prompt(suche=)`, `projekte.prompt_block(suche=)`, Feld
  `mit_suche` (`core/werkzeug_eintrag.py`); Tests `tests/test_werkzeug_texte.py`
- **Heute bei ZENTRALE:** Mit Schalter an steht hinter den Meta-Regeln
  „## Werkzeuge laden“ (Kern, search_tools, Kategorien), und jede Stelle,
  die ein zurückgestelltes Werkzeug nennt, sagt „über search_tools“. Aus:
  alles byte-gleich. Einzelheiten: `memory/ki/werkzeug_suche.md`, „Schritt 9“.

### W-09 Prüfstand A/B für die Werkzeug-Suche (Schritt 10)

- **Regel:** Erst messen, dann einschalten: dieselben Fälle mit Schalter aus
  und an, danach Standard an.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  (Werkzeuge per Evals verbessern) — offiziell; Bauplan in
  `memory/ki/werkzeug_suche.md`, Stand 14.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — braucht Sashas Okay für die Kosten (~3,50 € mit
  Sonnet-Richter, ~2,50 € mit Haiku-Richter). Schritt 9 ist seit 0446ae5 gebaut,
  der Prüfstand kann also laufen.
- **Heute bei ZENTRALE:** Nicht gelaufen. Wie: `memory/ki/pruefstand.md`;
  für qwen dieselben Fälle mit `ZENTRALE_WERKZEUG_SUCHE=aus` und `=an`.

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
- **Status:** umgesetzt — 0446ae5: `core/werkzeug_register.py` (antwort, run_code,
  save_from_sandbox, read_note, write_note, search_memory, rewrite_note,
  fetch_document, propose_skill, Kalender-Rückfall-Texte),
  `core/werkzeug_kalender.py` (Routinen, Phasen, Gruppe, Ebene, Stil,
  Quelle, Feld kategorie/label, qwen-Kurztexte `einfach`),
  `core/werkzeug_pdf_word.py` (edit_docx), `core/selbstauskunft.py` (Feld
  erledigt). Wächter: `tests/test_werkzeug_texte.py`
  (`test_keine_grossbuchstaben_befehle_in_den_gross_texten`).
- **Heute bei ZENTRALE:** Alle gross-Texte und -Felder in normaler
  Schreibung; groß bleiben nur Formate und Namen (RRULE, PDF, LSF …). qwen
  bekommt dieselben Texte (der Zuschnitt erhält sie; „erfinden“ bleibt drin,
  `tests/test_kalender_nachpruefung.py`). klein unverändert.

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
- **2026-10-22** — W-03 teilweise, W-01 ergänzt (9cce25a, Durchgang Recherche).
- **2026-10-22** — Durchgang Werkzeuge (0446ae5): W-08, W-11 umgesetzt; W-04,
  W-05, W-06 teilweise; W-01, W-03, W-09 ergänzt.
