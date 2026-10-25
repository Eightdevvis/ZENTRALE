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
#
# Seit 25.10.2026 zeigt die Leiste selbst nur die Tasten (leistenzeile,
# unten), meistgenutzte vorn; '?' + Taste erklärt eine. eintraege() bleibt
# die vollständige Liste mit Beschriftung (Tests, Überlagerungen).

from . import tasten as T
from . import tasten_zaehler
from .fenster import (PROGRAMME, STARTSEITE, aktives_programm, in_text_entry,
                      programm_mit_tabelle, titel)

TRENNER = " · "

# ── Regler der kompakten Leiste (2026-10-25, Sasha entscheidet den Feinschliff)
TRENNER_KOMPAKT = " · "    # zwischen zwei Tasten
AUSLASSUNG = "…"           # steht da, wenn nicht alle Tasten passen
FRAGE = "?"                # Präfix: ? + Taste erklärt die Taste
FARBE = "faint"            # Farbe der Leiste (Schlüssel in z.C)
FARBE_ERKLAERUNG = "bright"  # Farbe, solange eine Erklärung offen ist
WARTEN = "warten"          # Zustand nach '?': die nächste Taste wird erklärt
TEXT_WARTEN = "? → press the key you want explained"

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


def _ansicht(u, name):
    f = getattr(getattr(u, name, None), "ansicht", None)
    return f() if callable(f) else "start"


def ansicht_tasten(u, name):
    horcher = getattr(u.z, "horcher", None)
    p = getattr(u, name, None)
    if horcher is None or p is None:
        return []
    return horcher.eintraege(name, _ansicht(u, name))


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
            # Ein Programm kann seine Hauptansicht nennen (HAUPTANSICHT); die
            # erste der Tabelle ist nicht immer eine (Kalender: „ansehen" —
            # /help zeigte dort nur „any key close", 25.10.2026).
            haupt = getattr(getattr(u, name, None), "HAUPTANSICHT", None)
            ansicht = haupt if haupt in ansichten else ansichten[0]
            raus.append((titel(name), text(horcher.eintraege(name, ansicht))))
    return raus


# ── Kompakte Leiste, '?'-Erklärung, Sortierer (2026-10-25) ────────────
#
# Sasha: „mach einfach nur die shortcuts hin und wenn man ?+shortcut drückt
# dann wird die bedeutung aufgeklappt, dazu ein kleiner sortierer mit the
# most used shortcuts ganz nach vorne." Anlass: die Kalender-Hauptansicht
# hatte ~255 Zeichen Einträge, das Terminal 160 Spalten — S, R … fehlten.
#
# - Die Leiste zeigt nur noch die Tasten („t/w/m/y · S · R · g …"), ohne
#   Beschriftung; passt es trotzdem nicht, steht „…" vor den festen Tasten
#   am Ende ('/' und '?'), nie wird still etwas weggeworfen.
# - '?' und dann eine Taste: die Leiste zeigt, was diese Taste hier tut;
#   der nächste Tastendruck schließt. '?' greift nur, wo die offene Ansicht
#   es nicht selbst nimmt (Freitext, „any key"-Fragen) — heute belegt kein
#   Programm '?' (geprüft 25.10.2026). Shift/Alt gedrückt HALTEN sieht ein
#   Terminal nicht, darum ein Präfix.
# - Sortierer: tasten_zaehler.py (meistgenutzt zuerst, Reihenfolge nur beim
#   Öffnen einer Ansicht neu).
# /help und das '/'-Fenster bleiben vollständig mit Beschriftungen.

class Leiste:
    """Zustand der Leiste am Kontext: Zähler und die offene Erklärung."""

    def __init__(self, datei=None):
        self.zaehler = tasten_zaehler.Zaehler(datei)
        self.erklaer = None        # None | WARTEN | (taste, text)


def leiste_von(z):
    l = getattr(z, "leiste", None)
    if l is None:
        l = z.leiste = Leiste()
    return l


def frage_frei(z):
    """Darf '?' die Erklärung öffnen? Nicht im Freitext und nicht, wo die
    offene Ansicht '?' selbst nimmt (auch über „any key")."""
    if in_text_entry(z):
        return False
    mit = programm_mit_tabelle(z)
    return mit is None or mit[1].TASTEN.nimmt(mit[2], FRAGE) is None


def erklaert(z):
    return leiste_von(z).erklaer is not None


def frage_oeffnen(z):
    leiste_von(z).erklaer = WARTEN


