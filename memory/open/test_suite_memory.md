# Measure the test suite's memory use

**Stand 2026-10-29:** Open, **waits for Sasha — he measures it himself**,
alone, when nothing else is running. Found by Claude.

## Why

The laptop has 3.7 GB RAM. Earlier aborts of the suite came from several
suites running in parallel (several agents at once). Nobody knows how much a
single full run needs, so nobody can say how many may run side by side.

## What to find out

- Peak memory of one full run, on the laptop, nothing else open.
- Whether single test files stand out (PTY/TUI tests are suspects).
- Result goes into [../betrieb/tests.md](../betrieb/tests.md); this file is
  deleted in the same commit.
