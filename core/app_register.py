# core/app_register.py
#
# Was aus dem Schaufenster installiert ist — und wie die Quelle einer App im
# Katalog aussieht (2026-10-25, memory/hub/shop.md „Apps installieren").
# Schicht 1: core/apps.py (findet Apps) und core/shop.py (prüft den Katalog)
# lesen hier; das Installieren selbst macht core/app_installation.py
# (Schicht 2) darüber.
#
# Register je Rechner: <installiert_ordner>/apps-<rechner>.json (Standard
# data/hub/, nie abgeglichen: der Code liegt nur auf DIESEM Rechner, und auf
# einem anderen will Sasha vielleicht andere Ansichten). Form (JSON):
#     {"apps": [{"name": "budget", "quelle": "zentrale://shop/apps/budget",
#                "ordner": "/home/…/budgeter", "ansichten": ["browser"],
#                "am": "2026-10-25T12:00:00+02:00"}]}
# Name, Titel, Ansichten-Angebot liest der Hub immer frisch aus dem app.toml
# im Ordner — hier steht nur, was Sasha gewählt hat (dasselbe Objekt, nicht
# kopiert).
#
# Register v2 (memory/hub/app_delivery_plan.md step 1, 2026-10-31): every
# entry also says HOW it got here and what it runs —
#     "source": {"kind": "git", "ref": "<repo address>"},   # source adapter
#     "version": "1.2.0",                                    # installed now
#     "data": {}                                             # data plugs
# The file carries "format": 2. Old entries (no `source`) read as a `git`
# source whose ref is the checkout's own origin (ref ""), version "" and no
# data plugs. Old releases keep reading the file: they only look at name,
# ordner and ansichten, which v2 still writes.
#
# Wo Apps wohnen: Einstellung `app_ordner` (Env ZENTRALE_APP_ORDNER),
# Standard der Ordner, in dem ZENTRALE liegt — dort stehen schon Tutor und
# Karte.

import json
import os
import re
import urllib.parse

import ai_config
import dateien

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
ORDNER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SCHEMATA = ("https", "ssh", "file")
FORMAT = 2
KIND = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


# ── Orte ──────────────────────────────────────────────────────────────

def app_ordner() -> str:
    eigen = ai_config.setting("app_ordner")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.dirname(_ROOT)


def datei() -> str:
    eigen = ai_config.setting("installiert_ordner")
    basis = (os.path.abspath(os.path.expanduser(str(eigen))) if eigen
             else os.path.join(_ROOT, "data", "hub"))
    return os.path.join(basis, "apps-%s.json" % dateien.knoten())


# ── Lesen / schreiben ────────────────────────────────────────────────

