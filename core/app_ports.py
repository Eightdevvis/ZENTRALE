# core/app_ports.py
#
# What an app needs and offers, as ports (memory/hub/building_kit_plan.md
# 1.5, build step 9). One reader for every kind of manifest:
#
#   new keys   `needs` / `offers` (English, contracts/ports/1 $defs/manifestPorts)
#   old keys   `rechte` (needs) and `liefert` (offers) — still read until the
#              renaming wave; marked `legacy`: the rights check grants them
#              today, the compiler does not demand a wire for them
#   [daten]    an app whose data may sync gets the socket `data` taking a
#              `sync` wire (0..1), unless it declares one itself
#   built-in   core/eingebaute_apps.py PORTS (declared like a manifest)
#
# Foundation (layer 1): reads data only, imports apps, eingebaute_apps, port_types.

import apps
import eingebaute_apps
import port_types

# Old rights words → port types (hub_bauplan.md "Rechte").
_OLD_WORDS = {"modell": "model", "mikro": "mic", "lautsprecher": "speaker"}
_OLD_ACCESS = {"lesen": "read", "schreiben": "write"}


def _qualified(fam, name):
    t = f"{fam}:{str(name).lower()}"
    return t if port_types.entry(t) is not None else None


def legacy_needs(rechte) -> list:
    """`rechte = [...]` → needs (legacy). Unknown words are skipped."""
    out = []
    for w in rechte or []:
        w = str(w)
        t = None
        if w in _OLD_WORDS:
            t = _OLD_WORDS[w]
        elif w.startswith("ereignis:"):
            t = _qualified("event", w[len("ereignis:"):])
        elif ":" in w and w.rsplit(":", 1)[1] in _OLD_ACCESS:
            app, acc = w.rsplit(":", 1)
            t = _qualified(_OLD_ACCESS[acc], app)
        if t:
            n = port_types.need({"type": t, "legacy": True})
            n["occurrences"] = [0, n["occurrences"][1]]
            out.append(n)
    return out


def legacy_offers(liefert) -> list:
    out = []
    for w in liefert or []:
        w = str(w)
        t = None
        if w.startswith("kachel:"):
            t = _qualified("tile", w[len("kachel:"):])
        elif w.startswith("ereignis:"):
            t = _qualified("event", w[len("ereignis:"):])
        if t:
            out.append(port_types.offer({"type": t, "legacy": True}))
    return out


def _merge(first, more):
    seen = {p["id"] for p in first}
    return first + [p for p in more if p["id"] not in seen and not seen.add(p["id"])]


def of_manifest(m: dict) -> dict:
    """A manifest (app.toml as dict, or a built-in declaration) → {needs, offers}
    in long form with every default filled in."""
    needs = [port_types.need(x) for x in (m.get("needs") or [])]
    offers = [port_types.offer(x) for x in (m.get("offers") or [])]
    d = apps.daten(m) if isinstance(m.get("daten"), dict) else None
    if d and d["abgleichen"]:
        needs = _merge(needs, [port_types.need({"id": "data", "type": "sync", "occurrences": [0, 1]})])
    return {"needs": _merge(needs, legacy_needs(m.get("rechte"))),
            "offers": _merge(offers, legacy_offers(m.get("liefert")))}


def declared(m: dict) -> dict:
    """Only what a manifest says in the port keys (for the item check)."""
    return {k: m[k] for k in ("needs", "offers") if k in m}


def builtin(name: str) -> dict:
    """The declaration of a built-in app (or its stand-in) as a manifest dict."""
    e = dict(eingebaute_apps.EINGEBAUT.get(name) or eingebaute_apps.ERSATZ.get(name) or {})
    e.update(eingebaute_apps.PORTS.get(name, {}))
    return e


def of_app(name: str, manifest=None) -> dict:
    """The ports of an installed app: its own manifest when it has moved out
    (and declares or implies ports), else the built-in declaration."""
    m = manifest if manifest is not None else apps.manifest(name)
    own = of_manifest(m) if m else {"needs": [], "offers": []}
    if name in eingebaute_apps.PORTS or name in eingebaute_apps.EINGEBAUT:
        base = of_manifest(builtin(name))
        return {"needs": _merge(own["needs"], base["needs"]),
                "offers": _merge(own["offers"], base["offers"])}
    return own
