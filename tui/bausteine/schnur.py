# tui/bausteine/schnur.py
#
# Schnüre zwischen zwei Kästen auf dem Canvas — reine Geometrie, kein
# curses. Sasha, 2026-10-09: Elemente „wie mit einer Schnur verbinden, und
# die Schnur bleibt dran, wenn man Elemente verschiebt". Deshalb wird eine
# Schnur NIE gespeichert, sondern bei jedem Bild aus den aktuellen Lagen neu
# gelegt: rechtwinklig, mit Box-Zeichen, die Andockseite nach der Lage der
# beiden Kästen zueinander.
#
# Ein Kasten ist alles mit x, y, w, h (Zellen, Welt-Koordinaten).

# Richtungen einer Zelle: wohin die Linie aus ihr herausgeht.
_ZEICHEN = {
    frozenset("lr"): "─", frozenset("ud"): "│",
    frozenset("rd"): "┌", frozenset("ld"): "┐", frozenset("ru"): "└", frozenset("lu"): "┘",
    frozenset("lrd"): "┬", frozenset("lru"): "┴", frozenset("udr"): "├", frozenset("udl"): "┤",
    frozenset("lrud"): "┼",
    frozenset("l"): "─", frozenset("r"): "─", frozenset("u"): "│", frozenset("d"): "│",
}
# Spitze am Ziel, nach der Richtung, in der die Schnur ankommt. Einspaltige
# Zeichen (▸ statt ▶), sonst verrutscht die Zeile.
_SPITZE = {"r": "▸", "l": "◂", "d": "▾", "u": "▴"}


def mitte(k):
    return k["x"] + k["w"] // 2, k["y"] + k["h"] // 2


def seiten(a, b):
    """Andockseiten (von, nach) nach der Lage von b zu a. Eine Zeile ist etwa
    doppelt so hoch wie eine Spalte breit — der senkrechte Abstand zählt
    deshalb doppelt, sonst ginge die Schnur bei schräger Lage zu oft oben
    raus."""
    (ax, ay), (bx, by) = mitte(a), mitte(b)
    dx, dy = bx - ax, (by - ay) * 2
    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy > 0 else ("top", "bottom")


def anker(k, seite):
    """Die Zelle direkt vor der Seite des Kastens -> (x, y)."""
    cx, cy = mitte(k)
    return {"right": (k["x"] + k["w"], cy), "left": (k["x"] - 1, cy),
            "bottom": (cx, k["y"] + k["h"]), "top": (cx, k["y"] - 1)}[seite]


def weg(a, b):
    """Eckpunkte der Schnur von Kasten a nach b: erst raus aus der Seite,
    auf halber Strecke einmal abbiegen, dann hinein. -> [(x, y), …]"""
    sa, sb = seiten(a, b)
    (ax, ay), (bx, by) = anker(a, sa), anker(b, sb)
    if sa in ("left", "right"):
        mx = (ax + bx) // 2
        return [(ax, ay), (mx, ay), (mx, by), (bx, by)]
    my = (ay + by) // 2
    return [(ax, ay), (ax, my), (bx, my), (bx, by)]


def _zellen_der_strecke(punkte):
    """Eckpunkte -> jede Zelle der Linie einmal, in Reihenfolge."""
    raus = []
    for (x0, y0), (x1, y1) in zip(punkte, punkte[1:]):
        sx = (x1 > x0) - (x1 < x0)
        sy = (y1 > y0) - (y1 < y0)
        x, y = x0, y0
        while True:
            if not raus or raus[-1] != (x, y):
                raus.append((x, y))
            if (x, y) == (x1, y1):
                break
            x, y = x + sx, y + sy
    if not raus and punkte:
        raus.append(punkte[0])
    return raus


def _richtung(von, nach):
    dx, dy = nach[0] - von[0], nach[1] - von[1]
    return "r" if dx > 0 else "l" if dx < 0 else "d" if dy > 0 else "u"


def richtungen(punkte, netz=None):
    """Die Linie in ein Netz {(x, y): set(richtungen)} eintragen. Mehrere
    Schnüre im selben Netz ergeben von selbst Kreuzungen und Abzweige (┼ ├).
    -> (netz, ende): ende = (x, y, richtung des Ankommens) oder None."""
    netz = {} if netz is None else netz
    zellen = _zellen_der_strecke(punkte)
    for i, z in enumerate(zellen):
        r = netz.setdefault(z, set())
        if i > 0:
            r.add(_richtung(z, zellen[i - 1]))
        if i + 1 < len(zellen):
            r.add(_richtung(z, zellen[i + 1]))
    ende = None
    if len(zellen) >= 2:
        ende = zellen[-1] + (_richtung(zellen[-2], zellen[-1]),)
    elif zellen:
        ende = zellen[0] + ("r",)
    return netz, ende


def zeichen(richtungs_menge):
    return _ZEICHEN.get(frozenset(richtungs_menge), "┼" if richtungs_menge else " ")


def spitze(richtung):
    return _SPITZE.get(richtung, "•")


def halbe(punkte):
    """Die Zelle auf halber Länge (für eine Beschriftung)."""
    zellen = _zellen_der_strecke(punkte)
    return zellen[len(zellen) // 2] if zellen else None
