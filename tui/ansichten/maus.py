# tui/ansichten/maus.py
#
# Maus im Chat (2026-10-07). Sasha: „nur dass man halt mit maus UND tastatur
# navigieren könnte". Klick, Doppelklick, Mausrad — nichts sonst.
#
# Warum das Markieren im Terminal heil bleibt:
#   - Die Maus ist NUR an, solange der Chat offen ist (an/aus über
#     curses.mousemask in run_ui, jede Runde nach dem Fokus). Auf der
#     Startseite und in jedem anderen Fenster markiert das Terminal wie immer.
#   - Auch im Chat: Shift + Ziehen markiert trotzdem. xfce4-terminal (VTE)
#     und tmux geben die Maus bei gedrückter Shift-Taste nicht an das
#     Programm weiter, sondern markieren selbst.
#   - Keine Bewegungsmeldungen (REPORT_MOUSE_POSITION): sonst schickt das
#     Terminal bei jeder Bewegung etwas, und die TUI zeichnet dauernd neu.
#   - Beim Beenden (endwin) und beim Wechsel in einen Editor (endwin,
#     reset_prog_mode) schaltet ncurses die Maus-Meldungen selbst ab bzw.
#     wieder an — ein abgestürztes Programm hinterlässt kein klickendes
#     Terminal, solange curses.wrapper aufräumt.
#   - Abschalten: /mouse im Chat (oder ZENTRALE_TUI_MAUS=aus).
#
# Reine Helfer ohne Bildschirm: deuten(bstate) → Ereignis, treffer(…) → wer.

import curses
import os

# Was die TUI hören will: Knopf 1 geklickt (ncurses fasst Drücken und
# Loslassen zu einem Klick zusammen) und doppelt geklickt, dazu das Rad
# (Knopf 4 hoch, Knopf 5 runter — fehlt BUTTON5 in curses, dann 0x200000,
# wie ncurses 6 es schickt). Der Doppelklick ist nur in der Maske, damit sein
# zweiter Klick NICHT als zweiter Klick kommt (er würde Aufgeklapptes gleich
# wieder zuklappen); getan wird beim Doppelklick nichts.
RAD_RUNTER = getattr(curses, "BUTTON5_PRESSED", 0x200000)
MASKE = (curses.BUTTON1_CLICKED | curses.BUTTON1_DOUBLE_CLICKED
         | curses.BUTTON4_PRESSED | RAD_RUNTER)


def gewuenscht(umgebung=None):
    """Maus an, außer ZENTRALE_TUI_MAUS=aus/off/0."""
    wert = ((umgebung if umgebung is not None else os.environ).get("ZENTRALE_TUI_MAUS") or "")
    return wert.strip().lower() not in ("aus", "off", "0", "nein", "no")


def deuten(bstate):
    """bstate → "klick" | "doppel" | "rad_hoch" | "rad_runter" | None.
    Drücken zählt als Klick, falls ein Terminal nie CLICKED schickt;
    Loslassen allein ist nichts — sonst käme jeder Klick zweimal."""
    if bstate & curses.BUTTON4_PRESSED:
        return "rad_hoch"
    if bstate & RAD_RUNTER:
        return "rad_runter"
    if bstate & curses.BUTTON1_DOUBLE_CLICKED:
        return "doppel"
    if bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
        return "klick"
    return None


def treffer(flaechen, y, x):
    """Die zuletzt gezeichnete Fläche unter (y, x) — die oberste gewinnt.
    flaechen: [(y, x0, x1, aktion)] → aktion oder None."""
    for fy, x0, x1, aktion in reversed(flaechen):
        if fy == y and x0 <= x < x1:
            return aktion
    return None


def rad_treffer(raeder, y, x):
    """Welche Fläche scrollt hier? raeder: [(y0, x0, y1, x1, was)] → was."""
    for y0, x0, y1, x1, was in reversed(raeder):
        if y0 <= y < y1 and x0 <= x < x1:
            return was
    return None
