# Map app: GitHub repo, backend restart, cleanup

**Stand 2026-10-30:** Open, **waits for Sasha** (create the repo). The map
moved out on 23.10.2026 into `~/codicus/zentrale-karte` (local git, 28
commits, **no remote**).

- Create the private GitHub repo `zentrale-karte`, add it as remote, push.
- Restart the backend on each node so the hub starts the map server itself
  (until then `/api/map` answers 503 `aus`).
- Optional: own venv in `zentrale-karte` (today the hub uses ZENTRALE's).
- The old cache `core/map/data/cache/` in ZENTRALE was copied, not moved; it
  can be deleted once not needed (gitignored).
