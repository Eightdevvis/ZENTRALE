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
            raus.append(e)
    return raus


def schreiben(eintraege) -> None:
    dateien.json_schreiben(datei(), {"apps": sorted(eintraege, key=lambda e: e["name"])})


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
