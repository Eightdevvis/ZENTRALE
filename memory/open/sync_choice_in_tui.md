# Per-app sync choice not visible in the TUI; `/api/apps` lacks built-in apps

**Stand 2026-10-30:** Open, does not wait for Sasha. Left over from the
cloud-as-app build (23.10.2026, `memory/hub/cloud_app.md`).

- Only `zentrale status` shows which app syncs; the TUI shows nothing and
  cannot change it.
- `GET /api/apps` lists manifest apps only, not the built-in ones from
  `core/eingebaute_apps.py` (calendar, lists, …, cloud, adapter).
- No rights dialog for foreign manifests yet; until then the positive list in
  `core/abgleich_auswahl.py` is the only guard.
