# Building kit — plugs, contracts, packages, node lifecycle, wiring map (plan)

**Stand 2026-10-30: plan; build steps 0–3 (`13235f8`, `527afc3`), 5–6, 7–8 (`d1dc8fd`), 9 and 9b (`6a63d16`) built.** One blueprint for
how ZENTRALE is put together from the consumer's side: everything is a
building block that offers and needs plugs, the core is tiny, updates are
never forced, and the Desk can show and change the real wiring. It
supersedes parts of [knoten_beitritt.md](knoten_beitritt.md) (join flow,
"what a kind gets") and [cloud_app.md](cloud_app.md) (cloud as a special
built-in service) and answers question 6 of [app_motor_plan.md](app_motor_plan.md).
Schematix as built: [schematix.md](schematix.md).

Sasha, 2026-10-30:

> *„pdf viewer guckt in meine dateien. ich hab die app cloud. cloud schreibt
> in meine dateien. ich kann per pdf viewer cloud nutzen. komplizierter: ich
> hab den tutor. er schreibt spielstand und legt ordner an dynamisch. ich
> stöpsel ihn an die cloud. er schreibt sich selbst über die cloud. … und das
> is keine sonderstruktur für die cloud sondern das prinzip des spielkastens
> von zentrale. alles sind lego bausteine und du baust deine struktur selbst."*

> *„dass niemand gezwungen wird zu updaten um das system weiter mitzubenutzen."*

**Yardstick** ([../leitbild.md](../leitbild.md)): sections 1–5 are groundwork,
needed now because a real node (the Mini-PC) was installed and then silently
stopped (evidence below). Section 6, the wiring map, is the tool for stage 2
of the plan ("Die Hardware-Karte der Wohnung", rooms × senses, wiring
diagrams) — it is on the main path, not Desk polish.

## 0. Evidence: the Mini-PC (checked read-only 2026-10-30)

| Fact | Meaning |
|---|---|
| Installed 24.10. by `install.sh` → `~/.local/share/zentrale/hub/{38,39}`, `aktuell -> 39`, `~/.local/bin/zentrale` linked | install works |
| `~/.config/zentrale/konto.json`, `abgleich_weg = mitte`, `abgleich_mitte_art = http`, ten apps chosen (no `cloud_folder`) | login and setup worked |
| Synced exactly once (`abgleich/zustand.json`, 24.10. 10:17) | nothing ran afterwards |
| No `~/.config/systemd/user/`, `Linger=no`, no ZENTRALE process | no timers, nothing survives logout |
| Latest release is 41; timers came with release 41 (`9dce660`, 24.10. 11:56) | the fix exists, but release 39 has no way to fetch it |

**Root cause:** whatever keeps a node alive arrived *after* the node was
installed, and nothing pulls new releases by itself. A node can only heal
if the updater is the first thing that runs and is part of the installer,
not of a later `setup`. Second gap: user timers only run while Sasha is
logged in; the mini has no monitor and boots to a login prompt
([../open/mini_pc_tty_login.md](../open/mini_pc_tty_login.md)).

## 1. The principle: plugs, not special structures

### 1.1 Three words

- **Piece** — anything you can place: an app instance (tutor, PDF viewer,
  calendar "main"), a provider app (cloud, adapter), a node (mini, laptop),
  a device without ZENTRALE (router, printer, power bank).
- **Port** — a typed plug on a piece. A piece **offers** ports and
  **needs** ports. The type is a contract (section 2), never a product
  name: `files`, not "cloud folder"; `print`, not "HP".
- **Wire** — one connection from an offered port to a needed port of the
  same type. Wires are the *only* way pieces reach each other. The hub
  checks every call at the one door against the wires (today: the rights
  check), so a wire *is* a granted right with a chosen provider.

### 1.2 Sasha's examples, as wires

```
 [PDF viewer] needs files:read ◀──── [Cloud folder] offers files
                                           │ offers data   (~/Zentrale/Cloud = data/cloud/**)
                                           ▼
                                     [Cloud] offers sync ──▶ account (other nodes)

 [Tutor] needs data  ◀── platform gives every app its own data port (folders created freely inside)
         data ──wire──▶ [Cloud] sync       = today abgleich_apps["tutor"] = true
```

- The PDF viewer knows nothing about the cloud. It reads a `files` port;
  that the files sync is a property of *another* wire.
- The tutor creates folders dynamically inside its own data port; the
  `sync` wire carries the whole port, whatever is inside.
- Swap the provider, keep the app: `sync` could come from the PC as Mitte
  or from git; `files` could come from a USB stick. Nothing in the
  consumer changes. Same rule as the adapter's capabilities: AI tools hang
  on `print`, never on a printer model.

### 1.3 Starting port vocabulary (small on purpose)

