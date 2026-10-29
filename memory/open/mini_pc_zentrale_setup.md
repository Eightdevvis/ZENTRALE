# Mini-PC: ZENTRALE not set up yet, cloud folder not active

**Stand 2026-10-30:** Open. **Waits for Sasha** (login with the account from
KeePass).

- On the mini, `~/zentrale` only holds `install.sh`; ZENTRALE itself is not
  installed, so the cloud sync does not run there.
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
