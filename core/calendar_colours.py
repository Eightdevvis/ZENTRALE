# core/calendar_colours.py
#
# The colour of a calendar event — the ONE place for the rule (2026-10-29).
#
# Before, the TUI computed colours itself (tui/ansichten/kalender_ansichten.py)
# and kept its course table per device in ~/.local/state/zentrale/kalender_farben.json,
# while the phone only knew the layer colour: the same event looked different
# on every front. Now the rule lives here, the table is calendar-app data that
# syncs (data/calendar_colours.json), the palette is a data file next to this
# module (core/calendar_palette.json), and every front only draws:
#   - the backend annotates /api/calendar entries with `colour` (annotate_view)
#     — the TUI reads the slot from there;
#   - the phone ports key + lookup + precedence (mobile/lib/kalender/colours.dart)
#     and is pinned to this module by test vectors
#     (scripts/calendar_colour_vectors.py → mobile/test/daten/calendar_colour_vectors.json).
#
# Vocabulary:
#   key   what an event's colour follows: the course in its title ("analysis"),
#         a list/project it takes its title from ("quelle:<id>"), or its group
#         ("gruppe:<key>", month view B). Key strings are stored in the synced
#         table — never rename the prefixes.
#   slot  0..11, one of the palette colours t0..t11.
#   table {key: slot}, the synced file. A key not in the table falls back to
#         crc32(key) % 12 — every front computes the same.
#
# Precedence of what an event looks like (resolve):
#   X-ZENTRALE-STIL (CSS) > COLOR (RFC 7986 name) > span colour > course slot
#   > layer default.
# A style overrides only the properties it sets (e.g. just the border); the
# rest still comes from the course slot.
#
# Layer 1: stdlib + dateien/datasync/stil only, so the sync merge
# (abgleich_zusammenfuehren) can use the merge rule without an import cycle.
# Docs: memory/werkzeuge/calendar_colours.md.

import json
import os
import re
import zlib
from pathlib import Path

import datasync
import dateien
import stil as style_core

FORMAT = "zentrale-calendar-colours/1"
SLOT_COUNT = 12
# Order in which free slots are handed out (palette t0..t11): the first five as
# different as possible (cyan, orange, pink, sea green, violet) so the most
# frequent courses never look alike; then the rest.
ASSIGN_ORDER = (0, 3, 1, 11, 2, 8, 5, 4, 9, 6, 10, 7)

# Sasha, 10.10.2026: "manche kurse heißen leicht anderes, sind aber dieselben.
# exphy = experimentalphysik". Only the FIRST word of a title counts, short
# forms map to the full name. New short form → one line here.
SHORT_FORMS = {
    "exphy": "experimentalphysik",
    "tp": "theoretische",       # "TP Sprechstunde …" (23.10.2026)
    "ana": "analysis",          # "Ana Tutorium …", "Ana Sprechstunde …"
}

SOURCE_PREFIX = "quelle:"
GROUP_PREFIX = "gruppe:"
# The daily-rhythm layer (core/kalender_rhythmus.EBENE): background, never a course.
RHYTHM_LAYER = "rhythmus"
NO_GROUP = "keine"
CUSTOM_GROUP = "custom"


# ── Keys ────────────────────────────────────────────────────────────────

def course_key(title) -> str:
    """The course behind a title: first word, without the place, lower case,
    short forms resolved. 'Analysis I @ HS 1' → 'analysis';
    'ExPhy Übung' → 'experimentalphysik'; '' → ''."""
    name = (title or "").split(" @ ")[0].strip().lower()
    word = re.split(r"[\s\-–:/,.()]+", name)[0] if name else ""
    return SHORT_FORMS.get(word, word)


def source_key(source) -> str | None:
    """`quelle` of an entry ({art, id}) or its id → 'quelle:<id>'. The colour
    follows the list, not the live title — otherwise the block would change
    colour every time an item is ticked off."""
    sid = source.get("id") if isinstance(source, dict) else source
    return SOURCE_PREFIX + str(sid) if sid else None