| Port type | Offered by (today) | Needed by (today) | Today's form |
|---|---|---|---|
| `data` | platform, one per app | every app with `[daten]` | `[daten] muster` + positive list |
| `files` | platform folders `~/Zentrale/<name>` (Cloud, Ablage) | file apps (PDF viewer, future) | `cloud_folder`, `ablage` |
| `sync` | `cloud` (later PC-Mitte, git) | any `data`/`files` port | `abgleich_apps` per node |
| `model` | adapter connection `ki-anbieter` | assistant, tutor | rights word `modell` |
| `calendar-source` | adapter (google), cloud (zencloud), platform (local) | calendar instance | `quelle` in `kalender-<id>.json` |
| `event:<name>` | apps, sensors | apps | `liefert` / `rechte = ["ereignis:…"]` |
| `tile:<kind>` | apps | Desk, start page | `liefert = ["kachel:…"]` |
| `read:<app>` / `write:<app>` | apps | assistant, other apps | rights `kalender:lesen` … |
| `print`, `scan` | adapters per device | apps, AI tools | planned ([../open/printer_adapter.md](../open/printer_adapter.md)) |
| hardware: `mic`, `speaker`, `display`, `gpio` | nodes (detected in `core/knoten.py`) | apps | rights `mikro`, `lautsprecher` |
| link: `lan`, `wifi`, `wireguard`, `tailscale`, `bluetooth`, `usb`, `cable`, `power` | nodes, devices | nodes, devices | `netz` in the node description |

A new port type = one entry in the port schema + a test vector + a reader on each side. Same procedure as a new colour role or building block.
**Built (step 9):** registry `contracts/ports/1/types.json`; how the vocabulary was cut and why: [port_types.md](port_types.md).

### 1.4 Where each wire lives (one truth, no second store)

The wire has exactly one owner, and the owner follows the rule from
[standort_und_app.md](standort_und_app.md):

| Wire | Owner | Synced? | Lives in (today) |
|---|---|---|---|
| app stationed on a node, app `data` → `sync` | the node (frame) | no — per node is legitimate here | register `apps-<node>.json`, `abgleich_apps` |
| node hardware port → app (mic → tutor) | the node | no | (new, in the node frame) |
| app instance → provider (calendar ← google, PDF viewer ← cloud folder, assistant ← model) | the consumer app instance | **yes, without mercy** | `quelle` in `kalender-<id>.json`; new wires in the instance settings |
| node ↔ node / device (LAN, VPN, cable, power) | observed: the node description; physical: the wiring-map app | yes | `knoten/<name>.json` `netz`; new `data/wiring/things/*.json` |

