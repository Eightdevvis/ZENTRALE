# English renaming wave for existing German code and docs

**Stand 2026-10-30:** Open, waits for Sasha (to commission the run).

Rule since 29.10. (CLAUDE.md, top): everything new is English; existing German stays until a dedicated, large agent run renames it. That run is not planned or started. It needs a plan first (order, compatibility of data file names and keys, i18n of existing UI strings, test strategy), then waves per area. Related: [list_names_english.md](list_names_english.md).

**UI texts (Sasha, 30.10.):** „wir brauchen keine deutschen übersetzungen, eher eine englische vereinheitlichung." German is no longer the first UI language; the goal is one uniformly English UI. The translation tables stay (other languages later), but no new German entries are added. Existing German UI texts — German strings in code and the German entries of the `.po`/ARB tables — become part of this wave: unify them to English, then drop the German entries. Not before the wave.
