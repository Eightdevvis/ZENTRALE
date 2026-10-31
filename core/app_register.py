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


def quelle_fehler(stueck):
    """Ein Stück der Kategorie apps muss sagen, woher es kommt
    (`downloadUrl`, ein git-Repo über https/ssh/file) und wie die App heißt
    (`app_name`). → None oder ein Satz, was fehlt (shop.pruefen macht daraus
    einen kaputten Katalog).
    A built-in app (`built_in` true, still inside the core package — building
    kit step 10) has no `downloadUrl`; it only needs its `app_name`."""
    if built_in(stueck):
        return None if NAME.match(app_name(stueck)) else "app_name fehlt oder ist ungültig"
    url = stueck.get("downloadUrl")
    teile = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    if teile is None or teile.scheme not in SCHEMATA or not teile.path.strip("/"):
        return "downloadUrl fehlt oder ist kein git-repo (https, ssh, file)"
    if not ORDNER_NAME.match(ordner_name(url)):
        return "downloadUrl endet nicht auf einen ordnernamen"
    if not NAME.match(app_name(stueck)):
        return "app_name fehlt oder ist ungültig"
    return None


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
