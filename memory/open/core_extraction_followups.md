# Core extraction: next steps and TUI logic findings

**Stand 2026-10-31:** Open, does not wait for Sasha. From the inventory of
22.10.2026, re-measured 31.10. (`memory/hub/kern_auszug_inventur.md` — order,
next step and the decisions for Sasha live there, not here); steps 0–2
(security, hub basics, map) done.

- **A1 (bug risk):** changing an event in the calendar TUI is up to 7 write
  calls without rollback; "once → recurring" = create new + delete old — an
  abort leaves half a state (`tui/ansichten/kalender_werkzeuge.py:1078–1300`,
  `kalender_bedienung.py:590`; lines as of 31.10.: `1117–1290`). Move into
  the core as one call.
- A2–A20: logic that lives only in the TUI (calendar rules, graph forecast,
  note block ids without `stand`, app list `RAD_APPS` …) — see section A.
- Guards E5–E8 (no copies in `tui/`, one action = one write, no data files in
  `tui/`, route ownership) not built; E1, E2, E4, E9 exist.
- Graphs need untangling before they can move (section D).
- Lists: own file [list_app_extraction.md](list_app_extraction.md).
- `GET /api/data/*` / `POST /api/log`: fixed (a4c4872); remaining from the
  finding: backend listens on `0.0.0.0` with access mode „melden" by default.
