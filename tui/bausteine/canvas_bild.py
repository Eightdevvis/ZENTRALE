# tui/bausteine/canvas_bild.py
#
# Art „bild" für den Canvas (2026-10-10). Sasha: „Images soll man auch
# draufbappen. Fürs Terminal eine Zwischenlösung: es wird eine Preview mit
# Titel als Kachel angezeigt, die Preview das Bild verpixelt …, und man
# kann es im Imageviewer direkt geöffnet kriegen."
#
# Element: {id, x, y, w, h, art: "bild", datei, titel, modus}
#   datei   Pfad relativ zum Desk-Ordner (in der Datei ein file-Knoten)
#   titel   eigener Titel oder "" (dann gilt der Dateiname ohne Endung)
#   modus   "mono" | "farbe" — Taste `f` schaltet um
# Zwischengelegt von der ANSICHT (nie gespeichert, Vorsilbe „_"):
#   _vorschau  {status, zeilen?, text?} aus POST /api/desk-bild/vorschau —
#              Sashas ASCII-Filter (core/bild_vorschau.py)
#
# Wie Kacheln zeichnet die Art nur, was die Ansicht geholt hat; sie fragt
# kein Backend. `o` meldet ("bild_oeffnen", datei) — die Ansicht öffnet
# das Bild im Bildbetrachter. Farben gehen als Rolle "#rrggbb" hinaus; die
# Ansicht macht daraus ein Pixel-Farbpaar (Vordergrund auf Theme-Grund).

import os

try:
    from tui.bausteine import tastenteil
    from tui.bausteine.textfeld import TASTEN_ZEILE, Textfeld
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine import tastenteil
    from bausteine.textfeld import TASTEN_ZEILE, Textfeld

MODI = ("mono", "farbe")


def titel(element):
    eigen = str(element.get("titel") or "").strip()
    if eigen:
        return eigen
    return os.path.splitext(os.path.basename(str(element.get("datei") or "")))[0] or "bild"


def vorschau_groesse(element):
    """(spalten, zeilen) der Vorschau im Kasten: innen, ohne die Titelzeile."""
    return max(1, element["w"] - 2), max(1, element["h"] - 3)


class TitelModal:
    """Titel eines Bildes: eine Zeile, enter oder ctrl+s speichert. Leer =
    wieder der Dateiname."""
    titel = "bild-titel"
    TASTEN = {"tippen": [
        ("type", "tippen", "title"), ("enter", "speichern", "save"), ("ctrl+s", "speichern"),
        ("esc", "abbrechen", "cancel"), (TASTEN_ZEILE, "feld"),
    ]}

    def __init__(self, text):
        self.eingabe = Textfeld(text)

    def __repr__(self):
        return "TitelModal(%r)" % (self.eingabe,)

    def ansicht(self):
        return "tippen"

    def taste(self, ch):
        if 0x80 <= ch <= 0xFF:          # Umlaut-Bytes setzt das Textfeld zusammen
            return self.eingabe.taste(ch)
        return tastenteil.verteilen(self, ch)

    def aktion_tippen(self, zeichen):
        return self.eingabe.taste(ord(zeichen))

    def aktion_feld(self, taste):
        return self.eingabe.taste_name(taste)

    def aktion_speichern(self, _taste):
        return "speichern"

    def aktion_abbrechen(self, _taste):
        return "abbrechen"

    def anzeige(self, breite, hoehe):
        return self.eingabe.anzeige(breite, hoehe)

    def aenderungen(self):
        return {"titel": " ".join(self.eingabe.text.split())}


class Bild:
    name = "bild"
    rolle = "dim"
    neu_label = "bild"
    TASTEN = [("o", "oeffnen", "open"), ("f", "art_taste", "mono/colour"),
              ("e", "bearbeiten", "title")]

    def neu(self, eid, x, y, datei="", w=34, h=12):
        return {"id": eid, "art": self.name, "x": x, "y": y, "w": w, "h": h,
                "datei": datei, "titel": "", "modus": "mono"}

    def zeichne(self, element, w, h):
        zeilen = [[(titel(element)[:w], "bild_titel")]]
        v = element.get("_vorschau")
        if not v:
            return zeilen + [[("lädt …", "leise")]]
        if v.get("status") != "ok":
            return zeilen + [[(str(v.get("text") or "keine vorschau")[:w], "leise")]]
        for reihe in (v.get("zeilen") or [])[:max(0, h - 1)]:
            stuecke = []
            for zeichen, farbe in reihe[:w]:
                stuecke.append((zeichen, farbe if (farbe and zeichen != " ") else "bild"))
            zeilen.append(stuecke)
        return zeilen

    def grenzen(self, element):
        # Titel + eine Zeile Vorschau (2026-10-10); oben die Grenze der
        # Vorschau im Backend (core/bild_vorschau.py: 400 Spalten, 200
        # Zeilen) plus Rahmen und Titelzeile.
        return (10, 4), (402, 203)

    def modal(self, element):
        return TitelModal(str(element.get("titel") or ""))

    def oeffnen(self, element):
        return ("bild_oeffnen", element.get("datei"))

    def taste(self, element, zeichen):
        if zeichen != "f":
            return False
        element["modus"] = "farbe" if element.get("modus") != "farbe" else "mono"
        element.pop("_vorschau", None)          # die Ansicht holt die neue
        element.pop("_vorschau_fuer", None)
        return True
