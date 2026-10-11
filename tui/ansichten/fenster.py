# tui/ansichten/fenster.py
#
# Welches Programm hat gerade den Fokus, und in welcher Ansicht? Die
# Hauptschleife fragt vor jeder Taste: wer bekommt sie (aktives_programm),
# und tippt der Nutzer gerade Freitext (dann ist '/' ein Zeichen statt der
# Befehlszeile)? Die Antwort steht in der Tastentabelle der offenen Ansicht
# (tasten.py, seit 2026-10-11; bis dahin eine if-Kette je Fenster und die
# Handtabelle befehle.CTX_KEYS). Die Reihenfolge in PROGRAMME ist Verhalten:
# wer zuerst aktiv ist, gewinnt, falls einmal zwei Fenster aktiv sind.

from .horcher import Horcher

# Die Programme in der Reihenfolge, in der sie eine Taste bekommen (wer zuerst
# aktiv ist, gewinnt): (Zustands-Dict am Kontext, Name im Bündel der
# Hauptschleife). Eine Tabelle für Tastenverteilung UND Leiste — bis
# 11.10.2026 fragten beide in verschiedener Reihenfolge.
PROGRAMME = [
    ("G", "graphen"), ("L", "fokus"), ("M", "karte"), ("K", "kalender"),
    ("MAIL", "post"), ("NOTE", "notizen"), ("TECH", "technik"),
    ("PIANO", "klavier"), ("AI", "chat"), ("DESK", "desk"),
    ("SHOP", "shop"), ("WERK", "werkstatt"),
]
STARTSEITE = "startseite"            # niemand aktiv: das Rad
# Wie ein Programm in Überschriften heißt ('/'-Fenster, /help), wo der Name
# im Bündel nicht passt.
TITEL = {"fokus": "liste", "graphen": "graph", "chat": "ki-chat", "startseite": "start",
         "shop": "schaufenster"}


def titel(name):
    return TITEL.get(name, name)


def aktives_programm(z):
    """Name des Programms mit dem Fokus (Name im Bündel u)."""
    for dict_name, name in PROGRAMME:
        D = getattr(z, dict_name, None)
        if D and D.get("active"):
            return name
    return STARTSEITE


def verkabeln(z, u):
    """Alle Programme des Bündels am Kontext anmelden; der Horcher fragt
    jedes EINMAL nach seinen Tasten (Tastentabelle, sonst abhören) und merkt
    sie sich je Ansicht. run_ui und die Tests rufen das gleich nach dem Bau."""
    namen = [n for _d, n in PROGRAMME] + [STARTSEITE]
    z.programme = {n: getattr(u, n) for n in namen if getattr(u, n, None) is not None}
    z.horcher = Horcher()
    for n, p in z.programme.items():
        if hasattr(p, "anbinden"):       # wer das Bündel braucht (Startseite)
            p.anbinden(u)
        z.horcher.verkabeln(n, p)


def programm_mit_tabelle(z):
    """(name, programm, ansicht) des fokussierten Programms, wenn es eine
    Tastentabelle hat — sonst None."""
    name = aktives_programm(z)
    p = (getattr(z, "programme", None) or {}).get(name)
    if p is None or getattr(p, "TASTEN", None) is None or not hasattr(p, "ansicht"):
        return None
    return name, p, p.ansicht()


def in_text_entry(z):
    """Tippt der Nutzer gerade einen Freitext (Name, Eintrag, Antwort)?
    Dann bleibt '/' ein normales Zeichen und öffnet NICHT die Befehlszeile.
    Das sagt die Tastentabelle der offenen Ansicht: Freitext („type") oder
    '/' selbst belegt. Ohne Tabelle (abgehörtes Programm): nein."""
    mit = programm_mit_tabelle(z)
    if mit is None:
        return False
    _n, p, ansicht = mit
    return p.TASTEN.freitext(ansicht) or p.TASTEN.nimmt(ansicht, "/") is not None
