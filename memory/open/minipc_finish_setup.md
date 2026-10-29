# Mini-PC: finish the setup

**Stand 2026-10-30:** Open, **waits for Sasha** (on the Mini-PC). Installed and
logged in on 24.10.2026; data arrived except calendar and KI keys at that time.

1. `zentrale update` (newest release in the cloud is 41).
2. `zentrale timers install` → `zentrale timers` shows both ok.
3. Optional for the Google bridge: install `vdirsyncer` with pacman (only
   matters if the calendar source is Google; today it is `zencloud`).
4. Restart ZENTRALE once so the backend picks up the AI keys from the Adapter.
5. Check: `zentrale status`, chat answers, calendar shows events, no false
   "neues in einem anderen Gespräch".

Device: `memory/betrieb/mobiler_knoten.md`.
