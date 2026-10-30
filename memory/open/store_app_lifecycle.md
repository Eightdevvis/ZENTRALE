# Store apps: uninstall, update, rights dialog

**Stand 2026-10-29:** Open, does not wait for Sasha. Found while building
store installs (commits `20717be`, `e3b243f`, 25.10.2026).

**What exists:** The store (Schaufenster) installs any app with an `app.toml`
in two steps: fetch the repo, then set up only the views Sasha picks. The app
lands in the app wheel; with more than one view the wheel asks which one to
open. Installed state lives per machine in `data/hub/`. Docs:
`memory/hub/` (store description, hub blueprint), `openapi.yaml`.

**What is missing:**

- **Uninstall:** only built-in store apps (`cloud`, `cloud_folder`) can be
  removed (`POST /api/apps/remove`, building kit step 10); a downloaded app
  answers 501 — no way to remove its wheel entry, views, folder.
- **Update:** since building kit step 12 `zentrale update --automatic`
  fast-forwards installed apps unless held (`core/app_update.py`); there is
  no manual "update this app now" in the store and no choice of version.
- **Rights dialog:** the `rechte` listed in `app.toml` are not shown or
  confirmed before install.
- **Same machine only:** opening a view assumes TUI and backend run on the
  same computer.
- **Icons:** app-supplied PNG icons (up to 32×32) unfold in the wheel but are
  not animated like the built-in ones in `pixel.py`.
