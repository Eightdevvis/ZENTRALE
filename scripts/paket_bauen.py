#!/usr/bin/env python3
"""Das Paket des installierbaren Hubs bauen (memory/betrieb/setup.md).

Liest die Positivliste deploy/paket.txt und schreibt
  dist/zentrale-<fassung>.tar.gz   (oberster Ordner zentrale-<fassung>/, darin VERSION)
  dist/neueste.json                {version, sha256, groesse} — so wie GET /v1/paket antwortet

Fassung: --fassung, sonst deploy/RELEASE, sonst das Datum (JJJJ.MM.TT).
Ins Paket kommen dazu VERSION und VERTEILUNG.json (woher `zentrale update`
holt — aus deploy/verteilung.toml, memory/betrieb/verteilung.md).
BUNDLE.json (building kit step 12, memory/hub/building_kit_plan.md 3.2/3.3):
the components of this release as a schema.org ItemList — `core` and every
built-in app at the release's version, the extracted apps (own repositories)
without a version: they follow their repository unless a node holds them.

Die EINE Stelle, die entscheidet, was ausgeliefert wird: .deb (deb_bauen.py)
und PKGBUILD (arch_bauen.py) nehmen genau dieses tar.gz.
Verweigert alles, was nie ins Paket darf (data/, memory/, tests/, venv,
*.enc, ai_config.json, *.schluessel) — auch wenn es in der Liste stünde.
"""

import argparse
import ast
import datetime
import fnmatch
import hashlib
import io
import json
import os
import sys
import tarfile
import tomllib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LISTE = os.path.join(ROOT, "deploy", "paket.txt")

VERBOTEN_ORDNER = ("data/", "memory/", "tests/", "venv/", ".venv/", ".git/", ".claude/",
                   "dist/", "services/")
VERBOTEN_NAMEN = ("*.enc", "*.enc.bak", "ai_config.json", "*.schluessel", "*.pyc",
                  "*.key", "*.pem", ".env")
UEBERSPRINGEN = ("__pycache__",)


class PaketFehler(Exception):
    pass


# ── Der Schalter (deploy/verteilung.toml) ──────────────────────────────

VERTEILUNG_VORGABE = {
    "oeffentlich": False, "quelle": "github", "betreuer": "", "lizenz": "", "homepage": "",
    "quellen": {"cloud": {"neueste": "{cloud}/v1/paket",
                          "paket": "{cloud}/v1/paket/{version}.tar.gz"}},
}


def cloud_vorgabe(root=ROOT) -> str:
    """Die Cloud-Adresse aus ihrer einen Stelle (core/cloud_api.py, VORGABE)."""
    import re
    with open(os.path.join(root, "core", "cloud_api.py"), encoding="utf-8") as f:
        m = re.search(r'^VORGABE = "([^"]+)"', f.read(), re.M)
    if not m:
        raise PaketFehler("core/cloud_api.py: VORGABE nicht gefunden.")
    return m.group(1)


def verteilung_lesen(root=ROOT) -> dict:
    """deploy/verteilung.toml; fehlt sie, gilt: nicht öffentlich, Cloud mit Code."""
    cfg = json.loads(json.dumps(VERTEILUNG_VORGABE))
    try:
        with open(os.path.join(root, "deploy", "verteilung.toml"), "rb") as f:
            roh = tomllib.load(f)
    except FileNotFoundError:
        return cfg
    quellen = {**cfg["quellen"], **roh.get("quellen", {})}
    cfg.update(roh)
    cfg["quellen"] = quellen
    if not isinstance(cfg["oeffentlich"], bool):
        raise PaketFehler("deploy/verteilung.toml: oeffentlich muss true oder false sein.")
    if cfg["oeffentlich"] and cfg["quelle"] not in cfg["quellen"]:
        raise PaketFehler(f"deploy/verteilung.toml: unbekannte quelle '{cfg['quelle']}'.")
    return cfg


