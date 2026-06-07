# Dashboard & Frontend

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

## Layout (CSS-Grid mit named areas)

`#view-main` ist ein 3-Spalten-Grid:

```
+---------+---------------------+----------+
| sensors |        ai           |  graph   |
+---------+---------------------+----------+
|              term (Footer)              |
+-----------------------------------------+
```

Spaltenbreiten: `auto  minmax(0,1fr)  clamp(220px, 22vw, 340px)`.
Grid-areas: `sensors ai graph` / `term term term`. Areas sind bewusst
benannt, damit später AI- und Graph-Panel per JS-Class swappable sind
ohne jede Card einzeln umzubauen.

## Modi

Das Frontend hat eine zentrale „AI-Card" in der Mitte (`#main-display`).
Je nach Modus wird der Inhalt dieser Card ausgetauscht
(`#panel-ai` / `#panel-chat`). Sensoren-Spalte links und Mini-Graph
rechts bleiben dabei sichtbar.

> `#panel-tutor` und die zugehörigen JS-Funktionen existieren noch im
> HTML, sind aber dormant (Tutor pausiert, siehe `tutor_system.md`).

### Haupt-Ansicht (default, `#panel-ai`)
- **AI-Orb** (`#ai-orb`): pixelierte Neon-Sonne als SVG. Idle = ruhiger
  Glow + solider Kreis-Outline + ultra-langsame Pixel-Ring-Rotation.
  Active (`.ai-orb.active`) = Strahlen erscheinen, schneller Halo-Pulse,
  Partikel fliegen radial.
- **Mini-Chat-Log** (`#mini-log`): unter dem Orb, zeigt die letzten 5
  Konversations-Zeilen (User+AI), Polling alle 2.5s gegen
  `/api/chat/history`.
- **Sensoren-Spalte** (links): Button + Light Sensor.
- **Side-Graph** (rechts): Sleep-Quality-Chart (kompakt).
- **Terminal** (unten, in zwei Panels gesplittet):
  - **Links (`#terminal`, neon-grün):** voller Log-Stream. Speist sich
    aus `state.push_log(...)`, das von `net.py` (`NET →` / `NET ←`),
    `audio.py` (`STT →` / `TTS →`), `main.py` (`EVENT IN:` / `EVENT OUT:`),
    `graph.py` (`GRAPH ⊕` / `GRAPH →` / `GRAPH ←`) etc. befüllt wird.
  - **Rechts (`#terminal-net`, orange):** **nur** Internet-Traffic.
    Spiegel-Channel `state._internet_logs`, befüllt aus `net.py` wenn
    `net._is_internet(url)` True liefert (localhost/RFC1918/link-local
    /`*.local` → False, alles andere → True). Idle-Hinweis
    `// keine outbound-Pakete · offline ✓` wenn leer. Das Panel ist als
    **Tripwire** gedacht: ZENTRALE läuft per Design offline – sobald da
    eine Zeile auftaucht, ging tatsächlich was raus, und du siehst es
    sofort statt es im großen stdout zu übersehen.
    > Erfasst werden nur Calls, die durch `core/net.py` laufen. Browser-
    > Polling, externe Prozesse (`ollama pull`, `git pull`, APT) und
    > `audio.py` (loggt selbst, lokal-only) sind nicht im Panel.

Stil: cyberpunk dark-HUD — eckige Cards, Neon-Grün auf dunkel-
durchscheinendem Background, CRT-Scanlines als statisches Overlay
(ohne `mix-blend-mode`, das war auf der Pi-VC4-GPU zu teuer).

### Chat-Modus (Taste `C`)
- KI-Chat (lokales Ollama-Modell), Tokens streamen live.
- Slash-Commands: `/memory`, `/forget N`, `/clear`.
- **Mic-Button** (`#chat-mic-btn`) im Input-Row neben dem Text-Feld.
  Toggle-Verhalten: erster Click startet Aufnahme (rot, blinkt), zweiter
  Click stoppt und schickt das WAV an `/api/transcribe`. Transkribierter
  Text landet im Input-Feld (kein Auto-Send) – User kann editieren oder
  mit Enter senden. Beim Senden geht ein `via_mic`-Flag an `/api/chat`
  mit, der die KI über den Spracheingabe-Kontext informiert
  (Whisper-Fehler-Awareness, siehe `ki_system.md`). Sobald der User
  tippt nachdem der Text aus dem Mic kam, kippt das Flag auf `false`.
- Details zur KI: `ki_system.md`.

### Data-Collection-Modus (Taste `K`)
- Tastaturgesteuerte Datenerfassung.
- Details siehe unten.

## Monolith-Dashboard (`/monolith`)

Separate, neuere Dashboard-Variante (`ui/templates/monolith.html`, ein
einziges großes HTML mit mehreren IIFE-Script-Blöcken). Herzstück ist ein
animierter **ASCII-Kern** (`#core`), gesteuert vom *Exhibit-Direktor*
(`frameTick`, 90 ms/Frame). Umschaltbare Exhibits über Tabs: `gesicht`
(Avatar), `torus`, `würfel`, `globus`, `welt` (Weltkarte), `filter`
(Bild→ASCII-Filter aus `data/photos/`, mono/farbe per Re-Klick).

> Die IIFEs sind getrennte Scopes. Cross-Scope-Signale laufen über den
> CustomEvent-Bus auf `window` (`zentrale:logged`, `zentrale:ascii`),
> nicht über geteilte Funktionen.

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
