# Piece descriptions — any program or device as a piece, and the Schematix inventory (plan)

**Stand 2026-10-31: plan only, nothing built.** Owner: Sasha. Builds on the
building kit ([building_kit_plan.md](building_kit_plan.md): pieces, ports,
wires, Run gate — [port_types.md](port_types.md)) and on Schematix
([schematix.md](schematix.md)). Respects the permanent rule "apps live
outside the core" (CLAUDE.md) and the pending
[Schematix extraction](../open/schematix_extraction.md). Open decisions:
[../open/piece_descriptions_decisions.md](../open/piece_descriptions_decisions.md).

Sasha, 2026-10-31: *„neue programme, scheiß egal welche und woher, auslesen
und somewhat interpreten können … ich lade etwas neu runter. ich will es im
scheme drankabeln … entweder die app gibt sauber aus was sie ist und kann,
oder schematix rät es."* And: *„wir sollten das deuten und seine architektur
rolle klären, weil jetzt steht es zwischen app, kern, ki … das is cluttered."*

## 1. The problem

Schematix can place only what ZENTRALE already knows: its own apps (from
`app.toml`), nodes, store apps and ten hand-written device kinds
(`contracts/schematix/1/kinds.json`). Sasha downloads programs from
anywhere — apt, Flatpak, an AppImage, a tarball — and wants to wire them
in a scheme like everything else. For that every program or device must
show up as **one object** with a name, an icon, what it is, what it can and
cannot do, and typed ports — and every part of that object must be editable.

"Describing" today would fall between three chairs: the app (knows itself),
the core (owns pieces and the gate), the KI (can guess). The cut below gives
each one exactly one job.

## 2. The cut — describing is a capability with providers

Same plug principle as everywhere else (building kit 1.1, adapter
capabilities: the tool hangs on `print`, never on the printer model):
**describing is a port type `describe`; describers are providers that offer
it; the core only owns the format, the register and the gate.**

```
 CONSUMERS (read the register, never describe themselves)
 ┌───────────────────┐ ┌───────────┐ ┌─────────────┐ ┌──────────────┐
 │ Schematix          │ │ Store     │ │ Plug dialog │ │ KI assistant │
 │ inventory (i),     │ │ (cards)   │ │ (providers) │ │ (what is X?) │
 │ edit on the board  │ │           │ │             │ │              │
 └─────────┬─────────┘ └─────┬─────┘ └──────┬──────┘ └──────┬───────┘
           │ GET /api/descriptions?q=…   ·  PUT …/<id>/edits │
 ══════════╪═════════════════╪══════════════╪═══════════════╪══════════ CORE
 ┌─────────▼─────────────────▼──────────────▼───────────────▼────────┐
 │ 1. piece description FORMAT   (contract, JSON Schema 2020-12)     │
 │ 2. description REGISTER       (derived descriptions + user edits, │
 │                                synced with the account)           │
 │ 3. GATE RE-CHECK              (an edit that changes ports →       │
 │                                every wire re-validated)           │
 └─────────▲─────────────────────────▲─────────────────────▲─────────┘
           │ needs describe@^1       │                     │
 ══════════╪═════════════════════════╪═════════════════════╪══════════ PROVIDERS
 ┌─────────┴─────────┐ ┌─────────────┴───────────┐ ┌───────┴──────────┐
 │ (1) declared       │ │ (2) standard describer  │ │ (3) KI describer │
 │ app.toml / own     │ │ core default adapter,   │ │ own app package, │
 │ description file   │ │ static metadata only,   │ │ needs `model`,   │
 │ — always wins      │ │ never runs the program  │ │ optional, costs  │
 └───────────────────┘ └─────────────────────────┘ └──────────────────┘
```

- **The core never guesses.** It stores, merges layers and checks wires.
- **A describer never stores and never decides.** It answers "here is what
  I can tell, with this confidence"; the register keeps it.
- **A consumer never describes.** Schematix asks the register; when the
  register has nothing, Schematix asks the register to *describe* — the
  register asks its providers in order.

## 3. The format (core contract)

**Proposal:** `contracts/pieces/1/description.schema.json` (JSON Schema
2020-12, `$id urn:zentrale:pieces:description:1`), format
`zentrale-piece-description/1`, read rule of `core/formats.py` (unknown
major → read-only + one note; unknown fields survive a write). Port items
reuse `ports.schema.json` `$defs/need` and `$defs/offer` — no second port
grammar. Not written in this step (docs only).

