# Piece descriptions — any program or device as a piece, and the Schematix inventory (plan)

**Stand 2026-10-31: plan only, nothing built.** Owner: Sasha. Builds on the
building kit ([building_kit_plan.md](building_kit_plan.md): pieces, ports,
wires, Run gate — [port_types.md](port_types.md)) and on Schematix
([schematix.md](schematix.md)). Respects the permanent rule "apps live
outside the core" (CLAUDE.md) and the pending
[Schematix extraction](../open/schematix_extraction.md). Sasha's decisions
(2026-10-31) are recorded in section 12. Catalog lifecycle (add, remove,
replace): section 13, its open questions in
[catalog_lifecycle_decisions.md](../open/catalog_lifecycle_decisions.md).

> **The core in five sentences**
>
> 1. Everything is a piece with plugs: it offers or needs something; wires
>    connect only matching plugs.
> 2. The core knows four things: which plug types exist, a datasheet per
>    piece (name, kind, plugs with versions), which wires are plugged, and
>    how to check them.
> 3. Everything else is plugged in: cloud, calendar, describers, KI,
>    Schematix.
> 4. Every change runs the same way: check → show what changes → switch,
>    with a way back.
> 5. Interfaces only grow: once released, a plug type is never changed so
>    that old pieces misread it; a fundamental change gets version 2 next
>    to version 1 with a translator.

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
 │ inventory (+),     │ │ (cards)   │ │ (providers) │ │ (what is X?) │
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
| `source.keys` | every key this program is known under. The same program from two sources (distro package and Flatpak) is **two installed programs** to Linux (separate files and settings) → two descriptions, two entries (Sasha). Identical downloaded files are recognised by checksum (`appimage/<sha256-prefix>`) → one entry |
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

**The edit layer applies on top of *derived* descriptions** (tiers 2–3 and
"?"). **A self-description is authoritative:** what an app declares about
itself (tier 1: `app.toml` or `piece.json`) is read-only for ports, can and
can't — the user could otherwise break his own setup. Only the cosmetic
fields (name, icon) are editable on a self-described app.

The register keeps two things (dasselbe Objekt, nicht kopiert): one
derived description per program or device kind, and edits **per piece**:

- the **derived description** (what the describers said), replaced
  whenever it is re-described;
- the **edits** (what Sasha changed on one piece), a separate small record
  pointing at the piece and its description by `id`:

