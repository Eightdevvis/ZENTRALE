# Sprach-Tutor — ausgezogen

Seit 2026-10-09 ist der Sprach-Tutor ein **eigenes Programm** im Repo
`language-tutor` (liegt neben ZENTRALE, GitHub `Eightdevvis/language-tutor`)
und die erste App nach dem Hub-Bauplan ([../system/hub_bauplan.md](../system/hub_bauplan.md)).
Seine ganze Doku ist mitgezogen und liegt dort unter `docs/` (Einstieg
`docs/INDEX.md`; Bauplan, Verhalten, Persona-Tuning, Zimmer, Diagnose 08.10.).
Die Geschichte der Dateien ist dort erhalten.

Was in ZENTRALE vom Tutor bleibt:

| Was | Wo |
|---|---|
| Die App finden, ihr Manifest `app.toml` lesen | `core/apps.py` (Einstellung `app_pfad_tutor`, Standard `../language-tutor`) |
| App starten: Stimm-Dienste, Tutor-Server, Zimmer | `scripts/open_tutor_room.py` (Taste `u`, `/tutor`, Pi-Wandbild) |
| Ereignis „anwesenheit" an die App | `core/hub_ereignisse.py` (aus `core/brain.py`) |
| Das Zimmer auf dem Pi | `deploy/aussenposten.txt`, Einträge `app:tutor/…` → `apps/tutor/` im Paket |
| Stimm-Dienste (Whisper, TTS) | `services/` — gehören weiter dem Hub, der Tutor kennt nur ihre Adresse |

Alte Verweise in dieser Doku auf `memory/tutor/…` meinen die Dateien, die
jetzt im Tutor-Repo unter `docs/` liegen.
