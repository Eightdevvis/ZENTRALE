#!/usr/bin/env python3
# tui/boot_loader.py
#
# ════════════════════════════════════════════════════════════════════════
# ZENTRALE — Blumenwind-Ladeanimation für den DIREKT-Start
# ------------------------------------------------------------------------
# `zentrale-tui` / `zentrale-laptop` überspringen das Kassetten-Menü (und
# damit den Regenbogen-Ladebalken aus tui/select_kassette.py). Trotzdem läuft
# vor dem Start EIN Ding im Hintergrund: der Boot-Abgleich mit dem PC
# (zentrale-sync-boot). Bisher stand dort nur eine stumme Textzeile.
#
# Dieses Modul legt DA eine eigene Animation drunter: ein FELD über mehrere
# Zeilen, durch das ein langsamer Wind Blüten von rechts nach links treibt.
# Darunter steht, WAS gerade passiert (z.B. »Abgleich mit PC …«). Die
# 100 %-Logik des Regenbogens gibt es hier nicht — es gibt keinen Fortschritt
# zu messen, nur »läuft noch« vs. »fertig«: der Wind weht, bis der Sync-Prozess
# durch ist (mind. ein paar Sekunden, damit man ihn auch bei blitzschnellem
# Sync sieht), dann trägt er die Blüten weg.
#
# WIE der Wind entsteht (drei Zutaten, alle deterministisch aus dem Tick):
#  • PARTIKEL statt Spalten-Rauschen. Jede Blüte ist ein eigenes Ding mit
#    fester Startposition, Farbe und Glyph; sie wandert mit BRUCHTEILEN einer
#    Spalte pro Tick (~0,1–0,6). Das alte Modell würfelte pro Spalte neu und
#    schob den ganzen Streifen 1 Spalte/Tick — dadurch wirkte es hektisch und
#    »zusammengedetscht«. Jetzt gleitet dieselbe Blüte sichtbar durchs Bild.
#  • BÖEN. Die zurückgelegte Strecke ist Grundtempo + zwei überlagerte Sinus
#    (_drift). Die Ableitung bleibt immer positiv → nie rückwärts, aber es gibt
#    Anziehen und Abflauen. Das ist der »Wind«, nicht das Fließband.
#  • WIRBEL. Jede Blüte schwingt zusätzlich vertikal (Sinus über ihre eigene
#    x-Position + Eigenphase), pro Ebene unterschiedlich stark → sie taumeln
#    durchs Feld statt auf Schienen zu fahren. Drei Ebenen (Blütenstaub weit
#    hinten, kleine Blüten in der Mitte, kräftige Blüten vorn) laufen
#    unterschiedlich schnell → Parallax/Tiefe.
#
# BEWUSST nur stdlib (ANSI + math, kein curses) — wie select_kassette.py. Es
# gibt für sowas fertige Terminal-Engines (asciimatics-Partikelsystem,
# terminaltexteffects), aber für zwei Sekunden Bootbild lohnt keine Dependency
# in einem Offline-Setup. Die Render-Funktionen (flower_field, status_line)
# sind PUR und ohne TTY unit-testbar (--selftest bzw. tests/test_boot_loader.py).
# play() ist der einzige Teil mit I/O/Timing und wird beim Selbsttest nicht
# angefasst. Angucken ohne Sync: `python3 tui/boot_loader.py --demo`.
#
# Aufruf (aus ~/.local/bin/zentrale-launch, silent_boot_sync):
#     python3 tui/boot_loader.py "Abgleich mit PC"
# Startet zentrale-sync-boot im Hintergrund, animiert bis es fertig ist,
# räumt das Feld sauber weg und kehrt zurück. Kein TTY → still abgleichen
# (keine Steuerzeichen ins Log). Wirft nie, blockiert den Start nie länger als
# der Sync selbst (plus die kurze Mindestspielzeit).
# ════════════════════════════════════════════════════════════════════════

import math
import os
import sys
import time

# ── ANSI-Helfer ────────────────────────────────────────────────────────────
ESC = "\x1b"
RESET = ESC + "[0m"
HIDE_CUR = ESC + "[?25l"
SHOW_CUR = ESC + "[?25h"
CLR_LINE = ESC + "[K"       # bis Zeilenende löschen


def c256(i):
    return "%s[38;5;%dm" % (ESC, i)


def up(n):
    """n Zeilen hoch (Spalte bleibt). n <= 0 → nichts."""
    return (ESC + "[%dA" % n) if n > 0 else ""


