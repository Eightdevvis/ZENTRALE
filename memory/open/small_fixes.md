# Small fixes

**Stand 2026-10-29:** Open. Small stale spots, each checked on 29.10.2026 and
still there. Found by Claude. One commit per fix is fine; strike the line
here when done, delete the file when the list is empty.

| Where | What is stale |
|---|---|
| `core/ai.py`, docstring around line 153 | names `tutor.tools.tools_for` / `tutor.tools.execute_tool` — the tutor moved to its own repo on 09.10. |
| `.gitignore`, comment lines 63–64 | point to `tutor_system.md` under `memory/` (gone) and `tutor/data/<lang>/` |
| `tui/ansichten/rad_wahl.py`, `_shop` (line 37) | fallback text „shop kommt gleich" — `tui/ansichten/shop.py` exists now; also hard-coded UI text (CLAUDE.md: translation table) |
| `tests/test_openapi.py`, module docstring | lists `/api/kachel*`, `/api/desk*`, `/api/shop*` but not `/api/werkstatt`, `/api/tasten`, `/api/apps` (all in `PRAEFIXE`) |
| `language-tutor/.gitignore` (other repo) | no `.claude/` entry |
| [../system/INDEX.md](../system/INDEX.md), section „Stand der Fronten" | content in an index — breaks rule 7 of [../doku_regeln.md](../doku_regeln.md); move into a topic file |
| [../system/takt.md](../system/takt.md), `core/takt.py` | the word „Takt" confuses Sasha; rename open — **waits for Sasha** (name choice) |
