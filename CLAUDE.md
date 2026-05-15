# ZENTRALE – Entwicklungshinweise für Claude

Event-getriebenes Dashboard (Raspberry Pi + Linux-PC), vollständig
offline. KI läuft lokal via Ollama (Default-Modell: qwen2.5:14b, per
`OLLAMA_MODEL` umstellbar).

## Wo die Doku liegt

Die gesamte Projekt-Doku ist modular nach Thema abgelegt im Ordner
`memory/`. Einstieg ist immer das Inhaltsverzeichnis:

→ **`memory/INDEX.md`**

Statt das ganze README/diese Datei zu lesen: über den Index gezielt
das Thema öffnen, das gerade gebraucht wird – das spart Tokens und
hält die Antworten fokussiert.

## Schnell-Zeiger nach Thema

| Was du wissen willst                      | Wo es steht                          |
|-------------------------------------------|--------------------------------------|
| Was ist ZENTRALE, aktueller Stand         | `memory/ueberblick.md`               |
| Wer läuft wo (PC ↔ Pi)                    | `memory/topologie.md`                |
| Threads, Datenfluss, Modul-Übersicht      | `memory/architektur.md`              |
| Sensoren, Events, Brain, Actions          | `memory/event_system.md`             |
| Ollama, Memory, Tools, Net-Logging        | `memory/ki_system.md`                |
| Mandarin-Tutor (pausiert)                 | `memory/tutor_system.md`             |
| Whisper STT + TTS, Audio-Architektur      | `memory/audio_system.md`             |
| Dashboard-UI, Modi, Polling               | `memory/dashboard.md`                |
| Tastatur in jedem Modus                   | `memory/tastatur.md`                 |
| REST API                                  | `memory/api_endpoints.md`            |
| Setup, Dependencies, Modelle              | `memory/setup.md`                    |
| Starten (3 Terminals, Env-Vars)           | `memory/starten.md`                  |
| Hardware (Pi, Mikro, PIR, GPIO)           | `memory/hardware.md`                 |
| Deployment (rsync, systemd, Kiosk)        | `memory/deployment.md`               |
| Whitelist, .gitignore-relevantes          | `memory/datei_zugriffe.md`           |
| Architektur-Entscheidungen für Claude     | `memory/claude_hinweise.md`          |

## Pflege

- Jede strukturelle Änderung (neue Module, umbenannte Dateien, neue
  Features) → das passende `memory/`-File aktualisieren **und** den
  Index prüfen.
- Inhalte gehören in die Theme-Files, nicht in diese Datei.
- Bei Umbenennungen: alle Stellen mitziehen, sonst tote Referenzen
  in der Doku.
