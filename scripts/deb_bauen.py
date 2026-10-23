#!/usr/bin/env python3
"""Das Debian-Paket bauen: dist/zentrale_<fassung>_all.deb (memory/betrieb/verteilung.md).

Nimmt das tar.gz aus scripts/paket_bauen.py — dieselben Dateien, dieselbe Fassung —
und baut nur mit dpkg-deb (kein debhelper):

  /usr/lib/zentrale/...          das entpackte tar.gz + KANAL ("apt")
  /usr/bin/zentrale              packaging/starter.sh aus dem tar.gz
  /usr/share/doc/zentrale/       copyright, changelog.gz (Debian-Pflicht)

Python-Pakete installiert NICHT dpkg: der Starter baut beim ersten Start ein
venv unter ~/.local/share/zentrale/paket/venv (kein pip ins System-Python,
kein Netz während apt). Lädt nichts hoch.

  deb_bauen.py [--fassung F] [--paket dist/zentrale-F.tar.gz] [--ziel dist/]
"""

import argparse
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import paket_bauen  # noqa: E402

ROOT = paket_bauen.ROOT
LIB = "usr/lib/zentrale"
DEPENDS = "python3 (>= 3.11), python3-venv, ca-certificates"
RECOMMENDS = "libportaudio2"
BESCHREIBUNG = (
    "hub for lists, calendar, notes, memory and an assistant\n"
    " ZENTRALE keeps your lists, calendar, notes and memory on your own\n"
    " machines and syncs them encrypted between your devices. It comes with a\n"
    " terminal dashboard and an assistant that runs through the cloud.\n"
    " .\n"
    " On first start the command creates a Python environment for the user\n"
    " in ~/.local/share/zentrale (needs network once)."
)


def betreuer(cfg, root=ROOT) -> str:
    """deploy/verteilung.toml `betreuer`, sonst git config, sonst ein Platzhalter."""
    if cfg.get("betreuer"):
        return cfg["betreuer"]

    def git(k):
        r = subprocess.run(["git", "-C", root, "config", k], capture_output=True, text=True)
        return r.stdout.strip()
    name, mail = git("user.name"), git("user.email")
    return f"{name or 'ZENTRALE'} <{mail or 'zentrale@localhost'}>"


def deb_fassung(fassung: str) -> str:
    """Debian-Versionen beginnen mit einer Ziffer und kennen kein '_'."""
    v = fassung.replace("_", ".")
    return v if v[:1].isdigit() else "0~" + v


def _copyright(cfg) -> str:
    lizenz = cfg.get("lizenz") or "LicenseRef-alle-Rechte-vorbehalten"
    text = ("All rights reserved. The licence has not been decided yet."
            if not cfg.get("lizenz") else "See the LICENSE file shipped in /usr/lib/zentrale.")
    return ("Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n"
            "Upstream-Name: zentrale\n"
            + (f"Source: {cfg['homepage']}\n" if cfg.get("homepage") else "")
            + "\nFiles: *\n"
            f"Copyright: {betreuer(cfg)}\n"
            f"License: {lizenz}\n"
            f" {text}\n")


def _changelog(fassung, cfg) -> bytes:
    import email.utils
    text = (f"zentrale ({fassung}) unstable; urgency=medium\n\n"
            f"  * Release {fassung}.\n\n"
            f" -- {betreuer(cfg)}  {email.utils.formatdate(localtime=False)}\n")
    puffer = io.BytesIO()
    with gzip.GzipFile(fileobj=puffer, mode="wb", compresslevel=9, mtime=0, filename="") as g:
        g.write(text.encode("utf-8"))
    return puffer.getvalue()


def _schreiben(pfad, daten, modus=0o644):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb") as f:
        f.write(daten if isinstance(daten, bytes) else daten.encode("utf-8"))
    os.chmod(pfad, modus)


