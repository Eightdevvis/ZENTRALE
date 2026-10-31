# Dock anything from anywhere — sources, install, update, hold, uninstall, data, moving out (plan)

**Stand 2026-10-31 (rewritten the same day after Sasha's answers; his
answers to Q1–Q4 recorded the same evening, section 6): the frame (section 2)
and all four forks are decided; build status per step in section 5.** Blueprint for
roadmap step 4 of [kern_auszug_inventur.md](kern_auszug_inventur.md)
section D (decisions: section H there). It must hold before Lists (step 5,
[list_extraction_plan.md](list_extraction_plan.md)) and Schematix (step 10,
[../open/schematix_extraction.md](../open/schematix_extraction.md)) leave
the core. Builds on the building kit ([building_kit_plan.md](building_kit_plan.md)
§3 tiny core + bundle, §5 node lifecycle and holds), the ports and plug
dialog ([port_types.md](port_types.md)), the adapter idea
([adapter.md](adapter.md), inventory section G) and the store
([shop.md](shop.md)).

## Why

Sasha, 2026-10-31, on the first version ("a store for our apps"):

> *„wir denken nicht mehr dran dass wir paar apps gebaut haben. wir denken
> stattdessen, dass es millionen von apps in der flut der digitalen welt
> gibt die man an zentrale dranstöpseln kann wenn man will."*

> *„wir sprechen bei diesen architektur entscheidungen nich nur über unsere
> projekte sondern einfach einen rahmen der für alle funktionieren kann."*

So step 4 is no longer "deliver our apps": it is **ZENTRALE can dock any
program from any source**, and our own apps are just one source among many.
The old reasons still hold underneath:

- **The Mini-PC lesson** ([building_kit_plan.md](building_kit_plan.md) §0):
  what a node needs must reach it by a normal path, or it goes silent. The
  day `fokus` leaves `EINGEBAUT`, a node without the lists package stops
  syncing `data/lists.json` — no error, the lists go stale there.
- **Today there are three ways to get an app** (built-in, hard-coded
  neighbour folder, store via `git clone`), and the store way fails on a
  fresh node (no GitHub key).
- **Every new app with data needs a core edit** today (the sync allow-list
  lives in the core) — the opposite of "apps live outside the core".

## 1. What exists today (measured 2026-10-31, read from code)

Unchanged from the first version; the facts the frame must absorb.

### 1.1 Mechanisms

| Part | Where | What it does | Gap |
|---|---|---|---|
| Catalog | `core/shop_katalog.jsonld`, `core/shop.py`, `GET /api/shop` | schema.org `ItemList`; apps carry `downloadUrl` (git repo) + `app_name`, built-ins `built_in: true` | lists only budget, cloud, cloud folder; one source kind only (git) |
| Install | `core/app_installation.py` `laden`/`installieren`, `POST /api/apps/laden|installieren` | `git clone` into `<app_ordner>/.laden/<repo>` → check `app.toml` → move → register; adopts an existing checkout | needs `git` and **GitHub access** (budget: `ssh://git@github.com/Eightdevvis/budgeter.git`); no checksum |
| Register | `core/app_register.py` → `data/hub/apps-<node>.json` (not synced) | name, source address, folder, chosen views, date | no `version`, no source kind |
| Where code lands | `app_register.app_ordner()`: setting `app_ordner`, default the folder containing ZENTRALE | laptop: `~/codicus/` | installed node: `~/.local/share/zentrale/hub/` beside the release folders (⚠ prüfen: `_ROOT` uses `abspath`, not `realpath`) |
| Plug dialog | `core/plugs.py`, `app_installation.plug`; `zentrale apps install|plug`; TUI store | asks every `needs` socket; a required socket left open withdraws the app | works for any app |
| Built-in store apps | `core/builtin_store_apps.py` | cloud, cloud folder: "installed" = a node setting | — |
| Update | `core/app_update.py`, run by `zentrale update --automatic` after the core | `git pull --ff-only` per register entry; skips held apps and dirty checkouts | no health check, no roll-back; nothing for tutor/map |
| Hold | `app_register.holds()`, setting `app_holds` (never synced), `POST /api/apps/hold` | `{name: {version, commit, since}}` | holds a git commit |
| Uninstall | `app_installation.entfernen`, `POST /api/apps/remove` | built-ins only | **downloaded apps: 501** ([../open/store_app_lifecycle.md](../open/store_app_lifecycle.md)) |
| Hard-coded apps | `core/apps.py` `BEKANNT = {tutor, karte}`; TUI wheel `RAD_APPS`, `rad_wahl.py`, `app_start.py`, `scripts/open_tutor_room.py` | sibling folders, "installed" when the folder exists | [../open/store_tutor_map_migration.md](../open/store_tutor_map_migration.md); inventory A15, A16 |
| Bundle | `scripts/paket_bauen.py` `bundle()` → `BUNDLE.json` in the core tarball | core + `EINGEBAUT` at the release | nothing reads it on the node yet |
| Core package | `deploy/paket.txt` → `scripts/paket_bauen.py` → R2 `pakete/`, `GET /v1/paket` (`server/src/paket.ts`, invite code or session) | sha256, unpack beside, self-test, switch `aktuell`, previous release kept | the model to copy for our packages; **the node fetches updates with its session** (`zentrale_cli/aktualisieren.py:156`) |
| Data across core updates | `zentrale_cli/aktualisieren.py`: `hub/<release>/data -> ../../data` | everything under `data/` survives | tutor data is `tutor/data/**` (`eingebaute_apps.ERSATZ`), **outside `data/`** (⚠ prüfen: never tested on an installed node) |
| Sync allow-list | `core/abgleich_auswahl.ABGLEICH` (positive list, deny by default) | a manifest pattern syncs only if it is on this core list | **every new app with data needs a core edit** |
| Cloud folder | `core/cloud_folder.py`, `~/Zentrale/Cloud` = `data/cloud/**` in the sync namespace | a visible folder that syncs through the Mitte | the natural "synced location" for app data |
| Mitte back ends | `core/abgleich.py` setting `abgleich_mitte_art` = `git` (old private repo) or `http` (ZenCloud) | sync already has two back ends behind one interface | the seed of "sync as an adapter" (section 4) |

