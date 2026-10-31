# tui/ansichten/schematix_arten.py
#
# How a piece of Schematix looks on the board (memory/hub/schematix.md,
# style: memory/hub/schematix_style.md — hacker × wizard, an "ethereal
# machine"). One canvas art `piece` for every kind — node, app, the cloud, a
# thing — because the Desk's canvas only asks the art (tui/bausteine/canvas.py:
# zeichne, rand_von, rolle_von, rand_fokus). The element carries the map piece
# as it came from GET /api/schematix/map (`piece`), plus what the view keeps
# beside it (`offen`: versions panel folded open, `fehler`: an error pinned
# to it by Run).
#
# Pieces are sigils on a plate, not boxes: hardware (nodes, things, the
# cloud) is a small pixel-art icon (tui/bausteine/pixel_icons.py) with its NAME below
# it; software is one sigil glyph and its name. The frame is only the four
# corners — the plate (its own surface colour, schematix_bild.py) carries
# the shape. The size follows the content (shape()), so the board is not a
# grid of equal boxes; the scheme keeps its own sizes untouched.
#
# Every state is a glyph too, never only a colour (e-ink, 8 colours):
#   app ╭ ╮ corners · node ╭─╮ lines above and below · cloud ┌ ┐ corners
#   · documented thing ╔ ╗ corners · planned ┊┄ dotted outline, icon hatched,
#   "◇ not yet" · an error pinned to it: "✕ …" inside · focus: a thin
#   rounded outline ╭─╮│╰╯.

import textwrap

from .translate import _

try:
    from tui.bausteine import pixel_icons
except ImportError:                     # started as a script: tui/ is on the path
    from bausteine import pixel_icons

ART = "piece"

# A node piece → which device icon (tui/bausteine/device_icons.txt), by its
# name (letters only, so pi2 and mini-pc match too; first match wins).
NODE_ICONS = (("laptop", "laptop"), ("minipc", "mini-pc"), ("mini", "mini-pc"),
              ("tower", "tower"), ("pc", "tower"), ("pi", "raspberry-pi"),
              ("phone", "phone"), ("handy", "phone"), ("tablet", "tablet"))
NODE_DEFAULT = "tower"
# A thing kind (contracts/schematix/1/kinds.json) whose icon has another name.
KIND_ICONS = {}
# A software piece → its sigil: one quiet glyph instead of a box (APL and
# geometric signs DejaVu Sans Mono has, one cell wide each). Pinned for the
# well-known apps, otherwise picked from SIGIL_SET by the name.
SIGILS = {"cloud": "☁", "fokus": "◎", "tutor": "⍥", "kalender": "☽", "mail": "⍓",
          "notizen": "⍟", "schematix": "⎈", "werkstatt": "⚒", "graphen": "⍋", "karte": "⌂",
          "klavier": "♫", "pdf": "⍰"}
SIGIL_SET = "⍟⍉⍠⍣⍥⍫⍲⊛◬◈⌘✧☉♁☍◐⍋⍒⍙⍜"


def node_icon(name):
    n = "".join(ch for ch in str(name or "").lower() if ch.isalpha())
    return next((kind for key, kind in NODE_ICONS if n.startswith(key)), NODE_DEFAULT)


def icon_of(p):
    """Which icon a map piece gets: nodes by name, things by kind, the cloud
    its cloud; apps none (they get a sigil)."""
    if p.get("band") == "cloud":
        return "cloud"
    if p.get("kind") == "node":
        return node_icon(p.get("node") or str(p.get("id", "")).split(":", 1)[-1])
    if p.get("kind") == "device":
        kind = p.get("thing_kind") or p.get("role")
        return KIND_ICONS.get(kind, kind)
    return None


def sigil(name):
    n = str(name or "").lower()
    if n in SIGILS:
        return SIGILS[n]
    return SIGIL_SET[sum(map(ord, n)) % len(SIGIL_SET)] if n else "·"

SYNC = {"synced": ("⇅", "synced"), "off": ("┄", "stays on this device"),
        "open": ("?", "not decided yet"), "always": ("⇅", "always synced")}

