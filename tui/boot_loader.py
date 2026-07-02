#!/usr/bin/env python3
# tui/boot_loader.py
#
# ════════════════════════════════════════════════════════════════════════
# ZENTRALE — Blumenrauschen-Ladeanimation für den DIREKT-Start
# ------------------------------------------------------------------------
# `zentrale-tui` / `zentrale-laptop` überspringen das Kassetten-Menü (und
# damit den Regenbogen-Ladebalken aus tui/select_kassette.py). Trotzdem läuft
# vor dem Start EIN Ding im Hintergrund: der Boot-Abgleich mit dem PC
# (zentrale-sync-boot). Bisher stand dort nur eine stumme Textzeile.
#
# Dieses Modul legt DA eine eigene kleine Animation drunter: ein schmaler
# STREIFEN, in dem viele Blumen-Glyphe wie vom Winde verweht umherfliegen —
# in süßlichen, leicht variierenden Farben (Rosa/Lavendel/Pfirsich/Creme).
# Zwei driftende Ebenen (Parallax) + ein Flattern (Blumen blinken kurz weg)
# geben das »Rauschen«. Darunter steht, WAS gerade passiert (z.B. »Abgleich
# mit PC …«). Die 100 %-Logik des Regenbogens gibt es hier nicht — es gibt
# keinen Fortschritt zu messen, nur »läuft noch« vs. »fertig«: der Streifen
# rauscht, bis der Sync-Prozess durch ist (mind. ein paar Frames, damit man
# ihn auch bei blitzschnellem Sync sieht).
#
# BEWUSST nur stdlib (ANSI, kein curses) — wie select_kassette.py. Die Render-
# Funktionen (flower_strip, status_line) sind PUR und ohne TTY unit-testbar
# (--selftest bzw. tests/test_boot_loader.py). play() ist der einzige Teil mit
# I/O/Timing und wird beim Selbsttest nicht angefasst.
#
# Aufruf (aus ~/.local/bin/zentrale-launch, silent_boot_sync):
#     python3 tui/boot_loader.py "Abgleich mit PC"
# Startet zentrale-sync-boot im Hintergrund, animiert bis es fertig ist,
# räumt den Streifen sauber weg und kehrt zurück. Kein TTY → still abgleichen
# (keine Steuerzeichen ins Log). Wirft nie, blockiert den Start nie länger als
# der Sync selbst.
# ════════════════════════════════════════════════════════════════════════

import os
import sys
import time

# ── ANSI-Helfer ────────────────────────────────────────────────────────────
ESC = "\x1b"
RESET = ESC + "[0m"
HIDE_CUR = ESC + "[?25l"
SHOW_CUR = ESC + "[?25h"
CLR_LINE = ESC + "[K"       # bis Zeilenende löschen
UP_1 = ESC + "[1A"          # eine Zeile hoch (Spalte bleibt)


def c256(i):
    return "%s[38;5;%dm" % (ESC, i)


# ── Blumen-Palette ──────────────────────────────────────────────────────────
# Vordergrund: kräftige Blüten, die driften. Hintergrund: kleine Blütenstaub-
# Zeichen, die langsamer und blasser durchziehen (Parallax → Tiefe/Wind).
FLOWERS = ["✿", "❀", "❁", "✾", "❃", "❋", "✽", "✼", "⚘", "❆", "✻"]
PETALS = ["·", "*", "˚", "°", ".", "✢"]

# Süßliche, leicht variierende Farben (256-Farben): Rosa, Lavendel, Pfirsich,
# Creme, zartes Gelb. Kräftig für die Blüten …
FLOWER_COLORS = [218, 219, 225, 224, 217, 223, 230, 189, 183,
                 182, 175, 216, 213, 207, 211, 229, 195]
# … blasser/gedämpfter für den driftenden Blütenstaub im Hintergrund.
PETAL_COLORS = [225, 224, 189, 183, 146, 152, 230, 254, 195]


