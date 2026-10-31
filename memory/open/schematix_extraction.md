# Schematix extraction

**Stand 2026-10-31:** Open, does not wait for Sasha (only for the two merges
below). Found by Sasha: Schematix (building kit steps 13–15, 2026-10-30) was
built as a built-in app inside the core, against „tiny core, everything else
packages" ([building_kit_plan.md](../hub/building_kit_plan.md) §3). The rule
since then: CLAUDE.md, „Apps live outside the core".

## What moves

- `core/schematix_*.py` (7 modules)
- `tui/ansichten/schematix*.py` (4 views)
- `ui/routen/schematix.py` (`/api/schematix/*`, `/api/pieces`)
- the `schematix` entry in `core/eingebaute_apps.py` (`EINGEBAUT`, `PORTS`)
  and its line in [bauplan_kern.md](../system/bauplan_kern.md) „Altlast:
  Built-in apps" (the guard in `tests/test_kern_bauplan.py` then asks to
  strike it from `BUILT_IN_APPS_AT_MOST` too)
- `schematix_versions` in the `zentrale_cli/` door, docs
  [schematix.md](../hub/schematix.md), [schematix_style.md](../hub/schematix_style.md)

## Target

Its own package (own folder/repo with `app.toml`, like tutor/map/budget),
**preinstalled at signup like the cloud**, deselectable and holdable in the
store. Its data `data/schematix/**` comes from its manifest's `[daten]`.

## Stays in the core

`tui/bausteine/canvas.py`, `core/wires.py`, `sketch_compiler.py`,
`generations.py`, `port_types.py` — general building blocks. Schematix uses
them **only via public interfaces** (routes, ports, building blocks); what is
missing becomes a general interface in the core first.

## When

After the Schematix restyle and the canvas navigation rework are merged.

Inventory of the whole extraction: [kern_auszug_inventur.md](../hub/kern_auszug_inventur.md).
Other leftovers: [schematix_followups.md](schematix_followups.md).
