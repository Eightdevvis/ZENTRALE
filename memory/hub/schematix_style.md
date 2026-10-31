# Schematix — style: hacker × wizard, an "ethereal machine"

**Stand 2026-10-31: second attempt, built into the TUI.** The look of the
app Schematix (code `schematix`, how it works: [schematix.md](schematix.md)).
Ästhetik entscheidet Sasha: we measure and expose knobs, we don't "correct"
his taste — every default below is a starting point he tunes (key `c`).

## Why a second attempt

The first look (2026-10-30, "dense retro-occult terminal": layer chips
`▐1▌SYNC`, a gauge `LIVE ▕███░░▏`, `░▒` bands, framed panels, menu words in
caps) missed. Sasha, 31.10.: „den stil hast du leider gar nich getroffen
lol … zu viel retro game, das hier sieht aus wie mario64 in dark mode, aber
die aesthetic bei mir is eher so n hackerxwizard vibe lol, so dieses ding
von ethereal machine" — „arbeite aber bitte stärker mit flächen
differenzierung … du willst tiefe und kontrast bilden" — „für hardware
verschiedene symbole … statt nur so kasten" — „und dann steht unter dem
gerät immer der geräte name drunter".

**Out, for good:** menu tiles, gauges, icon strips, chunky frames, `░▒`
fill bands, colourful chips, game-menu wording, everything in caps.

## The mood (Sasha's images)

`~/Downloads/aesthetic/` on his laptop — other people's artworks, **never
copied into the repo**, only described: concentric circuit traces with
round pads grown into a tree like runes, glowing out of near-black;
dithered green in a dark shop aisle; a circuit-board collage in violet and
magenta; machines that look half engineering, half spell. Take it as a
direction, not a template.

## The rules we build

1. **Light, not fill.** Thin lines that glow on near-black. Green and violet
   are light (traces, glyphs, the focus outline), never a filled area.
2. **Depth by surfaces.** Several planes behind each other, each with its
   own ground (`surface-*`) and its own texture (`texture-*`); back = almost
   black and calm, front = brighter and sharper:

   | Plane | Ground | Texture | Moves while panning |
   |---|---|---|---|
   | the board (far) — data column, top line | `board` | none | — |
   | cloud | `surface-cloud` (violet-black) | star dust `· ˙`, sparse | ¼ speed |
   | software | `surface-software` | a fine grid of points | ½ speed |
   | nodes | `surface-nodes` | hatching `╱` | ¾ speed |
   | things | `surface-things` | stipple `· ∙ ˙`, denser — the ground | full speed |
   | pieces (front) | `surface-piece`, a plate — the texture stops there | — | with the piece |

   Two planes meet with a row of half blocks `▄` (the lower ground on the
   upper one). Each plane names itself quietly at its top: `// nodes · 05`.
3. **Pieces are sigils set into the ground, not boxes.** Only the corners of
   a frame are drawn; the plate carries the shape. The size follows the
   content, so the board is no grid of equal boxes (the scheme keeps its own
   sizes; only the drawing adapts).
   - **Software:** one sigil glyph (APL/geometric signs, pinned for known
     apps, otherwise picked by name) + the name, the sync line below.
   - **Hardware:** a small pixel-art icon of what it is (quadrant blocks,
     ≤ 8×4 cells) with **the device name always below it**. Nodes: icon on
     the left with the name below, what the node says on the right.
   - **Wires** are traces: rounded corners, a via `◦` where they meet a
     piece, a label in the middle when it says something (`off`, `not yet`,
     a type).
4. **Cryptic, quiet data at the margin.** The right column reads like
   terminal output: `// bands`, `// layers`, `// focus`, `// traces`,
   `name ······ 05`. Lower case, no menu words. Only real data — no
   invented noise, no invented words (plain band names, not "ether").
5. **Every state is a glyph too** (e-ink, 8-colour terminals), never only a
   colour — see the table below.
