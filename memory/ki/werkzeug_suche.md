# Werkzeug-Suche — fester Kern, der Rest auf Bedarf (seit 2026-10-14)

**Stand:** gebaut (Schritte 1–8 des Bauplans), Schalter `werkzeug_suche`
**Standard aus** — am Live-Verhalten ändert sich nichts, bis der Prüfstand
gelaufen ist. Einschalten: Einstellung `werkzeug_suche = an` (oder Env
`ZENTRALE_WERKZEUG_SUCHE=an`). Weil `profil.gross.TOOLS` beim Import entsteht,
gilt ein Umschalten erst nach einem Neustart des Servers.
Regeln und offene Punkte dazu (W-07 bis W-09): KI-Bibel
[bibel/werkzeuge.md](bibel/werkzeuge.md).

## Warum

Die gross-Schiene gab jedem Zug alle 71 Werkzeuge mit (~45.000 Zeichen
Schema). Gecacht, aber gelesen — und je mehr Werkzeuge, desto öfter greift
ein Modell daneben (OpenAI: „unter 20 zu Beginn eines Zugs"; das qwen-Profil
hat deshalb seit Runde 9 eine Vorauswahl, [modell_profile.md](modell_profile.md)).
Anthropic löst das mit **Werkzeug-Suche** (`defer_loading` + Suchwerkzeug)
und bei Skills mit **progressive disclosure** (im Kopf nur, wann einer passt;
der Rest beim Laden). Das hier macht beides nach.

## Wie es läuft

