# Der Takt — wann ZENTRALE von sich aus spricht

**Stand 2026-10-19:** `core/takt.py` entscheidet rein aus dem Kalender,
**wann** ein Anstoß fällig ist (60 und 30 min vor einem Termin, 5 min
Nachlauf, Nachtruhe 22–07, 20 min Mindestabstand, jeder Anstoß genau einmal
in `data/takt/YYYY-MM-DD.json`); ein 60-s-Thread in `core/takt_treiber.py` merkt ihn,
lässt das Modell den Satz formulieren und legt ihn ins Gespräch
„Erinnerungen" (seit 2026-10-07, [../ki/gespraeche.md](../ki/gespraeche.md));
die TUI holt die Gesprächsliste alle 20 s und zeigt ein ● am Kasten. Für
Sasha heißt das Ganze „Erinnerungen" — das Wort „Takt" steht in nichts
Sichtbarem (Log-Zeilen: `ERINNERUNG`). Die Lage
(`anwesenheit.py`) geht mit, die Meldung geht zusätzlich als
Desktop-Benachrichtigung raus (`melden.py`) — aber nur, wenn sie beim
Melden noch frisch ist (Abschnitt 2c), und der KI-Aufruf hat eine harte
Zeitgrenze von 90 s. `ZENTRALE_TAKT=0` schaltet ab.
Offen: Anwesenheitspings (Morgenritual, Check-in), das Schemen, Kostenblick.

`core/takt.py` (Logik) · `core/takt_treiber.py` (Treiber) · `tui/ansichten/chat.py` (Zustellung: `Chat.ai_poll`)

## Warum

Vor dem Takt (bis 18.08.2026) erinnerte ZENTRALE nur dann an einen Termin, wenn Sasha
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

**2. Der Treiber — `core/takt_treiber.py` (`starten()`, `sprechen()`).** Bis 2026-10-06 in `ui/app.py`; gestartet wird er weiter aus `start_ui()`. Ein Daemon-Thread,
Tick alle 60 s: fragen → **erst merken, dann sprechen** → einmal durchs normale
KI-Backend (also mit Gedächtnis, Kalender-Imprint und Werkzeugen) → Auftrag
(versteckt) und Antwort ins Gespräch `erinnerungen` (`core/gespraeche.py`);
als Verlauf sieht das Modell dabei dieses Gespräch, nicht das, an dem Sasha
gerade sitzt. Die Reihenfolge
merken-vor-sprechen ist Absicht: ein Absturz mitten im Modell-Aufruf würde
sonst denselben Anstoß beim nächsten Tick wiederholen. Abschaltbar mit
`ZENTRALE_TAKT=0`.

**2a. In welche Lage hinein.** Der Auftrag trägt die **Lage** mit (`core/anwesenheit.py`): ob Sasha da ist und ob ZENTRALE vor ihm
steht. Sie hat also seine Aufmerksamkeit sicher — oder muss sie erst holen, und
dann ist die Nachricht ein Satz, kein Absatz. Siehe
`memory/system/anwesenheit_und_ring.md`.

**2b. Die Meldung nach draussen.** Jeder Anstoß geht zusätzlich als **Desktop-Benachrichtigung** raus (`core/melden.py`) — aber nur,
wenn ZENTRALE nicht ohnehin sichtbar vor Sasha steht. Ohne das endet ihre
Initiative an der Fensterkante. Details in `memory/betrieb/systemeinheit.md`.