def erklaer_taste(u, ch):
    """Taste, während die Erklärung offen ist: nach '?' wird sie erklärt,
    danach schließt jede Taste. -1 (nichts gedrückt) und Resize zählen nicht."""
    import curses
    if ch == -1 or ch == curses.KEY_RESIZE:
        return
    l = leiste_von(u.z)
    if l.erklaer == WARTEN:
        l.erklaer = erklaerung(u, T.name_von(ch, getattr(u.z, "stdscr", None), alt=True))
    else:
        l.erklaer = None


_ZEIGEN = {"up": "↑", "down": "↓", "left": "←", "right": "→", "backspace": "⌫"}


def _zeig(name):
    for k, v in _ZEIGEN.items():
        name = name.replace(k, v)
    return name


def erklaerung(u, name):
    """(taste, text): was die Taste `name` (neutraler Name) gerade tut."""
    if name is None:
        return ("?", "unknown key")
    z = u.z
    mit = programm_mit_tabelle(z)
    if mit is not None:
        _prog, p, ansicht = mit
        liste = p.TASTEN.daten().get(ansicht, [])
        for e in liste:
            if e["taste"] in T.tt.BESONDERE or name not in T.tt.namen(e["taste"]):
                continue
            if e.get("text"):
                return (e["taste"], e["text"])
            for f in liste:                      # Zweitbelegung (k für ↑)
                if f["aktion"] == e["aktion"] and f.get("text"):
                    return (_zeig(name), "%s (like %s)" % (f["text"], f["taste"]))
            return (_zeig(name), "works here, no description")
    else:
        for t, w in programm_tasten(u)[1]:
            try:
                if name in T.tt.namen(t):
                    return (t, w or "works here, no description")
            except ValueError:
                continue
    if name == "/" and not in_text_entry(z):
        return ("/", "commands, and every key of this view with its meaning")
    if name == FRAGE:
        return (FRAGE, "explain a key: ? then the key")
    if mit is not None:
        for t, w in programm_tasten(u)[1]:
            if t == T.tt.JEDE:
                return (_zeig(name), "any key: " + w)
    return (_zeig(name), "does nothing here")


def zaehlen(z, mit):
    """Nach einer Taste ans Programm: was sie ausgelöst hat, zählen.
    mit = programm_mit_tabelle(z) von VOR der Taste (Tasten.zuletzt wurde
    davor auf None gesetzt)."""
    if mit is None:
        return
    prog, p, _a = mit
    zuletzt = p.TASTEN.zuletzt
    if zuletzt is None:
        return
    ansicht, _name, aktion = zuletzt
    for e in p.TASTEN.daten().get(ansicht, []):
        if e["aktion"] == aktion and e.get("text"):
            if e["taste"] not in T.tt.BESONDERE:
                leiste_von(z).zaehler.zaehlen(prog, ansicht, e["taste"])
            return


def kompakt(tasten, anker, breite):
    """Nur die Tasten, z. B. „ t/w/m/y · S · R · / · ?". Passt es nicht,
    fallen hintere Tasten aus dem Körper und „…" steht vor dem Anker
    ('/' und '?' bleiben immer sichtbar — über '/' sieht man alle)."""
    if not tasten and not anker:
        return ""

    def bau(teile):
        return " " + TRENNER_KOMPAKT.join(teile)
    voll = bau(tasten + anker)
    if len(voll) <= breite:
        return voll
    for n in range(len(tasten) - 1, -1, -1):
        s = bau(tasten[:n] + [AUSLASSUNG] + anker)
        if len(s) <= breite:
            return s
    return voll[:breite]


def leistenzeile(u, breite, punkt=()):
    """(text, farbschlüssel) der untersten Zeile. punkt = Tasten, die ein ●
    bekommen (KI-Antwort ungelesen: „space")."""
    z, bz = u.z, u.bz
    l = leiste_von(z)
    if l.erklaer == WARTEN:
        return (" " + TEXT_WARTEN)[:breite], FARBE_ERKLAERUNG
    if l.erklaer:
        return (" %s  %s" % l.erklaer)[:breite], FARBE_ERKLAERUNG
    if u.erinnerung.nag_active or bz.help_latched or bz.cmd_mode:
        koerper, anker = eintraege(u), []
    else:
        name = aktives_programm(z)
        koerper = l.zaehler.sortiert(name, _ansicht(u, name), ansicht_tasten(u, name))
        anker = [] if in_text_entry(z) else ["/"]
        if frage_frei(z):
            anker.append(FRAGE)
    tasten = [t + (" ●" if t in punkt else "") for t, _w in koerper]
    return kompakt(tasten, anker, breite), FARBE
