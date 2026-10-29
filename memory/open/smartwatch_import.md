# Smartwatch data into ZENTRALE (Xiaomi Smart Band 11)

**Stand 2026-10-29:** Open, **waits for Sasha** (test on the phone). From a
chat on 02.10.2026; Sasha deleted the chat, this file keeps what was open.

**Goal:** the band tracks steps, sleep and heart rate on its own — Sasha has
not logged by hand for a long time. That data should flow into ZENTRALE
automatically (sleep into the sleep graph, `core/graphs.py`).

**Gap in ZENTRALE:** since `f85d005` (14.09.2026) the docs say sleep times
„come from the smartwatch" (`memory/system/dashboard.md`,
`memory/system/event_system.md`), but no code reads watch data. There is no
import yet.

**Route 1 — Gadgetbridge** (open source, no cloud, Android; preferred):

- On 02.10.2026 the Smart Band 11 (released 09.2026) was **not** on the
  [supported list](https://gadgetbridge.org/gadgets/wearables/xiaomi/);
  Smart Band 10 is (since 0.87.0). Codeberg issues could not be checked
  (rate limit) — look for a Smart Band 11 issue and follow it.
- **Test still open:** pair it as „Xiaomi Smart Band 10" (Gadgetbridge
  setting to show unsupported devices, long-press the found device, pick the
  type). Needs the auth key from Mi Fitness first (`encryptKey` in
  `XiaomiFit.main.log`; newer Android may hide that app folder). Put the band
  in „connect new phone" mode and quit Mi Fitness before pairing.
  **Never flash firmware via Gadgetbridge.**
- While paired with Gadgetbridge, Mi Fitness gets nothing — not both at once.
- Data out: Gadgetbridge exports its SQLite database automatically to a
  folder → sync to the laptop → ZENTRALE imports it.

**Route 2 — fallback while Gadgetbridge can't:** Mi Fitness → Android
Health Connect → an export app → ZENTRALE. Automatic. (The Xiaomi account
data export works too, but is manual — only for a one-off look back.)

**Next step:** Sasha tries route 1 and reports whether steps and sleep
arrive. Then: build the importer (pluggable, so the source can switch from
Health Connect to Gadgetbridge later — see „ZENTRALE-Adapter steckbar") and
fix the docs lines above.

**When done:** delete this file and its INDEX line.
