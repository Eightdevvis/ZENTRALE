# core/formats.py
#
# The read rule for every versioned file format (memory/hub/building_kit_plan.md
# 2.2 rules 2 and 3, build step 5):
#
#   - Unknown major → read-only. A reader that finds a `format` whose major it
#     does not know never interprets the content and never writes the file. It
#     says so once: a note here, shown by `zentrale status` ("cloud data is
#     newer than this version — read only"). The note goes away by itself as
#     soon as the same format is read fine again (after an update).
#   - Must-preserve. Writers keep fields they do not know and write them back
#     unchanged (`keep_unknown`), so an old node rewriting a file never deletes
#     what a newer node added. tests/test_formats.py proves it for every entry
#     of FORMATS and fails when a `format` writer in core/ is not listed there.
#
# A `format` value is either a bare major (`1`, the Mitte's inhalt.enc and its
# envelopes, konto.json, the calendar side file) or "<name>/<major>"
# ("zentrale-geheim/1"). A missing `format` is the oldest form — always
# readable.
#
# Foundation (layer 1): knows no other ZENTRALE module except ai_config,
# dateien and i18n.

import datetime
import json
import os

import ai_config
import dateien
from i18n import _

DEFAULT_NOTES = "~/.local/state/zentrale/format_notes.json"

# contract key → (major this version reads and writes, label for people).
# One line per versioned format. The labels go through gettext at display time.
FORMATS = {
    "cloud-index": (1, "cloud data"),                      # inhalt.enc (core/abgleich.py)
    "cloud-envelope": (1, "a file from another device"),    # knoten/<node>/*.enc
    "account-file": (2, "the account file of this device"),  # konto.json (core/konto.py)
    "adapter-secrets": (1, "connected services' keys"),     # data/adapter/geheim.enc
    "adapter-connection": (1, "a connected service"),       # data/adapter/anschluesse/*.json
    "calendar-app-setting": (1, "the calendar setting"),    # kalender_einstellung
    "calendar-side-file": (1, "calendar extras"),           # data/kalender_neben.json
    "calendar-colours": (1, "calendar colours"),            # data/calendar_colours.json
    "account-ownership": (1, "the apps your account owns"),  # GET/PUT /v1/besitz (account_ownership)
    "plug-wires": (1, "the plugs of an app"),               # data/adapter/plugs/*.json (core/plug_store.py)
    "node-wires": (1, "another device's wiring"),          # `wires` in a node description (core/wires.py)
    "node-versions": (1, "another device's versions"),     # `versions` in a node description (core/schematix_versions.py)
    "schematix-palette": (1, "the colours of Schematix"),   # data/schematix/palette.json (core/schematix_store.py)
}


class NewerFormat(Exception):
    """The content has a major this version does not know: do not interpret,
    do not write. `what` is the key in FORMATS, `found` the major seen."""

    def __init__(self, what, found):
        self.what, self.found = what, found
        super().__init__(newer_text(what))


def major(value):
    """`1` → 1, "zentrale-geheim/2" → 2, "3" → 3; anything else → None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        tail = value.rsplit("/", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def known(what) -> int:
    return FORMATS[what][0]


def is_newer(value, what) -> bool:
    """Is `value` (a `format` field) a major this version does not know?
    A missing or unreadable value is not newer — the old readers decide."""
    m = major(value)
    return m is not None and m > known(what)


def check(doc, what, field="format"):
    """For a parsed document: raise NewerFormat (and leave one note) if its
    `format` is newer; otherwise clear an old note of this format. Non-dicts
    pass — the caller's own checks handle them."""
    value = doc.get(field) if isinstance(doc, dict) else None
    if is_newer(value, what):
        note_newer(what, major(value))
        raise NewerFormat(what, major(value))
    clear(what)
    return doc


def newer_text(what) -> str:
    text = _("{what} is newer than this version — read only").format(what=label(what))
    return text[:1].upper() + text[1:]


def label(what) -> str:
    return _(FORMATS[what][1]) if what in FORMATS else what


# ── Notes for `zentrale status` ────────────────────────────────────────

def _notes_path() -> str:
    return os.path.expanduser(ai_config.setting("format_notes") or DEFAULT_NOTES)


def _read_notes() -> dict:
    try:
        with open(_notes_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def note_newer(what, found):
    """Remember once that `what` was found in a newer major (no rewrite when
    the note is already there — a reader may run every five minutes)."""
    notes = _read_notes()
    if isinstance(notes.get(what), dict) and notes[what].get("found") == found:
        return
    notes[what] = {"found": found, "since": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        dateien.json_schreiben(_notes_path(), notes)
    except OSError:
        pass


def clear(what):
    """The format was read fine: its note (if any) is no longer true."""
    if not os.path.exists(_notes_path()):
        return
    notes = _read_notes()
    if notes.pop(what, None) is not None:
        try:
            dateien.json_schreiben(_notes_path(), notes)
        except OSError:
            pass


def notes() -> list:
    """→ [{what, found, since, text}] for `zentrale status`, oldest first."""
    out = []
    for what, n in sorted(_read_notes().items(), key=lambda kv: str(kv[1].get("since"))):
        if isinstance(n, dict):
            out.append(dict(n, what=what, text=newer_text(what)))
    return out


# ── Must-preserve ──────────────────────────────────────────────────────

def keep_unknown(old, new, owned=()):
    """`new` plus every top-level field of `old` that `new` does not set and
    the writer does not own. `owned` = fields the writer computes itself and
    may drop on purpose (e.g. an optional list that became empty). → new dict."""
    if not isinstance(old, dict):
        return dict(new)
    out = {k: v for k, v in old.items() if k not in new and k not in owned}
    out.update(new)
    return out
