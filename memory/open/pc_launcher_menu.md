# PC: `zentrale` still points to the removed cassette menu

**Stand 2026-10-29:** Open, not verified — the PC was offline when this was
filed. Found in the cleanup session of 04.10.2026 (cassettes removed,
commit `c52f1e1`).

- `~/.local/bin/zentrale-launch` is **not in git**, every node has its own copy.
  On the laptop it was fixed on 04.10.: `zentrale` and `zentrale-tui` both run
  the boot sync and then `scripts/start_tui.sh`; the `zentrale-laptop` symlink
  is gone.
- On the PC the old copy probably still runs `scripts/select_kassette.sh`
  for `zentrale` and `scripts/start_laptop.sh` for `zentrale-laptop`. Both
  scripts were deleted on 04.10. → `zentrale` on the PC fails.
- To do when the PC is reachable: check its `zentrale-launch`, make it match
  the laptop copy, remove a leftover `zentrale-laptop` symlink. Same question
  for the Pi, if it has the launcher.
- The PC backend itself is fine: `zentrale-pc.service` sets no
  `ZENTRALE_LOKALE_KI`, so local AI stays on there as before.

Waits for Sasha: no (needs the PC online).
