# Browser-Front unter /zentrale

**Stand 2026-10-14:** Die Browser-Front `monolith.html` ist seit 2026-10-12
wieder da, als zweite Ansicht neben der TUI unter
`http://localhost:5000/zentrale`. Ausgelagert aus `dashboard.md` (Regel 9).
Wie das Dashboard aufgebaut ist: [dashboard.md](dashboard.md).

Zurück aus dem Archiv (2026-10-04 geparkt, 2026-10-06 archiviert). Die TUI
bleibt die Haupt-Front; der Browser ist eine zweite Ansicht auf dieselben
`/api/`-Routen.

- **Route:** `ui/routen/browser.py` (Blueprint `browser`): `/zentrale` rendert
  `ui/templates/monolith.html` (`no-store`), `/` leitet dorthin weiter,
  `/api/photos[/<name>]` liefert Fotos für den Bild→ASCII-Filter (Ordner
  `data/photos/`, Env `ZENTRALE_PHOTO_DIR`; fehlt er, nimmt der Filter sein
  Test-Bild).
- **Dateien:** `ui/static/` (`engine.js` = Daten-Adapter, `viz.js`,
  `ascii.js`, `fonts/`) unter `/zentrale/static/…`, im Template per
  `url_for('browser.static', …)`. Die App hat keinen eigenen `/static`-Weg
  mehr (`static_folder=None` in `ui/app.py`). `fonts.css` verweist relativ.
- **KI-Blöcke:** `ki_aus = ai_backends.lokale_ki_aus()` ans Template; dann
  fallen sie per `{% if not ki_aus %}` / `if (!window.KI_AUS)` weg
  (Chat/Audio/Tutor/News/OLLAMA-Status), unten steht die Tastenkürzel-Box.
- **Verdeckter Tab ruht:** jede Wiederholung (Polling `/api/state` 1 s,
  Telemetrie, Tracker, Animationen) läuft über `wiederholen(fn, ms)` aus
  `engine.js` statt über `setInterval`. Bei `document.hidden` stehen alle;
  bei `visibilitychange` zurück läuft jede sofort einmal und dann weiter.
  Ausnahme: die Laufzeit-Anzeige während einer Aufnahme. Ein Test hält das
  fest (`tests/test_browser_front.py`).
- **Zugang:** die Tür (`ui/routen/zugang.py`) gilt wie überall; von diesem
  Rechner aus frei. Am Laptop lauscht das Backend nur auf `127.0.0.1`
  ([../betrieb/zugang.md](../betrieb/zugang.md) „Wer lauscht wo").
- Design-Entwürfe (Bernstein, Kern, Orakel) bleiben im Archiv:
  `memory/archive/browser_front/entwuerfe/`.

## Historie

- **2026-10-04** geparkt, **2026-10-06** archiviert, **2026-10-12** zurück
  unter `/zentrale` (0ec988a). **2026-10-14** aus `dashboard.md` hierher
  ausgelagert.