# ── Blumen-Palette ──────────────────────────────────────────────────────────
# Drei Ebenen, von hinten nach vorn: winziger Blütenstaub, kleine Blüten,
# kräftige Blüten. Vorn groß und satt, hinten klein und blass → Tiefe.
FLOWERS = ["✿", "❀", "❁", "✾", "❃", "❋", "✽", "✼", "⚘", "❆", "✻"]
SMALL_FLOWERS = ["✽", "✼", "✻", "✢", "❋", "✳", "⁕", "✤"]
PETALS = ["·", "*", "˚", "°", ".", "✢"]

# Süßliche, leicht variierende Farben (256-Farben): Rosa, Lavendel, Pfirsich,
# Creme, zartes Gelb. Kräftig für die vorderen Blüten …
FLOWER_COLORS = [218, 219, 225, 224, 217, 223, 230, 189, 183,
                 182, 175, 216, 213, 207, 211, 229, 195]
# … eine Stufe zurückgenommen für die mittlere Ebene …
MID_COLORS = [225, 224, 189, 183, 218, 223, 195, 230, 182]
# … und blass/gedämpft für den Blütenstaub ganz hinten.
PETAL_COLORS = [225, 224, 189, 183, 146, 152, 230, 254, 195]

# Ebenen: n = Blüten pro Referenzfeld (siehe _count), speed = Anteil am
# Grundtempo, swirl = wie stark sie vertikal taumeln, spin = ob der Glyph
# beim Fliegen umklappt (nur vorn/Mitte, sonst wird's unruhig).
LAYERS = (
    {"n": 34, "speed": 0.34, "glyphs": PETALS,        "colors": PETAL_COLORS,  "swirl": 0.5, "spin": 0},
    {"n": 22, "speed": 0.64, "glyphs": SMALL_FLOWERS, "colors": MID_COLORS,    "swirl": 1.0, "spin": 1},
    {"n": 16, "speed": 1.00, "glyphs": FLOWERS,       "colors": FLOWER_COLORS, "swirl": 1.5, "spin": 1},
)

# Referenzfeld, auf das sich LAYERS["n"] bezieht — bei anderer Größe wird die
# Blütenzahl flächenproportional skaliert, damit die Dichte gleich bleibt.
REF_W, REF_H = 64.0, 6.0

BASE_STEP = 0.34    # Spalten pro Tick auf der vordersten Ebene (ohne Böe)
MARGIN = 6          # unsichtbarer Rand links/rechts, in dem Blüten ein-/austreten


