# Schematix — style: a dark, densely packed retro-occult terminal

**Stand 2026-10-30: agreed direction, built into the TUI with steps 13–15
([schematix.md](schematix.md)).** The look of the app Schematix
(code `schematix`, plan: [building_kit_plan.md](building_kit_plan.md)
section 6). Sasha collected mood images in `~/Downloads/aesthetic/` on his
laptop — other people's artworks, **never copied into the repo**, only
described here. Sasha: take it as a direction, not everything. Ästhetik
entscheidet Sasha: we measure and expose knobs, we don't "correct" his taste.

## What the mood images say (described, not copied)

- **Retro game screen** (the "NEW GAME / LOAD GAME / OPTIONS / INCANTATIONS"
  sheet): many framed panels packed edge to edge, icon strips along the
  borders, gauges and meters, a skull dial, pixel type, menus in caps.
  Desaturated olive-green on black, magenta-red only in small doses.
- **Circuit-board collage**: rounded PCB tracks with solder pads, organs and
  machines grown together, magenta and violet glowing out of near-black.
- **Cross-section terrarium**: a cloud on top, a garden, ground layers, water
  at the bottom — a stacked cut through the world, with columns of
  colourful data labels on both sides.
- **Low-poly wizards in a lift**: dithered, eerie, a bit funny; green smoke,
  violet robes, a chequered floor.

## The reading we build (Sasha agreed 2026-10-30)

| Idea | In Schematix |
|---|---|
| Densely packed framed panels | top strip (layer toggles + gauges), the board, a side column (cross-section + focused piece), a bottom line in caps |
| Icon strips | each layer is a numbered chip `▐1▌SYNC ▐2▌SVC ▐3▌HW ▐4▌NET ▐5▌PWR`; on = filled, off = hollow and struck |
| Gauges / meters | `LIVE ▕██████░░▏ 9/12` — share of live wires; counters for planned, documented, errors |
| Menu in caps, playful | bottom line `SCHEMING · RUN THE SCHEME · INCANTATIONS (?)`; the board title says what you are doing ("scheming…" when the sketch differs from what is in effect) |
| Wires as organic PCB traces | rounded corners `╭╮╰╯`, a solder dot `●` where a wire leaves and enters a piece, junctions `┬┴├┤┼` where traces merge into a bus |
| Layers as a cross-section | bands from top to bottom: **cloud → software → network (nodes) → hardware/power (things)**; each band labelled at the left edge in its colour, and the side column shows the stack with counts |
| Dithered green on near-black | board background `#0a0e0b`, text a desaturated green, sparse `∙` grid, `░▒` dither on band separators |
| Accents used sparingly | magenta (power, the focused piece), violet (network), chrome (the cloud); the red `✕` only for refusals |
| Humour | "scheming", "the scheme compiles", "unplugged — stays on this device" |

## Readable without colour (e-ink, 8-colour terminals)

Every state is also a glyph, never only a colour:

| State | Frame | Wire | Label |
|---|---|---|---|
| live | `┌─┐` (node `┏━┓`) | `─│` with `●` ends | — |
| documented (a real thing outside software) | `╔═╗` | `═║` | `doc` |
| planned ("not yet") | `┌╌┐ ╎` dashed | `╌╎` dashed | `not yet` |
| off (unplugged) | — | `┄┊` dotted | `off` |
| error pinned to a piece | `▛▀▜` | — | `✕ <reason>` |

## Colour roles (knobs, not taste)

Colours are **roles** with values Sasha tunes himself (`c` in Schematix:
pick a role, the colour wheel opens; the measured contrast stands next to
each role, under 4.5:1 it is marked — never changed for him). Stored in
`data/schematix/palette.json` (synced); defaults in
`contracts/schematix/1/palette.json`. Constraints from his e-ink device
(Sasha's rule for the Bigme Color): never below 10 px (the TUI uses the
terminal font, so this applies to the phone/web front later), **never below
4.5:1 contrast** against the board background — the defaults all pass
(`tests/test_schematix.py` measures WCAG 2.x contrast).

| Role | Default | Contrast on `#0a0e0b` | Used for |
|---|---|---|---|
| `board` | `#0a0e0b` | — | background of the board |
| `ink` | `#a9c49a` | 10.2 | text |
| `dim` | `#7e9a72` | 6.3 | frames, grid, quiet text |
| `bright` | `#e2f0d2` | 16.3 | titles |
| `trace` | `#86b86e` | 8.4 | a wire without a layer colour |
| `solder` | `#d6e07a` | 13.7 | solder dots, the gauge |
| `focus` | `#e866d8` | 6.8 | the focused piece (magenta) |
| `planned` | `#8aa07f` | 6.9 | planned pieces and wires |
| `error` | `#ff6b6b` | 7.0 | the red `✕`, pinned errors |
| `layer-data` | `#8fd46c` | 10.9 | sync / data wires |
| `layer-services` | `#5fd4c8` | 10.9 | model, calendar source, events … |
| `layer-hardware` | `#e2b44c` | 10.1 | mic, speaker, things |
| `layer-network` | `#a98af0` | 7.0 | LAN, Wi-Fi, WireGuard, Tailscale (violet) |
| `layer-power` | `#e866d8` | 6.8 | power (magenta) |
| `cloud` | `#c4ccd6` | 12.0 | the cloud piece (chrome) |

Without 256 colours the TUI falls back to its theme roles (`ink`, `dim`,
`acc`, `warn`); the glyphs above still carry every state.

## The terminal build

Characters, box drawing and half-blocks only. The board is the Desk's canvas
building block ([desk_view.md](desk_view.md)) with two additions that any
app can use: a frame per kind (`rand`) and a wire style per connection
(`stil`: `pcb`, `planned`, `off`), plus the fit check (`passt`) that draws
the red `✕` at the cursor.

## Later (phone / web)

The same roles and glyph rules; pixel type at ≥ 10 px; the dither as a
real 2×2 Bayer texture. Not built — see
[../open/schematix_followups.md](../open/schematix_followups.md).
