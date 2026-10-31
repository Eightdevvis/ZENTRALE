# tui/bausteine/sgr_mouse.py
#
# Mouse and touchpad for the canvas (2026-10-31, Sasha: "I assumed you can
# navigate around with two fingers on the touchpad, intuitively"). Desk and
# Schematix share it through tui/bausteine/canvas.py (`rad`, `zeiger`); the
# main loop (tui/zentrale_tui.py) switches it on while a canvas has the
# focus and hands the events to the program's `maus(events)`.
#
# Why not ncurses' own mouse (curses.mousemask, used by the chat,
# tui/ansichten/maus.py): measured with ncurses 6.4, it turns the
# horizontal wheel (SGR buttons 66/67 — two-finger sideways) into a
# meaningless REPORT_MOUSE_POSITION or drops it, and it asks the terminal
# for 1000 only, so a drag never reports motion. So this module asks for
# 1000 (buttons) + 1002 (motion while a button is held) + 1006 (SGR
# encoding) itself and reads the reports from the key stream:
#   ESC [ < b ; x ; y M   (press / motion / wheel)     … m  (release)
# Under TERM=xterm-256color ncurses knows "ESC [ <" as kmous and returns
# KEY_MOUSE for it, the rest comes as plain characters; under tmux-256color
# (kmous = ESC [ M) everything comes as plain characters. `lesen` takes both.
#
# Bursts: a two-finger swipe sends dozens of wheel reports at once. `lesen`
# drains every report already waiting and sums the wheel into one event per
# frame; the canvas moves at most one capped pan step per frame for it.
#
# Restoring the terminal: `Modus.setzen(False)` writes the reset sequence;
# the main loop does it when the canvas loses the focus, in a `finally`
# around the loop (crash, reload, quit), before an external program gets
# the terminal (`ausgesetzt`), and atexit as the last net.
#
# Pure: reads through getch/ungetch callables and writes through a writer —
# testable without a terminal.

import atexit
import contextlib
import os
from collections import namedtuple

AN = b"\x1b[?1000h\x1b[?1002h\x1b[?1006h"
AUS = b"\x1b[?1006l\x1b[?1002l\x1b[?1000l"

KEY_MOUSE = 0o631                       # curses.KEY_MOUSE (no curses import here)
ESC = 27

# kind: "wheel" (dx, dy = notches, negative = left/up), "press", "drag",
# "release" (x, y = 0-based screen cell; left button only).
Ereignis = namedtuple("Ereignis", "art x y dx dy")


def deuten(b, x, y, ende):
    """One SGR report → Ereignis or None (buttons we don't use).
    b: button code, x/y 1-based, ende "M" (press/motion) or "m" (release)."""
    x, y = x - 1, y - 1
    if b & 64:                                       # wheel: 64 up, 65 down, 66 left, 67 right
        if ende == "m":
            return None
        knopf = b & 3
        dx, dy = {0: (0, -1), 1: (0, 1), 2: (-1, 0), 3: (1, 0)}[knopf]
        if b & 4 and dx == 0:                        # shift + wheel = sideways
            dx, dy = dy, 0
        return Ereignis("wheel", x, y, dx, dy)
    if b & 3 != 0:                                   # only the left button
        return None
    if b & 32:
        return Ereignis("drag", x, y, 0, 0)
    return Ereignis("release" if ende == "m" else "press", x, y, 0, 0)


def _bericht(getch, nach_esc):
    """Read one report after its start (ESC already read, or KEY_MOUSE when
    nach_esc is False). -> (Ereignis-or-None, True) when it was a mouse
    report, (read characters, False) when not."""
    gelesen = []

    def naechstes():
        ch = getch()
        if ch != -1:
            gelesen.append(ch)
        return ch

    if nach_esc:
        if naechstes() != ord("[") or naechstes() != ord("<"):
            return gelesen, False
    zahlen, zahl = [], ""
    for _ in range(24):
        ch = naechstes()
        if ch == -1:
            return gelesen, False
        c = chr(ch) if 0 <= ch < 256 else ""
        if c.isdigit():
            zahl += c
        elif c == ";" and zahl:
            zahlen.append(int(zahl))
            zahl = ""
        elif c in ("M", "m") and zahl and len(zahlen) == 2:
            b, x = zahlen
            return deuten(b, x, int(zahl), c), True
        else:
            return gelesen, False
    return gelesen, False


