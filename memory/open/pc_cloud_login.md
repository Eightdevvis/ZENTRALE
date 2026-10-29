# PC (pop-os) still syncs over rsync

**Stand 2026-10-30:** Open, **waits for Sasha** (PC must be on). Since
23.10.2026 the laptop syncs via the cloud; the PC never logged in.

On the PC: `zentrale update`/`git pull`, `zentrale setup` → log in as `sasha`,
`zentrale timers install`, remove the boot-sync unit from `zentrale-pc.service`
(`memory/betrieb/abgleich.md`, „Übergang vom rsync-Weg"). Until then don't
work on laptop and PC at the same time.

Also decide (Sasha): the old backup timer `zentrale-sicherung.timer` and the
backup branches `knoten/<rechner>` in the private data repo are **plaintext**
on GitHub (`memory/betrieb/datensicherung.md`). Deleting them deletes history —
only Sasha decides.
