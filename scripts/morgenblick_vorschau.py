#!/usr/bin/env python3
# scripts/morgenblick_vorschau.py
#
# Der Morgenblick mit Beispieltagen — zum Ansehen der Gestaltung, ohne
# Sashas Daten und ohne KI (feste Sätze):
#     scripts/morgenblick_vorschau.py <ordner>
# schreibt voll.html, normal.html, frei.html, leer.html nach <ordner>.
# Als Bild: den Ordner mit einem Chromium-Browser headless abfotografieren
# (memory/werkzeuge/morgenblick.md, „Prüfen").
#
# 2026-10-08.

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

import morgenblick as mb             # noqa: E402
import morgenblick_daten as daten    # noqa: E402


def T(titel, von, bis=None):
    def m(s):
        h, mi = s.split(":")
        return int(h) * 60 + int(mi)
    return {"titel": titel, "start": m(von), "ende": m(bis) if bis else None}


BEISPIELE = {
    "voll": [T("Stand-up", "07:00", "07:30"), T("Workshop Karte", "09:00", "12:00"),
             T("Mittag mit Jonas", "12:30", "13:30"), T("Probe Bandraum", "14:00", "15:00"),
             T("Abgabe Förderantrag", "15:00", "16:30"), T("Review", "16:00", "17:00"),
             T("Geige", "20:00", "21:30")],
    "normal": [T("Einkaufen", "10:00", "11:00"), T("Telefon mit Mia", "15:00", "15:45"),
               {"titel": "Geburtstag Oma", "ganztags": True}],
    "frei": [T("Parkour", "18:00", "19:00")],
    "leer": [],
}


def beispiel(name, termine):
    leer = name == "leer"
    g = {"datum": "2026-10-08",
         "kalender": {"heute": termine, "form": daten.tagesform(termine),
                      "morgen": [] if leer else [T("Zug nach Berlin", "08:10", "11:00")]},
         "mail": {"ungelesen_anzahl": 0 if leer else 3,
                  "unbekannte_absender_anzahl": 2 if name == "voll" else 0,
                  "einsortiert_24h": 0 if leer else 14},
         # Ein bösartiger Titel: muss als Text erscheinen, nie als Markup.
         "gespraeche": {"ungelesene_antwort":
                        ["Umzug <script>alert(1)</script> planen"] if name == "normal" else []},
         "ablage": {"neu_24h": [] if leer else ["Packliste Herbstferien"]}}
    blick = mb.rueckfall(g)
    if name == "voll":
        blick["knoepfe"] = mb.knoepfe_pruefen(
            [{"zu": 1, "beschriftung": "Ordner vorschlagen",
              "auftrag": "Zwei Mails von unbekannten Absendern liegen im Eingang. "
                         "Schlag für jede einen Ordner vor; fertig ist eine kurze Liste."}],
            len(blick["braucht_dich"]))
    return mb.html_fuer(g, blick)


def main():
    ziel = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(ziel, exist_ok=True)
    for name, termine in BEISPIELE.items():
        pfad = os.path.join(ziel, name + ".html")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(beispiel(name, termine))
        print(pfad, daten.tagesform(termine))


if __name__ == "__main__":
    main()
