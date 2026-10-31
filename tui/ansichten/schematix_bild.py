# tui/ansichten/schematix_bild.py
#
# Drawing Schematix (memory/hub/schematix_style.md): hacker × wizard, an
# "ethereal machine" — thin traces of light over planes of near-black.
#
# Depth by surfaces: the board is the far plane (`board`, calm, nothing on
# it but the quiet data column); every band of the cross-section (cloud,
# software, nodes, things) is a plane of its own with its own ground
# (`surface-<band>`) and its own texture (`texture-<band>`: star dust, a
# fine grid, hatching, noise). The textures move slower the further back the
# plane is (parallax while the view moves). A step of half blocks ▄ joins
# two planes. Pieces sit in front on a plate (`surface-piece`) — the
# texture stops there, so a piece reads as a sigil set into the ground; the
# wires run over the planes as traces of light.
#
# Colours are Sasha's colour roles (GET /api/schematix/palette), measured
# and never corrected. Without 256 colours the theme roles stand in; the
# glyphs (textures, frames, dashed/dotted traces, icons) still carry every
# plane and every state.

import curses

from .translate import _

# canvas role → palette role
ROLLE = {"raster": "dim", "schnur": "trace", "schnur_vor": "focus", "rahmen": "dim",
         "fokus": "focus", "griff": "solder", "groesse": "solder", "ziel": "focus",
         "text": "ink", "leise": "dim", "titel": "bright", "abgelehnt": "error"}
# palette role → theme role when there are no 256 colours
THEMA = {"ink": "ink", "dim": "dim", "bright": "bright", "focus": "acc", "error": "warn",
         "solder": "acc", "planned": "dim", "cloud": "bright", "glyph": "acc"}
FETT = {"titel", "fokus", "griff", "ziel", "abgelehnt"}

# The planes of the cross-section, back to front: (band, label, parallax).
PLANES = (("cloud", "cloud", 0.25), ("software", "software", 0.5),
          ("nodes", "nodes", 0.75), ("things", "things", 1.0))
CHIPS = (("data", "sync"), ("services", "services"), ("hardware", "hardware"),
         ("network", "network"), ("power", "power"))
ON, OFF = "━", "┄"                      # a layer on / off: the same signs as a live / off wire
SIDE_W = 32
DUST = "·∙˙·"                           # stipple of the ground plane (DejaVu has these)
SAMPLE = {"cloud": "˙ · ", "software": "· · ", "nodes": "╱  ╱", "things": "∙·˙∙"}


def _hash(x, y):
    h = (x * 374761393 + y * 668265263) & 0xffffffff
    h = (h ^ (h >> 13)) * 1274126177 & 0xffffffff
    return h ^ (h >> 16)


def _tex_cloud(x, y):                   # star dust: sparse, calm
    h = _hash(x, y) % 61
    return "·" if h == 0 else "˙" if h == 1 else " "


def _tex_software(x, y):                # a fine grid of points
    return "·" if x % 4 == 0 and y % 2 == 0 else " "


def _tex_nodes(x, y):                   # hatching
    return "╱" if (x + y) % 6 == 0 else " "


def _tex_things(x, y):                  # noise, denser: the ground
    h = _hash(x, y)
    return DUST[h % len(DUST)] if h % 4 == 0 else " "


TEXTURES = {"cloud": _tex_cloud, "software": _tex_software, "nodes": _tex_nodes, "things": _tex_things}


def texture_row(band, wx0, wy, width):
    """One row of a plane's texture from world column wx0. PURE."""
    f = TEXTURES.get(band)
    return "".join(f(wx0 + i, wy) for i in range(width)) if f else " " * width


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _roles(app):
    return ((app.S.get("palette") or {}).get("roles") or {})


def _attr(app, role, fg, bg, bold):
    """(palette role, fg hex, bg hex) → curses attribute (the one place that
    talks to curses colours; capture tests replace it)."""
    z = app.z
    C = z.C
    if fg and bg and C.get("pix_bg"):
        attr = z.pix_attr(_rgb(fg), _rgb(bg))
    elif role.startswith(("surface-", "texture-")):
        attr = C.get("faint", C.get("dim", 0))
    else:
        attr = C.get(THEMA.get(role, "ink"), C.get("ink", 0))
    return attr | (curses.A_BOLD if bold else 0)


