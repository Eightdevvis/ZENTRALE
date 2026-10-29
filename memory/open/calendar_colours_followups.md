# Calendar colours: migration and full test run

**Stand 2026-10-30:** Open, partly waits for Sasha.

1. **Migrate the course table (waits for Sasha):** restart the ZENTRALE backend on the laptop. On the next `/api/calendar` answer the old table `~/.local/state/zentrale/kalender_farben.json` (25 entries) moves once into `data/calendar_colours.json`; the old file stays with a `.migrated` marker. A dry run on a copy kept all 25 slots. Then check that TUI colours look as before and that the phone gets the table via the Mitte.
2. **Full Python suite not run** after `fff210d`/`a70e851`: it was stopped for low memory after 411 passing tests. Targeted tests and all 170 Dart tests are green. Run the full suite once with enough free RAM (see [test_suite_memory.md](test_suite_memory.md)).
3. Day-view preview PNGs of the colour change were rendered but never looked at (`flutter test` writes them to `mobile/build/kalender_vorschau/`).

Code: `core/calendar_colours.py`, `core/calendar_palette.json`, `mobile/lib/kalender/colours.dart`; doc `memory/werkzeuge/calendar_colours.md`.
