# System — Index

Wie ZENTRALE gebaut ist: Threads, Datenfluss, wer auf welcher Maschine läuft,
und wie die Fronten daran hängen.

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Gesamt-Architektur: Threads, Datenfluss, Modul-Übersicht | [architektur.md](architektur.md) |
| **Bauplan des Kerns** — Schichten, wer wen importieren darf, Türen, Altlasten (mit Prüftest) | [bauplan_kern.md](bauplan_kern.md) |
| **Produkt-Inventur** — was fertig, beta, Umbau, nur Dev; Lizenz-Ecke frei/Abo/exklusiv; was vor dem Verkauf fehlt (09.10.) | [produkt_inventur.md](produkt_inventur.md) |
| **Hub-Bauplan** — ZENTRALE als Plattform, Module als Apps: Manifest, Rechte, Datenordner je App, Ereignisse, Modell-Zugang, Umzugs-Reihenfolge; entschieden 09.10., Schritt 1 (Tutor als App) erledigt; Kacheln (entschieden) | [hub_bauplan.md](hub_bauplan.md) |
| **Bauplan der TUI** — wie `tui/` in Ansichten geschnitten ist, Kontext statt Closures, Reihenfolge, Sicherheitsnetz | [tui_bauplan.md](tui_bauplan.md) |
| **Desk View** — unendliche Fläche je Desk mit Zetteln und Schnüren (Taste `d`), Canvas-Baustein, Format JSON Canvas, Tasten, offene Punkte (09.10.) | [desk_view.md](desk_view.md) |
| **Pixelstil** der TUI — Sextant-Pixel, Braille-Icons, Paletten Tag/Nacht, Motive, Regeln für neue Symbole | [pixelstil.md](pixelstil.md) |
| Wer läuft wo — PC ↔ Pi ↔ Laptop, Sync der `data/*.json` | [topologie.md](topologie.md) |
| **Heimnetz (Plan)** — PC als Gehirn ohne Bildschirm, eigener Router, VPN, Sunshine; Übergang bis Glasfaser | [heimnetz.md](heimnetz.md) |
| Sensoren → Events → Brain → Actions | [event_system.md](event_system.md) |
| **Der Takt** — wann sie unaufgefordert spricht (Termin-Ping, Schweigeregeln) | [takt.md](takt.md) |
| **Anwesenheit & Ring** — ist Sasha da, schaut er hin; die Mitte der TUI | [anwesenheit_und_ring.md](anwesenheit_und_ring.md) |
| **Audio-Straße** — ein Mikro/Lautsprecher am Pi für Tutor, Assistent und weitere Agenten; Weiche offen | [audio_strasse.md](audio_strasse.md) |
| Die REST-Endpoints, die alle Fronten benutzen | [api_endpoints.md](api_endpoints.md) |
| Dashboard & Frontend: Modi, Polling, KI-Kern, SSE-Events | [dashboard.md](dashboard.md) |
| Tastatur-Belegung in jedem Modus | [tastatur.md](tastatur.md) |
| **ZEN-MOBILE** — die Handy-App (`mobile/`): Auge, KI-Chat, Handy als eigener Knoten an der Mitte | [zen_mobile.md](zen_mobile.md) |

## Stand der Fronten (2026-10-06)

Die **TUI** ist die einzige Front (`zentrale` / `zentrale-tui`). Das
Browser-Dashboard (`monolith.html`) ist archiviert
([../archive/browser_front.md](../archive/browser_front.md)). Die **Kassetten** (`core/kassette.py`) sind entfernt (Rückbau aus
dem `zentrale`-Tracker erledigt, 2026-10-04); übrig ist ein Schalter
`ZENTRALE_LOKALE_KI` (`ai_backends.lokale_ki_aus()`, siehe
[dashboard.md](dashboard.md)).

Die TUI ist ein **Thin Client**: kein eigenes Modell, kein eigenes Gedächtnis.
Sie spricht ausschließlich HTTP mit `/api/chat` und rendert den Event-Strom;
Denken, Graph, Tools und Gate liegen im Backend
([../ki/ki_system.md](../ki/ki_system.md)).