def farbe(app, rolle, grund="board"):
    """Canvas or palette role on a surface role → curses attribute."""
    roles = _roles(app)
    r = ROLLE.get(rolle, rolle)
    fg = roles.get(r) or roles.get("ink")
    bg = roles.get(grund) or roles.get("board")
    return _attr(app, r, fg, bg, rolle in FETT)


def _fill(app, y, x, w, grund="board"):
    app.z.safe_addstr(y, x, " " * max(0, w), farbe(app, "ink", grund))


def _strip(app, y, x, w):
    """Top line: the layers (━ on, ┄ off) and what the scheme holds."""
    S, z = app.S, app.z
    m = S["map"] or {}
    col = x
    for i, (layer, name) in enumerate(CHIPS):
        on = S["layers"].get(layer, True)
        text = "%s%d %s  " % (ON if on else OFF, i + 1, _(name))
        z.addclip(y, col, text, max(0, x + w - col), farbe(app, "layer-" + layer if on else "dim"))
        col += len(text)
    wires = m.get("wires") or []
    live = sum(1 for wi in wires if wi.get("state") == "live")
    planned = sum(1 for p in m.get("pieces") or [] if p.get("state") == "planned") + \
        sum(1 for wi in wires if wi.get("state") == "planned")
    docs = sum(1 for p in m.get("pieces") or [] if p.get("state") == "documented")
    errs = len(S.get("fehler") or {})
    right = _("live {a:02d}/{b:02d} · ◇ {p} · ▣ {d} · ✕ {e}").format(
        a=live, b=len(wires), p=planned, d=docs, e=errs)
    if col + len(right) + 2 <= x + w:
        z.addclip(y, x + w - len(right), right, len(right), farbe(app, "dim"))


def plane_of(m, wy):
    """Which band (plane) a world row belongs to: from 2 rows above its top."""
    current = None
    for b in sorted(m.get("bands") or [], key=lambda b: b["y"]):
        if wy >= b["y"] - 2:
            current = b["id"]
    return current or PLANES[0][0]


def _plane_tops(m):
    return {b["y"] - 2: b["id"] for b in m.get("bands") or []}


def _split(chunk_x, text, spans):
    """Cut a run of text at the edges of the plates on its row → pieces
    (x, text, on_plate). PURE."""
    out, x, buf, inside = [], chunk_x, "", None
    for i, ch in enumerate(text):
        cx = chunk_x + i
        on = any(a <= cx < b for a, b in spans)
        if on != inside and buf:
            out.append((x, buf, inside))
            x, buf = cx, ""
        inside = on
        buf += ch
    if buf:
        out.append((x, buf, inside))
    return out


def _board(app, y0, x0, bh, bw):
    S, z = app.S, app.z
    c = S["canvas"]
    m = S["map"] or {}
    c.vw, c.vh = max(1, bw), max(1, bh)
    c.ursprung = (y0, x0)                # for the mouse (tui/bausteine/sgr_mouse.py)
    if S.get("zentrieren"):
        _zentrieren(c)
        c.springen()
        S["zentrieren"] = False
    c.gleiten()
    ax, ay = c.anzeige_lage()
    tops = _plane_tops(m)
    parallax = {band: f for band, _l, f in PLANES}
    labels = {band: label for band, label, _f in PLANES}
    counts = {}
    for p in m.get("pieces") or []:
        counts[p.get("band")] = counts.get(p.get("band"), 0) + 1
    planes = []
    for j in range(bh):
        wy = ay + j
        band = plane_of(m, wy)
        planes.append(band)
        surface = "surface-" + band
        before = plane_of(m, wy - 1)
        if wy in tops and before != band:            # a step of half blocks joins two planes
            z.safe_addstr(y0 + j, x0, "▄" * bw, _step(app, surface, "surface-" + before))
            continue
        wx0 = int(ax * parallax.get(band, 1.0))
        z.safe_addstr(y0 + j, x0, texture_row(band, wx0, wy, bw), farbe(app, "texture-" + band, surface))
        if wy - 1 in tops and tops[wy - 1] == band:  # the plane's name, quiet, like a comment
            label = "// %s · %02d" % (_(labels.get(band, band)), counts.get(band, 0))
            z.addclip(y0 + j, x0 + 1, label, bw - 2, farbe(app, "dim", surface))
    # the plates under the pieces (where they are drawn now)
    spans = {}
    for e in c.elemente:
        for wy in range(e["y"], e["y"] + max(3, e["h"])):
            spans.setdefault(wy - ay, []).append((e["x"] - ax, e["x"] - ax + max(3, e["w"])))
    for j, stuecke in enumerate(c.bild(bh, bw)):
        surface = "surface-" + planes[j]
        row = spans.get(j, [])
        for sx, text, rolle in stuecke:
            if rolle == "raster":                    # the planes carry the orientation
                continue
            for px, part, on in _split(sx, text, row):
                z.safe_addstr(y0 + j, x0 + px, part, farbe(app, rolle, "surface-piece" if on else surface))


