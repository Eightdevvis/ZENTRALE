# core/listen_baum.py
#
# Reine Helfer über den Eintrags-Baum einer Liste (core/lists.py): zählen,
# erledigt?, Fokus darunter?, Anzeige-Reihenfolge einer Ebene, flach
# klopfen, Pfad zu einem Eintrag, die Steine der Bernsteinleiste. Kein
# Lesen, kein Schreiben, keine Imports — nur Rechnen über Dicts.
#
# Warum ein eigenes Modul (2026-10-10): die Listen-Ansicht der TUI
# (tui/ansichten/fokus.py) und die Listen-Kachel (core/kachel_fokus.py)
# sollen eine Liste GLEICH zeigen — dieselbe Reihenfolge, derselbe
# Fortschritt. Leitlinie „dasselbe Objekt, nicht kopiert": die Helfer
# wohnten bis dahin in fokus.py und sind hierher umgezogen; fokus.py nimmt
# sie von hier (Tür `tui/` → Kern, bauplan_kern.md). Weil die TUI auch auf
# einem Aussenposten ohne Backend läuft, steht die Datei in
# deploy/aussenposten.txt — sie darf darum nichts aus dem Kern importieren.
# Das BILD einer Liste (Kästen, Bernstein) steht nicht hier, sondern in
# core/listen_bild.py (seit 2026-10-11, memory/hub/listen_app.md).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).


def _dicts(items):
    return [it for it in (items or []) if isinstance(it, dict)]


def _kinder(it):
    kids = it.get("items")
    return kids if isinstance(kids, list) and kids else None


def zaehlen(items):
    """(erledigt, gesamt) über die BLÄTTER einer Eintragsliste. Ordner zählen
    nicht selbst mit — sie sind nur Gruppierung."""
    d = t = 0
    for it in _dicts(items):
        kids = _kinder(it)
        if kids:
            cd, ct = zaehlen(kids)
            d += cd
            t += ct
        else:
            t += 1
            if it.get("done"):
                d += 1
    return d, t


def knoten_zaehlen(node):
    """(erledigt, gesamt) EINES Knotens: über seine Blätter, ein Blatt zählt
    als ein Punkt (wie core/lists.node_progress)."""
    kids = _kinder(node)
    if kids:
        return zaehlen(kids)
    return (1 if node.get("done") else 0, 1)


def erledigt(it):
    """Effektiver Erledigt-Status (wie core/lists.is_done): Blatt = eigenes
    'done'; Ordner = erledigt, wenn ALLE Kinder erledigt sind."""
    kids = _kinder(it)
    if kids:
        return all(erledigt(c) for c in _dicts(kids))
    return bool(it.get("done"))


def hat_fokus(it):
    """Trägt der Eintrag selbst oder irgendwas darunter den Fokus?"""
    if it.get("focus"):
        return True
    return any(hat_fokus(c) for c in _dicts(it.get("items")))


def ordnen(items, erledigte=False):
    """Anzeige-Reihenfolge einer Ebene.

    erledigte=False: nur OFFENE Einträge — der Fokus (oder ein Ordner, in dem
    er steckt) klebt oben, der Rest nach Anzahl OFFENER Punkte aufsteigend
    (was kaum noch Saft braucht, steht oben — 31/37 vor 1/2), bei gleich
    vielen offenen das mit mehr Erledigtem zuerst; danach bleibt die
    gespeicherte Reihenfolge.
    erledigte=True: nur die abgeschlossenen (Inhalt der Bernsteinleiste)."""
    rows = _dicts(items)
    if erledigte:
        return [it for it in rows if erledigt(it)]

    def rest(it):
        d, t = zaehlen([it])
        return t - d, -d

    offen = [it for it in rows if not erledigt(it)]
    return sorted(offen, key=lambda it: (not hat_fokus(it), rest(it)))


