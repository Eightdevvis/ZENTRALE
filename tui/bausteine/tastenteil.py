# tui/bausteine/tastenteil.py
#
# Bausteine mit eigener Tastentabelle (2026-10-11, Sasha: EINE Tabelle je
# Programm, aus der Verteilung und Leiste ganz unten lesen). Ein Baustein
# trägt `TASTEN` als Klassenattribut in der Kurzform von
# tui/ansichten/tasten.py — {ansicht: [(taste, aktion[, text])]}, Format und
# Beschriftungen aus core/tastentabelle.py —, sagt mit `ansicht()`, welche
# gerade offen ist, und hat je Aktion eine Methode `aktion_<name>(taste)`
# (taste = neutraler Name: "up", "a", "enter" …; bei „type" das Zeichen).
#
# Eine Ansicht bindet ihn mit `Tasten.zusammen` ein (Desk: Canvas, Modale);
# dann verteilt SIE, und die Leiste zeigt seine Einträge. Bausteine
# importieren nichts aus ansichten/ (bausteine/__init__.py) — darum steht
# hier der kleine Rest für Gastgeber OHNE Tabelle: `verteilen(teil, ch)`
# nimmt einen curses-Code und geht über DIESELBE Tabelle (Kalender →
# Stylebox, Tests). Ohne Alt-Tasten (die liest nur tasten.py).

import curses

import tastentabelle as tt              # core/tastentabelle.py (Pfad: bausteine/__init__.py)

FREITEXT, JEDE = tt.FREITEXT, tt.JEDE

# curses-Code ↔ neutraler Name — nur, was Bausteine brauchen (das volle
# Gegenstück steht in tui/ansichten/tasten.py).
_NAME = {
    curses.KEY_UP: "up", curses.KEY_DOWN: "down",
    curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
    curses.KEY_BTAB: "shift+tab", curses.KEY_BACKSPACE: "backspace",
    127: "backspace", 8: "backspace", curses.KEY_DC: "del",
    curses.KEY_HOME: "home", curses.KEY_END: "end",
    curses.KEY_PPAGE: "pgup", curses.KEY_NPAGE: "pgdn",
    10: "enter", 13: "enter", curses.KEY_ENTER: "enter",
    9: "tab", 32: "space", 27: "esc",
}
_CODE = {"up": curses.KEY_UP, "down": curses.KEY_DOWN, "left": curses.KEY_LEFT,
         "right": curses.KEY_RIGHT, "shift+tab": curses.KEY_BTAB,
         "backspace": curses.KEY_BACKSPACE, "del": curses.KEY_DC,
         "home": curses.KEY_HOME, "end": curses.KEY_END,
         "pgup": curses.KEY_PPAGE, "pgdn": curses.KEY_NPAGE,
         "enter": 10, "tab": 9, "space": 32, "esc": 27}


def name(ch):
    """curses-Code → neutraler Name oder None."""
    if ch in _NAME:
        return _NAME[ch]
    if 1 <= ch <= 26:
        return "ctrl+" + chr(ch + 96)
    if 33 <= ch <= 126:
        return chr(ch)
    return None


def code(n):
    """Neutraler Name (oder getipptes Zeichen) → curses-Code, für Teile,
    die innen mit Codes rechnen (Textfeld)."""
    if n in _CODE:
        return _CODE[n]
    if n.startswith("ctrl+"):
        return ord(n[5]) - 96
    return ord(n)


def aktion(tabelle, ansicht, n):
    """(aktion, taste) für den Namen n in der Ansicht, sonst (None, n).
    Freitext bekommt das Zeichen (Leertaste = " ")."""
    liste = tabelle.get(ansicht) or []
    frei = jede = None
    for e in liste:
        if e[0] == FREITEXT:
            frei = e[1]
        elif e[0] == JEDE:
            jede = e[1]
        elif n in tt.namen(e[0]):
            return e[1], n
    if frei and n is not None and (len(n) == 1 or n == "space"):
        return frei, " " if n == "space" else n
    return (jede, n) if (jede and n is not None) else (None, n)


def weiter(teil, n):
    """Den neutralen Namen n an die Aktion geben, die er in der offenen
    Ansicht des Teils hat (auch für Teile in Teilen: Stylebox → Farbwähler)."""
    a, taste = aktion(teil.TASTEN, teil.ansicht(), n)
    return getattr(teil, "aktion_" + a)(taste) if a else None


def verteilen(teil, ch):
    """curses-Code ch über die Tabelle des Teils → Rückgabe der Aktion."""
    if ch is None or ch < 0:
        return None
    return weiter(teil, name(ch))
