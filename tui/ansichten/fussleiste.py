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
#   3. Übergang: ein Programm ohne Tabelle liefert noch selbst (tasten())
#      oder steht in befehle.CTX_KEYS.
#   Wo die Befehlszeile aufgeht (kein Freitext-Feld), steht zuletzt „/ commands".
#
# Ein Eintrag ist (taste, was), englisch beschriftet (Sasha, 07.10.2026).
# Die Beschriftung liest core/tastentabelle.namen(); codes() macht daraus
# Tastencodes — davon lebt tests/test_fussleiste.py: jede beworbene Taste
# muss im Fenster etwas tun.

from . import tasten as T
from .befehle import CTX_KEYS, CTX_TITLES
from .fenster import aktives_programm, current_ctx, in_text_entry

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
    liste = list(programm_tasten(u)[1])
    if not in_text_entry(z):
        liste.append(("/", "commands"))
    return liste


def programm_tasten(u):
    """(titel, [(taste, was)]) des fokussierten Programms in seiner Ansicht —
    für die Leiste und das '/'-Fenster. Ohne Befehle der Befehlszeile."""
    z = u.z
    name = aktives_programm(z)
    p = getattr(u, name, None)
    horcher = getattr(z, "horcher", None)
    if horcher is not None and horcher.kennt(name) and hasattr(p, "ansicht") \
            and horcher.herkunft(name) != "ohne":
        return name, horcher.eintraege(name, p.ansicht())
    # ── Übergang: Programme ohne Tastentabelle ──
    ck = current_ctx(z)
    ansicht = ansicht_mit_tasten(u, ck)
    if ansicht is not None:
        return CTX_TITLES.get(ck, ck), list(ansicht.tasten())
    return CTX_TITLES.get(ck, ck) if ck else name, tasten_der_zeile(CTX_KEYS.get(ck, []))


# Kontext → Name der Ansicht im Bündel, die ihre Tasten selbst liefert.
ANSICHTEN = {"ai": "chat"}


def ansicht_mit_tasten(u, ck):
    name = ANSICHTEN.get(ck)
    ansicht = getattr(u, name, None) if name else None
    return ansicht if hasattr(ansicht, "tasten") else None