```json
{
  "format": "zentrale-piece-description/1",
  "id": "program:flatpak/org.gimp.GIMP",
  "kind": "program",
  "name":    {"value": "GIMP", "from": "appstream", "confidence": "high"},
  "icon":    {"value": {"theme": "org.gimp.GIMP"}, "from": "desktop", "confidence": "high"},
  "summary": {"value": "Image editor", "from": "appstream", "confidence": "high"},
  "can": [
    {"value": "open and save PNG, JPEG, TIFF, XCF", "from": "desktop:MimeType", "confidence": "high"},
    {"value": "run plug-ins", "from": "ki", "confidence": "low"}
  ],
  "cannot": [
    {"value": "no network service, nothing to sync", "from": "appstream", "confidence": "medium"}
  ],
  "needs": [
    {"value": {"id": "images", "type": "files", "access": "write"},
     "from": "desktop:MimeType", "confidence": "high"}
  ],
  "offers": [],
  "notes": [
    {"value": "needs a display", "from": "appstream:requires", "confidence": "high",
     "unmapped": true}
  ],
  "source": {
    "keys": ["flatpak:org.gimp.GIMP", "desktop:org.gimp.GIMP.desktop"],
    "version": "3.0.4",
    "seen_on": ["node:laptop"],
    "described": "2026-10-31T10:12:00Z",
    "by": ["standard@1.0.0", "ki-describer@0.1.0"]
  }
}
```

The read rule, field by field:

| Field | Meaning |
|---|---|
| `id` | stable key: `<kind>:<source>/<name>` — `app:tutor`, `program:dpkg/gimp`, `program:flatpak/org.gimp.GIMP`, `program:appimage/<sha256-prefix>`, `device:printer`, `node:minipc` |
| `kind` | `app` (a ZENTRALE app), `program` (anything else that runs on a node), `device` (hardware without ZENTRALE), `node`. On the board, `program` is a fourth piece kind beside the three of [port_types.md](port_types.md) — see 3.1 |
| every content field | `{value, from, confidence}`: **where it came from** (`manifest`, `dpkg`, `pacman`, `desktop`, `appstream`, `man`, `mime`, `flatpak`, `snap`, `device-table`, `ki`, `user`) and **how sure** (`high` · `medium` · `low` · `none`) |
| `needs` / `offers` | port items in exactly the forms of `ports.schema.json`, types only from the registry (`types.json`). A describer may not invent a type |
| `notes` with `unmapped: true` | something real the program needs or does that no port type covers yet (display, internet). Shown on the card, never wireable. Many identical notes across programs are the signal for a new port family — that stays a registry step (building kit 1.3) |
| `source.keys` | every key this program is known under, so a dpkg and a Flatpak install of the same program can be linked later (open question) |
| `source.seen_on` | which nodes have it. A description is **account-wide**; a piece is per node (`program:gimp@laptop`), like `app:tutor@minipc` today |

Confidence is per field, not per description: a name from AppStream is
`high`, a port guessed by the KI is `low`. The UI marks `low` and `none`.

### 3.1 Programs are documented, not live

A foreign program does not speak the hub. ZENTRALE cannot enforce or apply
its wires, so its pieces behave like **things** today (building kit 6.3):
*documented* (it exists, the wire is drawn and checked) or *planned*. The
apply agent never writes them; the compiler still checks every one (type,
version, occurrences, cycles). A program that later ships an `app.toml`
becomes `kind: app` and its wires can go live — same id path, same place.

## 4. Describers — order, confidence, the "?" fallback

The register asks providers in this order and **merges per field**: a field
from a higher tier is never overwritten by a lower tier; a lower tier only
fills fields that are still missing or below `medium`.

| Tier | Provider | Where it lives | What it reads | Confidence |
|---|---|---|---|---|
| 1 declared | the app itself: `app.toml` (`name`, `icon`/`icon_motiv`, `needs`/`offers`, `beschreibung`) or a declared description file in the package (proposal: `piece.json`, the format above) | the package — read by the core manifest reader | the manifest | `high`, **always wins** |
| 2 standard | the **standard describer**, a default adapter of the core (like the mandatory adapter), offers `describe` | core | static metadata only (4.1) | `high`/`medium` by source |
| 3 KI | the **KI describer**, its own app package, needs `model`, offers `describe` | own package, outside the core | only metadata the standard describer collected (section 6) | at most `medium`, ports at most `low` |
| — | nobody knows | — | — | `none`: "?" |

