# Schematix: what is left after steps 13–15

**Stand 2026-10-30** (found while building steps 13–15,
[../hub/schematix.md](../hub/schematix.md)):

- **Phone / web front.** Schematix exists in the TUI only. The phone has no
  Desk yet; when it gets one, it reads the same routes (`/api/schematix/map`,
  `/api/pieces`, palette) and draws the same glyph rules
  ([../hub/schematix_style.md](../hub/schematix_style.md) "Later"): pixel type
  ≥ 10 px, a real 2×2 Bayer dither, contrast ≥ 4.5:1.
- **Pixel symbol in the Erschaffen wheel.** Werkstatt and Shop have one,
  Schematix shows its name only. Sasha's taste — wait for him.
- **App titles.** Built-in apps still carry German titles (`Listen`) on the
  map; the English names live in `zentrale_cli/texte.py`. Unify in the
  renaming wave ([english_renaming_wave.md](english_renaming_wave.md)).
- **Install from the scheme.** A store app placed with `+` is planned; its
  action "install" (plan 6.3: the normal store install with the plug
  dialog) is not on the board yet — install it in the store, the piece
  turns live by itself.
- **Planned node names.** The starter scheme uses the names of heimnetz.md
  (`pc`, `pi`, `laptop`, `minipc`). A node that joins under another name
  shows as its own live piece; the planned one stays until removed (`d`).
  A "this is that one" action could re-point the planned piece.
- **Editing a thing** (title, address, notes) goes by hand in its JSON file
  for now; the board only makes planned things real (`m`).
