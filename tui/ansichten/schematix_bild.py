# tui/ansichten/schematix_bild.py
#
# Drawing Schematix (memory/hub/schematix_style.md): a dark, densely packed
# retro-occult terminal — framed panels packed edge to edge, a strip of
# layer chips with a gauge on top, the board (the Desk's canvas) with a band
# gutter, a cross-section column on the right, a status line in caps.
# Colours are Sasha's colour roles (GET /api/schematix/palette); without 256
# colours the theme roles stand in and the glyphs carry every state.

import curses

from .translate import _

# canvas role → palette role
ROLLE = {"raster": "dim", "schnur": "trace", "schnur_vor": "focus", "rahmen": "dim",
         "fokus": "focus", "griff": "solder", "groesse": "solder", "ziel": "focus",
         "text": "ink", "leise": "dim", "titel": "bright", "abgelehnt": "error"}
# palette role → theme role when there are no 256 colours
THEMA = {"ink": "ink", "dim": "dim", "bright": "bright", "focus": "acc", "error": "warn",
         "solder": "acc", "planned": "dim", "cloud": "bright"}
FETT = {"titel", "fokus", "griff", "ziel", "abgelehnt", "cloud"}
BANDS = (("cloud", "CLOUD", "cloud", "▓"), ("software", "SOFTWARE", "layer-data", "▒"),
         ("nodes", "NODES", "bright", "▓"), ("things", "THINGS", "layer-hardware", "░"))
CHIPS = (("data", "SYNC"), ("services", "SVC"), ("hardware", "HW"), ("network", "NET"), ("power", "PWR"))
SIDE_W = 30


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def farbe(app, rolle):
    """Canvas or palette role → curses attribute."""
    z = app.z
    C = z.C
    roles = ((app.S.get("palette") or {}).get("roles") or {})
    r = ROLLE.get(rolle, rolle)
    attr = 0
    if roles and C.get("pix_bg") and r in roles:
        attr = z.pix_attr(_rgb(roles[r]), _rgb(roles.get("board", "#000000")))
    elif roles and C.get("pix_bg"):
        attr = z.pix_attr(_rgb(roles.get("ink", "#a9c49a")), _rgb(roles.get("board", "#000000")))
    else:
        attr = C.get(THEMA.get(r, "ink"), C.get("ink", 0))
    if rolle in FETT:
        attr |= curses.A_BOLD
    return attr


def _fill(app, y, x, w):
    app.z.safe_addstr(y, x, " " * max(0, w), farbe(app, "ink"))


def _gauge(n, total, width=10):
    full = 0 if not total else round(width * n / total)
    return "▕" + "█" * full + "░" * (width - full) + "▏"


def _strip(app, y, x, w):
    S, z = app.S, app.z
    m = S["map"] or {}
    col = x
    for i, (layer, name) in enumerate(CHIPS):
        on = S["layers"].get(layer, True)
        text = ("▐%d▌%s " if on else "·%d·%s ") % (i + 1, name if on else name.lower())
        z.addclip(y, col, text, max(0, x + w - col), farbe(app, "layer-" + layer if on else "dim"))
        col += len(text)
    wires = m.get("wires") or []
    live = sum(1 for wi in wires if wi.get("state") == "live")
    planned = sum(1 for p in m.get("pieces") or [] if p.get("state") == "planned") + \
        sum(1 for wi in wires if wi.get("state") == "planned")
    docs = sum(1 for p in m.get("pieces") or [] if p.get("state") == "documented")
    errs = sum(1 for p in m.get("pieces") or [] if p.get("fehler"))
    right = "%s %s %d/%d  ◇%d ▣%d ✕%d" % (_("LIVE"), _gauge(live, len(wires)), live, len(wires),
                                          planned, docs, errs)
    if col + len(right) + 2 <= x + w:
        z.addclip(y, x + w - len(right), right, len(right), farbe(app, "solder"))


def _band_of(m, wy):
    bands = sorted(m.get("bands") or [], key=lambda b: b["y"])
    current = None
    for b in bands:
        if wy >= b["y"] - 2:
            current = b["id"]
    return current


def _board(app, y0, x0, bh, bw):
    S, z = app.S, app.z
    c = S["canvas"]
    m = S["map"] or {}
    c.vw, c.vh = max(1, bw - 2), max(1, bh)
    if S.get("zentrieren"):
        _zentrieren(c)
        c.springen()
        S["zentrieren"] = False
    c.gleiten()
    ax, ay = c.anzeige_lage()
    style = {b: (glyph, role) for b, _n, role, glyph in BANDS}
    for j in range(bh):
        band = _band_of(m, ay + j)
        glyph, role = style.get(band, (" ", "dim"))
        z.safe_addstr(y0 + j, x0, glyph * 2, farbe(app, role))
        _fill(app, y0 + j, x0 + 2, bw - 2)
    for j, stuecke in enumerate(c.bild(bh, bw - 2)):
        for sx, text, rolle in stuecke:
            if rolle == "raster":
                text = text.replace("·", "∙")
            z.safe_addstr(y0 + j, x0 + 2 + sx, text, farbe(app, rolle))


