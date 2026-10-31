"""
Der Canvas-Baustein (tui/bausteine/canvas.py, schnur.py, textfeld.py,
canvas_arten.py) ohne Terminal: Zustände, Fokus-Sprung, Greifen, Schnüre,
Tastentabelle (seit 2026-10-11 statt eigener Tastendeutung), Zettel-Editor. Desk View, 2026-10-09
(memory/hub/desk_view.md).
"""
import curses

from tui.bausteine import canvas as cv
from tui.bausteine import schnur
from tui.bausteine.canvas_arten import Fremd, Kachel, Notiz, TextModal, standard_arten, umbrechen
from tui.bausteine.textfeld import Textfeld
from tui.ansichten.tasten import Tasten

# Die Tabelle, wie der Desk sie einbindet (Canvas + Zeilen der Arten).
TAB = Tasten(cv.tabelle_mit(standard_arten(cv.Arten())))


def druecke(c, ch):
    """Eine Taste (curses-Code) über die Tabelle an den Canvas."""
    return TAB.verteilen(c, c.ansicht(), ch)


def zettel(eid, x, y, w=10, h=4, text=""):
    return {"id": eid, "art": "notiz", "x": x, "y": y, "w": w, "h": h, "text": text}


def kreuz():
    """Mitte m und je ein Zettel oben/unten/links/rechts."""
    return [zettel("m", 0, 0), zettel("o", 0, -10), zettel("u", 0, 10),
            zettel("l", -30, 0), zettel("r", 30, 0)]


def leinwand(elemente=None, verbindungen=None, neu=True):
    arten = standard_arten(cv.Arten())
    notiz = arten.holen("notiz")
    c = cv.Canvas(arten, elemente if elemente is not None else kreuz(), verbindungen,
                  neu=(lambda x, y: notiz.neu(cv.neue_id(), x, y)) if neu else None)
    c.vx, c.vy, c.vw, c.vh = -40, -15, 80, 30
    return c


# ── Tastentabelle (2026-10-11) ────────────────────────────────────

def test_jede_aktion_der_tabelle_hat_eine_methode():
    assert TAB.fehlende_methoden(leinwand()) == []


def test_ansicht_folgt_zustand_und_gewaehlter_art():
    c = leinwand(kreuz() + [{"id": "f", "art": "fremd", "x": 60, "y": 0, "w": 10, "h": 4},
                            {"id": "b", "art": "bild", "x": 60, "y": 20, "w": 14, "h": 6}])
    assert c.ansicht() == "ruhe"                       # nichts gewählt
    c.fokus = "m"
    assert c.ansicht() == "notiz"                      # Art mit eigenen Zeilen
    c.fokus = "f"
    assert c.ansicht() == "kasten"                     # Art ohne: die allgemeine
    c.fokus = "b"
    assert c.ansicht() == "bild"
    c.taste("enter")
    assert c.ansicht() == "greifen"


def test_tasten_der_tabelle():
    assert TAB.nimmt("notiz", "up") == "waehlen"
    assert TAB.nimmt("notiz", "enter") == "greifen"
    assert TAB.nimmt("notiz", "+") == "neu"
    assert TAB.nimmt("notiz", "e") == "bearbeiten"
    assert TAB.nimmt("notiz", "v") == "verbinden"
    assert TAB.nimmt("notiz", "x") == TAB.nimmt("notiz", "del") == "loeschen"
    assert TAB.nimmt("notiz", "r") == "groesse"
    assert TAB.nimmt("notiz", "o") is None             # ein Zettel öffnet nichts
    assert TAB.nimmt("bild", "o") == "oeffnen" and TAB.nimmt("bild", "f") == "art_taste"
    assert TAB.nimmt("kasten", "e") is None            # fremd: kein Modal
    assert TAB.nimmt("ruhe", "enter") is None          # nichts gewählt: nichts zu greifen
    assert TAB.nimmt("notiz", "q") is None
    for ansicht in ("ruhe", "notiz", "kasten", "bild"):
        assert TAB.nimmt(ansicht, "tab") == TAB.nimmt(ansicht, "shift+tab") == "springen"


def test_lower_case_wasd_are_the_arrows_in_every_state():
    """2026-10-31, Sasha: "wasd doesn't react" — only the capitals (pan)
    were bound. Lower case now does what the arrows do, wherever they act."""
    for ansicht in ("ruhe", "notiz", "kasten", "bild", "greifen", "verbinden", "groesse"):
        for k, pfeil in (("w", "up"), ("a", "left"), ("s", "down"), ("d", "right")):
            assert TAB.nimmt(ansicht, k) == TAB.nimmt(ansicht, pfeil), (ansicht, k)
            assert TAB.nimmt(ansicht, k.upper()) == "schieben"
    c, d = leinwand(), leinwand()
    for _ in range(3):
        druecke(c, ord("d"))
        druecke(d, curses.KEY_RIGHT)
    assert (c.cx, c.cy, c.fokus) == (d.cx, d.cy, d.fokus) and c.cx is not None


def test_shift_und_alt_pfeile_schieben_ohne_text():
    for v in ("shift+", "alt+"):
        for n in ("up", "down", "left", "right"):
            assert TAB.nimmt("ruhe", v + n) == "schieben"
    gezeigt = [t for t, _x in TAB.eintraege("ruhe")]
    assert "W/A/S/D" in gezeigt and not any(t.startswith(("shift+", "alt+")) for t in gezeigt)
    c = leinwand()
    vx = c.vx
    druecke(c, curses.KEY_SLEFT)
    assert c.vx == vx - cv.PAN_X
    vy = c.vy
    druecke(c, curses.KEY_SF)
    assert c.vy == vy + cv.PAN_Y


