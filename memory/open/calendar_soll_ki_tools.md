# Calendar: KI tools don't know the "Soll" time of deadlines

**Stand 2026-10-29:** Open, does not wait for Sasha. Found by the KALENDER session.

**What:** Since `c0b1368` (24.10.2026) deadlines carry `soll_abstand` (minutes ≤ 0, or text like `-2d18h`; `""` removes it; .ics `X-ZENTRALE-SOLL`). TUI key `S` and the routes (`POST /api/calendar/typ`, routine/entry PUT) support it. The KI side does not: `core/ki_kalender_adapter.py` (~line 108–135, `_typ_args`) only passes `typ` and `vorwarnung`, and the KI tool schemas have no `soll_abstand` field. So the assistant cannot set or read the Soll time.

**To do:** add `soll_abstand` to the calendar tool schemas and the adapter (core functions `add_entry`/`add_routine`/`eintrag_aendern`/`routine_aendern`/`typ_setzen` already accept it; error codes `SOLL-UNGUELTIG`, `SOLL-NACH-MUSS`). Read `memory/ki/bibel/README.md` first (tool descriptions). Docs: `memory/werkzeuge/kalender_deadline.md`.
