#!/usr/bin/env python3
# scripts/ablage_umzug.py
#
# Die Ablage zieht um (2026-10-11): von data/ablage/<id>/ im Code-Ordner
# nach ~/Zentrale/Ablage/ (Einstellung ablage_dir) — Köpfe und Fassungen
# versteckt unter .ablage/dokumente/<id>/, die neueste Fassung jedes
# Dokuments als lesbare Datei obendrauf (core/ablage_sichtbar.py).
#
#   --trocken   (Standard) zeigt nur, was wohin käme. Fasst nichts an.
#   --wirklich  kopiert. data/ablage bleibt als Sicherung liegen; was am Ziel
#               schon liegt, wird nie überschrieben.
#
# Die ids bleiben, alte Gespräche und Morgenblick-Links gelten weiter.

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

import ablage              # noqa: E402
import ablage_sichtbar     # noqa: E402

ALT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ablage")


def bestand(alt: str) -> list:
    """[(id, kopf)] der alten Ablage."""
    raus = []
    try:
        namen = sorted(os.listdir(alt))
    except OSError:
        return raus
    for name in namen:
        k = os.path.join(alt, name, "kopf.json")
        if os.path.isfile(k):
            import json
            try:
                with open(k, encoding="utf-8") as f:
                    raus.append((name, json.load(f)))
            except (OSError, ValueError):
                raus.append((name, {}))
    return raus


def plan(alt: str = ALT) -> list:
    """[(id, von, nach, sichtbar_als, schon_da)]."""
    raus, belegt = [], set()
    for doc_id, k in bestand(alt):
        nach = os.path.join(ablage.ordner(), doc_id)
        fassungen = [n for n in os.listdir(os.path.join(alt, doc_id)) if n.startswith("v")]
        endung = os.path.splitext(sorted(fassungen)[-1])[1] if fassungen else ""
        sichtbar = ablage_sichtbar.dateiname(dict(k, id=doc_id, endung=endung))
        stamm, end = os.path.splitext(sichtbar)
        i = 2
        while sichtbar in belegt:           # wie ablage_sichtbar._frei: „ (2)"
            sichtbar, i = f"{stamm} ({i}){end}", i + 1
        belegt.add(sichtbar)
        raus.append((doc_id, os.path.join(alt, doc_id), nach, sichtbar, os.path.exists(nach)))
    return raus


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ablage nach ~/Zentrale/Ablage umziehen.")
    p.add_argument("--wirklich", action="store_true", help="kopieren (sonst nur zeigen)")
    p.add_argument("--trocken", action="store_true", help="nur zeigen (Standard)")
    p.add_argument("--alt", default=ALT, help="alte Ablage (Standard: data/ablage)")
    a = p.parse_args(argv)
    alt = a.alt
    schritte = plan(alt)
    print(f"Ablage alt: {os.path.realpath(alt)}")
    print(f"Ablage neu: {ablage.wurzel()}  ({len(schritte)} Dokumente)\n")
    for doc_id, von, nach, sichtbar, da in schritte:
        print(f"  {doc_id}\n    → {nach}{'  (schon da — bleibt)' if da else ''}\n"
              f"    sichtbar als: {os.path.join(ablage.wurzel(), sichtbar)}")
    if not a.wirklich:
        print("\nTrocken — nichts kopiert. Mit --wirklich kopieren.")
        return 0
    for doc_id, von, nach, _s, da in schritte:
        if not da:
            shutil.copytree(von, nach)
    ablage_sichtbar.abgleichen()
    print(f"\nKopiert. {alt} bleibt als Sicherung liegen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
