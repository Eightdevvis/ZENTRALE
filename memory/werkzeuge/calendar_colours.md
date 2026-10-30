# Calendar colours — one colour per event on every front

**Since 2026-10-29.** Before, the TUI computed event colours itself and kept
its course table per device (`~/.local/state/zentrale/kalender_farben.json`);
the phone only knew the layer colour, so almost everything there was one
orange. Now an event has the same colour in the TUI (A/B/C), the phone (day,
week, month, agenda, peephole table) and on every computer.

## Where what lives

| What | Where | Synced? |
|---|---|---|
| The rule (key, slot, assignment, precedence, merge) | `core/calendar_colours.py` (layer 1, stdlib + `stil`) | code |
| The course table `{key: slot}` | `data/calendar_colours.json`, `{"format": "zentrale-calendar-colours/1", "slots": {…}}`, next to `kalender_neben.json` (`kalender_speicher.pfade()["colours"]`) | **yes** — calendar-app data (`abgleich_auswahl.SICHERN`, app `kalender` in `eingebaute_apps`) |
| The palette (hex, day + night) | `core/calendar_palette.json`: per role `text`, `fill`, `on_fill` + the TUI's xterm indexes; background; `opacity` (fill/text/glass for uncommitted) | code; the phone bundles a byte-identical copy `mobile/assets/calendar_palette.json` |
| TUI drawing | `tui/ansichten/kalender_ansichten.py` (`kurs_rolle`, `gruppe_rolle`: slot → role `k_t<slot>`), xterm indexes in `tui/ansichten/farben.py` `KAL` | — |
| Phone port | `mobile/lib/kalender/colours.dart`; drawing in `views/calendar_palette.dart` (`lookOf`) | — |

**Palette: bundled, not synced** (decided 2026-10-29). The palette is part of
the app's look, not user data: changing it means a code change anyway
(TUI indexes, tests), and a bundled asset works offline from the first start.
Change a colour → edit `KAL` in `tui/ansichten/farben.py` *and*
`core/calendar_palette.json` (the test names the mismatch; hex = the standard
xterm-256 RGB of the index, `tui/pixel.xterm_rgb`), copy the file to
`mobile/assets/`, rebuild the phone app.

## Key and slot

- **Key** (`entry_key`): the list/project the event takes its title from →
  `quelle:<id>` (X-ZENTRALE-QUELLE, fallback URL `zentrale://fokus/…`) — fixed,
  so ticking off an item never changes the colour; else the **course** in the
  title (`course_key`: first word without „@ place", lower case, short forms
  `SHORT_FORMS`: `exphy` → experimentalphysik, `tp` → theoretische, `ana` →
  analysis). Empty title → no key → layer colour.
- **Group key** (`entry_group_key`): `gruppe:uni`, `gruppe:custom:<name>` from
  CATEGORIES — the colour of a grouped row in month view B.
- **Slot**: the table's slot, else `crc32(key) % 12` (the same in Python and
  Dart). Prefixes `quelle:`/`gruppe:` are stored data — never rename.
- **Assignment** (`assign`, only on computers, in `annotate_view` for every
  `/api/calendar` answer): every key that occurs ≥ 2× in the answer and has
  no slot yet gets the next free slot in `ASSIGN_ORDER` (cyan, orange, pink,
  sea green, violet, …; most frequent first). One-off events take their
  fallback slot and occupy nothing. Spans and rhythm phases never count.
  **A slot never moves.** Re-roll a colour: delete its entry from the file.
- The answer carries `colour: {key, slot, group_key, group_slot}` on every
  entry; the TUI only maps the slot to its role. The phone never assigns —
  it reads the synced table (`mobile/lib/mitte/regeln.dart` fetches
  `calendar_colours.json`) and falls back to crc32 like the core.

## Precedence (`resolve`, `block_colours`)

1. **X-ZENTRALE-STIL** (CSS from the style box) — overrides only the
   properties it sets (a border colour alone keeps the course fill). A broken
   STIL line means no style (COLOR is not consulted).
2. **COLOR** (RFC 7986 CSS3 name or hex, other calendars) → the fill.
   (1 and 2: `style_from_ics`, used by `kalender_ics_abbildung._stil_lesen`.)
3. **Span** (multi-day): span colour `sp1`.
4. **Course slot**: role `t<slot>` — fill `fill`, text `on_fill`.
5. **Layer default**: TUI `k_t0`, phone the vdir `color` of the layer.

A style fill without a text colour gets black or white (luminance > 0.179),
a border without its own colour takes the text colour — the same rule as the
TUI style box (`kalender_stil.farben`, a test keeps both equal).

**Phone look** (`CalendarPalette.lookOf`): committed blocks use the palette
fill exactly (no night softening any more — the TUI's neon fills), text the
role's `on_fill` if it reaches 4.5:1, else black/white. Uncommitted: the
same colour as glass — fill mixed into the background by `opacity.glass`,
stripes and frame in the role's text colour, text ≥ 4.5:1. Deadlines and
rhythm phases keep their own look.

## Migration of the old local table

Once per device (marker `<old file>.migrated` next to it), on the first
`/api/calendar` answer of a backend: every key of
`~/.local/state/zentrale/kalender_farben.json` (env `ZENTRALE_KALENDER_FARBEN`)
that the synced table does not have yet comes over with its slot; keys the
synced table already has keep the synced slot (the cloud is never
overwritten). The old file stays as a backup.

## Sync merge

Art `calendar_colours` in `core/abgleich_zusammenfuehren.py` →
`calendar_colours.merge`: union of all keys; a key both sides know keeps the
cloud's slot (whoever reached the cloud first assigned it first). No note, no
conflict copy; deletions are ignored. Two devices assigning concurrently
converge to the cloud's table (test `test_sync_merge_two_devices_converge`).
Two keys may end up on the same slot then — slots never move, so that stays;
new assignments skip taken slots.

## Tests and vectors

- `tests/test_calendar_colours.py`: keys, assignment, precedence, palette vs.
  TUI indexes, phone copy identical, table format, migration, merge,
  annotation, route, vectors current.
- `scripts/calendar_colour_vectors.py` → `contracts/calendar-colours/1/calendar_colour_vectors.json`
  (made-up events as real .ics, written by the core): change the core → run
  it, then `flutter test` (`test/calendar_colours_test.dart`, also writes
  `build/kalender_vorschau/colours_*.png`).