def quell_vorlagen(cfg, oeffentlich=None) -> dict:
    """→ {neueste, paket} mit den Laufzeit-Platzhaltern __CLOUD__ und __VERSION__.
    Nicht öffentlich: immer die Cloud (mit Einladungscode bzw. Konto)."""
    oeffentlich = cfg["oeffentlich"] if oeffentlich is None else oeffentlich
    q = cfg["quellen"][cfg["quelle"]] if oeffentlich else cfg["quellen"]["cloud"]
    raus = {}
    for k in ("neueste", "paket"):
        u = q[k].replace("{repo}", str(q.get("repo", "")))
        raus[k] = u.replace("{cloud}", "__CLOUD__").replace("{version}", "__VERSION__")
    return raus


def liste_lesen(pfad=LISTE):
    """→ [(quelle, ziel)] relativ zur Wurzel."""
    raus = []
    with open(pfad, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.split("#", 1)[0].strip()
            if not zeile:
                continue
            quelle, _, ziel = (t.strip() for t in zeile.partition("=>"))
            raus.append((quelle, ziel or quelle))
    return raus


def verboten(rel: str) -> bool:
    """Darf dieser Pfad (im Paket) nie hinein?"""
    teile = rel.replace(os.sep, "/").split("/")
    if teile[0] + "/" in VERBOTEN_ORDNER:
        return True
    if any(t in ("venv", ".venv", ".git", "__pycache__") for t in teile):
        return True
    return any(fnmatch.fnmatch(teile[-1], m) for m in VERBOTEN_NAMEN)


def _verfolgt(root, include_untracked=False):
    """Im git-Checkout nur, was eingecheckt ist (git ls-files) — liegengebliebene
    Probe- und Notizdateien bleiben draußen. Also: erst committen, dann bauen.
    include_untracked (only `zentrale dev`, devkit/workspace.py): also new files
    not committed yet, as long as git does not ignore them — the working tree
    as the developer sees it."""
    if not os.path.exists(os.path.join(root, ".git")):
        return None
    import subprocess
    extra = ["--others", "--exclude-standard"] if include_untracked else []
    r = subprocess.run(["git", "-C", root, "ls-files", "-z", "--cached", *extra], capture_output=True)
    if r.returncode != 0:
        return None
    return {os.path.join(root, p) for p in r.stdout.decode("utf-8", "replace").split("\0") if p}


def dateien(root=ROOT, liste=None, include_untracked=False):
    """→ sortierte [(quelle_abs, ziel_rel)]."""
    raus = {}
    bekannt = _verfolgt(root, include_untracked)
    for quelle, ziel in (liste if liste is not None else liste_lesen()):
        q = os.path.join(root, quelle.rstrip("/"))
        if not os.path.exists(q):
            raise PaketFehler(f"Steht in der Liste, fehlt aber: {quelle}")
        if os.path.isfile(q):
            paare = [(q, ziel.rstrip("/"))]
        else:
            paare = []
            for w, ds, fs in os.walk(q):
                ds[:] = sorted(d for d in ds if d not in UEBERSPRINGEN)
                for f in sorted(fs):
                    rel = os.path.relpath(os.path.join(w, f), q).replace(os.sep, "/")
                    paare.append((os.path.join(w, f), ziel.rstrip("/") + "/" + rel))
        for qa, z in paare:
            if os.path.islink(qa) or (bekannt is not None and qa not in bekannt):
                continue                 # keine Verweise im Paket (entpacken prüft sie nicht)
            if z.endswith(".pyc"):
                continue
            if verboten(z):
                raise PaketFehler(f"Darf nie ins Paket: {z}")
            raus[z] = qa
    return sorted((q, z) for z, q in raus.items())


def fassung_bestimmen(root=ROOT):
    try:
        with open(os.path.join(root, "deploy", "RELEASE"), encoding="utf-8") as f:
            r = f.read().strip()
        if r:
            return r
    except FileNotFoundError:
        pass
    return datetime.date.today().strftime("%Y.%m.%d")


# ── BUNDLE.json (building kit step 12) ─────────────────────────────────

def _literal(pfad, name):
    """A plain literal assigned at the top of a module (no import: the core
    modules want their settings)."""
    try:
        with open(pfad, encoding="utf-8") as f:
            baum = ast.parse(f.read())
    except (OSError, SyntaxError):
        return None
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign) and any(getattr(z, "id", None) == name for z in knoten.targets):
            return ast.literal_eval(knoten.value)
    return None


