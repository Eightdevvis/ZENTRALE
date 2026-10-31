"""Colour captures of Schematix for Sasha (tests/test_schematix_tui.py with
SCHEMATIX_CAPTURE=<folder>): the screen the test drew, with the real colour
roles, as a PNG next to the text capture. Only for looking — nothing is
asserted on it, and without Pillow or the DejaVu font it is skipped.

Block elements (▀▄▌▐▘▝▖▗▚▞▛▜▙▟█) are painted as rectangles, the way VTE
draws them itself; everything else comes from DejaVu Sans Mono."""
import os

FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "/usr/share/fonts/TTF/DejaVuSansMono.ttf")
CW, CH, SIZE = 9, 18, 15
QUAD = {"▘": (1, 0, 0, 0), "▝": (0, 1, 0, 0), "▖": (0, 0, 1, 0), "▗": (0, 0, 0, 1), "▀": (1, 1, 0, 0),
        "▄": (0, 0, 1, 1), "▌": (1, 0, 1, 0), "▐": (0, 1, 0, 1), "▚": (1, 0, 0, 1), "▞": (0, 1, 1, 0),
        "▛": (1, 1, 1, 0), "▜": (1, 1, 0, 1), "▙": (1, 0, 1, 1), "▟": (0, 1, 1, 1), "█": (1, 1, 1, 1)}
CHROME = ("#8a8f98", "#000000", False)       # the TUI around Schematix (theme colours unknown here)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def available():
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return any(os.path.exists(f) for f in FONTS)


def write(cells, colours, path):
    """cells: rows of (char, attr); colours: attr → (fg, bg, bold) for the
    attributes the capture handed out (others are the TUI chrome)."""
    from PIL import Image, ImageDraw, ImageFont
    font = next(f for f in FONTS if os.path.exists(f))
    bold = font.replace("SansMono.ttf", "SansMono-Bold.ttf")
    f = ImageFont.truetype(font, SIZE)
    fb = ImageFont.truetype(bold, SIZE) if os.path.exists(bold) else f
    rows, cols = len(cells), max(len(r) for r in cells)
    img = Image.new("RGB", (cols * CW, rows * CH), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y, row in enumerate(cells):
        for x, (ch, attr) in enumerate(row):
            fg, bg, b = colours.get(attr, CHROME)
            x0, y0 = x * CW, y * CH
            d.rectangle([x0, y0, x0 + CW - 1, y0 + CH - 1], fill=_rgb(bg))
            if ch == " ":
                continue
            if ch in QUAD:
                hw, hh = CW // 2, CH // 2
                for i, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                    if QUAD[ch][i]:
                        d.rectangle([x0 + dx * hw, y0 + dy * hh, x0 + (CW if dx else hw) - 1,
                                     y0 + (CH if dy else hh) - 1], fill=_rgb(fg))
                continue
            d.text((x0, y0 + 1), ch, font=fb if b else f, fill=_rgb(fg))
    img.save(path)