FRAME = {"app": "╭ ╮ ╰╯", "node": "╭─╮ ╰╯", "cloud": "┌ ┐ └┘", "documented": "╔ ╗ ╚╝",
         "planned": "╭┄╮┊╰╯"}
FOCUS_FRAME = "╭─╮│╰╯"
APP_MIN_W, THING_MAX_W = 12, 26
APP_GROW = 2                            # an app may be this much wider than its layout slot (the gap)
ERROR_W = 22                            # an error pinned on a piece wraps at this width


def _error_lines(text, width=ERROR_W):
    """The red ✕ and its reason, wrapped so the piece stays small."""
    parts = textwrap.wrap("✕ " + str(text), width) or ["✕"]
    return [[(parts[0], "abgelehnt")]] + [[("  " + x, "abgelehnt")] for x in parts[1:]]


def sync_text(state):
    sign, text = SYNC.get(state, ("·", state or ""))
    return sign, _(text)


def versions_lines(p):
    """The versions panel of a node piece (folded open with `i`)."""
    v = p.get("versions")
    out = []
    if not v:
        out.append((_("versions: unknown (an older ZENTRALE)"), "leise"))
    else:
        apps = ", ".join("%s %s" % kv for kv in sorted((v.get("apps") or {}).items())) or "—"
        contracts = " · ".join("%s %s" % (k, "/".join(str(m) for m in ms))
                               for k, ms in sorted((v.get("contracts") or {}).items())) or "—"
        same = ", ".join(v.get("same_version") or []) or _("none")
        out += [(_("apps: {apps}").format(apps=apps), "text"),
                (_("contracts: {c}").format(c=contracts), "text"),
                (_("auto-update: {x}").format(x=_("on") if v.get("auto_update") else _("off")), "text"),
                (_("same version as: {x}").format(x=same), "text")]
    for line in p.get("cannot_yet") or []:
        out.append(("✕ " + line, "abgelehnt"))
    return out


def _len(line):
    return sum(len(str(t)) for t, _r in line)


