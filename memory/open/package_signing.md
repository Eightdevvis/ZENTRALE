# Sign our own packages before ZENTRALE goes public

**Stand 2026-10-31:** Open, does not wait for Sasha (decided: later, but
before going public). Sasha, 31.10. (answers to the step-4 plan): signature
comes later; each source checks its own trust (apt and Flatpak already
sign), **our own packages** get a signature before ZENTRALE goes public.

- **What:** an Ed25519 signature over the sha256 of every package we
  publish — the ZENTRALE core package (`scripts/paket_bauen.py`,
  `server/src/paket.ts`), our app packages (`zentrale-package` source,
  [../hub/app_delivery_plan.md](../hub/app_delivery_plan.md) build step 16)
  and the phone release manifest
  ([phone_self_update_hardening.md](phone_self_update_hardening.md)) — one
  key system for all three.
- **Today:** sha256 over HTTPS from our own cloud only.
- **Done when:** a tampered package is refused on install and update;
  unsigned packages only in dev mode; key handling written down.
- Belongs on the list in [release_before_public.md](release_before_public.md).
