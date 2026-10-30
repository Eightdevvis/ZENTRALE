# core/wires.py
#
# One view over the wires that exist today (memory/hub/building_kit_plan.md
# 1.4, build step 9). Nothing is stored here: the wires are a PROJECTION of the
# settings that already hold them, and writing a wire writes into those same
# settings. No wire file next to them, no second store.
#
#   sync            app `data` → cloud `sync`, per node:  setting `abgleich_apps`
#                   (core/abgleich_apps.py) — live = true, off = false, no wire =
#                   not decided yet; never chosen (None) = every app live
#   calendar-source calendar instance ← google / cloud / local:  `quelle` in
#                   data/adapter/anschluesse/kalender-<id>.json
#                   (core/kalender_einstellung.py); no file = google (as before)
#   every other     a plug from the plug dialog (step 11: model, files, read:…,
#                   mic …): core/plug_store.py — the consumer instance's synced
#                   file (instance scope) or the node's own file (node scope)
#
#   sketch()        → {"format": "zentrale-sketch/1", pieces, wires} of this node
#   write(wires)    write the owners where `wires` differ from the projection;
#                   equal wires write nothing (round trip: settings byte-identical)
#   node_section()  this node's own node-scoped wires for its description in
#                   the cloud (follow-up 4: other nodes and Schematix read them
#                   with wires_of_description)
#
# Every write passes the gate first (core/generations.run); write() is the
# apply agent's hand, not a door. Nothing else writes these owners
# (guard: tests/test_plug_dialog.py).
#
# Foundation (layer 1).

import os

import abgleich_apps
import app_ports
import apps
import dateien
import eingebaute_apps
import formats
import kalender_einstellung as ke
import plug_store
import port_types

SKETCH = "zentrale-sketch/1"
NODE_WIRES_FORMAT = "zentrale-node-wires/1"          # the `wires` field of a node description
CLOUD = "zentrale://cloud/"
SYNC_PORT = CLOUD + "port/sync"
CALENDAR_APP = "kalender"
# calendar `quelle` ↔ the provider port of the wire
SOURCE_PORTS = {"google": "zentrale://adapter/port/google", "zencloud": CLOUD + "port/calendar"}
LOCAL_PORT = "calendar-local"


class WireError(ValueError):
    """A wire this node cannot write (English, for people)."""


def node_name() -> str:
    return dateien.knoten()


def node_id(name=None) -> str:
    return "node:" + (name or node_name())


def node_ref(name=None) -> str:
    return f"zentrale://hub/node/{name or node_name()}/"


def app_ref(name) -> str:
    return f"zentrale://{name}/"


def port(ref, pid) -> str:
    return ref + "port/" + pid


def split_port(address):
    """zentrale://cloud/port/sync → ("zentrale://cloud/", "sync")."""
    ref, sep, pid = str(address).rpartition("port/")
    return (ref, pid) if sep else (None, None)


def _hardware_offers(sys_root="/"):
    import knoten
    hw = knoten.hardware(sys_root)
    names = {"mikro": "mic", "lautsprecher": "speaker", "bildschirm": "display"}
    return [port_types.offer(t) for k, t in names.items() if hw.get(k)]


def node_piece(name=None, hardware=True) -> dict:
    offers = [port_types.offer(x) for x in eingebaute_apps.NODE_PORTS["offers"]]
    if hardware:
        offers += _hardware_offers()
    return {"id": node_id(name), "ref": node_ref(name), "kind": "node", "title": name or node_name(),
            "state": "live", "managed": True, "types": port_types.supported(),
            "needs": [], "offers": offers, "owns": []}


def piece_of_description(d: dict) -> dict:
    """Another node's description (GET /v1/knoten, core/knoten.py) as a node
    piece. Without `apply_agent` it is unmanaged: read-only, never targeted."""
    name = str(d.get("name") or "")
    return {"id": node_id(name), "ref": node_ref(name), "kind": "node", "title": name,
            "state": "live", "managed": bool(d.get("apply_agent")),
            "types": dict(d.get("types") or {}), "needs": [],
            "offers": [port_types.offer(x) for x in eingebaute_apps.NODE_PORTS["offers"]],
            "owns": []}


