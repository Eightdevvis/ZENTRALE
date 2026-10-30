# Building kit: decisions for Sasha

**Stand 2026-10-30:** Open, **waits for Sasha**. From the blueprint
[../hub/building_kit_plan.md](../hub/building_kit_plan.md) (plugs, no forced
updates, packages, node lifecycle, wiring map with Run). Each answerable in
one line. The proposal is in brackets.

1. Support window: how long do old versions keep syncing? (12 months after the successor ships)
2. Auto-update: a setting per node (frame), default on? (yes, per node, so the Pi kiosk can be frozen)
3. Linger: ask at install to keep timers running while logged out? (yes, ask once, default yes)
4. Apps: update automatically with the bundle, with a per-app hold? (yes)
5. When updates run: daily with a random delay, or right after a release? (daily, random up to 1 h)
6. Versions no longer sync between nodes (answers question 6 of app_motor_plan.md with "no"). OK? (yes)
7. Name of the wiring-map app: code `wiring`, UI name? ("Schaltplan")
8. Physical things (router, cables, power bank) stored as data of the map app. OK? (yes)
9. Device removal: also rotate the account key (re-encrypt everything), now or later? (later, own item)
10. Tailscale in use or planned next to the WireGuard plan in heimnetz.md? (layer exists either way)
