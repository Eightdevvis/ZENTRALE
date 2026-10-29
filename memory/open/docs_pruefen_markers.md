# Docs: `⚠ prüfen` markers nobody has answered yet

**Stand 2026-10-29:** Open, partly waits for Sasha. Left behind on 18.09.2026
when the whole `memory/` tree was reworked onto `memory/doku_regeln.md` (commits
`56b4684`…`08c3760`): wherever a sentence contradicted the code or another file
and could not be settled from the code, the agent wrote `⚠ prüfen:` instead of
guessing — exactly as rule 5 of the doc rules demands. Nobody has gone through
them since.

Eleven real markers (two further hits are the rule itself in
`doku_regeln.md`/`claude_hinweise.md`, one is a code example in
`hub/app_motor_plan.md`):

| File | Question | Who can answer |
|---|---|---|
| `betrieb/hardware.md` | Is the noise sensor from 02.06. still attached? Board pin 7 now carries the (unattached) PIR | Sasha |
| `betrieb/systemeinheit.md` | Is the system unit actually set up on the PC? | Sasha |
| `betrieb/display_debug.md` | Does the 1920×1080 layout problem of the browser kiosk still apply? | code/test |
| `system/anwesenheit_und_ring.md` | Should PIR hits feed `anwesenheit.da()`? Today they only reach the tutor room | Sasha |
| `system/dashboard.md` | Does the `lifestyle` box still point at `sleep_quality` (sleep comes from the watch)? | code |
| `ki/cloud_bericht.md` (2×) | Same system-unit question, and which cloud model is current — the doc says `claude-opus-5`, the report Sonnet 5/Haiku 4.5, the code default `claude-sonnet-5`; truth is in `data/ai_config.json` | code + Sasha |
| `ki/ki_personality_plan.md` | Is the fine-tuning path still pursued after the cloud switch? | Sasha |
| `werkzeuge/mail_system.md` | Is `MAIL_DRY_RUN=0` set in operation? | Sasha |
| `werkzeuge/news_system.md` | News moderation still talks to Ollama directly — re-bench or move to the cloud core? | Sasha |
| `claude_hinweise.md` | The rule "done means: in ALL fronts" vs. "browser fronts given up" — never decided | Sasha |
| `hub/app_motor_plan.md` | Check the current wording of the store rules before the first release | Sasha |

Each answer is one line of work: settle it, then delete the marker in the same
commit. The ones marked "code" can be checked without Sasha.
