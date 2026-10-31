# core/schematix_store.py
#
# Where Schematix keeps its own data (memory/hub/schematix.md): one folder,
# synced like every app's data (positive list `data/schematix/**`, app
# `schematix` in core/eingebaute_apps.py). Setting `schematix_ordner` (env
# ZENTRALE_SCHEMATIX_ORDNER; tests) moves it — then it is not synced.
#
#   palette.json      the colour roles Sasha tuned (memory/hub/schematix_style.md);
#                     defaults: contracts/schematix/1/palette.json
#
# Every file carries a `format` with the read rule of core/formats.py
# (unknown major → read-only, unknown fields kept on write).
#
# Foundation (layer 1).

import json
import os

import ai_config
import dateien
import datasync
import formats

PALETTE_FORMAT = "zentrale-schematix-palette/1"
_ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CONTRACT = os.path.join(_ROOT, "contracts", "schematix", "1")
_HEX = set("0123456789abcdef")


class StoreError(ValueError):
    """Input or file does not fit. `code` = HTTP status for the route."""

    def __init__(self, text, code=400):
        super().__init__(text)
        self.code = code


def folder() -> str:
    own = ai_config.setting("schematix_ordner")
    if own:
        return os.path.abspath(os.path.expanduser(str(own)))
    return os.path.join(_ROOT, "data", "schematix")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise StoreError("not readable JSON: %s" % os.path.basename(path), 422)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dateien.json_schreiben(path, data)
    datasync.notify_change(path)


# ── Palette (colour roles) ───────────────────────────────────────────────

def default_palette() -> dict:
    with open(os.path.join(CONTRACT, "palette.json"), encoding="utf-8") as f:
        return dict(json.load(f)["roles"])


def _palette_path():
    return os.path.join(folder(), "palette.json")


def is_hex(v) -> bool:
    return isinstance(v, str) and len(v) == 7 and v[0] == "#" and set(v[1:].lower()) <= _HEX


def palette() -> dict:
    """{role: "#rrggbb"}: the defaults with Sasha's values over them. A
    palette of a newer major is not read (the defaults show)."""
    roles = default_palette()
    d = _read_json(_palette_path())
    if isinstance(d, dict):
        try:
            formats.check(d, "schematix-palette")
        except formats.NewerFormat:
            return roles
        for k, v in (d.get("roles") or {}).items():
            if k in roles and is_hex(v):
                roles[k] = v.lower()
    return roles


def set_role(role, value) -> dict:
    """Set one colour role (None = back to the default). Never corrected —
    the contrast is only measured (contrast())."""
    if role not in default_palette():
        raise StoreError("unknown colour role: %s" % role, 404)
    if value is not None and not is_hex(value):
        raise StoreError("a colour is #rrggbb")
    path = _palette_path()
    old = _read_json(path)
    if isinstance(old, dict):
        formats.check(old, "schematix-palette")       # newer → NewerFormat, nothing written
    old = old if isinstance(old, dict) else {}
    roles = dict(old.get("roles") or {})
    if value is None:
        roles.pop(role, None)
    else:
        roles[role] = value.lower()
    _write_json(path, formats.keep_unknown(old, {"format": PALETTE_FORMAT, "roles": roles}))
    return palette()


# ── Things (documented devices, step 14) ──────────────────────────────────

THING_FORMAT = "zentrale-thing/1"


def _things_dir():
    return os.path.join(folder(), "things")


def _thing_path(tid):
    if not isinstance(tid, str) or not tid or "/" in tid or tid.startswith("."):
        raise StoreError("a thing id is lowercase letters, digits and -")
    return os.path.join(_things_dir(), tid + ".json")


def _thing_validator():
    import jsonschema
    with open(os.path.join(CONTRACT, "thing.schema.json"), encoding="utf-8") as f:
        return jsonschema.Draft202012Validator(json.load(f))


def check_thing(d) -> list:
    return [e.message for e in _thing_validator().iter_errors(d)]


def things() -> list:
    """Every readable thing (a newer major is skipped, one note; a broken
    file is skipped — never overwritten)."""
    out = []
    try:
        names = sorted(os.listdir(_things_dir()))
    except FileNotFoundError:
        return out
    for n in names:
        if not n.endswith(".json") or n.startswith("."):
            continue
        try:
            d = _read_json(os.path.join(_things_dir(), n))
            formats.check(d, "schematix-thing")
        except (StoreError, formats.NewerFormat):
            continue
        if isinstance(d, dict) and not check_thing(d):
            out.append(d)
    return out


def write_thing(d) -> dict:
    """Create or replace one thing (fields this version does not know stay)."""
    if not isinstance(d, dict):
        raise StoreError("a thing is an object")
    path = _thing_path(d.get("id"))
    old = _read_json(path)
    if isinstance(old, dict):
        formats.check(old, "schematix-thing")         # newer → NewerFormat, nothing written
    new = formats.keep_unknown(old, dict(d, format=THING_FORMAT))
    errors = check_thing(new)
    if errors:
        raise StoreError("thing: " + "; ".join(errors))
    _write_json(path, new)
    return new


def delete_thing(tid):
    path = _thing_path(tid)
    try:
        os.remove(path)
    except FileNotFoundError:
        raise StoreError("there is no such thing", 404)
    datasync.notify_change(path)


def _lum(hexv):
    out = []
    for i in (1, 3, 5):
        c = int(hexv[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b) -> float:
    """WCAG 2.x contrast ratio of two colours (1 … 21)."""
    la, lb = _lum(a), _lum(b)
    return round((max(la, lb) + 0.05) / (min(la, lb) + 0.05), 2)


def role_kind(role) -> str:
    """What a colour role is, by its name (the contract says so):
    `surface-*` the ground of a plane, `texture-*` the quiet pattern on it,
    everything else light/text."""
    if role.startswith("surface-"):
        return "surface"
    if role.startswith("texture-"):
        return "texture"
    return "text"


def against(role, roles) -> str:
    """The role a role is measured against: text on the board, the faintest
    text (`dim`) on a surface, a texture against its own surface."""
    kind = role_kind(role)
    if kind == "surface":
        return "dim"
    if kind == "texture":
        s = "surface-" + role[len("texture-"):]
        return s if s in roles else "board"
    return "board"


def measured(roles=None) -> dict:
    """{role: contrast} — what the colour panel shows; each role against
    what it is seen on (against()). Text roles and surfaces have the 4.5:1
    floor (floored()); textures are decoration and only measured."""
    roles = roles or palette()
    return {k: contrast(v, roles[against(k, roles)]) for k, v in roles.items()
            if k != "board" and against(k, roles) in roles}


def floored(role) -> bool:
    """Does Sasha's e-ink floor (4.5:1) apply to this role?"""
    return role_kind(role) != "texture"
