# tui/bausteine/canvas_arten.py
#
# Die Elementarten für den Canvas (tui/bausteine/canvas.py). Eine Art ist
# ein kleines Objekt mit:
#   name                       wie in element["art"]
#   zeichne(element, w, h)     -> Zeilen für das Innere des Kastens (w×h);
#                                 eine Zeile ist ein str oder [(text, rolle)]
#   modal(element)             -> ein Bearbeiten-Modal oder None
#   neu(id, x, y)              -> ein frisches Element (nur Arten, die man
#                                 mit + anlegen kann; `neu_label` = Name im
#                                 Wähler von +)
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
# Nahtstelle für Kacheln anderer Apps (memory/system/hub_bauplan.md
# „Kacheln", entschieden 2026-10-09): in der Datei ein text-Knoten mit
# Rückfall-Text und `zentrale_kachel: {v: 2, adresse}` — die eine Adresse
# des Objekts, z. B. zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7
# (seit 2026-10-10; die alte Form {v: 1, app, art, ref} schreibt
# core/desk.py beim Lesen um). core/desk.py liefert ihn als Element mit art
# „kachel", `kachel` = dieses Feld, `titel` = Rückfall-Text, und ändert
# daran nie etwas außer der Lage. Solange keine Art
# „kachel" registriert ist, zeichnet „fremd" ihn (typ + Rückfall).
# Seit 2026-10-10 gibt es die Art „kachel" (unten): `zeichne` zeigt, was
# die ANSICHT über `POST /api/kachel` geholt und am Element unter „_inhalt"
# zwischengelegt hat (nie der Canvas selbst), `oeffnen` (Taste o) meldet
# („kachel_oeffnen", element) — die Ansicht schickt den Verweis an
# `POST /api/kachel/aktion`. Langer Inhalt (Kalender) blättert über
# `blaettern`: die Lage steht unter „_oben", die Ansicht holt damit neu (die
# App kürzt selbst). Die Art ist für alle Apps dieselbe; was `+` anbietet,
# kommt aus dem Katalog des Hubs (tui/ansichten/desk_neu.py).

try:
    from tui.bausteine.textfeld import Textfeld
    from tui.bausteine.canvas_bild import Bild
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine.textfeld import Textfeld
    from bausteine.canvas_bild import Bild


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
    neu_label = "zettel"
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


class Kachel:
    """Verweis auf ein Objekt einer anderen App (hub_bauplan.md „Kacheln").
    Weiß nichts von HTTP: die Ansicht legt unter element["_inhalt"] ab, was
    sie geholt hat — {zustand: laedt|ok|zu_klein|weg|aus|fehler, zeilen?,
    text?, oben_max?, zu_klein?: {w, h} (Außenmaß mit Rahmen)}. Ohne Inhalt
    steht der Rückfall-Text aus der Datei da (`titel`). 2026-10-10."""
    name = "kachel"

    def zeichne(self, element, w, h):
        inhalt = element.get("_inhalt") or {}
        zustand = inhalt.get("zustand", "laedt")
        zeilen = inhalt.get("zeilen") or []
        if zustand == "ok":
            return [[(t, r) for t, r in z] for z in zeilen[:h]]
        if zustand == "zu_klein":
            k = inhalt.get("zu_klein") or {}
            return [[("zu klein", "leise")],
                    [("mind. %s×%s" % (k.get("w", "?"), k.get("h", "?")), "leise")]]
        if zustand == "aus" and zeilen:
            # letzter Stand, leise: man sieht, dass er alt ist (hub_bauplan.md)
            return [[(t, "leise") for t, _r in z] for z in zeilen[:h]]
        kopf = {"laedt": "lädt …", "weg": "nicht mehr da", "aus": "app antwortet nicht",
                "fehler": inhalt.get("text") or "geht nicht"}.get(zustand, zustand)
        rolle = "warn" if zustand in ("weg", "fehler") else "leise"
        return [[(kopf, rolle)]] + [[(t, "leise")] for t in umbrechen(element.get("titel", ""), w)]

    def blaettern(self, element, schritt):
        grenze = (element.get("_inhalt") or {}).get("oben_max", 0) or 0
        element["_oben"] = max(0, min(grenze, element.get("_oben", 0) + schritt))

    def oeffnen(self, element):
        return ("kachel_oeffnen", element)

    def modal(self, element):
        return None


def standard_arten(arten):
    """Die Arten, die jede App mit Canvas heute kennt, in `arten` eintragen."""
    for art in (Notiz(), Bild(), Fremd(), Kachel()):
        arten.registrieren(art)
    return arten
