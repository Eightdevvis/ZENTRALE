# Port types, wires and the Run gate (building kit steps 9 and 9b)

**Stand 2026-10-30: built `6a63d16` (steps 9 and 9b; plan:
[building_kit_plan.md](building_kit_plan.md) section 8).** The type system of the
building kit and the one gate every wiring change passes. The plan says *why*
(sections 1, 2, 6.7); this file says *what was built and how the vocabulary
was decided*. Sasha: *„niemand darf je einen kaputten Sketch kompilieren und
sein Netzwerk verbuggen."*

## Where it lives

| Part | File |
|---|---|
| Schemas of every item (JSON Schema 2020-12, one file, `$defs`): need, offer, manifest ports, registry, piece, wire, sketch, generation | `contracts/ports/1/ports.schema.json` |
| The type registry (data) | `contracts/ports/1/types.json` |
| Vectors: built-in manifests, item vectors, 17 sketches with their outcome | `contracts/ports/1/port_vectors.json` (made by `scripts/port_vectors.py`, expectations written by hand there) |
| Registry, item check, SemVer, short/long port forms | `core/port_types.py` |
| Ports of an app: `needs`/`offers`, old `rechte`/`liefert`/`[daten]` | `core/app_ports.py`; built-ins declare theirs in `core/eingebaute_apps.py` (`PORTS`, `INSTANCE_PORTS`, `NODE_PORTS`) |
| Wires as a projection, write-back into the owners | `core/wires.py` |
| The compiler (stage 2 + 3, the hard gate) | `core/sketch_compiler.py` |
| Run: diff, generations, switch, apply agent, roll-back; `choose_sync` | `core/generations.py` |
| HTTP | `GET /api/wires`, `PUT`/`DELETE /api/wires/<id>` (`ui/routen/hub_wires.py`, `openapi.yaml`) |
| Tests | `tests/test_port_types.py`, `tests/test_wiring_run.py`, `mobile/test/ports_test.dart` |

The routes are under `/api/`, not `/hub/` as the plan first wrote: `/hub/…`
is the side every app answers itself (`/hub/gesund`, `/hub/ereignis`).

## The vocabulary — and why it is cut this way

The plan names the vocabulary the main risk: too loose, and the checks catch
nothing; too rigid, and every new device or app needs a new major. The cut:

- **A port type is a family plus, for some families, a qualifier**:
  `sync`, `files`, `model`, `calendar-source`, `mic` …, and `event:<name>`,
  `tile:<kind>`, `read:<app>`, `write:<app>`. The families are closed (one
  registry entry each, a test vector and a reader on each side — plan 1.3);
  the qualifiers are open names, matched exactly. So an app can publish a
  new event or tile without a registry change (not rigid), but nobody can
  invent `teleport` (not loose).
- **Access is not part of the type.** `files` read or write is the need's
  `access`, as TOSCA puts properties on the requirement, not on the
  capability type. Otherwise every family would double.
- **Every family carries, in the registry** (TOSCA terms where they fit):
  `version` (SemVer — the version this code speaks), `layer` (data, services,
  hardware, network, power — the map layers of plan 6.2), `relationship`
  (TOSCA normative: DependsOn, ConnectsTo, HostedOn, AttachesTo), `scope`,
  `cycles`, default `occurrences`, and for the physical layers the NetBox
  term (interface, cable, power port).
- **`scope` answers "who owns the wire" (plan 1.4) and how it is counted:**
  `node` (sync, hardware: the node the consumer is stationed on, counted per
  node — the tutor may sync on the laptop and stay local on the mini),
  `instance` (calendar source, model, files: the consumer app instance, synced
  "without mercy"), `link` (network and power between nodes and devices).
- **`occurrences` = TOSCA `[min, max]`, max may be `UNBOUNDED`.** Most
  defaults are `[0, 1]`: a socket holds one plug and may stay empty — that is
  what "refusing leaves the port off" (step 11) needs. `calendar-source` is
  `[1, 1]`: a calendar always has exactly one source. The adapter's `data`
  socket is declared `[1, 1]` (it must sync, `pflicht`).
- **`cycles`:** data flow (sync, files, model, calendar source, write) must
  not loop; events, tiles, reads and all physical links may (a mesh network
  is a loop).
