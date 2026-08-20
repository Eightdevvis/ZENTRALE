# Der Takt — wann ZENTRALE von sich aus spricht

`core/takt.py` (Logik) · `ui/app.py` (Treiber) · `tui/zentrale_tui.py` (Zustellung)

## Warum

Bis zum 18.08.2026 erinnerte ZENTRALE nur dann an einen Termin, wenn Sasha
ohnehin gerade schrieb: der Kalender stand im Prompt, die Uhr daneben, und das
Modell rechnete jeden Turn nach, wie lange es noch hin ist. Genau die falsche
Richtung — es mahnte, wenn er da war, und schwieg, wenn er weg war. Sein Befund:

> *„nicht nur nervt sie mich alle paar minuten dass gleich der termin ist obwohl
> ich es das erste mal schon gesehen habe"*

Sein Schnitt: **die Uhr raus aus dem Prompt, das Erinnern in den Code.** Eine
Prompt-Regel ist eine Bitte; ein Anstoß aus dem Code ist eine Tatsache. Die
Uhrzeit holt sie sich seitdem mit `read_time`, wenn sie sie braucht
(→ `memory/werkzeuge/kalender_system.md`).

## Die drei Teile

**1. Die Entscheidung — `core/takt.py`.** Rein, testbar, ohne Netz und ohne
Modell. `faellig(jetzt)` liefert höchstens **einen** Anstoß oder `None`. Kein
Modell-Aufruf hier: ein Fehler in der Anstoß-Logik soll im Test auffallen und
nicht erst, wenn er Geld gekostet hat.

**2. Der Treiber — `_takt_starten()` in `ui/app.py`.** Ein Daemon-Thread,
Tick alle 60 s: fragen → **erst merken, dann sprechen** → einmal durchs normale
KI-Backend (also mit Gedächtnis, Kalender-Imprint und Werkzeugen) → Antwort per
`state.push_chat_message("assistant", …)` in den Verlauf. Die Reihenfolge
merken-vor-sprechen ist Absicht: ein Absturz mitten im Modell-Aufruf würde
sonst denselben Anstoß beim nächsten Tick wiederholen. Abschaltbar mit
`ZENTRALE_TAKT=0`.

**2a. In welche Lage hinein.** Seit dem 20.08.2026 trägt der Auftrag die
**Lage** mit (`core/anwesenheit.py`): ob Sasha da ist und ob ZENTRALE vor ihm
steht. Sie hat also seine Aufmerksamkeit sicher — oder muss sie erst holen, und
dann ist die Nachricht ein Satz, kein Absatz. Siehe
`memory/system/anwesenheit_und_ring.md`.

**2b. Die Meldung nach draussen.** Seit dem 19.08.2026 geht jeder Anstoß
zusätzlich als **Desktop-Benachrichtigung** raus (`core/melden.py`) — aber nur,
wenn ZENTRALE nicht ohnehin sichtbar vor Sasha steht. Ohne das endet ihre
Initiative an der Fensterkante. Details in `memory/betrieb/systemeinheit.md`.

**3. Die Zustellung — `ai_poll()` in der TUI.** Der Verlauf wurde früher
**einmal** beim Öffnen des KI-Kastens geholt; eine unaufgeforderte Nachricht
wäre also versandet. Jetzt sieht ein Thread alle 20 s nach und übernimmt den
Backend-Verlauf, solange kein Stream läuft. Steht der Kasten zu und hatte die
KI das letzte Wort, erscheint ein **●** vorne im Titel; das Öffnen löscht es.

## Was den Auftrag ausmacht

`faellig()` gibt einen **Auftrag in Worten** zurück, keine fertige Nachricht:

> *„Erinnere Sasha kurz daran, dass „Geigenstunde" um 17:45 anfängt, also in
> etwa 60 Minuten. Ein Satz, beiläufig, kein Countdown und keine Nachfrage."*

Was gesagt wird, formuliert das Modell — es kennt den Verlauf und weiß, ob
Sasha gerade mitten in etwas steckt. Der Code entscheidet nur das WANN.

Der Auftrag geht als letzte User-Nachricht mit, wird aber **nicht** in den
Verlauf geschrieben. Er ist eine Regieanweisung, keine Äußerung von Sasha —
sonst läse er morgen Sätze, die er nie geschrieben hat, und das Modell läse sie
als seine.

## Die Schweigeregeln (hart, nicht dem Modell überlassen)

Die Gefahr dieser Schicht ist nicht, dass ein Anstoß ausbleibt — das merkt man
und ärgert sich kurz. **Ein Assistent, der dreimal mahnt, wird abgeschaltet.**
Deshalb:

| Regel | Wert | Warum |
|---|---|---|
| Schwellen | 60 und 30 min vorher | Sashas Vorgabe: „ne stunde, ne halbe" |
| Nachlauf | 5 min | Ein Rechner schläft mal kurz; ohne Fenster fällt der Anstoß still aus. Knapp, sonst käme die 60er-Mahnung bei 40 min und damit direkt vor der 30er |
| Nachtruhe | 22:00–06:59 | — |
| Mindestabstand | 20 min | gilt auch zwischen *verschiedenen* Anstößen |
| Jeder Anstoß genau einmal | `data/takt/YYYY-MM-DD.json` | auf der Platte, damit ein Backend-Neustart nicht alles erneut mahnt |

Ganztags-Einträge erzeugen keinen Anstoß (kein Abstand berechenbar), und ein
Termin von **morgen** ist kein Countdown-Fall — was der Abend vorbereiten soll,
gehört ins Schemen.

Alte Tageszustände räumt `aufraeumen()` beim Start weg (7 Tage bleiben).

## Was noch fehlt

- **Anwesenheitspings** (Morgenritual bei der ersten Interaktion des Tages,
  Check-in nach längerer Abwesenheit) — die zweite Auslöser-Klasse aus Sashas
  Vorgabe. Das Signal dafür steht seit dem 20.08.2026 (`anwesenheit.da()`),
  die Auslöser noch nicht.
- **Das Schemen** baut später auf dem auf, was der Takt erzeugt.
- **Kosten im Blick behalten:** jeder Anstoß ist ein Modell-Aufruf.
  `data/ai_usage.json` nach einem Tag mit Takt gegen einen Tag ohne halten.