def _noise(x):
    """Deterministischer Pseudo-Zufall in [0, 1) aus einem ganzzahligen Seed.

    Kein random-Modul → die Animation ist eine PURE Funktion von (Spalte, Tick)
    und damit exakt reproduzierbar/testbar. Ein simpler Integer-Hash reicht,
    er muss nur gut »verwürfeln«.
    """
    x = int(x) & 0xFFFFFFFF
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    x = x ^ (x >> 16)
    return (x & 0xFFFF) / 65536.0


def _pick(seq, seed):
    """Ein Element aus seq, deterministisch anhand des Seeds."""
    return seq[int(_noise(seed) * len(seq)) % len(seq)]


def flower_strip(width, tick):
    """Ein Frame des Blumenrauschens als ANSI-String — PURE Funktion.

    Sichtbare Breite == width (jedes Zeichen belegt genau eine Spalte). Zwei
    driftende Ebenen:
      • Vordergrund: kräftige Blüten, wandern 1 Spalte/Tick nach links; ein
        »Flattern« (an den Tick gekoppelt) blendet einzelne kurz aus → es
        flimmert wie vom Wind bewegt, statt stur wie ein Fließband zu laufen.
      • Hintergrund: blasser Blütenstaub, driftet halb so schnell (1 Spalte
        pro 2 Ticks) → Parallax-Tiefe. Wird nur dort sichtbar, wo vorne Lücke
        ist.
    """
    width = max(0, int(width))
    tick = int(tick)
    cells = []
    for i in range(width):
        f = i + tick                       # Vordergrund-Position (schneller Drift)
        present = _noise(f * 2 + 7) < 0.42          # ~42 % Blüten-Dichte
        flutter = _noise((f * 3) ^ (tick + 101)) < 0.86   # ab und zu wegblinken
        if present and flutter:
            cells.append(c256(_pick(FLOWER_COLORS, f * 7 + 11))
                         + _pick(FLOWERS, f * 5 + 3))
            continue
        b = i + tick // 2                  # Hintergrund-Position (halber Drift)
        if _noise(b * 2 + 41) < 0.20:
            cells.append(c256(_pick(PETAL_COLORS, b * 7 + 17))
                         + _pick(PETALS, b * 5 + 13))
        else:
            cells.append(" ")
    return "".join(cells) + RESET


# Ein zartes Blümchen als »Läuft-noch«-Marker vor der Statuszeile, das die
# Farbe wechselt (dezenter Puls, kein Spinner-Gezappel).
_MARKER_COLORS = [218, 224, 230, 189, 225, 217]