def bauen(tar_pfad, fassung, ziel_ordner=None, cfg=None, root=ROOT) -> str:
    """tar.gz → .deb. Gibt den Pfad zurück."""
    if not shutil.which("dpkg-deb"):
        raise paket_bauen.PaketFehler("dpkg-deb fehlt — das .deb lässt sich hier nicht bauen.")
    cfg = cfg or paket_bauen.verteilung_lesen(root)
    ziel_ordner = ziel_ordner or os.path.join(root, "dist")
    version = deb_fassung(fassung)
    with tempfile.TemporaryDirectory(prefix="zentrale-deb-") as arbeit:
        baum = os.path.join(arbeit, "baum")
        lib = os.path.join(baum, LIB)
        with tarfile.open(tar_pfad, "r:gz") as tar:
            tar.extractall(os.path.join(arbeit, "aus"), filter="data")
        oben = os.listdir(os.path.join(arbeit, "aus"))
        if len(oben) != 1:
            raise paket_bauen.PaketFehler("Das tar.gz hat mehr als einen obersten Ordner.")
        os.makedirs(os.path.dirname(lib))
        shutil.move(os.path.join(arbeit, "aus", oben[0]), lib)
        _schreiben(os.path.join(lib, "KANAL"), "apt\n")
        starter = os.path.join(lib, "packaging", "starter.sh")
        if not os.path.isfile(starter):
            raise paket_bauen.PaketFehler("packaging/starter.sh fehlt im tar.gz (deploy/paket.txt).")
        os.makedirs(os.path.join(baum, "usr", "bin"))
        shutil.copyfile(starter, os.path.join(baum, "usr", "bin", "zentrale"))
        doc = os.path.join(baum, "usr", "share", "doc", "zentrale")
        _schreiben(os.path.join(doc, "copyright"), _copyright(cfg))
        _schreiben(os.path.join(doc, "changelog.gz"), _changelog(version, cfg))

        # Rechte wie Debian sie will: Ordner 755, Dateien 644, Ausführbares 755.
        groesse, summen = 0, []
        for w, ds, fs in os.walk(baum):
            os.chmod(w, 0o755)
            for f in sorted(fs):
                p = os.path.join(w, f)
                ausfuehrbar = os.stat(p).st_mode & 0o111
                os.chmod(p, 0o755 if ausfuehrbar else 0o644)
                with open(p, "rb") as h:
                    daten = h.read()
                groesse += len(daten)
                summen.append(f"{hashlib.md5(daten).hexdigest()}  {os.path.relpath(p, baum)}")
        os.chmod(os.path.join(baum, "usr", "bin", "zentrale"), 0o755)

        felder = [
            ("Package", "zentrale"), ("Version", version), ("Architecture", "all"),
            ("Maintainer", betreuer(cfg, root)), ("Installed-Size", str(groesse // 1024 + 1)),
            ("Depends", DEPENDS), ("Recommends", RECOMMENDS),
            ("Section", "utils"), ("Priority", "optional"),
        ]
        if cfg.get("homepage"):
            felder.append(("Homepage", cfg["homepage"]))
        felder.append(("Description", BESCHREIBUNG))
        _schreiben(os.path.join(baum, "DEBIAN", "control"),
                   "".join(f"{k}: {v}\n" for k, v in felder))
        _schreiben(os.path.join(baum, "DEBIAN", "md5sums"), "\n".join(sorted(summen)) + "\n")
        os.chmod(os.path.join(baum, "DEBIAN"), 0o755)

        os.makedirs(ziel_ordner, exist_ok=True)
        deb = os.path.join(ziel_ordner, f"zentrale_{version}_all.deb")
        r = subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", baum, deb],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise paket_bauen.PaketFehler("dpkg-deb: " + (r.stderr or r.stdout).strip())
    if shutil.which("lintian"):
        r = subprocess.run(["lintian", "--no-tag-display-limit", deb], capture_output=True, text=True)
        if r.stdout.strip():
            print(r.stdout.strip(), file=sys.stderr)
    return deb


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fassung")
    ap.add_argument("--paket", help="fertiges tar.gz statt neu bauen")
    ap.add_argument("--ziel")
    a = ap.parse_args(argv)
    try:
        if a.paket:
            fassung = a.fassung or os.path.basename(a.paket)[len("zentrale-"):-len(".tar.gz")]
            tar = a.paket
        else:
            tar, n = paket_bauen.bauen(a.fassung, ziel_ordner=a.ziel)
            fassung = n["version"]
        deb = bauen(tar, fassung, a.ziel)
    except paket_bauen.PaketFehler as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{deb}  ({os.path.getsize(deb) / 1e6:.2f} MB) — nichts hochgeladen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
