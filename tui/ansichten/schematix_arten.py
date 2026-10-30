# tui/ansichten/schematix_arten.py
#
# How a piece of Schematix looks on the board (memory/hub/schematix.md,
# style: memory/hub/schematix_style.md). One canvas art `piece` for every
# kind — node, app, the cloud, a thing — because the Desk's canvas only asks
# the art (tui/bausteine/canvas.py: zeichne, rand_von, rolle_von). The
# element carries the map piece as it came from GET /api/schematix/map
# (`piece`), plus what the view keeps beside it (`offen`: versions panel
# folded open, `fehler`: an error pinned to it by Run).
#
# Every state is a glyph too, never only a colour (e-ink, 8 colours):
#   node ┏━┓ · app ╭─╮ · cloud / documented thing ╔═╗ · planned ┌╌┐ "not yet"
#   · an error pinned to it: frame in the error role and "✕ …" inside.

from .translate import _

ART = "piece"

SYNC = {"synced": ("⇅", "synced"), "off": ("┄", "stays on this device"),
        "open": ("?", "not decided yet"), "always": ("⇅", "always synced")}


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


def node_height(p, offen):
    return 5 + (len(versions_lines(p)) if offen else 0)


class Piece:
    """The canvas art of every Schematix piece."""
    name = ART

    def zeichne(self, el, w, h):
        p = el.get("piece") or {}
        kind = p.get("kind")
        title = str(p.get("title") or p.get("id") or "?")
        lines = []
        if p.get("band") == "cloud":
            lines.append([("☁ " + title.upper(), "cloud")])
            lines.append([(_("the account's sync"), "leise")])
        elif kind == "node":
            this = "  ◂ " + _("this device") if p.get("this") else ""
            lines.append([("▣ " + title.upper(), "titel"), (this, "solder")])
            v = p.get("versions") or {}
            lines.append([(_("ZENTRALE {v}").format(v=v.get("zentrale") or p.get("programm") or "?"), "text"),
                          ("  " + (_("cloud on") if v.get("cloud", True) else _("local only")), "leise")])
            if p.get("managed") is False:
                lines.append([(_("read only: no apply agent"), "leise")])
            elif p.get("seen"):
                lines.append([(_("seen {t}").format(t=str(p["seen"])[:16].replace("T", " ")), "leise")])
            else:
                lines.append([(_("i: versions"), "leise")])
            if el.get("offen"):
                lines += [[(text, rolle)] for text, rolle in versions_lines(p)]
        elif kind == "device":
            lines.append([("◈ " + title, "titel")])
            lines.append([(str(p.get("role") or ""), "leise")])
        else:
            lines.append([(title, "titel")])
            if "sync" in p:
                sign, text = sync_text(p["sync"])
                lines.append([(sign + " ", "solder"), (text, "text" if p["sync"] != "open" else "leise")])
            elif p.get("source"):
                lines.append([(_("source: {s}").format(s=p["source"]), "leise")])
        # The state takes the second line (what a live piece would say there
        # is not true yet), with where it will be — readable without colour.
        where = " · ".join(str(x) for x in (p.get("role") if kind == "device" else None,
                                            p.get("address")) if x)
        if lines and p.get("state") == "planned":
            lines[1:] = [[("◇ " + _("not yet"), "planned"), ((" · " + where) if where else "", "leise")]]
        elif lines and p.get("state") == "documented":
            lines[1:] = [[("▣ " + _("documented"), "leise"), ((" · " + where) if where else "", "leise")]]
        if el.get("fehler"):
            lines.insert(1, [("✕ " + el["fehler"], "abgelehnt")])
        return lines[:max(0, h)]

    def modal(self, _el):
        return None

    def rand_von(self, el):
        p = el.get("piece") or {}
        if p.get("state") == "planned":
            return "┌╌┐╎└┘"
        if p.get("kind") == "node":
            return "┎─┒┃┖┚"
        if p.get("band") == "cloud" or p.get("state") == "documented":
            return "╔═╗║╚╝"
        return "╭─╮│╰╯"

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
            return "titel"
        return "rahmen"
