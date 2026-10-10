#!/usr/bin/env python3
"""Farbwähler und Stylebox zum Ausprobieren, ohne Backend (2026-10-10).

Die beiden Bausteine (tui/bausteine/farbwaehler.py, stylebox.py) hängen in
keiner Ansicht — die Kalender-Sitzung baut sie selbst ein. Hier laufen sie
allein in curses, mit demselben Kontext (Farbpaare, Theme) wie die TUI:

    venv/bin/python scripts/stil_probe.py            # Nacht-Theme
    venv/bin/python scripts/stil_probe.py --tag      # Tag-Theme

Tasten: f = Farbwähler, s = Stylebox, q = Ende. Was ein Modal zurückgibt,
steht danach oben. Doku: memory/system/bausteine_farbe_stil.md.
"""
import argparse
import curses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tui.ansichten import kontext  # noqa: E402
from tui.bausteine.farbwaehler import Farbwaehler  # noqa: E402
from tui.bausteine.stylebox import Stylebox, stil_kern  # noqa: E402

BEISPIEL = {"border-style": "dashed", "border-color": "#ff8800",
            "background-color": "#202030", "color": "#ffffff"}
ANGEBOT = ["border-style", "border-color", "background-color", "color",
           "--zentrale-muster", "background-image"]


def lauf(stdscr, thema):
    curses.curs_set(0)
    has_color = curses.has_colors()
    if has_color:
        curses.start_color()
        curses.use_default_colors()
    z = kontext.Kontext(stdscr, None, has_color, None)
    z.apply_theme(thema)
    stil, modal, meldung = dict(BEISPIEL), None, "f = farbwähler · s = stylebox · q = ende"
    while True:
        PIX = z.PIX                                     # wie die TUI: Budget je Bild
        if PIX["voll"] or len(PIX["pairs"]) > (PIX["top"] - PIX["base"]) // 2:
            PIX["pairs"].clear()
            PIX["voll"] = False
        stdscr.erase()
        H, W = stdscr.getmaxyx()
        z.safe_addstr(0, 1, meldung[:W - 2], z.C.get("dim", 0))
        z.safe_addstr(1, 1, ("stil: %s" % stil)[:W - 2], z.C.get("faint", 0))
        if modal is not None:
            y, x, h, w = modal.mittig(H - 2, W, 22, 70)
            modal.zeichne(z, y + 2, x, h, w)
        stdscr.refresh()
        ch = stdscr.getch()
        if modal is None:
            if ch == ord("q"):
                return
            if ch == ord("f"):
                modal = Farbwaehler(stil.get("color"))
            elif ch == ord("s"):
                modal = Stylebox(stil, ANGEBOT, titel="termin", text="Uni 08:30")
            continue
        erg = modal.taste(ch)
        if erg:
            meldung = "zurück: %r" % (erg,)
            if erg[0] == "fertig" and isinstance(erg[1], dict):
                stil = stil_kern.anwenden(stil, erg[1])     # None = entfernt
            modal = None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tag", action="store_true", help="Tag-Theme statt Nacht")
    args = ap.parse_args()
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lauf, "day" if args.tag else "night")


if __name__ == "__main__":
    main()