def _app_names() -> list:
    """Apps with data (sync table), the cloud, then every other installed app."""
    names = list(abgleich_apps.tabelle())
    for extra in ["cloud"] + [str(m.get("_slug") or m.get("name") or "") for m in apps.installiert()]:
        if extra and extra not in names:
            names.append(extra)
    return names


def _manifests() -> dict:
    out = {}
    for m in apps.installiert():
        out.setdefault(str(m.get("_slug") or m.get("name") or ""), m)
    return out


def pieces(name=None, hardware=True) -> list:
    node = node_id(name)
    table = abgleich_apps.tabelle()
    manifests = _manifests()
    out = [node_piece(name, hardware)]
    for n in _app_names():
        p = app_ports.of_app(n, manifests.get(n) or {})
        e = eingebaute_apps.EINGEBAUT.get(n) or eingebaute_apps.ERSATZ.get(n) or {}
        title = (table.get(n) or {}).get("titel") or (manifests.get(n) or {}).get("titel") or e.get("titel") or n
        out.append({"id": "app:" + n, "ref": app_ref(n), "kind": "app", "title": str(title),
                    "state": "live", "on": [node], "needs": p["needs"], "offers": p["offers"],
                    "owns": ["file:" + x for x in (table.get(n) or {}).get("muster", [])]})
    for iid in _calendar_ids():
        needs = [port_types.need(x) for x in eingebaute_apps.INSTANCE_PORTS[CALENDAR_APP]["needs"]]
        out.append({"id": f"app:{CALENDAR_APP}/{iid}", "ref": f"zentrale://{CALENDAR_APP}/{iid}/",
                    "kind": "app", "title": iid, "state": "live", "on": [node],
                    "needs": needs, "offers": [], "owns": [f"setting:{iid}#quelle"]})
    return out


def _calendar_ids() -> list:
    ids = list(ke.instanzen())
    return sorted(set(ids) | {ke.HAUPT})


# ── The wires ────────────────────────────────────────────────────────────

def sync_wire(app, state, name=None) -> dict:
    name = name or node_name()
    return {"id": f"sync/{name}/{app}", "from": SYNC_PORT, "to": port(app_ref(app), "data"),
            "type": "sync", "owner": node_id(name), "state": state}


def calendar_wire(iid, quelle, name=None) -> dict:
    src = SOURCE_PORTS.get(quelle) or port(node_ref(name), LOCAL_PORT)
    return {"id": f"calendar-source/{iid}", "from": src,
            "to": port(f"zentrale://{CALENDAR_APP}/{iid}/", "source"),
            "type": "calendar-source", "owner": f"app:{CALENDAR_APP}/{iid}", "state": "live"}


def quelle_of(wire):
    """The calendar `quelle` a calendar-source wire stands for (or None)."""
    for q, addr in SOURCE_PORTS.items():
        if wire.get("from") == addr:
            return q
    ref, pid = split_port(wire.get("from"))
    if pid == LOCAL_PORT and ref and ref.startswith("zentrale://hub/node/"):
        return "lokal"
    return None


def sync_wires(name=None) -> list:
    choice = abgleich_apps.entscheidungen()
    out = []
    for n, a in abgleich_apps.tabelle().items():
        if choice is None or a.get("pflicht"):
            out.append(sync_wire(n, "live", name))
        elif n in choice:
            out.append(sync_wire(n, "live" if choice[n] else "off", name))
    return out


def calendar_wires(name=None) -> list:
    return [calendar_wire(iid, ke.quelle(iid), name) for iid in _calendar_ids()]


OWN_TYPES = ("sync", "calendar-source")      # wires with an older home than plug_store


def is_plug(w) -> bool:
    return w.get("type") not in OWN_TYPES


def scope_of(w):
    return (port_types.entry(w.get("type")) or {}).get("scope")