# ── Cursor and Tab (2026-10-31) ───────────────────────────────────────
# Sasha: arrows only "aimed at the pieces that are there instead of moving
# smoothly over the surface". A free cursor now; tab jumps between pieces.

def test_arrows_move_the_cursor_cell_by_cell_into_empty_space():
    c = leinwand()                                     # view middle (0, 0) lies in m
    c.taste("rechts")
    assert (c.cx, c.cy) == (cv.CURSOR_X, 0) and c.fokus == "m"
    while c.unter(c.cx, c.cy) is not None:
        c.taste("rechts")
    assert c.fokus is None and c.cx == 10              # just past m: empty space, no focus
    while c.fokus is None:
        c.taste("rechts")
    assert c.fokus == "r" and c.cx == 30               # step by step onto r
    c.taste("runter")
    assert c.cy == cv.CURSOR_Y


def test_cursor_on_empty_space_is_drawn_and_on_a_piece_the_frame_shows_it():
    c = leinwand()
    c.cursor_setzen(-20, -5)
    zeilen = c.bild(30, 80)
    assert any(t == "+" and r == "fokus" for x, t, r in zeilen[-5 - c.vy] if x == -20 - c.vx)
    c.cursor_setzen(2, 1)
    assert c.fokus == "m"
    assert not any("+" in t and r == "fokus" for z in c.bild(30, 80) for _x, t, r in z)


def test_arrow_goes_on_from_the_focused_piece():
    c = leinwand()
    c.fokus = "r"                                      # e.g. after tab or a click
    c.taste("links")
    mx, my = schnur.mitte(c.element("r"))
    assert (c.cx, c.cy) == (mx - cv.CURSOR_X, my)


def test_cursor_stops_at_the_growable_edge_and_comes_back_at_once():
    c = leinwand()
    for _ in range(400):
        c.taste("rechts")
    x0, y0, x1, y1 = c.flaeche()
    assert c.cx == x1 - 1 == 40 + c.vw - 1             # content edge + one view
    assert c.vx <= c.cx < c.vx + c.vw                  # the view followed
    c.taste("links")
    assert c.cx == x1 - 1 - cv.CURSOR_X
    for _ in range(400):
        c.taste("hoch")
    assert c.cy == y0 == -10 - c.vh


def test_view_follows_the_cursor_near_the_edge():
    c = leinwand([zettel("a", 0, 0), zettel("b", 200, 0)])
    c.fokus = "a"
    vx = c.vx
    for _ in range(120):
        c.taste("rechts")
        assert c.vx + 4 <= c.cx < c.vx + c.vw - 4
        if c.fokus == "b":
            break
    assert c.vx > vx + 100 and c.fokus == "b"          # walked over to b, the view along


