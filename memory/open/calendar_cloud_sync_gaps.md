# Calendar via the Mitte (zencloud): known gaps

**Stand 2026-10-29:** Open, does not wait for Sasha. Calendar source switched to `zencloud` on the laptop on 29.10.2026 (`kalender-haupt.json`, commits `5f358a7`, `f3a5826`, `ea67dab`).

1. **Switching back to google can delete up to 5 Google events.** Google then sees the local folder; the deletion lock (`scripts/kalender_sync.py`) only fires from 6 missing events. Needed before anyone switches back: a stricter check on the first Google run after a source switch.
2. **No real progress (n of N) while filling the cloud.** The CLI only prints "still running". Hook needed: `abgleich.abgleichen(..., progress=None)` → `HttpMitte._hochladen` calls `progress(done, total)` after each blob PUT.
3. **Device without `apps_dabei.json`** that returns exactly on its first sync after the update syncs three-way once instead of "Mitte wins".
4. **Two devices switching to zencloud at the same moment** both fill the cloud.
5. **Google timer** `zentrale-kalender-sync.timer` still runs every 3 min and refuses cleanly (by design, see `memory/hub/adapter.md`). The Google OAuth token expired 27.10. Leave Google data untouched; stop the timer only when Sasha says so.