- **Piece kinds are only three:** `node` (a ZENTRALE node with its platform
  ports: local calendar, hardware), `app` (an app instance; a calendar
  instance is its own piece `app:kalender/<id>`), `device` (a thing without
  ZENTRALE, NetBox `role`: router, printer, power-bank …).
- **Versions:** a need carries a range (`sync@^1`, also `~1.2`, `1.2.3`,
  `*`), an offer a version; a node's description carries the versions it
  speaks (`types`) and whether it runs the apply agent (`apply_agent`). No
  version ranges between packages (plan 2.2 rule 6).
- **Addresses:** a piece is its object's `zentrale://` address (`ref`) plus a
  short id (`app:tutor`, `node:minipc`); a port is `<ref>port/<id>`.

## The rules of the compiler

Stage 2 (schema) stops on any fault. Stage 3, all rules, any error → no
generation; each error carries `code`, `text` (gettext) and the `piece` /
`wire` / `port` it is pinned to:

| Code | Rule |
|---|---|
| `schema` | the sketch, each piece, each wire against `ports.schema.json` |
| `duplicate-id`, `unknown-piece`, `unknown-port`, `unknown-type` | ids unique; wires join an existing offer and need of a registered type |
| `type-mismatch`, `version-mismatch` | wire type = offer type = need type; the offer's version inside the need's range |
| `unmet-requirement`, `too-many` | per need (per node for node-scoped types): live wires ≥ min, all non-planned wires ≤ max. Needs read from old keys (`legacy`) are not demanded |
| `cycle` | no loop over cycle-forbidding types; every wire on the loop is named |
| `double-owner`, `wrong-owner` | a resource (`owns`, e.g. `file:data/lists.json`) has one owner; a wire's owner is what its scope says |
| `live-on-planned` | nothing live hangs on a planned piece (wire end, owner, or the node an app is on) |
| `wire-broken` | a broken wire cannot be live |
| `type-too-new` | every node a non-planned wire runs on speaks a version in range |
| `node-unmanaged` | a node without the apply agent is read-only: its wires must equal `current` |

## Run

`generations.run(sketch)` = compile → diff against what is **in effect** (the
fresh projection, not the stored generation: a setting changed on a path that
does not pass the gate yet must never be reverted) → save both as
generations → switch the node's `current` (a symlink replaced in one rename)
→ the apply agent writes the owners (`wires.write`: only differences; sync →
`abgleich_apps.replace`, calendar → `adapter_ablauf.kalender_quelle_setzen`)
→ health check (writers succeeded and the projection now says what the
generation says) → failure: back to the previous generation and apply that.
Generations are self-contained JSON, `hash` = sha256 over the JCS form (RFC
8785) of format + pieces + wires; the last 10 per node are kept
(`~/.local/state/zentrale/generations`, setting `generations`).

**Fed by:** the CLI sync choice (`befehle.choose_sync`: new app asks,
wizard cloud folder, wizard purpose, wizard finish) and the routes. A device
that never chose (`abgleich_apps` unset = everything) starts from "nothing
decided" when it first chooses, as `setzen` always did.

## What later steps build on

- **Step 11 (plug dialog):** `app_ports.of_app(name)` lists the needs; offers
  of every piece come from `wires.sketch()`; a proposal is a wire, the
  confirmation is `generations.run` (refused → errors pinned to the port).
  Refusing = a wire with `state: off`. A new store app with `needs` and no
  wire fails the compile only for needs with min ≥ 1 — the dialog must wire
  those before the install counts.
- **Steps 13–15 (Schematix):** `GET /api/wires` is the read-only map data
  (pieces with ports, wires with layer via the registry); other nodes join
  as `wires.piece_of_description(<GET /v1/knoten entry>)` (managed or not);
  `PUT …?plan=1` gives the diff for the Run button; errors carry piece/wire
  ids to pin on the drawing; the socket table for the red ✕ is the registry
  (`port_types.entry`, same type = fits). Planned pieces and wires already
  compile (vectors `good-planned-new-type`, `live-on-planned`).

## Not yet

Open item [../open/run_gate_followups.md](../open/run_gate_followups.md): the
apply agent is not on the keeper timer, `zentrale adapter calendar` writes the
calendar source around the gate, the compiler's graph rules are not ported
to Dart, other nodes' wires are not projected (each node sees its own).
