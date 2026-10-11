# tui/echtfarbe.py
#
# 24-Bit-Farbe für einzelne Flächen, ohne die TUI umzustellen (2026-10-11).
#
# Warum (2026-10-11): die TUI läuft mit TERM=xterm-256color bzw.
# tmux-256color, curses kennt also 256 Farben — jeder Farbton des
# Farbwählers landete im 6-stufigen xterm-Würfel (gemessen: bei Zoom 16 nur
# noch 4 Farben im ganzen Kreis). TERM=xterm-direct gibt curses zwar 24 Bit,
# deutet dann aber die Palettennummern der Themes als RGB (alles wird blau).
# Deshalb der übliche Weg anderer TUIs: curses zeichnet an der Stelle nur
# einen gleichbleibenden Platzhalter (Leerzeichen im Theme-Grund), und
# NACH curses' refresh schreiben wir die Fläche selbst mit 38;2/48;2-SGR
# ins Terminal. Weil der Platzhalter von Bild zu Bild gleich bleibt, fasst
# curses die Zellen nicht an — kein Flackern. Verschwindet oder wandert
# eine Fläche, lässt redrawln curses die Zeilen ganz neu malen — keine
# Geisterbilder.
#
# Einstellung `farbe_truecolor`: auto | an | aus — aus der Umgebung
# (ZENTRALE_FARBE_TRUECOLOR) oder der Datei ~/.config/zentrale/farbe_truecolor
# (ein Wort, wie ~/.config/zentrale/theme). auto = an, wenn COLORTERM
# truecolor oder 24bit sagt (xfce4-terminal/VTE setzen das; tmux reicht es
# mit `terminal-features *:RGB` durch).
# Doku: memory/hub/bausteine_farbe_stil.md.

import os
import time

AN = ("an", "on", "ja", "1", "true", "yes")
AUS = ("aus", "off", "nein", "0", "false", "no")
AUFFRISCHEN_S = 2.0          # unverändert trotzdem neu schreiben (falls curses doch etwas überschrieb)


def einstellung(name, umgebung=None, ordner=None):
    """Ein Wort aus ZENTRALE_<NAME> oder ~/.config/zentrale/<name>; sonst ""."""
    umgebung = os.environ if umgebung is None else umgebung
    wert = umgebung.get("ZENTRALE_" + name.upper(), "")
    if not wert.strip():
        ordner = ordner or os.path.join(os.path.expanduser("~"), ".config", "zentrale")
        try:
            with open(os.path.join(ordner, name), encoding="utf-8") as f:
                wert = f.read()
        except OSError:
            wert = ""
    teile = wert.split()
    return teile[0].lower() if teile else ""


def truecolor_an(umgebung=None, ordner=None):
    """Darf/kann das Terminal 24 Bit? Einstellung schlägt Erkennung."""
    umgebung = os.environ if umgebung is None else umgebung
    wahl = einstellung("farbe_truecolor", umgebung, ordner) or "auto"
    if wahl in AN:
        return True
    if wahl in AUS:
        return False
    return umgebung.get("COLORTERM", "").strip().lower() in ("truecolor", "24bit")


def sgr(fg, bg):
    return "\x1b[38;2;%d;%d;%d;48;2;%d;%d;%dm" % (tuple(fg) + tuple(bg))


def sequenz(auftraege):
    """Auftrag (y, x, zeilen, maske) → Bytes: Cursor merken, je Zeile
    hinspringen, nur geänderte Farben setzen, am Ende Attribute und Cursor
    zurück (DECSC/DECRC sichern auch die SGR, die curses gerade glaubt)."""
    teile = ["\x1b7\x1b(B"]
    for y, x, zeilen, maske in auftraege:
        for r, zeile in enumerate(zeilen):
            springen, jetzt = True, None
            for c, (ch, fg, bg) in enumerate(zeile):
                if maske is not None and not maske[r][c]:
                    springen = True
                    continue
                if springen:
                    teile.append("\x1b[%d;%dH" % (y + r + 1, x + c + 1))
                    springen = False
                if (fg, bg) != jetzt:
                    teile.append(sgr(fg, bg))
                    jetzt = (fg, bg)
                teile.append(ch)
    teile.append("\x1b[0m\x1b8")
    return "".join(teile).encode("utf-8")


class Uebermalung:
    """Flächen eines Bildes sammeln und nach curses' refresh echt malen.

    malen(y, x, zeilen, platzhalter) während des Zeichnens; nach dem
    refresh nachmalen(stdscr). zeilen = [[(zeichen, fg_rgb, bg_rgb)]];
    platzhalter = was stdscr.inch an jeder Zelle liefern muss, damit wir
    dort malen dürfen — hat danach jemand anderes (ein Hinweis-Kasten) über
    die Fläche gezeichnet, bleibt seine Zelle stehen."""

    def __init__(self, schreiben=None, uhr=time.monotonic):
        self._schreiben = schreiben or (lambda b: os.write(1, b))
        self._uhr = uhr
        self.auftraege = []
        self._zuletzt = None          # (rechtecke, inhalt) des zuletzt Gemalten
        self._gemalt_t = 0.0

    def malen(self, y, x, zeilen, platzhalter=None):
        self.auftraege.append((y, x, tuple(tuple(z) for z in zeilen), platzhalter))

    def ungueltig(self):
        """Terminal ganz neu gemalt (Theme, Größe): beim nächsten Mal alles schreiben."""
        self._zuletzt = None

    @staticmethod
    def _rechtecke(auftraege):
        return tuple((y, x, len(z), max((len(r) for r in z), default=0))
                     for y, x, z, _m in auftraege)

    def nachmalen(self, stdscr):
        """Nach stdscr.refresh(): Flächen dieses Bildes schreiben."""
        jetzt, self.auftraege = self.auftraege, []
        alt = self._zuletzt
        rechtecke = self._rechtecke(jetzt)
        if alt is not None and alt[0] != rechtecke:
            # Fläche weg oder gewandert: curses malt deren Zeilen ganz neu,
            # sonst bliebe unser Bild dort stehen (curses hält es für leer).
            for y, _x, h, _w in alt[0]:
                try:
                    stdscr.redrawln(y, h)
                except Exception:
                    pass
            stdscr.refresh()
            alt = self._zuletzt = None
        if not jetzt:
            self._zuletzt = None
            return
        mit_maske = []
        for y, x, zeilen, platz in jetzt:
            maske = None
            if platz is not None:
                maske = tuple(tuple(_inch(stdscr, y + r, x + c) == platz
                                    for c in range(len(zeile)))
                              for r, zeile in enumerate(zeilen))
            mit_maske.append((y, x, zeilen, maske))
        inhalt = tuple(mit_maske)
        if (alt is not None and alt[1] == inhalt
                and self._uhr() - self._gemalt_t < AUFFRISCHEN_S):
            return
        self._schreiben(sequenz(inhalt))
        self._zuletzt = (rechtecke, inhalt)
        self._gemalt_t = self._uhr()


def _inch(stdscr, y, x):
    try:
        return stdscr.inch(y, x)
    except Exception:
        return None