Tier 3 is asked **only** when, after tier 2, `name`, `summary` or both port
lists are still below `medium` — and only when its `model` wire is live and
Sasha allowed it (section 6).

### 4.1 The standard describer — static only

**It never executes the unknown program.** No `--help`, no `--version`, no
dry run, no sandbox start. It reads files that describe the program, and
may ask the package manager's own query function (that runs the package
manager, never the program).

| Evidence | Gives |
|---|---|
| package database (dpkg/apt, pacman) | name, version, summary, description text, section/group, homepage |
| `.desktop` entries (freedesktop) | name, `Icon=`, `Categories=`, `MimeType=` (→ `files` needs with access), `Terminal=` |
| AppStream metainfo | summary, description, `provides` (binaries, media types, D-Bus), `requires`/`recommends` (display, internet, input) |
| manpage | NAME line, SYNOPSIS (first lines only, read as text) |
| file type / MIME of the downloaded file (shared-mime-info magic) | "this is an AppImage / ELF / script / archive" |
| Flatpak / Snap metadata, if present | app id, permissions (`filesystem=`, `network`, `devices=`) — very good evidence for ports |
| hardware icon and kind table | device kinds, their ports (today `kinds.json`) and icons (`device_icons.txt`) |

Mapping evidence to ports is a **table in the describer**, not code per
program (example rows: MIME `image/*` + editor category → `files` write;
Flatpak `filesystem=home` → `files` write; `--device=all` → note; printing
category + CUPS → needs `print`). Anything without a row → `notes`
(`unmapped`).

### 4.2 "?" — when nobody knows

Every field still `none` after all tiers shows **"?"**: icon "?" (a new
`unknown` block in `device_icons.txt`), name = the file name, empty port
lists, summary "Not recognised". The piece can still be placed, edited and
wired by hand — that is the user configuring it (Sasha: *„kann es immer
fragezeichen draufklatschen … das kann der user dann ja selbst
konfigurieren"*).

## 5. The user edit layer and the gate re-check

### 5.1 Edits are a layer, never a copy

The register keeps two things per piece kind (dasselbe Objekt, nicht
kopiert):

- the **derived description** (what the describers said), replaced
  whenever it is re-described;
- the **edits** (what Sasha changed), a separate small record pointing at
  the description by `id`:

```json
{"format": "zentrale-piece-edits/1",
 "of": "program:flatpak/org.gimp.GIMP",
 "base_hash": "sha256:4be1…",
 "set":    {"name": "Gimp (photos)", "icon": {"device": "tower"}},
 "ports":  {"add_needs": [{"id": "scans", "type": "scan"}],
            "remove": ["needs/images"]},
 "edited": "2026-10-31T10:20:00Z"}
```

- **What you see = description ⊕ edits**, resolved on every read. Edited
  fields show `from: user` and are never marked unsure.
- **Re-describing never overwrites an edit.** A new base only changes the
  fields Sasha did not touch. If the base changed under an edit
  (`base_hash` differs), the card shows "the program changed since your
  edit" with the new base value beside his — he keeps his or takes the new.
- **Per kind vs. per piece:** an edit of the description applies to every
  piece of that kind on every node and scheme. Name and icon may also be
  set on one piece only (a key on that canvas node in the scheme); ports
  never per piece — a port belongs to what the program *is*.
- **Synced with the account**, end-to-end encrypted like all `data/`
  (`data/pieces/edits/*.json`; derived descriptions in
  `data/pieces/descriptions/*.json`, also synced so a second node does not
  describe again — proposal, open question).
- **ZENTRALE apps:** name and icon editable; **ports read-only**, because
  the manifest is what the gate enforces on live wires. Programs, devices,
  "?" pieces: everything editable.

### 5.2 What happens to wires on an edit

Every edit that changes ports, and every re-describe that changes ports,
triggers the **gate re-check**: the register compiles every scheme and this
node's projection that contain a piece of that kind (`sketch_compiler`,
the rules of [port_types.md](port_types.md)). Rules:

1. A wire that no longer fits becomes **`broken`** with the reason code it
   failed (`unknown-port`, `type-mismatch`, `version-mismatch`,
   `too-many`). It stays in the scheme, red, pinned on both ends.
