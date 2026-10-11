"""Listen-Werkzeug: Bernsteinleiste + Anzeige-Reihenfolge einer Ebene.

Abgeschlossenes verschwindet aus der normalen Sicht (es steckt im Bernstein),
der Fokus klebt oben, der Rest sortiert sich nach wenigsten offenen Punkten."""
from tui.ansichten.fokus import bernstein_steine, liste_ordnen


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


def test_wenig_offen_steht_weiter_oben_gleichstand_bleibt_stabil():
    a = _ordner(1, [_blatt(10, True), _blatt(11), _blatt(12), _blatt(13)])  # 1/4 (3 offen)
    b = _ordner(2, [_blatt(20, True), _blatt(21, True), _blatt(22)])        # 2/3 (1 offen)
    c = _blatt(3)                                                            # 0/1 (1 offen)
    d = _blatt(4)                                                            # 0/1 (1 offen)
    assert _ids(liste_ordnen([c, a, d, b])) == [2, 3, 4, 1]


def test_offene_zaehlen_nicht_prozent():
    gross = _ordner(1, [_blatt(100 + i, i < 31) for i in range(37)])        # 31/37 (6 offen)
    klein = _ordner(2, [_blatt(20, True), _blatt(21)])                       # 1/2 (1 offen)
    assert _ids(liste_ordnen([gross, klein])) == [2, 1]


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


# ── Einträge als Kästen (seit 2026-10-11) ───────────────────────────
# Jeder Eintrag ist nur noch ein Kasten mit dem Titel; Status zeigt allein
# der Bernstein oben, keine pinke Leiste und kein Zähler je Eintrag.

def _schirm(h=24, w=40):
    """Fokus mit einem Schein-Bildschirm (Zeilen als Zeichenlisten)."""
    import types
    from tui.ansichten.fokus import Fokus
    gitter = [[" "] * w for _ in range(h)]

    def setzen(y, x, text, attr=0):
        for i, c in enumerate(str(text)):
            if 0 <= y < h and 0 <= x + i < w:
                gitter[y][x + i] = c

    C = {k: 0 for k in ("bright", "faint", "dim", "acc", "amber", "amberhi",
                        "amberdk", "graph", "warn")}
    z = types.SimpleNamespace(
        C=C, safe_addstr=setzen, draw_box=lambda *a, **k: None,
        addclip=lambda y, x, t, mw, attr=0, strike=False: setzen(y, x, str(t)[:max(0, mw)]),
        PIX={"voll": False, "pairs": {}}, PIX_MODUS="off", pix_attr=lambda *a: 0)
    f = Fokus.__new__(Fokus)
    f.z = z
    return f, gitter


def test_eintrag_ist_kasten_mit_titel_ohne_leiste():
    f, gitter = _schirm()
    f.L = {"view": "view", "path": [], "showdone": False, "isel": 0,
           "adding": False, "msg": "", "imode": "add", "input": "",
           "def": {"id": "l1", "name": "einkauf", "items": [
               _blatt(1), _blatt(2, done=True),
               _ordner(3, [_blatt(4), _blatt(5)])]}}
    f.draw_list_tool(0, 0, 24, 40)
    zeilen = ["".join(r) for r in gitter]
    titel = [i for i, z in enumerate(zeilen) if "▸ o3" in z or " p1 " in z]
    assert len(titel) == 2                          # beide offenen Einträge da
    for i in titel:                                 # je ein 3-Zeilen-Kasten
        assert zeilen[i - 1].strip().startswith("┌") and zeilen[i - 1].strip().endswith("┐")
        assert zeilen[i].strip().startswith("│") and zeilen[i].strip().endswith("│")
        assert zeilen[i + 1].strip().startswith("└")
        assert "/" not in zeilen[i]                 # kein Zähler im Kasten
    unter_bernstein = zeilen[titel[0] - 1:]
    assert not any("█" in z or "░" in z for z in unter_bernstein)  # keine Leiste
    assert "1/4" in "".join(zeilen[:titel[0]])      # Status nur im Bernstein oben


def test_pixel_bernstein_sitzt_wo_die_quelle_ihn_hinlegt():
    """Der Pixel-Bernstein ist nur Veredelung: gleiche Zeilen, gleiche Breite,
    der Zähler an derselben Stelle wie im Bild aus core/listen_bild.py."""
    import listen_bild
    items = [_blatt(1), _blatt(2, done=True), _blatt(3)]
    erwartet = listen_bild.ebene(items, 36, 20, ["einkauf"])
    leiste = "".join(t for t, _r in erwartet["zeilen"][erwartet["bernstein"]["zeile"]])
    f, gitter = _schirm()
    f.z.C["pix_bg"] = (0, 0, 0)
    f.z.PIX_MODUS = "mix"
    f.L = {"view": "view", "path": [], "showdone": False, "isel": 0,
           "adding": False, "msg": "", "imode": "add", "input": "",
           "def": {"id": "l1", "name": "einkauf", "items": items}}
    f.draw_list_tool(0, 0, 24, 40)
    zeile = "".join(gitter[1 + erwartet["bernstein"]["zeile"]])
    assert leiste.endswith(" 1/3") and zeile.rstrip().endswith(" 1/3")
    assert zeile.rstrip().index(" 1/3") == 2 + leiste.index(" 1/3")
    assert "▐" not in zeile                         # Pixel statt Rückfall-Fassung
