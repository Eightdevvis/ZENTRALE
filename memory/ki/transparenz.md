# Transparenz — Devtools, Tool-Calls im Chat, Ablauf-Protokoll

**Stand 2026-10-11:** Drei Fenster in das, was die KI tut: das
Devtools-Terminal (`scripts/ai_devtools.py`, voller Request live), die
Werkzeug-Zeilen und das Denken im Chat (SSE `werkzeug`, alle drei Wege) und das
Ablauf-Protokoll „trace ›" unter jeder Antwort (gespeichert, nur Cloud/gross).
Keines davon ändert, was ans Modell geht. Netz-Verkehr:
[internet_netz.md](internet_netz.md).

**Warum:** Sasha nach einem Turn, den niemand nachvollziehen konnte: „einfach
alle transparent und sichtbar, so wie man es bei dir claude sieht". Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Devtools-Terminal — `scripts/ai_devtools.py` (seit 08/2026)

Das Dashboard-Log sagt, WAS gekostet hat und DASS ein Tool lief. Was
tatsächlich rausgeht — der vollständige System-Prompt, der Graph-Kontext, das
Tool-Schema, die Reihenfolge der Blöcke, wo die Cache-Breakpoints sitzen —
sah man nirgends. Seit es zwei Prompt-Schienen gibt, ist genau das die Frage,
die man ständig hat.

In einem eigenen Terminal, aus dem Projekt-Root:

```
scripts/ai_devtools.py                    # localhost:5000
scripts/ai_devtools.py --url http://<pc>:5000
scripts/ai_devtools.py --voll             # nichts kürzen
```

Ausgabe pro Turn:

```
→ REQUEST claude-sonnet-5 | Schiene: gross
System-Prompt (1 Block, 2959 Zeichen ≈ 739 Token)
  [0] ◄ CACHE-BREAKPOINT
Messages (1)
  user:
    ◄ CACHE-BREAKPOINT
    was steht heute an?
    ## Aktiviertes Wissen …          ← das Wechselnde, ungecacht dahinter
Tools (20, 5217 Zeichen ≈ 1304 Token)  [339a3b98f42f]
  read_calendar
      Liest Kalender-Einträge: TERMINE und Routinen, also Verabredetes. …
      *zeitraum (string) heute | diese_woche | …
  …
← ANTWORT tool_use in=677 out=54 cache_read=5458
⚙ TOOL read_calendar
⊕ GRAPH (cloud) knoten: Falter, blau, Klapprad
```

## Tool-Calls und Denken stehen IM CHAT (seit 20.08.2026)

Sasha nach einem Turn, den niemand nachvollziehen konnte:

> *„machen wir im normalen chat einfach die tool calls usw details was sie macht
> wie tool call, thinking, usw einfach alle transparent und sichtbar, so wie man
> es bei dir claude sieht! … weil keine ahnung was sie hier fabriziert hat."*

Der Anlass: sie schrieb dieselbe Idee **zweimal** weg — erst als sauberen
Katalog-Eintrag, dann als Prosa in dieselbe Katalogdatei — und sagte beide Male
nur „steht drin" bzw. „jetzt steht's wirklich drin". Von außen sah das aus wie
eine Lüge beim ersten Mal. Ein sichtbares `write_note(name=ideen, text=…)` hätte
die Frage in einer Zeile beantwortet.

- **Emittiert** wird in `werkzeug_schleife.run_tool` — der einzigen Stelle,
  durch die **alle drei** Wege gehen (lokal erst seit 10/2026). Drei Phasen:
  `start` (Name + Argumente), `fertig` (Ergebnis), `fehler`. Mehrfach
  gepflegt hieße, dass die Anzeige auf einer Schiene irgendwann fehlt.
- **Durchgereicht** als eigenes SSE-Event `werkzeug` (`ui/routen/ki.py`), kein
  Antworttext — es landet also nicht im gespeicherten Verlauf.
- **Gezeigt** in der TUI als eigene Zeilen im Chat: `⚙ write_note(name=ideen,
  …)` und darunter `↳ Notiert in kataloge/ideen.` Zurückgenommen in der Farbe,
  ein Werkzeug-**Fehler** dagegen in Warnfarbe — das ist der Fall, in dem sie
  hinterher behauptet, es habe geklappt.
- **Denken** wird gesammelt und in den Verlauf gelegt, sobald etwas anderes
  passiert (ein Werkzeug, Text, eine Rückfrage). Erst am Turn-Ende anzuhängen
  hieße, den Gedankengang hinter die Taten zu stellen, die aus ihm folgten.

Die `werkzeug`-Ereignisse sind ein reiner **Anzeige-Kanal**: die Tests des
Tool-Protokolls (`test_cloud_loop.py`, `test_cloud_openai.py`) filtern sie in
ihrem `_lauf()` heraus, geprüft werden sie in `test_transparenz.py`.

**Werkzeuge stehen mit Beschreibung und Parametern da — seit 18.08.2026.**
Vorher schickte `kidebug.request()` nur die NAMEN; damit log das Terminal seinen
eigenen Anspruch, alles zu zeigen, was rausgeht. Ausgerechnet die
Beschreibungen sind das, woraus die KI ableitet, wann sie welches Werkzeug
nimmt — wer verstehen will, warum sie danebengreift, muss genau die lesen. Sie
sind außerdem ein spürbarer Teil des gecachten Präfix.

Ausgeschrieben werden sie nur beim **ersten** Request und danach wieder, wenn
sich der Satz ändert; sonst steht `[Schemata wie oben, <fingerprint>]`. Der
Satz ist statisch, und ihn 500-mal in einen Puffer von 500 Events zu legen
hieße, alles andere daraus zu verdrängen. Beim Verbinden vergisst der Bus, was
er schon gezeigt hat (`subscribe()` setzt `_TOOLS_FP` zurück) — sonst hätte
ausgerechnet eine frisch geöffnete Sitzung die Schemata nie gesehen.