6. **Glyphs DejaVu Sans Mono has** (Sasha's monospace) or that VTE draws
   itself (box drawing, block elements). Not Braille, not ⌖ ⟳ ⚡ (missing or
   double width).

## Readable without colour

| State | Frame | Wire | Icon / text |
|---|---|---|---|
| live app | `╭ ╮` corners | `─│` with `◦` vias | sigil + name |
| node | `╭─╮` lines above and below | — | icon, name below |
| cloud | `┌ ┐` corners | — | cloud icon |
| documented thing | `╔ ╗` corners | — | icon, name, `▣ documented` |
| planned ("not yet") | `╭┄╮ ┊` dotted outline | `╌╎` dashed | same icon, inside hatched, `◇ not yet` |
| off (unplugged) | — | `┄┊` dotted | `┄ stays on this device` |
| error pinned to a piece | frame in the error role | — | `✕ <reason>`, wrapped |
| focused / target | thin rounded outline `╭─╮│╰╯` | — | — |
| layer on / off (top line) | — | `━` / `┄` before the number | — |

## Hardware icons

Data, not code: `tui/bausteine/device_icons.txt` (a general building block,
[../system/pixelstil.md](../system/pixelstil.md)), one block of pixel rows
(`#` on, `.` off) per kind, 2×2 pixels per cell. Today: laptop, mini-pc,
tower, raspberry-pi, phone, tablet, router, modem, switch, cable, power
(a lightning bolt), power-bank (a bolt in a small case), charger,
bluetooth-device, printer, cloud. A new kind of thing = one more block in
that file. Which icon a node gets is matched on its name
(`NODE_ICONS` in `tui/ansichten/schematix_arten.py`: laptop, mini, pc, pi …).
Planned: the same icon, its filled inside as a checkerboard, in the
`planned` role.

## Colour roles (knobs, not taste)

Colours are **roles** Sasha tunes himself (`c` in Schematix: pick a role,
the colour wheel opens; the measured contrast stands next to it, under the
floor it is marked — never changed for him). Stored in
`data/schematix/palette.json` (synced); defaults in
`contracts/schematix/1/palette.json`. Three kinds, by name:

| Kind | Roles | Measured against | Floor |
|---|---|---|---|
| text / light | everything else | `board` | 4.5:1 |
| surface | `surface-*` | the faintest text (`dim`) on it | 4.5:1 |
| texture | `texture-*` | its own surface | none — decoration, shown "texture, no floor" |

Sasha's e-ink rule (Bigme Color): never below 10 px (applies to the
phone/web front later; the TUI uses the terminal font) and never below
4.5:1 for text — every default text role and surface passes
(`tests/test_schematix.py` measures WCAG 2.x). Defaults:

| Role | Default | Used for |
|---|---|---|
| `board` | `#05060a` | the far plane |
| `ink` / `dim` / `bright` | `#b4c8bf` / `#7d9389` / `#e6fff3` | text, quiet text, names |
| `glyph` | `#7dffbe` | sigils and icons of live pieces (green light) |
| `trace` / `solder` | `#5ee0a0` / `#a8ffd6` | a wire without a layer colour / its vias |
| `focus` | `#cba8f5` | the focus outline, panel titles (violet light) |
| `planned` | `#8f8ab8` | planned pieces and their icons |
| `error` | `#ff5f7e` | the red `✕`, pinned errors |
| `layer-data` … `layer-power` | `#5ee0a0` `#74d3f0` `#d6c38e` `#a98aff` `#f07ad0` | sync, services, hardware, network (violet), power |
| `cloud` | `#c6cdf5` | the cloud's name |
| `surface-cloud` … `surface-things` | `#07070f` `#060a0d` `#0a0e0d` `#0b0c0a` | the grounds of the four planes |
| `surface-piece` | `#0e1218` | the plates under the pieces and panels |
| `texture-cloud` … `texture-things` | `#38385e` `#1d3e48` `#25493a` `#3e4232` | the patterns (≈ 1.8:1, quiet on purpose) |

In a 256-colour terminal the near-black grounds fall onto the few dark
greys xterm has (they may look the same); with 24 bit they differ as set.
Without 256 colours the theme roles stand in (surfaces and textures in
`faint`); the glyphs still carry every plane and every state.

## Looking at it

`SCHEMATIX_CAPTURE=<folder> venv/bin/python -m pytest tests/test_schematix_tui.py`
writes every screen as text and as a PNG with the real colour roles
(`tests/_schematix_png.py`). The captures of this attempt:
`~/Zentrale/Ablage/schematix-captures-v2/`.

## Later (phone / web)

The same roles, planes and glyph rules; pixel type at ≥ 10 px; textures as
real patterns, the glow as a soft bloom. Not built —
[../open/schematix_followups.md](../open/schematix_followups.md).
