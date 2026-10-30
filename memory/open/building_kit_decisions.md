# Building kit: what is still open

**Stand 2026-10-30:** Open, **waits for Sasha** (two items). Blueprint:
[../hub/building_kit_plan.md](../hub/building_kit_plan.md). Questions 1–8 and
10 were answered on 30.10. and are written into the blueprint (support forever,
setup wizard, version sync settable in Schematix, name Schematix, things as
hardware pieces, Tailscale live).

1. **Schematix look:** Sasha sends a style. Needed before build step 13.
2. **Key rotation when a device is removed** (re-encrypt everything with a
   new account key) — Sasha: "idk". Proposal: not on every removal (costly,
   all devices must log in again); only as an option in the removal dialog,
   "device lost or stolen? → also change the key". Build it after step 8.