def status_line(label, tick):
    """Die Zeile UNTER dem Streifen: ein pulsierendes Blümchen + Text — PURE.

    Sagt, WAS gerade passiert (z.B. »Abgleich mit PC«). Die drei Punkte
    »wandern« (…/·· ·/· ··) für ein leises Lebenszeichen, ohne zu hektisch zu
    wirken.
    """
    label = "" if label is None else str(label)
    mark = c256(_MARKER_COLORS[tick % len(_MARKER_COLORS)]) + "✿" + RESET
    dots = ["   ", ".  ", ".. ", "..."][(tick // 2) % 4]
    dim = c256(245)
    return "%s  %s%s%s%s" % (mark, dim, label, RESET, c256(245) + " " + dots + RESET)


# ── Terminalbreite / Sync-Prozess (I/O — nicht Teil des Selbsttests) ────────
def _strip_width():
    """Gute Streifenbreite: an die Terminalbreite angelehnt, gedeckelt."""
    try:
        import shutil
        cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        cols = 80
    return max(20, min(46, cols - 4))


def _start_sync():
    """zentrale-sync-boot im Hintergrund starten (Ausgabe ins Log).

    Gibt das Popen-Objekt oder None (Tool fehlt / abgeschaltet). Best-effort,
    wirft nie — genau wie der Boot-Sync in select_kassette.py.
    """
    if os.environ.get("ZENTRALE_NO_BOOT_SYNC") == "1":
        return None
    import shutil
    import subprocess
    exe = shutil.which("zentrale-sync-boot")
    if not exe:
        return None
    try:
        logf = open("/tmp/zentrale-sync-boot.log", "wb")
        return subprocess.Popen([exe], stdout=logf, stderr=logf,
                                stdin=subprocess.DEVNULL)
    except Exception:
        return None


def play(label, wait_proc=None, min_frames=16, interval=0.06, out=None):
    """Streifen + Statuszeile animieren, bis wait_proc fertig ist.

    Zwei Zeilen, in-place neu gezeichnet: oben der Blumenstreifen, drunter die
    Statuszeile. Läuft mind. min_frames (damit man die Animation auch bei einem
    blitzschnellen Sync sieht) und darüber hinaus, solange wait_proc noch lebt.
    Am Ende werden beide Zeilen sauber gelöscht — die Folge-Ausgabe (Backend-
    Start) beginnt dann an sauberer Stelle.

    Kein TTY → gar nicht animieren (nur auf den Prozess warten), damit keine
    Steuerzeichen in ein Log/Pipe laufen. Wirft nie.
    """
    if out is None:
        out = sys.stdout
    isatty = False
    try:
        isatty = out.isatty()
    except Exception:
        isatty = False

    if not isatty:
        if wait_proc is not None:
            try:
                wait_proc.wait()
            except Exception:
                pass
        return

    width = _strip_width()
    tick = 0
    try:
        out.write(HIDE_CUR)
        out.flush()
        while True:
            frame = ("\r  " + flower_strip(width, tick) + CLR_LINE
                     + "\n  " + status_line(label, tick) + CLR_LINE + UP_1)
            out.write(frame)
            out.flush()
            time.sleep(interval)
            tick += 1
            done = (wait_proc is None) or (wait_proc.poll() is not None)
            if tick >= min_frames and done:
                break
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
    finally:
        # Beide Zeilen löschen, Cursor an den Zeilenanfang oben, sichtbar machen.
        try:
            out.write("\r" + CLR_LINE + "\n" + CLR_LINE + "\r" + UP_1 + SHOW_CUR)
            out.flush()
        except Exception:
            pass


def run(label="Abgleich mit PC"):
    """Sync starten, dahinter das Blumenrauschen spielen, aufräumen."""
    proc = _start_sync()
    try:
        play(label, wait_proc=proc)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=90)
            except Exception:
                pass


# ── Selbsttest (kein TTY, kein Sync, kein Timing) ───────────────────────────
def selftest():
    import re
    strip = lambda s: re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)

    def check(label, cond):
        print(("OK  " if cond else "FAIL") + "  " + label)

    frame = flower_strip(40, 3)
    check("flower_strip sichtbare Breite == 40",
          len(strip(frame)) == 40)
    check("flower_strip enthält 256-Farbcodes", "38;5;" in frame)
    glyphs = set(FLOWERS) | set(PETALS)
    check("flower_strip enthält Blumen/Blütenstaub",
          any(g in frame for g in glyphs))
    check("flower_strip deterministisch (gleicher Tick → gleich)",
          flower_strip(40, 3) == flower_strip(40, 3))
    check("flower_strip animiert (Tick 3 ≠ Tick 4)",
          flower_strip(40, 3) != flower_strip(40, 4))
    check("flower_strip Breite 0 → nur Reset",
          strip(flower_strip(0, 7)) == "")
    st = status_line("Abgleich mit PC", 2)
    check("status_line enthält das Label", "Abgleich mit PC" in strip(st))
    check("status_line hat pulsierendes Blümchen (✿)", "✿" in st)
    check("status_line robust bei None-Label", isinstance(status_line(None, 0), str))
    # darf-NIE-werfen: gemeine Argumente
    threw = False
    for w in (-5, 0, 1, 3, 200):
        for t in (0, 1, 7, 9999, -3):
            try:
                flower_strip(w, t)
                status_line("x", t)
            except Exception:
                threw = True
    check("flower_strip/status_line werfen nie", not threw)
    print("--- fertig ---")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    label = args[0] if args else "Abgleich mit PC"
    run(label)


if __name__ == "__main__":
    main()
