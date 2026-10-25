# core/app_installation.py
#
# Apps aus dem Schaufenster installieren (2026-10-25, memory/hub/shop.md
# „Apps installieren"). Bis dahin konnte der Laden nur „holen" (Besitz
# merken); Prozess-Apps standen fest in apps.BEKANNT. Jetzt:
#
#   laden(adresse)                 POST /api/apps/laden
#       Stück aus dem Katalog (Kategorie apps, schema.org SoftwareApplication)
#       → sein `downloadUrl` (ein git-Repo) wird nach <app_ordner>/.laden/
#       geholt, sein app.toml gelesen. Antwort: welche Ansichten die App hat
#       — die Auswahl, die Sasha VOR dem Einrichten trifft.
#   installieren(adresse, ansichten)   POST /api/apps/installieren
#       Nur die gewählten Ansichten (mindestens eine) werden gemerkt; der
#       Ordner zieht an seinen Platz <app_ordner>/<repo>, das Stück ist
#       geholt (shop.holen). Nochmal aufrufen ändert nur die Auswahl.
#
# Wo Apps wohnen: Einstellung `app_ordner` (Env ZENTRALE_APP_ORDNER),
# Standard der Ordner, in dem ZENTRALE liegt — dort stehen schon Tutor und
# Karte. Liegt dort bereits ein Checkout desselben Repos (Sasha entwickelt die
# App), wird er übernommen statt doppelt geholt.
#
# Was installiert ist, steht je Rechner in
# <installiert_ordner>/apps-<rechner>.json (Standard data/hub/, nie
# abgeglichen: der Code liegt nur auf DIESEM Rechner, und auf einem anderen
# will Sasha vielleicht andere Ansichten). Form (JSON):
#     {"apps": [{"name": "budget", "quelle": "zentrale://shop/apps/budget",
#                "ordner": "/home/…/budgeter", "ansichten": ["browser"],
#                "am": "2026-10-25T12:00:00+02:00"}]}
# Name, Titel, Ansichten-Angebot liest der Hub immer frisch aus dem app.toml
# im Ordner — hier steht nur, was Sasha gewählt hat (dasselbe Objekt, nicht
# kopiert).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md). Nur Standardbibliothek
# und git; der Katalog kommt aus core/shop.py.

import json
import os
import re
import shutil
import subprocess
import threading
import tomllib
import urllib.parse
from datetime import datetime

import ai_config
import dateien

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_LOCK = threading.Lock()
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_ORDNER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SCHEMATA = ("https", "ssh", "file")
LADEN = ".laden"                    # Zwischenlager in <app_ordner>
GIT_WARTEZEIT = 300                 # ein großes Repo über langsames Netz


class InstallFehler(ValueError):
    """`code` = HTTP-Status der Route."""

    def __init__(self, text, code=400):
        super().__init__(text)
        self.code = code


# ── Orte ──────────────────────────────────────────────────────────────

def app_ordner() -> str:
    eigen = ai_config.setting("app_ordner")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.dirname(_ROOT)


def _register_datei() -> str:
    eigen = ai_config.setting("installiert_ordner")
    basis = (os.path.abspath(os.path.expanduser(str(eigen))) if eigen
             else os.path.join(_ROOT, "data", "hub"))
    return os.path.join(basis, "apps-%s.json" % dateien.knoten())


# ── Was installiert ist ──────────────────────────────────────────────