```json
{"format": "zentrale-piece-edits/1",
 "of": "program:flatpak/org.gimp.GIMP",
 "piece": "program:flatpak/org.gimp.GIMP@laptop",
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
- **Per piece, not per kind (Sasha):** an edit applies to that one piece
  (one program on one node), with all fields including ports. No per-kind
  edits now. *Future idea, separate special mode:* group identical pieces
  and edit them together — needs a bigger ZENTRALE setup, not now.
- **Syncing — no special mechanism (plug principle):** the description
  register is a piece with a `data` port wired to `sync`, like any app's
  data. Derived descriptions and edits sync with it
  (`data/pieces/descriptions/*.json`, `data/pieces/edits/*.json`,
  end-to-end encrypted like all `data/`), so a second device never
  describes again or pays the KI again.
- **Self-described pieces (ZENTRALE apps, apps with `piece.json`):** name
  and icon editable; **ports, can, can't read-only** — the self-description
  is authoritative, and the manifest is what the gate enforces on live
  wires. Programs, devices, "?" pieces: everything editable.

### 5.2 What happens to wires on an edit

Every edit that changes ports, and every re-describe that changes ports,
triggers the **gate re-check**: the register compiles every scheme and this
node's projection that contain that piece (a re-describe: every piece
using that description) (`sketch_compiler`,
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

**Its own package** (`piece-describer-ai`, an internal name; own repo with
`app.toml`), `needs = ["model"]`, `offers = ["describe"]`. **Comes from the
store, not preinstalled** (Sasha). Without it, or without a live `model`
wire, nothing ever leaves the device and the "?" fallback stays.

**What leaves the device — exactly this, nothing else:**

- package name, version, summary, description text, section/categories,
  homepage (from the package database / AppStream / `.desktop`);
- `.desktop` `Categories=` and `MimeType=`; AppStream `provides`/`requires`;
- Flatpak/Snap permission names;
- the manpage NAME line and at most 20 SYNOPSIS lines;
- the file type of a downloaded file and its file name.

**Never:** file contents, the binary, paths under `$HOME`, user or host
names, node names, other programs on the machine, Sasha's schemes.

- **Consent (Sasha):** installing the KI describer package **is** the
  consent to send this metadata to the configured KI provider — no extra
  per-provider question. In the interpret dialog every new piece has a
  **checkbox "describe with KI: yes / no"**, so single programs can be kept
  away from the KI. The card still shows exactly what would be sent.
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

The inventory is **a view of the register**, nothing more. It replaces
today's `+` picker and opens with **`+`** (Sasha). `i` stays the versions
panel.

### 7.1 Keys

| Key | Where | What |
|---|---|---|
| `+` | board | open the inventory (a small modal, pops open and closed) |
| letters, digits, space, backspace | inventory | type to search (every printable key goes into the search field) |
| ↑ ↓ | inventory | move in the results |
| enter | inventory, on a known entry | take it: the modal closes, the piece is **in your hand** on the board |
| enter | inventory, on an unknown entry | the interpret dialog (7.3) |
| tab | inventory | open the detail card of the selected entry (is / can / can't, ports, sources) |
| esc | inventory | clear the search; second esc closes |
| `e` | board, on a piece | edit that piece: name, icon, ports (section 5) |
| `i` | board, cursor on a device/node piece | the versions panel (unchanged; opens only there) |

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
kinds; downloads in `~/Downloads` — only executables and AppImages
(Sasha), identical files collapsed by checksum.
Empty search = recent first, then by kind. Search matches name, edited
name, package keys, categories; order: prefix > word > fuzzy, described
before not described.

### 7.3 States

```
 closed ──+──▶ list ──type──▶ results ──enter (known)──▶ IN HAND ──enter──▶ dropped
                 ▲                │                          │ esc: put back
                 └──── esc ───────┤
                                  └─enter (unknown)──▶ INTERPRET DIALOG
                                                       [x] describe with KI
                                                       (shows what would be sent)
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
                                                     (documented / planned)
```

- **Known** = the register has a resolved description. Taking it is
  instant.
- **Unknown** cannot be dropped before it is interpreted — the interpret
  dialog is **mandatory** (Sasha). The KI checkbox is shown only when the
  KI describer is installed. Describing with tier 1+2 takes well under a
  second; with tier 3 a few seconds.
- **In hand** is today's grab mode (`enter` on a piece): arrows move, enter
  drops, esc puts it back. After interpreting, the piece is dropped as
  **documented** when installed on that device, **planned** otherwise —
  automatically, no question (Sasha).
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
| 4a | **Catalog lifecycle in the core** (section 13): catalog entries `present`/`missing`/`tombstone`, add/remove/replace as sketch changes through the gate and Run, 30-day undo, `replaced_by`, conflicts to `beiseite/` | the tests of section 13 (add, remove, re-add, conflict, missing, replace) |
| 5 | **Tier 1**: manifest reader writes descriptions for every installed and store app | every installed app has a description, ports equal its manifest, all `high`, `from: manifest` |
| 6 | **Device table to the core**: `kinds.json` moves from `contracts/schematix/1/` to `contracts/pieces/1/device_kinds.json` (coordinate with the extraction), plus the `unknown` icon block | the ten kinds resolve as `device:*` descriptions with their icons; Schematix reads them through the register route |
| 7 | **Standard describer** (core default adapter, offers `describe`): package db, `.desktop`, AppStream, manpage, MIME, Flatpak/Snap; mapping table | on a fixture root: GIMP → name, theme icon, `files` need, `high`; a fake binary that writes a marker when run is described and **the marker never appears**; a random ELF → "?" description |
| — | **Schematix extraction** ([open item](../open/schematix_extraction.md)) — not part of this plan, but steps 8–9a wait for it | Schematix runs as its own package and uses only public routes |
| 8 | **Inventory modal** in the Schematix package: `+`, type-to-search with icons, known → in hand, unknown → interpret dialog (KI checkbox) → card → drop; `i` stays versions | PTY test: `+`, type `gim`, enter → piece in hand, enter → documented on the board; an unknown entry shows the interpret dialog first; esc twice closes |
| 9 | **Edit on the board** (`e`): name, icon, ports, confirm line for wires that will break | PTY test: remove a port with a wire on it → confirm line names the wire → wire red, Run refused |
| 9a | **Remove / replace on the board** (Schematix package): `x`/`del` (today only planned pieces) removes any piece, `+` → card → "replace"; both show the diff, confirm, Run; missing pieces grey with "!" | PTY test: remove a piece with two wires → diff names both → Run → gone; replace Firefox with LibreWolf → one broken wire red; undo restores |
| 10 | **KI describer package** (store, own repo, `needs model`, `offers describe`): per-piece KI checkbox, local-model path, checker | with a fake model: only fields below `medium` are filled, marked `from: ki`, ports `low`; the sent payload equals the shown list exactly; checkbox off or no `model` wire → no call, "?" stays |
| 11 | **Other consumers**: store cards and plug dialog show the resolved name/icon/summary; the assistant reads the register | the store shows an edited name; the plug dialog lists a described program as provider only when its ports fit |

## 12. Sasha's decisions (2026-10-31)

| # | Question | Decision |
|---|---|---|
| 1 | Key for the inventory | **`+`**. `i` stays the versions panel (opens only with the cursor on a device/node piece) |
| 2 | Edits per kind or per piece? | **per piece**, all fields. Grouping identical pieces for a joint edit = future special mode, not now |
| 3 | Can the user overwrite an app's self-description? | **no** — authoritative and read-only for ports, can, can't; name and icon editable. Edits apply on top of *derived* descriptions |
| 4 | How do descriptions sync? | no special mechanism: the register is a piece with a `data` port wired to `sync`. Derived descriptions sync, so no second describe or KI cost |
| 5 | Downloads in the inventory? | yes, only executables and AppImages |
| 6 | Same program from two sources? | two installed programs → two entries; identical downloaded files (checksum) → one entry |
| 7 | KI consent | installing the KI describer = consent for the configured provider; per new piece a checkbox "describe with KI: yes / no" in the interpret dialog; the card shows what would be sent |
| 8 | KI describer preinstalled? | no, from the store |
| 9 | Drop an unknown program before interpreting? | no, the interpret dialog is mandatory; then dropped automatically as documented (installed on that device) or planned |
| 10 | KI describer package name | internal detail: `piece-describer-ai` |
| 11 | Datasheets for every piece in the world? | **no** — only a **catalog of the pieces in your own system** (installed apps, your devices and things, programs pulled into the inventory or described); the core must add, remove cleanly and replace (section 13) |

## 13. Catalog lifecycle: add, remove, replace

Sasha, 2026-10-31: *„dann muss der kern in der lage sein alte rauszuschmeißen
sauber und neue reinzulegen, oder direkt ersetzung zu führen."* The register
(section 5) holds one **catalog entry per piece** (`program:gimp@laptop`):
the piece id, a reference to its description by `id` (never a copy), its
edits, its state (`present` · `missing` · `tombstone`). Descriptions exist
only for catalog entries; the inventory's "not yet described" list is names
only. **One way:** every operation below is a change to the sketch, checked
by the gate, shown as one diff and applied by Run as one generation — the
same `check → show → switch, way back` as any wire.

**Add.** Describe (section 4) or read the manifest → datasheet with
provenance (`from`, `confidence`, `source`) → validated against the
description schema (and the port registry) → catalog entry `present` → it
shows in the inventory and can be dropped on the board. Adding a piece
changes no wire, so the diff is one line and Run only stores it.

**Remove.** (1) Every wire on the piece is collected; the diff lists exactly
the wires that would be cut ("3 wires cut: GIMP → Cloud folder (files) …").
(2) A **live** wire another node owns → refused: "run Schematix there"
(as today, [schematix.md](schematix.md)); nothing is removed half. (3) Sasha
confirms → Run removes the wires in one generation, then the entry becomes a
**tombstone** `{id, removed, removed_by, edits, wires}` (like device removal,
building kit step 8). (4) The tombstone keeps the edits and the cut wires
for **30 days** (proposal): "re-add" restores piece, edits and wires (wires
as documented/planned; a former live wire needs Run again). After 30 days
only `{id, removed, removed_by}` stays, forever — small, and it is what stops
another device's sync from bringing the piece back. (5) Nothing leaves the
cloud without a tombstone in its place; a device that edited the entry
*after* the tombstone does not win silently — its version is set aside
(`beiseite/`) and Sasha chooses (cloud never overwritten).

**Catalog vs. package.** Removing a ZENTRALE app *from the catalog* only
takes it off the board and cuts its wires — the package stays installed.
**Uninstalling** the package implies catalog removal: the uninstall runs the
remove flow above first (same diff, same refusal) and only then deletes the
package ([store uninstall is still missing](../open/store_app_lifecycle.md)).
A program the **OS removed** (apt, Flatpak, file deleted) is found missing by
the standard describer on that node → the entry turns **`missing`**: grey
"!" on the board, wires stay and are marked, nothing is cut, never silently
gone. Sasha then removes it (flow above), replaces it, or reinstalls (→
`present` again). A live wire on a missing app refuses Run (`piece-missing`).

**Replace** (Firefox → LibreWolf, router A → router B). One action, no new
key (`r` is Run): with the cursor on the old piece, `+` opens the inventory,
the new one is picked, and its card offers "replace <old>". The new piece
takes the old one's **place, wires and — optionally — its edited name** (a
checkbox in the diff, default off); only the description reference changes.
Every wire is re-checked against the new ports (section 5.2): fitting plug
types stay, the rest become **`broken`** with reason, visible. One diff
("kept 4 · broken 1: Firefox → Password store (secrets)"), applied by Run as
one generation; **undo** = roll back that generation, the old piece returns
with its wires and edits. The old entry becomes a **tombstone with
`replaced_by: <new id>`** (the new entry gets `replaces`), not a live
"replaced by" entry: a live entry could still be dropped or wired elsewhere
and would be two objects for one place; the tombstone blocks resurrection by
sync and still records the history for undo.

**Rule tie-ins.** One way: add, remove, replace, missing → all through the
gate and Run, no side door. Dasselbe Objekt: entries, tombstones and wires
reference descriptions by `id`; nothing is copied. Cloud never overwritten:
the tombstone is the only way something disappears, conflicts are set aside
for Sasha.

| Operation | Acceptance test (later build) |
|---|---|
| add | a described program becomes a `present` entry; an invalid datasheet (unknown port type) is refused with the field named; no wire changes |
| remove | diff names every wire; confirm + Run → wires gone in one generation, entry is a tombstone; a second node syncing an old copy does not bring it back; a live wire owned by another node → refused "run Schematix there", nothing changed |
| re-add | within 30 days: piece, edits and wires return (former live wire as documented until Run); after: entry without old edits |
| conflict | a node edits the entry offline after the tombstone → its version lands in `beiseite/`, the cloud keeps the tombstone |
| uninstall / missing | uninstall runs the remove flow first; a program deleted by the OS turns `missing`, its wires stay; Run with a live wire on a missing app → `piece-missing` |
| replace | Firefox → LibreWolf: fitting wires stay, the rest `broken` with reason; one generation; undo restores Firefox with all wires and edits; old entry is a tombstone with `replaced_by` |

New questions: [catalog_lifecycle_decisions.md](../open/catalog_lifecycle_decisions.md).

## History

- **2026-10-31** — written from Sasha's request (inventory, describe any
  program, edit every node, "?" fallback) and the agreed cut: describing is
  a capability with providers; core = format + register + gate re-check;
  Schematix = UI only; KI describer = own package.
- **2026-10-31** — Sasha's ten decisions recorded (section 12): inventory
  on `+`, edits per piece, self-descriptions authoritative, sync via the
  `data`→`sync` wire, per-piece KI checkbox; "the core in five sentences"
  added. Open item `piece_descriptions_decisions.md` closed.
- **2026-10-31** — section 13 catalog lifecycle (Sasha: the core keeps only
  the catalog of your own system and must add, remove and replace cleanly):
  tombstones, 30-day undo, `missing`, replace with `replaced_by`; build
  steps 4a and 9a.
