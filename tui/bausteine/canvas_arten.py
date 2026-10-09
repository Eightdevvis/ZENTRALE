# tui/bausteine/canvas_arten.py
#
# Die Elementarten für den Canvas (tui/bausteine/canvas.py). Eine Art ist
# ein kleines Objekt mit:
#   name                       wie in element["art"]
#   zeichne(element, w, h)     -> Zeilen für das Innere des Kastens (w×h);
#                                 eine Zeile ist ein str oder [(text, rolle)]
#   modal(element)             -> ein Bearbeiten-Modal oder None
#   neu(id, x, y)              -> ein frisches Element (nur Arten, die man
#                                 mit + anlegen kann)
# Ein Modal hat: titel, taste(ch) -> None|"speichern"|"abbrechen",
# anzeige(w, h) -> (zeilen, (cursor_zeile, cursor_spalte)), tasten() ->
# [(taste, was)], aenderungen() -> dict (wird ins Element übernommen).
#
# Optional: `rolle` (Farbrolle des Rahmens) und `blaettern(element, schritt)`
# (Bild↑/Bild↓ im gewählten Kasten), siehe canvas.py.
#
# 2026-10-09 gibt es „notiz" (ein Zettel des Canvas, in der Datei type
# "text", Markdown; erste Zeile = Titel) und „fremd" (was Obsidian sonst
# kennt: file, link, group — nur anzeigen). Der Zettel ist bewusst NICHT
# die Notiz des Notiz-Tools: dessen Format (data/notes.json) wird erst
# aufgearbeitet (Sasha, 2026-10-09); umstellen steht als offener Punkt in
# memory/system/desk_view.md.
#
# Nahtstelle für Kacheln anderer Apps (Hub-Bauplan, noch im Entwurf): eine
# Art „kachel:liste", „kachel:graph" … wird hier genauso registriert. Ihr
# `zeichne` gibt zurück, was die liefernde App für Art und Größe w×h
# geliefert hat (Text + Farbrollen) — geholt von der ANSICHT über HTTP und
# am Element zwischengelegt, nie vom Canvas selbst. Enter auf einer Kachel
# als Ereignis an die App braucht dann einen eigenen Rückgabewert im
# Canvas (wie „bearbeiten"); der Rest (Lage, Fokus, Schnüre) bleibt gleich.
# Langer Inhalt (z. B. eine Kalender-Kachel) blättert über `blaettern` wie
# der Zettel unten.

try:
    from tui.bausteine.textfeld import Textfeld
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine.textfeld import Textfeld


def umbrechen(text, breite):
    """Wortweise umbrechen; zu lange Wörter hart teilen. Steuerzeichen (Tab
    …) werden Leerzeichen, sonst verrutscht die Zeile im Terminal."""
    breite = max(1, breite)
    raus = []
    for roh in str(text).split("\n"):
        roh = "".join(c if c.isprintable() else " " for c in roh)
        zeile = ""
        for wort in roh.split(" "):
            while len(wort) > breite:
                if zeile:
                    raus.append(zeile)
                    zeile = ""
                raus.append(wort[:breite])
                wort = wort[breite:]
            neu = wort if not zeile else zeile + " " + wort
            if len(neu) <= breite:
                zeile = neu
            else:
                raus.append(zeile)
                zeile = wort
        raus.append(zeile)
    return raus


class TextModal:
    """Bearbeiten-Modal für ein Textfeld eines Elements (z. B. notiz.text)."""

    def __init__(self, titel, feld, text):
        self.titel = titel
        self.feld = feld
        self.eingabe = Textfeld(text)
        self.anfang = str(text or "")

    def taste(self, ch):
        return self.eingabe.taste(ch)

    def anzeige(self, breite, hoehe):
        return self.eingabe.anzeige(breite, hoehe)

    def tasten(self):
        return [("type", "write"), ("enter", "new line"),
                ("ctrl+s", "save"), ("esc", "cancel")]

    def geaendert(self):
        return self.eingabe.text != self.anfang

    def aenderungen(self):
        return {self.feld: self.eingabe.text}


class Notiz:
    """Ein Zettel: erste Zeile fett als Titel (ein „# " davor fällt weg),
    darunter der Text. Rahmen in der Farbrolle „amber" — Haftnotiz-gelb,
    aus farben.ROLES, keine eigene Farbe (2026-10-09)."""
    name = "notiz"
    rolle = "amber"
    BREITE, HOEHE = 24, 6

    def neu(self, eid, x, y):
        return {"id": eid, "art": self.name, "x": x, "y": y,
                "w": self.BREITE, "h": self.HOEHE, "text": ""}

    @staticmethod
    def _teile(text):
        kopf, _, rest = str(text or "").partition("\n")
        return kopf.lstrip("#").strip(), rest

    def zeichne(self, element, w, h):
        titel, rest = self._teile(element.get("text"))
        if not titel and not rest.strip():
            return [[("leer · e schreibt", "leise")]]
        zeilen = [[(t, "notiz_titel")] for t in umbrechen(titel, w)[:1]]
        koerper = umbrechen(rest, w) if rest.strip() else []
        platz = max(0, h - len(zeilen))
        oben = max(0, min(element.get("_oben", 0), max(0, len(koerper) - platz)))
        element["_oben"] = oben
        sicht = koerper[oben:oben + platz]
        if oben + platz < len(koerper) and sicht:      # unten geht es weiter
            sicht[-1] = sicht[-1][:max(0, w - 1)].ljust(max(0, w - 1)) + "…"
        return zeilen + sicht

    def blaettern(self, element, schritt):
        element["_oben"] = max(0, element.get("_oben", 0) + schritt)

    def modal(self, element):
        return TextModal("notiz", "text", element.get("text") or "")


class Fremd:
    """Knoten, die Obsidian kennt, diese TUI aber nicht bearbeitet (file,
    link, group): sie bleiben in der Datei, wie sie sind, und lassen sich
    verschieben und verbinden."""
    name = "fremd"

    def zeichne(self, element, w, h):
        return [[("[%s]" % element.get("typ", "?"), "leise")]] + umbrechen(element.get("titel", ""), w)

    def modal(self, element):
        return None


def standard_arten(arten):
    """Die Arten, die jede App mit Canvas heute kennt, in `arten` eintragen."""
    for art in (Notiz(), Fremd()):
        arten.registrieren(art)
    return arten
