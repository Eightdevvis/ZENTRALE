# core/apps.py
#
# Die installierten Apps des Hubs — wo sie liegen und was ihr Manifest sagt.
#
# Seit 2026-10-09 (memory/hub/hub_bauplan.md, Schritt 1): der Sprach-Tutor
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
# Aus dem Schaufenster installierte Apps (2026-10-25, core/app_installation.py):
# ihr Ordner und die gewählten Ansichten stehen je Rechner im Register;
# gefunden werden sie wie die aus BEKANNT, nur ohne feste Zeile hier.
#
# Selbst gebaute Apps (2026-10-10, Werkstatt, memory/hub/werkstatt.md):
# ein Ordner mit derselben app.toml unter `apps_ordner` (Standard data/apps/,
# abgeglichen), aber ohne `start` — sie sind kein Prozess, sondern eine
# Vorlage (`vorlage = "desk"`) mit Inhalt. Gefunden werden sie hier durch
# Nachsehen im Ordner, nicht über BEKANNT: Sasha baut sie selbst, ohne Code.

import os
import tomllib

import ai_config
import app_installation
import app_prozess

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# name → Ordnername neben ZENTRALE (Standard, wenn app_pfad_<name> fehlt)
BEKANNT = {"tutor": "language-tutor",
           "karte": "zentrale-karte"}       # seit 2026-10-22 (Weltkarte)


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
    if name not in BEKANNT:
        e = app_installation.eintrag(name)
        if e is not None:
            return os.path.abspath(e["ordner"])
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


def aus_dem_laden() -> list:
    """Manifeste der aus dem Schaufenster installierten Apps, je mit
    `_installiert` (der Eintrag im Register: quelle, gewählte ansichten)."""
    raus = []
    for e in app_installation.alle():
        if e["name"] in BEKANNT:
            continue
        m = manifest(e["name"])
        if m and m.get("name") == e["name"]:
            m["_installiert"] = e
            raus.append(m)
    return raus


def installiert() -> list:
    """Manifeste aller gefundenen Apps: Prozess-Apps aus BEKANNT, dann die
    aus dem Laden, dann die selbst gebauten."""
    return [m for m in (manifest(n) for n in BEKANNT) if m] + aus_dem_laden() + eigene()


# Ansichten einer App (hub_bauplan.md „Ansichten"): terminal und fenster seit
# 2026-10-09, browser seit 2026-10-25 (die App hat eine Web-Oberfläche unter
# ihrer `adresse`). Unbekannte Namen zeigt die Oberfläche, wie sie heißen.
ANSICHT_TITEL = {"browser": "im browser", "terminal": "im terminal", "fenster": "als fenster"}


def ansicht_titel(ansicht: str) -> str:
    return ANSICHT_TITEL.get(ansicht, ansicht)


def ansichten_installiert(m: dict) -> list:
    """Die Ansichten, die auf diesem Rechner eingerichtet sind: bei Apps aus
    dem Laden die gewählten, sonst alle aus dem Manifest. Je
    {id, titel, url (browser) | start (bool)}."""
    angebot = [str(a) for a in (m.get("ansichten") or [])]
    gewaehlt = (m.get("_installiert") or {}).get("ansichten")
    namen = [a for a in angebot if gewaehlt is None or a in gewaehlt]
    raus = []
    for a in namen:
        teil = (m.get("ansicht") or {}).get(a) or {}
        d = {"id": a, "titel": ansicht_titel(a)}
        if a == "browser":
            if not m.get("adresse"):
                continue
            d["url"] = str(m["adresse"]).rstrip("/") + "/" + str(teil.get("pfad") or "").lstrip("/")
        else:
            d["start"] = bool(teil.get("start"))
        raus.append(d)
    return raus


def icon(ordner: str, m: dict):
    """Das Symbol einer App fürs Rad: {"art": "bild", "raster"} aus `icon`
    (PNG neben app.toml, quadratisch, bis 32×32 in voller Größe) oder
    {"art": "motiv", "motiv"} aus `icon_motiv` — sonst None (das Rad zeigt
    den Namen)."""
    if m.get("icon"):
        datei = os.path.join(ordner, os.path.basename(str(m["icon"])))
        try:
            import bild_vorschau                  # Pillow, nur wo das Backend wohnt
            return {"art": "bild", "raster": bild_vorschau.icon_raster(datei, None)}
        except Exception:
            return None
    if m.get("icon_motiv"):
        return {"art": "motiv", "motiv": str(m["icon_motiv"])}
    return None


def abonnenten(ereignis: str) -> list:
    """Apps, die dieses Ereignis abonniert haben (Recht „ereignis:<name>")."""
    return [m for m in installiert()
            if f"ereignis:{ereignis}" in (m.get("rechte") or [])]


def python_fuer(m: dict) -> str:
    """Der Python der App: ihr eigenes venv, sonst das von ZENTRALE."""
    return app_prozess.python_fuer(m["_pfad"], _ROOT)


def befehl(m: dict, start: str) -> list:
    """Ein Start-Befehl aus dem Manifest („python …") als Liste, mit dem
    Python der App."""
    return app_prozess.befehl(m["_pfad"], start, _ROOT)


def ist_prozess(m: dict) -> bool:
    """Eine Prozess-App (eigener Server: `start` + `adresse`) — im Gegensatz
    zu einer selbst gebauten Vorlage-App."""
    return bool(m.get("start")) and bool(m.get("adresse"))


def routen(m: dict) -> list:
    """Pfad-Anfänge, die der Hub an diese App weiterreicht (`routen` im
    Manifest, z. B. ["/api/map"]). Nur Prozess-Apps; ungültige Einträge
    (kein führendes /, Leerzeichen, ..) fallen still weg."""
    if not ist_prozess(m):
        return []
    raus = []
    for r in m.get("routen") or []:
        r = str(r).rstrip("/")
        if r.startswith("/") and len(r) > 1 and " " not in r and ".." not in r:
            raus.append(r)
    return raus


def kachel_arten(m: dict) -> list:
    """Kachel-Arten, die die App liefert (`liefert = ["kachel:<art>"]`)."""
    if not ist_prozess(m):
        return []
    return [str(x)[len("kachel:"):] for x in (m.get("liefert") or [])
            if str(x).startswith("kachel:") and len(str(x)) > len("kachel:")]


def daten(m: dict):
    """`[daten]` aus dem Manifest (memory/hub/cloud_app.md): welche Dateien die
    App hat und ob sie abgeglichen werden dürfen →
    {"muster": [...], "abgleichen": bool} oder None (kein `[daten]`).

    Muster sind relativ zum ZENTRALE-Ordner (der Namensraum der Positivliste
    core/abgleich_auswahl.py). Was nach außen zeigt (absolut, `..`, `\\`,
    leer), fällt hier still weg; was übrig bleibt, gleicht der Abgleich
    trotzdem nur ab, wenn es auch auf der Positivliste steht."""
    d = m.get("daten")
    if not isinstance(d, dict):
        return None
    muster = []
    for x in d.get("muster") or []:
        x = str(x).strip()
        if x and not x.startswith(("/", "~")) and "\\" not in x \
                and ".." not in x.split("/") and x not in muster:
            muster.append(x)
    return {"muster": muster, "abgleichen": d.get("abgleichen") is True}
