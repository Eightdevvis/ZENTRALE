#!/usr/bin/env python3
"""Zeigt die drei Kalender-Ansichten (A/B/C) als Text im Terminal.

Warum: die Ansichten sind noch nicht in die TUI eingehängt — Sasha soll sie
vorher sehen und entscheiden können. Gezeichnet wird mit denselben reinen
Funktionen, die die TUI später ruft (tui/ansichten/kalender_ansichten.py), und den
Beispiel-Terminen aus dem Entwurf (tui/ansichten/kalender_beispiel.py).

    scripts/kalender_vorschau.py                    # alle drei, 136×32, farbig
    scripts/kalender_vorschau.py --breite 70        # schmaler Mittelkasten
    scripts/kalender_vorschau.py --ansicht B --hoehe 40
    scripts/kalender_vorschau.py --farbe aus        # reiner Text (für Dateien)

136 Spalten ist der Kalender-Kasten bei 140 Spalten Fensterbreite, seit offene
Apps die ganze Breite haben; im alten 3-Spalten-Dashboard wären es ~67.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tui.ansichten import kalender_ansichten as ka  # noqa: E402
from tui.ansichten import kalender_beispiel as kb  # noqa: E402

# Farbrolle → ANSI (256 Farben, Nacht-Theme der TUI angenähert).
ANSI = {"acc": 108, "warn": 226, "net": 51, "graph": 213, "span": 216,
        "amber": 214, "dim": 231, "faint": 245, "bright": 231}


def ansi(zeile) -> str:
    out = []
    for text, rolle in zeile:
        inv = rolle.endswith(ka.INV)
        basis = rolle[:-len(ka.INV)] if inv else rolle
        farbe = ANSI.get(basis, 231)
        fett = ";1" if basis in ("bright", "warn", "amber") else ""
        code = ("\033[38;5;16;48;5;%dm" % farbe) if inv else ("\033[38;5;%d%sm" % (farbe, fett))
        out.append(code + text + "\033[0m")
    return "".join(out)


def text(zeile) -> str:
    return "".join(t for t, _r in zeile)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--breite", type=int, default=136)
    p.add_argument("--hoehe", type=int, default=32)
    p.add_argument("--ansicht", choices=("A", "B", "C", "alle"), default="alle")
    p.add_argument("--farbe", choices=("an", "aus", "auto"), default="auto")
    p.add_argument("--heute", default=kb.HEUTE, help="YYYY-MM-DD (Beispiel: %s)" % kb.HEUTE)
    p.add_argument("--ref", default=kb.REF, help="geblätterter Tag (Beispiel: %s)" % kb.REF)
    a = p.parse_args(argv)
    farbig = a.farbe == "an" or (a.farbe == "auto" and sys.stdout.isatty())
    ansichten = ka.ANSICHTEN if a.ansicht == "alle" else (a.ansicht,)
    for an in ansichten:
        daten = kb.api_daten(ka.DATENANSICHT[an], ref=a.ref, heute=a.heute)
        print("── Ansicht %s (%s) · %d×%d " % (an, ka.ANSICHT_NAMEN[an], a.breite, a.hoehe)
              + "─" * max(0, a.breite - 32))
        for z in ka.zeichne(an, daten, a.breite, a.hoehe):
            print(ansi(z) if farbig else text(z).rstrip())
        print(" " + ka.tasten_hinweis(an))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
