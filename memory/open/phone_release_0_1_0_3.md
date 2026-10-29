# Phone app 0.1.0+3: build and publish (first self-update test)

**Stand 2026-10-30:** Open, waits for Sasha (free RAM or build on another machine).

- `mobile/pubspec.yaml` is at `0.1.0+3` (commit `a70e851`, calendar colours like the TUI). Published in the cloud is `0.1.0+2`.
- Not built yet: on the laptop only ~690 MB were free (Brave ~900 MB); Gradle needs ~2 GB (`mobile/android/gradle.properties`).
- Steps: build the release APK in `mobile/` → `scripts/publish_phone_app.py publish --notes "…"` (try `--dry-run` first) → on the phone the update dot appears top right on the next start → install.
- This is the first real end-to-end test of the self-update (`mobile/lib/update/`, `cloud/src/phone.ts`, doc `memory/betrieb/phone_app_release.md`).
