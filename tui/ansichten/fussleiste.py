# tui/ansichten/fussleiste.py
#
# Die Fußleiste ganz unten: NUR die Tasten, die im gerade fokussierten
# Fenster wirklich wirken. Sasha, 07.10.2026: „unten die leiste ist generell
# weird weil sie halt einfach nich stimmt meistens, da steht bspw IMMER space
# für ki auch wenn man in anderen fenstern is".
#
# Woher die Einträge kommen (eintraege):
#   1. Überlagerungen der Hauptschleife zuerst: Reminder-Kästchen, Hilfe,
#      offene Befehlszeile.
#   2. Eine Ansicht mit eigenem `tasten()` (heute der Chat — er hat Unter-
#      zustände wie Gesprächsliste, Gedächtnis, laufende Antwort) liefert sie
#      selbst. Eine NEUE Ansicht baut einfach `tasten()` und trägt sich in
#      ANSICHTEN unten ein.
#   3. Sonst die Tabelle befehle.CTX_KEYS zum Kontext aus current_ctx() —
#      dieselbe, die '/' zeigt. Eine Tabelle, zwei Anzeigen.
#   Wo die Befehlszeile aufgeht (kein Freitext-Feld), steht zuletzt „/ commands".
#
# Ein Eintrag ist (taste, was), englisch beschriftet (Sasha, 07.10.2026).
# codes() sagt, welche Tastencodes eine Beschriftung meint — davon lebt
# tests/test_fussleiste.py: jede beworbene Taste muss im Fenster etwas tun.

import curses

from .befehle import CTX_KEYS
from .fenster import current_ctx, in_text_entry

TRENNER = " · "

# Beschriftungen, die keine Taste sind („tippen"). Alles andere muss codes()
# kennen, sonst schlägt der Test an.
KEINE_TASTE = {"type", "any key"}

_PFEILE = {"↑": curses.KEY_UP, "↓": curses.KEY_DOWN,
           "←": curses.KEY_LEFT, "→": curses.KEY_RIGHT}
_NAMEN = {
    "enter": [10], "esc": [27], "tab": [9], "space": [32],
    "shift+tab": [curses.KEY_BTAB], "⌫": [curses.KEY_BACKSPACE],
    "del": [curses.KEY_DC], "home": [curses.KEY_HOME], "end": [curses.KEY_END],
    "pgup": [curses.KEY_PPAGE], "pgdn": [curses.KEY_NPAGE],
    "alt+enter": [27, 13], "f6": [curses.KEY_F6],
}


def _token(t):
    """Ein Wort einer Beschriftung -> [Tastenfolge, …]; None = unbekannt."""
    if t in _NAMEN:
        return [_NAMEN[t]]
    if t and all(c in _PFEILE for c in t):
        return [[_PFEILE[c]] for c in t]
    if t.startswith("alt+") and t[4:] and all(c in _PFEILE for c in t[4:]):
        return [[27, _PFEILE[c]] for c in t[4:]]
    if t.startswith("ctrl+") and len(t) == 6 and t[5].isalpha():
        return [[ord(t[5].lower()) - 96]]
    if len(t) == 1:
        return [[ord(t)]]
    return None


def codes(taste):
    """Beschriftung -> Liste von Tastenfolgen (jede eine Liste von Codes),
    die alle beworben sind. None: keine Taste (Befehl '/…' oder „type").
    Wirft ValueError bei einer Beschriftung, die niemand lesen kann."""
    if taste in KEINE_TASTE or (taste.startswith("/") and len(taste) > 1):
        return None
    folgen = []
    for wort in taste.split():
        # „a/s" = zwei Tasten; „/" allein ist die Taste Schrägstrich.
        for t in ([wort] if wort == "/" else wort.split("/")):
            f = _token(t)
            if f is None:
                raise ValueError("unbekannte taste %r in %r" % (t, taste))
            folgen += f
    return folgen


def tasten_der_zeile(eintraege):
    """Nur echte Tasten (die Fußleiste zeigt keine '/…'-Befehle)."""
    return [(t, w) for t, w in eintraege if not (t.startswith("/") and len(t) > 1)]


def text(eintraege):
    """„↑↓ select · enter open" — auch für Hinweise IN einem Kasten."""
    return TRENNER.join("%s %s" % (t, w) for t, w in eintraege)


def zeile(eintraege, breite):
    """Die Leiste auf `breite` Zeichen: ganze Einträge, nie ein halbes Wort.
    Passt schon der erste nicht, wird er hart gekürzt."""
    aus = ""
    for t, w in eintraege:
        stueck = "%s %s" % (t, w)
        kandidat = (aus + TRENNER + stueck) if aus else " " + stueck
        if len(kandidat) > breite:
            break
        aus = kandidat
    if not aus and eintraege:
        aus = (" %s %s" % eintraege[0])[:breite]
    return aus


def eintraege(u):
    """Was die Fußleiste gerade zeigt. u = das Bündel der Hauptschleife
    (zentrale_tui.run_ui): z, bz, erinnerung, chat …"""
    z, bz = u.z, u.bz
    if u.erinnerung.nag_active:
        return [("g", "log it"), ("any key", "dismiss")]
    if bz.help_latched:
        return [("any key", "close help")]
    if bz.cmd_mode:
        return [("enter", "run"), ("⌫", "delete"), ("esc", "cancel")]
    ck = current_ctx(z)
    ansicht = ansicht_mit_tasten(u, ck)
    if ansicht is not None:
        liste = list(ansicht.tasten())
    else:
        liste = tasten_der_zeile(CTX_KEYS.get(ck, []))
    if not in_text_entry(z):
        liste.append(("/", "commands"))
    return liste


# Kontext → Name der Ansicht im Bündel, die ihre Tasten selbst liefert.
ANSICHTEN = {"ai": "chat"}


def ansicht_mit_tasten(u, ck):
    name = ANSICHTEN.get(ck)
    ansicht = getattr(u, name, None) if name else None
    return ansicht if hasattr(ansicht, "tasten") else None
