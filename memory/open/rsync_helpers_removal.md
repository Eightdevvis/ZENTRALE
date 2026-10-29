# Remove the old rsync helpers

**Stand 2026-10-29:** Open, **waits for Sasha.** The rsync helpers in
`~/.local/bin` are the old way of syncing. They go once Sasha has switched to
the Mitte. Found by Claude.

## What

In `~/.local/bin` (not in the repo — and they should not be pulled in):
`zentrale-sync` (with the links `zentrale-pull` and `zentrale-push`),
`zentrale-push-data`, `zentrale-sync-boot`. Checked 29.10.: all still there.

## Order

1. Sasha switches to the Mitte himself — steps in
   [../betrieb/abgleich.md](../betrieb/abgleich.md), section
   „Übergang vom rsync-Weg".
2. Then delete the helpers and anything that still starts them
   (e.g. `zentrale-sync-boot` at boot — check autostart/systemd on each node).
3. Update the docs that still call rsync the default (`CLAUDE.md`,
   [../system/topologie.md](../system/topologie.md)).
