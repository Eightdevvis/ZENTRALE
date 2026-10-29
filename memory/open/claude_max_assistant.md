# Assistant via Sasha's Claude Max subscription (Claude Agent SDK)

**Stand 2026-10-29:** Planned, nothing built. **Waits for Sasha** (okay for
the first step, the measuring script). Decided by Sasha on 26.10.2026: only
for him personally, never in the store. Shared limits with his own Claude Code
use are fine; the assistant may see the usage.

## Blueprint

- **Variant A (ZENTRALE drives the loop) does not work:** Claude Code always
  runs tools itself.
- **Variant B (chosen):** ZENTRALE tools as an in-process MCP server
  (`create_sdk_mcp_server`). Every handler calls
  `core/werkzeug_schleife.py` `run_tool` (~320), so gate, approval button and
  checker log stay as they are.
- **New module** `core/cloud_claude_code.py` with the same `chat_stream`
  signature as `core/cloud.py` (~616) / `core/cloud_openai.py` (~223). The SDK
  runs in a thread with its own event loop, plus a queue to the caller.
- **Checker:** after the result run `nach_antwort` (`core/ehrlichkeit.py`
  ~799); a finding goes back as a new user message into the same session.
  `max_turns = runden_grenze()` (`core/ai_backends.py` ~395). Stop via
  `interrupt()`.
- **New session per turn**, built from `verlauf_fuer_ki`
  (`core/gespraeche.py` ~446), because conversations are synced between nodes.
- **System prompt is frozen per session:** only the fixed head goes into the
  system prompt; the changing block (`_volatile_text`, `core/cloud.py` ~381)
  goes with the message.

## Shielding (Sasha's private Claude Code setup must not leak in)

- `cwd` is an empty folder **outside** `~/codicus` — CLAUDE.md is also read
  from parent folders.
- `setting_sources=[]`; replace the system prompt completely.
- Built-in tools off; strict MCP config so the claude.ai connectors stay out.
- `can_use_tool` rejects everything that is not `mcp__zentrale__*`
  (`allowed_tools` only allows, it does not restrict).
- No session persistence (downside: ccusage does not see the assistant).
- Auto-memory: unclear whether it is off — verify.
- **Proof:** inspect the init message, and put a test sentence into
  `~/.claude/CLAUDE.md` that must never show up in an answer.

## Fallback when the subscription limit hits

- Detect by error text; capture the real text first (not known yet).
- `abo_gesperrt_bis` as step 0 in `cloud_provider()` (`core/ai_backends.py`
  ~54), then API (`claude`) or qwen.
- Retry only if no writing tool has run yet in that turn.
- Usage via ccusage (`~/.local/bin/ccusage`, active 5-hour blocks as JSON,
  cached 60 s): a line in the prompt from ~70 %, plus a tool `abo_auslastung`.

## Provider and scope

- New provider `claude_abo`, kind `claude_code`, default model sonnet,
  booked at 0 € with the real tokens.
- Background runs (`core/takt.py`) stay on API / qwen, setting `takt_anbieter`.
- **Privacy (Grundpfeiler):** whether data is used for training depends here on
  Sasha's claude.ai setting — **Sasha checks it.**
- **Terms:** third-party products may not offer the claude.ai login. Personal
  use is not explicitly covered — so never in the store, never on other
  accounts.
- **Phone:** works as a node through the core; the machine running Claude Code
  must be on, otherwise the core's fallback applies.

## Next

1. **First step (needs Sasha's okay):** `scripts/claude_abo_messung.py` —
   time to init, to first token and to end; checks the shielding; calls one
   read tool via MCP; checks `apiKeySource`.
2. Then steps 1–7 behind the switch `claude_abo` (default off).
3. Bible: entries touched are W-07, W-08, W-12, W-13, KT-04, KT-05, D-02,
   D-03, PR-07–PR-09, B-05, P-05 ([../ki/bibel/README.md](../ki/bibel/README.md)).
   New entries needed for shielding, subscription limit and terms. Update
   [../ki/anbieter_modelle.md](../ki/anbieter_modelle.md).

Related: budget and model choice [ai_budget_model_choice.md](ai_budget_model_choice.md)
(partly answered if this gets built).
