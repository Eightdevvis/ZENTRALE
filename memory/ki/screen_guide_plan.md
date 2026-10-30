# Screen guide — the AI sees the screen and points (plan)

**Stand 2026-10-31: plan, nothing built.** One AI tool `screen` (actions
`look`, `point`) needs a new port type `screen`; adapters offer it per
surface (first: the X11 desktop via AT-SPI plus screenshot). A skill
`teacher` makes the AI show the way instead of clicking. First use: Sasha
learns the Arduino IDE. Built once, it works on any surface that gets an
adapter (browser, Android, AR later) without touching tool or skill.

## Where each piece lives

| Piece | Place | Has a home today? |
|---|---|---|
| Port type `screen` | `contracts/ports/1/types.json` (+ vector in `scripts/port_vectors.py`) | yes |
| Map format | `contracts/screen-map/1/` (schema + vectors), like `contracts/ports/1/` | yes, by pattern |
| AI tool `screen` | `core/werkzeug_screen.py` (action schemas, like `core/werkzeug_kalender.py`), group `screen` in `core/werkzeug_gruppen.py` | yes; the target "AI tool = own store package" is not built for any tool yet |
| Skill `teacher` | shipped in `core/skill_vorlagen/`, installed into `ki/skills/teacher/SKILL.md` | yes |
| Adapter `screen-x11` | **none yet** | **no** — see below |
| Image blocks in tool results | `core/cloud.py`, `_tool_result` | yes |

**The adapter has no home.** Adapters today are *connections to outside
services* (`core/adapter_anschluss.schema.json` allows only
`kalender-vdirsyncer` and `ki-anbieter`). A local device adapter that offers
a hardware port type does not fit there, and hardware ports today are only
detected by the node (`core/knoten.py`). The printer waits for exactly the
same frame (`memory/open/printer_adapter.md`, step 1: rewrite
`memory/hub/adapter.md` as blueprint — broker, interfaces, pluggable
adapters). Decision: build that frame **once**, with `screen-x11` as its
first user (the printer is blocked on its network anyway), the printer
second. No screen-only side path.

Sasha, 2026-10-31: *„wenn jemand der alles schon kennt neben mir sitzen würde
und einfach draufzeigt was ich klicken soll … so wollen wir das tool bauen."*
And: *„die baustelle hier gleich so aufziehen, dass man die ki überall
rumdatschen kann wo sie will künftig, one build, for all use cases in this
type."*

## What exists elsewhere (searched 2026-10-31)

- **Clicky** (macOS, MIT, `farzaa/clicky`): push-to-talk → transcript +
  screenshot to Claude → the reply carries `[POINT:x,y:label:screenN]` → a
  blue overlay cursor flies there. A Windows fork exists; no Linux.
- **Cursy, Cursorbuddy, Navisual** (Windows/macOS): same idea; Navisual never
  clicks on purpose, it only shows.
- **AT-SPI** (Linux accessibility bus): GTK/Qt apps expose a tree of every
  control with role, name and screen extents. A ready-made map, exact and
  free. Rust crate `computer-use-linux` walks it; an AT-SPI MCP server exists.
- **OmniParser** (Microsoft): screenshot → list of UI elements with boxes and
  captions, for apps without an accessibility tree. Detector weights AGPL.

None runs on Sasha's i3/X11 laptop. We take the ideas, not the code.

## Why it is cut this way

- **The model names an element, the program knows the pixel.** Models are
  poor at hitting exact coordinates on a screenshot (Clicky lets them guess).
  The map gives every element a short id; the model says `#17`, the adapter
  turns that into the box. Exact, cheap, and a weak model can do it too —
  the same idea as the tool generator (`werkzeug_erzeuger.md`): our program
  makes the interface strict enough that the AI has to get it right.
- **One tool, not two.** `point` is meaningless without `look` (Sasha). Anthropic
  does the same: one `computer` tool with an `action` field. Also bible W-04:
  no overlapping tools.
- **Port type, not a device in the tool.** Same three layers as the printer
  (`memory/hub/port_types.md`): the port type is the fixed contract, an
  adapter offers it for one surface, the tool needs it and never knows which
  adapter answers. A new surface = a new adapter, nothing else.
- **Map first, picture only when needed.** Text is a fraction of an image's
  tokens, and less of Sasha's screen leaves the machine (ground pillar:
  privacy). The screenshot is a fallback for parts the map does not cover.
- **The AI shows, Sasha clicks.** Learning only works if Sasha's hand does it.
  A later `click` action is possible but goes through the permission gate
  (`erlaubnis_gate.md`) and is not part of this plan.

## The pieces

### 1. Port type `screen` (`contracts/ports/1/types.json`)

New family, `layer: hardware`, `scope: node`, `relationship: DependsOn`,
`occurrences [0, 1]`, `cycles: allowed`. Description: "See what a surface
shows as a map of elements, know where the user points, and show a marker."
Separate from the existing `display` (a screen as output, e.g. the kiosk):
looking at what is on it is a different contract. Test vectors as for every
family (plan 1.3 of `building_kit_plan.md`).

