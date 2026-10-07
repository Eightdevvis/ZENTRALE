# tui/ansichten/chat_befehle.py
#
# Slash-Befehle IM KI-Chat (/neu, /modell, /effort …) — nur das Lesen und
# die Liste, ohne curses und ohne HTTP, damit testbar
# (tests/test_chat_eingabe.py). Was ein Befehl tut, macht Chat.befehl in
# chat.py über /api/ai/einstellungen bzw. chat_gespraeche.py (Gespräche).
#
# Nicht zu verwechseln mit der Befehlszeile der TUI (befehle.py, '/' in
# jedem anderen Fenster): im Chat ist '/' ein Zeichen der Eingabe, und erst
# beim Abschicken wird geschaut, ob die Nachricht ein Befehl ist.
#
# Regel (2026-10-07): ein Befehl ist eine Eingabe, die mit '/' beginnt.
# '//' am Anfang schickt einen wörtlichen Schrägstrich an die KI ('//etc'
# → '/etc'). Ein unbekannter Befehl geht NICHT an die KI — ein Tippfehler
# in „/modell" soll nicht als Frage bezahlt werden.

from collections import namedtuple

# (Befehl, was er tut) — die Reihenfolge ist die der Hilfe.
BEFEHLE = [
    ("/neu",      "neues gespräch (das alte bleibt in der liste)"),
    ("/liste",    "alle gespräche (auch: tab bei leerer eingabe)"),
    ("/titel",    "titel zeigen · /titel <text> benennt um"),
    ("/archiv",   "dieses gespräch ins archiv, dann ein neues"),
    ("/wiederholen", "letzte antwort neu erzeugen"),
    ("/bearbeiten", "letzte eigene nachricht ändern und neu schicken"),
    ("/denken",   "gedachtes auf-/zuklappen (auch: strg+d)"),
    ("/gedaechtnis", "was die ki über dich weiß — ansehen und ändern"),
    ("/skills",   "skills der ki — ansehen, an- und ausschalten"),
    ("/ablage",   "dokumente der ki und anhänge ansehen"),
    ("/anhang",   "/anhang <pfad> gibt der ki eine datei mit (text, pdf, bild)"),
    ("/projekt",  "projekt dieses gesprächs · /projekt <name> · neu <name> · kein"),
    ("/projekte", "alle projekte — anweisungen, wissen, gespräche"),
    ("/modell",   "modell wählen · /modell <name> setzt direkt"),
    ("/anbieter", "anbieter wählen · /anbieter <name> oder auto"),
    ("/effort",   "denk-tiefe wählen (nur claude) · /effort low … max"),
    ("/budget",   "monatsbudget zeigen · /budget 20 setzt · /budget aus"),
    ("/lokal",    "nur die lokale ki"),
    ("/cloud",    "nur die cloud-ki"),
    ("/auto",     "lokal, wenn da — sonst cloud"),
    ("/hilfe",    "diese liste"),
]

# Andere Schreibweisen, die dasselbe meinen. /clear stand früher in der Doku.
ANDERE_NAMEN = {"help": "hilfe", "clear": "neu", "model": "modell",
                "provider": "anbieter", "local": "lokal", "list": "liste",
                "retry": "wiederholen", "edit": "bearbeiten",
                "gedächtnis": "gedaechtnis", "memory": "gedaechtnis",
                "dokumente": "ablage", "attach": "anhang", "datei": "anhang",
                "project": "projekt", "projects": "projekte"}

NAMEN = {b[1:] for b, _ in BEFEHLE}

Eingabe = namedtuple("Eingabe", "art name arg text")
#   art "senden":    text geht an die KI
#   art "befehl":    name (ohne '/'), arg (Rest, getrimmt)
#   art "unbekannt": name wie getippt
#   art "leer":      nichts zu tun


def lesen(roh):
    """Eine abgeschickte Eingabe deuten. -> Eingabe"""
    text = (roh or "").strip()
    if not text:
        return Eingabe("leer", "", "", "")
    if text.startswith("//"):
        return Eingabe("senden", "", "", text[1:])
    if not text.startswith("/"):
        return Eingabe("senden", "", "", text)
    teile = text[1:].split(None, 1)
    name = teile[0].lower() if teile else ""
    arg = teile[1].strip() if len(teile) > 1 else ""
    name = ANDERE_NAMEN.get(name, name)
    if name in NAMEN:
        return Eingabe("befehl", name, arg, text)
    return Eingabe("unbekannt", name, arg, text)


def hilfe_text():
    """Die Befehle als Text für den Verlauf."""
    breite = max(len(b) for b, _ in BEFEHLE)
    zeilen = ["befehle im chat:"]
    zeilen += ["%s  %s" % (b.ljust(breite), was) for b, was in BEFEHLE]
    zeilen.append("// am anfang schickt einen schrägstrich an die ki")
    return "\n".join(zeilen)
