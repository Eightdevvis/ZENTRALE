# Phone self-update: hardening

**Stand 2026-10-30:** Open, does not wait for Sasha.

1. The release manifest has no own signature yet (trust = own session + SHA-256 + Android's signing check). Add an Ed25519 signature on the manifest (`mobile/lib/update/`, `scripts/publish_phone_app.py`, `cloud/src/phone.ts`).
2. A future Google Play build must have self-update off (already: `zentrale.distribution=play`) AND drop `REQUEST_INSTALL_PACKAGES` from the manifest — Play restricts it.

Doc: `memory/betrieb/phone_app_release.md`.