def _noise(x):
    """Deterministischer Pseudo-Zufall in [0, 1) aus einem ganzzahligen Seed.

    Kein random-Modul → die Animation ist eine PURE Funktion von (Größe, Tick)
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


def _drift(tick, speed):
    """Zurückgelegte Strecke (Spalten) einer Ebene bis zum Tick — mit Böen.

    Grundtempo plus zwei überlagerte Sinus. Wichtig: die Ableitung
    (BASE_STEP ± 2.6/23 ± 1.4/9.5 ≈ 0.34 ± 0.26) bleibt POSITIV — der Wind
    zieht an und flaut ab, weht aber nie rückwärts.
    """
    t = float(tick)
    gust = 2.6 * math.sin(t / 23.0) + 1.4 * math.sin(t / 9.5 + 1.7)
    return (BASE_STEP * t + gust) * speed


def _count(layer, width, height):
    """Blütenzahl einer Ebene, flächenproportional zum Referenzfeld."""
    scale = (width * height) / (REF_W * REF_H)
    return max(1, int(round(layer["n"] * scale)))


def flower_field(width, height, tick, fade=1.0):
    """Ein Frame des Blumenwinds als Liste von `height` ANSI-Zeilen — PURE.

    Jede Zeile ist sichtbar exakt `width` Spalten breit (jedes Zeichen belegt
    genau eine Spalte). `fade` in [0, 1] blendet die Blüten anteilig ein/aus
    (0 = leeres Feld, 1 = volle Dichte) — dafür bekommt jede Blüte eine feste
    Schwelle, so dass sie beim Auf- und Abblenden einzeln erscheint bzw. weg-
    geweht wird, statt dass alles gleichzeitig umspringt.
    """
    width = max(0, int(width))
    height = max(0, int(height))
    tick = int(tick)
    try:
        fade = min(1.0, max(0.0, float(fade)))
    except Exception:
        fade = 1.0
    if width == 0 or height == 0:
        return [RESET for _ in range(height)]

    span = width + 2 * MARGIN          # Umlaufbreite inkl. unsichtbarem Rand
    grid = [[None] * width for _ in range(height)]

    # Von hinten nach vorn zeichnen (Maler-Algorithmus): vordere Blüten
    # überdecken den Blütenstaub dahinter.
    for li, layer in enumerate(LAYERS):
        n = _count(layer, width, height)
        drift = _drift(tick, layer["speed"])
        for i in range(n):
            seed = li * 9173 + i * 131 + 17
            if _noise(seed + 55501) >= fade:   # feste Schwelle → sanftes Ein-/Ausblenden
                continue
            # Waagerecht: feste Startposition, driftet nach links, läuft im
            # unsichtbaren Rand um (der Sprung passiert außerhalb des Bildes).
            x = (_noise(seed) * span - drift) % span - MARGIN
            col = int(math.floor(x))
            if col < 0 or col >= width:
                continue
            # Senkrecht: Grundhöhe (leicht über den Rand hinaus, damit Blüten
            # oben/unten ein- und austreten) + Taumeln.
            y0 = _noise(seed + 7717) * (height + 2.0) - 1.0
            phase = _noise(seed + 4231) * 6.283
            y = y0 + layer["swirl"] * math.sin(x * 0.21 + phase + tick * 0.045)
            row = int(math.floor(y + 0.5))
            if row < 0 or row >= height:
                continue
            # Glyph: fest gewählt; bei spin klappt er im Flug langsam um
            # (jede dritte Blüte), als würde sie sich in der Luft drehen.
            spin = layer["spin"] and (_noise(seed + 991) < 0.34)
            g_seed = seed + 3 + (tick // 9 if spin else 0)
            grid[row][col] = (c256(_pick(layer["colors"], seed + 11))
                              + _pick(layer["glyphs"], g_seed))

    return ["".join(c if c else " " for c in row) + RESET for row in grid]


# Ein zartes Blümchen als »Läuft-noch«-Marker vor der Statuszeile, das die
# Farbe wechselt (dezenter Puls, kein Spinner-Gezappel).
_MARKER_COLORS = [218, 224, 230, 189, 225, 217]


def status_line(label, tick):
    """Die Zeile UNTER dem Feld: ein pulsierendes Blümchen + Text — PURE.

    Sagt, WAS gerade passiert (z.B. »Abgleich mit PC«). Die drei Punkte
    »wandern« (…/·· ·/· ··) für ein leises Lebenszeichen. Puls und Punkte
    laufen bewusst auf geteilten Ticks — die Animation ist langsam, da darf
    die Statuszeile nicht drüber hektisch blinken.
    """
    label = "" if label is None else str(label)
    mark = c256(_MARKER_COLORS[(tick // 3) % len(_MARKER_COLORS)]) + "✿" + RESET
    dots = ["   ", ".  ", ".. ", "..."][(tick // 4) % 4]
    dim = c256(245)
    return "%s  %s%s%s%s" % (mark, dim, label, RESET, c256(245) + " " + dots + RESET)


# ── Terminalgröße / Sync-Prozess (I/O — nicht Teil des Selbsttests) ─────────
def _field_size():
    """Feldgröße: möglichst breit (der Wind braucht Weg), Höhe je nach Platz."""
    try:
        import shutil
        size = shutil.get_terminal_size((80, 24))
        cols, rows = size.columns, size.lines
    except Exception:
        cols, rows = 80, 24
    width = max(24, min(cols - 4, 110))
    # Feld + Statuszeile + Luft nach unten müssen ins Terminal passen.
    height = max(3, min(7, rows - 4))
    return width, height


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


# Ein-/Ausblenden: über so viele Ticks fährt die Blütendichte hoch bzw. runter.
FADE_IN = 10
FADE_OUT = 9


def play(label, wait_proc=None, min_frames=26, interval=0.07, out=None,
         size=None):
    """Feld + Statuszeile animieren, bis wait_proc fertig ist.

    height+1 Zeilen, in-place neu gezeichnet: oben das Blumenfeld, drunter die
    Statuszeile. Der Wind blendet über FADE_IN Ticks auf, weht mind. min_frames
    (damit man die Animation auch bei einem blitzschnellen Sync sieht) und
    darüber hinaus, solange wait_proc noch lebt; zum Schluss trägt er die Blüten
    über FADE_OUT Ticks weg. Danach werden alle Zeilen sauber gelöscht — die
    Folge-Ausgabe (Backend-Start) beginnt an sauberer Stelle.

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

    width, height = size if size else _field_size()

    def draw(tick, fade):
        rows = flower_field(width, height, tick, fade)
        frame = "\r" + "".join("  " + r + CLR_LINE + "\n" for r in rows)
        frame += "  " + status_line(label, tick) + CLR_LINE + "\r" + up(height)
        out.write(frame)
        out.flush()

    tick = 0
    try:
        # Platz RESERVIEREN, bevor wir anfangen: height+1 Leerzeilen ausgeben
        # und wieder hochspringen. Steht der Cursor unten am Bildschirmrand,
        # scrollt das Terminal dabei EINMAL sauber — täten wir das erst beim
        # Zeichnen, liefe der Rücksprung nach oben ins Leere und es blieben
        # Blüten-Fragmente stehen.
        out.write(HIDE_CUR + "\n" * (height + 1) + up(height + 1))
        out.flush()
        # Hauptlauf: aufblenden, wehen, bis Sync durch UND Mindestzeit um ist.
        while True:
            draw(tick, min(1.0, (tick + 1) / float(FADE_IN)))
            time.sleep(interval)
            tick += 1
            done = (wait_proc is None) or (wait_proc.poll() is not None)
            if tick >= min_frames and done:
                break
        # Abspann: der Wind nimmt die Blüten mit.
        for k in range(FADE_OUT):
            draw(tick, 1.0 - (k + 1) / float(FADE_OUT))
            time.sleep(interval)
            tick += 1
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
    finally:
        # Alle Zeilen löschen, Cursor zurück nach oben links, sichtbar machen.
        try:
            out.write("\r" + CLR_LINE
                      + "".join("\n" + CLR_LINE for _ in range(height))
                      + "\r" + up(height) + SHOW_CUR)
            out.flush()
        except Exception:
            pass