### 1.2 Per node

| Node | Runs ZENTRALE as | Apps today | Missing |
|---|---|---|---|
| **Laptop** (Sasha's dev machine) | git checkout `~/codicus/ZENTRALE` | built-ins; tutor/map as sibling checkouts; budget via store (adopted) | tutor/map in the register; checkouts stay as `git` source |
| **PC, fresh install** (soon, not joined) | `install.sh` → `~/.local/share/zentrale/hub/<release>` | built-ins only; store fails without a GitHub key | a source that needs no key and no account; **the first real test** |
| **Pi** (outpost, no `core/`) | package cut by `deploy/aussenposten.txt`, pulled from the PC | tutor parts as `app:tutor/…` lines from the PC's sibling folder | the PC's builder reads app parts from the register, not a sibling repo ([../open/pi_review.md](../open/pi_review.md)) |
| **Mini-PC** (release 39, silent) | `install.sh` | built-ins of release 39 | heal first ([../open/minipc_finish_setup.md](../open/minipc_finish_setup.md)); then the test case "app moved out, node on an old release" |
| **Phone** | APK, chat and calendar compiled in | none | not part of step 4 ([app_motor_plan.md](app_motor_plan.md) §6); later the phone gets its own sources (APK, F-Droid) in the same frame |

### 1.3 Our app repos

| App | Repo | Remote | Data |
|---|---|---|---|
| tutor | `~/codicus/language-tutor` | `Eightdevvis/language-tutor` | no `[daten]` (fallback `ERSATZ`, [../open/tutor_manifest_data.md](../open/tutor_manifest_data.md)); data at `ZENTRALE/tutor/data` |
| map (`karte`) | `~/codicus/zentrale-karte` | **none** ([../open/map_repo_remote.md](../open/map_repo_remote.md)) | none (29 MB map data + numpy in the code) |
| budget | `~/codicus/budgeter` | `Eightdevvis/budgeter` | DB in `~/.local/share/budget/`, on purpose node-local |

## 2. The frame (decided by Sasha 2026-10-31)

One sentence: **a catalog says what exists and where to get it; a source
adapter installs, updates, holds and removes it; the register is the one
truth of what is installed on this machine; the app's data is plugged into
a location like any other socket.**

```
 catalog item ──points at──▶ sources: [flatpak:org.gimp.GIMP, apt:gimp, zentrale-package:<url>]
      │                                     │ node picks one it has an adapter for
      ▼                                     ▼
 dock card (optional)              source adapter  ── install / update / hold / remove / version / check
 start, ports, data locations               │
      └───────────────▶ register (this node: name, source, version, data plugs, hold)
                                            │
                          plug dialog: data → files location (home | cloud folder | anywhere)
```

### 2.1 Sources are pluggable (decision 1)

A **source adapter** is the same idea as a device adapter (inventory
section G, [../open/printer_adapter.md](../open/printer_adapter.md)): the
core keeps one interface and a broker; each source docks with its own small
manifest. The interface, one per source kind, never per program:

| Call | Answers |
|---|---|
| `available(ref)` | versions it can install, newest first |
| `install(ref, version?)` | installed version + where the program now is |
| `update(ref)` / `rollback(ref)` | new (or previous) version; `rollback` only where the source can (else a clear "this source cannot go back") |
| `hold(ref, version)` / `release(ref)` | the source's own hold if it has one (apt hold, Flatpak mask), else ZENTRALE's hold |
| `remove(ref)` | removed, without touching user data (apt `remove`, never `purge`) |
| `version(ref)` | what is installed now, or nothing |
| `check(ref)` | runs? (our apps: `/hub/gesund`; foreign: the program starts / `--version` answers) |
| `trust` | what the source itself verifies (signature, checksum, nothing) — shown, never faked |

Source kinds, first and later:

| Kind | Ref | Root? | Trust (decision 3: each source checks its own) |
|---|---|---|---|
| `zentrale-package` | HTTPS URL + sha256 (our cloud or any URL; a plain tarball is the same adapter) | no | sha256 now, signature before public ([../open/package_signing.md](../open/package_signing.md)) |
| `git` | repo address + branch | no | none beyond the transport; **developer source** (Sasha's checkouts) |
| `flatpak` | app id, `--user` | no | Flatpak signs |
| `image` | OCI image, rootless (podman) | no | digest pinned; registry signature where offered |
| `appimage` / single file | URL + sha256 | no | sha256 |
| `apt`, `pacman`, … (likely one PackageKit adapter, 2.2a) | package name | **yes** | the distribution signs |
| later: `apk`/F-Droid (phone), Flathub/Debian **catalogs** as catalog adapters | — | — | — |

**Which adapters ship (Q3, Sasha 31.10.):** the **store** — not the core;
store ≠ core — ships with adapters for **our packages, git, PackageKit**
(covers apt, dnf, pacman …) **and Flatpak**, by the rule "everything needed
to operate ZENTRALE is preinstalled": a store without real sources is
useless. Snap, AppImage, images and the rest are adapters you add. The core
keeps only the interface and the broker (as for device adapters, inventory
section G); the adapters belong to the store and move with it.

**Rule for root sources:** ZENTRALE never runs sudo and never keeps a
password (building kit §5.2). A root source asks through the system's own
prompt (polkit) when a person is there, or says in one sentence what to run;
without a person it only reports "update available".

### 2.2 The catalog points, it does not hold

**Catalog source (Sasha 31.10.):** the store reads the **AppStream** data the
repositories already publish (apt's metadata incl. icons, Flathub's appstream
file) and installs through PackageKit/Flatpak; **Repology** is the fallback
for programs not in AppStream ("where to get it"). The store keeps its own
look, with icons. Our hand-written catalog stays for our own apps.

- A catalog item: name, description, **`sources`** (one or more, the node
  picks the first kind it has an adapter for, order by a setting), optional
  **dock card**. The old `downloadUrl` is read as one `git` source.
- **Dock card** = what ZENTRALE needs to treat a program as an app: how to
  start it, the ports it offers/needs, its data locations. Our apps carry it
  as `app.toml`. A foreign program gets one from the catalog (written by us
  or later the Schmied, inventory section H "foreign programs"). **Without a
  card** a program is still installed, updated and launchable — it just has
  no ports and no data to export (2.6).
- Our packages are one source among many, listed in the same catalog.
- Today's catalog stays the one list (`core/shop_katalog.jsonld`, later
  from Sasha's server). **Later (idea, not planned in detail):** instead
  of curating by hand, the store streams in what existing sources offer
  (2.2a).

### 2.2a Later: stream catalogs in, on mainstream standards

Rule "open standard formats" (no own format): the likely base for source
adapters and catalog are three existing standards (checked briefly
2026-10-31, from their public docs):

| Standard | What it covers | Use for us |
|---|---|---|
| **AppStream** (freedesktop.org) | metadata format for software components: name, summary, icons, screenshots, licence, releases, categories, content rating; distro and Flatpak repos ship it as catalog data (Debian/Ubuntu `DEP-11`, Fedora, Arch, Flathub) | the catalog side: read a source's AppStream data instead of writing items by hand; our dock card sits next to it |
| **PackageKit** | one D-Bus API to search, install, update and remove across distro package managers (apt, dnf, pacman, zypper … via back ends), with polkit for root; GNOME Software and KDE Discover use it (plus Flatpak's own library) | one source adapter covers every distro package manager instead of `apt` and `pacman` separately (step 14), and brings the polkit prompt |
| **Repology** | aggregates package names and versions across hundreds of repositories; **information only**, installs nothing | which sources carry a program and how current each is — to pick a source, never to install |

Later step 17. Not needed for step 4 or Lists.

### 2.3 Install: local, no account, no syncer (decision 2)

Installing touches one machine only. Account and cloud matter only for
carrying data (and the list of owned apps) to other machines.

1. Store / CLI / Schematix "install" → catalog item → pick the source.
2. Source adapter `install`. For `zentrale-package` (kept from the first
   version, the safe mechanics): download beside
   (`~/.local/share/zentrale/apps/<name>/.laden/`), **sha256**, unpack with
   the `data` filter, read `app.toml`, check `name`, own venv only if the app
   has `requirements.txt`, then `apps/<name>/<version>/` + link
   `apps/<name>/aktuell`.
3. **Self-test** (`check`). Fails → removed again, nothing registered, one
   sentence why.
4. **Plug dialog** (`plugs.sockets`, unchanged) — now including the data
   location (2.5).
5. Register entry: `source {kind, ref}`, `version`, data plugs. Logged in →
   also marked owned (`/v1/besitz`), so another device can offer it; not
   logged in → nothing else happens.

Foreign programs land wherever their source puts them (Flatpak in
`~/.local/share/flatpak`, apt system-wide); ZENTRALE records, never moves
them. **Our own packages (Q2, Sasha 31.10.):** while nothing is public, a
node fetches them with Sasha's **normal login** (he is the only user; no
invite-code construction). "Install without account" holds for every
foreign source now, and for our packages from the day ZENTRALE goes public.
Then: an info site (e.g. Vercel) and the packages where everyone is (public
GitHub Releases, Flathub, an own apt repo) — so ZENTRALE installs itself
through the same sources as any program.

### 2.4 Update, hold, roll-back

- `zentrale update --automatic` (daily timer) after the core: per register
  entry not held → its adapter's `update` → `check` → failed → `rollback`
  and one note in `status`.
- **"Updates" area in the store (Q4, Sasha 31.10.):** shows what is out of
  date; default "ZENTRALE updates everything"; or only selected programs
  automatically; or manual. Sources that need root go through polkit / the
  system's own password prompt — ZENTRALE never runs sudo.
- `zentrale-package` (kept from the first version): new version installed
  beside the running one, switch `aktuell`, restart if it ran, health
  check, switch back on failure; the last two versions stay on disk.
- **Hold** = "stay on version X" (store `h`); auto-update skips it; a held
  app keeps working as long as its contracts are offered (building kit
  rule 6). Manual: store "update now" / "previous version",
  `zentrale apps update|rollback <name>`.
- Versions do **not** sync between nodes (building kit §2.2 rule 5).

### 2.5 The data location is a socket (decision 5)

- An app's data is a **`files` socket** (port type `files`, scope
  `instance`, already in `contracts/ports/1/types.json`). The app says what
  it keeps (its folder layout, relative); **where** is a plug.
- Providers of a location: **home** (`~/.local/share/zentrale/data/<app>/`,
  local only), **cloud folder** (`~/Zentrale/Cloud/…`, synced everywhere,
  because the cloud folder syncs), **anywhere** (a path, a stick, later a
  network share). The default is the user's choice, asked once in the
  wizard and kept as a setting (per account when logged in — "one way",
  not per device).
- **Sync follows the location, not a list in the core.** An app whose data
  sits in the cloud folder syncs because the folder does. No per-app entry
  in `core/abgleich_auswahl.ABGLEICH` ever again: that list keeps only the
  core's legacy files and may only shrink (new guard, step 6). Secrets never
  go into a data location; they go through the adapter's encrypted store
  ([adapter.md](adapter.md)).
- **One legacy provider:** "ZENTRALE data" = today's `data/` with today's
  allow-list. Apps that move out of the core plug into it, so their files
  stay exactly where they are (2.8).
- **Moving data = re-plugging**, one generic operation for every app:
  stop the app → copy to the new location → verify (same files, same
  sha256) → switch the plug through the gate → start → the old copy stays
  as a backup until the person deletes it. Never a silent move.

### 2.6 Uninstall: export first, then remove (decision 4)

1. Stop the app.
2. **Export** every data location the app (or its dock card) declares into
   one zip, default in a visible folder (`~/Zentrale/Exports/<app>-<date>.zip`,
   ⚠ prüfen the name at build). Verify the zip (every file in, sha256
   equal). Export fails → stop, nothing removed.
3. Unplug its wires **through the one gate** (`generations`), so the next
   compile does not miss a piece; register entry and hold out.
4. Source adapter `remove`.
5. Data: a **local** location is emptied (the zip has it; the person reviews
   or throws it away by hand). A **synced** location is never emptied by an
   uninstall on one machine — other machines may still run the app, and the
   cloud is never overwritten. "Delete this app's data everywhere" is its
   own explicit action, zip first as well.
6. **Foreign programs:** only declared locations are exported; everything
   else stays untouched, and ZENTRALE tells where data probably still is
   (`~/.config/<name>`, `~/.local/share/<name>`, `~/.var/app/<id>` for
   Flatpak …), as a list, never deleting it.
- Reinstall later: a synced location is plugged again as it is; a local
  one starts empty (or the person imports the zip). Ownership stays with
  the account.
- Built-ins and the mandatory adapter keep their own remove rules (adapter:
  never removable).

### 2.7 Preinstalled: what you need to operate ZENTRALE (decision 6)

- **The rule** (Sasha 31.10.): everything one needs to *operate* ZENTRALE —
  whatever one uses it for — is installed; nothing else. A piece is
  preinstalled only if without it the person cannot run, wire, install or
  remove anything.
- Under that rule today: **core, `zentrale` CLI, TUI, Schematix and the
  store (catalog + store client)**. Nothing else, **no checklist**.
  Everything else the person installs; guides and a tutorial come later.
- Core, CLI and TUI are the core package. The **store is not the core**
  (Sasha 31.10.: store ≠ core) — it is preinstalled and brings the source
  adapters (2.1); today its code still sits in the core package. **Schematix** stays built
  in until inventory step 10; then it is a package the installer (and the
  first update that drops it from the core, 2.8) installs — holdable and
  removable like any app. No account needed.
- The cloud keeps its path from building kit §4: it comes with login. That
  is the account's own piece, not an app list.
- A logged-in second device is **offered** the owned apps (exists, `79482b5`)
  — one list, nothing installed without a yes.

### 2.8 Apps moving out of the core: once, never again (decision 7)

Lists, notes, piano, graphs, calendar, Schematix … leave the core once.
That is a special case (CLAUDE.md "Apps live outside the core") and gets
**no big update machinery** — the first version's `MOVED_OUT` table and
automatic `ensure()` are dropped.

**Chosen: "install first, then switch", guided per app** — simpler than an
automatic migration (no new table, no trigger on every start) and safer
(each move happens while a person watches, with a backup in hand):

1. The app's package exists in the catalog, with the **same app name, same
   socket ids, its data socket plugged into the legacy provider "ZENTRALE
   data"** — so it reads and writes the very same files
   (`data/lists.json`, `data/features.json`). No data is converted.
2. On each node, by a person (Sasha) with one guided command
   (`zentrale apps install <name>` plus the checklist below): the package
   is installed **while the core still has the app built in**; the built-in
   wins until the core drops it (⚠ prüfen: the package must not serve the
   same routes meanwhile — guard E8 runs only in tests).
3. **Update guard, the only machinery:** a core release that drops an app
   from its built-ins (old `BUNDLE.json` vs new `BUNDLE.json`, already in
   every tarball) does not switch on a node where that app is not in the
   register — the node stays on the old release (where the app is still
   built in) and `status` says "install lists first". Checkout nodes (git
   pull cannot be refused): the move is done on the laptop **before** the
   removing commit lands; any other checkout shows a loud line in `status`
   and the TUI start line until the package is installed.
4. Devices with auto-update off stay on their release; nothing is lost.

**No data loss — ZENTRALE is Sasha's only calendar.** Every move, every
node:

| When | What |
|---|---|
| **Before** | full backup of the app's files (`scripts/daten_sichern.py`, plus a dated copy outside the repo); a dev-profile rehearsal on a copy of the real data ([../betrieb/dev_mode.md](../betrieb/dev_mode.md)) |
| **After** | verify old = new: sha256 of every data file unchanged by the switch; the app's read route answers byte-equal from the built-in (before) and the package (after), e.g. `GET /api/lists?view=1`; for the calendar also the count and a hash over all events and a check on the phone |
| **Roll-back** (written down per app before the move) | go back to the previous core release (or `git revert` on a checkout) → the built-in returns; remove the package with its adapter. Because both use the same files, nothing is migrated back. If a file did change: restore from the backup |

The calendar (inventory step 12) gets its own written move plan on top of
this table before it starts.

### 2.9 Plugs and ports

Nothing new beyond 2.5 and 2.6: the plug dialog is app-agnostic
(`plugs.py`, `plug_store.py`); uninstall unplugs through the gate
([../open/catalog_lifecycle_decisions.md](../open/catalog_lifecycle_decisions.md)
question 2); moved-out apps keep their names and socket ids, so
`abgleich_apps["fokus"]` and every plug stay valid.

## 3. Tutor and map first (proof of the path)

They are already outside the core: catalog items with a `zentrale-package`
source, `BEKANNT` empties, the wheel builds `m`/`u` from `/api/apps` (A16),
the tutor starts via `POST /api/apps/tutor/start` (A15), the laptop's
checkouts are adopted as `git` sources. The tutor's data gets a data socket
(2.5) and leaves `ZENTRALE/tutor/data` once by re-plugging (copy, verify,
switch); `eingebaute_apps.ERSATZ` goes.

## 4. Login and sync as an adapter (decision 8 — decided: Q1 B)

**Decided by Sasha 2026-10-31 (Q1: yes):** the cloud is already a building
block — it offers the `sync` port, and ZenCloud is today's only provider;
the plug principle was planned from the start. "Adapter" only means a
second provider can later use the same socket. **Built after Lists move**
(step 18). The analysis below stays as the blueprint.

Sasha: if sync only runs through a cloud, and that cloud is a provider we
don't operate, the only login needed is at the provider — not at us. And:
**ZenCloud is itself only a third-party provider (Cloudflare) with our
login glued on top.** So our account is not something special — it is one
sync provider among others, the one we happen to set up.

**Today** ([knoten_beitritt.md](knoten_beitritt.md) "Bauplan v1",
[adapter.md](adapter.md)): our own account (username only, Argon2id on the
device, zero-knowledge) and ZenCloud (Cloudflare worker + D1 + R2). The
account key encrypts everything; the server holds the wrapped keys, the
Mitte (encrypted blobs + one head with compare-and-swap), device
descriptions, ownership, the package downloads (invite code or session),
the insecure-release warning and the usage watch. The adapter's secrets
sync encrypted with the account key.

**What "sync through provider X" would mean:**

| Piece | Today (ZenCloud) | With a provider adapter |
|---|---|---|
| Sync | `HttpMitte` | `sync` port offered by a provider adapter (WebDAV/Nextcloud, S3, Dropbox, Google Drive …). The seed exists: `abgleich_mitte_art` already switches between `git` and `http` |
| Head / conflicts | compare-and-swap in D1 (409) | needs a conditional write at the provider (ETag/`If-Match`; WebDAV, S3, Dropbox, Drive have one) — a provider without it cannot be a Mitte |
| Keys | wrapped keys in D1 | the same wrapped-key file (same Argon2id/HKDF scheme, vectors unchanged) stored **inside the provider folder**; the password still unlocks it — an unlock phrase, not a login at us |
| Zero-knowledge | server sees only ciphertext | unchanged: the provider sees only `*.enc` |
| Node join | `PUT /v1/knoten` | `knoten/<name>.json` in the provider folder (a node writes only its own file — conflict-free by design, as today) |
| Ownership | `/v1/besitz` | an encrypted file in the provider folder |
| What still needs us | — | package downloads while private (Q2), the insecure-release warning (could be a public static file), the store catalog (public, no login) |

Question Q1, answered B. Not needed for step 4 —
installing needs no account anyway (decision 2) — so it does not block
Lists.

## 5. Build steps

Each step ships alone, small enough for one agent, tested in the dev mode's
fakes (fake cloud, fake systemctl, profiles). **B** = needed before Lists
may move (inventory step 5). Order as listed; 2–4 may run in parallel
after 1.

| # | Step | B | Acceptance test |
|---|---|---|---|
| 1 | **Register v2**: `source {kind, ref}`, `version`, `data` plugs; old entries read as `git` | B | old register reads unchanged; round trip; old release reads the new file (`tests/test_alte_fassung.py`) |
| 2 | **Source-adapter frame** in the core (interface 2.1, kind registry, contract vectors `contracts/sources/1/`); today's clone/pull wrapped as the `git` adapter, no behaviour change | B | existing store tests green through the adapter; a conformance suite every adapter must pass (fake adapter) |
| 3 | **Catalog `sources`** + dock card fields; `downloadUrl` read as `git` | B | old catalog unchanged in `/api/shop`; item with two sources → node picks by setting |
| 4a | **Package builder** `scripts/app_paket_bauen.py <repo>` (positive list `paket.txt` per repo, refuses `data/`, `.git`, keys) | B | builds tutor/map/budget; same input → same sha256 |
| 4b | **Hosting** of our packages per Q2 (cloud routes `GET /v1/apps/<name>[/<v>.tar.gz]`, upload script, `server/openapi.yaml`); while private: **login session only** | B | vitest: no session → 401, 404 unknown, sha256 matches |
| 4c | **`zentrale-package` adapter**: install beside, sha256, unpack, venv, self-test, `aktuell` link; fetches with the session | B | fake cloud: works without `git` on PATH; without login → nothing installed, one sentence "log in to fetch our packages"; wrong sha256 → nothing installed; no `/hub/gesund` → nothing registered, sentence says why |
| 5 | **Update, hold, roll-back** through the adapter (2.4), `zentrale apps update|rollback`; store **"Updates" area** (out-of-date list; mode all / selected / manual, Q4) | B | N → N+1; broken N+1 → stays on N with a note; held untouched; roll-back byte-equal; mode "selected" skips the others, "manual" updates nothing |
| 6 | **Data socket**: providers home / cloud folder / anywhere / legacy "ZENTRALE data"; default-location setting + wizard question; sync follows the location; guard: `ABGLEICH` may only shrink | B (legacy provider only) | an app with data in the cloud folder syncs with no core edit; the guard fails on a new pattern in `ABGLEICH` |
| 7 | **Re-plug data** (copy → verify → switch → keep backup) | — | interrupted copy → old plug stays; verify mismatch → no switch; backup present after success |
| 8 | **Uninstall with export** (2.6): zip, verify, unplug through the gate, adapter `remove`; synced locations untouched; foreign: probable locations listed | B (roll-back of a move removes a package) | after remove: not in `/api/apps`, no wire, Run compiles, zip complete, fake cloud unchanged; failing export → nothing removed |
| 9 | **Tutor and map through the store** (section 3), tutor data re-plugged, `ERSATZ` gone, `BEKANNT` empty | B (proof) | fresh profile installs both from the fake cloud, wheel shows them; laptop lists them as `git` sources |
| 10 | **Outpost build reads installed packages** (`app:<name>/…` from the register) | with 9 | outpost package byte-equal before/after on the laptop |
| 11 | **Move-out guard** (2.8 step 3): `BUNDLE.json` diff in the update self-test; loud `status` line on checkouts; move checklist template (backup, verify, roll-back) in `memory/hub/` | B | old-release test: N with a fake built-in, N+1 without it → node without the package stays on N with the note; with the package → switches, data files byte-equal |
| 12 | **Fresh PC = the real test** (Sasha, by hand): install with invite code, **log in** (our packages need the session while private, Q2), install budget and tutor, update, hold, uninstall (zip appears), reinstall; see the data sync | B | checklist in `memory/open/` ticked; findings → `memory/open/` |
| 13 | **Store's preinstalled foreign source 1: Flatpak `--user`** (Q3) + one dock card for a real program (e.g. a PDF viewer needing `files`) | — (preinstalled with the store; after Lists) | install/update/remove a real Flatpak in a dev profile; its `files` socket plugs to the cloud folder |
| 14 | **Store's preinstalled foreign source 2: one PackageKit adapter** (Q3; covers apt, pacman, dnf …; polkit prompt, never sudo) | — (preinstalled with the store; after Lists) | conformance suite; no sudo anywhere (guard); without a person: only "update available" |
| 14b | Adapters you add: `image`, `appimage`, Snap … (from the catalog like any app) | — | per adapter the conformance suite |
| 15 | Schematix as a preinstalled package (with inventory step 10) | — | fresh install has it; removable and holdable |
| 16 | **Signature** for our packages (before public, [../open/package_signing.md](../open/package_signing.md)) | — | tampered package refused; unsigned only in dev mode |
| 17 | **Catalog from AppStream** (apt metadata incl. icons, Flathub appstream file), **Repology as fallback** for programs not in AppStream (2.2); store keeps its own look with icons | — (with 13/14) | a Flathub/Debian program appears in the store with its icon, without a hand-written item |
| 18 | **Sync as an adapter** (Q1 B, section 4): ZenCloud the first provider of the `sync` socket; keys, devices, ownership as encrypted files in the plugged storage | — (after Lists) | own blueprint before building |

Later UX idea (Sasha 31.10., not planned): while ZENTRALE boots, connect the
cloud right away and pick which apps to take over from the old nodes.

After the B steps (and 12 on the real PC) Lists may move: its package
plugs into "ZENTRALE data", Sasha installs it per node with the move
checklist, then the core release drops `fokus`.

## 6. Questions for Sasha — answered 2026-10-31

All four forks are answered; the answers are worked into sections 2–5.

| Q | Answer (Sasha, 2026-10-31) | Where it went |
|---|---|---|
| **Q1 login** | **Yes (B):** the cloud is already a building block offering the `sync` port, ZenCloud is today's only provider; "adapter" only means a second provider can use the same socket later. Build after the lists move. | section 4, step 18 |
| **Q2 our packages** | While nothing is public, a node fetches Sasha's own packages with his **normal login** (only user, no invite-code construction). "Install without account" holds for all foreign sources now and for ours from going public. Later: info site (e.g. Vercel) + packages where everyone is (public GitHub Releases, Flathub, own apt repo). | 2.3, steps 4b/4c/12 |
| **Q3 sources that ship** | The **store** (store ≠ core) ships adapters for our packages, git, **PackageKit** and **Flatpak** — "everything needed to operate ZENTRALE is preinstalled". Snap, AppImage, images … are adapters you add. Catalog: AppStream from the repos, Repology as fallback, own look with icons. | 2.1, 2.2, 2.7, steps 13/14/14b/17 |
| **Q4 updates** | An **"Updates" area in the store**: shows what is out of date; default "ZENTRALE updates everything", or only selected programs, or manual. Root sources through polkit / the system's prompt, never sudo by ZENTRALE. | 2.4, step 5 |

## Historie

- **2026-10-31 (answers)** — Q1–Q4 answered by Sasha and recorded (section
  6): sync as an adapter after Lists (step 18); our packages with the
  normal login while private; the store (≠ core) ships our-package, git,
  PackageKit and Flatpak adapters (steps 13/14 = its preinstalled set,
  after Lists); "Updates" area in the store (step 5); catalog from
  AppStream with Repology as fallback (step 17).

- **2026-10-31 (second version)** — rewritten after Sasha's answers: from
  "a store for our apps" to "dock anything from anywhere". Main differences
  to the first version: sources are pluggable adapters (was: our cloud
  packages + git only); installing needs no account (was: session
  required); signature later and per source, open item filed (was Q2);
  uninstall exports a zip, synced data never touched (was: keep/delete
  question Q3); data location is a `files` socket, sync follows the
  location, no core allow-list edits (was Q4: `data/<app>/` + core list);
  preinstalled = what one needs to operate ZENTRALE (core, CLI, TUI,
  Schematix, store) (was Q5: everything built in ticked); ZenCloud framed
  as one third-party provider with our login on top; AppStream/PackageKit/
  Repology noted as the later base for catalog and source adapters; moving out = "install first, then switch", guided, with backup/
  verify/roll-back and one `BUNDLE.json` guard (was: `MOVED_OUT` table +
  automatic `ensure()`, Q6); login/sync-as-adapter laid out as Q1. Kept:
  the measured facts (section 1), the package install/update/roll-back
  mechanics, tutor and map as the proof.
- **2026-10-31 (first version, `375764a`)** — measured the three ways an app
  arrives today, per node, and the gaps; proposed one path with cloud
  packages, `MOVED_OUT` and the update gate; six questions for Sasha.
