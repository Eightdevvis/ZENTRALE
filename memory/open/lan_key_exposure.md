# API keys were readable from the LAN — rotate?

**Stand 2026-10-30:** Open, **waits for Sasha**. Until commit `a4c4872`
(22.10.2026) `GET /api/data/ai_config` returned the API keys to anyone in the
home network (backend on `0.0.0.0`, access mode „melden"). The keys now live
encrypted in the Adapter (`memory/hub/adapter.md`).

Decide: rotate the Anthropic and Dashscope keys (only reachable from the own
network/hotspot, so low risk).
