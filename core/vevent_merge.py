# core/vevent_merge.py
#
# Three-way merge INSIDE one VEVENT, at the level of property groups
# (since 2026-10-29). Used by abgleich_vorschlaege for events changed on the
# phone: the phone says which version of the cloud it saw (base), the cloud
# may have moved on meanwhile (cloud). Before, any change on both sides of
# the same VEVENT was a conflict — also when the cloud only added a note and
# the phone moved the time. Now each GROUP is one unit:
#
#   phone unchanged          → cloud
#   cloud unchanged          → phone
#   both changed the same    → fine
#   both changed differently → conflict: the caller rejects the WHOLE proposal
#                              (no partial accept, the cloud is never overwritten)
#
# A group is a set of properties that only make sense together — taking
# DTSTART from one side and RRULE from the other would build an event nobody
# wrote. The grouping (memory/betrieb/abgleich_fremde_knoten.md "Termine vom
# Handy") follows core/kalender_ics_abbildung (X_* constants, VERWALTET):
#
#   time       DTSTART DTEND DURATION RRULE RDATE EXDATE EXRULE and the
#              ZENTRALE fields that describe them: X-ZENTRALE-AUS (exact list
#              of switched-off days, always next to its EXDATEs), -PAUSE
#              (pauses → EXDATEs), -SEIT, -OHNE-ANFANG, -RRULE-ROH,
#              -ZEIT-ROH, -ART (kind of piece, follows from the time shape)
#   title      SUMMARY          place      LOCATION GEO
#   note       DESCRIPTION      look       CATEGORIES COLOR
#   status     STATUS           busy       TRANSP
#   deadline   X-ZENTRALE-TYP X-ZENTRALE-SOLL + OUR warning VALARM
#              (X-ZENTRALE-VORWARNUNG:TRUE, or DESCRIPTION "Deadline: …")
#   reminders  all other VALARMs (from the phone, from Google) as one set
#   source     X-ZENTRALE-QUELLE URL (written together: zentrale://… address)
#   style      X-ZENTRALE-STIL   · motif X-ZENTRALE-MOTIV
#   cancel     X-ZENTRALE-ABSAGE-NOETIG · position X-ZENTRALE-POS
#   extras     X-ZENTRALE-EXTRAS
#   anything else: one group per property name; other subcomponents: one
#   group per component name.
#
# Not compared, never a conflict: DTSTAMP, LAST-MODIFIED, SEQUENCE (written
# fresh, see _technical), UID and RECURRENCE-ID (the key of the VEVENT).
#
# What the phone OMITS: a property ZENTRALE does not manage (not in `managed`,
# e.g. DESCRIPTION, X-ZENTRALE-*, Google fields) and no VALARM of a kind
# count as "unknown to the phone" = unchanged — a node that loses them while
# reading does not delete them (as kalender_ics_abbildung.zusammenfuehren).
# A managed property that is missing (LOCATION cleared) IS a change.
#
# Text level, line for line: lines that are not touched keep their bytes
# (folding, parameters, order). Pure functions, no clock.

from abgleich_ics import _name

TIME = "time"
TECHNICAL = frozenset({"DTSTAMP", "LAST-MODIFIED", "SEQUENCE"})
KEY = frozenset({"UID", "RECURRENCE-ID"})
# The same as kalender_ics_abbildung.X_VORWARNUNG / ALARM_TEXT (copied: this
# is the foundation, the mapping a service; tests check they stay equal).
X_WARNING = "X-ZENTRALE-VORWARNUNG"
WARNING_TEXT = "Deadline: "

GROUPS = {
    TIME: ("DTSTART", "DTEND", "DURATION", "RRULE", "RDATE", "EXDATE", "EXRULE",
           "X-ZENTRALE-AUS", "X-ZENTRALE-PAUSE", "X-ZENTRALE-SEIT", "X-ZENTRALE-OHNE-ANFANG",
           "X-ZENTRALE-RRULE-ROH", "X-ZENTRALE-ZEIT-ROH", "X-ZENTRALE-ART"),
    "title": ("SUMMARY",),
    "place": ("LOCATION", "GEO"),
    "note": ("DESCRIPTION",),
    "look": ("CATEGORIES", "COLOR"),
    "status": ("STATUS",),
    "busy": ("TRANSP",),
    "deadline": ("X-ZENTRALE-TYP", "X-ZENTRALE-SOLL"),
    "source": ("X-ZENTRALE-QUELLE", "URL"),
    "style": ("X-ZENTRALE-STIL",),
    "motif": ("X-ZENTRALE-MOTIV",),
    "cancel": ("X-ZENTRALE-ABSAGE-NOETIG",),
    "position": ("X-ZENTRALE-POS",),
    "extras": ("X-ZENTRALE-EXTRAS",),
}
_GROUP_OF = {n: g for g, names in GROUPS.items() for n in names}
REMINDERS = "reminders"
DEADLINE = "deadline"

