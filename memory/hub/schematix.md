# Schematix — the wiring map app

**Stand 2026-10-30: step 13 built (`64821b8`, v1, read-only); step 14 (`6d27b1c`, v2: schemes, planned and documented pieces, things); step 15 (v3: rewire by drawing, Run).** The app `schematix`
(plan: [building_kit_plan.md](building_kit_plan.md) sections 6 and 8, steps
13–15; look: [schematix_style.md](schematix_style.md)). One plan is a
**scheme**; making and changing schemes is **scheming** (Sasha's pun on
„schemen"). Built on the Desk building block ([desk_view.md](desk_view.md)):
the board is the same canvas, wires are laid fresh from positions every
frame, nothing on the board is a copy.

## How Sasha opens and uses it (TUI)

Start page → the **Erschaffen** wheel (beside Werkstatt and Shop) →
`schematix` → enter. The scheme **home** opens (made from
[../system/heimnetz.md](../system/heimnetz.md) the first time):

- **Top strip:** layer chips `▐1▌SYNC ▐2▌SVC ▐3▌HW ▐4▌NET ▐5▌PWR` and the
  gauge `LIVE ▕████░░▏ live/all` with counters (◇ planned, ▣ documented, ✕ errors).
- **Board** (cross-section, top → bottom): the cloud, the apps of each node
  in its column, the nodes, the things. The gutter on the left shows the
  band in its colour.
- **Right column** (wide terminals): the cross-section with counts per band,
  wires per layer, and the focused piece with its sockets.
- **Status line:** the scheme, how many nodes/pieces/wires, or a note
  ("not logged in — only this device is shown").

| Key | What |
|---|---|
| ↑↓←→ | focus jumps to the next piece in that direction |
| W A S D (also shift/alt+arrows) | move the view |
| enter | grab the piece, arrows move it, enter drops it (stored in the scheme), esc puts it back |
| + | add a piece: installed apps, nodes, store apps, kinds of things — placed as **planned**, in the hand |
| d / del (planned piece) | remove it from the scheme (asks y / n) — live pieces leave only when they leave reality |
| m (planned thing) | make it real: it is documented in the things store, same reference, the piece stays |
| v | draw a wire from the focused piece: arrows move the target, enter connects. A socket that does not fit shows a red ✕ at the cursor; enter there does not attach and says why at the socket ("PDF viewer needs `files`, Cloud offers `sync`") |
| p | the plugs of the piece: ↑↓ a wire, x unplugs / plugs it (or takes back a change, or removes a planned wire), esc back |
| r | Run: check → diff. The panel shows "✓ the scheme compiles" and the plan lines, enter switches, esc goes back; refused → the errors, pinned on the pieces (`✕ …`) |
| s (on another node) | this node keeps the same ZENTRALE version as that one (again: its own updates) |
| 1 2 3 4 5 | layer on/off: sync, services, hardware (things too), network, power |
| i (on a node) | fold the versions panel open/closed |
| c | colour roles: ↑↓ role, enter colour wheel, x back to default, esc back |
| esc | back to the start page |

What a piece says, as `zentrale status` on its node: `⇅ synced`,
`┄ stays on this device`, `? not decided yet`, `⇅ always synced` (the
adapter). A node shows its ZENTRALE version, cloud on / local only, when it
was seen; `i` adds its app versions, contract majors, auto-update, "same
version as", and what it cannot do yet (from what its description lacks).

## Schemes, planned and documented (step 14)

- **A scheme** = one JSON Canvas 1.0 file `data/schematix/schemes/<name>.canvas`
  (synced, Obsidian opens it). Each node/edge carries one key `zentrale`
  (`piece`, `kind`, `ref`, `state`, `node`, `thing_kind`, `address` · on
  edges `wire`, `type`, `layer`, `state`, `from`, `to`, `owner`). Everything
  else in the file (Obsidian's `color`, notes, groups, arrows, keys of a
  newer ZENTRALE) is written back unchanged — round-trip test.
- **States** (plan 6.3): *live* comes from the truth, the scheme only keeps
  its place; *documented* = a thing in `data/schematix/things/<id>.json`
  (format `zentrale-thing/1`, JSON Schema `contracts/schematix/1/thing.schema.json`,
  with its `links` — network/power wires it owns); *planned* = only in the
  scheme. A planned piece carries the address it will have (`node:pc`,
  `zentrale://schematix/things/router/`); when that object appears it is
  live by itself — same id, same place, nothing redrawn.
- **Starter "home"** from heimnetz.md: router `.254`, fibre modem, switch,
  power bank, PC `.1`, Pi `.10`, Pi 2 `.11`, laptop `.20`, mini `.21`, LAN
  and WireGuard wires — all planned except the nodes that already report;
  the tablet is documented with its live Tailscale link to the mini.
- **Saving** sends the whole board (`PUT /api/schematix/schemes/<name>` with
  the `stand` of the last load, like the Desk); changed elsewhere → 409,
  the TUI reloads and says so.

## Rewire by drawing, Run (step 15)

- **Drawing** a wire (`v`) or unplugging one (`p`, `x`) changes only the
  sketch; the board shows it in the focus colour with `⟳ … · r` and the
  title says "scheming…". A drawn network/power wire is a planned link of
  the scheme (stored at once); everything else waits for Run.
- **The socket table** for the red ✕ is the type registry: an offer of one
  piece that a need of the other takes, same type (`schematix_draht.fits`
  in the TUI, `schematix_run.fits` in the core — every surface draws it
  itself, the guarantee is the compiler). Refused, never greyed out.
- **Run** (`POST /api/schematix/run`): this node's projection + the
  changes; the whole scheme is checked with it (planned pieces and wires,
  documented things and their links, the other nodes) — planned items are
  checked, never applied; a live link that touches a planned piece counts
  as planned. Then `generations.run`: diff, switch, apply, health check,
  roll-back. A wire another node owns is refused: "run Schematix there".
  Unplugging the tutor's sync wire gives exactly one plan line, and after
  the switch `zentrale status` says "stays on this device".
- **Same version** (Sasha 30.10.): a setting of the node that follows
  (`same_version` in `data/ai_config.json`, never synced), set with `s`,
  published in its description (`versions.same_version`), drawn as a wire
  from the followed node. The updater does not act on it yet
  ([../open/schematix_followups.md](../open/schematix_followups.md)).

## Where the data comes from

| What | Truth | Code |
|---|---|---|
| this node's pieces and wires | its projection (`GET /api/wires`) | `core/wires.py` |
| other nodes | their descriptions in the cloud (`GET /v1/knoten`): `wires` (node-scoped wires), `versions` (new, step 13), `types`, `apply_agent` | `core/schematix_map.py`, `core/schematix_versions.py` |
| map + layout | laid fresh on every `GET /api/schematix/map` (and every 30 s while open) | `core/schematix_map.py` |
| `+` picker | `GET /api/pieces` (installed, providers, nodes, store apps not installed, device kinds) | `core/schematix_pieces.py`, `core/schematix_kinds.py` |
| colour roles | `data/schematix/palette.json` over `contracts/schematix/1/palette.json` | `core/schematix_store.py` |
| schemes | `data/schematix/schemes/<name>.canvas` | `core/schematix_scheme.py` |
| things | `data/schematix/things/<id>.json` | `core/schematix_store.py`, kinds `core/schematix_kinds.py` |

One piece per app **on a node** (`app:tutor@minipc`) because sync is
decided per node; the cloud is one piece for the account. Every node
publishes `versions` (format `zentrale-node-versions/1`, read rule of
`core/formats.py`) with its wires (`zentrale sync`, `devices`, wizard).
Schematix is itself an app with data: `data/schematix/**` syncs (positive
list), it appears in the sync choice like every app.

## Code

| Part | File |
|---|---|
| view, keys (one table), loading | `tui/ansichten/schematix.py` |
| panels, colours, board | `tui/ansichten/schematix_bild.py` |
| the canvas art `piece` (frames per state, versions panel) | `tui/ansichten/schematix_arten.py` |
| drawing wires: socket table, misfit text, wire for a drawn pair, plugs toggle | `tui/ansichten/schematix_draht.py` |
| Run from the drawing | `core/schematix_run.py` |
| canvas additions any app may use: `rand_von`/`rolle_von` per art, wire `stil` (pcb/planned/off), `passt` (red ✕) | `tui/bausteine/canvas.py`, `tui/bausteine/schnur.py` |
| routes | `ui/routen/schematix.py`, `openapi.yaml` (tag `schematix`) |
| tests | `tests/test_schematix.py` (acceptance on the fake cloud), `tests/test_schematix_scheme.py` (step 14), `tests/test_schematix_run.py` (step 15), `tests/test_schematix_tui.py` (TUI, screen captures), `tests/tasten_zustaende/schematix.py` |

Text captures of the screen: `SCHEMATIX_CAPTURE=<folder> venv/bin/python -m
pytest tests/test_schematix_tui.py` writes one `.txt` per screen.

## Not yet

[../open/schematix_followups.md](../open/schematix_followups.md).
