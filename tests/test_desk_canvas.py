"""
Der Canvas-Baustein (tui/bausteine/canvas.py, schnur.py, textfeld.py,
canvas_arten.py) ohne Terminal: Zustände, Fokus-Sprung, Greifen, Schnüre,
Shift+Pfeil-Erkennung, Zettel-Editor. Desk View, 2026-10-09
(memory/system/desk_view.md).
"""
import curses

from tui.bausteine import canvas as cv
from tui.bausteine import schnur
from tui.bausteine.canvas_arten import Fremd, Kachel, Notiz, TextModal, standard_arten, umbrechen
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
    assert cv.taste_deuten(ord("o"), b"o") == "oeffnen"
    assert cv.taste_deuten(ord("q"), b"q") == "zeichen:q"
    assert cv.taste_deuten(-1, b"") is None


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
    erg = c.taste(cv.taste_deuten(ord("o"), b"o"))
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
    assert cv.taste_deuten(ord("f"), b"f") == "zeichen:f"
    erg = c.taste("zeichen:f")
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

def test_wasd_grossbuchstaben_schieben_kleinbuchstaben_nicht():
    for ch, r in (("W", "hoch"), ("A", "links"), ("S", "runter"), ("D", "rechts")):
        assert cv.taste_deuten(ord(ch), b"") == "pan_" + r
    assert cv.taste_deuten(ord("d"), b"") == "loeschen"    # klein bleibt wie es ist
    assert cv.taste_deuten(ord("s"), b"") == "zeichen:s"


def test_alt_pfeil_ueber_den_namen_und_als_folge():
    for name, r in ((b"kLFT3", "links"), (b"kRIT3", "rechts"),
                    (b"kUP3", "hoch"), (b"kDN3", "runter")):
        assert cv.taste_deuten(571, name) == "pan_" + r
    assert cv.esc_folge([curses.KEY_UP]) == "pan_hoch"          # ESC + Pfeil (Meta)
    assert cv.esc_folge([ord(c) for c in "[1;3C"]) == "pan_rechts"
    assert cv.esc_folge([27] + [ord(c) for c in "[D"]) == "pan_links"
    assert cv.esc_folge([27] + [ord(c) for c in "OB"]) == "pan_runter"
    assert cv.esc_folge([ord("x")]) is None


def test_wasd_wirkt_in_jedem_zustand_ausser_der_frage():
    c = leinwand()
    c.taste("rechts"); c.taste("enter")                        # greifen
    vx = c.vx
    c.taste(cv.taste_deuten(ord("D"), b""))
    assert c.vx == vx + cv.PAN_X and c.modus == "greifen"
    c.taste("enter"); c.taste("loeschen")                      # Frage
    vx = c.vx
    c.taste(cv.taste_deuten(ord("D"), b""))
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
    c.taste("rechts")
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
    c = leinwand()
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


def test_ohne_uhr_immer_der_grundschritt():
    c = leinwand()
    for _ in range(5):
        vx = c.vx
        c.taste("pan_links")
        assert c.vx - vx == -cv.PAN_X
