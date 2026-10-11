"""
Programm und Kachel teilen EIN Bild (Sasha 2026-10-11, memory/hub/listen_app.md).

Das Aussehen eines Listeneintrags steht nur in core/listen_bild.py. Die
Listen-Kachel (core/kachel_fokus.py) und die Listen-Ansicht der TUI
(tui/ansichten/fokus.py) zeigen beide nur, was dort herauskommt. Diese Tests
wachen darüber: dieselbe Liste ergibt in Kachel und TUI dieselben Zeilen,
und die Kachel bekommt keinen eigenen Zeichner zurück.
"""
import ast
import inspect
import os
import types

import farbrollen
import kacheln
import kachel_fokus
import listen_bild
import lists

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Zeichen, an denen man einen eigenen Listen-Look erkennt
LOOK = set("┌┐└┘│─▐▌█░▸▾◆★○✓")


def _text(zeile):
    return "".join(t for t, _r in zeile)


def _liste():
    lid = lists.create_list("Einkauf")["id"]
    for t in ("Milch", "Brot", "Eier"):
        lists.add_item(lid, t)
    ordner = lists.add_item(lid, "Baumarkt")
    lists.add_item(lid, "Schrauben", ordner["id"])
    lists.toggle_item(lid, 2)                         # Brot erledigt
    lists.set_focus(lid, 3)                           # Eier ◆
    return lid


def _kachel(lid, w, h, erledigte=False):
    status, a = kacheln.holen({"adresse": "zentrale://fokus/liste?erledigte=%s&liste=%s"
                               % ("true" if erledigte else "false", lid), "w": w, "h": h})
    assert status == 200, a
    return a


def _tui(lst, w, h, showdone=False):
    """Die Listen-Ansicht auf einem Schein-Bildschirm, Inhalt genau w×h."""
    from tui.ansichten.fokus import Fokus
    bw, bh = w + 4, h + 2                             # Rahmen + Hinweiszeile
    gitter = [[" "] * bw for _ in range(bh)]

    def setzen(y, x, text, attr=0):
        for i, c in enumerate(str(text)):
            if 0 <= y < bh and 0 <= x + i < bw:
                gitter[y][x + i] = c

    z = types.SimpleNamespace(
        C={k: 0 for k in ("bright", "faint", "acc", "amber", "amberhi", "amberdk")},
        safe_addstr=setzen, draw_box=lambda *a, **k: None,
        addclip=lambda y, x, t, mw, attr=0, strike=False: setzen(y, x, str(t)[:max(0, mw)]),
        PIX={"voll": False, "pairs": {}}, PIX_MODUS="off", pix_attr=lambda *a: 0)
    f = Fokus.__new__(Fokus)
    f.z = z
    f.L = {"view": "view", "path": [], "showdone": showdone, "isel": 0, "adding": False,
           "msg": "", "imode": "add", "input": "", "def": lst}
    f.draw_list_tool(0, 0, bh, bw)
    return ["".join(r)[2:2 + w] for r in gitter[1:1 + h]]


def test_dieselbe_liste_ist_in_kachel_und_tui_dasselbe_bild():
    lid = _liste()
    lst = next(l for l in lists.read_lists() if l["id"] == lid)
    for w, h, erledigte in ((36, 16, False), (30, 10, False), (24, 12, True)):
        kachel = [_text(z) for z in _kachel(lid, w, h, erledigte)["zeilen"]]
        tui = _tui(lst, w, h, showdone=erledigte)
        assert kachel, (w, h)
        # Seit 2026-10-11 ohne „[a neu]" im Kopf (Tasten nur in der Leiste):
        # auch der Kopf ist Zeile für Zeile derselbe.
        for k, t in zip(kachel, tui):
            assert t.rstrip() == k.rstrip(), (w, h, k, t)
        assert all(not t.strip() for t in tui[len(kachel):])


def test_kachel_ist_das_bild_der_quelle_rollen_und_alles():
    lid = _liste()
    lst = next(l for l in lists.read_lists() if l["id"] == lid)
    bild = listen_bild.ebene(lst["items"], 30, 14, [lst["name"]])
    assert _kachel(lid, 30, 14)["zeilen"] == bild["zeilen"]


