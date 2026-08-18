# System — Index

Wie ZENTRALE gebaut ist: Threads, Datenfluss, wer auf welcher Maschine läuft,
und wie die Fronten daran hängen.

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Gesamt-Architektur: Threads, Datenfluss, Modul-Übersicht | [architektur.md](architektur.md) |
| Wer läuft wo — PC ↔ Pi ↔ Laptop, Sync der `data/*.json` | [topologie.md](topologie.md) |
| Sensoren → Events → Brain → Actions | [event_system.md](event_system.md) |
| **Der Takt** — wann sie unaufgefordert spricht (Termin-Ping, Schweigeregeln) | [takt.md](takt.md) |
| Die REST-Endpoints, die alle Fronten benutzen | [api_endpoints.md](api_endpoints.md) |
| Dashboard & Frontend: Modi, Polling, KI-Kern, SSE-Events | [dashboard.md](dashboard.md) |
| Tastatur-Belegung in jedem Modus | [tastatur.md](tastatur.md) |
| ⚠ **Veraltet** — beschreibt das gelöschte `index.html`, kein Hook stimmt noch. Nimm `dashboard.md`. | [ui_hooks.md](ui_hooks.md) |

## Stand der Fronten (2026-08-15)

Gearbeitet wird nur noch an der **TUI** (`zentrale-tui`). Die Browser-Fronten
(monolith / laptop) sind praktisch aufgegeben. Die **Kassetten-Logik**
(`core/kassette.py`, `ki_aus()`) ist damit überflüssig geworden und steht als
Rückbau im `zentrale`-Tracker — der Code lebt vorerst weiter.

Die TUI ist ein **Thin Client**: kein eigenes Modell, kein eigenes Gedächtnis.
Sie spricht ausschließlich HTTP mit `/api/chat` und rendert den Event-Strom;
Denken, Graph, Tools und Gate liegen im Backend
([../ki/ki_system.md](../ki/ki_system.md)).
