# KI budget for October and the default model

**Stand 2026-10-29:** Open. **Waits for Sasha** (raise the October budget or
wait for November; model choice).

- **Prices fixed** in `core/prices.py` (9e920d7): Sonnet 5 costs $2/$10;
  Sonnet 5.5, Opus 5.5 and Haiku 5.5 added with tiers. Costs already booked in
  `data/ai_usage.json` were deliberately not rewritten: real October chat
  ~7.50 €, booked 10.17 €. So the fallback to qwen stays on until month end
  (B-05 in [../ki/bibel/baustellen.md](../ki/bibel/baustellen.md)).
- **Decide:** raise the October budget, or wait for November.
- **Proposal:** default Sonnet 5.5, fallback Haiku 5.5 instead of qwen. The
  fallback in `core/ai_backends.py` (`cloud_provider` ~54, `budget_lage` ~458)
  only switches the provider, not the model — needs a small change. Haiku 5.5
  with the German tool prompt is unmeasured.
- **EU-hosted option:** Mistral Large 4 ($1.36/$4.18), tool use unproven.
- **Missing:** `claude-fable-5-1` is not in `core/prices.py` (only
  `claude-fable-5`).
- **Cost per turn:** Sonnet ~0.09 €, qwen ~0.04 € (qwen needs ~5 calls per
  turn).
- If the subscription route is built ([claude_max_assistant.md](claude_max_assistant.md)),
  this question is partly settled.

Models and providers: [../ki/anbieter_modelle.md](../ki/anbieter_modelle.md).