### 2. The map format — `zentrale-screen-map/1`

One format every adapter fills, JSON with a JSON Schema in
`contracts/screen/1/`. Roles from WAI-ARIA (`button`, `menuitem`, `tab`,
`textbox` …), no own words (open standard formats).

```json
{"format": "zentrale-screen-map/1",
 "surface": "x11:0", "app": "Arduino IDE", "window": "sketch_oct31a",
 "taken": "2026-10-31T14:02:11Z", "source": "atspi | vision | mixed",
 "pointer": {"x": 812, "y": 430, "over": 23},
 "elements": [
   {"id": 17, "role": "button", "name": "Upload", "box": [64, 48, 28, 28],
    "parent": 3, "enabled": true}
 ]}
```

- `box` = `[x, y, w, h]` in screen pixels of that surface.
- `pointer.over` = the id under Sasha's mouse: "what is this?" needs no
  coordinates at all.
- Ids live as long as one map; `point` with an id from an older map gets an
  error that says to `look` again (bible W-02).
- Size: only visible, named, interactive elements plus their containers
  (menus, panels) as parents. Hard cap per answer (bible W-06), with a
  `focus` parameter to look into one region in detail.

### 3. Adapter `screen-x11` (first one)

A small daemon on the node (Python, the AI never runs it directly):

- **Map:** AT-SPI tree of the focused window (roles, names, screen extents).
- **Fallback:** a screenshot of the window; elements found by local OCR
  (and later a detector like OmniParser) are added with `source: vision`.
  Local, so the picture itself need not leave the machine.
- **Pointer:** the mouse position from X11.
- **Overlay:** a transparent always-on-top window draws a marker (ring +
  label) on the box, fades after a few seconds or when Sasha clicks there.
  i3: the overlay must be a floating, unmanaged window that takes no focus.

**Arduino IDE caveat:** IDE 2 is Electron. Electron exposes almost nothing to
AT-SPI unless accessibility is switched on at start (a renderer
accessibility flag). Step 1 checks this on the real IDE; if the tree stays
thin, the vision fallback carries this case, and it must be good from the
start anyway.

Later adapters, same contract: `screen-browser` (DOM + ARIA, overlay in the
page), `screen-android` (accessibility service), AR (Mini, see
`zukunftsvisionen.md`).

### 4. AI tool `screen`

Built through the tool generator where it fits (action schemas in MCP form
+ `x-zentrale`), loaded on demand (tool search, W-07), group `screen`.

| action | input | answer |
|---|---|---|
| `look` | `focus` (element id, optional), `picture` (bool, default false) | the map (trimmed); with `picture` the screenshot as an image block |
| `point` | `id`, `label` (short text shown at the marker) | "shown: #17 Upload" or an error with the next step |

Description (bible W-01: what, when yes, when no, what not) says among
other things: use `look` before every `point`; point at one thing at a time;
never claims to click; the map shows only the focused window.

**Gap to close first:** pictures from tool results do not reach the cloud
model today (`browser.md`: only Sasha's attachments carry images,
`core/cloud.py` builds image blocks only there). Anthropic accepts image
blocks inside `tool_result`; `cloud.py` must pass them through. Without
that, `picture: true` is blind.

### 5. Skill `teacher`

Loaded when Sasha asks "where do I …" or "show me how …". Behaviour, not
mechanics: one step at a time, point, explain in one sentence, wait until
Sasha has done it (`look` again to see the change), then the next step. Never
do it for Sasha. Says when something is not on screen ("open the Tools menu
first") instead of guessing.

### 6. How Sasha asks

First: the ZENTRALE chat as it is (typing). Later: push-to-talk via the
`mic` port type and the answer spoken via `speaker` (`audio_system.md`), so
Sasha does not have to leave the program to ask.

Name `screen` confirmed by Sasha 2026-10-31.

## Steps

0. **Device-adapter frame** (shared with the printer, see above): blueprint
   in `memory/hub/adapter.md`, then the generic frame.
1. **Probe on the real IDE** (no AI, no money): dump the AT-SPI tree of the
   Arduino IDE with and without the accessibility flag; screenshot + local
   OCR of the same window. Decides how much the fallback must do.
2. Port type `screen` + map schema + vectors.
3. Adapter `screen-x11`: map, pointer, overlay; a small CLI to test it
   (`zentrale screen look`, `zentrale screen point 17`).
4. `cloud.py`: image blocks in tool results.
5. Tool `screen` with descriptions and examples (W-01, W-05).
6. Skill `teacher`.
7. Try it on Arduino with Sasha; one test-bench case (`pruefstand.md`) per typical question
   ("where do I upload", "what is this button", "how do I pick the board").
   Costs computed before the run.

## Open

- Privacy of `picture: true` (a screenshot of Sasha's screen goes to the
  cloud model): free like `look`, or through the gate once per conversation?
