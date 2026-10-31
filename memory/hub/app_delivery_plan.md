# One way to get an app — delivery, update, hold, uninstall, moving out (plan)

**Stand 2026-10-31: plan only, nothing built; six forks wait for Sasha
(section 4).** Blueprint for roadmap step 4 of
[kern_auszug_inventur.md](kern_auszug_inventur.md) section D: every node gets
every app the same way — through the store — before Lists (step 5,
[list_extraction_plan.md](list_extraction_plan.md)) and Schematix (step 10,
[../open/schematix_extraction.md](../open/schematix_extraction.md)) leave the
core. Builds on the building kit ([building_kit_plan.md](building_kit_plan.md)
§3 tiny core + bundle, §4 cloud preinstalled, §5 node lifecycle and holds),
the store ([shop.md](shop.md) "Apps installieren", "Built-in apps,
ownership, holds"), the plug dialog ([port_types.md](port_types.md)) and the
app engine ([app_motor_plan.md](app_motor_plan.md) §4–5). Decided by Sasha:
**one repo per app** (GitHub, private, created with `gh` as `Eightdevvis`).

## Why

- **The Mini-PC lesson** ([building_kit_plan.md](building_kit_plan.md) §0):
  a node was installed, synced once and then went silent, because what kept
  it alive arrived later and nothing pulled it. The same happens to an app:
  sync is per app (`core/abgleich_apps.py` builds its table from the
  *installed* manifests plus `core/eingebaute_apps.py`). The day `fokus`
  leaves `EINGEBAUT`, a node that has no lists package simply stops syncing
  `data/lists.json` — no error, the lists just go stale there.
- **Today there are three ways to get an app**, not one: built-in (compiled
  into the core), hard-coded neighbour folder (`core/apps.py` `BEKANNT`:
  tutor, map), and the store (budget, `git clone`). Every extraction would
  add to the second way unless the store becomes the only one.
- **The store way does not work on a fresh node yet**: it clones private
  GitHub repos over SSH — a fresh PC (Sasha reinstalls it soon, not joined
  meanwhile) has no GitHub key, so every downloaded app fails there.
- CLAUDE.md "Apps live outside the core": *preinstalled = installed at
  signup, deselectable/holdable*, never compiled in.

## 1. What exists today (measured 2026-10-31, read from code)

### 1.1 Mechanisms

| Part | Where | What it does | Gap for step 4 |
|---|---|---|---|
| Catalog | `core/shop_katalog.jsonld`, `core/shop.py`, `GET /api/shop` | schema.org `ItemList`; apps carry `downloadUrl` (git repo) + `app_name`, built-ins carry `built_in: true` | only budget, cloud, cloud folder are listed; tutor/map are not |
| Install (download) | `core/app_installation.py` `laden`/`installieren`, `POST /api/apps/laden|installieren` | `git clone` into `<app_ordner>/.laden/<repo>` → check `app.toml` → move to `<app_ordner>/<repo>` → register; adopts an existing checkout of the same repo | needs `git` (installer does not check it) and **GitHub access** (budget: `ssh://git@github.com/Eightdevvis/budgeter.git`); no checksum, no signature |
| Register | `core/app_register.py` → `data/hub/apps-<node>.json` (not synced) | name, source address, folder, chosen views, date | no version field; laptop holds only `budget` |
| Where code lands | `app_register.app_ordner()`: setting `app_ordner`, default the folder that contains ZENTRALE | laptop: `~/codicus/` | installed node: `~/.local/share/zentrale/hub/` next to the release folders `38/`, `39/` (⚠ prüfen: `_ROOT` uses `abspath`, not `realpath`) |
| Plug dialog at install | `core/plugs.py`, `app_installation.plug`; CLI `zentrale apps install|plug`; TUI store | asks every `needs` socket; a required socket left unplugged withdraws the app from the register (folder stays) | — (works for any app) |
| Built-in store apps | `core/builtin_store_apps.py` | cloud, cloud folder: "installed" = the existing node setting; remove = setting off, nothing deleted | — |
| Update | `core/app_update.py`, run by `zentrale update --automatic` (daily timer) after the core | `git pull --ff-only` per register entry; skips held apps and checkouts with local changes | no health check, no roll-back, no version choice; nothing for apps outside the register (tutor, map) |
| Hold | `app_register.holds()`, setting `app_holds` (never synced), `POST /api/apps/hold` | `{name: {version, commit, since}}` | holds a git commit, not a package version |
| Uninstall | `app_installation.entfernen`, `POST /api/apps/remove` | built-ins only | **downloaded apps: 501** ([../open/store_app_lifecycle.md](../open/store_app_lifecycle.md)) |
| Hard-coded apps | `core/apps.py` `BEKANNT = {tutor: language-tutor, karte: zentrale-karte}`; TUI wheel `startseite.py` `RAD_APPS` (`m`, `u`), `rad_wahl.py`, `app_start.py` + `scripts/open_tutor_room.py` | found as sibling folders, always "installed" when the folder exists | [../open/store_tutor_map_migration.md](../open/store_tutor_map_migration.md); inventory A15, A16 |
| Bundle | `scripts/paket_bauen.py` `bundle()` → `BUNDLE.json` in the core tarball | core + `EINGEBAUT` at the release; `BEKANNT` + catalog apps without version | nothing reads it on the node yet (only documentation of the release) |
| Signup/second device | `zentrale_cli/wizard.py` `_offer_owned`; `core/account_ownership.py` (`/v1/besitz`) | built-ins owned by the account are switched on; downloaded ones only get a hint "get them in the store" | no "preinstalled" set; no download in the wizard |
| Core package | `deploy/paket.txt` → `scripts/paket_bauen.py` → cloud R2 `pakete/`, `GET /v1/paket`, `/v1/paket/<v>.tar.gz` (`server/src/paket.ts`, invite code or session) | sha256 checked, unpacked beside, self-test, switch `aktuell`, previous release kept | the model to copy for apps |
| Data across core updates | `zentrale_cli/aktualisieren.py`: `hub/<release>/data -> ../../data` | everything under `data/` survives updates | the tutor's patterns are `tutor/data/**` (`eingebaute_apps.ERSATZ`) — **outside `data/`**, so on an installed node they would sit inside the release folder (⚠ prüfen: never tested on an installed node) |
| Sync allow-list | `core/abgleich_auswahl.ABGLEICH` (positive list, deny by default) | a manifest pattern syncs only if it is on this core list | **every new app with data needs a core edit** — contradicts "apps outside the core" |

### 1.2 Per node

| Node | How it runs ZENTRALE | How apps get there today | Missing for "one way" |
|---|---|---|---|
| **Laptop** (`0RAMMachine`, Sasha's dev machine) | git checkout `~/codicus/ZENTRALE` | built-ins in the core; tutor/map as sibling checkouts (`BEKANNT`); budget via store (adopted own checkout) | tutor/map into the register; the checkout must keep working as "developer source" |
| **PC, fresh install** (soon, not joined meanwhile) | `install.sh` with invite code → `~/.local/share/zentrale/hub/<release>` | built-ins only; store install fails without a GitHub key; tutor/map: nothing (no sibling folder) | a package source that needs only the account; preinstalled set at signup; **the natural first real test** |
| **Pi** (outpost, no `core/`) | package cut by `deploy/aussenposten.txt`, pulled from the PC backend (`scripts/aussenposten_update.py`) | tutor parts as `app:tutor/…` lines read from the PC's sibling folder; map deliberately not | separate review ([../open/pi_review.md](../open/pi_review.md)); here only: the PC's builder must read app parts from the *installed* package, not a sibling repo (step 8) |
| **Mini-PC** (installed 24.10., release 39, silent) | `install.sh` | built-ins of release 39 | must be healed first ([../open/minipc_finish_setup.md](../open/minipc_finish_setup.md)); then it is the test case for "an app leaves the core while the node is on an old release" |
| **Phone** | APK; chat and calendar compiled in (`mobile/lib/`), no app register | none | not part of step 4: the app engine's step 1 ([app_motor_plan.md](app_motor_plan.md) §6, [../open/app_engine_decisions.md](../open/app_engine_decisions.md)). Lists/Schematix are not on the phone, so nothing is lost there now |

### 1.3 The app repos

| App | Repo | Remote | `[daten]` | Notes |
|---|---|---|---|---|
| tutor | `~/codicus/language-tutor` | `git@github.com:Eightdevvis/language-tutor.git` | **none** (fallback `eingebaute_apps.ERSATZ`, [../open/tutor_manifest_data.md](../open/tutor_manifest_data.md)) | data at `ZENTRALE/tutor/data` |
| map (`karte`) | `~/codicus/zentrale-karte` | **none** ([../open/map_repo_remote.md](../open/map_repo_remote.md)) | none needed (no user data) | 29 MB map data + numpy |
| budget | `~/codicus/budgeter` | `Eightdevvis/budgeter` (catalog) | none on purpose (DB in `~/.local/share/budget/`, stays on the node) | first store app |

## 2. The one path

One sentence: **the store catalog says what exists, the cloud holds the
package files, the node installs a versioned package beside the old one,
switches only after a health check, and the register is the one truth of
what is installed here.** Git checkouts stay, but only as the developer's
source on Sasha's machine.

### 2.1 Where a package comes from (fork Q1)

```
 app repo (GitHub, private)          ZENTRALE cloud (R2)                  node
 ─────────────────────────           ───────────────────                  ────
 tag v1.2.0 ──▶ scripts/app_paket_bauen.py ──▶ apps/<name>/neueste.json ──▶ GET /v1/apps/<name>
                (on Sasha's machine,          apps/<name>/<v>.tar.gz   ──▶ GET /v1/apps/<name>/<v>.tar.gz
                 like the core package)                                   (session; sha256 checked)
 catalog item:  downloadUrl = zentrale cloud address of the package, app_name, version list
```

- The catalog stays the one list of what exists (`core/shop_katalog.jsonld`
  today, later from Sasha's server — the exchange point in `shop.md`).
- Recommended: the **cloud** serves app packages exactly like the core
  package (same build script style, same R2 bucket, same session rule). A
  node needs only its account — no GitHub key, no `git`.
- `git` stays for one case: a **developer source** (Sasha's checkouts). The
  register records `source: package | checkout`; `checkout` entries are
  updated by `git pull --ff-only` as today, `package` entries by the cloud.
- Package format: a `.tar.gz` like the core (one unpack and checksum path;
  [app_motor_plan.md](app_motor_plan.md) §1 says `.zip` — part of Q1).
- What goes into a package: a positive list in the app repo (`paket.txt`,
  same rules as `deploy/paket.txt`: never `data/`, `.git`, keys). The
  builder refuses otherwise.

### 2.2 Where an app lives on a node

| What | Where | Survives | Why |
|---|---|---|---|
| Code | `~/.local/share/zentrale/apps/<name>/<version>/` + `apps/<name>/aktuell -> <version>` (checkout nodes: the checkout folder) | app updates (previous version kept) | same pattern as the core: switch a link, roll back by switching it back |
| Own venv (only if the app has `requirements.txt`) | `apps/<name>/<version>/venv` (reused when requirements are unchanged, like `aktualisieren.py`) | — | map needs numpy; budget and tutor use stdlib or ZENTRALE's |
| Register | `data/hub/apps-<node>.json` + new fields `version`, `source` | core updates (`data/` symlink) | per node, never synced (standort_und_app.md) |
| Holds | setting `app_holds` (`data/ai_config.json`) — `version` becomes the key fact, `commit` only for checkouts | core updates | per node |
| App data | under `data/` only (fork Q4) | core and app updates, uninstall (fork Q3) | `data/` is the only folder that survives a core update today |

### 2.3 Install

1. Store / CLI / wizard / Schematix "install" → `POST /api/apps/laden`
   reads the catalog item: `source = package` → `GET /v1/apps/<name>`
   (newest or a chosen version; the store already lets Sasha pick views,
   picking a version is the same dialog).
2. Download beside (`apps/<name>/.laden/`), **sha256** against
   `neueste.json` (later signature, fork Q2), unpack with the `data` filter
   (as the core does), read `app.toml`, check `name == app_name`.
3. Venv if needed, **self-test**: start it, `GET /hub/gesund` answers (tile
   apps: `/hub/kachel` answers). Fails → folder removed, nothing registered,
   one sentence why.
4. Views chosen → **plug dialog** (`plugs.sockets`, unchanged): `data → sync`
   is asked by the sync choice as today; `model`, `files` … are asked here. A
   required socket left open withdraws the app (unchanged rule).
5. Register entry (`version`, `source`), `aktuell` link, ownership marked
   (`/v1/besitz`) when logged in. The wheel shows it (`GET /api/apps`).

### 2.4 Update, hold, roll-back

- `zentrale update --automatic` (daily timer) after the core: for each
  `package` entry not held → newest version from the cloud → steps 2–3 of
  install beside the running one → switch `aktuell` → restart the app if it
  ran → health check → failed → switch back, one note in `status`. The last
  two versions stay on disk.
- **Hold** = "stay on version X" (store `h`, unchanged UI). Auto-update skips
  it; a held app keeps working as long as its contracts are offered
  (building kit rule 6).
- **Manual**: store detail "update now" / "go back to the previous version".
  `zentrale apps update <name>` and `zentrale apps rollback <name>` for the
  terminal fallback.
- Versions do **not** sync between nodes (building kit §2.2 rule 5,
  decided 30.10.); the "same version" wire in Schematix stays as built.

### 2.5 Uninstall — and where the data goes

- `POST /api/apps/remove` for downloaded apps (today 501): stop the process,
  take the register entry and its hold away, switch its `data → sync` wire
  and its other wires off **through the one gate** (`generations`), remove
  the code folder. The wheel and `/api/apps` no longer show it.
- **The cloud is never touched** (Sasha's rule "the cloud is never
  overwritten"): uninstall only stops this node's sync of the app's
  patterns; the Mitte keeps everything; other nodes keep running the app.
- **The local copy of the data**: fork Q3 (recommended: kept, with an
  explicit "also delete the data on this device" choice).
- **Reinstall later**: the first sync of that app treats the node like a new
  device — **cloud wins, the local leftover is set aside** (the existing
  held-back rule of the first sync), Sasha chooses. Never a silent merge
  from an old local copy into the cloud.
- Ownership (`/v1/besitz`) stays — the account still owns it, so another
  device or a reinstall offers it again.
- Built-in apps and the mandatory adapter keep their existing remove rules
  (adapter: never removable).

### 2.6 Plugs and ports

Nothing new: the plug dialog is already app-agnostic (`plugs.py`,
`plug_store.py`). Two additions only:
- **Uninstall unplugs** through the gate (else the next compile fails on a
  missing piece — compare [../open/catalog_lifecycle_decisions.md](../open/catalog_lifecycle_decisions.md) question 2).
- **Moved-out apps keep their wires**: the package uses the same app name
  (`fokus`, `schematix`) and the same socket ids as its `PORTS` entry in
  `core/eingebaute_apps.py`, so `abgleich_apps["fokus"]` and every plug stay
  valid — no question is asked again.

### 2.7 "Preinstalled at signup"

- The catalog item gets `additionalProperty preinstalled: true` (one truth,
  in the catalog — not a list in the core). Which apps: fork Q5.
- **Signup / first login** (wizard, after "cloud"): one checklist "These
  apps come with ZENTRALE — untick what you don't want here", all ticked.
  Confirm → each is installed by the normal path (2.3), plug dialog with
  defaults, ownership marked. A deselected one is simply not installed; it
  stays in the store.
- **Second device**: the existing "owned elsewhere" step installs downloaded
  apps too (today it only points to the store), same checklist, default
  ticked.
- **Holdable** like any package (2.4). No special code path: preinstalled
  is only a default tick.
- Built-ins (cloud, cloud folder, adapter) keep their own setting path until
  they leave the core.

### 2.8 An app moves out of the core — reaching nodes that had it built in

The hard case (Lists first, then notes, piano, Schematix …). Goal: **no
node loses an app it had, and every step can go back.**

**Order (enforced, not remembered):**

1. The app's repo exists, its package is **published in the cloud and
   listed in the catalog** — while the core still has it built in. Same app
   name, same data paths (Q4), same socket ids.
2. The core release that removes it from `EINGEBAUT` adds one line to a new
   table **`MOVED_OUT`** (`{name: {address, since_release}}`, next to the
   legacy list in `core/eingebaute_apps.py`; the guard E9 list shrinks by
   one, `MOVED_OUT` only grows).
3. Publishing guard: `scripts/paket_bauen.py` refuses a release when an app
   that was in `EINGEBAUT` of the previous release is neither still there
   nor in `MOVED_OUT` with a catalog item that has a published package.

**On each node (two triggers, one function `moved_out.ensure()`):**

| Node | Trigger | What happens |
|---|---|---|
| installed node (`install.sh`) | `zentrale update` of the **new** release, inside the self-test, **before** `aktuell` switches | for every `MOVED_OUT` app this node had (built-in apps are on every full node; an explicit "off" in `abgleich_apps` is still installed but stays unsynced — fork Q6) → install its package (2.3, no questions, plugs taken from the existing settings). Any failure → **stay on the old release** (which still has the app built in), one note in `status`. |
| checkout node (laptop, PC as long as it runs from git) | backend start and the keeper (every sync run) | `git pull` already removed the module, so the same `ensure()` runs on start: installs from the sibling checkout if present (adopt), else from the cloud; until it succeeded, `status`, the TUI start line and `/api/apps` say loudly "lists moved out — not installed here" |
| node with auto-update off | — | stays on its release, the app stays built in, nothing is lost; `status` shows "update available" as today |
| Pi (outpost) | the PC's outpost build | nothing on the Pi itself: it is an HTTP client of the PC; the PC's list routes are forwarded to the package (list_extraction_plan: the TUI view stays in the hub) |

**Roll-back:** going back to the previous core release (by hand, or by the
self-heal) gives the built-in app back. Because the package reads and writes
**the same files** (`data/lists.json`, `data/features.json`) in the same
format, nothing has to be migrated in either direction — that is the main
reason for recommending "keep existing data paths" in Q4. The installed
package stays registered, and an old release reads the register too
(`apps.aus_dem_laden`), so it would see a package `fokus` next to its
built-in one. ⚠ prüfen in step 10: the built-in must win and the package
must not be started on the same routes (guard E8 runs only in tests). Mixed
nodes (one on the old release, one on
the new) sync the same files the whole time.

### 2.9 Tutor and map first (proof of the path)

They prove the whole path before anything leaves the core: they are already
outside, have a process, views and (tutor) data. Tutor and map get catalog
items and packages; `BEKANNT` empties; the wheel builds `m`/`u` from
`/api/apps` (A16) and starts the tutor via `POST /api/apps/tutor/start` (A15).
On the laptop the existing checkouts are adopted (`source: checkout`). The
tutor's data moves under `data/` (Q4) with its `[daten]` in its own
`app.toml`, and `eingebaute_apps.ERSATZ` goes.

## 3. Build steps

Each step ships alone and is small enough for one agent. Tests run in the
dev mode's fakes (fake cloud, fake systemctl, profiles — [../betrieb/dev_mode.md](../betrieb/dev_mode.md)).
Steps 1–3 can run in parallel; 4 needs 2+3.

| # | Step | Acceptance test |
|---|---|---|
| 1 | **Repos and manifests.** `gh repo create Eightdevvis/zentrale-karte --private`, push ([../open/map_repo_remote.md](../open/map_repo_remote.md)); tutor `app.toml` gets `[daten]` ([../open/tutor_manifest_data.md](../open/tutor_manifest_data.md)) — path per Q4; `paket.txt` in tutor, map, budget | E3 guard green in each repo; `abgleich_apps.tabelle()` unchanged for the tutor with `ERSATZ` removed |
| 2 | **App package builder** `scripts/app_paket_bauen.py <repo>` → `dist/apps/<name>-<version>.tar.gz` + `neueste.json` (version from `app.toml`, positive list, forbidden paths as `paket_bauen.py`) | builds tutor/map/budget; refuses `data/`, `.git`, keys; same input → same sha256 |
| 3 | **Cloud routes** `GET /v1/apps/<name>` and `/v1/apps/<name>/<version>.tar.gz` (session required, R2 `apps/<name>/…`), upload script beside `paket_hochladen.mjs`, `server/openapi.yaml` | vitest: 401 without session, 404 unknown, sha256 matches; contract vector file `contracts/app-packages/1/` |
| 4 | **Install from a package** (`source: package`) in `app_installation`: download beside, sha256, unpack, venv, self-test (`/hub/gesund`), register `version`/`source`; catalog `downloadUrl` may be a cloud package address; git stays as `checkout` | fake cloud: install works without `git` on PATH; wrong sha256 → nothing installed; broken app (no `/hub/gesund`) → nothing registered, sentence says why |
| 5 | **Update, hold, roll-back for packages** in `app_update` + `zentrale apps update|rollback`, store "update now"/"previous version" | N → N+1 switched; broken N+1 → stays on N with a note; held app untouched; roll-back restores N byte-equal |
| 6 | **Uninstall downloaded apps** (`POST /api/apps/remove`, TUI `x`, `zentrale apps remove`): stop, unplug through the gate, register out, code out; data per Q3 | after remove: not in `/api/apps`, no wire, Run compiles; fake cloud unchanged; data files per Q3; reinstall → first sync cloud wins, local leftover set aside |
| 7 | **Tutor and map through the store**: catalog items, packages published, `BEKANNT` empty (guard: may only shrink, then gone), wheel from `/api/apps` (A16), tutor start via route (A15), bundle builder stops reading `BEKANNT`, laptop checkouts adopted | E1 green; fresh dev profile installs tutor and map from the fake cloud and the wheel shows both; laptop: `GET /api/apps` lists them with `source: checkout` |
| 8 | **Outpost build reads installed packages**: `app:<name>/…` lines resolve from the register's folder, not a sibling repo (Pi itself: [../open/pi_review.md](../open/pi_review.md)) | outpost package byte-equal before/after on the laptop |
| 9 | **Preinstalled at signup**: catalog `preinstalled`, wizard checklist, second-device step installs downloaded owned apps | fresh profile → wizard → the ticked apps are installed and owned, the unticked one is not; second profile on the same fake account gets them offered and installed |
| 10 | **`MOVED_OUT` + `ensure()` + publishing guard** (2.8), wired into the update self-test and the backend start/keeper | old-release test (`tests/test_alte_fassung.py`) extended: release N with a fake built-in app, N+1 without it + package in the fake cloud → after update the app is installed, its data file still syncs, nothing lost; package missing → node stays on N; checkout profile → `ensure()` installs on start; guard refuses a release that drops a built-in without `MOVED_OUT` |
| 11 | **Fresh PC = the real test** (Sasha, by hand): checklist in `memory/open/` — install with invite code, log in, preinstalled apps there, budget from the store without a GitHub key, uninstall budget, reinstall, update an app, hold one | everything on the checklist ticked on the real PC; findings → `memory/open/` |
| 12 | Signature (only after Q2): Ed25519 over the sha256, core and apps with one key system ([../open/phone_self_update_hardening.md](../open/phone_self_update_hardening.md)) | tampered package refused; unsigned only in dev mode |

After 1–10 (and 11 on the real PC), step 5 of the inventory (Lists) may
start: it then only adds `fokus` to `MOVED_OUT` and publishes its package.
Schematix (step 10) follows the same recipe.

## 4. Questions for Sasha

Each has a recommendation; nothing is decided until Sasha answers.

**Q1 — Where do app packages come from?**
- A: **Our cloud** serves them like the ZENTRALE package (built from the app
  repo by a script, stored in the cloud, the node needs only its account).
  *Recommended* — works on a fresh PC and later for customers; GitHub stays
  the place for code, not for delivery.
- B: GitHub Releases of each private repo — every node needs a GitHub token.
- C: `git clone` as today — every node needs a GitHub SSH key; fine for
  Sasha's machines only.
- Sub-point: package as `.tar.gz` like ZENTRALE itself (recommended) or
  `.zip` as the app engine plan wrote.

**Q2 — Signing: now or later?**
- A: Now only a checksum over HTTPS from our own cloud; the real signature
  (Ed25519) comes for ZENTRALE and apps together before going public.
  *Recommended* — same protection level as the ZENTRALE package today.
- B: Sign app packages right away (key management first).

**Q3 — Uninstall: what happens to the app's data on this device?** (The cloud
is never touched in any option.)
- A: **Kept** on the device; a separate "also delete the data here" choice.
  *Recommended* — nothing is ever lost by a click; on reinstall the cloud
  wins and the leftover is set aside for you to choose.
- B: Deleted on the device (the app engine plan said this).
- C: Ask every time.

**Q4 — Where does an app's data live on a node?**
- A: Apps that move out **keep their current files** (`data/lists.json`
  stays where it is); new apps get one folder each, `data/<app>/`, which
  syncs without a core edit. *Recommended* — moving out needs no data
  migration, and going back to an older version is free. The tutor moves its
  data from `ZENTRALE/tutor/data` into `data/tutor/` once (today it would not
  survive a ZENTRALE update on an installed node).
- B: Every app moves its data into its own folder now — cleaner, but one
  data migration per app, each with its own roll-back.

**Q5 — What is preinstalled at signup?**
- A: Everything that is built in today and moves out (lists, notes,
  calendar, assistant, Schematix, piano, Desk/Werkstatt …) is ticked by
  default, deselectable; tutor, map, budget are optional in the store.
  *Recommended* — a new device feels like today's ZENTRALE.
- B: Only the base (cloud, cloud folder, assistant); everything else is a
  list to pick from.
- C: You name the list.

**Q6 — When an app moves out, what happens on a device that had it built in?**
- A: The ZENTRALE update **installs it automatically** before switching to
  the new version; if that fails, the device stays on the old version (where
  the app is still built in). An app you had switched off for syncing stays
  installed but unsynced. *Recommended* — nothing disappears, nothing is
  asked, roll-back is free.
- B: The update switches, and the next start asks "lists moved out —
  install?".
- (Devices with auto-update off stay on their version in both cases.)

## Historie

- **2026-10-31** — written (docs only) for inventory step 4: measured the
  three ways an app arrives today, per node type, and the gaps (GitHub key on
  a fresh node, 501 on uninstall, tutor data outside `data/`, sync allow-list
  in the core); proposed one path with cloud packages, `MOVED_OUT` and the
  update gate; six questions for Sasha.
