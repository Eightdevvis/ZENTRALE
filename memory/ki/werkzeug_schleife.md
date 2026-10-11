# Eine Werkzeug-Schleife — `core/werkzeug_schleife.py`

**Stand 2026-10-11:** Eine Schleife (`laufen`) für alle drei Wege (lokal,
Anthropic, OpenAI-kompatibel) besitzt Runden, Gate, terminale Werkzeuge,
Antwort, Fehler und Stoppen; drei Adapter kennen nur ihren Dialekt. Was ein
Tool-Call bedeutet, steht einmal in `run_tool()`. Fehler sind keine Antwort.
Rundengrenze am Modell (`ai_backends.runden_grenze`, Standard 100).

**Warum:** Bis Oktober 2026 stand die Schleife dreimal da und lief auseinander.
Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Eine Werkzeug-Schleife – `core/werkzeug_schleife.py` (seit 10/2026)

Bis Oktober 2026 stand die Tool-Schleife **dreimal** da (lokal, Anthropic,
OpenAI). Die lokale Kopie war auseinandergelaufen: keine `werkzeug`-Events,
ein krachendes Tool riss den Zug ab, eigener Ablehnungstext. Jetzt gibt es
eine Schleife (`laufen`), die Runden, Gate, terminale Tools (`antwort`,
`read_news`, `ask_choice`), Antwort und Fehler besitzt, und **drei Adapter**,
die nur ihren Dialekt kennen:

| Adapter | Datei | Eigenheit |
|---|---|---|
| `_OllamaAdapter` | `core/ai.py` | think aus nach dem ersten Tool (qwen-Template-Bug) |
| `_AnthropicAdapter` | `core/cloud.py` | `tool_result`-Blöcke in EINER user-Message, wandernder Cache-Breakpoint |
| `_OpenAIAdapter` | `core/cloud_openai.py` | Tool-Calls stückweise aus dem Stream, `role: "tool"` |

Jeder Adapter hat `runde()` (ein Modell-Aufruf → `Runde(text, calls)`),
`assistent_anhaengen()` und `ergebnisse_anhaengen()`. Den Prompt baut weiter
jeder Weg selbst. Was ein Tool-Call **bedeutet**, steht genau einmal, in
`werkzeug_schleife.run_tool()`.

**Sonderwege nach Register (seit 2026-10-07, Phase 3).** `run_tool` nennt
keinen Werkzeug-Namen mehr: `in_der_schleife` → der Weg aus
`werkzeug_schleife.SELBST` (`antwort` = Text ist die Antwort, `ask_choice` =
Knopf-Dialog); `terminal` mit Ausführer → `_terminal_ausgeben` (heute nur
`read_news`: `cinema`-Event, Kopf „Sendung (Stand …)" weg, direkt als
Antwort, nicht gemerkt). Im Tutor greift beides nicht.
`tests/test_werkzeug_schleife_register.py` hält Register und `SELBST`
deckungsgleich und beweist gleiches Verhalten (lief auch gegen den alten
Code grün).

**Fehler sind keine Antwort.** API-Fehler, Cloud-Ablehnung (`refusal`) und
die Rundengrenze kommen als `{"fehler": …}`. `ui/routen/ki.py` reicht das als SSE
`fehler` an die TUI und schreibt es NICHT als ihren Text ins Gespräch.
Vorher stand `[Cloud-Fehler: …]` als KI-Antwort im Verlauf, und der Takt
konnte es sogar als „Initiative“ melden. Seit 2026-10-09 wird der
abgebrochene Zug trotzdem gespeichert — als Antwort mit Feld `fehler`, den
Werkzeugen und dem Ablauf, Text meist leer (bis dahin war er ganz weg, und
die KI wusste im nächsten Zug nichts davon). `gespraeche.fehler_hinweis`
gibt ihn ihr im Verlauf als „[System, nicht deine Worte: Dein letzter Zug
brach ab — <Meldung>. Bis dahin gelaufen: …]" (höchstens 12 Schritte, Args
gekürzt); der feste Kopf bleibt (Prompt-Cache). Gestoppt ohne Text zählt
genauso („von Sasha gestoppt"). Die TUI zeigt „✗ abgebrochen: …" mit
„retry" daran (SSE `{antwort, abbruch}`).

**Eine Regel für alle (Sasha, 05.10.2026):** Die Rundengrenze hängt am
Modell, nicht am Weg (`ai_backends.runden_grenze`, Standard 100 (bis 09.10.: 8), pro Modell in
`runden_grenzen` der Config kleiner). Der Ablehnungstext verlangt überall die
Richtigstellung, falls sie im selben Zug schon notiert hat, es sei passiert —
vorher bekam nur der lokale Weg diesen Satz.

**Stoppen (seit 2026-10-07).** `laufen(…, abbruch=)` nimmt ein
`threading.Event` und prüft es vor jeder Runde und vor jedem Werkzeug; die
Adapter prüfen es bei jedem Stück ihres Stroms, schließen ihn, buchen, was
der Anbieter bis dahin gemeldet hat, und werfen `Gestoppt(text)`. Heraus
kommt der halbe Text (roh, nicht gemerkt) und `{"gestoppt": True}`. Das
Event legt `/api/chat` pro Zug an (`state.chat_zug_beginnen`),
`/api/chat/stop` setzt es. Takt und Tutor übergeben keins und sind nicht
stoppbar. Ausführlich: [claude_web_plan.md](claude_web_plan.md) Abschnitt 7.

Der Tutor ist seit 2026-10-09 ein eigenes Repo (`language-tutor`) mit
eigenen Schleifen; `kern.fahrzeug()`/`kern.fahren()` sind mit ihm aus
`core/kern.py` raus ([../tutor/INDEX.md](../tutor/INDEX.md)).

## Aus dem alten Ollama-Weg

**Sicherheitsnetz:** früher ein hartes `max_rounds = 5` in `chat_stream`
gegen Endlosschleifen bei kaputten Tool-Calls. `max_rounds` gibt es im Code
nicht mehr (geprüft 2026-10-11); heute ist es die Rundengrenze oben
(`ai_backends.runden_grenze`, für `qwen3.5:9b` per `runden_grenzen` 5).

**Streaming-Detail:** Tool-Calls kommen im **letzten** Streaming-Chunk
(`done=true`) im Feld `tool_calls`. Heißt: erst auf das Ende des Streams
warten, dann Tools auflösen.

## Historie

- **2026-10** — drei Schleifen zu einer; Sonderwege nach Register (10-07);
  Stoppen (10-07); abgebrochener Zug wird gespeichert (10-09); Rundengrenze
  100 statt 8 (10-09).
- **2026-10-11** — aus `ki_system.md` ausgelagert.