# What the receipt text calls a group (gettext msgids, core/locale).
LABELS = {
    TIME: "time", "title": "title", "place": "place", "note": "note",
    "look": "category and colour", "status": "status", "busy": "busy/free",
    DEADLINE: "deadline", REMINDERS: "reminders", "source": "source",
    "style": "style", "motif": "motif", "cancel": "needs cancelling",
    "position": "position", "extras": "other ZENTRALE fields",
}
OTHER_LABEL = "field {name}"


class _Item:
    """One top-level property (or one subcomponent) of a VEVENT."""

    def __init__(self, name, raw, canon, sub=False):
        self.name, self.raw, self.canon, self.sub = name, raw, canon, sub
        self.group = None


def _unfold(raw_lines):
    out = []
    for z in raw_lines:
        if z.startswith((" ", "\t")) and out:
            out[-1] += z.rstrip("\r\n")[1:]
        elif z.strip():
            out.append(z.rstrip("\r\n").rstrip())
    return out


def _is_ours(canon_lines) -> bool:
    """Our deadline warning: marked, or (a server dropped the mark) its text."""
    for z in canon_lines:
        n = _name(z)
        v = z.split(":", 1)[1] if ":" in z else ""
        if n == X_WARNING and v.strip().upper() == "TRUE":
            return True
        if n == "DESCRIPTION" and v.startswith(WARNING_TEXT):
            return True
    return False


def parse(block: str):
    """VEVENT text → (first line, [_Item], last line). Raises ValueError."""
    lines = block.splitlines(keepends=True)
    if not lines or lines[0].strip().upper() != "BEGIN:VEVENT":
        raise ValueError("not a VEVENT")
    end = len(lines) - 1
    while end > 0 and not lines[end].strip():
        end -= 1
    if lines[end].strip().upper() != "END:VEVENT":
        raise ValueError("VEVENT without END")
    items, i = [], 1
    while i < end:
        start = i
        i += 1
        while i < end and lines[i].startswith((" ", "\t")):
            i += 1
        first = _unfold(lines[start:i])
        if not first:
            continue
        head = first[0]
        if head.upper().startswith("BEGIN:"):
            kind, depth = head.split(":", 1)[1].strip().upper(), 1
            while i < end and depth:
                o = lines[i].strip().upper()
                if not lines[i].startswith((" ", "\t")):
                    if o.startswith("BEGIN:"):
                        depth += 1
                    elif o.startswith("END:"):
                        depth -= 1
                i += 1
            raw = "".join(lines[start:i])
            canon = tuple(sorted(_unfold(lines[start:i])))
            it = _Item(kind, raw, canon, sub=True)
            if kind == "VALARM":
                it.group = DEADLINE if _is_ours(canon) else REMINDERS
            else:
                it.group = "sub:" + kind
        else:
            name = _name(head)
            it = _Item(name, "".join(lines[start:i]), head)
            if name not in TECHNICAL and name not in KEY:
                it.group = _GROUP_OF.get(name, "prop:" + name)
        items.append(it)
    return lines[0], items, "".join(lines[end:])


def _value(items, group):
    return tuple(sorted(str(it.canon) for it in items if it.group == group))


def _fill_unknown(side, base, managed):
    """What `side` omits and nobody can tell it meant to delete: unmanaged
    property names and VALARM kinds it has none of → the base's lines."""
    if base is None:
        return side
    names = {it.name for it in side if not it.sub}
    subs = {it.group for it in side if it.sub}
    extra = [it for it in base
             if (not it.sub and it.name not in names and it.name not in managed
                 and it.group is not None)
             or (it.sub and it.group not in subs)]
    return side + extra


def label(group: str, translate) -> str:
    if group in LABELS:
        return translate(LABELS[group])
    return translate(OTHER_LABEL).format(name=group.split(":", 1)[1])


