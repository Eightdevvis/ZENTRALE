# Docs tests: no hook, main goes red

**Stand 2026-10-29:** Open. Agents change `memory/` and do not run the docs
tests, so `main` turns red unnoticed. Nothing in the repo runs them on commit
(no `core.hooksPath`, no pre-commit hook). Found by Claude; does not wait for
Sasha.

## Evidence

- **12.10.2026** — commit `0ec988a` pushed `system/dashboard.md` over its
  limit in the giant-files table of [../doku_regeln.md](../doku_regeln.md).
- **29.10.2026** — `tests/test_memory_groesse.py` is red on `main`:
  `werkzeuge/kalender_ansichten_vorschau.md` shrank to 602 lines (last touched
  in `fff210d`), the table still said 604; lowered to 602 on 29.10.

## Idea

- A hook in the repo (e.g. a `.githooks/` folder, enabled via
  `core.hooksPath`) that runs `tests/test_memory_*.py` when a commit touches
  `memory/`. Fast — these tests do not start the whole suite.
- One line in `CLAUDE.md` (Pflege) so every agent knows the hook exists and
  must not be skipped.
- Note: `core.hooksPath` is a local git setting, so each checkout/node has to
  enable it once — say so in the line.
