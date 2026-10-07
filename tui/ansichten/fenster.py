# tui/ansichten/fenster.py
#
# Welches Fenster hat gerade den Fokus? Zwei Fragen, die die Hauptschleife
# vor jeder Taste stellt: tippt der Nutzer gerade Freitext (dann ist '/' ein
# Zeichen statt der Befehlszeile), und welche Tastenhilfe zeigt '/'? Beide
# lesen nur die Zustands-Dicts, die die Ansichten am Kontext ablegen
# (z.AI, z.G …). Die Reihenfolge der Abfragen ist Verhalten: wer zuerst
# gefragt wird, gewinnt, falls einmal zwei Fenster aktiv sind.
# Bis 06.10.2026 Closures in run_ui, siehe memory/system/tui_bauplan.md.


def in_text_entry(z):
    """Tippt der Nutzer gerade einen Freitext (Name, Eintrag, Antwort)?
    Dann bleibt '/' ein normales Zeichen und öffnet NICHT die Befehlszeile."""
    AI, G, K, L, MAIL, NOTE, PIANO, TUTOR = (z.AI, z.G, z.K, z.L, z.MAIL, z.NOTE,
                                             z.PIANO, z.TUTOR)
    if G["active"]:
        return G["view"] in ("new", "view", "remind")   # Name/Wert/Reminder-Uhrzeit
    if L["active"]:
        return L["adding"] or L["view"] == "move_new"
    if K["active"]:
        # Termin/Routine anlegen+bearbeiten ODER Sidebar-Item neu/umbenennen
        return K["mode"] == "add" or K["linput"] is not None
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
    if TUTOR["active"]:
        # Ganze Zeile ist Eingabe (reden ODER '/befehl') → '/' bleibt ein
        # Zeichen, die Tutor-Zeile parst Slash-Befehle selbst (Browser-Konsole).
        return True
    return False

def current_ctx(z):
    """Kontext-Schlüssel des fokussierten Fensters für die '/'-Anzeige.
    None = Tipp-Screen ohne eigene Shortcut-Liste."""
    AI, ELEK, G, K, L, M, MAIL = z.AI, z.ELEK, z.G, z.K, z.L, z.M, z.MAIL
    NOTE, PIANO, TECH, TUTOR = z.NOTE, z.PIANO, z.TECH, z.TUTOR
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
        if K["mode"] != "view":
            return None
        if K["listfocus"]:
            return "cal:sort" if K["lsort"] else "cal:list"
        return "cal:week" if K["view"] == "week" else "cal:month"
    if MAIL["active"]:
        if MAIL["replying"] or MAIL.get("picking"):
            return None
        if MAIL["level"] == "cats":
            return "mail:cats"
        return "mail:read" if MAIL["mode2"] == "read" else "mail:list"
    if AI["active"]:
        return "ai"
    if TUTOR["active"]:
        return "tutor"
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