2. **Nothing is deleted automatically and nothing is kept silently.**
3. A broken wire cannot be live (`wire-broken`, exists today), so **Run is
   refused** while one is in the sketch, until Sasha unplugs (`off`),
   removes or re-points it, or takes the edit back.
4. The edit is saved even if wires break — after one confirm line: "2 wires
   no longer fit: GIMP → Cloud folder (files), GIMP → Printer (print).
   They stay, marked broken. Save? y / n".
5. When an edit makes a broken wire fit again, a documented or planned wire
   returns to the state it had before (`was` kept on the wire). A wire that
   was live never goes live again by itself — that needs Run.

Examples:

| Edit | Wire before | After |
|---|---|---|
| GIMP: remove need `images` (`files`) | Cloud folder → GIMP `images`, documented | broken (`unknown-port`), red, Run refused until unplugged/removed |
| Printer: change offer `print@1` to `print@2` | Budget app needs `print@^1`, live | broken (`version-mismatch`); Run refused; Budget's live setting untouched until Run |
| Router: add offer `lan` | — | nothing breaks; the new socket shows in `v` |
| "?" piece: add need `files` | — | nothing breaks; now Cloud folder can be wired to it |
| Undo the GIMP edit | broken (was documented) | documented again, without Run |

## 6. KI describer — privacy and cost

**Its own package** (proposal: `piece-describer-ai`, own repo with
`app.toml`), `needs = ["model"]`, `offers = ["describe"]`. Not
preinstalled. Without it, or without a live `model` wire, nothing ever
leaves the device and the "?" fallback stays.

**What leaves the device — exactly this, nothing else:**

- package name, version, summary, description text, section/categories,
  homepage (from the package database / AppStream / `.desktop`);
- `.desktop` `Categories=` and `MimeType=`; AppStream `provides`/`requires`;
- Flatpak/Snap permission names;
- the manpage NAME line and at most 20 SYNOPSIS lines;
- the file type of a downloaded file and its file name.

**Never:** file contents, the binary, paths under `$HOME`, user or host
names, node names, other programs on the machine, Sasha's schemes.

