# Building kit steps 7 and 8: what is left after the build

**Stand 2026-10-30:** Open. Found while building steps 7 and 8 (`6924069`,
[../hub/building_kit_plan.md](../hub/building_kit_plan.md)). Item 1 **waits
for Sasha** (deploy).

1. **Server deploy** — the cloud does not know the new routes until Sasha
   deploys: D1 migration `server/migrations/0004_insecure.sql`, then the
   Worker (`DELETE /v1/knoten/{name}`, `PUT /v1/konto/schluessel`, headers
   `Deprecation`/`Link`). Until then `zentrale leave` only logs out (and
   says the device still shows in `devices`) and `devices remove` fails with 405.
2. **Phone app** (`mobile/`): no `device_removed` text yet (shows the server
   sentence), no `Zentrale-Release` header (the phone is never warned as
   insecure), and after a key change it must be logged in again by hand.
3. **Removed device's network keys**: knoten_beitritt.md says its public
   key leaves router and `authorized_keys` — not built (no router yet).
4. **Old stands after a key change** stay on the server (encrypted with the
   old key, readable only with a session); `besitz` is not re-encrypted
   (no client uses it yet). A purge of old stands would close that.
5. **Schematix** shows `insecure` and tombstones once it exists (build step 13).