def lesen() -> list:
    try:
        with open(datei(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    raus = []
    for e in (d.get("apps") if isinstance(d, dict) else None) or []:
        if (isinstance(e, dict) and NAME.match(str(e.get("name") or ""))
                and isinstance(e.get("ordner"), str) and isinstance(e.get("ansichten"), list)):
            raus.append(normalized(e))
    return raus


def normalized(e) -> dict:
    """One register entry in v2 form. An entry without a valid `source`
    (written before v2) reads as a `git` source with ref "" (= the
    checkout's own origin); `version` defaults to "", `data` to {}."""
    e = dict(e)
    src = e.get("source")
    if not (isinstance(src, dict) and KIND.match(str(src.get("kind") or ""))
            and isinstance(src.get("ref", ""), str)):
        src = {"kind": "git", "ref": ""}
    e["source"] = {"kind": str(src["kind"]), "ref": str(src.get("ref") or "")}
    e["version"] = e["version"] if isinstance(e.get("version"), str) else ""
    e["data"] = dict(e["data"]) if isinstance(e.get("data"), dict) else {}
    return e


def schreiben(eintraege) -> None:
    dateien.json_schreiben(datei(), {"format": FORMAT,
                                     "apps": sorted((normalized(e) for e in eintraege),
                                                    key=lambda e: e["name"])})


def alle() -> list:
    """Alle aus dem Laden installierten Apps dieses Rechners, nach Name."""
    return sorted(lesen(), key=lambda e: e["name"])


def namen() -> list:
    return [e["name"] for e in alle()]


def eintrag(name):
    for e in lesen():
        if e["name"] == name:
            return e
    return None


# ── Die Quelle einer App im Katalog ──────────────────────────────────

def app_name(stueck) -> str:
    """additionalProperty `app_name` eines Stücks (= name im app.toml)."""
    for p in stueck.get("additionalProperty") or []:
        if isinstance(p, dict) and p.get("name") == "app_name":
            return str(p.get("value") or "")
    return ""


def built_in(stueck) -> bool:
    """additionalProperty `built_in` true: the app ships inside the core
    package (core/builtin_store_apps.py), nothing to download."""
    for p in stueck.get("additionalProperty") or []:
        if isinstance(p, dict) and p.get("name") == "built_in":
            return p.get("value") is True
    return False


def ordner_name(url) -> str:
    """ssh://git@github.com/x/budgeter.git → budgeter"""
    n = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return n[:-4] if n.endswith(".git") else n


def _git_ref_error(url):
    teile = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    if teile is None or teile.scheme not in SCHEMATA or not teile.path.strip("/"):
        return "downloadUrl fehlt oder ist kein git-repo (https, ssh, file)"
    if not ORDNER_NAME.match(ordner_name(url)):
        return "downloadUrl endet nicht auf einen ordnernamen"
    return None


def quelle_fehler(stueck):
    """Ein Stück der Kategorie apps muss sagen, woher es kommt und wie die
    App heißt (`app_name`). Woher: `sources` (catalog v2, see below) and/or
    the old `downloadUrl` (a git repo over https/ssh/file). → None oder ein
    Satz, was fehlt (shop.pruefen macht daraus einen kaputten Katalog).
    A built-in app (`built_in` true, still inside the core package — building
    kit step 10) has no source; it only needs its `app_name`."""
    if built_in(stueck):
        return None if NAME.match(app_name(stueck)) else "app_name fehlt oder ist ungültig"
    roh = _property(stueck, "sources")
    if roh is not None:
        fehler = _sources_error(roh)
        if fehler:
            return fehler
    if roh is None or "downloadUrl" in stueck:
        fehler = _git_ref_error(stueck.get("downloadUrl"))
        if fehler:
            return fehler
    fehler = _dock_card_error(_property(stueck, "dock_card"))
    if fehler:
        return fehler
    if not NAME.match(app_name(stueck)):
        return "app_name fehlt oder ist ungültig"
    return None


# ── Catalog v2: sources and dock card (app_delivery_plan.md step 3) ──
#
# A catalog item points at one or more sources; the node picks the first
# kind it has a source adapter for, in the order of the node setting
# `source_order` (plan 2.2). In the item (schema.org PropertyValue, the
# open standard the catalog already uses):
#     {"name": "sources", "value": ["zentrale-package:https://…/budget",
#                                   "git:ssh://git@github.com/x/budgeter.git"]}
# One source = "<kind>:<ref>" (the kind before the first colon). The old
# `downloadUrl` is read as one more `git` source, after the listed ones.
#     {"name": "dock_card", "value": {"start": "…", "ansichten": […], …}}
# Dock card = what ZENTRALE needs to treat a program as an app (start,
# ports, data locations) — the keys of an app.toml. Optional: our apps
# carry it as their app.toml, a foreign program gets it from the catalog.

SOURCE_ORDER = "source_order"
DEFAULT_SOURCE_ORDER = ("zentrale-package", "flatpak", "packagekit", "git")
DOCK_CARD_STRINGS = ("start", "adresse", "titel", "version", "icon")
DOCK_CARD_LISTS = ("ansichten", "liefert", "rechte")


def _property(stueck, name):
    for p in stueck.get("additionalProperty") or []:
        if isinstance(p, dict) and p.get("name") == name:
            return p.get("value")
    return None


def _split_source(text):
    kind, _, ref = str(text).partition(":")
    return kind, ref


def _sources_error(roh):
    if not isinstance(roh, list) or not roh:
        return "sources ist keine liste von quellen"
    for q in roh:
        if not isinstance(q, str):
            return "sources: %r ist kein text" % (q,)
        kind, ref = _split_source(q)
        if not KIND.match(kind) or not ref.strip() or len(ref) > 512:
            return "sources: %r ist nicht <art>:<ort>" % q
        if kind == "git":
            fehler = _git_ref_error(ref)
            if fehler:
                return "sources: " + fehler.replace("downloadUrl", "git-quelle")
    return None


def _dock_card_error(card):
    if card is None:
        return None
    if not isinstance(card, dict):
        return "dock_card ist kein objekt"
    for k in DOCK_CARD_STRINGS:
        if k in card and not isinstance(card[k], str):
            return "dock_card: %s ist kein text" % k
    for k in DOCK_CARD_LISTS:
        if k in card and not (isinstance(card[k], list) and all(isinstance(x, str) for x in card[k])):
            return "dock_card: %s ist keine liste von texten" % k
    return None


def sources(stueck) -> list:
    """Every source of a catalog item, as listed: [{"kind", "ref"}]; the
    old `downloadUrl` last as `git` (once). Built-ins have none."""
    if built_in(stueck):
        return []
    raus = []
    for q in _property(stueck, "sources") or []:
        if isinstance(q, str):
            kind, ref = _split_source(q)
            raus.append({"kind": kind, "ref": ref})
    url = stueck.get("downloadUrl")
    if isinstance(url, str) and {"kind": "git", "ref": url} not in raus:
        raus.append({"kind": "git", "ref": url})
    return raus


def dock_card(stueck):
    """The item's dock card (dict) or None."""
    card = _property(stueck, "dock_card")
    return dict(card) if isinstance(card, dict) else None


def source_order() -> list:
    """Node setting `source_order`: kinds in preference order (a list, or a
    comma-separated text from the environment). Kinds not named keep the
    default order after the named ones."""
    roh = ai_config.setting(SOURCE_ORDER)
    if isinstance(roh, str):
        roh = [x.strip() for x in roh.split(",")]
    eigen = [k for k in (roh if isinstance(roh, list) else []) if isinstance(k, str) and KIND.match(k)]
    return list(dict.fromkeys([*eigen, *DEFAULT_SOURCE_ORDER]))


def pick_source(stueck, kinds):
    """The source this node uses for an item: among the item's sources whose
    kind is in `kinds` (the kinds this node has an adapter for), the one
    whose kind comes first in `source_order()`; kinds the order does not
    name come after, in catalog order. → {"kind", "ref"} or None."""
    usable = [q for q in sources(stueck) if q["kind"] in set(kinds)]
    order = source_order()
    rang = {k: i for i, k in enumerate(order)}
    usable.sort(key=lambda q: rang.get(q["kind"], len(order)))   # stable: catalog order
    return usable[0] if usable else None


# ── Holds (building kit step 12) ─────────────────────────────────────
#
# "Hold at this version" for an extracted app (own repository, installed
# from the store): `zentrale update --automatic` leaves it as it is. Node
# setting `app_holds` (data/ai_config.json, never synced — what is installed
# where is per node): {name: {"version": app.toml version, "commit": sha,
# "since": iso}}. Built-in apps are never held: they ship with the core,
# which updates by its own setting (building_kit_plan.md 3.2).

HOLDS = "app_holds"


def holds() -> dict:
    d = ai_config.setting(HOLDS)
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items() if NAME.match(str(k)) and isinstance(v, dict)}


def held(name) -> bool:
    return name in holds()


def set_hold(name, on, version="", commit="") -> dict:
    """Hold or release one app. → the holds after the change."""
    from datetime import datetime
    h = holds()
    if on:
        h[name] = {"version": str(version or ""), "commit": str(commit or ""),
                   "since": datetime.now().astimezone().isoformat(timespec="seconds")}
    else:
        h.pop(name, None)
    ai_config.set_override(HOLDS, h, persist=True)
    return h
