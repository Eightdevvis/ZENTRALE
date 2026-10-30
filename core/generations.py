# core/generations.py
#
# Run: sketch → check → diff → switch (memory/hub/building_kit_plan.md 6.7,
# build step 9b; details memory/hub/port_types.md). One way for every change:
# whoever wants to change a wire (the CLI's sync choice, later the store's
# plug dialog and Schematix) calls run(); nothing writes the owners around it.
#
#   run(sketch)         compile (core/sketch_compiler.py, the hard gate) → diff
#                       against what is in effect → switch → apply → health
#                       check; a failed health check rolls back
#   diff(old, new)      plan lines in the OpenTofu style ("+ …", "- …", "~ …")
#   Store               generations as self-contained hashed JSON files; one
#                       "current" pointer per node, switched atomically (a
#                       symlink replaced in one rename, like hub/aktuell); the
#                       last N kept
#   reconcile(...)      the apply agent: make the owners say what the node's
#                       current generation says (core/wires.write), check,
#                       roll back to the previous generation when unhealthy
#
# A node without the apply agent (node description without `apply_agent`)
# is unmanaged: read-only on the map, never targeted (sketch_compiler).
#
# Where: setting `generations` (env ZENTRALE_GENERATIONS), default
# ~/.local/state/zentrale/generations — per node, never synced (the node frame).
#
# Foundation (layer 1).

import datetime
import json
import os

import ai_config
import dateien
import sketch_compiler
import wires
from i18n import _

DEFAULT_DIR = "~/.local/state/zentrale/generations"
KEEP = 10


class RunResult(dict):
    """{ok, errors, diff, generation, previous, rolled_back, problems}."""

    @property
    def ok(self):
        return self["ok"]


# ── Store ────────────────────────────────────────────────────────────────

class Store:
    def __init__(self, root=None, keep=KEEP):
        self.root = os.path.expanduser(root or ai_config.setting("generations") or DEFAULT_DIR)
        self.keep = keep

    def _file(self, h):
        return os.path.join(self.root, "gen", h.split(":", 1)[1] + ".json")

    def _node(self, node):
        return os.path.join(self.root, "nodes", dateien.sicherer_name(node))

    def save(self, gen) -> str:
        """Write the generation (once; same hash = same content)."""
        path = self._file(gen["hash"])
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            dateien.json_schreiben(path, gen)
        return gen["hash"]

    def load(self, h):
        try:
            with open(self._file(h), encoding="utf-8") as f:
                gen = json.load(f)
        except (OSError, ValueError):
            return None
        return gen if sketch_compiler.generation_hash(gen) == h == gen.get("hash") else None

    def current_hash(self, node):
        link = os.path.join(self._node(node), "current")
        try:
            return "sha256:" + os.path.basename(os.readlink(link))[:-len(".json")]
        except OSError:
            return None

    def current(self, node):
        h = self.current_hash(node)
        return self.load(h) if h else None

    def history(self, node) -> list:
        try:
            with open(os.path.join(self._node(node), "history.json"), encoding="utf-8") as f:
                h = json.load(f)
        except (OSError, ValueError):
            return []
        return h if isinstance(h, list) else []

    def switch(self, node, h, note=None):
        """Point `node` at generation `h`, atomically: a new symlink beside
        the old one, then one rename over it."""
        d = self._node(node)
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, f".current.{os.getpid()}.tmp")
        if os.path.lexists(tmp):
            os.remove(tmp)
        os.symlink(os.path.relpath(self._file(h), d), tmp)
        os.replace(tmp, os.path.join(d, "current"))
        hist = [x for x in self.history(node) if x.get("hash") != h]
        hist.append({"hash": h, "at": datetime.datetime.now().isoformat(timespec="seconds"),
                     **({"note": note} if note else {})})
        dateien.json_schreiben(os.path.join(d, "history.json"), hist[-self.keep:])
        self._prune()

    def previous(self, node):
        """The generation before the current one (for a roll-back)."""
        cur = self.current_hash(node)
        hashes = [x.get("hash") for x in self.history(node)]
        if cur in hashes and hashes.index(cur) > 0:
            return self.load(hashes[hashes.index(cur) - 1])
        return None

    def _prune(self):
        """Keep the generations any node's history still names."""
        keep = set()
        nodes = os.path.join(self.root, "nodes")
        for n in os.listdir(nodes) if os.path.isdir(nodes) else []:
            keep |= {x.get("hash") for x in self.history(n)}
            h = self.current_hash(n)
            keep.add(h)
        folder = os.path.join(self.root, "gen")
        for f in os.listdir(folder) if os.path.isdir(folder) else []:
            if f.endswith(".json") and "sha256:" + f[:-5] not in keep:
                os.remove(os.path.join(folder, f))


# ── Diff ─────────────────────────────────────────────────────────────────

def _titles(gen) -> dict:
    return {p["ref"]: p.get("title") or p["id"] for p in (gen or {}).get("pieces", [])}


def _side(address, titles):
    ref, pid = wires.split_port(address)
    return f"{titles.get(ref) or ref} {pid}"


def _line(w, titles, state=True):
    where = w["owner"].split(":", 1)[1]
    text = _("{to} → {frm} on {owner}").format(to=_side(w["to"], titles), frm=_side(w["from"], titles),
                                              owner=where)
    if state and w["state"] != "live":
        text += " (" + _(w["state"]) + ")"
    return text


