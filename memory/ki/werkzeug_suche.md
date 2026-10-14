# Werkzeug-Suche — fester Kern, der Rest auf Bedarf (seit 2026-10-14)

**Stand:** gebaut (Schritte 1–8 des Bauplans), Schalter `werkzeug_suche`
**Standard aus** — am Live-Verhalten ändert sich nichts, bis der Prüfstand
gelaufen ist. Einschalten: Einstellung `werkzeug_suche = an` (oder Env
`ZENTRALE_WERKZEUG_SUCHE=an`). Weil `profil.gross.TOOLS` beim Import entsteht,
gilt ein Umschalten erst nach einem Neustart des Servers.

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

- **Schritt 9:** ein Satz im gross-Prompt zu search_tools und ein Merkmal
  in `MERKMALE` — nicht gebaut (am Prompt-Text arbeitete parallel ein
  anderer Agent). Bis dahin erklärt nur die Werkzeug-Beschreibung die Suche.
  Dazu die Stellen, die zurückgestellte Werkzeuge beim Namen nennen
  (Prompt-Text, Gedächtnis-Kopf, Beschreibungen der Kern-Werkzeuge) — sie
  stimmen weiter, das Werkzeug ist nur erst nach einer Suche da; Liste im
  Abschnitt unten.
- **Schritt 10:** Prüfstand A/B (Schalter aus/an, dieselben Fälle), erst
  danach Standard an. Schätzung: ≈ 1,75 € je Durchgang mit Sonnet-Richter
  ([pruefstand.md](pruefstand.md)), zwei Durchgänge ≈ 3,50 €; mit
  Haiku-Richter ≈ 2,50 €. Die Suche kostet je Fund eine Runde mehr, spart
  dafür ~30.000 Zeichen gelesenes Schema je Runde.
