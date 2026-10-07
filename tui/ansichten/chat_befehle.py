# tui/ansichten/chat_befehle.py
#
# Slash-Befehle IM KI-Chat (/new, /model, /effort …) — nur das Lesen und
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
# in „/model" soll nicht als Frage bezahlt werden.

from collections import namedtuple

# (Befehl, was er tut) — die Reihenfolge ist die der Hilfe. Seit 07.10.2026
# englisch (Sasha: „die deutschen sind mir zu weird"); die deutschen Namen
# gehen weiter, stehen aber nirgends mehr (ANDERE_NAMEN).
BEFEHLE = [
    ("/new",      "neues gespräch (das alte bleibt in der liste)"),
    ("/chats",    "gespräche links aufklappen (auch: tab bei leerer eingabe)"),
    ("/rename",   "titel zeigen · /rename <text> benennt um"),
    ("/archive",  "dieses gespräch ins archiv, dann ein neues"),
    ("/retry",    "letzte antwort neu erzeugen"),
    ("/edit",     "letzte eigene nachricht ändern und neu schicken"),
    ("/thinking", "gedachtes auf-/zuklappen (auch: ctrl+d)"),
    ("/memory",   "was die ki über dich weiß — ansehen und ändern"),
    ("/skills",   "skills der ki — ansehen, an- und ausschalten"),
    ("/files",    "dokumente der ki und anhänge ansehen"),
    ("/attach",   "/attach <pfad> gibt der ki eine datei mit (text, pdf, bild)"),
    ("/project",  "projekt dieses gesprächs · /project <name> · new <name> · none"),
    ("/projects", "alle projekte — anweisungen, wissen, gespräche"),
    ("/permissions", "was die ki ohne fragen darf — ansehen, zurücknehmen"),
    ("/customize", "einstellungen: skills, gedächtnis, kosten, was sie kann, modell"),
    ("/mouse",    "maus im chat an/aus (shift + ziehen markiert immer)"),
    ("/model",    "alle modelle der anbieter (tippen filtert) · /model <name>"),
    ("/provider", "anbieter wählen · /provider <name> oder auto"),
    ("/effort",   "denk-tiefe wählen (nur claude) · /effort low … max"),
    ("/budget",   "monatsbudget zeigen · /budget 20 setzt · /budget off"),
    ("/local",    "nur die lokale ki"),
    ("/cloud",    "nur die cloud-ki"),
    ("/auto",     "lokal, wenn da — sonst cloud"),
    ("/help",     "diese liste"),
]

# Englischer Name → der Name, unter dem Chat.befehl ihn ausführt. Die inneren
# Namen bleiben deutsch, damit chat.py & Co. unverändert weiterlaufen.
INNEN = {"new": "neu", "chats": "liste", "rename": "titel", "archive": "archiv",
         "retry": "wiederholen", "edit": "bearbeiten", "thinking": "denken",
         "memory": "gedaechtnis", "files": "ablage", "attach": "anhang",
         "project": "projekt", "projects": "projekte", "model": "modell",
         "provider": "anbieter", "local": "lokal", "help": "hilfe",
         "permissions": "erlaubnis", "customize": "einstellungen", "mouse": "maus"}

# Stille Aliase: die deutschen Namen von vorher und alte Schreibweisen
# (/clear stand früher in der Doku). In keiner Hilfe, keiner Fußleiste.
ANDERE_NAMEN = {"clear": "neu", "list": "liste", "gedächtnis": "gedaechtnis",
                "dokumente": "ablage", "datei": "anhang", "denken": "denken",
                "neu": "neu", "liste": "liste", "titel": "titel", "archiv": "archiv",
                "wiederholen": "wiederholen", "bearbeiten": "bearbeiten",
                "gedaechtnis": "gedaechtnis", "ablage": "ablage", "anhang": "anhang",
                "projekt": "projekt", "projekte": "projekte", "modell": "modell",
                "anbieter": "anbieter", "lokal": "lokal", "hilfe": "hilfe",
                "erlaubnis": "erlaubnis", "erlaubnisse": "erlaubnis",
                "settings": "einstellungen", "einstellungen": "einstellungen", "maus": "maus"}

NAMEN = {INNEN.get(b[1:], b[1:]) for b, _ in BEFEHLE}

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
    innen = INNEN.get(name) or ANDERE_NAMEN.get(name, name)
    if innen in NAMEN:
        return Eingabe("befehl", innen, arg, text)
    return Eingabe("unbekannt", name, arg, text)    # so, wie getippt


def hilfe_text():
    """Die Befehle als Text für den Verlauf."""
    breite = max(len(b) for b, _ in BEFEHLE)
    zeilen = ["befehle im chat:"]
    zeilen += ["%s  %s" % (b.ljust(breite), was) for b, was in BEFEHLE]
    zeilen.append("// am anfang schickt einen schrägstrich an die ki")
    zeilen.append("\\ am zeilenende + enter (oder alt+enter): neue zeile · \\\\ + enter: ein \\ und senden")
    zeilen.append("ctrl+c stoppt eine antwort · esc schließt, die antwort läuft weiter")
    return "\n".join(zeilen)
