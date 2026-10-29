# Tutor: the tool channel teaches the model the wrong thing

**Stand 2026-10-29:** Open, does not wait for Sasha. Repo:
`Eightdevvis/language-tutor` (the tutor left ZENTRALE on 2026-10-09). Found
18./19.09.2026 by Claude while Sasha tested Ling Ling on the laptop; captured
from the devtool bus, not guessed.

## What happened

Ling Ling **narrated** tool calls instead of making them: her raw output read
`show_thought 用的是「你」这个词，意思是 *du*` next to a real but **empty** call
`show_thought {}`, later `（show_thought 调用）` as plain text, and parameter
lines `meaning: you` / `reading: nǐ` ended up in the subtitle bar and were
spoken aloud. The front now strips those lines (`room.py` `_TOOLLINE_RE`,
`_TOOLPARAM_RE`, `_TOOLJSON_RE`) — **a plaster over the cause**, and Sasha said
so.

## Why it happens (all still true, checked 29.10.)

- The persona prompts name tools **by name inside the prose**
  (`tutor/langs/zh/prompt.md` lines 3/9/13/17, same in `es`/`de` and in
  `langs/PROMPT_TEMPLATE.en.md`), so a tool name is just target-language
  vocabulary in a sentence.
- The few-shot block shows **only text turns, never a tool call** — the model
  has no example of the channel it is supposed to use.
- `es/assessment_prompt.md` even demonstrates tool calls as prose arrows
  (`→ (show_thought «hola» = hallo; …)`) and names dead tools, while the same
  file forbids writing tool names in text. The gate is dead, the file is still
  loaded.
- The contract is soft (`tutor/tools.py`): `execute_tool` has no try/except (an
  exception kills the turn), `express {}` silently returns `"ok"`, an unknown
  tool gets a **German** rejection string, the result of `introduce_new` is
  thrown away, and tool results never enter the history — so next turn she does
  not know she already showed a word.
- The model layer ignores `finish_reason == "length"`: with `max_tokens` 140
  (zh 70) a truncated tool-call JSON fails to parse and is then executed with
  `{}` — the likely source of `show_thought {}`.
- Dead tools still appear in prompts, tool texts, `prompts/tools.md` and the
  front's name list (`mark_known`, `get_confirmed_vocab`, `get_testing_vocab`,
  `increment_correct_use`).

## What to do

Decided with Sasha 19.09.: **reduce the tool set to 8** (`express`,
`show_thought`, `play_music`, `stop_music`, `watch_tv`, `turn_off_tv`,
`get_local_news`, `get_due_reviews`; drop `introduce_new` and the three
sentence-pattern tools from the schema, keep their data and functions). Then:
no tool name in the prose, one generated channel paragraph instead; **few-shot
with real tool calls** per package (`few_shot.json`, translated per provider);
a hard argument check with target-language rejections; no execution on
truncated JSON (retry the round with a bigger cap); a short tool note in the
history; dead tools out everywhere and `prompts/tools.md` generated from the
contract.

Full plan (written 19.09., never executed):
`~/.claude/plans/gut-jetzt-lass-uns-pure-castle.md`, steps 1 and 2. Related:
[tutor_behaviour_bench.md](tutor_behaviour_bench.md) — without the bench such a
fix cannot be proven.