def test_kachel_reicht_nur_durch(monkeypatch):
    """Die Kachel zeichnet nicht selbst: was listen_bild liefert, geht
    unverändert hinaus (der Hub kürzt nur, was über w×h hinausginge)."""
    lid = _liste()
    marke = [[["eigenes design", "betont"]]]
    monkeypatch.setattr(listen_bild, "ebene", lambda *a, **k: {
        "zeilen": marke, "oben": 0, "oben_max": 0})
    assert _kachel(lid, 30, 10)["zeilen"] == marke


def test_kachel_fokus_hat_keinen_eigenen_eintrags_zeichner():
    """Wächter: kein eigener Look in der Kachel — keine Rahmen-/Marken-
    Zeichen, kein Bau von Stücken, nur listen_bild."""
    pfad = os.path.join(WURZEL, "core", "kachel_fokus.py")
    baum = ast.parse(open(pfad, encoding="utf-8").read())
    importe = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            assert not (set(knoten.value) & LOOK), \
                "kachel_fokus zeichnet selbst (%r) — Aussehen gehört in core/listen_bild.py" % knoten.value
        if isinstance(knoten, ast.Import):
            importe |= {a.name for a in knoten.names}
        if isinstance(knoten, ast.ImportFrom):
            importe |= {"%s.%s" % (knoten.module, a.name) for a in knoten.names}
    assert "listen_bild" in importe
    assert not {"kachel_form.stueck", "kachel_form.kuerzen", "listen_baum"} & importe
    eigene = {n.name for n in baum.body if isinstance(n, ast.FunctionDef)}
    assert eigene <= {"_liste", "parameter_jetzt", "_pruefen", "kachel", "bevorzugt", "aktion"}, \
        "neue Funktion in kachel_fokus: %s — zeichnet sie? Dann nach listen_bild" % (
            eigene - {"_liste", "parameter_jetzt", "_pruefen", "kachel", "bevorzugt", "aktion"})


def test_tui_kasten_zeichnet_nicht_selbst():
    """Auch die Vollansicht malt nur: der Kasten und die Ebene kommen aus
    listen_bild, in ihrem Code stehen keine Rahmen-Zeichen."""
    from tui.ansichten.fokus import Fokus
    for f in (Fokus.kasten_render, Fokus._malen):
        assert not (set(inspect.getsource(f)) & set("┌┐└┘│▸◆★")), f.__name__
    quelle = inspect.getsource(Fokus.draw_list_tool)
    assert "listen_bild.ebene(" in quelle and "rows_render" not in quelle


def test_listen_bild_nur_rollen_aus_dem_woerterbuch_und_ohne_kern():
    assert set(listen_bild.ROLLEN) <= set(farbrollen.ROLLEN)
    baum = ast.parse(open(os.path.join(WURZEL, "core", "listen_bild.py"), encoding="utf-8").read())
    importe = {a.name for n in ast.walk(baum) if isinstance(n, ast.Import) for a in n.names}
    importe |= {n.module for n in ast.walk(baum) if isinstance(n, ast.ImportFrom)}
    assert importe == {"listen_baum"}             # kein curses, läuft auch auf dem Aussenposten


def test_kasten_marker_auswahl_und_mehr():
    e = listen_bild.eintrag({"text": "Bau", "items": [{"id": 1}], "focus": True, "project": True})
    oben, mitte, unten = listen_bild.kasten(e, 20, gewaehlt=True, mehr=4)
    assert _text(mitte) == "│ ▸ Bau ★ ◆        │" and len(_text(oben)) == 20
    assert ["▸ Bau ★ ◆", "auswahl"] in mitte and oben[0][1] == "betont"
    assert _text(unten).endswith(" +4 ─┘") and len(_text(unten)) == 20
    ohne = listen_bild.eintrag({"text": "Bau", "project": True}, projekt_marke=False)
    assert listen_bild.titel(ohne) == "Bau"
    assert _text(listen_bild.kasten(ohne, 12)[1]) == "│ Bau      │"
