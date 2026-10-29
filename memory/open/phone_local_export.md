# Phone app: nothing lost on uninstall

**Stand 2026-10-30:** Open, does not wait for Sasha.

Sasha (29.10.): uninstalling the app must not lose anything. Android gives no hook before uninstall, so:
- what belongs in the cloud is there after every sync (already),
- local-only data (pending proposals, unsynced chat lines, local UI state) is written regularly as a ZIP into the phone's Downloads folder, which survives an uninstall,
- plus an "export everything" button in settings.

Not built. Code would go into `mobile/lib/` (English, UI text via ARB).
