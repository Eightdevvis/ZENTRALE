# ZENTRALE – Memory Index

Dieser Ordner ist die modulare Wissensbasis des Projekts. Jedes Thema hat
sein eigenes File. Nicht alles auf einmal lesen – über diesen Index
gezielt zu dem Thema springen, das gerade gebraucht wird.

Konvention: dieser Index enthält **nur** Thema → Pfad. Inhalte gehören
in die jeweiligen Files. Wenn ein neues Thema dazukommt → File anlegen
und hier eine Zeile ergänzen. Wenn ein Thema umbenannt/verschoben wird →
hier sofort mitziehen, sonst tote Links.

## Themen

| Thema                              | Pfad                                |
|------------------------------------|-------------------------------------|
| Projekt-Überblick & Status         | memory/ueberblick.md                |
| Gesamt-Architektur & Threads       | memory/architektur.md               |
| Event-System (Sensoren → Actions)  | memory/event_system.md              |
| KI-System (Ollama, Memory, Tools)  | memory/ki_system.md                 |
| Mandarin-Tutor                     | memory/tutor_system.md              |
| Audio (Whisper STT + TTS)          | memory/audio_system.md              |
| Dashboard & Frontend               | memory/dashboard.md                 |
| Tastatur-Belegung (alle Modi)      | memory/tastatur.md                  |
| REST API Endpoints                 | memory/api_endpoints.md             |
| Setup & Installation               | memory/setup.md                     |
| Starten (lokal, 3 Terminals)       | memory/starten.md                   |
| Hardware (Pi, Mikro, PIR)          | memory/hardware.md                  |
| Deployment (Pi, systemd, Kiosk)    | memory/deployment.md                |
| Display-Debug (Pi-Monitor schwarz) | memory/display_debug.md             |
| Dateizugriffe (Whitelist, Ignore)  | memory/datei_zugriffe.md            |
| Claude-spezifische Hinweise        | memory/claude_hinweise.md           |

## Pflege

- Jede Doku-Änderung gehört in das passende Thema-File, nicht ins README.
- Wenn unklar wo etwas hingehört: lieber neues Thema-File anlegen als
  ein bestehendes überladen.
- README und CLAUDE.md verweisen auf diesen Index – sie selbst halten
  nur die Quick-Start-Kurzfassung.