def test_held_arrows_accelerate_but_never_fling():
    class Uhr:
        t = 100.0

        def __call__(self):
            Uhr.t += 0.02
            return Uhr.t

    c = leinwand()
    c.uhr = Uhr()
    schritte = []
    for _ in range(30):
        x = c.cx
        c.taste("rechts")
        if x is not None:
            schritte.append(c.cx - x)
    assert max(schritte) > cv.CURSOR_X                 # held: faster
    assert max(schritte) <= max(cv.PAN_X, c.vw // cv.PAN_VIEW_DIVISOR)


def test_after_panning_the_cursor_out_of_view_an_arrow_starts_in_the_middle():
    c = leinwand()
    c.cursor_setzen(-30, 0)
    for _ in range(10):
        c.taste("pan_rechts")
    assert not (c.vx <= c.cx < c.vx + c.vw)
    c.taste("runter")
    mx, my = c.mitte_des_ausschnitts()
    assert (c.cx, c.cy) == (mx, my + cv.CURSOR_Y)


def test_tab_cycles_the_pieces_in_reading_order():
    c = leinwand()
    c.taste("naechster")
    assert c.fokus == "m"                              # first: nearest the middle
    folge = []
    for _ in range(5):
        c.taste("naechster")
        folge.append(c.fokus)
    assert folge == ["r", "u", "o", "l", "m"]          # top→bottom, left→right, wraps
    c.taste("vorheriger")
    assert c.fokus == "l"
    assert c.unter(c.cx, c.cy)["id"] == "l"            # the cursor went along
    druecke(c, 9)
    assert c.fokus == "m"
    druecke(c, curses.KEY_BTAB)
    assert c.fokus == "l"


def test_tab_scrolls_the_far_piece_into_view():
    c = leinwand([zettel("a", 0, 0), zettel("b", 200, 0)])
    c.fokus = "a"
    c.taste("naechster")
    assert c.fokus == "b"
    assert c.vx <= 200 and 210 <= c.vx + c.vw


def test_plus_puts_the_new_piece_at_the_cursor():
    c = leinwand([])
    c.cursor_setzen(-20, -6)
    c.taste("neu")
    e = c.element(c.fokus)
    assert schnur.mitte(e)[0] in range(-21, -18) and c.modus == "greifen"


# ── Greifen, Verschieben, Ablegen, Abbrechen ──────────────────────────

def test_greifen_schieben_ablegen():
    c = leinwand()
    c.fokus = "m"
    assert c.taste("enter") is None and c.modus == "greifen"
    c.taste("rechts"); c.taste("rechts"); c.taste("runter")
    erg = c.taste("enter")
    assert erg.art == "geaendert" and erg.grund == "verschoben"
    m = c.element("m")
    assert (m["x"], m["y"]) == (2, 1) and c.modus == "ruhe"


def test_greifen_und_esc_setzt_zurueck():
    c = leinwand()
    c.fokus = "m"
    c.taste("enter"); c.taste("links"); c.taste("links")
    assert c.taste("esc") is None
    assert (c.element("m")["x"], c.element("m")["y"]) == (0, 0) and c.modus == "ruhe"


def test_greifen_ohne_bewegung_speichert_nichts():
    c = leinwand()
    c.fokus = "m"
    c.taste("enter")
    assert c.taste("enter") is None


def test_plus_legt_neu_an_mittig_und_gegriffen():
    c = leinwand([])
    c.taste("neu")
    assert c.modus == "greifen" and len(c.elemente) == 1
    e = c.elemente[0]
    mx, my = c.mitte_des_ausschnitts()
    assert e["art"] == "notiz" and abs(e["x"] + e["w"] // 2 - mx) <= 1
    c.taste("hoch")
    erg = c.taste("enter")
    assert erg.art == "geaendert" and erg.grund == "neu" and erg.element is e


def test_plus_und_esc_verwirft_den_neuen():
    c = leinwand([])
    c.taste("neu")
    c.taste("esc")
    assert c.elemente == [] and c.fokus is None


def test_pan_schiebt_den_ausschnitt_und_beim_greifen_den_kasten_mit():
    c = leinwand()
    vx = c.vx
    c.taste("pan_rechts")
    assert c.vx == vx + cv.PAN_X
    c.fokus = "m"
    c.taste("enter")
    c.taste("pan_runter")
    assert c.element("m")["y"] == cv.PAN_Y
    c.taste("esc")
    assert c.element("m")["y"] == 0


def test_bearbeiten_meldet_sich_bei_der_ansicht():
    c = leinwand()
    c.fokus = "m"
    erg = c.taste("bearbeiten")
    assert erg.art == "bearbeiten" and erg.element["id"] == "m"


def test_esc_in_ruhe_will_zu():
    assert leinwand().taste("esc").art == "zu"


# ── Löschen mit Rückfrage ─────────────────────────────────────────────

def test_loeschen_fragt_und_nein_laesst_es():
    c = leinwand()
    c.fokus = "m"
    c.taste("loeschen")
    assert c.modus == "frage"
    c.taste("pan_links")                          # in der Frage wirkt nichts anderes
    c.taste("nein")
    assert c.element("m") and c.modus == "ruhe"


def test_loeschen_ja_nimmt_die_schnuere_mit():
    c = leinwand(verbindungen=[{"id": "v1", "von": "m", "nach": "r"},
                               {"id": "v2", "von": "l", "nach": "m"},
                               {"id": "v3", "von": "o", "nach": "u"}])
    c.fokus = "m"
    c.taste("loeschen")
    erg = c.taste("ja")
    assert erg.art == "geaendert" and erg.grund == "geloescht"
    assert c.element("m") is None
    assert [v["id"] for v in c.verbindungen] == ["v3"]


# ── Schnüre ───────────────────────────────────────────────────────────

def test_verbinden_springt_mit_dem_ziel_und_enter_verbindet():
    c = leinwand()
    c.fokus = "m"
    c.taste("verbinden")
    assert c.modus == "verbinden" and c.ziel and c.ziel != "m"
    c.taste("rechts")
    c.taste("rechts")
    assert c.ziel == "r"
    erg = c.taste("enter")
    assert erg.art == "geaendert" and erg.grund == "verbunden"
    assert c.verbindungen[-1]["von"] == "m" and c.verbindungen[-1]["nach"] == "r"


def test_verbinden_esc_bricht_ab():
    c = leinwand()
    c.fokus = "m"
    c.taste("verbinden")
    c.taste("esc")
    assert c.modus == "ruhe" and c.verbindungen == []


def test_verbinden_auf_verbundenes_paar_fragt_nach_loesen():
    c = leinwand(verbindungen=[{"id": "v1", "von": "r", "nach": "m"}])
    c.fokus = "m"
    c.taste("verbinden")
    while c.ziel != "r":
        c.taste("rechts")
    c.taste("verbinden")
    assert c.modus == "frage" and "lösen" in c.frage["text"]
    erg = c.taste("ja")
    assert erg.grund == "geloest" and c.verbindungen == []


def test_schnur_folgt_beim_verschieben():
    """Die Schnur hängt an den Kästen, nicht an Zellen: nach dem Verschieben
    startet sie am neuen Ort."""
    c = leinwand([zettel("a", 0, 0), zettel("b", 30, 0)],
                 [{"id": "v", "von": "a", "nach": "b"}])
    vorher = schnur.weg(c.element("a"), c.element("b"))
    c.fokus = "a"
    c.taste("enter")
    for _ in range(3):
        c.taste("runter")
    c.taste("enter")
    nachher = schnur.weg(c.element("a"), c.element("b"))
    assert nachher != vorher
    assert nachher[0] == schnur.anker(c.element("a"), "right")
    assert nachher[-1] == schnur.anker(c.element("b"), "left")


def test_schnur_wird_gezeichnet_und_liegt_unter_den_kaesten():
    c = leinwand([zettel("a", 0, 0), zettel("b", 30, 6)], [{"id": "v", "von": "a", "nach": "b"}])
    c.vx, c.vy = -2, -2
    zeilen = c.bild(14, 50)
    text = {}
    for y, stuecke in enumerate(zeilen):
        for x, t, rolle in stuecke:
            for i, ch in enumerate(t):
                text[(x + i, y)] = (ch, rolle)
    schnur_zellen = [k for k, (ch, r) in text.items() if r == "schnur"]
    assert schnur_zellen
    assert any(ch in "┐┘┌└" for ch, r in text.values() if r == "schnur")
    assert any(ch == "▸" for ch, r in text.values() if r == "schnur")   # Spitze zeigt ins Ziel
    # nichts von der Schnur im Inneren eines Kastens
    for (x, y) in schnur_zellen:
        wx, wy = x + c.vx, y + c.vy
        for e in c.elemente:
            assert not (e["x"] < wx < e["x"] + e["w"] - 1 and e["y"] < wy < e["y"] + e["h"] - 1)


def test_seiten_nach_lage():
    a = {"x": 0, "y": 0, "w": 10, "h": 4}
    assert schnur.seiten(a, {"x": 40, "y": 0, "w": 10, "h": 4}) == ("right", "left")
    assert schnur.seiten(a, {"x": -40, "y": 0, "w": 10, "h": 4}) == ("left", "right")
    assert schnur.seiten(a, {"x": 0, "y": 20, "w": 10, "h": 4}) == ("bottom", "top")
    assert schnur.seiten(a, {"x": 0, "y": -20, "w": 10, "h": 4}) == ("top", "bottom")


def test_kreuzende_schnuere_ergeben_ein_kreuz():
    netz, _ = schnur.richtungen([(0, 5), (10, 5)])
    netz, _ = schnur.richtungen([(5, 0), (5, 10)], netz)
    assert schnur.zeichen(netz[(5, 5)]) == "┼"


def test_verbindungen_mit_seiten_fuer_die_datei():
    c = leinwand([zettel("a", 0, 0), zettel("b", 30, 0)], [{"id": "v", "von": "a", "nach": "b"}])
    (v,) = c.verbindungen_mit_seiten()
    assert v["von_seite"] == "right" and v["nach_seite"] == "left"


# ── Bild, Arten ───────────────────────────────────────────────────────

def test_bild_hat_die_groesse_und_zeigt_fokus():
    c = leinwand()
    c.fokus = "m"
    zeilen = c.bild(30, 80)
    assert len(zeilen) == 30
    assert all(sum(len(t) for _x, t, _r in z) <= 80 for z in zeilen)
    rollen = {r for z in zeilen for _x, _t, r in z}
    assert {"fokus", "amber", "raster"} <= rollen     # Zettel-Rahmen in Haftnotiz-Farbe


def test_zettel_erste_zeile_ist_titel_und_blaettert():
    n = Notiz()
    el = zettel("z", 0, 0, text="# Einkauf\n" + "\n".join("zeile %d" % i for i in range(10)))
    innen = n.zeichne(el, 20, 4)
    assert innen[0] == [("Einkauf", "notiz_titel")]
    assert innen[1] == "zeile 0" and innen[-1].endswith("…")
    c = leinwand([el])
    c.fokus = "z"
    c.taste("blaettern_runter")
    assert n.zeichne(el, 20, 4)[1] == "zeile 1"


def test_unbekannte_art_verschwindet_nicht():
    c = leinwand([{"id": "x", "art": "kachel:irgendwas", "x": 0, "y": 0, "w": 10, "h": 3}])
    c.vx, c.vy = -1, -1
    zeilen = c.bild(10, 30)
    assert any("?" in t for z in zeilen for _x, t, _r in z)


def test_umbrechen():
    assert umbrechen("eins zwei drei", 9) == ["eins zwei", "drei"]
    assert umbrechen("abcdefghij", 4) == ["abcd", "efgh", "ij"]


# ── Textfeld / Modal ──────────────────────────────────────────────────

def tippe(feld, text):
    for b in text.encode("utf-8"):
        feld.taste(b)


def test_textfeld_umlaute_neue_zeile_und_cursor():
    f = Textfeld("")
    tippe(f, "Grüße")
    f.taste(10)
    tippe(f, "zwei")
    assert f.text == "Grüße\nzwei"
    f.taste(curses.KEY_UP)
    assert f.cursor(40) == (0, 4)
    f.taste(curses.KEY_BACKSPACE)
    assert f.text == "Grüe\nzwei"


def test_textfeld_speichern_und_abbrechen():
    f = Textfeld("x")
    assert f.taste(19) == "speichern"
    assert f.taste(27) == "abbrechen"


def test_textfeld_anzeige_scrollt_mit_dem_cursor():
    f = Textfeld("\n".join(str(i) for i in range(20)))
    sicht, (r, s) = f.anzeige(10, 5)
    assert sicht[-1] == "19" and r == 4


def test_zettel_modal_aendert_den_text():
    m = Notiz().modal(zettel("z", 0, 0, text="alt"))
    assert isinstance(m, TextModal)
    tippe(m, "!")
    assert m.taste(19) == "speichern"
    assert m.aenderungen() == {"text": "alt!"}


def test_o_meldet_die_aktion_der_art_enter_greift_immer():
    """2026-10-10: Enter greift JEDES Element (auch eine Kachel), `o` öffnet,
    wenn die Art `oeffnen` hat; ein Zettel ohne `oeffnen` tut bei `o` nichts."""
    class Kachel:
        name = "kachel"

        def zeichne(self, element, w, h):
            return []

        def modal(self, element):
            return None

        def oeffnen(self, element):
            return ("oeffnen", element["kachel"]["ref"])
    c = leinwand([zettel("z", 0, 0),
                  {"id": "k", "art": "kachel", "x": 30, "y": 0, "w": 10, "h": 4,
                   "kachel": {"v": 1, "app": "fokus", "art": "liste", "ref": {"id": "l1"}}}])
    c.arten.registrieren(Kachel())
    c.fokus = "k"
    erg = c.aktion_oeffnen("o")
    assert erg.art == "aktion" and erg.grund == ("oeffnen", {"id": "l1"}) and c.modus == "ruhe"
    assert c.taste("enter") is None and c.modus == "greifen"
    c.taste("esc")
    c.fokus = "z"
    assert c.taste("oeffnen") is None and c.modus == "ruhe"


def test_eigene_taste_der_art_meldet_geaendert():
    class Schalter:
        name = "schalter"

        def zeichne(self, element, w, h):
            return []

        def modal(self, element):
            return None

        def taste(self, element, zeichen):
            if zeichen != "f":
                return False
            element["an"] = not element.get("an")
            return True
    c = leinwand([{"id": "s", "art": "schalter", "x": 0, "y": 0, "w": 10, "h": 4}])
    c.arten.registrieren(Schalter())
    c.fokus = "s"
    erg = c.aktion_art_taste("f")
    assert erg.art == "geaendert" and erg.grund == "art" and c.elemente[0]["an"] is True
    assert c.taste("zeichen:x") is None


def test_plus_ohne_fabrik_fragt_nach_der_art_und_legt_dann_ab():
    c = leinwand(neu=False)
    erg = c.taste("neu")
    assert erg.art == "neu_waehlen" and c.modus == "ruhe"
    notiz = c.arten.holen("notiz")
    assert [a.name for a in c.arten.anlegbar()] == ["notiz", "bild"]
    c.neu_ablegen(notiz.neu("n1", 0, 0))
    assert c.modus == "greifen" and c.fokus == "n1"
    assert c.taste("enter").grund == "neu"


def test_kachel_ohne_registrierte_art_zeigt_den_rueckfall():
    arten = cv.Arten()
    for art in (Notiz(), Fremd()):                 # eine TUI ohne Kachel-Art
        arten.registrieren(art)
    c = cv.Canvas(arten, [{"id": "k", "art": "kachel", "x": 0, "y": 0, "w": 24, "h": 4,
                           "typ": "kachel · fokus/liste", "titel": "Einkauf: Milch"}])
    c.vx, c.vy = -1, -1
    text = "".join(t for z in c.bild(8, 40) for _x, t, _r in z)
    assert "kachel · fokus/liste" in text and "Einkauf" in text


def test_kachel_art_zeigt_puffer_rueckfall_und_zustaende():
    """Die Art „kachel" (2026-10-10) zeichnet nur, was die Ansicht unter
    _inhalt abgelegt hat; o meldet den Verweis; blättern bis oben_max."""
    k = Kachel()
    el = {"id": "k", "art": "kachel", "w": 24, "h": 5, "titel": "Kalender 12.10.",
          "kachel": {"v": 1, "app": "kalender", "art": "ausschnitt", "ref": {"tage": 7}}}
    assert k.zeichne(el, 22, 3)[0] == [("lädt …", "leise")]
    assert ("Kalender 12.10.", "leise") in k.zeichne(el, 22, 3)[1]
    assert k.oeffnen(el) == ("kachel_oeffnen", el)      # die Ansicht liest den Verweis
    el["_inhalt"] = {"zustand": "ok", "zeilen": [[("Mo 12.10.", "kal")], [("09:00 ", "faint"), ("Arzt", "ink")]],
                     "oben_max": 2}
    assert k.zeichne(el, 22, 3) == [[("Mo 12.10.", "kal")], [("09:00 ", "faint"), ("Arzt", "ink")]]
    k.blaettern(el, 1); k.blaettern(el, 1); k.blaettern(el, 1)
    assert el["_oben"] == 2                         # nicht weiter als die App sagt
    k.blaettern(el, -5)
    assert el["_oben"] == 0
    el["_inhalt"] = dict(el["_inhalt"], zustand="aus")
    assert all(r == "leise" for z in k.zeichne(el, 22, 3) for _t, r in z)
    el["_inhalt"] = {"zustand": "zu_klein", "zu_klein": {"w": 50, "h": 4}}
    assert "mind. 50×4" in "".join(t for z in k.zeichne(el, 22, 3) for t, _r in z)
    el["_inhalt"] = {"zustand": "weg"}
    assert k.zeichne(el, 22, 3)[0] == [("nicht mehr da", "warn")]
    c = leinwand([dict(el, x=0, y=0)])
    c.fokus = "k"
    assert c.taste("oeffnen").grund[0] == "kachel_oeffnen"
    assert c.taste("enter") is None and c.modus == "greifen"     # enter greift auch Kacheln


# ── Weich schieben, W A S D, Alt+Pfeile (2026-10-10) ──────────────────

def test_wasd_grossbuchstaben_schieben():
    for ch, r in (("W", "hoch"), ("A", "links"), ("S", "runter"), ("D", "rechts")):
        assert TAB.nimmt("notiz", ch) == "schieben"
        c = leinwand()
        c.fokus = "m"
        vx, vy = c.vx, c.vy
        druecke(c, ord(ch))
        dx, dy = {"hoch": (0, -cv.PAN_Y), "links": (-cv.PAN_X, 0),
                  "runter": (0, cv.PAN_Y), "rechts": (cv.PAN_X, 0)}[r]
        assert (c.vx, c.vy) == (vx + dx, vy + dy)
    assert TAB.nimmt("notiz", "d") == "waehlen"        # lower case: the arrows (2026-10-31)


def test_wasd_wirkt_in_jedem_zustand_ausser_der_frage():
    c = leinwand()
    c.taste("rechts"); c.taste("enter")                        # greifen
    vx = c.vx
    druecke(c, ord("D"))
    assert c.vx == vx + cv.PAN_X and c.modus == "greifen"
    c.taste("enter"); c.taste("loeschen")                      # Frage
    vx = c.vx
    druecke(c, ord("D"))
    assert c.vx == vx and c.modus == "frage"


def test_gleit_schritt_naehert_sich_und_rastet_ein():
    pos, wege = 0.0, []
    for _ in range(20):
        pos = cv.gleit_schritt(pos, 10)
        wege.append(pos)
    assert 0 < wege[0] < wege[1] < 10                           # Zwischenlagen
    assert wege[-1] == 10.0 and isinstance(wege[-1], float)
    assert cv.gleit_schritt(9.6, 10) == 10.0                     # unter ½ Zelle: einrasten
    assert cv.gleit_schritt(-5.0, -20) < -5.0                    # auch rückwärts


def test_ohne_weich_zeichnet_bild_sofort_das_ziel():
    c = leinwand()
    c.taste("pan_rechts")
    assert not c.gleiten() and not c.bewegt_sich()
    assert c.anzeige_lage() == (c.vx, c.vy)


def test_weich_gleitet_hoechstens_ein_paar_bilder_und_steht_dann():
    c = leinwand()
    c.weich = True
    c.gleiten()                                                # Start: steht
    start = c.vx
    c.taste("pan_rechts")
    assert c.bewegt_sich()
    lagen = []
    for _ in range(cv.GLEIT_BILDER + 2):
        lagen.append(c.anzeige_lage()[0])
        if not c.gleiten():
            break
    assert not c.bewegt_sich() and c.anzeige_lage() == (c.vx, c.vy)
    assert start in lagen and any(start < x < c.vx for x in lagen)   # dazwischen gezeichnet
    assert len(lagen) <= cv.GLEIT_BILDER


def test_weiter_sprung_steht_spaetestens_nach_gleit_bildern():
    c = leinwand()
    c.weich = True
    c.gleiten()
    c.vx += 300                                                # z. B. Fokus-Sprung weit weg
    n = 0
    while c.gleiten():
        n += 1
        assert n < cv.GLEIT_BILDER
    assert c.anzeige_lage()[0] == c.vx


def test_folgen_beim_fokus_sprung_gleitet_auch():
    c = leinwand([zettel("a", 0, 0), zettel("b", 200, 0)])
    c.weich = True
    c.gleiten()
    c.fokus = "a"
    c.taste("naechster")                               # tab: jump to the far piece
    assert c.fokus == "b" and c.bewegt_sich()
    c.gleiten()
    assert c.anzeige_lage()[0] < c.vx


def test_bild_zeichnet_an_der_anzeige_lage_greifen_bleibt_zellgenau():
    c = leinwand([zettel("a", 0, 0)])
    c.weich = True
    c.gleiten()
    c.fokus = "a"
    c.taste("enter")
    c.taste("pan_rechts")
    e = c.element("a")
    assert e["x"] == cv.PAN_X and isinstance(e["x"], int)       # die Welt bleibt ganzzahlig
    c.gleiten()
    ox, oy = c.anzeige_lage()
    assert ox < c.vx                                # die Ansicht gleitet noch
    zeilen = c.bild(30, 80)
    # in der Hand: liegt auf dem Schirm, wo es nach dem Gleiten liegt
    spalte = e["x"] - c.vx
    assert any(s == spalte and t.startswith("╔") for s, t, _r in zeilen[e["y"] - c.vy])


def test_gegriffenes_gleitet_mit_der_ansicht_statt_vorzuspringen():
    """2026-10-10: beim Schieben mit etwas in der Hand sprang der Kasten
    vor und rutschte zurück. Jetzt steht er auf dem Schirm still, während
    die Welt (Raster, andere Kästen) unter ihm gleitet."""
    c = leinwand([zettel("a", 0, 0), zettel("b", 30, 0)])
    c.weich = True
    c.vx = c.vy = 0
    c.gleiten()
    c.fokus = "a"
    c.taste("enter")

    def spalte_von(zeilen, zeichen):
        return next(s for z in zeilen for s, t, r in z if t.startswith(zeichen))
    vorher = spalte_von(c.bild(30, 80), "╔")
    c.taste("pan_rechts")
    spalten_a, spalten_b = [], []
    for _ in range(cv.GLEIT_BILDER + 1):
        c.gleiten()
        zeilen = c.bild(30, 80)
        spalten_a.append(spalte_von(zeilen, "╔"))
        spalten_b.append(spalte_von(zeilen, "┌"))
    assert set(spalten_a) == {vorher}                       # gegriffen: steht still
    assert spalten_b == sorted(spalten_b, reverse=True) and len(set(spalten_b)) > 2  # Welt gleitet
    assert spalten_b[-1] == 30 - cv.PAN_X                    # und kommt an


class Uhr:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_gedrueckt_halten_beschleunigt_bis_vierfach_und_pause_setzt_zurueck():
    # A wide board and a big view: neither pan limit (2026-10-31) is in reach.
    c = leinwand(kreuz() + [zettel("fern", 2000, 0), zettel("tief", 0, 1000)])
    c.vw, c.vh = 200, 80
    c.uhr = uhr = Uhr()
    schritte = []
    for _ in range(8):
        vx = c.vx
        c.taste("pan_rechts")
        schritte.append(c.vx - vx)
        uhr.t += 0.03                                          # Tastenwiederholung
    assert schritte[0] == cv.PAN_X
    assert schritte == sorted(schritte) and schritte[1] > schritte[0]
    assert schritte[-1] == cv.PAN_X * 4                        # Deckel
    uhr.t += 0.5                                               # Pause
    vx = c.vx
    c.taste("pan_rechts")
    assert c.vx - vx == cv.PAN_X
    uhr.t += 0.03
    vy = c.vy
    c.taste("pan_runter")                                      # andere Richtung: Grundschritt
    assert c.vy - vy == cv.PAN_Y


def test_pan_step_holds_only_the_direction_of_travel():
    assert cv.pan_step(0, 6, -50, 50) == 6
    assert cv.pan_step(48, 6, -50, 50) == 50                   # stops at the bound
    assert cv.pan_step(50, 6, -50, 50) == 50
    assert cv.pan_step(50, -6, -50, 50) == 44                  # back: moves at once
    assert cv.pan_step(80, 6, -50, 50) == 80                   # beyond already: stays,
    assert cv.pan_step(80, -6, -50, 50) == 74                  # no jump back


def test_held_pan_is_bounded_never_lost_and_recovers():
    """2026-10-31, Schematix: held W/A/S/D carried the view 480 columns a
    second past the content into empty space ("flies too fast, then
    stuck"). Now: a step is at most a quarter view, the view stays on the
    growable surface (content + one view on every side), the way back moves
    at once."""
    c = leinwand()                                              # content x -30..40, y -10..14
    c.uhr = uhr = Uhr()
    for richtung, achse, voll in (("rechts", "vx", c.vw), ("runter", "vy", c.vh),
                                  ("links", "vx", c.vw), ("hoch", "vy", c.vh)):
        for _ in range(200):                                    # a long burst
            vor = getattr(c, achse)
            c.taste("pan_" + richtung)
            assert abs(getattr(c, achse) - vor) <= max(cv.PAN_X, voll // cv.PAN_VIEW_DIVISOR)
            uhr.t += 0.02
        lo_x, hi_x, lo_y, hi_y = c.pan_bounds()
        assert lo_x <= c.vx <= hi_x and lo_y <= c.vy <= hi_y   # never lost in the void
        assert (c.vx, c.vy) != (-40, -15)                      # but it got there: a view past
        if richtung == "rechts":
            assert c.vx == hi_x == 40                          # right edge of the content
        if richtung == "hoch":
            assert c.vy == lo_y == -10 - c.vh
        zurueck = {"rechts": "links", "links": "rechts", "runter": "hoch", "hoch": "runter"}[richtung]
        vor = getattr(c, achse)
        uhr.t += 0.02
        c.taste("pan_" + zurueck)                               # recovers at once, base step
        assert abs(getattr(c, achse) - vor) == (cv.PAN_X if achse == "vx" else cv.PAN_Y)


def test_the_growable_surface_grows_with_what_is_built():
    """Sasha: "you can extend the surface endlessly if you want" — put a
    piece at the edge, and the area reaches a view further."""
    c = leinwand()
    for _ in range(100):
        c.taste("pan_rechts")
    assert c.vx == 40
    c.cursor_setzen(c.vx + c.vw // 2, 0)
    c.taste("neu")                                     # a new piece out there …
    c.taste("enter")                                   # … dropped
    rechts = max(e["x"] + e["w"] for e in c.elemente)
    for _ in range(100):
        c.taste("pan_rechts")
    assert c.vx == rechts > 40


def test_pan_limits_free_while_carrying_and_on_an_empty_canvas():
    c = leinwand([])
    for _ in range(100):
        c.taste("pan_rechts")
    assert c.vx == -40 + 100 * cv.PAN_X                         # nothing to lose
    c = leinwand([zettel("a", 0, 0)])
    c.fokus = "a"
    c.taste("enter")
    for _ in range(100):
        c.taste("pan_rechts")
    assert c.element("a")["x"] == 100 * cv.PAN_X                # the hand carries it anywhere


def test_ohne_uhr_immer_der_grundschritt():
    c = leinwand()
    for _ in range(5):
        vx = c.vx
        c.taste("pan_links")
        assert c.vx - vx == -cv.PAN_X


# ── Größe ändern (r, 2026-10-10) ──────────────────────────────────────

def test_r_ist_groesse_und_der_gastgeber_darf_vorher_nein_sagen():
    assert TAB.nimmt("notiz", "r") == "groesse"
    c = leinwand()
    c.fokus = "m"
    gefragt = []
    c.vor_groesse = lambda e: gefragt.append(e["id"]) or False
    druecke(c, ord("r"))
    assert gefragt == ["m"] and c.modus == "ruhe"
    c.vor_groesse = lambda e: True
    druecke(c, ord("r"))
    assert c.modus == "groesse"


def test_groesse_wachsen_schrumpfen_enter_behaelt():
    c = leinwand([zettel("m", 0, 0, w=20, h=6)])
    c.fokus = "m"
    assert c.taste("groesse") is None and c.modus == "groesse"
    for ev in ("rechts", "rechts", "runter", "links", "rechts"):
        assert c.taste(ev) is None
    m = c.element("m")
    assert (m["x"], m["y"], m["w"], m["h"]) == (0, 0, 22, 7)   # oben links bleibt
    erg = c.taste("enter")
    assert erg.art == "geaendert" and erg.grund == "groesse" and c.modus == "ruhe"
    assert c.groesse is None


def test_groesse_esc_setzt_zurueck_und_ohne_aenderung_kein_speichern():
    c = leinwand([zettel("m", 0, 0, w=20, h=6)])
    c.fokus = "m"
    c.taste("groesse"); c.taste("rechts"); c.taste("runter")
    assert c.taste("esc") is None and c.modus == "ruhe"
    assert (c.element("m")["w"], c.element("m")["h"]) == (20, 6)
    c.taste("groesse"); c.taste("rechts"); c.taste("links")
    assert c.taste("enter") is None                   # gleich groß: nichts speichern


def test_groesse_haelt_am_minimum_und_maximum_an():
    c = leinwand([zettel("m", 0, 0, w=11, h=5)])
    c.fokus = "m"
    c.taste("groesse")
    c.taste("links"); c.taste("hoch")
    assert (c.element("m")["w"], c.element("m")["h"]) == (10, 4)       # min des Zettels
    c.taste("links")
    assert c.element("m")["w"] == 10 and "kleiner geht nicht" in c.groesse["anschlag"]
    assert "10×4" in c.groesse["anschlag"]
    c.taste("rechts")
    assert c.groesse["anschlag"] == ""                                  # wieder frei
    c.taste("esc")
    # Kachel: Grenzen aus dem Katalog (von der Ansicht als _grenzen abgelegt)
    k = {"id": "k", "art": "kachel", "x": 0, "y": 0, "w": 9, "h": 5,
         "_grenzen": {"min": (8, 4), "max": (10, 5)}}
    c = leinwand([k])
    c.fokus = "k"
    c.taste("groesse")
    c.taste("rechts"); c.taste("rechts"); c.taste("runter")
    assert (k["w"], k["h"]) == (10, 5) and "größer geht nicht" in c.groesse["anschlag"]
    c.taste("links"); c.taste("links"); c.taste("links"); c.taste("hoch"); c.taste("hoch")
    assert (k["w"], k["h"]) == (8, 4)


def test_groesse_vorgabe_ohne_eigene_grenzen():
    c = leinwand([{"id": "f", "art": "fremd", "x": 0, "y": 0, "w": 4, "h": 3}])
    c.fokus = "f"
    c.taste("groesse"); c.taste("links"); c.taste("links")
    assert c.element("f")["w"] == cv.GROESSE_MIN[0]


def test_groesse_ausschnitt_folgt_der_wachsenden_ecke_und_pan_geht():
    c = leinwand([zettel("m", 0, 0, w=20, h=6)])
    c.fokus = "m"
    c.taste("groesse")
    vx = c.vx
    for _ in range(80):
        c.taste("rechts")
    m = c.element("m")
    assert c.vx > vx and m["x"] + m["w"] <= c.vx + c.vw          # Ecke sichtbar
    vy = c.vy
    c.taste("pan_runter")                                          # S schiebt weiter
    assert c.vy > vy and c.modus == "groesse" and m["y"] == 0


def test_groesse_rahmen_ist_zu_sehen():
    c = leinwand([zettel("m", 0, 0, w=20, h=6)])
    c.fokus = "m"
    c.taste("groesse")
    rollen = {r for z in c.bild(30, 80) for _x, _t, r in z}
    text = "".join(t for z in c.bild(30, 80) for _x, t, _r in z)
    assert "groesse" in rollen and "◢" in text


def test_schnur_folgt_der_neuen_groesse():
    """Schnüre werden aus den Lagen gelegt — nach dem Größer-Machen liegen
    sie anders, ohne dass jemand sie anfasst."""
    a, b = zettel("a", 0, 0, w=10, h=4), zettel("b", 30, 20, w=10, h=4)
    c = leinwand([a, b], [{"id": "v", "von": "a", "nach": "b"}])
    vorher = schnur.weg(a, b)
    seiten_vorher = c.verbindungen_mit_seiten()[0]["von_seite"]
    c.fokus = "a"
    c.taste("groesse")
    for _ in range(25):
        c.taste("runter")
    assert c.taste("enter").grund == "groesse"
    assert schnur.weg(a, b) != vorher
    assert c.verbindungen_mit_seiten()[0]["von_seite"] != seiten_vorher
    zellen = {(x, y) for y, z in enumerate(c.bild(c.vh, c.vw)) for x0, t, r in z
              if r == "schnur" for x in range(x0, x0 + len(t))}
    assert zellen                                                  # gezeichnet
