# Tool search: stays off, follow-ups before a new test run

**Stand 2026-10-29:** Open, does not wait for Sasha except for the test-run
budget. Switch `werkzeug_suche` (default off), step 9 built in 0446ae5
([../ki/werkzeug_suche.md](../ki/werkzeug_suche.md)).

## Test bench 23.10.2026, qwen-plus

- m01, search off: 4/4, 5 calls, 0.03 €.
- m01, search on: 4/4, but 111 calls, 0.60 €, 259 s. On a calendar task qwen
  drifted into a web search (LMU instead of Uni Saarland), repeated
  `web_search` dozens of times and stopped only at the 100-round limit.
- m02–m04, search on: 2/2, 2/2, 2/3.
- Result: search stays off.

## To do

1. Lower the per-turn round limit from 100 to ~20–25
   (`STANDARD_RUNDEN`, `core/ai_backends.py` ~392, `runden_grenze` ~395) and
   add a guard against identical repeated calls.
2. Phrase the research rule so it does not fire on calendar tasks.
3. New test run, cases one by one (cost).
4. Update bible W-09 with this finding
   ([../ki/bibel/werkzeuge.md](../ki/bibel/werkzeuge.md)).

## Budget

Test-bench pot October ~10.60 € of 5 € (booked before the price fix).
`--trotz-budget` needs Sasha's approval, and Claude Code's permission check
blocks it for agents.