def _centre(line, width):
    pad = max(0, (width - _len(line)) // 2)
    return [(" " * pad, "text")] + line if pad else line


def _where(p):
    return " · ".join(str(x) for x in (p.get("address"),) if x)


def _state_line(p):
    """What the state says, readable without colour — or None (live)."""
    where = _where(p)
    tail = [(" · " + where, "leise")] if where else []
    if p.get("state") == "planned":
        return [("◇ " + _("not yet"), "planned")] + tail
    if p.get("state") == "documented":
        return [("▣ " + _("documented"), "leise")] + tail
    return None


def _icon_rows(p):
    kind = icon_of(p)
    planned = p.get("state") == "planned"
    return pixel_icons.cells(kind, hatched=planned) if kind else [], "planned" if planned else "glyph"


def _node(p, offen, fehler):
    """Icon on the left with the name below it; what the node says on the right."""
    rows, role = _icon_rows(p)
    name = str(p.get("title") or p.get("node") or p.get("id") or "?")
    left = [[(r, role)] for r in rows] + [[(name, "titel")]]
    lw = max([len(r) for r in rows] + [len(name)]) + 3
    v = p.get("versions") or {}
    right = [[(_("zentrale {v}").format(v=v.get("zentrale") or p.get("programm") or "?"), "text")]
             + ([("  ◂ " + _("this device"), "solder")] if p.get("this") else [])]
    state = _state_line(p)
    if state:
        right.append(state)
    else:
        right.append([(_("cloud on") if v.get("cloud", True) else _("local only"), "leise")])
    if p.get("managed") is False:
        right.append([(_("read only: no apply agent"), "leise")])
    elif p.get("seen"):
        right.append([(_("seen {t}").format(t=str(p["seen"])[:16].replace("T", " ")), "leise")])
    else:
        right.append([(_("i: versions"), "leise")])
    if fehler:
        right[1:1] = _error_lines(fehler, 30)
    out = []
    for j in range(max(len(left), len(right))):
        a = left[j] if j < len(left) else []
        b = right[j] if j < len(right) else []
        out.append(a + [(" " * (lw - _len(a)), "text")] + b)
    if offen:
        out += [[(text, rolle)] for text, rolle in versions_lines(p)]
    return out, None


def _cloud(p, fehler):
    rows, role = _icon_rows(p)
    lw = max([len(r) for r in rows] + [0]) + 2
    right = [[(str(p.get("title") or "cloud").lower(), "cloud")], [(_("the account's sync"), "leise")]]
    if fehler:
        right += _error_lines(fehler)
    out = []
    for j in range(max(len(rows), len(right))):
        a = [(rows[j], role)] if j < len(rows) else []
        b = right[j] if j < len(right) else []
        out.append(a + [(" " * (lw - _len(a)), "text")] + b)
    return out, None


def _thing(p, fehler):
    """The device as a little picture, its name below, then its state."""
    rows, role = _icon_rows(p)
    name = str(p.get("title") or p.get("id") or "?")
    lines = [[(r, role)] for r in rows] or [[("◈", role)]]
    lines.append([(name, "titel")])
    state = _state_line(p)
    if fehler:
        lines += _error_lines(fehler)
    elif state:
        lines.append(state[:1])
        if _where(p):
            lines.append([(_where(p), "leise")])
    elif p.get("role"):
        lines.append([(str(p["role"]), "leise")])
    return lines, "centre"


def _app(p, fehler):
    title = str(p.get("title") or p.get("id") or "?")
    lines = [[(sigil(p.get("name") or title) + " ", "glyph"), (title, "text")]]
    state = _state_line(p)
    if state:
        lines.append(state)
    elif "sync" in p:
        sign, text = sync_text(p["sync"])
        lines.append([(sign + " ", "solder"), (text, "text" if p["sync"] != "open" else "leise")])
    elif p.get("source"):
        lines.append([(_("source: {s}").format(s=p["source"]), "leise")])
    if fehler:
        lines[1:1] = _error_lines(fehler)
    return lines, None


def content(p, offen=False, fehler=None):
    """The inner lines of a piece → (lines, align). PURE."""
    if p.get("band") == "cloud":
        return _cloud(p, fehler)
    if p.get("kind") == "node":
        return _node(p, offen, fehler)
    if p.get("kind") == "device":
        return _thing(p, fehler)
    return _app(p, fehler)


def shape(p, offen=False, fehler=None):
    """Outer size (w, h) of a piece on the board, from what it shows: a
    node keeps its width, a thing or an app is as wide as its content."""
    lines, _a = content(p, offen, fehler)
    natural = max([_len(x) for x in lines] + [1]) + 4
    h = len(lines) + 2
    w0 = int(p.get("w") or 24)
    if p.get("kind") == "node":
        return max(w0, natural), h
    if p.get("kind") == "device":
        return min(THING_MAX_W, max(APP_MIN_W, natural)), h
    if p.get("band") == "cloud":
        return natural, h
    return min(w0 + APP_GROW, max(APP_MIN_W, natural)), max(h, int(p.get("h") or 4))


def node_height(p, offen):
    return shape(p, offen)[1]


class Piece:
    """The canvas art of every Schematix piece."""
    name = ART

    def zeichne(self, el, w, h):
        p = el.get("piece") or {}
        lines, align = content(p, el.get("offen"), el.get("fehler"))
        if align == "centre":
            lines = [_centre(x, w) for x in lines]
        # one column of air on the left: the glyph sits inside the corners
        lines = [[(" ", "text")] + x for x in lines]
        return lines[:max(0, h)]

    def modal(self, _el):
        return None

    def rand_von(self, el):
        p = el.get("piece") or {}
        if p.get("state") == "planned":
            return FRAME["planned"]
        if p.get("kind") == "node":
            return FRAME["node"]
        if p.get("band") == "cloud":
            return FRAME["cloud"]
        if p.get("state") == "documented":
            return FRAME["documented"]
        return FRAME["app"]

    def rand_fokus(self, _el):
        return FOCUS_FRAME

    def rolle_von(self, el):
        p = el.get("piece") or {}
        if el.get("fehler"):
            return "abgelehnt"
        if p.get("state") == "planned":
            return "planned"
        if p.get("band") == "cloud":
            return "cloud"
        if p.get("kind") == "device":
            return "layer-hardware"
        if p.get("kind") == "node":
            return "glyph"
        return "rahmen"