def plug_wires(name=None, refs=None) -> list:
    """The plugs of plug_store that land on this node: instance plugs whose
    consumer and provider are pieces here (a synced file may name an app
    installed only elsewhere — it stays in the file, untouched), and the
    node's own plugs."""
    name = name or node_name()
    if refs is None:
        refs = {p["ref"] for p in pieces(name, hardware=False)}
    out = [w for w in plug_store.instance_wires() if scope_of(w) == "instance" and is_plug(w)]
    out += [w for w in plug_store.node_wires(name)
            if scope_of(w) == "node" and is_plug(w) and w.get("owner") == node_id(name)]
    return [w for w in out
            if split_port(w.get("from"))[0] in refs and split_port(w.get("to"))[0] in refs]


def all_wires(name=None, refs=None) -> list:
    return sync_wires(name) + calendar_wires(name) + plug_wires(name, refs)


def sketch(name=None, hardware=True) -> dict:
    """The projection of this node: every piece with its ports and every wire
    that has a stored truth today."""
    ps = pieces(name, hardware)
    return {"format": SKETCH, "pieces": ps, "wires": all_wires(name, {p["ref"] for p in ps})}


# ── The node's own wires in its description (follow-up 4) ─────────────────

def node_section(name=None) -> dict:
    """This node's own node-scoped wires (its sync choices, its hardware
    plugs) for the node description in the cloud. Only this node writes its
    description; every other node and Schematix only read it."""
    name = name or node_name()
    mine = [w for w in all_wires(name) if scope_of(w) == "node" and w.get("owner") == node_id(name)]
    return {"format": NODE_WIRES_FORMAT, "wires": sorted(mine, key=lambda w: w["id"])}


def wires_of_description(d: dict) -> list:
    """The wires another node published in its description. Read rule of
    step 5: an unknown major or a malformed field gives none (nothing is
    guessed); only that node's own node-scoped wires that pass the item
    check are taken."""
    sec = d.get("wires") if isinstance(d, dict) else None
    if not isinstance(sec, dict) or not str(sec.get("format", "")).startswith("zentrale-node-wires/"):
        return []
    try:
        formats.check(sec, "node-wires")
    except formats.NewerFormat:
        return []
    owner = node_id(str(d.get("name") or ""))
    return [w for w in sec.get("wires") or [] if isinstance(w, dict) and w.get("owner") == owner
            and port_types.check(w, "wire") == [] and scope_of(w) == "node"]


# ── Writing back into the owners ──────────────────────────────────────────

def changes(desired, current) -> list:
    """(id, old wire | None, new wire | None) for every wire that differs."""
    old = {w["id"]: w for w in current}
    new = {w["id"]: w for w in desired}
    out = []
    for wid in sorted(set(old) | set(new)):
        a, b = old.get(wid), new.get(wid)
        if _core(a) != _core(b):
            out.append((wid, a, b))
    return out


def _core(w):
    return None if w is None else {k: w.get(k) for k in ("from", "to", "type", "owner", "state")}


def _calendar_write(iid, quelle, root):
    """Default writer of a calendar source: the one place that re-plugs it
    (core/adapter_ablauf.kalender_quelle_setzen — sets the value, fills or
    takes over the cloud calendar). → None when done, else the reason."""
    import adapter_ablauf
    r = adapter_ablauf.kalender_quelle_setzen(iid, quelle, root)
    return calendar_problem(r)


# "interrupted" keeps the new value on purpose (adapter_ablauf: the next sync
# completes it; going back would let the Google timer run on a half-switched
# device), so it is no problem for the health check.
CALENDAR_DONE = ("gleich", "gesetzt", "fuellt", "uebernimmt", "continued", "interrupted")


def calendar_problem(r):
    """A kalender_quelle_setzen answer → None (done) or the reason."""
    if r.get("ergebnis") in CALENDAR_DONE:
        return None
    return r.get("fehler") or r.get("ergebnis")


