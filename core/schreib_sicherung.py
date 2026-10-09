# core/schreib_sicherung.py
#
# „Ganz oder gar nicht" für schreibende Werkzeuge, deren Dienst das nicht
# selbst kann: vor dem Schreiben die betroffenen Dateien merken, nach dem
# Schreiben nachlesen — und wenn es nicht so dasteht wie verlangt, den alten
# Stand Byte für Byte zurücklegen (2026-10-09, core/fehlercodes.py: es gibt
# nur ERLEDIGT oder ABGEBROCHEN).
#
#   s = Sicherung(dateien=[...], ordner=[...])
#   … schreiben, nachlesen …
#   s.zurueck()        # alles wie vorher: geänderte Dateien zurück,
#                      # neue Dateien und neue (leere) Ordner weg
#
# Ordner werden rekursiv gemerkt, ohne versteckte Einträge (.git, Zwischen-
# dateien). Für kleine Datenordner gedacht (Gedächtnis, ein Ablage-Dokument,
# eine Skill-Mappe) — nicht für data/ als Ganzes.
#
# Der Kalender braucht das nicht: sein Kern lehnt per Kennung ab, ohne zu
# schreiben (core/kalender_kennung.py).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

import os

import dateien


def _lesen(pfad):
    try:
        with open(pfad, "rb") as f:
            return f.read()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def _baum(ordner) -> tuple:
    """-> ({datei: bytes}, {ordner}) unter `ordner`, ohne Verstecktes."""
    dateien_, ordner_ = {}, set()
    if not os.path.isdir(ordner):
        return dateien_, ordner_
    for wurzel, unter, namen in os.walk(ordner):
        unter[:] = [u for u in unter if not u.startswith(".")]
        ordner_.add(os.path.abspath(wurzel))
        for n in namen:
            if n.startswith("."):
                continue
            p = os.path.abspath(os.path.join(wurzel, n))
            dateien_[p] = _lesen(p)
    return dateien_, ordner_


class Sicherung:
    def __init__(self, dateien=(), ordner=()):
        self._dateien = {os.path.abspath(p): _lesen(p) for p in dateien}
        self._ordner = [os.path.abspath(o) for o in ordner]
        self._baeume = {}
        for o in self._ordner:
            self._baeume[o] = _baum(o)
        self.zurueckgelegt = False

    def geaendert(self) -> bool:
        """Hat sich seit dem Merken etwas geändert?"""
        if any(_lesen(p) != alt for p, alt in self._dateien.items()):
            return True
        return any(_baum(o)[0] != self._baeume[o][0] for o in self._ordner)

    def zurueck(self) -> None:
        """Den gemerkten Stand wiederherstellen (atomar je Datei)."""
        for p, alt in self._dateien.items():
            self._eine(p, alt)
        for o in self._ordner:
            alt_dateien, alt_ordner = self._baeume[o]
            jetzt_dateien, jetzt_ordner = _baum(o)
            for p in set(jetzt_dateien) | set(alt_dateien):
                self._eine(p, alt_dateien.get(p))
            # neu entstandene Ordner, tiefste zuerst, nur wenn jetzt leer
            for d in sorted(jetzt_ordner - alt_ordner, key=len, reverse=True):
                try:
                    os.rmdir(d)
                except OSError:
                    pass
            if not os.path.isdir(o) and alt_ordner:
                os.makedirs(o, exist_ok=True)
        self.zurueckgelegt = True

    @staticmethod
    def _eine(pfad, alt) -> None:
        jetzt = _lesen(pfad)
        if jetzt == alt:
            return
        if alt is None:
            try:
                os.remove(pfad)
            except FileNotFoundError:
                pass
        else:
            dateien.atomar_schreiben(pfad, alt)