def steine(done, total, breite):
    """Spalten der Bernsteinleiste: je Spalte 'L' (leuchtender Stein), 'U'
    (leerer Stein) oder ' ' (Fuge). Ein Stein = ein Punkt; die Steinbreite
    rechnet sich aus Breite/Anzahl. Passen nicht alle Punkte als eigene Spalte
    rein, steht jede Spalte anteilig für mehrere (dann ohne Fugen)."""
    try:
        total, done, breite = int(total), int(done), int(breite)
    except (TypeError, ValueError):
        return []
    if total <= 0 or breite <= 0:
        return []
    done = max(0, min(done, total))
    if total > breite:                          # zu viele Punkte → skalieren
        lit = done * breite // total
        return ["L"] * lit + ["U"] * (breite - lit)
    fuge = breite // total >= 2                 # 1 Spalte Fuge, wenn Platz ist
    out = []
    for i in range(total):                      # Steine über die VOLLE Breite verteilen
        zelle = (i + 1) * breite // total - i * breite // total
        last = i == total - 1
        stein = zelle if (not fuge or last) else zelle - 1
        out += ["L" if i < done else "U"] * stein
        out += [" "] * (zelle - stein)
    return out


def pfad_zu(items, iid, acc=None):
    """id-Kette von der Listen-Wurzel bis zu iid (inklusive) — oder None."""
    if acc is None:
        acc = []
    for it in _dicts(items):
        if it.get("id") == iid:
            return acc + [iid]
        kids = _kinder(it)
        if kids:
            sub = pfad_zu(kids, iid, acc + [it.get("id")])
            if sub is not None:
                return sub
    return None


def flach(items, depth=0, out=None):
    """Den Eintrags-Baum in eine flache [(item, tiefe), …]-Liste klopfen,
    Eltern vor Kindern, gespeicherte Reihenfolge."""
    if out is None:
        out = []
    for it in _dicts(items):
        out.append((it, depth))
        kids = _kinder(it)
        if kids:
            flach(kids, depth + 1, out)
    return out


def finden(items, iid):
    """Den Eintrag mit iid irgendwo im Baum (oder None)."""
    for it, _d in flach(items):
        if it.get("id") == iid:
            return it
    return None


# ── Lists step 3 (2026-10-31, memory/hub/list_extraction_plan.md) ─────
# What the TUI's list view computed in its own process (A8) and what the
# calendar computed with these helpers in its own code now comes over HTTP
# from the lists' routes (ui/routen/listen.py). The rules stay here.

def level(lst, path):
    """One level of a list along a drill path of item ids →
    (direct items, valid path, names). A broken path (an item is gone) is
    cut where it breaks."""
    lst = lst if isinstance(lst, dict) else {}
    node_ = lst
    valid, names = [], [str(lst.get("name") or lst.get("id") or "")]
    for iid in path or []:
        nxt = next((it for it in _dicts(node_.get("items")) if it.get("id") == iid), None)
        if nxt is None:
            break
        node_ = nxt
        valid.append(iid)
        names.append(str(nxt.get("text") or ""))
    items = node_.get("items")
    return (items if isinstance(items, list) else []), valid, names


def _view(node_, whole):
    """What a surface needs to show one node without computing: counts over
    the leaves, effective done, and — for a node with points — the display
    order of its open points and its finished points (ids)."""
    kids = _kinder(node_)
    done, total = zaehlen(node_.get("items")) if whole else knoten_zaehlen(node_)
    view = {"done": done, "total": total,
            "complete": erledigt(node_) if not whole else bool(total) and done == total}
    if kids or whole:
        view["order"] = [it.get("id") for it in ordnen(kids or [])]
        view["finished"] = [it.get("id") for it in ordnen(kids or [], True)]
    return view


def with_view(lists):
    """`GET /api/lists?view=1`: the same lists, each list and each item with
    a `view` {done, total, complete, order?, finished?} (A8). New dicts, the
    input is not changed."""
    def item(it):
        out = {k: v for k, v in it.items() if k != "items"}
        if isinstance(it.get("items"), list):
            out["items"] = [item(c) if isinstance(c, dict) else c for c in it["items"]]
        out["view"] = _view(it, False)
        return out

    out = []
    for lst in lists or []:
        if not isinstance(lst, dict):
            out.append(lst)
            continue
        new = {k: v for k, v in lst.items() if k != "items"}
        if isinstance(lst.get("items"), list):
            new["items"] = [item(c) if isinstance(c, dict) else c for c in lst["items"]]
        new["view"] = _view(lst, True)
        out.append(new)
    return out


