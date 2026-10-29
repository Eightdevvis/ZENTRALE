# List app: extraction not done

**Stand 2026-10-29:** Open, does not wait for Sasha. Left over from the list
rebuild on 11.10.2026 (boxes + one shared image, commits `b53ded0`,
`8c69f10`). Found by Claude.

The list app (`fokus`) is built to be pulled out of ZENTRALE, but is not
pulled out yet. The full plan is in
[../hub/listen_app.md](../hub/listen_app.md), section „So sieht der spätere
Auszug aus" — follow that, not a copy here. In short, still tied in:

- `core/kachel_fokus.py` imports hub code (`kachel_form`, `kachel_parameter`,
  `adressen`).
- `core/lists.py` uses `dateien`; its storage should move to `daten/fokus/`.
- `core/kalender_quelle.py`, `core/morgenblick_daten.py`,
  `ui/routen/kalender.py` and the Prüfstand read `lists` directly — later
  they have to ask over HTTP.
- Tile parameter `tiefe` is deprecated (no effect since 11.10.); it can leave
  the schema in `core/kachel_fokus.py` once no old desk addresses use it.
