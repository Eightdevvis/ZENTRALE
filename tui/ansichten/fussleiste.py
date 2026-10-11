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
#   2. Das fokussierte Programm (fenster.aktives_programm) in seiner gerade
#      offenen Ansicht — nachgeschlagen beim Horcher (horcher.py), der jedes
#      Programm beim Verkabeln einmal nach seiner Tastentabelle gefragt hat
#      (seit 2026-10-11; dieselbe Tabelle verteilt die Tasten, tasten.py).
#   Bis 2026-10-11 stand hier eine Handtabelle (befehle.CTX_KEYS) und jedes
#   Programm schrieb zusätzlich eine Hinweiszeile in seinen Kasten — beides
#   lief auseinander. Jetzt gibt es nur diese eine Leiste.
#   Wo die Befehlszeile aufgeht (kein Freitext-Feld), steht zuletzt „/ commands".
#
# Ein Eintrag ist (taste, was), englisch beschriftet (Sasha, 07.10.2026).
# Die Beschriftung liest core/tastentabelle.namen(); codes() macht daraus
# Tastencodes — davon lebt tests/test_fussleiste.py: jede beworbene Taste
# muss im Fenster etwas tun.

from . import tasten as T
from .fenster import PROGRAMME, STARTSEITE, aktives_programm, in_text_entry, titel

TRENNER = " · "

# Beschriftungen, die keine Taste sind („tippen"). Alles andere muss codes()
# kennen, sonst schlägt der Test an.
KEINE_TASTE = {"type", "any key"}

def codes(taste):
    """Beschriftung -> Liste von Tastenfolgen (jede eine Liste von Codes),
    die alle beworben sind. None: keine Taste (Befehl '/…' oder „type").
    Wirft ValueError bei einer Beschriftung, die niemand lesen kann."""
    if taste in KEINE_TASTE or (taste.startswith("/") and len(taste) > 1):
        return None
    return [T.codes(n) for n in T.tt.namen(taste)]


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
    liste = list(programm_tasten(u)[1])
    if not in_text_entry(z):
        liste.append(("/", "commands"))
    return liste


def programm_tasten(u):
    """(titel, [(taste, was)]) des fokussierten Programms in seiner offenen
    Ansicht — für die Leiste und das '/'-Fenster. Nachgeschlagen beim
    Horcher (keine Rechnung beim Zeichnen)."""
    name = aktives_programm(u.z)
    return titel(name), ansicht_tasten(u, name)


def ansicht_tasten(u, name):
    horcher = getattr(u.z, "horcher", None)
    p = getattr(u, name, None)
    if horcher is None or p is None:
        return []
    f = getattr(p, "ansicht", None)
    return horcher.eintraege(name, f() if callable(f) else "start")


def hilfe(u):
    """[(programm, „taste was · …")] für /help: je Programm die Tasten seiner
    ersten (Haupt-)Ansicht, aus dem Horcher — keine zweite Liste von Hand."""
    horcher = getattr(u.z, "horcher", None)
    if horcher is None:
        return []
    raus = []
    for name in [STARTSEITE] + [n for _d, n in PROGRAMME]:
        ansichten = horcher.ansichten(name)
        if ansichten:
            raus.append((titel(name), text(horcher.eintraege(name, ansichten[0]))))
    return raus
