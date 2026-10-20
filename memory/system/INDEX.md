# System — Index

Wie der Kern von ZENTRALE gebaut ist: Threads, Datenfluss, Schichten, wer
auf welcher Maschine läuft, und wie die Fronten daran hängen. Die Plattform
darüber (Hub-Schnittstelle, Apps, Werkstatt, Shop, Desk, Bausteine, Produkt):
[../hub/INDEX.md](../hub/INDEX.md).

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Gesamt-Architektur: Threads, Datenfluss, Modul-Übersicht | [architektur.md](architektur.md) |
| **Gefahrzonen** — Fehler, die versteckt wiederkommen: Eingefrorener Tag (Mitternacht im Dauerbetrieb; die eine Uhr `core/uhr.py`, Tageswechsel-Ereignis, Wächter, bekannte Funde); Stumme Leere (leeres Ergebnis ohne Grund, `except: {}`) | [gefahrzonen.md](gefahrzonen.md) |
| **Bauplan des Kerns** — Schichten, wer wen importieren darf, Türen, Altlasten (mit Prüftest) | [bauplan_kern.md](bauplan_kern.md) |
| **Bauplan der TUI** — wie `tui/` in Ansichten geschnitten ist, Kontext statt Closures, Reihenfolge, Sicherheitsnetz | [tui_bauplan.md](tui_bauplan.md) |
| **Tastentabelle und Leiste** — EINE Tastenleiste ganz unten; jedes Programm verteilt aus einer Tabelle, der Horcher liest sie beim Verkabeln; Ansichten je Programm | [tastentabelle.md](tastentabelle.md) |
| **Pixelstil** der TUI — Sextant-Pixel, Braille-Icons, Paletten Tag/Nacht, Motive, Regeln für neue Symbole | [pixelstil.md](pixelstil.md) |
| Wer läuft wo — PC ↔ Pi ↔ Laptop, Sync der `data/*.json` | [topologie.md](topologie.md) |
| **Heimnetz (Plan)** — PC als Gehirn ohne Bildschirm, eigener Router, VPN, Sunshine; Übergang bis Glasfaser | [heimnetz.md](heimnetz.md) |
| Sensoren → Events → Brain → Actions | [event_system.md](event_system.md) |
| **Der Takt** — wann sie unaufgefordert spricht (Termin-Ping, Schweigeregeln, Frische vor dem Melden) | [takt.md](takt.md) |
| **Anwesenheit & Ring** — ist Sasha da, schaut er hin; die Mitte der TUI | [anwesenheit_und_ring.md](anwesenheit_und_ring.md) |
| **Audio-Straße** — ein Mikro/Lautsprecher am Pi für Tutor, Assistent und weitere Agenten; Weiche offen | [audio_strasse.md](audio_strasse.md) |
| Die REST-Endpoints, die alle Fronten benutzen (Kacheln/Desk genau: `openapi.yaml`) | [api_endpoints.md](api_endpoints.md) |
| Dashboard & Frontend: Modi, Polling, KI-Kern, SSE-Events | [dashboard.md](dashboard.md) |
| Browser-Front unter /zentrale: Route, Dateien, ruhender Tab, Zugang | [browser_front.md](browser_front.md) |
| **Fokus-Werkzeug** (Listen, Taste `f`) — Tasten, Ebenen, Bernsteinleiste; steht beim Listenprogramm | [../hub/listen_app.md](../hub/listen_app.md) |
| Tastatur-Belegung in jedem Modus | [tastatur.md](tastatur.md) |
| **ZEN-MOBILE** — die Handy-App (`mobile/`): Auge, KI-Chat, Handy als eigener Knoten an der Mitte | [zen_mobile.md](zen_mobile.md) |

## Stand der Fronten (2026-10-12)

Die **TUI** ist die Haupt-Front (`zentrale` / `zentrale-tui`). Das
Browser-Dashboard (`monolith.html`) liegt seit 2026-10-12 wieder unter
`http://localhost:5000/zentrale` ([dashboard.md](dashboard.md)). Die **Kassetten** (`core/kassette.py`) sind entfernt (Rückbau aus
dem `zentrale`-Tracker erledigt, 2026-10-04); übrig ist ein Schalter
`ZENTRALE_LOKALE_KI` (`ai_backends.lokale_ki_aus()`, siehe
[dashboard.md](dashboard.md)).

Die TUI ist ein **Thin Client**: kein eigenes Modell, kein eigenes Gedächtnis.
Sie spricht ausschließlich HTTP mit `/api/chat` und rendert den Event-Strom;
Denken, Graph, Tools und Gate liegen im Backend
([../ki/ki_system.md](../ki/ki_system.md)).
