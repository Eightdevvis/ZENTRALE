"""
Der Canvas-Baustein (tui/bausteine/canvas.py, schnur.py, textfeld.py,
canvas_arten.py) ohne Terminal: Zustände, Fokus-Sprung, Greifen, Schnüre,
Shift+Pfeil-Erkennung, Zettel-Editor. Desk View, 2026-10-09
(memory/system/desk_view.md).
"""
import curses

from tui.bausteine import canvas as cv
from tui.bausteine import schnur
from tui.bausteine.canvas_arten import Notiz, TextModal, standard_arten, umbrechen
from tui.bausteine.textfeld import Textfeld


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


# ── Tasten deuten ─────────────────────────────────────────────────────

def test_shift_pfeil_ueber_den_namen_egal_welche_nummer():
    """tmux/xterm melden Shift+Pfeil als erweiterte Taste mit wechselnder
    Nummer — der Name zählt."""
    for name, r in ((b"kLFT2", "links"), (b"kRIT2", "rechts"),
                    (b"kUP2", "hoch"), (b"kDN2", "runter"),
                    (b"KEY_SLEFT", "links"), (b"KEY_SR", "hoch")):
        assert cv.shift_pfeil(577, name) == r
        assert cv.taste_deuten(577, name) == "pan_" + r


def test_shift_pfeil_rueckfall_ohne_namen():
    assert cv.taste_deuten(curses.KEY_SLEFT, b"") == "pan_links"
    assert cv.taste_deuten(curses.KEY_SF, b"") == "pan_runter"
    assert cv.shift_pfeil(curses.KEY_LEFT, b"KEY_LEFT") is None


def test_einfache_tasten():
    assert cv.taste_deuten(curses.KEY_UP, b"KEY_UP") == "hoch"
    assert cv.taste_deuten(10, b"^J") == "enter"
    assert cv.taste_deuten(ord("+"), b"+") == "neu"
    assert cv.taste_deuten(ord("e"), b"e") == "bearbeiten"
    assert cv.taste_deuten(ord("v"), b"v") == "verbinden"
    assert cv.taste_deuten(ord("d"), b"d") == "loeschen"
    assert cv.taste_deuten(ord("q"), b"q") is None


def test_esc_folgen():
    assert cv.esc_folge([]) == "esc"
    assert cv.esc_folge([ord(c) for c in "[1;2D"]) == "pan_links"
    assert cv.esc_folge([ord("x")]) is None          # Alt+x: nichts tun


# ── Fokus ─────────────────────────────────────────────────────────────

def test_erster_pfeil_waehlt_den_kasten_naechst_der_mitte():
    c = leinwand()
    c.taste("rechts")
    assert c.fokus == "m"


def test_fokus_springt_raeumlich():
    c = leinwand()
    c.fokus = "m"
    for richtung, ziel in (("rechts", "r"), ("links", "m"), ("links", "l"),
                           ("rechts", "m"), ("hoch", "o"), ("runter", "m"), ("runter", "u")):
        c.taste(richtung)
        assert c.fokus == ziel, (richtung, c.fokus)


def test_fokus_springt_nicht_ins_leere():
    c = leinwand()
    c.fokus = "r"
    c.taste("rechts")
    assert c.fokus == "r"


def test_ausschnitt_folgt_dem_fokus():
    c = leinwand([zettel("a", 0, 0), zettel("b", 200, 0)])
    c.fokus = "a"
    c.taste("rechts")
    assert c.fokus == "b"
    assert c.vx <= 200 and 210 <= c.vx + c.vw


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