def group_key(category, category_name=None) -> str | None:
    """Group (CATEGORIES) → 'gruppe:uni' / 'gruppe:custom:<name casefolded>';
    no group → None. Same key as the TUI's month grouping
    (tui/ansichten/kalender_gruppen.schluessel)."""
    if not isinstance(category, str) or not category or category == NO_GROUP:
        return None
    if category == CUSTOM_GROUP:
        n = (category_name or "").strip() if isinstance(category_name, str) else ""
        return GROUP_PREFIX + "custom:" + n.casefold() if n else None
    return GROUP_PREFIX + category


def entry_key(entry) -> str | None:
    """Colour key of an API entry (the dict /api/calendar returns): its list
    source if it has one, else the course in its title. None = no key (empty
    title) → layer default."""
    if not isinstance(entry, dict):
        return None
    k = source_key(entry.get("quelle")) if isinstance(entry.get("quelle"), dict) else None
    return k or course_key(entry.get("label")) or None


def entry_group_key(entry) -> str | None:
    if not isinstance(entry, dict):
        return None
    return group_key(entry.get("kategorie"), entry.get("kategorie_name"))


def is_span(entry) -> bool:
    """A multi-day span: drawn in the span colour, never takes a course slot.
    `span`/`von` mark the span rows of the view, `spanning` the days of a span
    (a one-day "span" — first and last day — is a normal event)."""
    if not isinstance(entry, dict):
        return False
    if entry.get("span") or entry.get("von"):
        return True
    return bool(entry.get("spanning")) and not (entry.get("span_first") and entry.get("span_last"))


def is_phase(entry) -> bool:
    return isinstance(entry, dict) and entry.get("layer") == RHYTHM_LAYER


# ── Slots ───────────────────────────────────────────────────────────────

def fallback_slot(key: str) -> int:
    """Computed slot for a key the table does not know. crc32, not hash():
    hash() differs per process; crc32 is the same in Python and Dart."""
    return zlib.crc32(key.encode("utf-8")) % SLOT_COUNT


