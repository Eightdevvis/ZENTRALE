# core/apps.py
#
# Die installierten Apps des Hubs — wo sie liegen und was ihr Manifest sagt.
#
# Seit 2026-10-09 (memory/system/hub_bauplan.md, Schritt 1): der Sprach-Tutor
# ist die erste App. Er wohnt in einem eigenen Repo neben ZENTRALE, läuft als
# eigener Prozess und sagt in seiner app.toml, was er will (start, adresse,
# ansichten, rechte). ZENTRALE importiert keinen Code einer App — es liest nur
# ihr Manifest, startet sie und schickt ihr Ereignisse (core/hub_ereignisse.py).
#
# Wo eine App liegt: Einstellung app_pfad_<name> (Env ZENTRALE_APP_PFAD_<NAME>),
# Standard: ein Ordner gleichen Namens neben diesem Repo (für den Tutor
# ../language-tutor). Mehr Apps = eine Zeile in BEKANNT; eine echte
# App-Verwaltung (installieren, Rechte fragen) kommt erst mit Schritt 2.

import os
import tomllib

import ai_config

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# name → Ordnername neben ZENTRALE (Standard, wenn app_pfad_<name> fehlt)
BEKANNT = {"tutor": "language-tutor"}


def pfad(name: str) -> str:
    """Ordner der App (auch wenn er fehlt)."""
    gesetzt = ai_config.setting("app_pfad_" + name)
    if gesetzt:
        return os.path.abspath(os.path.expanduser(str(gesetzt)))
    return os.path.abspath(os.path.join(_ROOT, "..", BEKANNT.get(name, name)))


def manifest(name: str):
    """Das Manifest der App als dict — oder None, wenn sie nicht installiert
    ist oder ihr app.toml kaputt ist (dann mit Zeile im Log)."""
    datei = os.path.join(pfad(name), "app.toml")
    try:
        with open(datei, "rb") as f:
            m = tomllib.load(f)
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"[apps] {datei} nicht lesbar: {e}", flush=True)
        return None
    m["_pfad"] = pfad(name)
    return m


def installiert() -> list:
    """Manifeste aller gefundenen Apps."""
    return [m for m in (manifest(n) for n in BEKANNT) if m]


def abonnenten(ereignis: str) -> list:
    """Apps, die dieses Ereignis abonniert haben (Recht „ereignis:<name>")."""
    return [m for m in installiert()
            if f"ereignis:{ereignis}" in (m.get("rechte") or [])]


def python_fuer(m: dict) -> str:
    """Der Python der App: ihr eigenes venv, sonst das von ZENTRALE."""
    for ordner in (m["_pfad"], _ROOT):
        for name in ("venv", ".venv"):
            kandidat = os.path.join(ordner, name, "bin", "python")
            if os.path.exists(kandidat):
                return kandidat
    import sys
    return sys.executable


def befehl(m: dict, start: str) -> list:
    """Ein Start-Befehl aus dem Manifest („python …") als Liste, mit dem
    Python der App."""
    teile = str(start).split()
    if teile and teile[0] == "python":
        teile[0] = python_fuer(m)
    return teile
