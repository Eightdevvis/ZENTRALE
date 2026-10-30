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
#
#   sketch()        → {"format": "zentrale-sketch/1", pieces, wires} of this node
#   write(wires)    write the owners where `wires` differ from the projection;
#                   equal wires write nothing (round trip: settings byte-identical)
#
# Every write passes the gate first (core/generations.run); write() is the
# apply agent's hand, not a door.
#
# Foundation (layer 1).

import os

import abgleich_apps
import app_ports
import apps
import dateien
import eingebaute_apps
import kalender_einstellung as ke
import port_types

SKETCH = "zentrale-sketch/1"
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


def all_wires(name=None) -> list:
    return sync_wires(name) + calendar_wires(name)


def sketch(name=None, hardware=True) -> dict:
    """The projection of this node: every piece with its ports and every wire
    that has a stored truth today."""
    return {"format": SKETCH, "pieces": pieces(name, hardware), "wires": all_wires(name)}


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
    if r.get("ergebnis") in ("gleich", "gesetzt", "fuellt", "uebernimmt", "continued"):
        return None
    return r.get("fehler") or r.get("ergebnis")


def write(desired, name=None, root=None, calendar_writer=None) -> list:
    """Make the owners say what `desired` says, for the wires this node owns.
    Only differences are written; → [(id, problem | None)] of what was written."""
    name = name or node_name()
    root = root or os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    mine = [w for w in desired if w.get("state") != "planned" and _writable(w, name)]
    current = [w for w in all_wires(name) if _writable(w, name)]
    done, sync_changed = [], False
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
    if sync_changed:
        abgleich_apps.replace(_sync_choice([w for w in mine if w["type"] == "sync"]))
    return done


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
    """Wires whose owner store this node writes: its own sync wires and the
    (synced) calendar instance settings."""
    return (w.get("type") == "sync" and w.get("owner") == node_id(name)) or \
        w.get("type") == "calendar-source"