def lesen(ch, getch, ungetch):
    """ch was just read (ESC or KEY_MOUSE). If a mouse report follows: read
    it and every report already waiting -> list of Ereignis (wheel summed,
    drags merged to the last). Otherwise put back what was read and return
    None — the key goes its usual way.

    getch() must not block long (the caller sets a short timeout); -1 =
    nothing waiting."""
    if ch not in (ESC, KEY_MOUSE):
        return None
    erg, ok = _bericht(getch, ch == ESC)
    if not ok:
        for c in reversed(erg):
            ungetch(c)
        return None
    roh = [erg] if erg else []
    for _ in range(512):                             # drain the burst
        weiter = getch()
        if weiter == -1:
            break
        if weiter not in (ESC, KEY_MOUSE):
            ungetch(weiter)
            break
        erg, ok = _bericht(getch, weiter == ESC)
        if not ok:
            for c in reversed(erg):
                ungetch(c)
            ungetch(weiter)
            break
        if erg:
            roh.append(erg)
    return zusammenfassen(roh)


def zusammenfassen(roh):
    """Consecutive wheel reports → one (summed); consecutive drags → the
    last one. Presses and releases keep their order."""
    raus = []
    for e in roh:
        letzt = raus[-1] if raus else None
        if letzt and e.art == letzt.art == "wheel":
            raus[-1] = letzt._replace(x=e.x, y=e.y, dx=letzt.dx + e.dx, dy=letzt.dy + e.dy)
        elif letzt and e.art == letzt.art == "drag":
            raus[-1] = e
        else:
            raus.append(e)
    return raus


# curses.KEY_DOWN/UP/LEFT/RIGHT (no curses import at load time here).
PFEILE = (0o402, 0o403, 0o404, 0o405)


def pfeile_schlucken(ch, stdscr):
    """Without mouse reporting (tmux with mouse off, or a terminal with
    alternate scroll) the wheel arrives as a pile of arrow keys — and a held
    arrow that the TUI fell behind on piles up the same way. The same arrow
    already waiting behind ch is swallowed: one step per frame, no fling,
    no overshoot after letting go. -> how many were swallowed."""
    if ch not in PFEILE:
        return 0
    n = 0
    try:
        stdscr.timeout(0)
        for _ in range(256):
            weiter = stdscr.getch()
            if weiter == -1:
                break
            if weiter != ch:
                import curses
                try:
                    curses.ungetch(weiter)
                except curses.error:
                    pass
                break
            n += 1
    except Exception:                                # a screen stand-in without timeout
        pass
    return n


class Modus:
    """Mouse reporting on/off in the terminal; writes only on a change."""

    def __init__(self, schreiben=None):
        self._schreiben = schreiben or (lambda b: os.write(1, b))
        self.an = False
        atexit.register(self.setzen, False)

    def setzen(self, an):
        an = bool(an)
        if an == self.an:
            return
        try:
            self._schreiben(AN if an else AUS)
        except OSError:
            pass
        self.an = an

    @contextlib.contextmanager
    def ausgesetzt(self):
        """Off while an external program owns the terminal, then back."""
        war = self.an
        self.setzen(False)
        try:
            yield
        finally:
            self.setzen(war)


def gewuenscht(umgebung=None):
    """Mouse on unless ZENTRALE_TUI_MAUS=aus/off/0 (the same switch as the
    chat mouse, tui/ansichten/maus.py)."""
    wert = ((umgebung if umgebung is not None else os.environ).get("ZENTRALE_TUI_MAUS") or "")
    return wert.strip().lower() not in ("aus", "off", "0", "nein", "no")


MODUS = Modus()


def pflegen(programm, nur_aus=False):
    """Main loop, every round: reporting on while the program in front
    wants it (`maus_will`: a canvas is open — Desk, Schematix) and the user
    did not switch it off, off otherwise. nur_aus: only switch off now (the
    chat's ncurses mouse is maintained in between, so the two never
    overwrite each other's modes on the frame the focus changes)."""
    will = bool(programm is not None and hasattr(programm, "maus_will")
                and programm.maus_will() and gewuenscht())
    if not (will and nur_aus):
        MODUS.setzen(will)


def verteilen(ch, stdscr, programm, gesperrt=False):
    """ch was just read. A mouse report while reporting is on? Then read it
    and everything piled up behind it, hand it to `programm.maus(events)`
    (not while something lies on top: `gesperrt`) and -> True — the key is
    used up. Otherwise -> False and ch goes its usual way."""
    if not MODUS.an or ch not in (ESC, KEY_MOUSE):
        return False
    import curses
    stdscr.timeout(10)
    ereignisse = lesen(ch, stdscr.getch, curses.ungetch)
    if ereignisse is None:
        return False
    if not gesperrt and programm is not None and hasattr(programm, "maus"):
        programm.maus(ereignisse)
    return True