def valid_slot(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and 0 <= x < SLOT_COUNT


def slot_for(key, slots: dict) -> int | None:
    """Slot of a key: the table, else the fallback. No key → None."""
    if not key:
        return None
    s = (slots or {}).get(key)
    return s if valid_slot(s) else fallback_slot(key)


def count_keys(entries) -> dict:
    """How often each key occurs among `entries` (course/source key and group
    key). Spans and rhythm phases do not count (background, not a course)."""
    n: dict = {}
    for e in entries:
        if not isinstance(e, dict) or is_span(e) or is_phase(e):
            continue
        for k in (entry_key(e), entry_group_key(e)):
            if k:
                n[k] = n.get(k, 0) + 1
    return n


def assign(entries, slots: dict) -> list:
    """Every key that occurs at least twice in `entries` and has no slot yet
    gets the next free slot in ASSIGN_ORDER (all taken → its fallback slot).
    More frequent keys first, so the real courses get the clearest colours.
    One-off events take their fallback slot and occupy nothing. Changes
    `slots`; returns the new keys (empty = nothing to save). A slot never
    moves once given."""
    n = count_keys(entries)
    new = sorted((k for k, c in n.items() if c >= 2 and k not in slots),
                 key=lambda k: (-n[k], k))
    for k in new:
        taken = set(slots.values())
        free = [p for p in ASSIGN_ORDER if p not in taken]
        slots[k] = free[0] if free else fallback_slot(k)
    return new


def view_entries(view) -> list:
    """All entries of an /api/calendar answer ({days: {iso: [entries]}})."""
    days = view.get("days") if isinstance(view, dict) else None
    out = []
    for lst in (days.values() if isinstance(days, dict) else []):
        out.extend(e for e in (lst if isinstance(lst, list) else []) if isinstance(e, dict))
    return out


# ── Style precedence ────────────────────────────────────────────────────

def style_from_ics(style_text, color_name) -> dict | None:
    """What an event's own look is, from its .ics lines: X-ZENTRALE-STIL
    (CSS, already unescaped) wins; without it COLOR (RFC 7986: a CSS3 name,
    other calendars, or hex) becomes the fill. A broken STIL line → None (and
    COLOR is not consulted: the event has a style, just an unreadable one).
    Used by core/kalender_ics_abbildung and ported 1:1 to the phone."""
    if style_text is not None:
        try:
            return style_core.pruefen(style_core.aus_css(style_text), style_core.KASTEN) or None
        except ValueError:
            return None
    if color_name is not None:
        h = style_core.hex_aus_name(str(color_name))
        return {"background-color": h} if h else None
    return None


def resolve(style, key, slots: dict, span: bool = False) -> dict:
    """Where an event's colour comes from — precedence, front-agnostic:
    {"source": "style"|"span"|"course"|"layer", "role": "t<slot>"|"sp1"|None,
     "slot", "key", "style"}.
    `role` is the palette role for everything the style leaves open; None =
    the front's layer default. `style` is the clean style dict or None."""
    style = style if isinstance(style, dict) and style else None
    slot = None if span else slot_for(key, slots)
    role = "sp1" if span else ("t%d" % slot if slot is not None else None)
    source = "style" if style else ("span" if span else ("course" if slot is not None else "layer"))
    return {"source": source, "role": role, "slot": slot, "key": key, "style": style}


def readable_on(background: str) -> str:
    """Black or white, whichever reads better on `background` (relative
    luminance threshold 0.179, as the TUI's style box)."""
    def k(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (k(v) for v in style_core.hex_zu_rgb(background))
    return "#000000" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 else "#ffffff"


def block_colours(resolved: dict, theme: str, palette: dict | None = None,
                  layer_default: str | None = None) -> dict:
    """Final hex colours of an event block in `theme` ("day"|"night"):
    {fill, text, border}. Style properties override, the palette role fills
    the rest (fill = role fill, text = role on_fill); no role → layer_default
    as fill. Same rule as the TUI's style box (tui/ansichten/kalender_stil.farben):
    a style fill without a text colour gets black/white, a border without its
    own colour takes the text colour."""
    pal = (palette or load_palette())["themes"][theme]["roles"]
    role = pal.get(resolved.get("role") or "")
    fill = role["fill"] if role else layer_default
    text = role["on_fill"] if role else (readable_on(layer_default) if layer_default else None)
    st = resolved.get("style") or {}
    if st.get("background-color"):
        fill = st["background-color"]
        text = st.get("color") or readable_on(fill)
    elif st.get("color"):
        text = st["color"]
    border = st.get("border-color") or text
    return {"fill": fill, "text": text, "border": border}


# ── Palette (data file next to this module) ─────────────────────────────

PALETTE_PATH = Path(__file__).with_name("calendar_palette.json")
_palette_cache: dict = {}


def load_palette() -> dict:
    if "p" not in _palette_cache:
        with open(PALETTE_PATH, encoding="utf-8") as f:
            _palette_cache["p"] = json.load(f)
    return _palette_cache["p"]


# ── The table on disk (data/calendar_colours.json, synced) ──────────────

def parse_table(raw) -> dict:
    """File content (bytes/str/dict) → {key: slot}; tolerant: broken or
    foreign content → {} (the views must never fail on it). Also reads the
    old flat format {key: slot} of the TUI's local file."""
    try:
        d = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(d, dict):
        return {}
    slots = d.get("slots") if d.get("format") == FORMAT else (None if "format" in d else d)
    if not isinstance(slots, dict):
        return {}
    return {k: v for k, v in slots.items() if isinstance(k, str) and k and valid_slot(v)}


def table_text(slots: dict) -> str:
    """{key: slot} → file content; keys sorted so equal tables are equal bytes
    (the sync compares bytes)."""
    return json.dumps({"format": FORMAT, "slots": dict(sorted(slots.items()))},
                      indent=1, ensure_ascii=False) + "\n"


def read_table(path) -> dict:
    try:
        with open(path, "rb") as f:
            return parse_table(f.read())
    except OSError:
        return {}


def write_table(path, slots: dict) -> None:
    dateien.atomar_schreiben(path, table_text(slots))
    datasync.notify_change(str(path))


# ── One-time migration of the TUI's old local table ─────────────────────
# Until 2026-10-29 the TUI kept {key: slot} per device in
# ~/.local/state/zentrale/kalender_farben.json (env ZENTRALE_KALENDER_FARBEN).
# Its entries move into the synced table once per device: a key the synced
# table already has keeps its slot there (first assignment wins — the cloud
# is never overwritten), every other key comes over with its old slot. The
# old file stays as a backup; a marker next to it says it was taken over.

def old_table_path() -> str:
    return (os.environ.get("ZENTRALE_KALENDER_FARBEN")
            or os.path.expanduser("~/.local/state/zentrale/kalender_farben.json"))


def migrate(path, old_path=None) -> dict:
    """Take the old local table over into `path` once. →
    {"migrated": bool, "taken": n, "kept": n (key already in the synced
    table), "old": path}. Without an old file, or already done: migrated False."""
    old = old_path or old_table_path()
    marker = old + ".migrated"
    result = {"migrated": False, "taken": 0, "kept": 0, "old": old}
    if os.path.exists(marker) or not os.path.exists(old):
        return result
    try:
        with open(old, "rb") as f:
            old_slots = parse_table(f.read())
    except OSError:
        return result
    slots = read_table(path)
    taken = {k: v for k, v in old_slots.items() if k not in slots}
    result.update(taken=len(taken), kept=len(old_slots) - len(taken))
    if taken:
        slots.update(taken)
        write_table(path, slots)
    try:
        dateien.atomar_schreiben(marker, json.dumps(
            {"into": str(path), "taken": len(taken), "kept": result["kept"]}) + "\n")
    except OSError:
        pass
    result["migrated"] = True
    return result


_migrated: set = set()


def annotate_view(view: dict, path) -> dict:
    """The backend's step for /api/calendar: (1) once per process and table,
    migrate the old local table; (2) assign slots to new recurring keys in
    this view and save the table if something was added; (3) put `colour`
    on every entry: {key, slot, group_key, group_slot}. The fronts draw
    t<slot> and never compute a colour themselves. Returns `view`."""
    p = str(path)
    if p not in _migrated:
        _migrated.add(p)
        try:
            migrate(p)
        except OSError:
            pass
    slots = read_table(p)
    entries = view_entries(view)
    if assign(entries, slots):
        try:
            write_table(p, slots)
        except OSError:
            pass                    # then just for this answer
    for e in entries:
        k, g = entry_key(e), entry_group_key(e)
        e["colour"] = {"key": k, "slot": slot_for(k, slots),
                       "group_key": g, "group_slot": slot_for(g, slots)}
    return view


# ── Sync merge (core/abgleich_zusammenfuehren, art "calendar_colours") ──

def merge(basis, local, mitte) -> bytes:
    """Merge rule of the synced table: union of all keys; a key both sides
    know keeps the slot the cloud (Mitte) has — whoever reached the cloud
    first assigned it first, and the cloud is never overwritten. No note,
    no conflict copy: it is not user text, and every device converges to
    the cloud's table. Deletions are ignored (slots never go away)."""
    slots = parse_table(local) if local is not None else {}
    slots.update(parse_table(mitte) if mitte is not None else {})
    return table_text(slots).encode("utf-8")