def targets(lists, kind, lid, iid=None):
    """Where a list (kind "list") or an item (kind "item") can be filed into
    ("einordnen", `>`), across ALL lists — flat, in stored order, WITHOUT the
    source's own subtree (no cycle) and without the source list itself.
    → [{lid, iid (None = top of that list), text, tiefe}] (tiefe 0 = list)."""
    excl = set()
    if kind == "item":
        src_lst = next((l for l in _dicts(lists) if l.get("id") == lid), None)
        src = finden((src_lst or {}).get("items"), iid)
        if src is not None:
            excl = {it.get("id") for it, _d in flach([src])}
    out = []
    for lst in _dicts(lists):
        this = lst.get("id")
        if kind == "list" and this == lid:
            continue
        out.append({"lid": this, "iid": None, "text": str(lst.get("name") or ""), "tiefe": 0})
        for it, d in flach(lst.get("items")):
            if kind == "item" and this == lid and it.get("id") in excl:
                continue
            out.append({"lid": this, "iid": it.get("id"), "text": str(it.get("text") or ""),
                        "tiefe": d + 1})
    return out


# Resolve a node to "what is on top now": the calendar shows a time slot's
# title live from a list or project (core/kalender_quelle.py), behind
# POST /api/lists/aufloesen.

OK, EMPTY, MISSING = "ok", "leer", "fehlt"


def node(lists, qid):
    """`"<list>"` or `"<list>/<item>"` → (node, name, list id, is_item) or None."""
    lid, _, iid = str(qid or "").partition("/")
    lst = next((l for l in _dicts(lists) if l.get("id") == lid), None)
    if lst is None:
        return None
    if not iid:
        return lst, lst.get("name") or lid, lid, False
    if not iid.isdigit():
        return None
    it = finden(lst.get("items"), int(iid))
    if it is None:
        return None
    return it, it.get("text") or iid, lid, True


def top_leaf(items):
    """The topmost open LEAF in display order (or None)."""
    row = ordnen(items)
    if not row:
        return None
    kids = _kinder(row[0])
    return top_leaf(kids) if kids else row[0]


def open_leaves(items, n):
    """The first `n` open LEAVES in display order (the first is top_leaf)."""
    out = []

    def walk(lvl):
        for it in ordnen(lvl):
            if len(out) >= n:
                return
            kids = _kinder(it)
            if kids:
                walk(kids)
            else:
                out.append(it)
    walk(items)
    return out


def resolve(lists, qid, n=0):
    """One node, now → {"zustand": ok|leer|fehlt, "titel", "name",
    "eintrag": {liste, id} | None, "offene": [first n open points],
    "projekt": bool}.
    ok:    titel = topmost open point, eintrag = that point (to tick it)
    leer:  titel = "<name> — alles erledigt"
    fehlt: list/item gone → titel and name None (the caller has a fallback)."""
    hit = node(lists, qid)
    if hit is None:
        return {"zustand": MISSING, "titel": None, "name": None, "eintrag": None,
                "offene": [], "projekt": False}
    it, name, lid, is_item = hit
    project = bool(it.get("project"))
    leaf = top_leaf(it.get("items"))
    if leaf is None:
        if is_item and not erledigt(it):
            # an item without points of its own IS the step itself
            return {"zustand": OK, "titel": name, "name": name, "offene": [],
                    "eintrag": {"liste": lid, "id": it.get("id")}, "projekt": project}
        return {"zustand": EMPTY, "titel": "%s — alles erledigt" % name, "name": name,
                "eintrag": None, "offene": [], "projekt": project}
    points = [p.get("text") or "?" for p in open_leaves(it.get("items"), n)] if n > 0 else []
    return {"zustand": OK, "titel": leaf.get("text") or "?", "name": name, "offene": points,
            "eintrag": {"liste": lid, "id": leaf.get("id")}, "projekt": project}