Events: `ai.req` (voller Request), `ai.out` (Roh-Antwort inkl. Denk-Blöcken und
dem Vorgeplänkel vor einem Tool-Call, das der Chat sonst schluckt), `ai.tool`,
`ai.graph` (was der Extraktor geschrieben hat).

- **Bus:** `core/kidebug.py`, Ring-Puffer + Subscriber-Queues, `emit()` schluckt
  jeden Fehler — ein Debug-Kanal, der ein Gespräch abreißen lässt, ist
  schlimmer als keiner.
- **Normalerweise AUS** (`ZENTRALE_AI_DEBUG=0`). Das Terminal schaltet ihn beim
  Verbinden selbst an; den vollen Prompt im Speicher zu halten lohnt nur, wenn
  jemand zuschaut.
- **Endpunkt:** `GET /api/ai/debug/stream` (SSE).
- **Eigener Bus, nicht der des Tutors.** Der Tutor hat seinen eigenen
  (`tutor/debug.py`, seit 2026-10-09 im Repo `language-tutor`); der Kern
  importiert nichts von ihm. Seit dem Auszug hat der Tutor auch wieder eine
  eigene Anbieter-Liste (`tutor/modell/anbieter_liste.py`); in ZENTRALE ist
  es nur `core/providers.py`.

⚠ Hier geht der komplette Prompt raus, inklusive Graph-Kontext — also Sashas
Zustände und Erlebnisse. So privat wie der Graph selbst.

## Ablauf-Protokoll — „trace ›" unter jeder Antwort (seit 2026-10-09)

Sasha: wie bei „Used …" nicht nur sehen, welches Werkzeug lief, sondern was
es zurückgab und wie die Antwort darauf weiterging — der ganze Zug von seiner
Nachricht bis zur fertigen Antwort, in Reihenfolge, ohne Auslassungen. Die
Devtools (oben) zeigen das live; das Protokoll bleibt mit der Antwort
gespeichert und ist in der TUI nachzulesen.

- **Nur mitschreiben** (`core/zug_ablauf.py`, Schicht 1, contextvar wie
  `core/zug.py`). Nichts davon ändert, was ans Modell geht — der Prompt-Cache
  bleibt, wie er ist (`tests/test_zug_ablauf.py` vergleicht den Request mit
  und ohne Protokoll byte für byte).
- **Nur Cloud, Schiene gross.** `/api/chat` öffnet das Protokoll, wenn die
  Cloud denkt; scharf wird es erst, wenn der Weg `system()` meldet
  (`cloud.ablauf_melden`, beide Cloud-Wege, nur gross). Lokal/klein bleibt
  alles, wie es gemessen ist — dort gibt es kein `ablauf`.
- **Wer meldet was:** `cloud.ablauf_melden` → `system` (nur Fingerabdruck
  sha256[:16] + Länge, der feste Kopf ist jeden Zug derselbe) und `kontext`
  (der Umschlag `<kontext_automatisch>` voll: Jetzt, Alarme, offene Zusagen;
  dazu Titel/Größe der Anhänge der neuesten Nachricht). `werkzeug_schleife.laufen`
  → `text` (Vorgeplänkel vor/zwischen Werkzeugen, das der Chat nicht zeigt),
  `werkzeug` (Name, Argumente, Ergebnis **wie an die Schleife zurück**, also
  mit Kopfzeile `[ergebnis: …]`, Status, Dauer), `pruefung` (Befunde, Hinweis
  an die KI, die erste verworfene Antwort — danach folgt die zweite),
  `fehler`/`gestoppt`. `_ask_permission`/`_ask_buttons` → `frage` (Frage,
  Knöpfe, Sashas Antwort; „schon erlaubt (…)" bei Geltungsbereich).
  Die Buchungen (`_log_usage` & Co.) zählen in `kosten` mit. Die Route hängt
  zum Schluss `antwort` (wie gespeichert) und `kosten` an.
- **Denken** bleibt, wie es war (eigenes Feld `denken`), nicht im Ablauf.
- **Obergrenze** 50.000 Zeichen je Eintrag (`EINTRAG_MAX`): das längste Feld
  wird hinten gekürzt, mit Vermerk und `gekuerzt: <Zeichen>`. Sonst wird
  nichts gekürzt (anders als `werkzeuge[].ergebnis`, 8.000).
- **Gespeichert** als Feld `ablauf` der Antwort (`core/gespraeche.py`).
  `/api/chat/history` und `GET /api/gespraeche/<id>` liefern nur
  `ablauf_n`; den Inhalt `GET /api/gespraeche/<id>/ablauf/<nachricht>`
  (`letzte` = die letzte Antwort mit Protokoll). SSE: nach dem Speichern
  `{antwort: id, ablauf: n}`.
- **Export:** `/trace` im Chat → `POST …/ablauf/letzte/ablage` legt den Ablauf
  als Textdatei in die Ablage (Herkunft `ablauf`, bis 2.000.000 Zeichen,
  `zug_ablauf.als_text`).
- Fehlt: ein Zug, der an einem Fehler ohne jeden Text scheitert, wird nicht
  gespeichert (wie bisher) — sein Protokoll also auch nicht.

## Historie

- **2026-08** — Devtools-Terminal; **08-18** Werkzeuge mit Beschreibung und
  Parametern; **08-20** Tool-Calls und Denken im Chat.
- **2026-10-09** — Ablauf-Protokoll.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