**3. Die Zustellung — `ai_poll()` in der TUI** (`tui/ansichten/chat_gespraeche.py`).
Ein Thread holt alle 20 s die Gesprächsliste. Liegt in einem Gespräch, das
gerade nicht vor Sasha liegt, eine ungelesene Antwort (meist „Erinnerungen"),
erscheint ein **●** vorne im Kasten-Titel und auf der Startseite; Öffnen
dieses Gesprächs markiert es gelesen.

**2c. Frische und Zeitgrenze (seit 2026-10-19).** Anlass: Erinnerung
15:30 für einen Termin um 16:00 ausgelöst, 3 s später schlief der Laptop,
der Cloud-Aufruf überlebte den Schlaf und kam um 17:59 zurück — notify-send
meldete einen Termin, der seit einer Stunde vorbei war.

- `faellig()` gibt `ausgeloest` und `beginn` (Wanduhr) sowie `label`/`time`
  mit. Direkt vor dem Melden fragt `sprechen()` `takt.veraltet(anstoss)`:
  hat der Termin schon begonnen oder ist die Auslösung älter als
  `FRISCH_GRENZE` (= `NACHLAUF`, 5 min), wird **nicht** gemeldet. Die
  Antwort landet trotzdem im Gespräch „Erinnerungen", mit der Warnung
  „Veraltet, nicht gemeldet: <Grund>". Wanduhr (`datetime.now`), nicht
  `monotonic` — die monotone Uhr steht im Schlaf still.
- Der KI-Zug läuft in einem eigenen Thread; `takt_treiber.KI_GRENZE` (90 s,
  gegen die Wanduhr in 1-s-Scheiben gemessen, damit nach einem Schlaf die
  Frist sofort vorbei ist). Bei Ablauf: Abbruch-Signal setzen, späte
  Tokens verfallen, statt der KI-Antwort geht eine feste Kurzmeldung
  („„X“ fängt um HH:MM an.") raus — nur, wenn noch frisch; im Verlauf mit
  der Warnung „Kurzmeldung ohne KI".

## Was den Auftrag ausmacht

`faellig()` gibt einen **Auftrag in Worten** zurück, keine fertige Nachricht:

> *„Erinnere Sasha kurz daran, dass „Geigenstunde" um 17:45 anfängt, also in
> etwa 60 Minuten. Ein Satz, beiläufig, kein Countdown und keine Nachfrage."*

Was gesagt wird, formuliert das Modell — es kennt den Verlauf und weiß, ob
Sasha gerade mitten in etwas steckt. Der Code entscheidet nur das WANN.

Der Auftrag geht als letzte User-Nachricht mit. Er ist eine Regieanweisung,
keine Äußerung von Sasha. Bis 2026-10-07 wurde er deshalb gar nicht
gespeichert; seitdem steht er im Gespräch „Erinnerungen" **versteckt**: die
TUI zeigt ihn nicht (Sasha liest keine Sätze, die er nie geschrieben hat), und
die KI sieht ihn später mit dem Vorsatz „[Automatischer Auftrag von ZENTRALE,
nicht von Sasha geschrieben]" — so weiß sie, worauf ihre Erinnerung
antwortete, ohne ihn für Sashas Worte zu halten.

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
| Frische beim Melden | 5 min (`FRISCH_GRENZE`), Termin nicht begonnen | Ein Schlaf zwischen Auslösen und Melden macht die Erinnerung wertlos |
| KI-Zeitgrenze | 90 s (`KI_GRENZE`) | Danach Kurzmeldung ohne KI |
| Jeder Anstoß genau einmal | `data/takt/YYYY-MM-DD.json` | auf der Platte, damit ein Backend-Neustart nicht alles erneut mahnt |

Ganztags-Einträge erzeugen keinen Anstoß (kein Abstand berechenbar), und ein
Termin von **morgen** ist kein Countdown-Fall — was der Abend vorbereiten soll,
gehört ins Schemen.

Alte Tageszustände räumt `aufraeumen()` beim Start weg (7 Tage bleiben).

## Was noch fehlt

- **Anwesenheitspings** (Morgenritual bei der ersten Interaktion des Tages,
  Check-in nach längerer Abwesenheit) — die zweite Auslöser-Klasse aus Sashas
  Vorgabe. Das Signal dafür steht (`anwesenheit.da()`), die Auslöser noch
  nicht.
- **Das Schemen** baut später auf dem auf, was der Takt erzeugt.
- **Kosten im Blick behalten:** jeder Anstoß ist ein Modell-Aufruf.
  `data/ai_usage.json` nach einem Tag mit Takt gegen einen Tag ohne halten.

## Historie

- **18.08.2026** — Takt gebaut: Uhr raus aus dem Prompt, Erinnern in den
  Code (Sashas Befund oben).
- **19.08.2026** — Desktop-Benachrichtigung (`melden.py`), Kern als Dienst.
- **20.08.2026** — Lage (`anwesenheit.py`) geht mit dem Auftrag mit.
- **19.10.2026** — Frische-Prüfung vor dem Melden und 90-s-Zeitgrenze für
  den KI-Aufruf (Erinnerung nach Laptop-Schlaf zwei Stunden zu spät).
