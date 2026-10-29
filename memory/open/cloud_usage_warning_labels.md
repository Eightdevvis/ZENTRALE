# Cloud usage warnings: say "money" or "outage", brake all R2 limits

**Stand 2026-10-30:** Open, does not wait for Sasha. Promised to Sasha on
23.10.2026, not built. Found by Claude (session 6e7db12f).

Sasha: the warnings must tell him exactly when he might pour money into
Cloudflare. On Workers Free only **R2** costs money above the free tier
(10 GB storage, 1M Class A, 10M Class B per month); Workers and D1 just stop
until the next UTC day.

- Each warning line (`zentrale status`, start of `zentrale`, `zentrale cloud
  usage`) says **money** (R2 limits) or **outage** (Workers, D1).
- The brake (`BREMSE_SPEICHER`, today only R2 storage → 507 `speicher_voll`)
  also covers R2 Class A and Class B ops before 100 %.

Where: `server/src/nutzung.ts`, `server/src/grenzen.ts`, `zentrale_cli/texte.py`,
`memory/betrieb/cloud.md`.
