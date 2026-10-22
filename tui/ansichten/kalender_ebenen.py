"""Wochenansicht C: wer wo in der Tagesspalte liegt (aus kalender_ansichten.py
ausgelagert, 22.10.2026 — die Datei war über der Riesen-Grenze).

`bahnen` legt sich überschneidende Blöcke nebeneinander, `lagen` rechnet
sie in Rechtecke der Leinwand um. Beide sind rein (keine Farben, kein curses).
Die Ebenen ruft kalender_ansichten._c_achse getrennt: feste Termine unter sich,
uncommitted unter sich — uncommitted liegt UNTER den festen (22.10.2026).
"""
import math


def bahnen(bloecke, raster=None):
    """Überschneidungen nebeneinander, wie im Google-/Apple-Kalender: Bahnen
    gelten je Überlappungs-Gruppe (zusammenhängende Kette sich schneidender
    Blöcke), nicht für den ganzen Tag (Sasha, 22.10.2026: sonst werden alle
    Termine gequetscht, obwohl sie Platz hätten). In der Gruppe bekommt
    jeder Block die erste freie Bahn (Greedy) und dehnt sich nach rechts in
    Nachbarbahnen aus, in denen nichts mit ihm kollidiert.

    Ob sich zwei Blöcke schneiden, entscheiden die GEZEICHNETEN Zeilen, nicht
    die Minuten: raster=(lo, takt) rechnet jeden Block auf die Rasterzeilen um,
    die _c_achse ihm gibt (10:00–10:15 und 10:15–11:00 liegen bei 30-min-Takt
    beide auf der 10:00-Zeile). Sonst bekämen beide die volle Spalte und der
    zweite übermalte den ersten (Sasha, 22.10.2026: „überdecken sich nun
    einfach nur"). Ohne raster gelten die Minuten.
    -> [(bahn, bis_bahn, bahnen_der_gruppe, s, e, t)]; ein Block ohne
    Überschneidung ist (0, 0, 1, …) = volle Spalte."""
    def spanne(s, e):
        if raster is None:
            return s, e
        lo, m = raster
        k0 = (s - lo) // m
        return k0, max(k0 + 1, -(-(e - lo) // m))   # wie k0/k1 in _c_achse

    out: list = []
    gruppe: list = []
    ende_je_bahn: list = []
    gruppen_ende = None

    def abschliessen():
        ng = max(1, len(ende_je_bahn))
        for bi, a, b, s, e, t in gruppe:
            bis = bi
            while bis + 1 < ng and not any(
                    g[0] == bis + 1 and g[1] < b and a < g[2] for g in gruppe):
                bis += 1
            out.append((bi, bis, ng, s, e, t))

    zeilen = [spanne(s, e) + (s, e, t) for s, e, t in bloecke]
    for a, b, s, e, t in sorted(zeilen, key=lambda z: (z[0], z[2], -z[1], -z[3])):
        if gruppen_ende is not None and a >= gruppen_ende:
            abschliessen()
            gruppe, ende_je_bahn, gruppen_ende = [], [], None
        for i, be in enumerate(ende_je_bahn):
            if a >= be:
                ende_je_bahn[i] = b
                break
        else:
            i = len(ende_je_bahn)
            ende_je_bahn.append(b)
        gruppe.append((i, a, b, s, e, t))
        gruppen_ende = b if gruppen_ende is None else max(gruppen_ende, b)
    if gruppe:
        abschliessen()
    return out


def lagen(bahnen, xs, pw, lo, m, sicht_ende) -> list:
    """Bahnen eines Tages (bahnen) → sichtbare Rechtecke
    [(t, s, e, bx, bw, k0, k1)]: Spalte bx, Breite bw, Rasterzeilen k0..k1."""
    out = []
    for bi, bis, nb, s, e, t in bahnen:
        if e <= lo or s >= sicht_ende:
            continue
        teil = max(1, (pw - (nb - 1)) // nb)
        bx = xs + bi * (teil + 1)
        rand = xs + pw if bis >= nb - 1 else xs + bis * (teil + 1) + teil
        if bx >= xs + pw:
            continue
        k0 = (max(s, lo) - lo) // m
        k1 = max(k0, math.ceil((min(e, sicht_ende) - lo) / m) - 1)
        out.append((t, s, e, bx, max(1, rand - bx), k0, k1))
    return out
