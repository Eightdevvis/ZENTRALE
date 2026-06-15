# Dashboard & Frontend

> **AKTUELLER STAND (2026-06): zwei „Kassetten" auf EINEM Backend.**
> Die gelebte Haupt-UI ist das Monolith-Dashboard (`ui/templates/monolith.html`).
> Seit 2026-06-08 gibt es zusätzlich die **Laptop-Kassette**
> (`ui/templates/laptop.html`) — „ZENTRALE in klein", KI-frei, für eine
> RAM-schwache Laptop-Maschine. Beide teilen sich Backend/State/Routen; welche
> ausgeliefert wird, entscheidet die Kassetten-Wahl (s.u.). Das alte `index.html`
> (AI-Orb, `#view-main`-Grid, `#panel-ai`/`#panel-chat`-Modi) ist **weg** - die
> entsprechenden Sektionen wurden hier gelöscht, weil veraltete Layout-Doku schon
> einmal zu falschen KI-Prompt-Texten geführt hat (Dashboard-Sicht, siehe
> `grounding_recherche.md`). Was Sasha real sieht steht unter „## Monolith-Dashboard"
> bzw. „## Laptop-Kassette".

## Kassetten (monolith | laptop | tui)

Eine Codebase, ein Backend, **mehrere Fronten** — bewusst getrennte Fronten
statt eines Modus-Schalters im Monolith (damit sie sich unabhängig entwickeln,
ohne „Zusammendatschen"):

- **`core/kassette.py`** ist die einzige Wahrheit: liest die Env-Var
  `ZENTRALE_KASSETTE` (Default `monolith`; unbekannte Werte → `monolith`).
  `name()`, `is_laptop()`, `is_tui()`, `ki_aus()`, `template()`.
  `ki_aus()` ist `True` für **laptop und tui** (alles außer monolith).
- **`core/main.py`** fährt den KI-Auto-Bootup (Ollama-Warmup + News-Fetcher)
  **nur wenn `ki_aus()` False** ist (also nur monolith) hoch. Sonst: nichts
  davon → Ollama wird nie angesprochen.
- **`ui/app.py`** rendert `kassette.template()` auf `/` (+ `/monolith`-Alias).
  Wenn `ki_aus()`: KI-Endpoints abgeriegelt — `/api/chat`,
  `/api/permission_answer`, `/api/speak`, `/api/transcribe` → **503**;
  `/api/ai/status` → `{available:false, kassette:<name>}`; `/api/chat/history` → `[]`.
- Gestartet wird die Wahl über den Start-Befehl: `zentrale` zeigt ein
  **Kassetten-Menü** (`tui/select_kassette.py`, ↑/↓ + Enter, animierter Stern,
  Regenbogen-Ladebalken) und exec't in die gewählte Kassette; `zentrale-laptop`
  → laptop, `zentrale-tui` → tui überspringen das Menü direkt (setzen die
  Env-Var). Siehe `starten.md`.

Die drei Fronten:

| Kassette | Front | KI | Datei |
|----------|-------|----|-------|
| monolith | Browser, voll | an | `ui/templates/monolith.html` |
| laptop   | Browser, lean | aus | `ui/templates/laptop.html` |
| tui      | **Terminal (curses)** | aus | `tui/zentrale_tui.py` |

### Laptop-Kassette (`ui/templates/laptop.html`)

Eigenständige, schlanke Datei — **nicht** vom Monolith abgeleitet: kein
`engine.js`/`viz.js`/`ascii.js`, kein Frametick, kein Flicker. Eigener
Mini-Adapter (inline `<script>`), der **nur** `/api/state` (1 s) und
`/api/telemetry` (2 s) pollt — kein `/api/ai/status`, kein
`/api/chat/history`, damit auf der RAM-schwachen Maschine nichts ins Leere
läuft. Optik: ZENTRALE-Look, AUTO-Theme (hell 05–21 / sonst dunkel),
**statische** Scanlines (kein Keyframe), sonst still.

Layout (3 Spalten, lean):

```
+------------+--------------------------+------------------+
| telemetrie |                          | lifestyle        |
| (LAP·CPU/  |   MITTE (leeres Skelett, | (tracker, noch   |
|  RAM/TEMP) |    Inhalt folgt          |  nicht an        |
| stdout     |    gemeinsam)            |  /api/data)      |
| (#term)    |                          +------------------+
|            |                          | outbound         |
|            |                          | (#term-net)      |
+------------+--------------------------+------------------+
```

> **Sensoren-Panel entfernt (2026-06):** in ALLEN drei Kassetten (monolith,
> laptop, tui) ist die Sensoren-Anzeige raus — kein echter Sensor angeschlossen,
> der Platzhalter soll weg. Das **Backend bleibt verkabelt** (Event-Loop,
> `/api/sensor/<name>`-Webhook, `sensors` in `/api/state`); zum Wiederanzeigen
> Box + Handler aus der git-History zurückholen (in den Templates steht das tote
> `.srow`-CSS noch bereit).

- **Header:** kein Ollama-Status (KI aus); NET/UP/Theme/Uhr.
- **Mitte:** in `laptop.html` jetzt der **Kalender** (blätterbare Woche/Monat,
  `/api/calendar`, s.u. „Kalender-Mitte"); in der **TUI** wahlweise
  **Graph-Werkzeug** (`g`), **Listen** (`l`), **Karte** (`m`) oder **Kalender** (`c`).
- **Minimale Boot-Dependencies:** nur `flask` + `python-dateutil` (kein
  Whisper/TTS/sherpa/piper nötig — die Kassette ist KI-frei). Siehe `starten.md`.

### Terminal-Kassette (`tui/zentrale_tui.py`)

KEIN Browser — rendert direkt im Terminal (curses). Motivation: ein Browser-Tab
frisst auf einer RAM-schwachen Maschine 300–600 MB+, das Backend selbst nur
~32 MB. Die TUI ist ein **eigenständiger Client** (kein Flask-Template): sie
pollt dasselbe `/api/state` (1 s) + `/api/telemetry` (2 s) über HTTP und zeichnet
ein 3-Spalten-Layout analog zur Laptop-Kassette (telemetrie/stdout |
mitte-skelett | lifestyle/outbound; Sensoren-Panel entfernt, s.o.). Header mit
NET/UP/Uhr. Tasten: `q` beendet,
`t` zykliert das Theme (auto/hell/dunkel — auto nach Uhrzeit, wie im Web).
Themes: Light-Mode mit weißem Hintergrund (kein Gelb auf Weiß), Dark-Mode
**ultra-high-contrast** (reinweißer Text 231 auf hartem Schwarz 16, Rahmen Grau
245). Akzent-Grün ist gedämpft (Salbei 108, nie bold → kein Neon). Box-Inhalte
werden auf die jeweilige Box-Innenbreite gekürzt (kein Überlauf in Nachbarspalten).

**Befehlszeile (unten):** `/` öffnet eine Eingabezeile am unteren Rand (die
Shell ist im Alternate-Screen nicht erreichbar — das ist der Ersatz). Beim
Tippen klappt eine **Live-Liste** der passenden Befehle nach oben auf und filtert
mit; Enter führt aus, `Esc` (oder den Slash wegbackspacen) schließt wieder.
Befehle: `/help` (latcht die volle Hilfe inkl. Tastenkürzel, klappt bei der
nächsten Taste weg), `/theme [auto|hell|dunkel]`, `/quit`. Die Logik liegt
curses-frei auf Modulebene (`parse_command`, `overlay_rows`) und ist ohne TTY
unit-testbar. Im Normal-Modus (Zeile zu) wirken `q`/`t` weiter als Shortcuts.

**Graph-Werkzeug (Mitte, Taste `g`):** dieselbe geteilte Logik wie im Monolith
(`core/graphs.py` + `/api/graphs`), hier in curses verbaut. `g` gibt der
MITTE-Box den Fokus; ein kleines Zustandsmodell `G` (`view`: `list`/`new`/`view`)
steuert die Bedienung: in **list** mit ↑/↓ wählen, `n` neu, `d` löschen
(öffnet einen **Mini-Bestätigungsdialog** über der Liste: `j`/Enter löscht,
jede andere Taste bricht ab — `G["confirm"]`), Enter öffnet; in **new** Name
tippen, `Tab` zykliert den **Typ** (s.u.),
Enter legt an (`POST /api/graphs`); in **view** trägt man Werte für *heute* ein,
gespeichert über `/api/log` — dieselbe Route wie die Data-Collection.

Vier **Graph-Typen** (`GRAPH_TYPES`, Validierung in `core/graphs.py`):
- `number` — freie Messwerte (Ziffern + Enter), `blockspark`-Kurve.
- `scale` — 1–5 Bewertung (Taste 1–5 trägt sofort ein).
- `time` — **Uhrzeit pro Datum** (z.B. Einschlafzeit). Eingabe `HH:MM`
  (`parse_clock`), gespeichert als `value` = Minuten seit Mitternacht.
- `period` — **Zeitspanne pro Datum** (z.B. Schlaf `23:00–07:00`). Zwei-Stufen-
  Eingabe von→bis (`pstage`/`input2`), gespeichert als `value`=Start-Minute +
  `end`=End-Minute. `end < value` = über Mitternacht.

`time`/`period` werden als **24h-Gitter** gezeichnet (`draw_time_plot`):
X = letzte Einträge (Datum), Y = Uhrzeit (00:00 **unten** … 24:00 **oben**,
Stunden-Marken), `time` → Punkt `●`, `period` → Balken `█` (über Mitternacht in
zwei Segmente gesplittet via `fill()`, da die Achse an Mitternacht verankert
ist — orientierungs-unabhängig). Formatierung über `fmt_clock` / `graph_last`;
die Sparkline-Reihe liefert `graph_series` (`period` → Dauer via
`period_duration`).

Werte/Definitionen holt das Werkzeug synchron per `api_call()` (POST/DELETE).
Die `lifestyle`-Box rechts zeigt **alle Graphen überlagert** in EINEM Gitter:
X = **festes Fenster der letzten 7 Tage** (heute rechts, 6 Tage zurück nach
links, über die volle Breite verteilt — egal wie viel gefüllt ist; leere Tage
bleiben leer), Y **bewusst mehrdeutig** — jeder Graph nutzt seine *eigene*
Achse + Darstellung, alles übereinandergelegt zum Vergleich. Gezeichnet als
**dünne Linien**, je Graph in einer eigenen **Farbe** (Unterscheidung über die
Farbe, nicht über fette Symbole):
- `period` → dünne **vertikale** Linie `│` über die Zeitspanne (24h-Skala,
  00:00 unten; Wrap über Mitternacht in zwei Segmente),
- `time` → Punkt auf der 24h-Skala,
- `scale` → Punkt auf der eigenen 1–5-Skala,
- `number` → Punkt auf der eigenen min/max-Spanne (über die sichtbaren Werte).

Die Punkt-Typen (`time`/`scale`/`number`) werden über die Tage zu einer
**Liniengrafik verbunden** (Steigung → `╱` steigt, `╲` fällt, `─` flach,
`│` senkrecht; einzelner Punkt → `·`). Farb-Palette `LIFE_COL` (durchgezykelt),
darunter eine gepackte Legende (farbiges `─`-Sample → Name). Es geht um Verlauf
& Gleichzeitigkeit, nicht um absolute Werte (`row_clock`/`row_norm`). Quelle ist
das langsame Hintergrund-Polling (`Store._poll_graphs`, alle 5 s). `Esc`/`g`
schließt das Werkzeug wieder. `--selftest` listet die Graphen inkl.
Typ/Sparkline (ohne TTY).

**Listen-Werkzeug (Mitte, Taste `l`):** abhakbare Todo-/Sammel-Listen — Pendant
zum Graph-Werkzeug, aber für „random stuff" statt Zeitreihen. Geteilte Logik
(`core/lists.py` + `/api/lists`), hier in curses verbaut. `l` gibt der MITTE-Box
den Fokus; ein Zustandsmodell `L` (`view`: `list`/`new`/`view`/`nest`) steuert: in
**list** mit ↑/↓ Liste wählen, `n` neu, `d` löschen (Mini-Bestätigungsdialog wie
beim Graph: `j`/Enter löscht, sonst Abbruch — `L["confirm"]`), `>` ordnet die Liste
in eine andere ein (→ **nest**: Ziel-Liste wählen, Enter; `POST …/<lid>/nest`),
Enter öffnet; in **new** Name tippen + Enter (`POST /api/lists`); in **view** die
Einträge der Liste — **verschachtelt**: jeder Eintrag kann eigene Unterpunkte
tragen, die TUI klopft den Baum mit `l_flatten()` flach (Einrückung = Tiefe) und
zeigt bei Eltern `(erledigt/gesamt)` der Kinder. ↑/↓ wählen, **`space`/Enter**
hakt ab/auf (`…/items/<iid>/toggle`, trifft jede Tiefe), `a` hängt einen neuen
Eintrag oben an, **`s` hängt einen Unterpunkt** unter den markierten
(`L["addparent"]` → `POST …/items {parent}`), `d` löscht den markierten samt
Teilbaum. Erledigte stehen gedämpft mit `[x]` da. Lange Listen scrollen um den
Cursor. Alles synchron per `api_call()`; nach jeder Aktion `l_load()`+`l_sync_def()`
(offene Liste aus der frischen Registry neu greifen). `Esc`/`l` schließt.
`--selftest` listet die Listen inkl. erledigt-Zähler (ohne TTY). Anders als die
Graphen gibt es **keine** `lifestyle`-Box-Überlagerung — eine Liste ist kein
Zeitreihen-Plot. (Monolith/Laptop sind für Listen noch **nicht** verkabelt; das
Backend `/api/lists` steht aber für alle Kassetten bereit.)

**Karte (Mitte, Taste `m`):** Maps-System Schritt 1 — grobe Weltkarte (Küsten
1:110m) in der MITTE-Box, analog zum Graph-Werkzeug. Die TUI ist reiner
Zeichner: holt fertig projizierte Linien über `/api/map/base` (Engine in
`core/map/`) und rastert sie per Bresenham. Steuerung `↑↓←→`/`hjkl` pan,
`+`/`−` zoom, `0` reset, `esc`/`m` zu. **`f`** schaltet den Stil um: `outline`
(Küsten-Bresenham `▓`) ↔ `braille` (gefülltes Land in Braille-Punkten, 2×4
Subpixel/Zelle — Endpoint `/api/map/braille`, gerendert in
`core/map/render.py:base_braille`; die TUI druckt nur die fertigen Zeilen). **`o`**
schaltet das **Handelsrouten-Overlay** (Achse 2) ein/aus: leuchtende
`◆`-Marker an den maritimen Engstellen + Detail (Name/heutiger Verkehr) der dem
Fadenkreuz nächsten Stelle, samt Datenstand. Quelle: IMF PortWatch über
`/api/map/layer/trade` (Provenienz/Lizenz: [maps_quellen.md](maps_quellen.md)).
Mit **`w`** klappt die Karte im
**nativen pygame-Fenster** auf (`scripts/map_window.py`, echte antialiased
Vektorgrafik, gleicher Viewport — wie `/slide` PDFs extern öffnet; dort Taste
**`t`** fürs selbe Overlay als Bernstein-Marker); der
ASCII-Grid in der TUI ist nur die reduzierte Variante. Architektur + die drei
Achsen (Detail/Layer/Zeit): [maps_system.md](maps_system.md).

**Kalender (Mitte, Taste `c`):** blätterbare **Woche** (Mo-So-Tagesliste) bzw.
**Monat** (Zeichen-Gitter), umschaltbar. Wie die Karte reiner Zeichner: holt
fertig gruppierte Tage über `/api/calendar` (Logik in `core/kalender.py`,
`week_view`/`month_view`). Steuerung `←→`/`hl` blättern, `v`/`Tab` Woche↔Monat,
`0` heute, `esc`/`c` zu. Heute hervorgehoben, Monats-Randtage ausgegraut,
`ausfall`-Routinen als `ℹ`. **Einmal-Termine direkt eintragen/löschen:** `a`
öffnet ein gestaffeltes Formular (Datum→Zeit→Titel → `POST /api/calendar/entry`);
in der Wochenliste mit `↑↓` einen Termin wählen, `d`+`j` löscht ihn
(`DELETE /api/calendar/entry`). Routinen bleiben beim KI-Tool (kein ✕). Defensiv
wie der Karten-Pfad (Fehler-Marker statt Dauer-Refetch). Details + die zwei
Browser-Fronten: [kalender_system.md](kalender_system.md).

- **Nur stdlib:** `curses` + `urllib` + `json` + `threading` — null Extra-Deps.
  Setzt UTF-8-Locale vor curses-Init (für Box-/Block-Zeichen).
- Ein Hintergrund-Thread pollt, der curses-Loop liest den Snapshot (thread-safe
  über Lock). Bei Backend-Ausfall: Header zeigt `[backend ?]`, kein Crash.
- `--selftest` gibt einen Text-Snapshot ohne curses aus (Verifikation ohne TTY).
- Backend läuft im `tui`-Mode (KI aus, wie laptop). Start: `zentrale-tui`
  fährt Backend (stdout → Logdatei, nicht ins Terminal) + TUI hoch. Siehe
  `starten.md`. Env `ZENTRALE_URL` überschreibt das Backend-Ziel (Default
  `http://localhost:5000`).

## Stack

- **Backend**: Flask (`ui/app.py`).
- **Frontend**: ein einziges `index.html` mit Vanilla JS, SVG-Charts,
  kein CDN, kein Build-Step. Bewusst gewählt – das Ding muss auf einem
  Pi im Kiosk-Modus offline laufen.

## Polling-Modell

Drei separate Polling-Loops im Frontend, jeder mit eigener Frequenz:

| Endpoint              | Intervall | Was es liefert                                  |
|-----------------------|-----------|-------------------------------------------------|
| `GET /api/state`      | 1 s       | Events, Sensoren, Vokabel, Logs (Haupt-State)   |
| `GET /api/ai/status`  | 30 s      | Ollama erreichbar? + Modell-Name                |

> Das frühere 3 s-Polling gegen `/api/tutor/status` ist raus (Tutor
> pausiert, siehe `tutor_system.md`).

Kein WebSocket, kein SSE für Statusdaten – Polling reicht für
ein Single-User-Dashboard und ist deutlich simpler.

Streaming wird **nur** dort benutzt, wo es wirklich nötig ist:

- `POST /api/chat` – Server-Sent Events (SSE), damit Tokens live
  erscheinen.

## Monolith-Dashboard (Route `/`, source of truth)

Das gelebte Dashboard (`ui/templates/monolith.html`, ein einziges großes HTML mit
mehreren IIFE-Script-Blöcken). Seit 2026-06-08 unter `/` (Alias `/monolith` bleibt
für Kiosk/Bookmarks). Herzstück ist ein
animierter **ASCII-Kern** (`#core`), gesteuert vom *Exhibit-Direktor*
(`frameTick`, 90 ms/Frame). Umschaltbare Exhibits über Tabs: `gesicht`
(Avatar), `torus`, `würfel`, `globus`, `welt` (Weltkarte), `filter`
(Bild→ASCII-Filter aus `data/photos/`, mono/farbe per Re-Klick), `graph`
(s.u., interaktives Panel statt ASCII) und `kalender` (s.u.). `graph` und
`kalender` sind **nicht** im Auto-Direktor (interaktiv, nicht zum Durchzappen).

> **Graph-Werkzeug (Exhibit `graph`)** — der Mittelbereich wird zum
> interaktiven Lifestyle-Tracker: eigene Graphen **anlegen** (Typ `number`
> = freie Messwerte/Kurve, oder `scale` = 1–5), **Werte eintragen** (Datum
> + Wert), **Kurve sehen** (SVG-Plot via `viz.js`). Bei `graph` blendet
> `frameTick` `#core` aus und `#graph-panel` (`.gpanel`) ein und steigt
> früh aus (kein ASCII-Tick). Definitionen serverseitig in
> `data/graphs.json` (`core/graphs.py`, Endpoints `GET/POST /api/graphs`,
> `DELETE /api/graphs/<id>`); die Messwerte teilen sich die
> Data-Collection (`/api/log` schreibt nach `data/<graph_id>.json`,
> `/api/data/<id>` liest). Jeder gespeicherte Wert feuert `zentrale:logged`
> → die `lifestyle`-Box rechts zeigt jeden angelegten Graphen automatisch
> als Sparkline (Quelle: `/api/graphs`, Feld `value`).
>
> **Geteilte Logik, pro Kassette verbaut:** `core/graphs.py` + die
> `/api/graphs`-Endpoints existieren für ALLE Kassetten; nur die UI ist
> kassetten-spezifisch verkabelt — Monolith hier (Browser-Panel), TUI in
> der curses-Mitte (Taste `g`, siehe „Terminal-Kassette"). `laptop.html`
> ist (noch) nicht verkabelt. Das **Anlege-Formular im Monolith** bietet nur
> `number`/`scale`; die Uhrzeit-Typen `time`/`period` (Y-Achse = Uhrzeit)
> legt man in der TUI an (Backend kennt alle vier). Ein so angelegter
> `time`/`period`-Graph erscheint in der Monolith-`lifestyle`-Box als
> Sparkline über `value` (Minuten) — funktioniert, nur ohne HH:MM-Format.

> **Kalender (Exhibit `kalender`)** — der Mittelbereich zeigt den Kalender:
> blätterbare **Woche** (Mo-So-Liste) bzw. **Monat** (Gitter), umschaltbar,
> heute hervorgehoben, `ausfall`-Routinen als `ℹ`, Header-Zähler `⚠N` aus den
> offenen Alarmen. Eigenes `#calendar-panel` (`.cpanel`, `frameTick` blendet wie
> bei `graph` `#core` aus). Reiner Zeichner: Daten von `/api/calendar`
> (`view`+`ref`), Datums-Logik in `core/kalender.py`. **Derselbe Endpoint** für
> alle drei Fronten (Monolith-Tab, Laptop-Mittelbox, TUI-Taste `c`). Einmal-
> Termine direkt anlegen („＋ Termin"-Form → `POST /api/calendar/entry`) und je
> Termin per ✕ löschen (`DELETE …`); Routinen bleiben beim KI-Tool. Schreiben ist
> direkte Nutzeraktion, **nicht** KI-gegatet. Details:
> [kalender_system.md](kalender_system.md).

> Die IIFEs sind getrennte Scopes. Cross-Scope-Signale laufen über den
> CustomEvent-Bus auf `window` (`zentrale:logged`, `zentrale:ascii`),
> nicht über geteilte Funktionen.

### Layout (was Sasha real sieht)

`#stage` ist 1920×1080 (Kiosk, scale-to-fit). Oben eine schmale Statusleiste
(`.top`: „ZEN · monolith · adaptive konsole", Ollama/Netz/Uptime, Theme
AUTO/HELL/DUNKEL). Darunter `.body` als 3 Spalten:

```
+------------+----------------------+------------+
| LINKS      |  MITTE (#col-mid)    | RECHTS     |
| telemetrie |  ki-kern:            | lifestyle  |
| stdout     |   tabs + #core       |  (tracker) |
| (#term)    |   + ⚠ alarm-corner   | outbound   |
|            |  konsole (chat-in)   |  (#term-net|
|            |  minilog + cinema-sub|   tripwire)|
+------------+----------------------+------------+
```

> **Sensoren-Panel entfernt (2026-06)** — in allen Kassetten, inkl. Monolith
> (Details + Backend-bleibt-verkabelt: siehe „## Kassetten"). Auch der
> `_DASHBOARD_VIEW`-Prompt in `core/ai.py` nennt die Sensoren nicht mehr.

- **LINKS:** `telemetrie` (PC·CPU-Meter), `stdout` (`#term`, voller Log-Stream
  aus `state.push_log`).
- **MITTE (`#col-mid`):** die `ki-kern`-Box mit Exhibit-Tabs (Gesicht/Torus/
  Würfel/Globus/Welt/Filter/Graph/Auto) + dem ASCII-Kern `#core` (s.u.) + der
  Alarm-Ecke; darunter `core-readout` (AI-State „BEREIT", „zeigt: gesicht"), das
  `minilog` (letzte Konversationszeilen) und `#cinema-sub`. Darunter die
  `konsole` (`#chat-input`, wo Sasha tippt). Der `Graph`-Tab macht den
  Mittelbereich zum Graph-Werkzeug (s.o.).
- **RECHTS:** `lifestyle` (Tracker: hartkodierte Kategorien + jeder im
  Graph-Werkzeug angelegte Graph als Sparkline) + `outbound` (`#term-net`,
  Internet-Tripwire, Idle „// offline ✓").

### Alarm-Ecke (`#alarm-corner`) — die ⚠-Warnsymbole

Unten links **in `.core-wrap`** (also am ASCII-Kern), `position:absolute`
left/bottom 12px, `flex column-reverse`. Pro offenem Kalender-Alarm ein
Pixel-**Warndreieck** (`.alarm-tri`, `<title>`=Volltext für Hover), gedeckelt auf
`ALARM_MAX=5` + „+N"-Indikator. Quelle: `e.alarms` aus `/api/state`
(= `kalender.open_alarms`), gerendert von `renderAlarms()`. Leer → Ecke leer.
Im Cinema-Modus verblasst sie (`opacity .12`, Puls aus). **Das ist „die Warnung im
Dashboard", auf die Sasha zeigt** — die KI weiß davon seit 2026-06 über den
`_DASHBOARD_VIEW`-Prompt-Block (`core/ai.py`), damit sie die Frage „was ist diese
Warnung?" mit dem Alarm-Block verbindet statt „kenne dein Dashboard nicht" zu
sagen (Hintergrund: `grounding_recherche.md`).

### ASCII-Kern / Bild-Marker (KI redet visuell)

Tippt die KI in ihrer Antwort den Marker `[[bild: stichwort]]` (Backend-
Pipeline + Begründung der Marker-statt-Tool-Entscheidung siehe
`ki_system.md`), übernimmt das gematchte ASCII-Bild den Kern **auf Zeit**:

- **Transport:** Das Backend zieht den Marker aus dem Antworttext und
  yieldet das Bild **inline** im SSE-Antwort-Stream → Event `data.ascii`
  (der Marker selbst erreicht das Frontend nie als Text). Der Chat-IIFE-
  Leser feuert daraus ein `window`-Event `zentrale:ascii` `{art, name}`;
  der Exhibit-Direktor (andere IIFE) hört darauf und ruft `showAiArt()`.
  So erscheint das Bild synchron, während die Worte streamen.
- **Anzeige:** `showAiArt` setzt `aiArt` (Vorrang vor allen Exhibits).
  `frameTick` blendet das Bild zeilenweise ein (`AI_ART_REVEAL` ≈ 14
  Frames), hält es `AI_ART_HOLD` ≈ 110 Frames (~10 s) und kehrt dann
  automatisch zum normalen Auto-Programm zurück (`syncTabs`).
- Kein Text → nicht im Minilog, kein TTS. Reine Mimik zur Antwort.

### Sendungs-/Cinema-Modus (News-Sendung)

Liest die KI eine News-Sendung vor (Tool `lies_news`), schaltet das Dashboard
in einen Kino-Modus: **Seiten-Spalten + Header dimmen sanft** (`opacity .3`),
die **Mittelspalte (`#col-mid`) bleibt hell** und der **Kern (`#core`) voll
sichtbar** (Animationen/Bilder laufen weiter — kein schwarzer Vollvorhang!).
Der **gerade gesprochene Satz** erscheint groß als **Lower-Third** (`#cinema-sub`
unten in `.core-wrap`), synchron zur Satz-TTS (`drainSpeakQueue`/`audio.onended`).
`#minilog` (letzte User-Zeile) faded raus; Konsole schrumpft + dimmt (klart beim
Tippen). Trigger: SSE-Event `data.cinema` (Backend yieldet `{cinema:true}` wenn
`lies_news` läuft) → `enterCinema()` setzt `data-cinema="on"` aufs Stage.
Schließt am Sendungsende (`done` + letzter Satz) oder bei `stopSpeaking`; bei
`chatMuted` aus. Voller Mechanismus: [news_system.md](news_system.md).

### Knopf-Leiste (2–4 Knöpfe statt Eingabe)

Zwei Auslöser, dieselbe Leiste: das Backend fängt ein bestätigungspflichtiges
Schreib-Tool ab (Auto-Gate, Default JA/NEIN) **oder** die KI ruft selbst
`frage_knopf` mit eigenen Labels (Backend-Mechanik + Begründung siehe
`ki_system.md`). Der Chat-IIFE tauscht die Konsolen-Eingabe gegen die Knöpfe:

- **Transport:** SSE-Event `data.permission {frage, optionen}` (parallel zu
  `token` und `ascii` im selben `/api/chat`-Stream; `optionen` fehlt beim
  Auto-Gate → Default `['ja','nein']`). Der Reader zeigt die Frage als KI-Zeile
  im Minilog + TTS, ruft `showPermissionDialog(optionen)` und liest **weiter** –
  der Stream bleibt offen, das Backend blockiert.
- **Anzeige:** `#perm-bar` (im `.console`-Row, default `display:none`) blendet
  sich ein, `#chat-input`/`#chat-mic-btn` aus (der `›`-Prompt bleibt als Anker).
  Die Knöpfe baut das JS dynamisch in `#perm-btns` (ein `.perm-btn` pro Label,
  Großschreibung per CSS), der angewählte trägt `.sel` (Akzentfarbe).
- **Navigation:** Pfeil ← → zykliert `permSel` modulo durch die N Knöpfe, Enter
  wählt den aktiven (`permOptions[permSel]`). Listener auf `document` mit
  `capture=true`, weil das versteckte Input keinen Fokus mehr hat. Maus-Klick
  geht auch (jeder Knopf hat seinen eigenen Click-Handler).
- **Antwort:** `submitPermission(label)` blendet die Leiste zurück, stoppt eine
  noch laufende TTS-Frage, setzt AI-State `thinking` und feuert `POST
  /api/permission_answer {answer: label}` (fire-and-forget) → entsperrt den
  wartenden Stream, der Rest der Antwort streamt auf demselben Reader weiter.
  Bricht der Stream beim Warten ab, stellt der `finally`-Zweig die normale
  Eingabe wieder her (kein Hängenbleiben).

## Data Collection

Taste `K` öffnet den Data-Collection-Modus.

**Kategorie-Auswahl:**
- `1`, `2`, … – Kategorie wählen
- `ESC` oder `K` – zurück

**Formular:**
- `↑` / `↓` – zwischen Feldern navigieren
- `Enter` – Feld bearbeiten
- `K` – **speichern** und zurück
- `ESC` – zurück **ohne** zu speichern

(Vollständige Tastenliste inkl. Smiley- und Date-Edit: `tastatur.md`.)

**Feld-Typen:**
- `date` – Datum, mit `↑`/`↓` tageweise ändern
- `smiley_scale` – 5 SVG-Smileys (😞→😄), mit `←`/`→` auswählen
- `text` – einfaches Eingabefeld (Placeholder-Implementierung)

### Aktuell vorhandene Kategorien

In `core/categories.py` sind bereits zwei Kategorien definiert:

| `id`            | Name           | Felder                                            |
|-----------------|----------------|---------------------------------------------------|
| `sleep_quality` | Sleep Quality  | `date` (date), `quality` (smiley_scale, 5 Stufen) |
| `food_intake`   | Food Intake    | `date` (date), `meal` (text)                      |

Das Sleep-Quality-Chart auf dem Haupt-Dashboard ist hardcoded auf die
`sleep_quality`-Daten – andere Kategorien werden aktuell nur im
Data-Collection-Modus verwaltet, nicht visualisiert.

### Neue Kategorie hinzufügen

In `core/categories.py`:

```python
{
    "id": "meine_kategorie",
    "name": "Meine Kategorie",
    "fields": [
        {"id": "date",    "label": "Date",    "type": "date"},
        {"id": "quality", "label": "Qualität", "type": "smiley_scale", "steps": 5},
    ],
}
```

Daten landen automatisch in `data/<id>.json`.
