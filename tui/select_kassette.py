#!/usr/bin/env python3
# tui/select_kassette.py
#
# ════════════════════════════════════════════════════════════════════════
# ZENTRALE — Kassetten-Selector (Terminal-Menü)
# ------------------------------------------------------------------------
# Einstieg von `zentrale`: zeigt ein kleines Menü „Welche Kassette wählen?",
# man bewegt sich mit ↑/↓ (ein animierter Stern ✶ funkelt auf der aktuellen
# Zeile), Enter startet — danach läuft ein game-mäßiger Regenbogen-Ladebalken
# und das Skript exec't in die gewählte Kassette.
#
# BEWUSST nur stdlib (termios + ANSI, kein curses): leaner, und die Render-/
# Logik-Funktionen (star_glyph, render_menu, rainbow_segment, parse_key) sind
# rein und ohne TTY unit-testbar (--selftest).
#
# Direkt-Befehle bleiben: `zentrale-laptop` / `zentrale-tui` überspringen das
# Menü. `zentrale` → dieses Menü.
# ════════════════════════════════════════════════════════════════════════

import os
import sys
import time

# (key, label, beschreibung, start-skript relativ zum projekt-root)
CASSETTES = [
    ("monolith", "monolith", "Browser · voll · KI",     "scripts/start_local.sh"),
    ("laptop",   "laptop",   "Browser · lean · KI aus",  "scripts/start_laptop.sh"),
    ("tui",      "tui",      "Terminal · KI aus",        "scripts/start_tui.sh"),
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── ANSI-Helfer ────────────────────────────────────────────────────────────
ESC = "\x1b"
RESET = ESC + "[0m"
HIDE_CUR = ESC + "[?25l"
SHOW_CUR = ESC + "[?25h"
ALT_ON = ESC + "[?1049h"
ALT_OFF = ESC + "[?1049l"
HOME = ESC + "[H"
CLR_BELOW = ESC + "[J"
CLR_LINE = ESC + "[K"


def c256(i):
    return "%s[38;5;%dm" % (ESC, i)


# Funkelnder Stern: Form wechselt (klein→groß→klein), Farbe von Gold zu Weiß.
STAR_GLYPHS = ["✦", "✧", "✶", "✷", "✸", "✹", "✺", "✹", "✸", "✷", "✶", "✧"]
STAR_COLORS = [220, 222, 226, 228, 230, 231, 230, 228, 226, 222, 220, 214]


def star_glyph(tick):
    """Ein Stern-Glyph für diesen Animations-Tick (zyklisch)."""
    return STAR_GLYPHS[tick % len(STAR_GLYPHS)]


def star_colored(tick):
    g = STAR_GLYPHS[tick % len(STAR_GLYPHS)]
    col = STAR_COLORS[tick % len(STAR_COLORS)]
    return c256(col) + g + RESET


# Regenbogen-Farbrad (256-Farben, glatt durchs Spektrum).
RAINBOW = [196, 202, 208, 214, 220, 226, 190, 154, 118, 82, 46, 48,
           51, 45, 39, 33, 27, 21, 57, 93, 129, 165, 201, 198]


def rainbow_segment(width, filled, phase):
    """
    Ein Balken-String: 'filled' gefüllte Regenbogen-Blöcke (Farbe scrollt mit
    'phase'), Rest matte '░'. PURE Funktion (gibt ANSI-String zurück).
    """
    out = []
    for i in range(width):
        if i < filled:
            col = RAINBOW[(i + phase) % len(RAINBOW)]
            out.append(c256(col) + "█")
        else:
            out.append(c256(238) + "░")
    return "".join(out) + RESET


def render_menu(sel, tick):
    """
    Baut das komplette Menü-Frame als ANSI-String (beginnt mit HOME, löscht
    nach unten). PURE Funktion — testbar (ANSI strippen, Inhalt prüfen).
    """
    gold = c256(220)
    dim = c256(245)
    faint = c256(240)
    white = ESC + "[1m" + c256(231)
    green = c256(108)

    lines = []
    lines.append("")
    lines.append("   %s✦  Z E N T R A L E  ✦%s" % (gold, RESET))
    lines.append("   %sWelche Kassette wählen?%s" % (dim, RESET))
    lines.append("")
    for i, (key, label, desc, _script) in enumerate(CASSETTES):
        if i == sel:
            marker = star_colored(tick)
            name = "%s%-9s%s" % (white, label, RESET)
            d = "%s%s%s" % (green, desc, RESET)
        else:
            marker = "%s·%s" % (faint, RESET)
            name = "%s%-9s%s" % (dim, label, RESET)
            d = "%s%s%s" % (faint, desc, RESET)
        lines.append("   %s  %s  %s" % (marker, name, d))
    lines.append("")
    lines.append("   %s↑/↓ wählen · Enter starten · q quit%s" % (faint, RESET))

    return HOME + ("\r\n".join(line + CLR_LINE for line in lines)) + "\r\n" + CLR_BELOW


def parse_key(data):
    """Rohe stdin-Bytes → Aktion: 'up' | 'down' | 'select' | 'quit' | None."""
    if b"\x1b[A" in data or b"\x1bOA" in data:
        return "up"
    if b"\x1b[B" in data or b"\x1bOB" in data:
        return "down"
    if b"\r" in data or b"\n" in data:
        return "select"
    if b"q" in data or b"Q" in data or b"\x03" in data:  # q / Ctrl-C
        return "quit"
    return None


# ── Interaktive Schleife (braucht TTY) ──────────────────────────────────────
def menu_loop(fd):
    import select as _sel
    sel = 0
    tick = 0
    sys.stdout.write(render_menu(sel, tick))
    sys.stdout.flush()
    while True:
        r, _, _ = _sel.select([fd], [], [], 0.12)   # 0.12s → Stern funkelt weiter
        if fd in r:
            data = os.read(fd, 64)
            if not data:
                return None
            act = parse_key(data)
            if act == "quit":
                return None
            elif act == "up":
                sel = (sel - 1) % len(CASSETTES)
            elif act == "down":
                sel = (sel + 1) % len(CASSETTES)
            elif act == "select":
                return sel
        tick += 1
        sys.stdout.write(render_menu(sel, tick))
        sys.stdout.flush()


def play_loader(label):
    """Game-mäßiger Regenbogen-Ladebalken auf dem Normal-Screen."""
    width = 28
    sys.stdout.write("\n  %sstarte %s …%s\n\n" % (c256(108), label, RESET))
    sys.stdout.flush()
    phase = 0
    for filled in range(width + 1):
        pct = int(filled / width * 100)
        bar = rainbow_segment(width, filled, phase)
        sys.stdout.write("\r  [%s] %s%3d%%%s" % (bar, c256(231), pct, RESET))
        sys.stdout.flush()
        phase += 1
        time.sleep(0.035)
    # kurzer Shimmer bei 100 %
    for _ in range(10):
        bar = rainbow_segment(width, width, phase)
        sys.stdout.write("\r  [%s] %s100%%%s" % (bar, c256(231), RESET))
        sys.stdout.flush()
        phase += 1
        time.sleep(0.045)
    sys.stdout.write("\n\n")
    sys.stdout.flush()


def launch(idx):
    """Terminal ist hier schon restauriert. Loader + exec in die Kassette."""
    key, label, desc, script = CASSETTES[idx]
    play_loader(label)
    script_abs = os.path.join(PROJECT_ROOT, script)
    os.execv("/bin/bash", ["/bin/bash", script_abs])


# ── Selbsttest (kein TTY, keine raw-Mode, kein exec) ────────────────────────
def selftest():
    import re
    strip = lambda s: re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)

    def check(label, cond):
        print(("OK  " if cond else "FAIL") + "  " + label)

    check("star_glyph zyklisch", star_glyph(0) in STAR_GLYPHS and star_glyph(99) in STAR_GLYPHS)
    frame = strip(render_menu(2, 5))
    check("Menü listet alle 3 Kassetten", all(k in frame for _, k, _, _ in CASSETTES))
    # Stern muss auf der gewählten Zeile (tui, idx 2) stehen, nicht auf den anderen
    star_set = set(STAR_GLYPHS)
    tui_line = [ln for ln in frame.splitlines() if "tui" in ln][0]
    mono_line = [ln for ln in frame.splitlines() if "monolith" in ln][0]
    check("Stern auf Auswahl (tui)", any(g in tui_line for g in star_set))
    check("kein Stern auf nicht-Auswahl (monolith)", not any(g in mono_line for g in star_set))
    check("'Welche Kassette wählen?' im Frame", "Welche Kassette wählen?" in frame)
    seg = rainbow_segment(28, 14, 0)
    check("rainbow: 14 gefüllt (█) + 14 leer (░)", seg.count("█") == 14 and seg.count("░") == 14)
    check("rainbow enthält 256-Farbcodes", "38;5;" in seg)
    check("parse_key ↑", parse_key(b"\x1b[A") == "up")
    check("parse_key ↓", parse_key(b"\x1b[B") == "down")
    check("parse_key Enter", parse_key(b"\r") == "select")
    check("parse_key q", parse_key(b"q") == "quit")
    check("parse_key sonst -> None", parse_key(b"x") is None)
    print("--- fertig ---")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return

    import termios
    import tty
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        sys.stderr.write("select_kassette: kein TTY — bitte interaktiv starten "
                         "(oder zentrale-laptop / zentrale-tui direkt).\n")
        sys.exit(1)

    old = termios.tcgetattr(fd)
    choice = None
    try:
        tty.setraw(fd)
        sys.stdout.write(ALT_ON + HIDE_CUR)
        sys.stdout.flush()
        choice = menu_loop(fd)
    finally:
        # Terminal IMMER zurücksetzen, bevor irgendwas anderes passiert.
        sys.stdout.write(SHOW_CUR + ALT_OFF)
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    if choice is None:
        sys.stdout.write("abgebrochen.\n")
        return
    launch(choice)   # spielt Loader, dann exec in die Kassette


if __name__ == "__main__":
    main()