def _step(app, lower, upper):
    """The half-block step between two planes: ▄ in the lower plane's ground
    on the upper one's."""
    roles = _roles(app)
    return _attr(app, lower, roles.get(lower) or roles.get("board"),
                 roles.get(upper) or roles.get("board"), False)


def _zentrieren(c):
    """On open: the middle of all pieces in the middle of the view."""
    if not c.elemente:
        c.vx, c.vy = -(c.vw // 2), -(c.vh // 2)
        return
    x0 = min(e["x"] for e in c.elemente)
    y0 = min(e["y"] for e in c.elemente)
    x1 = max(e["x"] + e["w"] for e in c.elemente)
    c.vx = (x0 + x1) // 2 - c.vw // 2
    c.vy = y0 - 2
    if x1 - x0 > c.vw:
        c.vx = x0 - 2


def _dots(name, value, width):
    """`name ······ value` in a column of `width`. PURE."""
    value = str(value)
    gap = max(1, width - len(name) - len(value) - 2)
    return "%s %s %s" % (name, "·" * gap, value)


def _side(app, y0, x0, h, w):
    """The data column at the margin: quiet, like terminal output."""
    S, z = app.S, app.z
    m = S["map"] or {}
    pieces = m.get("pieces") or []
    out = [("// " + _("bands"), "dim")]
    counts = {}
    for p in pieces:
        counts[p.get("band")] = counts.get(p.get("band"), 0) + 1
    for band, label, _f in PLANES:
        out.append((_dots(_(label), "%02d" % counts.get(band, 0), w), "ink"))
    out.append(("", "dim"))
    out.append(("// " + _("layers"), "dim"))
    wires = list(({w["id"]: w for w in m.get("wires") or []} | {k: dict(v) for k, v in S["pending"].items()}).values())
    for i, (layer, name) in enumerate(CHIPS):
        n = sum(1 for wi in wires if wi.get("layer") == layer)
        on = S["layers"].get(layer, True)
        out.append((_dots("%d %s" % (i + 1, _(name)), "%02d %s" % (n, ON if on else OFF), w),
                    "layer-" + layer if on else "dim"))
    p = app.fokus_piece()
    if p:
        out.append(("", "dim"))
        out.append(("// " + _("focus"), "dim"))
        out += focus_lines(p, wires)
    out.append(("", "dim"))
    out.append(("// " + _("traces"), "dim"))
    for wi in sorted(wires, key=lambda x: x["id"]):
        sign = {"live": "━", "off": "┄", "planned": "╌"}.get(wi.get("state"), "·")
        out.append(("%s %s" % (sign, wi["id"]), "ink" if wi.get("state") == "live" else "dim"))
    for j, (text, role) in enumerate(out[:h]):
        z.addclip(y0 + j, x0, text, w, farbe(app, role))


def focus_lines(p, wires):
    """What the side column says about the focused piece: id, sockets and
    what is plugged into them."""
    out = [("› " + str(p.get("id")), "bright")]
    if p.get("node"):
        out.append((_("  on {node}").format(node=p["node"]), "dim"))
    mine = [w for w in wires if p["id"] in (w.get("from_piece"), w.get("to_piece"))]
    for need in p.get("needs") or []:
        n = [w for w in mine if w.get("to_piece") == p["id"] and w.get("to_port") == need.get("id")]
        state = ", ".join(sorted({w.get("state") for w in n})) or "—"
        out.append(("◂ %s %s" % (need.get("type"), state), "dim" if not n else "ink"))
    for offer in p.get("offers") or []:
        n = [w for w in mine if w.get("from_piece") == p["id"] and w.get("from_port") == offer.get("id")]
        out.append(("▸ %s ×%d" % (offer.get("type"), len(n)), "dim" if not n else "ink"))
    return out


def _status(app, y, x, w):
    S, z = app.S, app.z
    m = S["map"] or {}
    msg = app.status_text()
    if msg:
        z.addclip(y, x, msg, w, farbe(app, "abgelehnt"))
        return
    notes = m.get("notes") or []
    nodes = sum(1 for p in m.get("pieces") or [] if p.get("kind") == "node")
    text = notes[0] if notes else _("› scheme {s} · {n} nodes · {p} pieces · {w} wires").format(
        s=S.get("scheme"), n=nodes, p=len(m.get("pieces") or []), w=len(m.get("wires") or []))
    z.addclip(y, x, text, w, farbe(app, "dim"))


def _frame(app, y0, x0, h, w, title):
    """A thin panel on the plate surface: ╭─ title ─╮ in the dim role."""
    z = app.z
    line = farbe(app, "dim", "surface-piece")
    for j in range(h):
        _fill(app, y0 + j, x0, w, "surface-piece")
    z.safe_addstr(y0, x0, "╭" + "─" * (w - 2) + "╮", line)
    for j in range(1, h - 1):
        z.safe_addstr(y0 + j, x0, "│", line)
        z.safe_addstr(y0 + j, x0 + w - 1, "│", line)
    z.safe_addstr(y0 + h - 1, x0, "╰" + "─" * (w - 2) + "╯", line)
    if title:
        z.addclip(y0, x0 + 2, " " + title + " ", w - 4, farbe(app, "focus", "surface-piece"))


def _against(role, roles, pal):
    a = (pal.get("against") or {}).get(role)
    if a:
        return a
    if role.startswith("surface-"):
        return "dim"
    if role.startswith("texture-"):
        s = "surface-" + role[len("texture-"):]
        return s if s in roles else "board"
    return "board"


def colour_rows(pal):
    """The lines of the colour panel: (role, hex, contrast, against, floored). PURE."""
    roles = pal.get("roles") or {}
    measured = pal.get("measured") or {}
    floored = pal.get("floored")
    out = []
    for role, hexv in roles.items():
        a = _against(role, roles, pal)
        f = (role in floored) if floored is not None else not role.startswith("texture-")
        out.append((role, hexv, measured.get(role), a if role != "board" else None, f))
    return out


def _colours(app, top, mx, h, w):
    S, z = app.S, app.z
    pal = S.get("palette") or {}
    rows = colour_rows(pal)
    floor = pal.get("minimum") or 4.5
    mw, mh = min(86, w - 4), min(len(rows) + 4, h - 2)
    y0, x0 = top + (h - mh) // 2, mx + (w - mw) // 2
    _frame(app, y0, x0, mh, mw, _("colour roles · contrast measured, never corrected"))
    room = mh - 3
    sel = S["colour_sel"] % max(1, len(rows))
    first = max(0, min(sel - room + 1, len(rows) - room)) if sel >= room else 0
    for i, (role, hexv, c, against, floored) in enumerate(rows[first:first + room]):
        on = first + i == sel
        y = y0 + 1 + i
        line = "%s %-17s %s " % ("›" if on else " ", role, hexv)
        z.addclip(y, x0 + 2, line, mw - 4, farbe(app, "focus" if on else "ink", "surface-piece"))
        sx = x0 + 2 + len(line)
        if role.startswith("texture-"):                             # a texture: on its plane
            sample = SAMPLE.get(role[len("texture-"):], "····")
            z.safe_addstr(y, sx, sample, farbe(app, role, against))
        elif role.startswith("surface-"):                           # a ground: its text on it
            z.safe_addstr(y, sx, " Aa ", farbe(app, "dim", role))
        else:
            z.safe_addstr(y, sx, "▐██▌", farbe(app, role, "surface-piece"))
        if c is not None:
            low = floored and c < floor
            what = {"board": _("on board"), "dim": _("dim on it")}.get(against) or \
                _("on {s}").format(s=against)
            tail = "%.1f:1 %s%s" % (c, what, ("  < %.1f" % floor) if low else "" if floored else
                                    " · " + _("texture, no floor"))
            z.addclip(y, sx + 5, tail, x0 + mw - 2 - (sx + 5),
                      farbe(app, "abgelehnt" if low else "dim", "surface-piece"))
    if S["farbe"] is not None:
        f = S["farbe"]
        fh, fw = f.groesse(h, w) if hasattr(f, "groesse") else (22, 70)
        fy, fx, fh, fw = f.mittig(h, w, min(fh, h), min(fw, w))
        f.zeichne(z, top + fy, mx + fx, fh, fw)


GROUPS = {"installed": "app", "provider": "provider", "node": "node", "store": "store", "device": "thing"}


def _picker(app, top, mx, h, w):
    """The `+` picker: everything placeable, by group (GET /api/pieces)."""
    S = app.S
    pk = S["picker"]
    rows = [("%-8s %s" % (GROUPS.get(e.get("group"), e.get("group")), e.get("title") or e.get("id")), "ink")
            for e in pk["pieces"]] or [(_("nothing to place"), "dim")]
    _panel(app, top, mx, h, w, _("add a piece · planned until it is real"), rows,
           pk["sel"] % max(1, len(rows)) if pk["pieces"] else None, 50)


def _panel(app, top, mx, h, w, title, rows, sel=None, width=64):
    """A thin panel in the middle of the board: rows of (text, role)."""
    z = app.z
    mw, mh = min(width, w - 4), min(len(rows) + 3, h - 2)
    y0, x0 = top + (h - mh) // 2, mx + (w - mw) // 2
    _frame(app, y0, x0, mh, mw, title)
    room = mh - 3
    first = 0 if sel is None or sel < room else min(sel - room + 1, len(rows) - room)
    for j, (text, role) in enumerate(rows[first:first + room]):
        on = sel is not None and first + j == sel
        z.addclip(y0 + 1 + j, x0 + 2, ("› " if on else "  ") + text, mw - 4,
                  farbe(app, "focus" if on else role, "surface-piece"))


STATE_SIGN = {"live": "━", "off": "┄", "planned": "╌", "broken": "✕"}


def _plugs(app, top, mx, h, w):
    """p: the wires of the focused piece — x unplugs / plugs one (Run applies)."""
    pl = app.S["plugs"]
    rows = []
    for wi in pl["wires"]:
        sign = STATE_SIGN.get(wi.get("state"), "·")
        tail = "  ↻ " + _("not run yet") if wi.get("pending") else ""
        rows.append(("%s %-15s %-30s %s%s" % (sign, wi.get("type"), wi["id"], wi.get("state"), tail),
                     "ink" if wi.get("state") == "live" else "dim"))
    _panel(app, top, mx, h, w, _("plugs of {p}").format(p=pl.get("piece")),
           rows or [(_("nothing is plugged into this piece"), "dim")], pl["sel"] if rows else None, 76)


def _run(app, top, mx, h, w):
    """r: what Run would do — the diff (enter switches) or the errors."""
    r = app.S["run"]
    if r.get("ok"):
        rows = [("✓ " + _("the scheme compiles"), "glyph")]
        rows += [(line, "ink") for line in r.get("diff") or []] or [(_("nothing to switch"), "dim")]
        if r.get("diff"):
            rows.append(("", "dim"))
            rows.append((_("enter switches · esc goes back"), "dim"))
    else:
        rows = [("✕ " + _("refused — nothing switched"), "abgelehnt")]
        rows += [("✕ " + (e.get("text") or e.get("code") or "?"), "abgelehnt") for e in r.get("errors") or []]
    _panel(app, top, mx, h, w, _("run · check → diff → switch"), rows, None, 90)


def zeichnen(app, top, mx, h, w):
    S, z = app.S, app.z
    x0, iw = mx + 1, w - 2
    for j in range(1, h - 1):                    # the far plane: everything starts on the board
        _fill(app, top + j, x0, iw)
    if S["map"] is None or S["canvas"] is None:
        z.addclip(top + 2, mx + 3, S["msg"] or _("laying the map …"), w - 6,
                  farbe(app, "abgelehnt" if S["msg"] else "dim"))
        return
    _strip(app, top + 1, x0 + 1, iw - 2)
    side = SIDE_W if iw >= 100 else 0
    bh = max(1, h - 5)
    bw = iw - (side + 1 if side else 0)
    _board(app, top + 3, x0, bh, bw)
    if side:
        _side(app, top + 3, x0 + bw + 2, bh, side - 2)
    _status(app, top + h - 2, x0 + 1, iw - 2)
    if S["picker"] is not None:
        _picker(app, top, mx, h, w)
    if S["plugs"] is not None:
        _plugs(app, top, mx, h, w)
    if S["run"] is not None:
        _run(app, top, mx, h, w)
    if S["ebene"] == "colours":
        _colours(app, top, mx, h, w)
