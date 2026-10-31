# Pi: look at what really runs there

**Stand 2026-10-31:** Open, **waits for Sasha** (he wants to look at it
himself: "pi is mittlerweile bisschen verwildert").

- Since `ee2e519` other devices need the access key. The Pi's TUI, room view
  and sensor bridge send it once the key file is on the Pi
  ([../betrieb/zugang.md](../betrieb/zugang.md), step 4); unknown whether it
  is there.
- Browser kiosk mode (not the default "room") sends no key: needs a new
  browser link every 30 days.
- No key distribution when a node joins; the Pi has no `core/`, so the vault
  does not help there.
