# List app: extraction not done

**Stand 2026-10-29:** Open, does not wait for Sasha. Left over from the list
rebuild on 11.10.2026 (boxes + one shared image, commits `b53ded0`,
`8c69f10`). Found by Claude.

The list app (`fokus`) is built to be pulled out of ZENTRALE, but is not
pulled out yet. The full plan is in
[../hub/listen_app.md](../hub/listen_app.md), section „So sieht der spätere
Auszug aus" — follow that, not a copy here. Step plan (core first, then the move):
[../hub/list_extraction_plan.md](../hub/list_extraction_plan.md). In short, still tied in:

- `core/kachel_fokus.py` imports hub code (`kachel_form`, `kachel_parameter`,
  `adressen`).
- `core/lists.py` uses `dateien`; its storage should move to `daten/fokus/`.
- `core/morgenblick_daten.py` and `ui/routen/kalender.py` read `lists`
  directly — later they have to ask over HTTP. `core/kalender_quelle.py`
  asks through one seam since 31.10. (`lists.resolve` = `POST
  /api/lists/aufloesen`; the selection still enumerates `lists.read_lists`);
  the Prüfstand takes the place by setting (`ZENTRALE_LISTS_DIR`).
- Tile parameter `tiefe` is deprecated (no effect since 11.10.); it can leave
  the schema in `core/kachel_fokus.py` once no old desk addresses use it.
