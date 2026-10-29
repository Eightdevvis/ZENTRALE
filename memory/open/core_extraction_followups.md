# Core extraction: next steps and TUI logic findings

**Stand 2026-10-30:** Open, does not wait for Sasha. From the inventory of
22.10.2026 (`memory/hub/kern_auszug_inventur.md`); steps 1+2 (hub basics, map)
done 23.10.

- **A1 (bug risk):** changing an event in the calendar TUI is up to 7 write
  calls without rollback; "once → recurring" = create new + delete old — an
  abort leaves half a state (`tui/ansichten/kalender_werkzeuge.py:1078–1300`,
  `kalender_bedienung.py:590`). Move into the core as one call.
- A2–A16: logic that lives only in the TUI (calendar rules, graph forecast,
  note block ids without `stand`, app list `RAD_APPS` …) — see section A.
- Guards E5–E8 (TUI routes in OpenAPI, no copies in `tui/`, one action = one
  write) not built.
- Graphs need untangling before they can move (section D).
- Lists: own file [list_app_extraction.md](list_app_extraction.md).
- `GET /api/data/*` / `POST /api/log`: fixed (a4c4872); remaining from the
  finding: backend listens on `0.0.0.0` with access mode „melden" by default.
