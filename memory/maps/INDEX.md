# Karte — ausgezogen

Seit 2026-10-22 ist die Weltkarte ein **eigenes Programm** im Repo
`zentrale-karte` (liegt neben ZENTRALE) und die zweite App nach dem
Hub-Bauplan ([../hub/hub_bauplan.md](../hub/hub_bauplan.md)), nach dem
Sprach-Tutor. Ihre ganze Doku ist mitgezogen und liegt dort unter `docs/`
(Einstieg `docs/INDEX.md`: Layer-Architektur `maps_system.md`, Quellen-Charta
`maps_quellen.md`, Design-Brief `maps_design_brief.md`). Die Geschichte der
Dateien ist dort erhalten.

Was in ZENTRALE von der Karte bleibt:

| Was | Wo |
|---|---|
| Die App finden, ihr Manifest `app.toml` lesen | `core/apps.py` (Einstellung `app_pfad_karte`, Standard `../zentrale-karte`) |
| Den Karten-Server mit dem Backend starten (`autostart = true`) | `core/app_verwaltung.py` (aus `core/main.py`) |
| `/api/map/*` unverändert an die App reichen (`routen = ["/api/map"]`) | `core/app_weiterleitung.py`, `ui/routen/hub_apps.py` |
| Die Karten-Ansicht der TUI (Taste `m`, ruft nur `/api/map/*`) | `tui/ansichten/karte.py` |
| Das Fenster aus der TUI (Taste `w`) | `scripts/open_app_window.py karte …` → `[ansicht.fenster]` der App |

Alte Verweise in dieser Doku auf `memory/maps/…` oder `core/map/` meinen die
Dateien, die jetzt im Karten-Repo unter `docs/` bzw. `karte/map/` liegen.
