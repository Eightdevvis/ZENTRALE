# Projekt-Überblick & Status

## Was ZENTRALE ist

Event-getriebene Zentrale für einen Wand-Monitor auf Raspberry Pi
(Entwicklung läuft parallel auf einem Linux-PC). Sensoren und Zeitgeber
erzeugen Events, der Core verarbeitet sie, das Web-Dashboard zeigt alles
an – **offline by default**.

Die KI ist lokal (Ollama + qwen3.5:9b). Kein Cloud-Modell, keine Telemetrie.
**Eine Ausnahme seit 2026-06-07:** die KI hat eine **gegatete Internet-Pipe**
(Tools `web_search`/`fetch_url`, in der `klein`-Schiene `web_suche`/`hole_url` —
siehe „Zwei Schienen" in `memory/ki/ki_system.md`; Suche via SearXNG
self-hosted) – jeder Call nach draußen
muss von Sasha per Knopf bestätigt werden und leuchtet im Internet-Monitor
des Dashboards auf. Ohne diese bewusste Freigabe verlässt nichts das Heimnetz.
Details: `memory/ki/ki_system.md` → „Internet-Pipe". Die KI hat zusätzlich Lese-Zugriff
auf eine fest definierte Whitelist von Projektdateien (siehe
`memory/betrieb/datei_zugriffe.md`) und eine persistente Memory über Sessions hinweg.

## Aktueller Stand (2026-06)

| Komponente                                    | Stand                              |
|-----------------------------------------------|------------------------------------|
| Dashboard, Data Collection, Chat              | fertig + getestet                  |
| KI-Memory (Konzept-Graph), Tool-Use           | fertig + getestet                  |
| Monolith-Dashboard (`/monolith`)              | in Integration, parallel zu `/`    |
| Visuelle Stimme (Bild-Marker `[[bild:]]`)     | live (siehe `memory/ki/ki_system.md`)        |
| Gegatete Internet-Pipe (`web_search`/`fetch_url`)| live, JA/NEIN-Knopf-Gate         |
| Kalender + Konflikt-Alarm                     | live                               |
| Sprach-Tutor (Persona-Portal, `tutor/`)       | live: `zh`/Ling Ling über qwen; `fr`/`ru`/`ar`/`es` als Skizzen (siehe `memory/tutor/tutor_system.md`) |
| Echter PIR-Sensor + GPIO                      | nicht angebunden – `sensors.py` simuliert via Tastatur |

## Geplante Features (Roadmap)

- Echter GPIO-Support für Pi (RPi.GPIO, kein sudo nötig wenn User in
  `gpio`-Gruppe ist)
- PIR-Sensor (HC-SR501) an GPIO für echte Motion Detection
- Nachrichten-Zusammenfassungen via RSS
- Anbindung an das hauseigene Security-System
- Multi-Monitor Support

## Verwandt

- Architektur-Details: `memory/system/architektur.md`
- Was funktioniert wie: jeweils das Thema-File