def merge(base: str | None, phone: str, cloud: str | None, managed) -> tuple:
    """→ (merged VEVENT text, changed_from_phone: set, conflicts: [group]).
    base/cloud None = not there (a new RECURRENCE-ID part). `managed` = the
    property names ZENTRALE manages for this kind of VEVENT (VERWALTET or
    VERWALTET_ABWEICHUNG): only those count as deleted when omitted."""
    if base is None and cloud is None:         # new on the phone only
        _f, items, _l = parse(phone)
        return phone, {it.group for it in items if it.group}, []
    _b0, b_items, _b1 = parse(base) if base is not None else (None, None, None)
    p_first, p_items, p_last = parse(phone)
    if cloud is not None:
        first, c_items, last = parse(cloud)
    else:
        first, c_items, last = p_first, [], p_last
    # Only the phone's omissions are "unknown": the cloud is a computer that
    # keeps what it does not manage (zusammenfuehren) — what it lacks, it removed.
    p_items = _fill_unknown(p_items, b_items, managed)
    b_items = b_items or []

    groups = []
    for it in c_items + p_items + b_items:
        if it.group is not None and it.group not in groups:
            groups.append(it.group)
    from_phone, conflicts = set(), []
    for g in groups:
        vb, vp, vc = _value(b_items, g), _value(p_items, g), _value(c_items, g)
        if vp == vb or vp == vc:
            continue
        if vc == vb:
            from_phone.add(g)
        else:
            conflicts.append(g)
    if conflicts:
        return None, set(), conflicts
    if cloud is not None and not from_phone:
        return cloud, set(), []

    out, placed = [], set()
    for it in c_items:              # the cloud's order; a group from the phone
        if it.group in from_phone:  # goes where the cloud had it
            if it.group not in placed:
                out.extend(x for x in p_items if x.group == it.group)
                placed.add(it.group)
            continue
        out.append(it)
    for g in [g for g in groups if g in from_phone and g not in placed]:
        new = [x for x in p_items if x.group == g]
        k = next((k for k, it in enumerate(out) if it.sub), len(out))
        out[k:k] = [x for x in new if not x.sub]
        out.extend(x for x in new if x.sub)
    out = _technical(out, c_items, p_items, from_phone)
    return first + "".join(it.raw for it in out) + last, from_phone, []


def _digits(items, name):
    for it in items:
        if not it.sub and it.name == name:
            return "".join(c for c in it.canon.split(":", 1)[-1] if c.isdigit())
    return ""


def _technical(out, cloud, phone, from_phone):
    """DTSTAMP and LAST-MODIFIED: the later of both sides (the phone always
    stamps its edit; never older than the cloud's, so a computer-to-computer
    merge in abgleich_ics sees it as the newest). SEQUENCE (RFC 5545 3.8.7.4):
    +1 on the cloud's when time or status came from the phone."""
    for name in ("DTSTAMP", "LAST-MODIFIED"):
        if _digits(phone, name) > _digits(cloud, name):
            line = next(it for it in phone if not it.sub and it.name == name)
            k = next((k for k, it in enumerate(out) if not it.sub and it.name == name), None)
            if k is None:
                out.insert(next((k for k, it in enumerate(out) if it.sub), len(out)), line)
            else:
                out[k] = line
    seq_c, seq_p = _digits(cloud, "SEQUENCE"), _digits(phone, "SEQUENCE")
    seq = max(int(seq_c or 0), int(seq_p or 0))
    if from_phone & {TIME, "status"}:
        seq = max(seq, int(seq_c or 0) + 1)
    if seq or seq_c or seq_p:
        line = _Item("SEQUENCE", f"SEQUENCE:{seq}\r\n", f"SEQUENCE:{seq}")
        k = next((k for k, it in enumerate(out) if not it.sub and it.name == "SEQUENCE"), None)
        if k is None:
            out.insert(next((k for k, it in enumerate(out) if it.sub), len(out)), line)
        else:
            out[k] = line
    return out


def fold(line: str) -> str:
    """One content line, folded at 75 octets (RFC 5545 3.1), CRLF."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur)
            cur = b""
        cur += b
    out.append(cur)
    return "\r\n ".join(x.decode("utf-8") for x in out) + "\r\n"


def replace_property(block: str, name: str, lines: list) -> str:
    """All top-level `name` properties of a VEVENT → `lines` (unfolded content
    lines, folded here) at the place of the first one; none → before the
    first subcomponent."""
    first, items, last = parse(block)
    new = [_Item(name, fold(z), z) for z in lines]
    at = next((k for k, it in enumerate(items) if not it.sub and it.name == name), None)
    items = [it for it in items if it.sub or it.name != name]
    if at is None:
        at = next((k for k, it in enumerate(items) if it.sub), len(items))
    else:
        at = min(at, len(items))
    items[at:at] = new
    return first + "".join(it.raw for it in items) + last
