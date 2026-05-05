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
| `GET /api/tutor/status` | 3 s     | Session aktiv? + Whisper/TTS verfügbar?          |
| `GET /api/ai/status`  | 30 s      | Ollama erreichbar? + Modell-Name                |

Kein WebSocket, kein SSE für Statusdaten – Polling reicht für
ein Single-User-Dashboard und ist deutlich simpler.

Streaming wird **nur** dort benutzt, wo es wirklich nötig ist:

- `POST /api/chat` – Server-Sent Events (SSE), damit Tokens live
  erscheinen.
- `POST /api/tutor/start` und `POST /api/tutor/respond` – ebenfalls SSE.

## Modi

Das Frontend hat ein zentrales Layout mit „Karten". Je nach Modus wird
die linke Hauptkarte ausgetauscht.

### Haupt-Ansicht (default)
- **Haupt-Karte**: Sleep-Quality-Chart (SVG).
- **Sensoren**: Button, Light, Motion als Statusanzeige.
- **Mandarin**: Vokabel des Tages mit Schriftzeichen + Pinyin.
- **Terminal**: Live-Log der letzten System-Ausgaben. Speist sich aus
  `state.push_log(...)`, das von `net.py` (`NET →` / `NET ←`),
  `audio.py` (`STT →` / `TTS →`) und `main.py` (`EVENT IN:` / `EVENT OUT:`)
  befüllt wird.

### Chat-Modus (Taste `C`)
- KI-Chat mit Mistral, Tokens streamen live.
- Slash-Commands: `/memory`, `/forget N`, `/clear`.
- Details zur KI: `ki_system.md`.

### Tutor-Modus (Taste `T` oder Motion-Sensor)
- Mandarin-Smalltalk mit STT + TTS.
- `Space` = Aufnahme starten/stoppen.
- Details: `tutor_system.md`.

### Data-Collection-Modus (Taste `K`)
- Tastaturgesteuerte Datenerfassung.
- Details siehe unten.

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
