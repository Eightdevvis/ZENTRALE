# App engine: open decisions and first step

**Stand 2026-10-30:** Open, waits for Sasha (questions 3–7).

Plan: [../hub/app_motor_plan.md](../hub/app_motor_plan.md). Decided 29.10.: the assistant is an app with its fixed place at the eye; probe WASM vs. JS on a real phone before committing.

Still open for Sasha (plan, "Open questions"): 3 payments in a Play build, 4 distribution channels (Play / own APK / F-Droid), 5 WebView views on the phone or building blocks only, 6 should an update on one node pull all others, 7 where the store signing key lives and whether workshop apps are signed with Sasha's key.

Not started (does not wait): step 1 of the migration — `mobile/lib/motor/` with the future interface, KI chat and calendar moved to `mobile/lib/apps/assistent/` and `mobile/lib/apps/kalender/`, the ring buttons built from an app register, installed-per-node gating (only installed apps show and sync), import-boundary test. Sasha 29.10.: keep building phone features "prepared and isolated" until then.