The hub offers **one view over all of them**: `GET /api/wires` (list) and
`PUT /api/wires/<id>` / `DELETE` (rewire; `/api/`: `/hub/…` is the apps' side). These routes *project* the
existing settings and write back into them. `abgleich_apps` and the
calendar `quelle` stay the stored truth, with no wire file next to them.
Every write passes the check gate of section 6.7.

Wire record (JSON, schema `contracts/ports/1/ports.schema.json` `$defs/wire`, 2020-12):

```json
{"id": "w-tutor-data-sync",
 "from": "zentrale://cloud/port/sync",
 "to": "zentrale://tutor/port/data",
 "type": "sync", "owner": "node:minipc",
 "state": "live", "seen": "2026-10-30T09:15:00Z"}
```

`state` ∈ `live` (has effect), `off` (declared, unplugged), `broken`
(provider gone or contract too new — section 2). Planned things are not
wires yet; they live only on the map (section 6.3).

### 1.5 What changes in today's model

| Today | Becomes | Cost |
|---|---|---|
| `rechte` (needs) and `liefert` (offers) in `app.toml` | stay readable; new English keys `needs` / `offers` with port types; the renaming wave drops the old ones | small, reader in `core/apps.py` |
| `[daten] muster` | the implementation of the `data` port; positive list stays the lock (deny by default) | none |
| `cloud` = built-in "service" in `core/eingebaute_apps.py`, `cloud_an()` | a provider piece offering `sync`; store item, preinstalled at signup (section 4) | small |
| "new app with data asks once: sync it?" | = the hub proposes a wire `data → sync`; same question, same place | none |
| calendar `quelle` google/zencloud/lokal | a `calendar-source` wire of the calendar instance | none (projection only) |
| rights word names an app (`kalender:lesen`) | allowed as "wire to that app"; new apps say `read:calendar` and the user picks the provider | small |
| rights dialog missing | the install dialog *is* the plug dialog: list needed ports, propose providers, user confirms | built `ec0020a` |

## 2. Contracts and versioning — no forced updates

### 2.1 What a contract is

Every port type and every protocol between pieces is a **contract** with a
name and a SemVer version, described in a standard (OpenAPI 3.1, JSON
Schema 2020-12) and shipped with **test vectors**. Today's contracts:

| Contract | Version today | Description | Vectors today |
|---|---|---|---|
| cloud API | path `/v1` | `server/openapi.yaml` | `contracts/account-keys/1/konto_testvektoren.json` |
| key schema | HKDF infos `…/v1` | [knoten_beitritt.md](knoten_beitritt.md) | same |
| Mitte format (`inhalt.enc`, envelope, hidden names) | `"format": 1` | [../betrieb/abgleich.md](../betrieb/abgleich.md) | `contracts/cloud-sync/1/mitte_testvektoren.json` |
| node description | none | `core/knoten.py` | none |
| manifest `app.toml` | none (`motor = "1"` planned) | [hub_bauplan.md](hub_bauplan.md) | none |
| tiles / views | `zentrale_kachel.v = 2` | `openapi.yaml` | none |
| calendar app setting | `zentrale-kalender-app/1` | `core/kalender_einstellung.schema.json` | calendar vectors |
| app data | per app | per app | calendar, colours |

### 2.2 The rules

1. **Within a major version only additive changes.** New optional fields,
   new port types, new routes. Never rename, never make optional required,
   never change meaning.
2. **Must-ignore, must-preserve.** A reader ignores unknown fields *and
   writes them back unchanged*. Without the second half, an old node
   rewriting a JSON file would delete what a new node added.
3. **Unknown major → read-only, never misread.** A reader that sees a major
   it does not know does not write that file/port and says so once
   (`zentrale status`: "calendar data is newer than this version — read
   only"). Built in step 5 (`a6f37db`): `core/formats.py` for every
   `format` field — `inhalt.enc`, envelopes, `konto.json`, adapter, calendar
   setting, side file, colours; `tests/test_formats.py` per format.
4. **A new major runs in parallel.** Cloud: `/v2` next to `/v1`, both
   served. App data: the new app version writes the new form *and* keeps the
   old form updated (down-projection) for the whole support window; an old
   node keeps reading and writing the old form, the new one merges it in.
   Majors are expensive by design — the rule says "avoid them".
5. **Versions do not sync between nodes — by default.** Which version of the
   platform or of an app runs is part of the node frame. Data and settings
   sync; code versions don't. Sasha 30.10.: *settable*, in Schematix: a
   "same version" wire between nodes (or a group) makes them follow each
   other. (Answers question 6 of [app_motor_plan.md](app_motor_plan.md).)
6. **Packages depend on contracts, never on other packages.** The tutor
   needs `model ^1` and `data ^1`, not "adapter 0.7". That keeps the
   compatibility question linear: contract × reader, not package × package.

### 2.3 Support window: forever (Sasha 30.10.)

**Every released version keeps syncing forever.** How that stays possible:

- **No major is ever switched off.** A new major ships with one
  **translator** to the previous major (up and down, a pure function with
  its own vectors). Old majors are served through the chain v1↔v2↔v3, so
  each new major adds one translator, never a rewrite of old ones.
- **Majors stay rare** (rule 4): the chain only grows when a contract
  really cannot grow additively.
- **The old-release test covers every release ever published**, not a
  window (section 2.4). A release that breaks any old one is not published.
- **The one exception is security, and even it does not force:** if an
  old version's crypto is found broken, the cloud keeps serving it but
  marks the node "insecure" (Schematix, `status`, `devices`); the owner
  decides whether to update or remove it. The headers `Deprecation`
  (RFC 9745) carry that warning; `Sunset` is never sent. Built `d1dc8fd`: D1
  table `insecure_releases` (data), header `Zentrale-Release`, `server/README.md`.
- An old node lacks new features, nothing else: an unknown port type shows `broken` ("needs a newer ZENTRALE").

### 2.4 How it is tested

| Test | What it proves | Where |
|---|---|---|
| **Contract vectors** — one folder per contract and major: request → response, file → parsed, merge in → merge out | every implementation (Python core, Dart phone, TS server) agrees byte for byte | `contracts/<name>/<major>/` (built `b64f3e4`: vector files moved there; translator chain `core/translators.py`) |
| **Preserve test** — each reader loads a file with extra unknown fields, writes it, fields are still there | rule 2 | generated per JSON schema |
| **Old-release test** — CI keeps every released tarball; two fake devices, one on release N−k, one on HEAD, sync against the fake cloud and against the local worker, both converge, nothing lost | rule 1–4 end to end | `tests/test_alte_fassung.py` (built `b64f3e4`: releases 37–41 vs HEAD, fake cloud; local worker not yet), tarballs rebuilt from git into `dist/releases/` (`scripts/release_archive.py`) |
| **Server keeps old majors** — the vitest suite runs every supported major's vectors | the cloud never drops a version early | `server/test/` |

A release is not published if the old-release test is red for any
earlier release.

## 3. Packaging — tiny core, everything else packages

### 3.1 The core ("raw ZENTRALE", the frame per node)

Only what a node needs to exist, join and heal itself:

- the command `zentrale` (terminal fallback, always present — leitbild),
- hub door: manifest reader, register, port/wire checks, `/hub/*` routes,
- store client (catalog, install, update, remove),
- account + cloud client + Mitte (the sync engine; the *cloud piece* is the
  app that uses it — section 4),
- the mandatory adapter,
- the **keeper**: timers for update, sync, calendar bridge (section 5.2),
- node description and hardware detection.

Everything else — calendar, lists, notes, graphs, assistant, desk,
workshop, mail, piano, tutor, map, wiring map — is a package. Today they
are still inside the core ([kern_auszug_inventur.md](kern_auszug_inventur.md));
they leave one by one as the extraction goes on.

### 3.2 A "full update" is just a bundle

- **Bundle** = a list of `package@version`, as a schema.org `ItemList` (like
  the catalog and ownership). The release "41" becomes the bundle
  `everything@41`: `core@41` + the built-in apps at their versions.
- **Default for everyone:** follow the bundle, automatically (section 5.3).
- **Pick parts:** in the store, per app "hold at this version" or "don't
  install". The core is never held by the store — it updates by its own
  setting (section 5.3), because the store runs on it.
- Because of rule 6 (packages depend only on contracts), a held app keeps
  working as long as the contracts it needs are still offered — and rule 1
  says they are, within a major.

### 3.3 Is that too complicated? Recommendation

Separate packages are only worth something once an app has actually left
the core. Until then, splitting the tarball would add work and no choice.
So:

1. **Now (built `e24374f`):** one tarball, with `BUNDLE.json` inside (core +
   built-in apps at the release, extracted apps without a version).
2. **Per extracted app:** its own catalog package (tutor, map, budget are own
   repos), installable and holdable. `eingebaute_apps.py` shrinks.
3. **"Pick parts" UI** only when at least three apps are separate.
4. **Not built:** dependency solver, version ranges between packages,
   partial core updates. Rule 6 makes them unnecessary — that is what keeps
   the split cheap.

## 4. The cloud is a store app, preinstalled at signup

- The store catalog gets two items in category apps: **Cloud** (`cloud`,
  offers `sync`, account + devices + usage watch) and **Cloud folder**
  (`cloud_folder`, offers `files` + `data`). Both stay inside the core
  package for now (built-in), but they are listed, installed and removable
  like any app.
- **Signup / login installs `cloud`** on that node and marks it owned
  (`/v1/besitz`, `core/account_ownership.py`). Removing it = the node stays
  local, nothing deleted in the cloud. Built `79482b5` ([shop.md](shop.md)).
- `cloud_folder` is offered right after signup ("a folder that syncs") —
  one question, default yes.
- Ownership belongs to the account, installation to the node (decided
  22.10.); a new node sees what the account owns and asks "what do you
  plan here?" (stationing, [standort_und_app.md](standort_und_app.md)).

## 5. Node lifecycle — the consumer journey

Sasha with the Mini-PC is the consumer. Each step: what the person does,
what ZENTRALE does, what exists.

### 5.1 The journey

| # | Step | Person does | ZENTRALE does | Today |
|---|---|---|---|---|
| 1 | **Install** | runs the installer with the invite code | checks Python, unpacks, venv, links `zentrale`, **installs the keeper timers**, starts the setup wizard | yes (keeper `13235f8`; wizard when a terminal is attached `527afc3`) |
| 2 | **Account** | setup wizard: create or log in (or stay local) | keys on the device, session in `konto.json`, installs the **cloud** app, registers the node (`PUT /v1/knoten`) | yes (cloud as store app: `79482b5`) |
| 3 | **Cloud** | nothing | first sync: cloud wins, local versions set aside; offers the cloud folder | yes (cloud folder: wizard step, `527afc3`) |
| 4 | **Apps** | picks apps in the store or "what do you plan here?" | install dialog = plug dialog: needed ports, providers proposed (data → sync yes), confirm; app appears in the wheel | install yes; owned-app offer `79482b5`; plug dialog `ec0020a` |
| 5 | **Updates** | nothing (or turns auto-update off) | core: by setting; apps: follow bundle, holds respected; never forced; old versions keep syncing in the window | core: timer, setting, self-test (`527afc3`); apps: follow repo, holds (`e24374f`) |
| 6 | **Second device** | same as 1–2 on the new device | node joins, cloud wins, owned apps offered, same app settings everywhere | yes (owned apps offered: `79482b5`) |
| 7 | **Remove a device** | on the device: `zentrale leave`; from another: `zentrale devices remove <name>` | leave: logout, timers off, local data kept or deleted on request; remove: end that node's sessions, tombstone its description, drop it from the map; for a lost or stolen device the dialog offers "also change the account key" (Sasha 30.10.: only then, never on every removal) | built `d1dc8fd` (key change: `core/key_rotation.py`, `PUT /v1/konto/schluessel`) |

### 5.2 What keeps a node alive

| Unit (systemd **user**) | When | Runs | Today |
|---|---|---|---|
| `zentrale-update.timer` | daily, random delay up to 1 h | `zentrale update --automatic` | `527afc3` (`RandomizedDelaySec=1h`) |
| `zentrale-abgleich.timer` | every 5 min | `zentrale sync --automatic` | release 41; installer + every update since `13235f8` |
| `zentrale-kalender-sync.timer` | every 3 min | `zentrale adapter run` | release 41; installer + every update since `13235f8` |
| `zentrale-kern.service` (backend) | only for node kinds that serve others (brain, wall display) | the backend | only in Sasha's checkout (`deploy/`) |

- **Installed by the installer, not by setup** (install.sh: built `13235f8`). `install.sh` (and the
  .deb/PKGBUILD post-install for the user) calls `zentrale timers install`
  right after linking. Before login the sync timer simply returns (it
  already does: no session → exit 0).
- **Every update re-runs `timers install`** (built `13235f8`: the NEW release's, idempotent). So a unit added
  in a later release reaches every node that updates. Nodes updated by OLD code heal: the sync
  timer (new code via `aktuell`) re-runs it once when the release changed (`keeper.json`, `527afc3`).
- **Linger:** user timers stop at logout and don't start before login.
  The wizard (`527afc3`) asks once to enable lingering for the own user (needs no
  root on systemd distributions where the polkit default allows it for the
  own user; otherwise one sentence how to do it, and `status` says "syncs
  only while you are logged in"). Never sudo (`loginctl --no-ask-password`).
- **Health shows up**: the node description gets `zuletzt_gesehen` on every
  sync; `zentrale devices` (and the map) shows "mini — last seen 6 days
  ago" in a warning colour after 1 day.

### 5.4 Dev installer mode (Sasha 30.10.)

Run through every mode of the journey without reinstalling. `zentrale dev`
creates **profiles**: each one an isolated ZENTRALE home (own data and
config folder, own fake systemd, fake cloud or a test account), made and
reset in seconds. A profile can start at any state: fresh, wizard step *n*,
logged in, on an old release *N*, offline, removed. `dev update N→M` plays
an update with local tarballs, self-test and keeper included. Built on the
same fakes as the tests (fake cloud, fake systemctl), so what Sasha clicks
through is what CI checks. Never touches the real installation. **Built** `13235f8`: [../betrieb/dev_mode.md](../betrieb/dev_mode.md).

**Setup wizard** (Sasha 30.10.): every first-run question in one guided
dialog, step by step, back allowed, defaults pre-selected: account (create /
log in / local) → cloud folder → **auto-update** → keep syncing when logged
out (linger) → what is this device for (stationing, apps). Same steps in
TUI and phone, strings through the translation table, re-openable later
from the settings. **Built** `527afc3` (`zentrale_cli/wizard.py`, CLI; no TUI setup exists yet).

### 5.3 Platform updates by setting

- Setting `auto_update` (node frame), first asked in the wizard (default
  **on**). Shown in `zentrale status`, switchable later with
  `zentrale update auto on|off`, in the TUI and in Schematix.
- `--automatic`: fetch `/v1/paket`, nothing new → exit quietly. New →
  download beside, sha256 (later Ed25519 signature,
  [../open/phone_self_update_hardening.md](../open/phone_self_update_hardening.md)),
  venv, **self-test** of the new version (`zentrale version --check`:
  imports, reads settings, reaches the cloud), only then switch `aktuell`,
  re-run `timers install`, restart a running backend. Self-test fails →
  stay on the old version, one note. The previous version stays for a
  manual roll-back (exists today). **Built `527afc3`** (state in `update.json`).
- Off: `status` and the start line before the TUI say "update available: 39 → 43",
  nothing else happens (inside the TUI: not yet).
- apt/pacman: the setting only shows the hint; the package manager updates
  (exists today: `update` refuses there).

## 6. The wiring map on the Desk

Sasha: *„ein schaltplan skizzierer … mit zentrale apps, logik … sachen
reinlegen, rumstecken, gucken was worüber läuft, auf hardware und software
ebene, sachen markieren als not yet, falls man es nur plant, verschiedene
ebenen, tailscale, lan, kabel, bluetooth, verbindungen, strom."*

Not the geographic map app `zentrale-karte` ([../maps/INDEX.md](../maps/INDEX.md)).
This is the app **Schematix** (code `schematix`). One plan in it is a
**scheme**; creating and editing schemes is **scheming** (German
„schemen", Sasha 30.10. — a pun on the English word). Built on the Desk
([desk_view.md](desk_view.md)) — Sasha 29.10.: an app, not needed everywhere.
Look: [schematix_style.md](schematix_style.md); the app as built: [schematix.md](schematix.md).

### 6.1 The key rule: the drawing IS the wiring

- A piece on the map is a **reference** (`zentrale://…` address) to the real
  object: an app instance, a node, a port, a documented device. Never a
  copy. Same pattern as Desk tiles (`zentrale_kachel.adresse`).
- Real wires are **derived** from `GET /api/wires` on every draw, like Desk
  strings are laid fresh from positions. The file stores them only as a
  display fallback for Obsidian, rewritten from the truth on save.
- Drawing changes only the **sketch**. Nothing switches until you press
  **Run** (Sasha: "kompilieren" = "ausführen"), which checks the sketch
  and only then switches ZENTRALE over to it (section 6.7). Unplugging the
  tutor from the cloud and running it ends up exactly as
  `abgleich_apps["tutor"] = false`, and `zentrale status` shows the same.
- Changed elsewhere (CLI, store dialog, other node) → the next draw shows
  it. Those changes pass the same check (one way for every change). The map
  can only differ from reality in planned things and in a sketch you have
  not run yet.

### 6.2 Layers

| Layer | Wires / pieces | Source of truth |
|---|---|---|
| software: data & sync | `data`, `files`, `sync` | `abgleich_apps`, register, `[daten]` |
| software: services | `model`, `calendar-source`, `read:*`, `event:*`, `tile:*` | app instance settings, adapter |
| hardware ports | `mic`, `speaker`, `display`, `gpio`, `print`, `scan` | node description (detected), adapters |
| network | `lan`, `wifi`, `wireguard`, `tailscale`, `bluetooth`, `usb` | node description `netz` (observed), map app (documented) |
| hardware (things) | router, switch, cable, power bank, charger — **own pieces** on this layer (Sasha 30.10.), not notes on a node | map app (documented) |

Layers toggle on and off (one key per layer); each layer has a colour
role. Each wire shows what runs over it right now where known: "sync ✓
10:15", "bridge: laptop", "offline 6 d". Tailscale is live today (mini ↔
tablet), WireGuard from heimnetz.md is planned.

**Versions panel:** every node piece folds open to show its ZENTRALE
version, each app version, which contract majors it speaks, what it
cannot do yet ("no wiring map: needs ≥ 44") and its `auto_update` and
"same version" settings — switchable right there.

### 6.3 States: live, documented, planned ("not yet")

| State | Meaning | Stored where | Drawn |
|---|---|---|---|
| **live** | exists and has effect | its owner (section 1.4) | normal |
| **documented** | real but outside software (router, cable, power bank) | `data/wiring/things/<id>.json` (map app data, synced, JSON Schema) | normal, own frame role |
| **planned** | only intended | only in the canvas file (`"state": "planned"`) | faint + label "not yet" |

- A planned piece can carry the address it *will* have (store item, node
  name from [../system/heimnetz.md](../system/heimnetz.md)). When that object
  appears (app installed, node joined), the piece turns live by itself —
  same reference, nothing redrawn.
- Placing a store app that is not installed puts it as planned; its
  action "install" runs the normal store install with the plug dialog.
- A planned wire between live pieces has no effect until "make real".

### 6.4 Data model: JSON Canvas 1.0

One map = one `.canvas` file in the map app's data folder (synced), so
Obsidian opens it. Standard fields only; the typed data sits under **one
namespaced key `zentrale`** per node and edge (the spec is silent on extra
fields), with the port ids next to `fromSide`/`toSide`.

```json
{"nodes": [
  {"id": "g-home", "type": "group", "label": "Home", "x": 0, "y": 0, "width": 900, "height": 500},
  {"id": "n-tutor", "type": "text", "text": "Tutor", "x": 300, "y": 60, "width": 160, "height": 60,
   "zentrale": {"ref": "zentrale://tutor/", "on": "zentrale://hub/node/minipc"}},
  {"id": "n-router", "type": "text", "text": "Router (Flint 2)", "x": 40, "y": 300, "width": 200, "height": 60,
   "zentrale": {"state": "planned", "kind": "device:router@1"}}],
 "edges": [
  {"id": "e-sync", "fromNode": "n-tutor", "toNode": "n-cloud", "label": "data → sync", "color": "4",
   "zentrale": {"wire": "w-tutor-data-sync", "layer": "sync", "fromPort": "data", "toPort": "sync"}}]}
```

Risk: some editors drop unknown keys when they save. A load → save
round-trip test (Obsidian included) decides; fallback is a sidecar file
keyed by node id next to the canvas.

- **Groups** (`type: "group"`) are places: home, desk, bag, a room (stage 2 of the leitbild).
- **Edges** carry the layer; `color` is only the Obsidian fallback, ZENTRALE draws by colour role.

### 6.5 Pieces in the `+` picker

`GET /api/pieces` lists everything placeable, fresh on every `+` (like the
tile catalog): installed apps with their ports, preinstalled providers
(cloud, cloud folder, adapter and its connections), nodes from
`GET /v1/knoten`, store apps not installed (placed as planned), and device
kinds for documented things (router, switch, printer, power bank, cable,
Bluetooth device). A new app shows up by itself.

### 6.6 First content

The map app ships one starter desk "Home network" generated from
[../system/heimnetz.md](../system/heimnetz.md): router `.254`, PC `.1`, Pi
`.10`, laptop `.20`, mini `.21`, WireGuard, power bank — all planned except
the nodes that already report to the cloud. heimnetz.md stays the plan
text; the map is where its pieces get ticked off by becoming live.

### 6.7 Run: sketch → check → diff → switch

Sasha: *„wir müssen sicherstellen, dass niemand je in der lage ist, einen
kaputten sketch zu compilen und sein netzwerk voll zu verbuggen."* Priority
is the type check. **No own language and no own format:** we take existing
concepts and standards (below) and write only the checks.

**Format & type system** (research 2026-10-30, merged by the coordinator):

- **Concepts, not runtimes:** the topology model of
  [TOSCA v2.0](https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html)
  (node types; capabilities = offers; requirements = needs; relationship
  types), the generations of [NixOS](https://nixos.org/manual/nixos/stable/)
  (build → atomic switch → roll-back) and the physical vocabulary of
  [NetBox](https://netboxlabs.com/docs/netbox/) (cables, power ports,
  interfaces). Not their tools: TOSCA tooling is Go only
  ([Puccini](https://github.com/tliron/puccini)), no Dart; NixOS is its own
  language and Linux only. Node-RED and Home Assistant are untyped; Modelica
  and SysML v2 are full languages without an apply step.
- **Canvas:** [JSON Canvas 1.0](https://jsoncanvas.org/spec/1.0/) with the
  `zentrale` key (section 6.4).
- **Types:** a **type registry in JSON Schema 2020-12** using the TOSCA
  terms, plus the layer types (power, cable, LAN, Tailscale, Bluetooth …).
  Each app manifest is JSON checked against it. Every type has a SemVer
  version; requirements carry ranges (`storage@^1`). That is also the
  no-forced-updates mechanism of section 2. JSON Schema because it is the
  only choice with solid validators in both Python (`jsonschema`) and Dart
  ([`json_schema` 5.x](https://pub.dev/packages/json_schema/changelog), with
  the 2020-12 draft set); CUE, Pkl, KCL, Nickel and Dhall have no or weak
  Dart support.
- **Main risk:** the type vocabulary itself, too loose or too rigid. It is
  designed early with TOSCA/NetBox terms (build step 9).

**The pipeline.** For the user it is one action, **Run**. Inside it has
five stages, and stages 2–3 are the hard gate:

| # | Stage | What happens | Where |
|---|---|---|---|
| 1 | **Sketch** | a wire whose types don't fit **cannot be connected at all** (Sasha 2026-10-30): while dragging it over an unfitting socket the cursor shows a small red ✕; dropping it there does not attach and shows a short error at the socket ("PDF viewer needs `files`, cloud offers `sync`"). Source: a small capability ↔ requirement table per layer. This is convenience, not the guarantee | every surface (TUI, phone) |
| 2 | **Item check** | each piece and wire against its JSON Schema | Python and Dart, on every node |
| 3 | **Compile** (the gate) | graph rules no schema language can express: every non-planned requirement fulfilled exactly once; no forbidden cycles; one owner per resource; version ranges satisfied for the node it runs on (from the node description). **Any error → no output**, with the errors pinned to the pieces on the map | Python only, own code (~200–400 lines) |
| 4 | **Plan / diff** | the result is a self-contained, hashed **generation** file (plain JSON); shown as a diff against the current generation, in the [OpenTofu](https://opentofu.org/docs/)/Terraform plan style: "+ tutor data → cloud sync on minipc, − calendar ← google" | core |
| 5 | **Switch** | confirm → the "current" pointer per node flips atomically to the new generation; the last N generations are kept. Each node runs a reconcile loop toward its current generation (Kubernetes style, see its [admission checks](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)), writing the existing owners (`abgleich_apps`, calendar `quelle` …). A failed health check → back to the previous generation, with a note | apply agent per node, inside the keeper (section 5.2) |

- **Planned items** go through stages 2–3 like everything else (a broken
  plan is still broken) but are never applied. If anything live depends on
  a planned item, the compile fails: "router is not yet — the mini's LAN
  wire can't be live".
- **One way for every change:** the CLI (`zentrale sync` choice), the store
  plug dialog and the map all produce a new generation through the same
  gate. Nothing writes the owners around it.
- **Nodes on older versions:** the compiler reads each node's supported
  type versions from its node description (new field). A wire that needs a
  newer type on an old node is a compile error unless it is marked planned
  ("not yet: needs update on mini"). Inside a major the old node applies
  what it knows and leaves the rest (rule 1 of section 2). A node from before
  the apply agent ignores generations and keeps its settings. The compiler
  treats it as unmanaged: read-only on the map, never targeted, never
  broken by someone else's run.

**What we write ourselves:** the type registry (schema files), the
compiler with its graph checks, the socket table for the editors, and the apply agent with the generation pointer. That is all. No new language.
**Built (9/9b, `6a63d16`; 11, `ec0020a`):** registry, compiler, generations, apply agent (on the keeper since 11), fed by the CLI sync choice, `adapter calendar` and the plug dialog — [port_types.md](port_types.md).

## 7. What exists vs. what is missing

| Part | Exists | Missing |
|---|---|---|
| install | `install.sh`, sha256, venv, link, PATH hint, keeper timers, wizard + linger (`527afc3`) | — |
| account/cloud | Zero-Knowledge account, `HttpMitte`, node description, `devices`; cloud + cloud folder as store items, account ownership (`79482b5`) | one ownership truth (shop files vs. `/v1/besitz`) |
| sync | per-app choice, cloud wins, held-back files | — (format read rule + preserve test: `a6f37db`) |
| timers | `zentrale timers` (sync, calendar, update), installer call, re-run on every update, self-heal (`527afc3`) | — |
| update | `zentrale update` (beside, switch, roll-back by hand), `--automatic`, setting, self-test, hint (`527afc3`) | Ed25519 signature; hint inside the TUI |
| versioning | `/v1`, HKDF `/v1`, `format` fields, several vector files | policy (insecure warning: `d1dc8fd`; contract folder, old-release test: `b64f3e4`) |
| packaging | one tarball, `deploy/paket.txt`, `BUNDLE.json`, holds (`e24374f`) | per-app packages as apps leave |
| plugs | `rechte`, `liefert`, `[daten]`, calendar `quelle`, positive list; port schema, `needs`/`offers`, `/api/wires` (`6a63d16`); plug dialog (`ec0020a`) | — |
| lifecycle | join by login; `leave`, `devices remove`, removed sessions, tombstone, key change for lost/stolen (`d1dc8fd`) | Schematix display |
| wiring map | Desk (JSON Canvas, strings, tiles, references), node descriptions; Schematix v1 (step 13) | planned state, things store |
| run pipeline | type registry, compiler, generations, apply agent (`6a63d16`), on the keeper timer (`ec0020a`) | socket table in the editors, Dart port of the rules ([../open/run_gate_followups.md](../open/run_gate_followups.md)) |

## 8. Build order — small steps, each with its acceptance test

Each step ships on its own; earlier steps never wait for later ones.

| # | Step | Acceptance test |
|---|---|---|
| 0 | **Built `13235f8`.** **Dev installer mode** (section 5.4): profiles, start states, `dev update N→M` | a fresh profile runs the wizard to the end (wizard part: `527afc3`) and is reset in < 10 s; the real installation is untouched |
| 1 | **Built `13235f8`.** **Keeper in the installer**: `install.sh` calls `zentrale timers install`; `update` re-runs it | test with fake systemctl: fresh install → both units rendered and enabled before login; update from a release without a unit → unit appears |
| 2 | **Built `527afc3`.** **Update timer + setting + setup wizard**: `zentrale-update` unit, `update --automatic`, `auto_update` asked in the wizard (default on), self-test, hint when off | fake cloud with N+1 → switched and self-test ran; broken N+1 → stays on N with one note; setting off → only "update available" in `status` |
| 3 | **Built `527afc3`.** **Linger question** in installer and `setup`, `status` line when off | with linger on, a test session-less run fires the sync unit; off → `status` says "only while logged in" |
| 4 | **Mini-PC by hand once** ([../open/minipc_finish_setup.md](../open/minipc_finish_setup.md)): update to the release with steps 1–3 | after a reboot without login, `zentrale devices` on the laptop shows the mini seen < 10 min ago |
| 5 | **Built `a6f37db`.** **Read rule for formats**: unknown major → read-only + note (`inhalt.enc` first, then every `format` field); preserve-unknown-fields test per schema | vector with `"format": 2` → old reader writes nothing and warns; extra fields survive a write |
| 6 | **Built `b64f3e4`.** **Contract folder + old-release test**: `contracts/<name>/<major>/`, archive of every released tarball, `tests/test_alte_fassung.py` | HEAD and release N−1 converge on two fake devices; publishing script refuses when red |
| 7 | **Built `d1dc8fd`.** **Insecure-node warning** (`Deprecation` header, never `Sunset`) and its display in client and Schematix | server test marks a release insecure → `status` warns, sync keeps working |
| 8 | **Built `d1dc8fd`.** **Leave and remove**: `zentrale leave`, `zentrale devices remove`, server route to end a node's sessions, tombstone in `knoten/`; after it, key rotation as an option in the removal dialog for lost/stolen devices (Sasha 30.10.) | removed node's next sync gets 401 and says "this device was removed"; tombstone visible in `devices` |
| 9 | **Built `6a63d16`.** **Type registry first** (TOSCA/NetBox terms, JSON Schema 2020-12, SemVer per type), then ports in manifests: `needs`/`offers` read (old keys too), built-in apps declare them; `GET /api/wires` projects `abgleich_apps` + calendar `quelle` | every built-in manifest validates in Python and Dart; projection round-trip: write the projected wires back → settings byte-identical |
| 9b | **Built `6a63d16`.** **Compiler + generations + apply agent** (section 6.7), first fed only by the CLI sync choice | a set of broken sketches (double owner, unmet requirement, live depends on planned, too-new type on an old node) all fail with no output; a good one switches and a failed health check rolls back |
| 10 | **Built `79482b5`.** **Cloud and cloud folder as store items**, installed at signup, ownership via `/v1/besitz` | fresh account → store shows both installed; second device offers owned apps |
| 11 | **Built `ec0020a`.** **Plug dialog** at install (= rights dialog) | installing an app with `needs = ["model"]` lists providers; refusing leaves the app installed but that port `off` |
| 12 | **Built `e24374f`.** **Bundle file** in the package; store shows per-app hold for extracted apps | built package contains `BUNDLE.json` matching `deploy/RELEASE`; held app is skipped by the automatic update |
| 13 | **Built (see History).** **Schematix v1, read-only** (look: Sasha's style): app `schematix`, versions panel, Desk kinds `piece`/`wire`, layers, `/hub/pieces` | map of Sasha's account shows laptop, mini, apps and sync wires exactly as `zentrale status` on each node |
| 14 | **Schematix v2**: planned and documented pieces, things store, starter desk from heimnetz.md | planned router drawn as "not yet"; joining a node turns its planned piece live; Obsidian opens the file |
| 15 | **Schematix v3, rewire by drawing**: unfitting wires refused (red ✕ cursor, short error on drop), Run = check → diff → switch | unplug tutor → sync on the map, Run, the diff shows one line; after the switch `zentrale status` on that node shows "stays on this device" |

**Final acceptance — fresh reinstall on the Mini-PC, no manual work:**
remove the installation on the mini (cloud data untouched), run the
installer with an invite code, log in once in `setup` — and then type
nothing more. Reboot without logging in. Within 10 minutes the laptop's
`zentrale devices` shows the mini as seen just now; a list change on the
laptop is on the mini within 10 minutes; a newly published release is
running on the mini within 25 hours. Steps 1–4 are enough for this; the
rest builds on a node that stays alive.

## History

- **2026-10-30** — written after the Mini-PC check (installed, synced once,
  then silent) and Sasha's points on consumer view, auto-update setting, no
  forced updates, decomposed updates, plug model and wiring map.
- **2026-10-30** — Sasha's answers: support forever (translator chain),
  setup wizard, dev installer mode, version sync settable in Schematix with
  a versions panel, name Schematix / schemes, things as own hardware pieces,
  Tailscale live; refused wires instead of greyed sockets.
- **2026-10-30** — steps 0 and 1 built (`13235f8`), steps 2 and 3 (`527afc3`); key rotation decided (option for lost/stolen devices, after step 8); steps 7 and 8 built (`d1dc8fd`), key change on the unchanged key schema; steps 5 and 6 built (`a6f37db`, `b64f3e4`); steps 9 and 9b built (`6a63d16`): type registry, compiler, Run gate ([port_types.md](port_types.md)); steps 10 and 12 (`79482b5`, `e24374f`); step 11 (`ec0020a`): plug dialog, apply agent on the keeper, node wires in the description; step 13: Schematix v1 ([schematix.md](schematix.md)).
