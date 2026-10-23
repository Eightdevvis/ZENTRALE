#!/usr/bin/env python3
"""Alles für die Verteilung bauen — nach dist/, hochgeladen wird NICHTS
(memory/betrieb/verteilung.md).

  verteilung.py install-sh            deploy/install.sh aus deploy/install.sh.in neu rendern
  verteilung.py install-sh --pruefen  nur prüfen, ob deploy/install.sh zum Schalter passt
  verteilung.py alles [--fassung F]   install.sh, tar.gz, .deb, PKGBUILD — in dieser Reihenfolge

Der Schalter und die Quellen stehen in deploy/verteilung.toml; welche Dateien
ausgeliefert werden, entscheidet allein scripts/paket_bauen.py (deploy/paket.txt).
"""

import argparse
import os
import shlex
import shutil
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import paket_bauen  # noqa: E402

ROOT = paket_bauen.ROOT
VORLAGE = os.path.join("deploy", "install.sh.in")
INSTALL_SH = os.path.join("deploy", "install.sh")


def install_sh_rendern(cfg, root=ROOT) -> str:
    """install.sh für den Schalter in `cfg` — nur Konstanten werden eingesetzt,
    die Logik für beide Stellungen steht in der Vorlage."""
    with open(os.path.join(root, VORLAGE), encoding="utf-8") as f:
        text = f.read()
    v = paket_bauen.quell_vorlagen(cfg)
    werte = {
        "@HINWEIS@": ("# GERENDERT aus deploy/install.sh.in von scripts/verteilung.py nach "
                      "deploy/verteilung.toml\n# (oeffentlich = "
                      f"{'true' if cfg['oeffentlich'] else 'false'}). Nicht von Hand ändern."),
        "@OEFFENTLICH@": "1" if cfg["oeffentlich"] else "0",
        "@CLOUD_VORGABE@": shlex.quote(paket_bauen.cloud_vorgabe(root)),
        "@NEUESTE@": shlex.quote(v["neueste"]),
        "@PAKET@": shlex.quote(v["paket"]),
    }
    for marke, wert in werte.items():
        if text.count(marke) != 1:
            raise paket_bauen.PaketFehler(f"{VORLAGE}: {marke} muss genau einmal vorkommen.")
        text = text.replace(marke, wert)
    return text


def install_sh_schreiben(root=ROOT, cfg=None, ziel=None):
    text = install_sh_rendern(cfg or paket_bauen.verteilung_lesen(root), root)
    ziel = ziel or os.path.join(root, INSTALL_SH)
    with open(ziel, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(ziel, 0o755)
    return ziel


def alles(fassung=None, root=ROOT, ziel_ordner=None):
    import arch_bauen
    import deb_bauen
    ziel_ordner = ziel_ordner or os.path.join(root, "dist")
    cfg = paket_bauen.verteilung_lesen(root)
    install_sh_schreiben(root, cfg)
    os.makedirs(ziel_ordner, exist_ok=True)
    shutil.copy2(os.path.join(root, INSTALL_SH), os.path.join(ziel_ordner, "install.sh"))
    tar, neueste = paket_bauen.bauen(fassung, root=root, ziel_ordner=ziel_ordner, verteilung=cfg)
    deb = deb_bauen.bauen(tar, neueste["version"], ziel_ordner, cfg, root)
    arch = arch_bauen.bauen(tar, neueste, ziel_ordner, cfg, root)
    return [os.path.join(ziel_ordner, "install.sh"), tar,
            os.path.join(ziel_ordner, "neueste.json"), deb, *arch]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="was", required=True)
    i = sub.add_parser("install-sh")
    i.add_argument("--pruefen", action="store_true")
    a = sub.add_parser("alles")
    a.add_argument("--fassung")
    a.add_argument("--ziel")
    args = ap.parse_args(argv)
    try:
        if args.was == "install-sh":
            soll = install_sh_rendern(paket_bauen.verteilung_lesen())
            if args.pruefen:
                with open(os.path.join(ROOT, INSTALL_SH), encoding="utf-8") as f:
                    if f.read() != soll:
                        print("deploy/install.sh passt nicht zu deploy/verteilung.toml — "
                              "neu rendern: scripts/verteilung.py install-sh", file=sys.stderr)
                        return 1
                print("deploy/install.sh passt.")
                return 0
            print(install_sh_schreiben())
            return 0
        cfg = paket_bauen.verteilung_lesen()
        print(f"Schalter: oeffentlich = {str(cfg['oeffentlich']).lower()} — es wird nichts hochgeladen.")
        for p in alles(args.fassung, ziel_ordner=args.ziel):
            print(f"  {os.path.relpath(p, ROOT)}  ({os.path.getsize(p) / 1e6:.2f} MB)")
    except paket_bauen.PaketFehler as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