def run(label="Abgleich mit PC"):
    """Sync starten, dahinter den Blumenwind spielen, aufräumen."""
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

    field = flower_field(60, 6, 3)
    check("flower_field liefert height Zeilen", len(field) == 6)
    check("flower_field sichtbare Breite == 60",
          all(len(strip(r)) == 60 for r in field))
    check("flower_field enthält 256-Farbcodes",
          any("38;5;" in r for r in field))
    glyphs = set(FLOWERS) | set(SMALL_FLOWERS) | set(PETALS)
    check("flower_field enthält Blumen/Blütenstaub",
          any(g in r for r in field for g in glyphs))
    check("flower_field deterministisch (gleicher Tick → gleich)",
          flower_field(60, 6, 3) == flower_field(60, 6, 3))
    check("flower_field animiert (über 20 Ticks)",
          len({tuple(flower_field(60, 6, t)) for t in range(20)}) >= 10)
    check("flower_field Breite 0 → leere Zeilen",
          all(strip(r) == "" for r in flower_field(0, 4, 7)))
    check("flower_field fade=0 → leeres Feld",
          all(strip(r).strip() == "" for r in flower_field(60, 6, 3, 0.0)))
    # »langsam«: von Tick zu Tick darf sich nur ein kleiner Teil der Zellen
    # ändern — sonst zappelt es wieder wie das alte Spalten-Rauschen.
    a = "".join(strip(r) for r in flower_field(60, 6, 40))
    b = "".join(strip(r) for r in flower_field(60, 6, 41))
    diff = sum(1 for x, y in zip(a, b) if (x == " ") != (y == " "))
    check("flower_field driftet sanft (%d von %d Zellen wechseln)" % (diff, len(a)),
          diff < 0.12 * len(a))
    # »luftig«: nicht zusammengedetscht, aber auch nicht leer.
    fill = sum(1 for ch in a if ch != " ") / float(len(a))
    check("flower_field luftig (8-30 %% belegt), ist %.0f %%" % (fill * 100),
          0.08 <= fill <= 0.30)
    st = status_line("Abgleich mit PC", 2)
    check("status_line enthält das Label", "Abgleich mit PC" in strip(st))
    check("status_line hat pulsierendes Blümchen (✿)", "✿" in st)
    check("status_line robust bei None-Label", isinstance(status_line(None, 0), str))
    # darf-NIE-werfen: gemeine Argumente
    threw = False
    for w in (-5, 0, 1, 3, 200):
        for h in (-2, 0, 1, 9):
            for t in (0, 1, 7, 9999, -3):
                try:
                    flower_field(w, h, t, 0.5)
                    status_line("x", t)
                except Exception:
                    threw = True
    check("flower_field/status_line werfen nie", not threw)
    print("--- fertig ---")


def demo(seconds=9.0):
    """Die Animation ohne Sync anschauen (python3 tui/boot_loader.py --demo)."""
    frames = max(1, int(seconds / 0.07))
    play("Vorschau Blumenwind", wait_proc=None, min_frames=frames)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    if "--demo" in sys.argv:
        demo()
        return
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    label = args[0] if args else "Abgleich mit PC"
    run(label)


if __name__ == "__main__":
    main()
