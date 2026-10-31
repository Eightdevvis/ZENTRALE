# Catalog lifecycle — questions for Sasha

**Stand 2026-10-31:** Open, waits for Sasha. Found while writing section 13
of [piece_descriptions_plan.md](../hub/piece_descriptions_plan.md)
(add, remove, replace pieces in the catalog). Plan only, nothing built.

One line each, with a proposal:

1. **Undo window after removal** — how long are edits and cut wires kept with
   the tombstone for "re-add"? *Proposal: 30 days; the bare tombstone stays
   forever.*
2. **Missing app with a live wire** — a ZENTRALE app vanished from a node
   but its wire is live: refuse Run with a new reason code `piece-missing`?
   *Proposal: yes, like `wire-broken`; documented/planned wires only marked.*
3. **Name on replace** — does the new piece keep the old edited name by
   default? *Proposal: no, the new piece's own name; "keep old name" is one
   checkbox in the diff.*

Done = answers into section 12/13 of the plan, then delete this file and its
INDEX line.