def calendar_writer(report=None, results=None):
    """A calendar writer for generations.run that shows progress (`report`,
    the CLI's sign of life) and hands back kalender_quelle_setzen's whole
    answer in `results`, so the CLI can say what happened in its own words."""
    def write_one(iid, quelle, root):
        import adapter_ablauf
        r = adapter_ablauf.kalender_quelle_setzen(iid, quelle, root, report=report)
        if results is not None:
            results.append(r)
        return calendar_problem(r)
    return write_one


def node_owned(w, name=None) -> bool:
    """A wire this node owns by itself (scope node): what the keeper enforces."""
    return scope_of(w) == "node" and w.get("owner") == node_id(name)


def write(desired, name=None, root=None, calendar_writer=None, only=None) -> list:
    """Make the owners say what `desired` says, for the wires this node owns
    (and, with `only`, just those it selects). Only differences are written;
    → [(id, problem | None)] of what was written."""
    name = name or node_name()
    root = root or os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    pick = (lambda w: _writable(w, name) and (only is None or only(w)))
    mine = [w for w in desired if w.get("state") != "planned" and pick(w)]
    current = [w for w in all_wires(name) if pick(w)]
    done, sync_changed, plugs = [], False, {}
    for wid, old, new in changes(mine, current):
        w = new or old
        if w["type"] == "sync":
            sync_changed = True
            done.append((wid, None))
        elif w["type"] == "calendar-source":
            if new is None:
                raise WireError(f"{wid}: a calendar always has a source")
            q = quelle_of(new)
            if q is None:
                raise WireError(f"{wid}: unknown calendar source {new['from']}")
            iid = split_port(new["to"])[0].rstrip("/").rsplit("/", 1)[1]
            done.append((wid, (calendar_writer or _calendar_write)(iid, q, root)))
        else:
            plugs.setdefault(_plug_file(w, name), {})[wid] = new
    for path, changed in plugs.items():
        problem = _write_plugs(path, changed)
        done += [(wid, problem) for wid in changed]
    if sync_changed:
        abgleich_apps.replace(_sync_choice([w for w in mine if w["type"] == "sync"]))
    return done


def _plug_file(w, name):
    scope = scope_of(w)
    if scope == "instance":
        return plug_store.instance_file(_app_of(w))
    if scope == "node" and w.get("owner") == node_id(name):
        return plug_store.node_file(name)
    raise WireError(f"{w['id']}: this node cannot store a {w['type']} wire")


def _write_plugs(path, changed):
    """Replace or remove (new None) the changed wires in one plug file; the
    rest of the file (other apps' wires, fields this version does not know)
    stays as it is. → None or the problem (a newer format: read-only)."""
    keep = [w for w in plug_store.read(path) if w["id"] not in changed]
    try:
        plug_store.write(path, keep + [w for w in changed.values() if w is not None])
    except formats.NewerFormat as e:
        return str(e)
    return None


def _app_of(w) -> str:
    return split_port(w["to"])[0][len("zentrale://"):-1]


def _sync_choice(wires) -> dict:
    """The setting `abgleich_apps` that the sync wires stand for. Choices of
    apps that are not in the table (uninstalled) are kept; required apps
    (the adapter) are never asked and never stored."""
    table = abgleich_apps.tabelle()
    out = dict(abgleich_apps.entscheidungen() or {})
    wired = set()
    for w in wires:
        app = _app_of(w)
        wired.add(app)
        if not (table.get(app) or {}).get("pflicht"):
            out[app] = w["state"] == "live"
    for app, a in table.items():
        if app not in wired and not a.get("pflicht"):
            out.pop(app, None)           # no wire = not decided yet
    return out


def _writable(w, name) -> bool:
    """Wires whose owner store this node writes: its own node-scoped wires
    (sync, hardware plugs), the (synced) calendar instance settings and the
    (synced) instance plugs."""
    if w.get("type") == "calendar-source":
        return True
    scope = scope_of(w)
    if scope == "node":
        return w.get("owner") == node_id(name)
    return scope == "instance" and is_plug(w)
