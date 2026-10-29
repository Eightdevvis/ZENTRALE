# Phone app: things only tested in simulation

**Stand 2026-10-30:** Open, waits for Sasha (needs the real phone).

All of these pass in tests but were never checked on the device:
1. **Back from the chat** on Android 16 (`android:enableOnBackInvokedCallback`, eye icon top left; `mobile/test/zurueck_test.dart`).
2. **Login time:** Argon2id (m=64 MiB) took ~1.7 s on the laptop; on the phone unmeasured. If too slow → native implementation behind the same function (`mobile/lib/konto/`).
3. **Reminders:** VALARM → Android notifications, exact alarms, after reboot (`mobile/lib/kalender/`, boot receiver in the manifest).
4. **Peephole feel:** `panPixelsPerRadian = 780`, `rollPanShare`, dead zone in `mobile/lib/peephole/peephole_tuning.dart`. If Sasha finds it too fast/slow → adjust.
5. **Finger-paced swipe ring and eye shape** (`mobile/lib/auge/auge_regler.dart`: `unterlidTief`, `wischStrecke`, eyelash constants) — aesthetics are Sasha's call.
6. **Calendar edit flow end to end** through the real cloud (proposal → receipt → inbox cleared; reject banner).
