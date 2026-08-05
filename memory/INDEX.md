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
| Topologie (PC ↔ Pi, wer macht was) | memory/topologie.md                 |
| Gesamt-Architektur & Threads       | memory/architektur.md               |
| Event-System (Sensoren → Actions)  | memory/event_system.md              |
| KI-System (Ollama, Graph-Memory)   | memory/ki_system.md                 |
| Kalender-System (Layer, Termine)   | memory/kalender_system.md           |
| Morgen-Messenger (Deckel auf → Fenster) | memory/morgen_messenger.md     |
| Zyklus/PMS-Rechner (»periode«-Graph)| memory/zyklus_pms.md               |
| News-System (Tagesschau, Briefing) | memory/news_system.md               |
| Mail-System (IMAP-Triage, Keymap)  | memory/mail_system.md               |
| Notizen-System (Blöcke: text/list/float) | memory/notizen_system.md      |
| Maps-System (Layer-Karte, 3 Achsen)| memory/maps_system.md               |
| Maps Design-Brief (Look-Handoff)   | memory/maps_design_brief.md         |
| Maps Quellen-Charta (Layer→Quelle) | memory/maps_quellen.md              |
| Memory-Plan v2 (Historie, A–G)     | memory/ki_memory_plan.md            |
| Personality-Plan (Fine-Tuning)     | memory/ki_personality_plan.md       |
| Logic-Loop (Action-Scaffold, WIP)  | memory/logic_loop_plan.md           |
| Grounding-Recherche (nicht raten)  | memory/grounding_recherche.md       |
| Bench-History (Testdaten + Protokolle) | memory/bench_history.md         |
| Sprach-Tutor (eigenes Projekt in tutor/, Sprach-Framework) | memory/tutor_system.md |
| Audio (Whisper STT + TTS)          | memory/audio_system.md              |
| Dashboard & Frontend               | memory/dashboard.md                 |
| UI-Schnittstellen (DOM/JS-Hooks)   | memory/ui_hooks.md ⚠ **VERALTET** (beschreibt das gelöschte `index.html`, kein Hook stimmt noch) → nimm `dashboard.md` |
| Tastatur-Belegung (alle Modi)      | memory/tastatur.md                  |
| REST API Endpoints                 | memory/api_endpoints.md             |
| Setup & Installation               | memory/setup.md                     |
| Starten (lokal, 3 Terminals)       | memory/starten.md                   |
| Hardware (Pi, Mikro, PIR)          | memory/hardware.md                  |
| Deployment (Pi, systemd, Kiosk)    | memory/deployment.md                |
| Display-Debug (Pi-Monitor schwarz) | memory/display_debug.md             |
| Sicherheit (Bedrohungsmodell, LUKS)| memory/sicherheit.md                |
| Browser (Brave-Theme, Terminal-Browsing, Tor) | memory/browser.md        |
| Remote-LUKS-Unlock (Dropbear)      | memory/auto_unlock.md               |
| Dateizugriffe (Whitelist, Ignore)  | memory/datei_zugriffe.md            |
| Claude-spezifische Hinweise        | memory/claude_hinweise.md           |

## Pflege

- Jede Doku-Änderung gehört in das passende Thema-File, nicht ins README.
- Wenn unklar wo etwas hingehört: lieber neues Thema-File anlegen als
  ein bestehendes überladen.
- README und CLAUDE.md verweisen auf diesen Index – sie selbst halten
  nur die Quick-Start-Kurzfassung.
