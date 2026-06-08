# Dashboard & Frontend

> **AKTUELLER STAND (2026-06): Live ist NUR noch das Monolith-Dashboard**
> (`ui/templates/monolith.html`). Das alte `index.html` (AI-Orb, `#view-main`-
> Grid, `#panel-ai`/`#panel-chat`-Modi, Chat/Data-Collection per Taste) ist
> **weg** - die entsprechenden Sektionen wurden hier gelöscht, weil veraltete
> Layout-Doku schon einmal zu falschen KI-Prompt-Texten geführt hat (Dashboard-
> Sicht, siehe `grounding_recherche.md`). Was Sasha real sieht steht unter
> „## Monolith-Dashboard".

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
(Bild→ASCII-Filter aus `data/photos/`, mono/farbe per Re-Klick).

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
| sensoren   |  ki-kern:            | lifestyle  |
| telemetrie |   tabs + #core       |  (tracker) |
| stdout     |   + ⚠ alarm-corner   | outbound   |
| (#term)    |  konsole (chat-in)   |  (#term-net|
|            |  minilog + cinema-sub|   tripwire)|
+------------+----------------------+------------+
```

- **LINKS:** `sensoren` (BUTTON/LICHT/BEWEGUNG-PIR/TÜR), `telemetrie` (PC·CPU-
  Meter), `stdout` (`#term`, voller Log-Stream aus `state.push_log`).
- **MITTE (`#col-mid`):** die `ki-kern`-Box mit Exhibit-Tabs (Gesicht/Torus/
  Würfel/Globus/Welt/Filter/Auto) + dem ASCII-Kern `#core` (s.u.) + der Alarm-
  Ecke; darunter `core-readout` (AI-State „BEREIT", „zeigt: gesicht"), das
  `minilog` (letzte Konversationszeilen) und `#cinema-sub`. Darunter die
  `konsole` (`#chat-input`, wo Sasha tippt).
- **RECHTS:** `lifestyle` (Tracker) + `outbound` (`#term-net`, Internet-Tripwire,
  Idle „// offline ✓").

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