- **Fester Kern** (`werkzeug_gruppen.IMMER`, höchstens fünf — Sasha nach
  Anthropics Doku „keep the 3–5 tools Claude needs most"): `antwort` und
  `search_tools` als Pflicht, dazu die drei meistgenutzten laut Werkzeug-Spur
  der gespeicherten Gespräche (Stand 14.10.: von 75 Antworten nutzten
  `web_search` 13, `fetch_url` 6, `read_calendar` 5, jedes andere ≤ 3).
  Alles andere auf gross hat `laden = "bedarf"` — auch Kalender-Schreiben,
  Notizen/Gedächtnis, `search_chats`, `ask_choice`, `load_skill`.
- **`search_tools(query)`** (Register, ganz hinten, nur gross, ohne Gate,
  nur mit Schalter) sucht per BM25 und schaltet frei: jeder Treffer bringt
  seine **ganze Gruppe** (`werkzeug_gruppen.GRUPPEN`: browser, dateien,
  sandbox, ablage, pdf, word, tabellen, post, messreihen, skills (mit
  load_skill), gedaechtnis (Notizen), gespraeche, rueckfrage (ask_choice),
  fehler, projekte, kalender (Termine schreiben), routinen, rhythmus, gruppe,
  stil, quelle). Findet die Suche einen Skill, schaltet sie load_skill mit frei.
  Standard 5 Treffer, Mitläufer unter einem Drittel der besten Punktzahl
  fallen weg, höchstens 16 Werkzeuge je Suche. Passende **Skills** nennt sie
  mit (laden mit load_skill).
- **Anthropic** (`core/cloud.py`): dieselbe Werkzeug-Liste wie immer, die
  Bedarf-Werkzeuge mit `defer_loading: true` — der Cache-Präfix bleibt
  gleich. Das Ergebnis von search_tools geht als **reine Liste von
  `tool_reference`-Blöcken** zurück; gefundene Skills als eigener Text-Block
  hinter den Ergebnissen.
- **OpenAI-kompatibel** (`core/cloud_openai.py`): Anfang = Kern + was das
  Gespräch vorab braucht (`werkzeug_suche.vorab`, beim qwen-Profil dessen
  Schlagworte) + früher Freigeschaltetes. Gefundene Schemas hängt der
  Adapter ab der nächsten Runde hinten an — die Liste wächst nur.
- **Ohne Suche gerufen** (das Modell kennt den Namen aus dem Verlauf): läuft
  trotzdem, das Erlaubnis-Gate steht wie immer davor.
- **Über Züge hinweg:** das werkzeug-Ereignis trägt `freigeschaltet`
  (`{anfrage, namen}`), `ui/routen/ki.py` merkt es in der Werkzeug-Spur der
  Antwort. `anhang.verlauf_einsetzen` gibt es als `suche` an die Nachricht;
  der Anthropic-Weg setzt davor das Paar **Suchaufruf + Ergebnis** wieder
  ein — byte-gleich in jedem Zug (die id ist ein Hash aus Inhalt und Suche),
  sonst bräche der Cache ab dort. Ein inzwischen weggefallenes Werkzeug wird
  nicht referenziert.
- **Skills:** mit Schalter zeigt die Liste im Kopf je Skill nur den ersten
  Satz (≤ 160 Zeichen, `skills.kurzzeile`), `load_skill` liefert die volle
  Beschreibung vorn mit („Wann er passt: …"). Die Skills selbst ändert das
  nicht.
- **Prüfer:** `ModellSchiene.pruefer` bekommt auch die zurückgestellten
  Namen (ein Aufruf als Text wird erkannt, egal ob schon geladen).
- **Klassifikator später:** `vorab(verlauf, index) -> namen` — im Profil
  (`qwen.vorab`, über `ModellSchiene.vorab`) oder allgemein
  (`werkzeug_gruppen.vorab`). Heute die Schlagwort-Logik des qwen-Profils.

## Dateien

| Was | Wo |
|---|---|
| Kern-Liste, Gruppen, Schlagworte, Vorauswahl (auch qwen) | `core/werkzeug_gruppen.py` |
| Index, BM25, Treffer, Freischaltung, Paare, MCP-Liste | `core/werkzeug_suche.py` |
| Felder `laden`, `gruppe`, `schalter` | `core/werkzeug_eintrag.py`; gesetzt in `werkzeug_register.laden_setzen` |
| search_tools (Eintrag) | `core/werkzeug_register.py` (`SUCHE`) |
| Ausführung (die Schleife selbst) | `werkzeug_schleife._such_werkzeug` |
| Index als MCP `tools/list` | `scripts/werkzeug_index.py` (`--suche "…"` zum Ausprobieren) |
| Probelauf gegen die echte API | `scripts/werkzeug_suche_probe.py` |
| Tests | `tests/test_werkzeug_suche.py` |

Neues Werkzeug auf gross: in `IMMER` oder eine Gruppe von `GRUPPEN`
eintragen ([werkzeuge.md](werkzeuge.md), „Ein neues Werkzeug anlegen").

## Probelauf 14.10.2026 (claude-sonnet-5)

`scripts/werkzeug_suche_probe.py`, eigenes Suchwerkzeug, zwei Werkzeuge mit
`defer_loading`, ohne Beta-Header:

- **Text + `tool_reference` gemischt im tool_result: abgelehnt** (400
  „Tool definitions/code execution functions cannot be mixed with other
  content"). Nur `tool_reference`-Blöcke gehen → deshalb Skills als eigener
  Text-Block neben dem Ergebnis (der ist erlaubt, geprüft).
- Nur `tool_reference`: angenommen, das Modell ruft das gefundene Werkzeug
  in der nächsten Runde.
- `tool_reference` auf ein **nicht** zurückgestelltes Werkzeug: angenommen.
- **cache_read** bleibt über die Runde mit dem Suchergebnis voll (5.635 in
  jeder Runde): Werkzeuge + System bleiben gecacht; die freigeschaltete
  Definition kostet einmal als normale Eingabe.
- Neuer Zug auf einem Verlauf mit Suchaufruf + Ergebnis: angenommen, das
  Modell ruft das Werkzeug ohne neue Suche — die Freischaltung hält.
- Kosten: 11 Aufrufe, laut `core/prices.py` ≈ 0,05 € (die Tabelle rechnet
  Sonnet 5 mit 3/15 $ und Cache-Schreiben 2×; nach Listenpreis eher 0,03 €).

## Offen

- **Schritt 9:** gebaut am 22.10.2026 (Abschnitt „Schritt 9: die Suche im
  Prompt" unten), greift nur mit eingeschaltetem Schalter.
- **Schritt 10:** Prüfstand A/B (Schalter aus/an, dieselben Fälle), erst
  danach Standard an. Schätzung: ≈ 1,75 € je Durchgang mit Sonnet-Richter
  ([pruefstand.md](pruefstand.md)), zwei Durchgänge ≈ 3,50 €; mit
  Haiku-Richter ≈ 2,50 €. Die Suche kostet je Fund eine Runde mehr, spart
  dafür ~30.000 Zeichen gelesenes Schema je Runde.

## Schritt 9: die Suche im Prompt (seit 2026-10-22)

Alles nur mit Schalter an und nur auf einer Schiene mit
`MERKMALE["werkzeug_suche"]` (gross, also auch qwen über das Profil);
Entscheidung in `cloud._suche_im_prompt`. Aus bleibt jeder Text byte-gleich
(Schnappschüsse `tests/test_prompt_nutzer.py`, `tests/test_werkzeug_schnappschuss.py`;
`tests/test_werkzeug_texte.py`).

- **Absatz „## Werkzeuge laden"** (`profil.gross.SUCHE`, ~430 Zeichen),
  direkt hinter den Meta-Regeln (`cloud._static_system`): welche fünf
  geladen sind (aus `werkzeug_gruppen.IMMER`), dass jedes andere Werkzeug
  über search_tools kommt, auch die, die der Prompt beim Namen nennt, und
  eine Zeile Kategorien. Damit sind die Meta-Regeln 1, 3, 4, 6, 7 abgedeckt,
  ohne ihren Text zu ändern.
- **Gedächtnis-Kopf:** eine Zeile mehr unter den Regeln (`gedaechtnis._REGELN_SUCHE`).
- **Jetzt-Block:** „ruf read_time (über search_tools)" (`ki_prompt._now_prompt(suche=True)`).
- **Projekt-Block:** „read_project_file(name) (über search_tools)".
- **Skill-Liste:** war schon da (`skills._KOPF_KURZ`).
- **Beschreibungen der Kern-Werkzeuge:** Feld `mit_suche` hängt einen Satz an
  read_calendar (read_calendar_warnings), web_search (search_memory) und
  fetch_url (browser_open). read_calendar nennt ask_choice nicht mehr; die
  Absage-Nachfrage steht im Alarm-Block.

Mit Schalter an wächst der feste Kopf um ~440 Zeichen (Testumgebung: 8.832 →
9.275; mit Schalter aus 12.486, unverändert).

### Die Stellen vom 14.10.2026 (Ausgangsliste)

Stand 14.10.2026, erledigt am 22.10.2026 wie oben:

| Stelle | nennt |
|---|---|
| `core/profil/gross.py`, Meta-Regeln 1, 3, 4, 6, 7 (`_CAPABILITIES_VORLAGE`) | read_note, search_memory, write_note, rewrite_note, load_skill, propose_skill, search_chats |
| `core/gedaechtnis.py`, Regeln im Gedächtnis-Kopf (`_REGELN`) | read_note, write_note, archive_note |
| `core/ki_prompt.py`, Jetzt-Block | read_time |
| `core/projekte.py`, Projekt-Block | read_project_file |
| `core/skills.py`, `_KOPF` der Skill-Liste (nur mit Schalter aus; mit Schalter gilt `_KOPF_KURZ`, der search_tools nennt) | load_skill |
| Beschreibung von `read_calendar` (Register) | read_calendar_warnings, ask_choice |
