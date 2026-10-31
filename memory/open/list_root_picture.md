# List view: the root's boxes still drawn in process

**Stand 2026-10-31:** Open, **waits for Sasha** (an architecture fork). Found
by Claude during lists step 3
([../hub/list_extraction_plan.md](../hub/list_extraction_plan.md)).

Lists step 3 moved everything the TUI's list view computed in its own process
behind routes: counts and display order (`GET /api/lists?view=1`), filing
targets (`GET /api/lists/targets`), the picture of an open level
(`GET /api/lists/<lid>/bild`). `listen_baum` left the TUI door. **One thing
the plan did not name is left:** the root of the view (projects on top, a
line, the other lists below) draws each node as a box with
`listen_bild.kasten` in process (`tui/ansichten/fokus.py`, `l_desc_view`,
`kasten_render`). So `listen_bild` is still in the TUI door and in
`deploy/aussenposten.txt` (with `listen_baum`, which it imports).

Where the root's picture lives decides the shape of a new interface, so it
was not decided in the run. Options:

1. **The root is a picture of the core too** — `listen_bild.wurzel(...)`
   draws both zones, labels and the scroll window; served by the picture
   route without a list (e.g. `GET /api/lists/bild?w&h&auswahl`). The TUI only
   paints. Same rule as everywhere ("one picture"), `listen_bild` leaves the
   door. **Recommended.**
2. **Only the boxes come over HTTP** — the root asks for the boxes of its
   nodes (selected and not) and keeps zones, labels and scrolling itself.
   Smaller route, but layout logic stays in the surface.
3. **Leave it** — `listen_bild` stays in the door until the move (step 5).

Done = the TUI imports no list module, `listen_bild` out of
`TUI_TUER_HOECHSTENS` (`tests/test_kern_bauplan.py`), `bauplan_kern.md` and
`deploy/aussenposten.txt` (with `listen_baum`).
