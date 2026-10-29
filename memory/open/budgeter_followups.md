# Budget app (budgeter): follow-ups

**Stand 2026-10-29:** Open, partly waits for Sasha (look and feel). App repo
`~/codicus/budgeter` (`Eightdevvis/budgeter`, `ebe311f`), built 25.10.2026.
Data lives in `~/.local/share/budget/`, not in the repo.

- **German code:** identifiers, modules (`kern.py`, `regeln.py`, …) and UI
  text are German and hard-coded. Under the English rule (CLAUDE.md,
  29.10.2026) the app needs renaming to English and its UI text moved into a
  `gettext` table. Was built before the rule.
- **No import:** only JSON/CSV export; no bank-statement CSV import.
- **No negative correction:** a cash difference has to be booked as an
  expense; a real balance correction is missing.
- **Confusing total:** the overview line „Monatsbudgets gesamt" also contains
  minus remainders of old months that were never filled. Correct, but unclear.
- **TUI is slimmer:** places, categories and fixed costs can only be created
  in the browser view.
- **Look:** colours and spacing are a first pass (CSS variables in
  `budget/static/style.css`); waits for Sasha to decide.