def diff(old, new) -> list:
    """OpenTofu-style plan lines, sorted by wire id:
        + Tutor data → Cloud sync on minipc
        - Tutor data → Cloud sync on minipc
        ~ Lists data → Cloud sync on minipc: live → off
        ~ kalender-haupt source → Cloud calendar on kalender/kalender-haupt (was: Adapter google)"""
    titles = _titles(old) | _titles(new)
    out = []
    for wid, a, b in wires.changes((new or {}).get("wires", []), (old or {}).get("wires", [])):
        if a is None:
            out.append("+ " + _line(b, titles))
        elif b is None:
            out.append("- " + _line(a, titles))
        elif all(a.get(k) == b.get(k) for k in ("from", "to", "type", "owner")):
            out.append("~ " + _line(b, titles, state=False) + f": {_(a['state'])} → {_(b['state'])}")
        else:
            out.append("~ " + _line(b, titles) + " " + _("(was: {old})").format(old=_side(a["from"], titles)))
    return out


# ── The apply agent ──────────────────────────────────────────────────────

def _applies_here(w, node):
    return w.get("state") != "planned" and wires._writable(w, node)


def default_health(gen, node, problems) -> list:
    """Healthy = every writer succeeded and the owners now say what the
    generation says. → list of problems (empty = healthy)."""
    out = [f"{wid}: {p}" for wid, p in problems if p]
    want = [w for w in gen["wires"] if _applies_here(w, node)]
    have = [w for w in wires.all_wires(node) if _applies_here(w, node)]
    out += [_("{wire} did not take effect").format(wire=wid) for wid, _a, _b in wires.changes(want, have)]
    return out


def reconcile(store, node=None, health=None, writer=None, root=None) -> dict:
    """Bring the owners to the node's current generation. Unhealthy →
    switch back to the previous generation and apply that (once).
    → {"applied": hash|None, "problems": [...], "rolled_back": bool}."""
    node = node or wires.node_name()
    health = health or default_health
    gen = store.current(node)
    if gen is None:
        return {"applied": None, "problems": [], "rolled_back": False}
    done = wires.write([w for w in gen["wires"] if _applies_here(w, node)], node, root, writer)
    problems = health(gen, node, done)
    if not problems:
        return {"applied": gen["hash"], "problems": [], "rolled_back": False}
    prev = store.previous(node)
    if prev is None:
        return {"applied": gen["hash"], "problems": problems, "rolled_back": False}
    store.switch(node, prev["hash"], note="rolled back: " + "; ".join(problems)[:300])
    wires.write([w for w in prev["wires"] if _applies_here(w, node)], node, root, writer)
    return {"applied": prev["hash"], "problems": problems, "rolled_back": True}


# ── Run: the one way for every change ────────────────────────────────────

def in_effect(node=None):
    """What is in effect now, compiled: the projection of the stored truths.
    (Not the stored generation — a setting changed by a path that does not
    pass the gate yet must never be reverted by a run.) → (gen, errors)."""
    return sketch_compiler.compile_sketch(wires.sketch(node), current=None)


def run(sketch, node=None, store=None, apply=True, health=None, writer=None, root=None) -> RunResult:
    """Compile `sketch`; any error → nothing happens. Else diff against what
    is in effect, save both generations, switch this node's pointer and
    apply (unless apply=False: a plan only)."""
    node = node or wires.node_name()
    now = wires.sketch(node)
    current = {w["id"]: w for w in now["wires"]}
    gen, errors = sketch_compiler.compile_sketch(sketch, current=current)
    if errors:
        return RunResult(ok=False, errors=errors, diff=[], generation=None, previous=None,
                         rolled_back=False, problems=[])
    before, _errs = sketch_compiler.compile_sketch(now, current=current)
    lines = diff(before, gen)
    result = RunResult(ok=True, errors=[], diff=lines, generation=gen["hash"],
                       previous=before["hash"] if before else None, rolled_back=False, problems=[])
    if not apply or not lines:
        return result
    store = store or Store()
    if before is not None and store.current_hash(node) != before["hash"]:
        store.save(before)                    # what was in effect: the roll-back target
        store.switch(node, before["hash"], note="in effect before a run")
    store.save(gen)
    store.switch(node, gen["hash"])
    r = reconcile(store, node, health, writer, root)
    result.update(rolled_back=r["rolled_back"], problems=r["problems"], ok=not r["rolled_back"])
    return result


def with_wires(sketch, changed=(), removed=()) -> dict:
    """A copy of `sketch` with wires replaced/added (by id) and removed."""
    gone = set(removed) | {w["id"] for w in changed}
    return dict(sketch, wires=[w for w in sketch["wires"] if w["id"] not in gone] + list(changed))


def choose_sync(choice: dict, node=None, **kw) -> RunResult:
    """The CLI's sync choice ({app: True|False}) through the gate. Starting
    to decide on a device that never chose (None = everything) starts from
    "nothing decided", like abgleich_apps.setzen always did."""
    import abgleich_apps
    node = node or wires.node_name()
    sk = wires.sketch(node)
    removed = []
    if abgleich_apps.entscheidungen() is None:
        table = abgleich_apps.tabelle()
        removed = [w["id"] for w in sk["wires"] if w["type"] == "sync"
                   and not (table.get(wires._app_of(w)) or {}).get("pflicht")]
    changed = [wires.sync_wire(app, "live" if on else "off", node) for app, on in choice.items()]
    return run(with_wires(sk, changed, removed), node, **kw)
