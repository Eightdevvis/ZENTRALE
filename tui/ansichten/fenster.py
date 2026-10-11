# tui/ansichten/fenster.py
#
# Welches Fenster hat gerade den Fokus? Zwei Fragen, die die Hauptschleife
# vor jeder Taste stellt: tippt der Nutzer gerade Freitext (dann ist '/' ein
# Zeichen statt der Befehlszeile), und welche Tastenhilfe zeigt '/'? Beide
# lesen nur die Zustands-Dicts, die die Ansichten am Kontext ablegen
# (z.AI, z.G …). Die Reihenfolge der Abfragen ist Verhalten: wer zuerst
# gefragt wird, gewinnt, falls einmal zwei Fenster aktiv sind.
# Bis 06.10.2026 Closures in run_ui, siehe memory/system/tui_bauplan.md.

from .horcher import Horcher
from .post import MAIL_EINGANG

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
    Mit Tastentabelle sagt es die Tabelle: Freitext („type") oder '/' selbst
    belegt."""
    mit = programm_mit_tabelle(z)
    if mit is not None:
        _n, p, ansicht = mit
        return p.TASTEN.freitext(ansicht) or p.TASTEN.nimmt(ansicht, "/") is not None
    AI, G, K, L, MAIL, NOTE, PIANO = (z.AI, z.G, z.K, z.L, z.MAIL, z.NOTE, z.PIANO)
    if G["active"]:
        return G["view"] in ("new", "view", "remind")   # Name/Wert/Reminder-Uhrzeit
    if L["active"]:
        return L["adding"] or L["view"] == "move_new"
    if K["active"]:
        # Ein Kasten (Termin anlegen/ändern, Rückfrage) ist offen → alles ist
        # Text, auch „/". Die Fokus-Frage stellt die Bedienung (kalender_bedienung).
        return (K.get("w") or {}).get("dialog") is not None
    if MAIL["active"]:
        return MAIL["replying"]
    if NOTE["active"]:
        # Ebene 2 (Block bearbeiten) oder Titel tippen → Freitext, '/' literal.
        return NOTE["layer"] == 2 or NOTE["titling"]
    if PIANO["active"]:
        # Beim Namen-Tippen ist '/' ein Zeichen; sonst ist die ganze
        # Tastatur Klaviatur — die Befehlszeile hat da nichts verloren.
        return True
    DESK = getattr(z, "DESK", None)       # Desk View (2026-10-09): Name/Modal = Text
    if DESK and DESK["active"]:
        return DESK["name"] is not None or DESK["modal"] is not None \
            or (DESK.get("bild_wahl") or {}).get("pfad") is not None
    WERK = getattr(z, "WERK", None)       # Werkstatt (2026-10-10): Name tippen = Text
    if WERK and WERK["active"]:
        return WERK["feld"] is not None
    if AI["active"]:
        # Ganzes Panel ist Prompt-Eingabe → '/' bleibt ein Zeichen, öffnet
        # nicht die Befehlszeile. (Bei offener Erlaubnis-Frage ignoriert der
        # AI-Zweig alles außer j/n/Zahl/esc.)
        return True
    return False

def current_ctx(z):
    """Kontext-Schlüssel des fokussierten Fensters für die '/'-Anzeige.
    None = Tipp-Screen ohne eigene Shortcut-Liste."""
    AI, G, K, L, M, MAIL = z.AI, z.G, z.K, z.L, z.M, z.MAIL
    NOTE, PIANO, TECH = z.NOTE, z.PIANO, z.TECH
    if G["active"]:
        return "graph" if G["view"] == "list" else None
    if L["active"]:
        v = L["view"]
        if v == "forest" and not L["adding"] and not L["confirm"]:
            return "list:forest"
        if v == "view" and not L["adding"]:
            return "list:view"
        if v in ("place", "move"):
            return "list:pick"
        return None
    if M["active"]:
        return "map"
    if K["active"]:
        w = K.get("w") or {}
        if w.get("dialog") is not None or w.get("popup"):
            return None
        stil = (K.get("stil") or "A").lower()
        if stil == "a":
            return "cal:a:" + (w.get("fokus") or "termine")
        return "cal:" + stil
    if MAIL["active"]:
        if MAIL["replying"] or MAIL.get("picking"):
            return None
        if MAIL["level"] == "cats":
            return "mail:cats"
        # Im Eingang hakt f ab und d löscht nicht — anderswo umgekehrt; die
        # Leiste soll nur zeigen, was geht (2026-10-07).
        art = "mail:read" if MAIL["mode2"] == "read" else "mail:list"
        return art + (":eingang" if MAIL["cat"] == MAIL_EINGANG else "")
    DESK = getattr(z, "DESK", None)
    if DESK and DESK["active"]:
        # Wahl, Ruhe, Greifen, Verbinden, Frage → eigene Tasten; Name tippen
        # und Modal sind Freitext (None). Die Ansicht weiß es selbst.
        D = DESK
        if D["name"] is not None or D["modal"] is not None:
            return None
        if D["ebene"] == "wahl":
            return "desk:wahl"
        # Wähler hinter + (2026-10-10): Art, dann Bild; Pfad tippen = Freitext.
        if D.get("bild_wahl") is not None:
            return None if D["bild_wahl"].get("pfad") is not None else "desk:neu"
        if D.get("art_wahl") is not None:
            return "desk:neu"
        c = D["canvas"]
        modus = c.modus if c else "ruhe"
        if modus == "ruhe" and c is not None:
            fokus = c.element(c.fokus)
            if fokus is not None and fokus.get("art") == "bild":
                return "desk:bild"          # o öffnen, f mono/farbe
            if fokus is not None and fokus.get("art") == "kachel":
                return "desk:kachel"        # o öffnen in der App (2026-10-10)
        return "desk:" + {"ruhe": "canvas"}.get(modus, modus)
    SHOP = getattr(z, "SHOP", None)       # Schaufenster (2026-10-10)
    if SHOP and SHOP["active"]:
        return "shop"
    WERK = getattr(z, "WERK", None)
    if WERK and WERK["active"]:           # Werkstatt (2026-10-10): tippen = Freitext
        return None if WERK["feld"] is not None else "werkstatt"
    if AI["active"]:
        return "ai"
    if PIANO["active"]:
        return "piano"
    if TECH["active"]:
        return "technik"
    if NOTE["active"]:
        # Ebene 2 / Titel-Eingabe sind Freitext → '/' ist dort ein Zeichen,
        # das Overlay geht gar nicht erst auf (siehe in_text_entry). Bleibt
        # Ebene 1 (block-navigation) bzw. die Übersicht.
        if NOTE["titling"] or NOTE["layer"] == 2:
            return None
        return "note:list" if NOTE["view"] == "list" else "note:edit"
    return "home"
