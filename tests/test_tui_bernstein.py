"""Listen-Werkzeug: Bernsteinleiste + Anzeige-Reihenfolge einer Ebene.

Abgeschlossenes verschwindet aus der normalen Sicht (es steckt im Bernstein),
der Fokus klebt oben, der Rest sortiert sich nach Erfülltheit absteigend."""
from tui.zentrale_tui import bernstein_steine, liste_ordnen


def _blatt(i, done=False, focus=False):
    return {"id": i, "text": "p%d" % i, "done": done, "focus": focus}


def _ordner(i, kids, focus=False):
    return {"id": i, "text": "o%d" % i, "items": kids, "focus": focus}


def _ids(rows):
    return [r["id"] for r in rows]


def test_erledigtes_verschwindet_aus_der_normalen_sicht():
    items = [_blatt(1, done=True), _blatt(2), _ordner(3, [_blatt(4, True)])]
    assert _ids(liste_ordnen(items)) == [2]
    assert _ids(liste_ordnen(items, erledigte=True)) == [1, 3]


def test_mehr_erfuellt_steht_weiter_oben_gleichstand_bleibt_stabil():
    a = _ordner(1, [_blatt(10, True), _blatt(11), _blatt(12), _blatt(13)])  # 1/4
    b = _ordner(2, [_blatt(20, True), _blatt(21, True), _blatt(22)])        # 2/3
    c = _blatt(3)                                                            # 0/1
    d = _blatt(4)                                                            # 0/1
    assert _ids(liste_ordnen([c, a, d, b])) == [2, 1, 3, 4]


def test_fokus_klebt_oben_auch_wenn_er_tief_steckt():
    voll = _ordner(1, [_blatt(10, True), _blatt(11)])                        # 1/2
    tief = _ordner(2, [_blatt(20), _blatt(21, focus=True)])                  # 0/2
    assert _ids(liste_ordnen([voll, tief])) == [2, 1]
    assert _ids(liste_ordnen([_blatt(5), _blatt(6, focus=True)])) == [6, 5]


def test_ordnen_ist_robust():
    assert liste_ordnen(None) == []
    assert liste_ordnen([None, "x", 3]) == []
    assert _ids(liste_ordnen([_ordner(1, [])])) == [1]     # leerer Ordner = offen


def test_ein_stein_je_punkt_und_abgehakte_leuchten():
    cols = bernstein_steine(2, 5, 20)            # 4 Spalten je Punkt: 3 Stein + Fuge
    steine = "".join(cols).split()
    assert len(steine) == 5
    assert steine[:2] == ["LLL", "LLL"] and steine[2:3] == ["UUU"]
    assert len(cols) == 20 and cols[-1] != " "   # füllt die Leiste ganz


def test_steine_fuellen_auch_krumme_breiten():
    cols = bernstein_steine(6, 13, 50)
    assert len(cols) == 50 and cols[-1] != " "
    assert len("".join(cols).split()) == 13


def test_enge_leiste_ohne_fugen_und_skaliert_bei_zu_vielen_punkten():
    assert bernstein_steine(1, 3, 3) == ["L", "U", "U"]
    assert " " not in bernstein_steine(1, 3, 5)
    cols = bernstein_steine(50, 100, 10)         # 10 Punkte je Spalte
    assert cols == ["L"] * 5 + ["U"] * 5


def test_steine_werfen_nie():
    for args in [(0, 0, 10), (5, 3, 10), (-1, 3, 10), (1, 3, 0), (None, 3, 5),
                 ("x", 3, 5), (1, 3, -4), (3, 3, 1)]:
        cols = bernstein_steine(*args)
        assert isinstance(cols, list)
        assert all(c in ("L", "U", " ") for c in cols)