def _lesen() -> list:
    try:
        with open(_register_datei(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    raus = []
    for e in (d.get("apps") if isinstance(d, dict) else None) or []:
        if (isinstance(e, dict) and _NAME.match(str(e.get("name") or ""))
                and isinstance(e.get("ordner"), str) and isinstance(e.get("ansichten"), list)):
            raus.append(e)
    return raus


def _schreiben(eintraege) -> None:
    dateien.json_schreiben(_register_datei(), {"apps": sorted(eintraege, key=lambda e: e["name"])})


def alle() -> list:
    """Alle aus dem Laden installierten Apps dieses Rechners (Einträge wie
    in der Datei), nach Name."""
    return sorted(_lesen(), key=lambda e: e["name"])


def namen() -> list:
    return [e["name"] for e in alle()]


def eintrag(name):
    for e in _lesen():
        if e["name"] == name:
            return e
    return None


# ── Katalog → Quelle ─────────────────────────────────────────────────

def _app_name(stueck) -> str:
    for p in stueck.get("additionalProperty") or []:
        if isinstance(p, dict) and p.get("name") == "app_name":
            return str(p.get("value") or "")
    return ""


def quelle_pruefen(stueck) -> None:
    """Ein Stück der Kategorie apps muss sagen, woher es kommt
    (`downloadUrl`, ein git-Repo über https/ssh/file) und wie die App heißt
    (additionalProperty `app_name`). shop.pruefen ruft das für jedes Stück
    der Kategorie — ein Laden mit unholbarer App ist kaputt."""
    url = stueck.get("downloadUrl")
    teile = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    if teile is None or teile.scheme not in SCHEMATA or not teile.path.strip("/"):
        raise InstallFehler("downloadUrl fehlt oder ist kein git-repo (https, ssh, file)", 503)
    if not _ORDNER_NAME.match(_ordner_name(url)):
        raise InstallFehler("downloadUrl endet nicht auf einen ordnernamen", 503)
    if not _NAME.match(_app_name(stueck)):
        raise InstallFehler("app_name fehlt oder ist ungültig", 503)


def _ordner_name(url) -> str:
    """ssh://git@github.com/x/budgeter.git → budgeter"""
    n = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return n[:-4] if n.endswith(".git") else n


def _repo_schluessel(url) -> str:
    """Dasselbe Repo, egal wie geschrieben: git@host:x/y.git,
    ssh://git@host/x/y, https://host/x/y.git → host/x/y (klein)."""
    url = str(url or "").strip()
    m = re.match(r"^[\w.-]+@([\w.-]+):(.+)$", url)         # scp-Form von git
    if m:
        host, pfad = m.group(1), m.group(2)
    else:
        t = urllib.parse.urlsplit(url)
        host, pfad = (t.hostname or ""), t.path
    pfad = pfad.strip("/")
    if pfad.endswith(".git"):
        pfad = pfad[:-4]
    return ("%s/%s" % (host, pfad)).lower()


def _stueck(adresse):
    import shop                              # Katalog (Schicht 2 nebenan)
    try:
        kategorie, kennung = shop._aus_adresse(adresse)
        s = shop.stueck(kategorie, kennung)
    except shop.ShopFehler as e:
        raise InstallFehler(str(e), e.code)
    if kategorie != "apps":
        raise InstallFehler("das ist keine app — installieren geht nur mit apps")
    if not shop._preis_null(s):
        raise InstallFehler("kostet etwas — bezahlen geht noch nicht", 402)
    return s


# ── git ───────────────────────────────────────────────────────────────

def _git(*args, cwd=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0",
               GIT_SSH_COMMAND=os.environ.get("GIT_SSH_COMMAND") or "ssh -o BatchMode=yes")
    try:
        return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=GIT_WARTEZEIT)
    except FileNotFoundError:
        raise InstallFehler("git fehlt auf diesem rechner", 503)
    except subprocess.TimeoutExpired:
        raise InstallFehler("herunterladen dauert zu lange — netz da?", 504)


def _herkunft(ordner):
    r = _git("remote", "get-url", "origin", cwd=ordner)
    return r.stdout.strip() if r.returncode == 0 else ""


def _manifest(ordner) -> dict:
    try:
        with open(os.path.join(ordner, "app.toml"), "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise InstallFehler("die app hat kein app.toml — so kann der hub sie nicht einrichten", 422)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise InstallFehler("app.toml nicht lesbar: %s" % e, 422)


def _ansichten(m) -> list:
    return [str(a) for a in (m.get("ansichten") or []) if isinstance(a, str) and a]


# ── Laden und installieren ───────────────────────────────────────────

def _orte(stueck):
    url = stueck["downloadUrl"]
    name = _ordner_name(url)
    return url, os.path.join(app_ordner(), name), os.path.join(app_ordner(), LADEN, name)


def _vorhanden(url, ziel):
    """Liegt am Ziel schon dieses Repo? → True; ein fremder Ordner → Fehler."""
    if not os.path.exists(ziel):
        return False
    if os.path.isfile(os.path.join(ziel, "app.toml")) and \
            _repo_schluessel(_herkunft(ziel)) == _repo_schluessel(url):
        return True
    raise InstallFehler("„%s\" gibt es schon und ist etwas anderes — "
                        "bitte erst wegräumen" % ziel, 409)


def _pruefen(stueck, m) -> str:
    name = str(m.get("name") or "")
    if name != _app_name(stueck):
        raise InstallFehler("app.toml heißt „%s\", der laden sagt „%s\""
                            % (name, _app_name(stueck)), 422)
    import apps
    if name in apps.BEKANNT or name in apps.eigene_namen():
        raise InstallFehler("„%s\" gibt es schon als feste oder selbst gebaute app" % name, 409)
    if not _ansichten(m):
        raise InstallFehler("app.toml nennt keine ansichten", 422)
    return name


def _wahl_antwort(stueck, ordner, m, neu) -> dict:
    import apps
    name = str(m["name"])
    e = eintrag(name)
    angebot = _ansichten(m)
    gewaehlt = [a for a in (e or {}).get("ansichten", []) if a in angebot] or list(angebot)
    return {"adresse": stueck["@id"], "name": name,
            "titel": str(m.get("titel") or name), "version": str(m.get("version") or ""),
            "ansichten": [{"id": a, "titel": apps.ansicht_titel(a)} for a in angebot],
            "gewaehlt": gewaehlt, "installiert": e is not None, "neu": neu}


def laden(adresse) -> dict:
    """Die App holen (noch nicht einrichten) und sagen, welche Ansichten sie
    anbietet. → {adresse, name, titel, version, ansichten: [{id, titel}],
    gewaehlt, installiert, neu}. `neu` = gerade heruntergeladen (sonst lag
    sie schon da)."""
    s = _stueck(adresse)
    url, ziel, lager = _orte(s)
    with _LOCK:
        if _vorhanden(url, ziel):
            m = _manifest(ziel)
            _pruefen(s, m)
            return _wahl_antwort(s, ziel, m, False)
        if os.path.isdir(lager):
            shutil.rmtree(lager)                  # alter halber Versuch
        os.makedirs(os.path.dirname(lager), exist_ok=True)
        r = _git("clone", "--quiet", url, lager)
        if r.returncode != 0:
            shutil.rmtree(lager, ignore_errors=True)
            grund = (r.stderr.strip().splitlines() or ["unbekannt"])[-1]
            raise InstallFehler("herunterladen ging nicht: %s" % grund, 502)
        try:
            m = _manifest(lager)
            _pruefen(s, m)
        except InstallFehler:
            shutil.rmtree(lager, ignore_errors=True)
            raise
        return _wahl_antwort(s, lager, m, True)


def installieren(adresse, ansichten) -> dict:
    """Mit den gewählten Ansichten einrichten (mindestens eine aus dem
    app.toml). Lädt vorher, falls nötig. → {name, titel, ansichten,
    ordner, adresse, neu}. `neu` = vorher nicht installiert."""
    if not isinstance(ansichten, list) or not ansichten \
            or not all(isinstance(a, str) for a in ansichten):
        raise InstallFehler("welche ansichten? (mindestens eine)")
    s = _stueck(adresse)
    url, ziel, lager = _orte(s)
    if not _vorhanden(url, ziel) and not os.path.isfile(os.path.join(lager, "app.toml")):
        laden(adresse)
    with _LOCK:
        if not _vorhanden(url, ziel):
            m = _manifest(lager)
            _pruefen(s, m)
            os.replace(lager, ziel)
        m = _manifest(ziel)
        name = _pruefen(s, m)
        angebot = _ansichten(m)
        falsch = [a for a in ansichten if a not in angebot]
        if falsch:
            raise InstallFehler("diese ansicht hat die app nicht: %s" % ", ".join(falsch))
        gewaehlt = [a for a in angebot if a in ansichten]      # Reihenfolge der App
        alt = eintrag(name)
        rest = [e for e in _lesen() if e["name"] != name]
        rest.append({"name": name, "quelle": s["@id"], "ordner": ziel, "ansichten": gewaehlt,
                     "am": (alt or {}).get("am")
                     or datetime.now().astimezone().isoformat(timespec="seconds")})
        _schreiben(rest)
    import shop
    shop.holen(s["@id"])                          # installiert heißt auch: geholt
    return {"name": name, "titel": str(m.get("titel") or name), "ansichten": gewaehlt,
            "ordner": ziel, "adresse": s["@id"], "neu": alt is None}
