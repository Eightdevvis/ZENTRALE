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
#
# Selbst gebaute Apps (2026-10-10, Werkstatt, memory/system/werkstatt.md):
# ein Ordner mit derselben app.toml unter `apps_ordner` (Standard data/apps/,
# abgeglichen), aber ohne `start` — sie sind kein Prozess, sondern eine
# Vorlage (`vorlage = "desk"`) mit Inhalt. Gefunden werden sie hier durch
# Nachsehen im Ordner, nicht über BEKANNT: Sasha baut sie selbst, ohne Code.

import os
import tomllib

import ai_config

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# name → Ordnername neben ZENTRALE (Standard, wenn app_pfad_<name> fehlt)
BEKANNT = {"tutor": "language-tutor"}


def eigene_ordner() -> str:
    """Wo die selbst gebauten Apps liegen (Einstellung apps_ordner)."""
    eigen = ai_config.setting("apps_ordner")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.join(_ROOT, "data", "apps")


def pfad(name: str) -> str:
    """Ordner der App (auch wenn er fehlt)."""
    gesetzt = ai_config.setting("app_pfad_" + name)
    if gesetzt:
        return os.path.abspath(os.path.expanduser(str(gesetzt)))
    if name not in BEKANNT and os.path.isfile(os.path.join(eigene_ordner(), name, "app.toml")):
        return os.path.join(eigene_ordner(), name)
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


def eigene_namen() -> list:
    """Ordnernamen (= Kurzname, slug) der selbst gebauten Apps, sortiert.
    Versteckte Ordner und Ordner ohne app.toml zählen nicht."""
    o = eigene_ordner()
    try:
        namen = os.listdir(o)
    except (FileNotFoundError, NotADirectoryError):
        return []
    return sorted(n for n in namen if not n.startswith((".", "_")) and n not in BEKANNT
                  and os.path.isfile(os.path.join(o, n, "app.toml")))


def eigene() -> list:
    """Manifeste der selbst gebauten Apps (mit `_slug`)."""
    raus = []
    for n in eigene_namen():
        m = manifest(n)
        if m:
            m["_slug"] = n
            raus.append(m)
    return raus


def installiert() -> list:
    """Manifeste aller gefundenen Apps: Prozess-Apps aus BEKANNT, dann die
    selbst gebauten."""
    return [m for m in (manifest(n) for n in BEKANNT) if m] + eigene()


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