def _zentrieren(c):
    """On open: the middle of all pieces in the middle of the view."""
    if not c.elemente:
        c.vx, c.vy = -(c.vw // 2), -(c.vh // 2)
        return
    x0 = min(e["x"] for e in c.elemente)
    y0 = min(e["y"] for e in c.elemente)
    x1 = max(e["x"] + e["w"] for e in c.elemente)
    c.vx = (x0 + x1) // 2 - c.vw // 2
    c.vy = y0 - 1
    if x1 - x0 > c.vw:
        c.vx = x0 - 1


def _side(app, y0, x0, h, w):
    S, z = app.S, app.z
    m = S["map"] or {}
    pieces = m.get("pieces") or []
    z.addclip(y0, x0, _("CROSS-SECTION"), w, farbe(app, "bright"))
    y = y0 + 1
    counts = {}
    for p in pieces:
        counts[p.get("band")] = counts.get(p.get("band"), 0) + 1
    for band, name, role, glyph in BANDS:
        z.addclip(y, x0, "%s %-9s %3d" % (glyph * 2, name, counts.get(band, 0)), w, farbe(app, role))
        y += 1
    y += 1
    z.addclip(y, x0, _("LAYERS"), w, farbe(app, "bright"))
    y += 1
    wires = m.get("wires") or []
    for i, (layer, name) in enumerate(CHIPS):
        n = sum(1 for wi in wires if wi.get("layer") == layer)
        on = S["layers"].get(layer, True)
        z.addclip(y, x0, "%d %-5s %3d %s" % (i + 1, name, n, "■" if on else "□"), w,
                  farbe(app, "layer-" + layer if on else "dim"))
        y += 1
    y += 1
    p = app.fokus_piece()
    if p and y < y0 + h - 2:
        z.addclip(y, x0, _("FOCUS"), w, farbe(app, "bright"))
        y += 1
        for text, role in focus_lines(p, wires):
            if y >= y0 + h:
                break
            z.addclip(y, x0, text, w, farbe(app, role))
            y += 1


def focus_lines(p, wires):
    """What the side column says about the focused piece: id, sockets and
    what is plugged into them."""
    out = [(str(p.get("id")), "ink")]
    if p.get("node"):
        out.append((_("on {node}").format(node=p["node"]), "dim"))
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
    if S["msg"]:
        z.addclip(y, x, S["msg"], w, farbe(app, "abgelehnt"))
        return
    notes = m.get("notes") or []
    nodes = sum(1 for p in m.get("pieces") or [] if p.get("kind") == "node")
    text = notes[0] if notes else _("SCHEME: ACCOUNT · {n} NODES · {p} PIECES · {w} WIRES").format(
        n=nodes, p=len(m.get("pieces") or []), w=len(m.get("wires") or []))
    z.addclip(y, x, text, w, farbe(app, "dim"))


def _colours(app, top, mx, h, w):
    S, z = app.S, app.z
    pal = S.get("palette") or {}
    roles = list((pal.get("roles") or {}).items())
    measured = pal.get("measured") or {}
    floor = pal.get("minimum") or 4.5
    mw, mh = min(56, w - 4), min(len(roles) + 4, h - 2)
    y0, x0 = top + (h - mh) // 2, mx + (w - mw) // 2
    for j in range(mh):
        _fill(app, y0 + j, x0, mw)
    z.draw_box(y0, x0, mh, mw, _("colour roles · contrast on the board"), farbe(app, "focus"))
    for i, (role, hexv) in enumerate(roles[:mh - 3]):
        sel = i == S["colour_sel"] % max(1, len(roles))
        c = measured.get(role)
        low = c is not None and c < floor
        line = "%s %-16s %s  " % ("›" if sel else " ", role, hexv)
        z.addclip(y0 + 1 + i, x0 + 2, line, mw - 4, farbe(app, "focus" if sel else "ink"))
        z.safe_addstr(y0 + 1 + i, x0 + 2 + len(line), "███", farbe(app, role))
        if c is not None:
            z.addclip(y0 + 1 + i, x0 + 6 + len(line), "%.1f:1%s" % (c, "  < 4.5" if low else ""),
                      mw - 8 - len(line), farbe(app, "abgelehnt" if low else "dim"))
    if S["farbe"] is not None:
        f = S["farbe"]
        fh, fw = f.groesse(h, w) if hasattr(f, "groesse") else (22, 70)
        fy, fx, fh, fw = f.mittig(h, w, min(fh, h), min(fw, w))
        f.zeichne(z, top + fy, mx + fx, fh, fw)


def zeichnen(app, top, mx, h, w):
    S, z = app.S, app.z
    if S["map"] is None or S["canvas"] is None:
        z.addclip(top + 2, mx + 3, S["msg"] or _("laying the map …"), w - 6,
                  farbe(app, "abgelehnt" if S["msg"] else "dim"))
        return
    x0, iw = mx + 1, w - 2
    _strip(app, top + 1, x0 + 1, iw - 2)
    z.addclip(top + 2, x0, ("░▒" * iw)[:iw], iw, farbe(app, "dim"))
    side = SIDE_W if iw >= 100 else 0
    bh = max(1, h - 5)
    bw = iw - (side + 1 if side else 0)
    _board(app, top + 3, x0, bh, bw)
    if side:
        for j in range(bh):
            z.safe_addstr(top + 3 + j, x0 + bw, "│", farbe(app, "dim"))
        _side(app, top + 3, x0 + bw + 2, bh, side - 2)
    _status(app, top + h - 2, x0 + 1, iw - 2)
    if S["ebene"] == "colours":
        _colours(app, top, mx, h, w)
