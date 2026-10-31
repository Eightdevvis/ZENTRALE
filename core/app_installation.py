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
# Wo Apps wohnen und was installiert ist (Register je Rechner):
# core/app_register.py. Liegt am Platz bereits ein Checkout desselben Repos
# (Sasha entwickelt die App), wird er übernommen statt doppelt geholt.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md). Nur Standardbibliothek
# und git; der Katalog kommt aus core/shop.py.

import os
import re
import shutil
import subprocess
import threading
import tomllib
import urllib.parse
from datetime import datetime

import account_ownership
import app_register as reg
import app_update
import apps
import builtin_store_apps as builtin
import konto
import shop

_LOCK = threading.Lock()
LADEN = ".laden"                    # Zwischenlager in <app_ordner>
GIT_WARTEZEIT = 300                 # ein großes Repo über langsames Netz


class InstallFehler(ValueError):
    """`code` = HTTP-Status der Route."""

    def __init__(self, text, code=400):
        super().__init__(text)
        self.code = code


alle, namen, eintrag, app_ordner = reg.alle, reg.namen, reg.eintrag, reg.app_ordner


def _save(eintraege):
    """reg.schreiben; a register from a newer ZENTRALE is never overwritten."""
    import formats
    try:
        reg.schreiben(eintraege)
    except formats.NewerFormat:
        raise InstallFehler("the app list on this device was written by a newer "
                            "ZENTRALE — update first", 409)


# ── Katalog → Quelle ─────────────────────────────────────────────────

_app_name, _ordner_name = reg.app_name, reg.ordner_name


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

# Source kinds this node can install today: only `git` (clone/pull). The
# source-adapter frame (app_delivery_plan.md step 2) replaces this list.
KINDS = ("git",)


def _orte(stueck):
    q = reg.pick_source(stueck, KINDS)
    if q is None:
        raise InstallFehler("this device has no installer yet for: %s"
                            % ", ".join(sorted({x["kind"] for x in reg.sources(stueck)})), 501)
    url = q["ref"]
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
    if name in apps.BEKANNT or name in apps.eigene_namen():
        raise InstallFehler("„%s\" gibt es schon als feste oder selbst gebaute app" % name, 409)
    if not _ansichten(m):
        raise InstallFehler("app.toml nennt keine ansichten", 422)
    return name


def _wahl_antwort(stueck, ordner, m, neu) -> dict:
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
    if reg.built_in(s):
        return _builtin_answer(s, False)
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
    ordner, adresse, neu}. `neu` = vorher nicht installiert.
    A built-in app (step 10) needs no views: it is switched on here."""
    s = _stueck(adresse)
    if reg.built_in(s):
        name = reg.app_name(s)
        try:
            r = builtin.install(name)
        except builtin.BuiltinError as e:
            raise InstallFehler(str(e), e.code)
        shop.holen(s["@id"])
        mark_owned(s["@id"])
        return _builtin_answer(s, r["new"], choice=False)
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
        rest = [e for e in reg.lesen() if e["name"] != name]
        rest.append({"name": name, "quelle": s["@id"], "ordner": ziel, "ansichten": gewaehlt,
                     "am": (alt or {}).get("am")
                     or datetime.now().astimezone().isoformat(timespec="seconds"),
                     "source": {"kind": "git", "ref": url},
                     "version": str(m.get("version") or ""),
                     "data": (alt or {}).get("data") or {}})
        _save(rest)
    shop.holen(s["@id"])                          # installiert heißt auch: geholt
    mark_owned(s["@id"])
    return {"name": name, "titel": str(m.get("titel") or name), "ansichten": gewaehlt,
            "ordner": ziel, "adresse": s["@id"], "neu": alt is None}


# ── Built-in apps, removing, ownership (building kit step 10) ────────

def _builtin_answer(s, new, choice=True) -> dict:
    """The answer of laden (choice: AppWahl) or installieren for a built-in
    app: no views to pick, no folder."""
    name = reg.app_name(s)
    d = {"adresse": s["@id"], "name": name, "titel": str(s.get("name") or name),
         "ansichten": [], "neu": new, "built_in": True}
    if choice:
        d.update(version="", gewaehlt=[], installiert=builtin.installed(name))
    else:
        d["ordner"] = ""
    return d


def mark_owned(adr) -> bool:
    """Installed with an account = owned by the account (/v1/besitz,
    core/account_ownership.py). Best effort: offline or logged out → False,
    the local "geholt" (core/shop.py) still holds."""
    if not konto.angemeldet():
        return False
    try:
        account_ownership.mark([adr])
        return True
    except account_ownership.OwnershipError:
        return False


def entfernen(adresse) -> dict:
    """Remove an app from THIS node; ownership and data stay. Today only
    built-in apps — downloaded ones: memory/open/store_app_lifecycle.md.
    → {adresse, name, installiert: False, war: bool}."""
    s = _stueck(adresse)
    if not reg.built_in(s):
        raise InstallFehler("removing downloaded apps is not built yet", 501)
    r = builtin.remove(reg.app_name(s))
    return {"adresse": s["@id"], "name": r["name"], "installiert": False, "war": r["was"]}


def hold(adresse, on) -> dict:
    """Hold an extracted app at its current version on THIS node (building kit
    step 12): `zentrale update --automatic` skips it until released.
    → {adresse, name, held, version}. Built-in apps follow the core → 400."""
    s = _stueck(adresse)
    if reg.built_in(s):
        raise InstallFehler("built-in apps update with the core, they cannot be held", 400)
    name = reg.app_name(s)
    e = eintrag(name)
    if e is None:
        raise InstallFehler("not installed on this device", 409)
    version = ""
    try:
        version = str(_manifest(e["ordner"]).get("version") or "")
    except InstallFehler:
        pass
    reg.set_hold(name, bool(on), version, app_update.head(e["ordner"]) if on else "")
    return {"adresse": s["@id"], "name": name, "held": bool(on), "version": version}


def held_addresses() -> dict:
    """{shop address: hold} for the held apps installed on this node."""
    h = reg.holds()
    return {e["quelle"]: h[e["name"]] for e in reg.lesen()
            if e["name"] in h and isinstance(e.get("quelle"), str)}


def installed_addresses() -> list:
    """Shop addresses of every app installed on THIS node: built-in ones by
    their setting, downloaded ones from the register."""
    raus = [builtin.address(n) for n in builtin.installed_names()]
    raus += [e["quelle"] for e in reg.lesen() if isinstance(e.get("quelle"), str)]
    return sorted(set(raus))


# ── Plug dialog (building kit step 11, core/plugs.py) ─────────────────

def plug(name, choices) -> dict:
    """Plug in what the person chose for an installed app ({need id:
    provider port | None}) through the one gate (core/plugs.confirm). A
    required socket (min ≥ 1) still without a live wire afterwards means the
    install does not count: a store app is withdrawn from this node's register
    (its folder stays — installing again only plugs). Without that, the
    node's whole wiring would no longer compile. → plugs.confirm's answer
    plus `withdrawn`."""
    import plugs
    if not plugs.known(name):
        raise InstallFehler("„%s\" is not installed here" % name, 404)
    r = plugs.confirm(name, choices if isinstance(choices, dict) else {})
    r["withdrawn"] = False
    if r["unmet"] and eintrag(name) is not None:
        withdraw(name)
        r["withdrawn"] = True
    return r


def withdraw(name) -> bool:
    """Take an app out of this node's register (the folder stays). → True
    when it was there."""
    with _LOCK:
        rest = [e for e in reg.lesen() if e["name"] != name]
        if len(rest) == len(reg.lesen()):
            return False
        _save(rest)
    return True
