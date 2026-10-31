# tui/bausteine/pixel_icons.py
#
# Small pixel-art icons drawn with quadrant blocks — a general building
# block (2026-10-31; first user: Schematix, memory/hub/schematix_style.md:
# „laptop einfach nen kleiner gemalter laptop im pixelart, strom als blitz,
# powerbank als portable blitz …").
#
# The icons are DATA, not code branches: one bitmap per kind in
# device_icons.txt, drawn in pixels ('#' on, '.' off), two pixels wide and
# two high per terminal cell (▘▝▖▗▀▄▌▐▚▞▛▜▙▟█ — Unicode 3.2, VTE draws them
# itself, no font needed). A new kind plugs in with one more block in that
# file; nothing else changes. Another icon file can be read with
# `parse(text)` + `to_cells(rows)`.
#
# Quadrant glyphs need no colour: an icon reads on e-ink and in an 8-colour
# terminal just as well. `hatched=True` draws the same icon with its inside
# as a checkerboard (the outline stays whole) — for what is not there yet.
#
# PURE: no curses.

import functools
import os

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_icons.txt")
MAX_W, MAX_H = 16, 8                    # pixels: at most 8×4 cells


_QUAD = {(0, 0, 0, 0): " ", (1, 0, 0, 0): "▘", (0, 1, 0, 0): "▝", (0, 0, 1, 0): "▖",
         (0, 0, 0, 1): "▗", (1, 1, 0, 0): "▀", (0, 0, 1, 1): "▄", (1, 0, 1, 0): "▌",
         (0, 1, 0, 1): "▐", (1, 0, 0, 1): "▚", (0, 1, 1, 0): "▞", (1, 1, 1, 0): "▛",
         (1, 1, 0, 1): "▜", (1, 0, 1, 1): "▙", (0, 1, 1, 1): "▟", (1, 1, 1, 1): "█"}


def _is_pixels(line):
    return set(line) <= set("#.")


def parse(text):
    """An icon file → {kind: [pixel rows]}: a name line, pixel rows, an empty
    line; lines starting with '#' that are not pixel rows are comments. PURE."""
    out, kind = {}, None
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            kind = None
        elif kind is None and not line.startswith("#"):
            kind = line
            out[kind] = []
        elif kind is not None and _is_pixels(line):
            out[kind].append(line[:MAX_W])
    return {k: v[:MAX_H] for k, v in out.items() if v}


@functools.lru_cache(maxsize=1)
def bitmaps():
    with open(FILE, encoding="utf-8") as f:
        return parse(f.read())


def to_cells(rows, hatched=False):
    """Pixel rows → cell rows of quadrant glyphs. PURE."""
    h = len(rows) + len(rows) % 2
    w = max((len(r) for r in rows), default=0)
    w += w % 2
    px = [r.ljust(w, ".") for r in rows] + ["." * w] * (h - len(rows))

    def lit(x, y):
        return 0 <= y < h and 0 <= x < w and px[y][x] == "#"

    def on(x, y):
        if not lit(x, y) or not hatched or (x + y) % 2 == 0:
            return lit(x, y)
        # hatched: the inside goes to a checkerboard, the outline stays whole
        return not all(lit(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    out = []
    for y in range(0, h, 2):
        out.append("".join(_QUAD[tuple(int(on(x + dx, y + dy)) for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1)))]
                           for x in range(0, w, 2)))
    return out


@functools.lru_cache(maxsize=128)
def _cells(kind, hatched):
    rows = bitmaps().get(kind)
    return tuple(to_cells(rows, hatched)) if rows else ()


def cells(kind, hatched=False):
    """The icon of `kind` as cell rows, or [] when there is none."""
    return list(_cells(kind, bool(hatched)))


def kinds():
    return list(bitmaps())
