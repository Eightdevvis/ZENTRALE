# Calendar: one edit = one call

**Stand 2026-10-31: built (`270fada`).** One user edit of a calendar entry is
one call to the core, saved all or nothing: `PUT /api/calendar/edit`
(`core/kalender_bearbeiten.edit`) on top of `kalender.one_write()`. The TUI
sends one call per action; guard E6 keeps it so. Inventory row A1 in
[../hub/kern_auszug_inventur.md](../hub/kern_auszug_inventur.md).

## Why and how

Before, editing in the TUI was up to 7 separate writes (`typ` before, `PUT
eintrag/routine/spanne`, `kategorie`, `stil`, `quelle`, `typ` after,
`ebene`); "once → series/span" was create + delete. A failure halfway left a
half-changed entry. Sasha: „omg bitte was is das denn haha. beheben."

- **`kalender.one_write()`** (context manager): inside it `_load_raw` reads
  and `_save_raw` writes a working copy of this thread; the calendar lock
  (now re-entrant) is held for the whole block. Clean exit → ONE real save
  (with push and alarms); exception → nothing written. Nested blocks join
  the outer one. Caveat: inside the block the .ics store has not yet given
  new entries their UID — read new kennungen only after the block.
- **`kalender_bearbeiten.edit(kennung, new, day=, replace=, locate=)`** and
  **`PUT /api/calendar/edit`** (described in `openapi.yaml`): `new` = the
  main change per kind (one-time `day, label, time, ende, ort`; series
  `label, time, ende, ort, wiederholung`; span `label, ort, verschieben,
  bis` — the same semantics as the old single routes, now targeted by
  kennung) plus the wished `kategorie, kategorie_name, stil, typ,
  vorwarnung, soll_abstand, quelle, layer`; the core compares them with the
  stored entry and changes only what differs, in the old order (typ →
  normal first, deadline after the change, layer last). `replace {kind:
  routine|spanne, …create body}` creates the series/span and deletes the
  one-time entry in the same save (`routine_from_body`/`span_from_body` are
  also what the POST routes use). `locate {layer, day, label, time}` instead
  of `kennung` for JSON entries without one. Answer `{ok, eintrag}` re-read
  by kennung; rejection 400 `{error, code, next}` (new code
  AENDERUNG-ABGELEHNT; `next` from `core/fehlercodes.py`), nothing written.
- `spanne_neu` (span + its day times) is one save now as well.
- TUI: the edit forms build one `PUT /api/calendar/edit` (`_edit_call`,
  `_edit_wish`); the old per-field calls are gone. **Guard E6:**
  `kalender_werkzeuge._plan` raises on a second write call;
  `tests/test_calendar_one_call.py` checks that, that every plan goes
  through `_plan`, and every edit form. Core: `tests/test_calendar_edit.py`
  (one save, rejection writes nothing, failure in the delete half of a
  conversion rolls back) — both stores.
- Still several calls elsewhere: none known in the TUI (legacy list empty).
  The old single routes stay for other callers (browser, AI adapter).