def _app(identifier, version=None, **mehr):
    d = {"@type": "SoftwareApplication", "identifier": identifier}
    if version is not None:
        d["softwareVersion"] = version
    d.update(mehr)
    return d


def bundle(fassung, root=ROOT) -> dict:
    """The bundle `everything@<fassung>`: core + built-in apps at this
    version, extracted apps (own repositories) following their repository."""
    teile = [_app("core", fassung, name="ZENTRALE core")]
    eingebaut = _literal(os.path.join(root, "core", "eingebaute_apps.py"), "EINGEBAUT") or {}
    for name in sorted(eingebaut):
        teile.append(_app(name, fassung, additionalProperty=[
            {"@type": "PropertyValue", "name": "built_in", "value": True}]))
    ausgezogen = {}
    for name, ordner in (_literal(os.path.join(root, "core", "apps.py"), "BEKANNT") or {}).items():
        ausgezogen[name] = _app(name, additionalProperty=[
            {"@type": "PropertyValue", "name": "folder", "value": ordner}])
    try:
        with open(os.path.join(root, "core", "shop_katalog.jsonld"), encoding="utf-8") as f:
            katalog = json.load(f)
    except (OSError, ValueError):
        katalog = {}
    for el in katalog.get("itemListElement") or []:
        it = el.get("item") or {}
        if it.get("category") == "apps" and it.get("downloadUrl"):
            name = next((p.get("value") for p in it.get("additionalProperty") or []
                         if p.get("name") == "app_name"), it.get("identifier"))
            ausgezogen[name] = _app(name, downloadUrl=it["downloadUrl"], sameAs=it.get("@id"))
    teile += [ausgezogen[n] for n in sorted(ausgezogen)]
    return {"@context": "https://schema.org", "@type": "ItemList",
            "name": f"everything@{fassung}", "version": fassung,
            "numberOfItems": len(teile),
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": t}
                                for i, t in enumerate(teile)]}


def bauen(fassung=None, root=ROOT, ziel_ordner=None, liste=None, stufe=9, verteilung=None,
          include_untracked=False):
    """→ (pfad des Pakets, {version, sha256, groesse}). `stufe` = gzip-Stufe
    (Tests nehmen 1: dasselbe Paket, nur schneller gepackt)."""
    fassung = fassung or fassung_bestimmen(root)
    cfg = verteilung or verteilung_lesen(root)
    zusatz = {
        "VERSION": fassung + "\n",
        "VERTEILUNG.json": json.dumps({"oeffentlich": cfg["oeffentlich"],
                                       **quell_vorlagen(cfg)}, indent=2) + "\n",
        "BUNDLE.json": json.dumps(bundle(fassung, root), indent=2, ensure_ascii=False) + "\n",
    }
    ziel_ordner = ziel_ordner or os.path.join(root, "dist")
    os.makedirs(ziel_ordner, exist_ok=True)
    oben = f"zentrale-{fassung}"
    pfad = os.path.join(ziel_ordner, oben + ".tar.gz")

    def normal(info):
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info

    with tarfile.open(pfad, "w:gz", compresslevel=stufe) as tar:
        for q, z in dateien(root, liste, include_untracked):
            tar.add(q, arcname=f"{oben}/{z}", recursive=False, filter=normal)
        for name, text in zusatz.items():
            v = text.encode("utf-8")
            info = normal(tarfile.TarInfo(f"{oben}/{name}"))
            info.size, info.mtime, info.mode = len(v), int(datetime.datetime.now().timestamp()), 0o644
            tar.addfile(info, io.BytesIO(v))
    with open(pfad, "rb") as f:
        daten = f.read()
    neueste = {"version": fassung, "sha256": hashlib.sha256(daten).hexdigest(),
               "groesse": len(daten)}
    with open(os.path.join(ziel_ordner, "neueste.json"), "w", encoding="utf-8") as f:
        json.dump(neueste, f, indent=2)
        f.write("\n")
    return pfad, neueste


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fassung", help="statt deploy/RELEASE")
    ap.add_argument("--ziel", help="statt dist/")
    a = ap.parse_args(argv)
    try:
        pfad, n = bauen(a.fassung, ziel_ordner=a.ziel)
    except PaketFehler as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{pfad}  ({n['groesse'] / 1e6:.1f} MB, sha256 {n['sha256'][:16]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
