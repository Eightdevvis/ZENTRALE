# Cloud: what can still identify a user

**Stand 2026-10-30:** Open, does not wait for Sasha (decide case by case).
From the anonymous-accounts build, 23.10.2026 (`memory/betrieb/cloud.md`).

- `codes.verbraucht_von` links an invite code to its account, and
  `verbraucht_am` equals `konten.erstellt` — whoever handed out the code knows
  whose account it is.
- Device names (usually the hostname) are stored in `sitzungen` and the
  device list in plaintext.
- The usage meter writes one D1 row per request (eats into the 100k daily
  write limit).
- Bridge lease compares the clocks of two devices; drift shortens it.
- Cloudflare itself sees client IPs at the edge (not fixable on our side).
