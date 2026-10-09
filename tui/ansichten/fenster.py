# tui/ansichten/fenster.py
#
# Welches Fenster hat gerade den Fokus? Zwei Fragen, die die Hauptschleife
# vor jeder Taste stellt: tippt der Nutzer gerade Freitext (dann ist '/' ein
# Zeichen statt der Befehlszeile), und welche Tastenhilfe zeigt '/'? Beide
# lesen nur die Zustands-Dicts, die die Ansichten am Kontext ablegen
# (z.AI, z.G …). Die Reihenfolge der Abfragen ist Verhalten: wer zuerst
# gefragt wird, gewinnt, falls einmal zwei Fenster aktiv sind.
# Bis 06.10.2026 Closures in run_ui, siehe memory/system/tui_bauplan.md.

from .post import MAIL_EINGANG


def in_text_entry(z):
    """Tippt der Nutzer gerade einen Freitext (Name, Eintrag, Antwort)?
    Dann bleibt '/' ein normales Zeichen und öffnet NICHT die Befehlszeile."""
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
    if AI["active"]:
        # Ganzes Panel ist Prompt-Eingabe → '/' bleibt ein Zeichen, öffnet
        # nicht die Befehlszeile. (Bei offener Erlaubnis-Frage ignoriert der
        # AI-Zweig alles außer j/n/Zahl/esc.)
        return True
    return False

def current_ctx(z):
    """Kontext-Schlüssel des fokussierten Fensters für die '/'-Anzeige.
    None = Tipp-Screen ohne eigene Shortcut-Liste."""
    AI, ELEK, G, K, L, M, MAIL = z.AI, z.ELEK, z.G, z.K, z.L, z.M, z.MAIL
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
    if AI["active"]:
        return "ai"
    if PIANO["active"]:
        return "piano"
    if ELEK["active"]:
        return "elektronik"
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