- The card shows that list for this program **before** the first call;
  the first use per provider asks once ("Send these 7 fields to Mistral?
  y / n / always"). The choice is a setting of the account.
- With a local model (Ollama on a `model` wire), nothing leaves the
  machine; the card says "local".
- **Cost:** one call per program, about 1,500 tokens in and 400 out. With a
  small model that is well under one cent per program; the card shows the
  estimate from the provider's price table before the call. Results are
  stored in the register, so a program is described by the KI **once per
  account**, not per node and not per opening.

**KI rules** (KI-Bibel, `memory/ki/bibel/README.md` — read before building):
the tool/prompt text is the main lever (W-01, P-05: copy Anthropic's way);
structured output against the description schema; fields only from the
metadata given — a value without a basis is `none`, not invented (the
principle of W-14 and PR-12, carried over from calendar fields); every
port it proposes is checked against the type registry and dropped when the
type is unknown; context small (KT-01). A Python checker validates the
answer before the register stores it (PR-01).

## 7. The inventory modal (Schematix UI)

The inventory is **a view of the register**, nothing more. It replaces the
`+` picker (`+` stays as a second key for it — open question).

### 7.1 Keys

| Key | Where | What |
|---|---|---|
| `i` | board | open the inventory (a small modal, pops open and closed) |
| letters, digits, space, backspace | inventory | type to search (every printable key goes into the search field) |
| ↑ ↓ | inventory | move in the results |
| enter | inventory, on a known entry | take it: the modal closes, the piece is **in your hand** on the board |
| enter | inventory, on an unknown entry | "describe first" (7.3) |
| tab | inventory | open the detail card of the selected entry (is / can / can't, ports, sources) |
| esc | inventory | clear the search; second esc closes |
| `e` | board, on a piece | edit that piece: name, icon, ports (section 5) |
| `n` | board, on a node | the versions panel (moved from `i` — proposal, open question) |

`n` = "node": a plain letter, free in Schematix today, swallowed by no
terminal, tmux or window manager. Today's `i` (versions) moves there.

### 7.2 What the list shows

One line per entry, **always with its icon** (pixel icon, app icon, sigil
or "?"), the name, and a quiet right column: kind and state.

```
┌ inventory ──────────────────────────────────────┐
│ > gim█                                          │
│  ▣ GIMP               program · laptop          │
│  ⍫ Gimp-Plugin-Batch  program · not described   │
│  ? gimp-2.10.AppImage file in ~/Downloads       │
│                                                 │
│ ↑↓ choose · enter take · tab details · esc close│
└─────────────────────────────────────────────────┘
```

Sources, fresh on every open (like the `+` picker today): every resolved
description in the register; installed programs **not yet described**
(the standard describer's list: package database, `.desktop` files,
Flatpak/Snap — names only, no describing yet); store apps; nodes; device
kinds; downloaded executables in `~/Downloads` (proposal, open question).
Empty search = recent first, then by kind. Search matches name, edited
name, package keys, categories; order: prefix > word > fuzzy, described
before not described.

### 7.3 States

```
 closed ──i──▶ list ──type──▶ results ──enter (known)──▶ IN HAND ──enter──▶ dropped
                 ▲                │                          │ esc: put back
                 └──── esc ───────┤
                                  └─enter (unknown)──▶ ASK "describe first?"
                                                         │ enter          │ esc
                                                         ▼                ▼ results
                                                    DESCRIBING (short wait, spinner,
                                                     "reading package data…",
                                                     "asking <model>…" only if tier 3)
                                                         ▼
                                                    RESULT CARD: is / can / can't,
                                                     ports, "?" and low marks
                                                     enter accept · e edit · esc back
                                                         ▼ accept / save
                                                       IN HAND ──enter──▶ dropped
```

- **Known** = the register has a resolved description. Taking it is
  instant.
- **Unknown** cannot be dropped before it is described — the inventory
  asks first (Sasha's rule). Describing with tier 1+2 takes well under a
  second; with tier 3 a few seconds.
- **In hand** is today's grab mode (`enter` on a piece): arrows move, enter
  drops, esc puts it back. Dropped programs and devices are *documented*
  on this node (they exist); a store app not installed is *planned*.
- The card can be edited now (`e`) or any time later on the board (`e` on
  the piece).

## 8. Icons — hardware vs. apps

| Piece | Icon source | Fallback |
|---|---|---|
| device (router, printer …) | the hardware icon table `tui/bausteine/device_icons.txt` (16 kinds today), by kind | the new `unknown` block ("?") |
| node | the same table, by node name (`NODE_ICONS` today in `schematix_arten.py`) | `tower` |
| ZENTRALE app | the package: `icon` (PNG, rendered to the pixel raster the wheel uses, `core/apps.py` `icon()`) or `icon_motiv` | a sigil from the fixed set, picked from the name (as today) |
| program | the `.desktop` `Icon=` name, looked up in the freedesktop icon theme (PNG/SVG), rendered to the same raster | sigil by name, then "?" |
| unknown | "?" | — |

Every icon is editable (`e`): pick a device icon, an app icon, a sigil or
"?", or point to an image file. The choice is an edit (section 5), so it
survives re-describing. Icons are data, never code: a new device kind is
one more block in `device_icons.txt` (and one row in the device table).

## 9. What exists today vs. what is missing

| Part | Exists | Missing |
|---|---|---|
| port types, need/offer forms | `contracts/ports/1/`, `core/port_types.py` | the `describe` type (section 10) |
| gate | compiler, `wire-broken`, `broken` wire state, error pins on the board | re-check triggered by a description edit |
| device kinds | `contracts/schematix/1/kinds.json` (10 kinds, Schematix's contract) | a home in the core for the standard describer (it leaves with Schematix otherwise) |
| device icons | `device_icons.txt`, `pixel_icons.py` (core building blocks) | `unknown` "?" block |
| app icons | `core/apps.py` `icon()` (PNG → raster, `icon_motiv`) | theme icon lookup for foreign programs |
| app self-description | `app.toml` name, `icon`, `needs`/`offers` | an optional `piece.json` for can/can't |
| placing pieces | `+` picker over `GET /api/pieces` (in Schematix) | search, foreign programs, describe-before-drop |
| piece editing | move, remove planned, make real | name/icon/ports edit |
| description format, register, edits | — | everything |
| standard describer | — | everything |
| KI describer | `model` port, adapter `ki-anbieter` | the package |

## 10. Port type proposal: `describe`

To add to the vocabulary plan (building kit 1.3) and later to
`contracts/ports/1/types.json` with a vector — **not done here**:

| Field | Value | Why |
|---|---|---|
| family | `describe` | describing is a capability, like `print` |
| version | `1.0.0` | speaks `zentrale-piece-description/1` |
| layer | `services` | |
| relationship | `DependsOn` | the register depends on describers |
| scope | `node` | evidence is local: the describer reads the node it runs on |
| cycles | `forbidden` | data flow |
| occurrences (need of the register) | `[0, UNBOUNDED]` | zero describers is legal ("?"), several are merged |
| qualifier | none | the tier comes from the provider (`declared`/`static`/`guess` in its offer), not the type |

Offered by: the core's standard describer (`static`), the KI describer
(`guess`); the manifest reader is tier 1 inside the core and needs no wire.
Needed by: the register only. Consumers never wire to a describer; they read
the register.

## 11. Build order — small steps, each with its acceptance test

Core first, Schematix UI only after Schematix has its own package.

| # | Step | Acceptance test |
|---|---|---|
| 1 | **Format contract**: `contracts/pieces/1/description.schema.json` + `edits.schema.json` + vectors; read rule in `core/formats.py` | vectors (GIMP, router, "?", app) validate in Python and Dart; a `format: …/2` vector is read-only with one note; unknown fields survive a write |
| 2 | **`describe` port type** in `types.json` + vector | registry test green; a sketch with two describers on the register compiles, one with a cycle does not |
| 3 | **Register in the core**: store, resolve = description ⊕ edits, `GET /api/descriptions?q=`, `GET /api/descriptions/<id>`, `PUT …/<id>/edits`, in `openapi.yaml`; files in the sync positive list | re-describing with a changed base keeps the edits byte-identical; a changed `base_hash` is reported; a second node reads the description without describing again |
| 4 | **Gate re-check**: an edit or re-describe that changes ports compiles every affected scheme + the projection; misfits → `broken` with reason and `was` | printer loses `print` → the scheme wire becomes broken, is still in the file, Run refuses with `wire-broken`; undo → documented again; a live wire never returns without Run |
| 5 | **Tier 1**: manifest reader writes descriptions for every installed and store app | every installed app has a description, ports equal its manifest, all `high`, `from: manifest` |
| 6 | **Device table to the core**: `kinds.json` moves from `contracts/schematix/1/` to `contracts/pieces/1/device_kinds.json` (coordinate with the extraction), plus the `unknown` icon block | the ten kinds resolve as `device:*` descriptions with their icons; Schematix reads them through the register route |
| 7 | **Standard describer** (core default adapter, offers `describe`): package db, `.desktop`, AppStream, manpage, MIME, Flatpak/Snap; mapping table | on a fixture root: GIMP → name, theme icon, `files` need, `high`; a fake binary that writes a marker when run is described and **the marker never appears**; a random ELF → "?" description |
| — | **Schematix extraction** ([open item](../open/schematix_extraction.md)) — not part of this plan, but steps 8–9 wait for it | Schematix runs as its own package and uses only public routes |
| 8 | **Inventory modal** in the Schematix package: `i`, type-to-search with icons, known → in hand, unknown → describe → card → drop; versions panel to `n` | PTY test: `i`, type `gim`, enter → piece in hand, enter → documented on the board; an unknown entry shows the describe step first; esc twice closes |
| 9 | **Edit on the board** (`e`): name, icon, ports, confirm line for wires that will break | PTY test: remove a port with a wire on it → confirm line names the wire → wire red, Run refused |
| 10 | **KI describer package** (own repo, `needs model`, `offers describe`): consent card, local-model path, checker | with a fake model: only fields below `medium` are filled, marked `from: ki`, ports `low`; the sent payload equals the shown list exactly; no `model` wire → no call, "?" stays |
| 11 | **Other consumers**: store cards and plug dialog show the resolved name/icon/summary; the assistant reads the register | the store shows an edited name; the plug dialog lists a described program as provider only when its ports fit |

## 12. Open questions for Sasha

In [../open/piece_descriptions_decisions.md](../open/piece_descriptions_decisions.md),
one line each with a proposal.

## History

- **2026-10-31** — written from Sasha's request (inventory, describe any
  program, edit every node, "?" fallback) and the agreed cut: describing is
  a capability with providers; core = format + register + gate re-check;
  Schematix = UI only; KI describer = own package.
