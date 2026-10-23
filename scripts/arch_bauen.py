#!/usr/bin/env python3
"""PKGBUILD + .SRCINFO für Arch/EndeavourOS rendern (memory/betrieb/verteilung.md).

Vorlage: packaging/arch/PKGBUILD.in. Quelle ist das tar.gz aus
scripts/paket_bauen.py; eingetragen werden Fassung, Quell-URL (aus
deploy/verteilung.toml, öffentliche Quelle) und sein sha256. Schreibt

  dist/arch/PKGBUILD
  dist/arch/.SRCINFO                (das, was `makepkg --printsrcinfo` liefern würde)
  dist/arch/zentrale-<fassung>.tar.gz   (Kopie: makepkg baut damit auch ohne Netz)

Lädt nichts hoch (kein AUR-Push).

  arch_bauen.py [--fassung F] [--paket dist/zentrale-F.tar.gz] [--ziel dist/]
"""

import argparse
import hashlib
import os
import re
import shlex
import shutil
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import paket_bauen  # noqa: E402
from deb_bauen import betreuer  # noqa: E402

ROOT = paket_bauen.ROOT
VORLAGE = os.path.join("packaging", "arch", "PKGBUILD.in")
PKGDESC = "Hub for lists, calendar, notes, memory and an assistant on every device"


def pkgver(fassung: str) -> str:
    """pacman: keine '-', ':' oder '/' in pkgver."""
    return re.sub(r"[-:/]", "_", fassung)


def _lizenz(cfg) -> str:
    return cfg.get("lizenz") or "LicenseRef-alle-Rechte-vorbehalten"


def quelle(cfg, fassung) -> str:
    """Die öffentliche Quell-URL — der PKGBUILD ist für die Zeit NACH dem Schalter."""
    v = paket_bauen.quell_vorlagen(cfg, oeffentlich=True)["paket"]
    if "__CLOUD__" in v:
        v = v.replace("__CLOUD__", paket_bauen.cloud_vorgabe())
    return v.replace("__VERSION__", fassung)


def rendern(cfg, fassung, sha256, root=ROOT) -> str:
    with open(os.path.join(root, VORLAGE), encoding="utf-8") as f:
        text = f.read()
    werte = {
        "@BETREUER@": betreuer(cfg, root),
        "@FASSUNG@": shlex.quote(fassung),
        "@PKGVER@": pkgver(fassung),
        "@URL@": shlex.quote(cfg.get("homepage") or ""),
        "@LIZENZ@": shlex.quote(_lizenz(cfg)),
        "@QUELLE@": quelle(cfg, fassung),
        "@SHA256@": sha256,
    }
    for marke, wert in werte.items():
        if marke not in text:
            raise paket_bauen.PaketFehler(f"{VORLAGE}: {marke} fehlt.")
        text = text.replace(marke, wert)
    return text


def srcinfo(cfg, fassung, sha256) -> str:
    """Wie `makepkg --printsrcinfo` (Tabs, pkgbase zuerst)."""
    z = ["pkgbase = zentrale", f"\tpkgdesc = {PKGDESC}", f"\tpkgver = {pkgver(fassung)}",
         "\tpkgrel = 1"]
    if cfg.get("homepage"):
        z.append(f"\turl = {cfg['homepage']}")
    z += ["\tarch = any", f"\tlicense = {_lizenz(cfg)}", "\tdepends = python>=3.11",
          "\toptdepends = portaudio: sound in the terminal piano",
          f"\tsource = zentrale-{fassung}.tar.gz::{quelle(cfg, fassung)}",
          f"\tsha256sums = {sha256}", "", "pkgname = zentrale", ""]
    return "\n".join(z)


def bauen(tar_pfad, neueste, ziel_ordner=None, cfg=None, root=ROOT):
    """→ [PKGBUILD, .SRCINFO, tar.gz-Kopie] in <ziel>/arch/."""
    cfg = cfg or paket_bauen.verteilung_lesen(root)
    fassung = neueste["version"]
    with open(tar_pfad, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    if neueste.get("sha256") and neueste["sha256"] != sha:
        raise paket_bauen.PaketFehler("sha256 des tar.gz passt nicht zu neueste.json.")
    ordner = os.path.join(ziel_ordner or os.path.join(root, "dist"), "arch")
    os.makedirs(ordner, exist_ok=True)
    pkgbuild = os.path.join(ordner, "PKGBUILD")
    with open(pkgbuild, "w", encoding="utf-8") as f:
        f.write(rendern(cfg, fassung, sha, root))
    info = os.path.join(ordner, ".SRCINFO")
    with open(info, "w", encoding="utf-8") as f:
        f.write(srcinfo(cfg, fassung, sha))
    kopie = os.path.join(ordner, f"zentrale-{fassung}.tar.gz")
    shutil.copyfile(tar_pfad, kopie)
    return [pkgbuild, info, kopie]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fassung")
    ap.add_argument("--paket", help="fertiges tar.gz statt neu bauen")
    ap.add_argument("--ziel")
    a = ap.parse_args(argv)
    try:
        if a.paket:
            fassung = a.fassung or os.path.basename(a.paket)[len("zentrale-"):-len(".tar.gz")]
            tar, n = a.paket, {"version": fassung}
        else:
            tar, n = paket_bauen.bauen(a.fassung, ziel_ordner=a.ziel)
        for p in bauen(tar, n, a.ziel):
            print(p)
    except paket_bauen.PaketFehler as e:
        print(e, file=sys.stderr)
        return 1
    print("— nichts hochgeladen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
