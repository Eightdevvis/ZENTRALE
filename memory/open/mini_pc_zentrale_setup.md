# Mini-PC: installed but silent, cloud folder not active

**Stand 2026-10-30:** Open. **Partly waits for Sasha** (on the mini).

- **Correction (checked read-only 2026-10-30):** ZENTRALE *is* installed —
  by the cloud installer on 24.10. into `~/.local/share/zentrale/hub/{38,39}`,
  `aktuell -> 39`, logged in (`~/.config/zentrale/konto.json`). It synced
  once (24.10. 10:17) and never again: no timers (they came with release
  41), no linger, no auto-update. Finishing steps:
  [minipc_finish_setup.md](minipc_finish_setup.md); the lasting fix:
  [../hub/building_kit_plan.md](../hub/building_kit_plan.md) (sections 0, 5.2).
- **Cloud folder** (`~/Zentrale/Cloud`, app `cloud_folder`, merged 29.10. in
  `49a06dd`): activate on the laptop and on the mini with `zentrale sync` and
  answer yes once (old app selections do not include it).
- The university folder `uds` was only **copied** to the mini
  (`~/Downloads/uds`, 32 MB). Once the cloud folder runs on both, move it in
  there so it syncs instead of drifting apart.
- **Claude Code sessions:** all 304 laptop sessions were copied to the mini's
  `~/.claude/projects/` (nothing overwritten; memory merged, laptop-only
  entries marked `[Laptop]`). Sessions of repos resume only when the repo sits
  at the same path on the mini (`/home/sasha/codicus/...`); the mini has no
  `~/codicus` yet.
- A file manager must be installed and set as default for folders on sway, or
  the cloud icon cannot open the folder.
