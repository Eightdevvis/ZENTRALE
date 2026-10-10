# core/kachel_form.py
#
# Die Form einer Kachel-Antwort und die Fehler, die eine Quelle melden kann
# — ohne Fachwissen, damit Hub (core/kacheln.py) und jede Quelle
# (core/kachel_kalender.py …) dasselbe meinen, ohne sich gegenseitig zu
# importieren. Was eine Kachel ist: memory/system/hub_bauplan.md „Kacheln".
#
# Eine Zeile ist eine Liste von Stücken [text, rolle]; die Rolle sagt, was
# das Stück BEDEUTET, nie welche Farbe es hat — das Wörterbuch steht in
# core/farbrollen.py, die Farbe wählt jede Oberfläche selbst. Was eine
# Quelle Unbekanntes schickt, wird hier „text" (2026-10-10, vorher hingen
# die Rollen an den Farben der TUI).
#
# Maße: w×h sind abstrakte ZELLEN eines Rasters (Spalten × Zeilen), immer
# das Innere ohne Rahmen. Ein Terminal zeigt eine Zelle als ein Zeichen,
# ein Fenster oder Handy rechnet sie in sein eigenes Raster um.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

import hashlib
import json

import farbrollen


class KachelFehler(ValueError):
    """Die Anfrage taugt nicht (Bezug kaputt, Bereich zu lang …). Der Text
    geht so an Sasha — Alltagswörter."""


class KachelWeg(LookupError):
    """Das Objekt, auf das die Kachel zeigt, gibt es nicht mehr."""


class KachelZuKlein(Exception):
    """Unter der Mindestgröße: w×h Zellen (Inneres) wären nötig."""

    def __init__(self, w, h):
        super().__init__("zu klein")
        self.w, self.h = int(w), int(h)


def stueck(text, rolle=farbrollen.RUECKFALL):
    return [str(text), str(rolle)]


def kuerzen(text, breite):
    """Auf `breite` Zeichen, mit „…" am Ende, wenn etwas fehlt."""
    text = "".join(c if c.isprintable() else " " for c in str(text))
    if breite <= 0:
        return ""
    if len(text) <= breite:
        return text
    return text[:breite - 1] + "…" if breite > 1 else text[:1]


def zeilen_kuerzen(zeilen, w, h):
    """Zeilen auf w×h bringen — die Quelle kürzt selbst (hub_bauplan.md),
    das hier ist das Netz darunter, falls sie sich verrechnet."""
    raus = []
    for zeile in zeilen[:max(0, h)]:
        rest, neu = w, []
        for text, rolle in zeile:
            if rest <= 0:
                break
            t = str(text)[:rest]
            neu.append([t, farbrollen.rolle(rolle)])
            rest -= len(t)
        raus.append(neu)
    return raus


def stand_von(*teile):
    """Kurzer Fingerabdruck eines Inhalts: gleicher Inhalt → gleicher Stand."""
    roh = json.dumps(teile, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(roh).hexdigest()[:16]
