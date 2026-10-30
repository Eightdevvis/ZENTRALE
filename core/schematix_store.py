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


def measured(roles=None) -> dict:
    """{role: contrast against the board} — what the colour panel shows."""
    roles = roles or palette()
    return {k: contrast(v, roles["board"]) for k, v in roles.items() if k != "board"}
