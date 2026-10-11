"""Farbwähler, Stylebox und core/stil.py (2026-10-10,
memory/system/bausteine_farbe_stil.md): Geometrie des Kreises, Cursor,
Zoom, Helligkeit, Hex hin und zurück, 256 Farben, Paar-Budget; die
Stylebox zeigt nur, was angeboten ist, ändert jede Art richtig, öffnet für
Farben den Farbwähler, lässt das gesperrte Icon zu, gibt gültiges CSS."""
import curses

import pytest

import stil
from tui import pixel
from tui.bausteine import farbwaehler as fw
from tui.bausteine.stylebox import Stylebox, RAHMEN_ZEICHEN

ENTER, ESC = 10, 27


def tippen(modal, text):
    for c in text:
        erg = modal.taste(ord(c))
    return erg


# ── core/stil.py ────────────────────────────────────────────────────────────
def test_hex_lesen_normalisiert_und_lehnt_ab():
    assert stil.hex_lesen("#FF8800") == "#ff8800"
    assert stil.hex_lesen("f80") == "#ff8800"
    assert stil.hex_lesen(" #abc ") == "#aabbcc"
    for schlecht in ("", None, "#12345", "#ggg000", "rot", "#1234567"):
        assert stil.hex_lesen(schlecht) is None
    assert stil.rgb_zu_hex(stil.hex_zu_rgb("#0a7fff")) == "#0a7fff"
    with pytest.raises(ValueError):
        stil.hex_zu_rgb("nix")


def test_schema_ist_json_schema_der_angebotenen_namen():
    s = stil.schema(["color", "border-style"])
    assert list(s["properties"]) == ["color", "border-style"]
    assert s["additionalProperties"] is False
    assert s["properties"]["color"]["pattern"] == stil.HEX_MUSTER
    assert [w["const"] for w in s["properties"]["border-style"]["oneOf"]] == \
        ["solid", "dashed", "dotted", "double", "none"]
    assert stil.EIGENSCHAFTEN["background-image"]["readOnly"] is True
    with pytest.raises(ValueError):
        stil.schema(["colour"])


def test_schema_taugt_gegen_das_meta_schema():
    jsonschema = pytest.importorskip("jsonschema")
    s = stil.schema()
    jsonschema.Draft202012Validator.check_schema(s)
    jsonschema.validate({"color": "#ffffff", "--zentrale-muster": "karo"}, s)


def test_pruefen_saeubert_und_lehnt_ab():
    assert stil.pruefen({"color": "#FFF", "border-style": "Dashed"}) == \
        {"color": "#ffffff", "border-style": "dashed"}
    with pytest.raises(ValueError):
        stil.pruefen({"color": "red"})
    with pytest.raises(ValueError):
        stil.pruefen({"border-style": "groove"})
    with pytest.raises(ValueError):
        stil.pruefen({"color": "#ffffff"}, namen=["border-style"])
    assert stil.unterschied({"color": "#ffffff"}, {"color": "#ffffff", "border-style": "none"}) == \
        {"border-style": "none"}
    assert stil.unterschied({"color": "#ffffff"}, {}) == {"color": None}   # entfernt


def test_none_heisst_entfernen_und_anwenden_laesst_es_weg():
    with pytest.raises(ValueError):
        stil.pruefen({"color": None})                        # ein Stil hat keine Lücken
    assert stil.pruefen({"color": None, "border-style": "Double"}, entfernen=True) == \
        {"color": None, "border-style": "double"}
    with pytest.raises(ValueError):
        stil.pruefen({"font-size": None}, ["color"], entfernen=True)
    alt = {"color": "#ffffff", "border-style": "dashed"}
    neu = stil.anwenden(alt, {"color": None, "background-color": "#202030", "border-color": None})
    assert neu == {"border-style": "dashed", "background-color": "#202030"}
    assert alt == {"color": "#ffffff", "border-style": "dashed"}   # alt bleibt
    for a, b in ((alt, neu), (neu, alt), ({}, alt), (alt, {})):
        assert stil.anwenden(a, stil.unterschied(a, b)) == b


# ── Farbwähler: Geometrie ───────────────────────────────────────────────────
@pytest.mark.parametrize("u, v, farbton, satt", [
    (1, 0, 0, 1), (0, 1, 90, 1), (-1, 0, 180, 1), (0, -1, 270, 1),
    (0.5, 0, 0, 0.5), (0, 0, 0, 0), (2, 0, 0, 1)])
def test_winkel_ist_farbton_abstand_ist_saettigung(u, v, farbton, satt):
    f, s = fw.punkt_zu_farbton(u, v)
    assert f == pytest.approx(farbton) and s == pytest.approx(satt)


def test_rand_rechts_ist_rot_mitte_ist_weiss():
    assert fw.hsv_hex(*fw.punkt_zu_farbton(1, 0), 1) == "#ff0000"
    assert fw.hsv_hex(*fw.punkt_zu_farbton(0, 1), 1) == "#80ff00"
    assert fw.hsv_hex(*fw.punkt_zu_farbton(0, 0), 1) == "#ffffff"
    assert fw.hsv_hex(*fw.punkt_zu_farbton(1, 0), 0) == "#000000"


def test_kreis_ist_rund_und_aussen_leer():
    zellen = fw.rad_zellen(30, 15, (0.0, 0.0), 1, 1.0, (12, 4), (0, 0, 0))
    assert len(zellen) == 15 and len(zellen[0]) == 30
    assert zellen[0][0] == (" ", (0, 0, 0), (0, 0, 0))       # Ecke außerhalb
    mitte = zellen[7][15]
    assert mitte[0] == "█" and mitte[1] == (255, 255, 255)
    rechts = zellen[7][29]
    assert rechts[1][0] == 255 and rechts[1][2] < 60           # rechts rot
    assert any(ch not in " █" for ch, _f, _b in zellen[0])    # Rand aus Sextanten
    halb = fw.rad_zellen(30, 15, (0.0, 0.0), 1, 1.0, (12, 4), (0, 0, 0), "half")
    assert {ch for z in halb for ch, _f, _b in z} <= {" ", "█", "▀", "▄"}


# ── Cursor, Zoom, Helligkeit ────────────────────────────────────────────────
def test_pfeile_schieben_und_bleiben_im_kreis():
    f = fw.Farbwaehler()
    f.taste(curses.KEY_RIGHT)
    assert (f.u, f.v) == (pytest.approx(fw.SCHRITT), 0)
    f.taste(curses.KEY_UP)
    assert f.v == pytest.approx(fw.SCHRITT)
    for _ in range(40):
        f.taste(curses.KEY_RIGHT)
    assert f.u ** 2 + f.v ** 2 == pytest.approx(1)
    assert f.taste(curses.KEY_LEFT) is None


def test_zoom_stufen_und_schritt_schrumpft():
    f = fw.Farbwaehler()
    schritte = []
    for _ in range(7):
        schritte.append((f.zoom, f.schritt))
        f.taste(ord("+"))
    assert [z for z, _s in schritte] == [1, 2, 4, 8, 16, 16, 16]
    assert schritte[4][1] == pytest.approx(fw.SCHRITT / 16)
    f.taste(curses.KEY_RIGHT)
    assert f.u == pytest.approx(fw.SCHRITT / 16)
    for _ in range(9):
        f.taste(ord("-"))
    assert f.zoom == 1
    f.taste(ord("="))
    assert f.zoom == 2


def test_zoom_zeigt_den_ausschnitt_um_den_cursor_feiner():
    f = fw.Farbwaehler("#ff8040")
    assert f.mitte() == (0.0, 0.0)
    f.taste(ord("+"))
    f.taste(ord("+"))
    assert f.mitte() == pytest.approx((f.u, f.v), abs=1e-5)
    bg = (0, 0, 0)
    grob = fw.rad_zellen(30, 15, (0.0, 0.0), 1, 1.0, (12, 4), bg)
    fein = fw.rad_zellen(30, 15, f.mitte(), 4, 1.0, (12, 4), bg)

    def farben(zellen):
        return {fg for z in zellen for ch, fg, _b in z if ch != " "}
    # Im Ausschnitt um den Cursor liegen viele Stufen, die das ganze Rad nur
    # als eine oder zwei Farben zeigt (Raster relativ zum Ausschnitt).
    nahe = {c for c in farben(grob) if max(abs(a - b) for a, b in zip(c, f.rgb)) < 40}
    assert len(farben(fein)) > len(nahe)
    assert fw.marke_feld(30, 15, f.mitte(), 4, (f.u, f.v)) == (7, 15)


def test_helligkeit_mit_bild_tasten_und_klammern():
    f = fw.Farbwaehler("#ff0000")
    f.taste(curses.KEY_NPAGE)
    assert f.wert == pytest.approx(0.95)
    f.taste(ord("["))
    assert f.wert == pytest.approx(0.90)
    f.taste(ord("]"))
    f.taste(curses.KEY_PPAGE)
    f.taste(curses.KEY_PPAGE)
    assert f.wert == 1.0
    assert f.hex == "#ff0000"
    f.taste(ord("+"))
    f.taste(curses.KEY_NPAGE)
    assert f.wert == pytest.approx(1 - fw.WERT_SCHRITT / 2)
    for _ in range(100):
        f.taste(curses.KEY_NPAGE)
    assert f.hex == "#000000"


# ── Hex ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("hexwert", ["#ff8800", "#202030", "#000000", "#ffffff",
                                     "#0a7fff", "#7f7f7f", "#123456", "#fedcba"])
def test_hex_hin_und_zurueck(hexwert):
    f = fw.Farbwaehler(hexwert)
    assert f.hex == hexwert
    assert f.taste(ENTER) == ("fertig", hexwert)
    # auch über Kreis + Helligkeit gerechnet (nicht nur der gemerkte Wert)
    h, s = f.farbton
    assert fw.hsv_hex(h, s, f.wert) == hexwert


def test_hex_tippen():
    f = fw.Farbwaehler()
    tippen(f, "#33CC")
    assert f.hex_feld == "33cc"
    assert f.hex == "#ffffff"                    # noch nicht fertig: Kreis unverändert
    tippen(f, "ff")
    assert f.hex == "#33ccff"                    # sechs Ziffern: sofort gesetzt
    assert f.taste(ENTER) == ("fertig", "#33ccff")


def test_hex_kurzform_fehler_und_esc_schliesst_nur_das_feld():
    f = fw.Farbwaehler("#000000")
    tippen(f, "#f8")
    assert f.taste(ENTER) is None and f.fehler
    f.taste(curses.KEY_BACKSPACE)
    tippen(f, "80")
    assert f.taste(ENTER) == ("fertig", "#ff8800")
    g = fw.Farbwaehler("#000000")
    tippen(g, "#12")
    assert g.taste(ESC) is None and g.hex_feld is None
    assert g.taste(ESC) == ("abbruch",)


def test_pfeil_schliesst_hex_feld_und_bewegt():
    f = fw.Farbwaehler()
    tippen(f, "#ab")
    f.taste(curses.KEY_RIGHT)
    assert f.hex_feld is None and f.u > 0


def test_start_ungueltig_ist_weiss():
    assert fw.Farbwaehler("blau").hex == "#ffffff"
    assert fw.Farbwaehler(None).taste(ESC) == ("abbruch",)


# ── Zeichnen: Paar-Budget, 256 Farben ───────────────────────────────────────
class _Z:
    """Ein Kontext wie tui/ansichten/kontext.py, nur mitschreibend: Paare
    zählen wie pix_attr (Budget base..top), Zellen sammeln."""

    def __init__(self, true=False, base=60, top=255, schon=0, farbe=True):
        self.C = {"pix_bg": (0, 0, 0) if farbe else None, "pix_true": true,
                  "acc": 1, "dim": 2, "faint": 3, "bright": 4, "ink": 5, "warn": 6}
        self.PIX = {"pairs": {("x", i): i for i in range(schon)}, "base": base,
                    "top": top, "voll": False}
        self.has_color = farbe
        self.PIX_MODUS = "mix"
        self.schirm = {}

    def pix_farbe(self, rgb):
        if self.C["pix_true"]:
            return tuple(min(255, round(v / 16) * 16) for v in rgb)
        return pixel.rgb_256(rgb)

    def pix_attr(self, fg, bg):
        key = (self.pix_farbe(fg), self.pix_farbe(bg))
        if key not in self.PIX["pairs"]:
            if self.PIX["top"] - len(self.PIX["pairs"]) <= self.PIX["base"]:
                self.PIX["voll"] = True
                return -1
            self.PIX["pairs"][key] = 1000 + len(self.PIX["pairs"])
        return self.PIX["pairs"][key]

    def safe_addstr(self, y, x, text, attr=0):
        for i, ch in enumerate(str(text)):
            self.schirm[(y, x + i)] = (ch, attr)

    def draw_box(self, y, x, h, w, title, attr=0):
        self.safe_addstr(y, x + 2, " %s " % title.upper(), attr)

    def text(self):
        zeilen = {}
        for (y, x), (ch, _a) in sorted(self.schirm.items()):
            zeilen.setdefault(y, []).append(ch)
        return "\n".join("".join(z) for _y, z in sorted(zeilen.items()))


@pytest.mark.parametrize("true", [False, True])
@pytest.mark.parametrize("schon", [0, 100, 150])
def test_paar_budget_laeuft_nie_ueber(true, schon):
    z = _Z(true=true, schon=schon)
    f = fw.Farbwaehler("#ff8800")
    for zoom in range(3):
        f.zeichne(z, 0, 0, 22, 70)
        assert not z.PIX["voll"], (true, schon, zoom)
        f.taste(ord("+"))


def test_bei_knappem_budget_wird_das_raster_groeber():
    weit, eng = _Z(true=True), _Z(true=True, schon=150)
    f = fw.Farbwaehler()
    f.zeichne(weit, 0, 0, 22, 70)
    fein = f.stufen_jetzt
    f.zeichne(eng, 0, 0, 22, 70)
    assert fw.STUFEN.index(f.stufen_jetzt) > fw.STUFEN.index(fein)
    voll = _Z(true=True, schon=190)
    f.zeichne(voll, 0, 0, 22, 70)
    assert f.stufen_jetzt is None and "zu wenig farben" in voll.text()
    assert not voll.PIX["voll"]


def test_256_farben_nimmt_naechste_farbe():
    z = _Z(true=False)
    f = fw.Farbwaehler("#ff8800")
    f.zeichne(z, 0, 0, 22, 70)
    assert all(0 <= a <= 255 and 0 <= b <= 255
               for k in z.PIX["pairs"] if k[0] != "x" for a, b in [k])
    assert "≈ 256: 208" in z.text() and "#ff8800" in z.text()
    t = _Z(true=True)
    f.zeichne(t, 0, 0, 22, 70)
    assert "≈ 256" not in t.text()


def test_ohne_farben_nur_text():
    z = _Z(farbe=False)
    f = fw.Farbwaehler("#123456")
    f.zeichne(z, 0, 0, 22, 70)
    assert "#123456" in z.text() and "keine farben" in z.text()
    assert not [k for k in z.PIX["pairs"] if k[0] != "x"]


def test_klein_zeigt_nur_hex():
    z = _Z()
    fw.Farbwaehler("#abcdef").zeichne(z, 0, 0, 5, 20)
    assert "#abcdef" in z.text()


# ── Stylebox ────────────────────────────────────────────────────────────────
ALLES = ["border-style", "border-color", "background-color", "color",
         "--zentrale-muster", "background-image"]
START = {"border-style": "dashed", "border-color": "#ff8800",
         "background-color": "#202030", "color": "#ffffff"}


def test_zeigt_nur_die_angebotenen_eigenschaften():
    sb = Stylebox(START, ["color"])
    assert [z["name"] for z in sb.zeilen()] == ["color"]
    assert sb.werte == {"color": "#ffffff"}                 # Rest des Stils nicht angeboten
    z = _Z()
    sb.zeichne(z, 0, 0, 14, 60)
    assert "Schrift" in z.text() and "Rahmen" not in z.text()
    voll = Stylebox(START, ALLES)
    assert [z["name"] for z in voll.zeilen()] == ALLES
    with pytest.raises(ValueError):
        Stylebox({}, ["border-radius"])


def test_angebot_als_schema_mit_eingeschraenkter_wahl():
    schema = stil.schema(["border-style"])
    schema["properties"]["border-style"]["oneOf"] = [
        {"const": "solid", "title": "dünn"}, {"const": "double", "title": "doppelt"}]
    sb = Stylebox({}, schema)
    assert sb.zeilen()[0]["text"] == "‹ keine ›"             # nicht gesetzt = ausgewählt
    sb.taste(curses.KEY_RIGHT)                               # keine → dünn → doppelt → keine
    assert sb.werte["border-style"] == "solid"
    assert sb.zeilen()[0]["text"] == "‹ dünn ›"
    sb.taste(curses.KEY_RIGHT)
    assert sb.zeilen()[0]["text"] == "‹ doppelt ›"
    sb.taste(curses.KEY_RIGHT)
    assert "border-style" not in sb.werte and sb.zeilen()[0]["text"] == "‹ keine ›"
    sb.taste(curses.KEY_LEFT)                                # rückwärts: keine → doppelt
    assert sb.werte["border-style"] == "double"


def test_wahl_aendern_mit_pfeilen_und_leertaste():
    sb = Stylebox(START, ALLES)
    sb.taste(curses.KEY_RIGHT)
    assert sb.werte["border-style"] == "dotted"
    sb.taste(curses.KEY_LEFT)
    sb.taste(curses.KEY_LEFT)
    assert sb.werte["border-style"] == "solid"
    for _ in range(4):
        sb.taste(9)                                          # Tab bis zum Muster
    sb.taste(ord(" "))                                       # ‹ keine › → keins
    sb.taste(ord(" "))
    assert sb.werte["--zentrale-muster"] == "punkte"
    sb.taste(curses.KEY_BACKSPACE)
    assert "--zentrale-muster" not in sb.werte              # entfernt (war nicht gesetzt)
    sb.taste(curses.KEY_UP)
    assert sb.aktuell["name"] == "color"


def test_keine_ist_eine_echte_wahl_im_kreis():
    sb = Stylebox({}, ALLES)
    texte = [z["text"] for z in sb.zeilen()]
    assert texte == ["‹ keine ›"] * 5 + ["‹ keine › · noch gesperrt"]
    reihe = []
    for _ in range(6):                                       # Rahmen: einmal rundum
        sb.taste(ord(" "))
        reihe.append(sb.werte.get("border-style"))
    assert reihe == ["solid", "dashed", "dotted", "double", "none", None]
    assert sb.zeilen()[0]["text"] == "‹ keine ›"
    sb.taste(curses.KEY_LEFT)                                # keine ← … am Ende: none
    assert sb.werte["border-style"] == "none"
    sb.taste(curses.KEY_RIGHT)
    assert "border-style" not in sb.werte                    # ‹ keine › schreibt kein CSS „none"
    assert sb.taste(ENTER) == ("fertig", {"border-style": None})   # Vertrag wie af5915e
    assert stil.anwenden({}, sb.ergebnis) == {}
    sb = Stylebox({}, ALLES)
    sb.feld = ALLES.index("--zentrale-muster")
    sb.taste(curses.KEY_RIGHT)
    assert sb.werte["--zentrale-muster"] == "none" and sb.zeilen()[4]["text"] == "‹ keins ›"
    sb.taste(curses.KEY_LEFT)
    assert sb.zeilen()[4]["text"] == "‹ keine ›"
    sb = Stylebox({"border-style": "dashed"}, ["border-style"])
    sb.taste(curses.KEY_LEFT)
    sb.taste(curses.KEY_LEFT)                                # dashed → solid → keine
    assert sb.zeilen()[0]["text"] == "‹ keine ›"
    assert sb.taste(ENTER) == ("fertig", {"border-style": None})


def test_farbe_keine_setzen_keine():
    sb = Stylebox({}, ["border-color"])
    assert sb.zeilen()[0]["text"] == "‹ keine ›" and sb.zeilen()[0]["farbe"] is None
    sb.taste(curses.KEY_RIGHT)                               # öffnet den Farbwähler
    tippen(sb, "#33ccff")
    sb.taste(ENTER)
    assert sb.waehler is None and sb.zeilen()[0]["text"] == "#33ccff"
    assert sb.zeilen()[0]["farbe"] == (0x33, 0xcc, 0xff)
    sb.taste(curses.KEY_DC)                                  # zurück auf ‹ keine ›
    assert sb.zeilen()[0]["text"] == "‹ keine ›" and "border-color" not in sb.werte
    assert sb.taste(ENTER) == ("fertig", {"border-color": None})
    sb = Stylebox({"border-color": "#ff8800"}, ["border-color"])
    sb.taste(curses.KEY_BACKSPACE)
    assert sb.zeilen()[0]["text"] == "‹ keine ›"
    assert sb.taste(ENTER) == ("fertig", {"border-color": None})


def test_farbe_oeffnet_farbwaehler_und_schreibt_zurueck():
    sb = Stylebox(START, ALLES)
    sb.taste(curses.KEY_DOWN)                                # Rahmenfarbe
    sb.taste(ord(" "))
    assert sb.waehler is not None and sb.waehler.hex == "#ff8800"
    z = _Z()
    sb.zeichne(z, 0, 0, 22, 70)
    assert "FARBE WÄHLEN" in z.text()
    tippen(sb, "#33ccff")
    assert sb.taste(ENTER) is None and sb.waehler is None    # Wähler fertig, Box bleibt
    assert sb.werte["border-color"] == "#33ccff"
    # Abbruch im Wähler lässt den Wert stehen
    sb.taste(curses.KEY_DOWN)
    sb.taste(ord("#"))                                       # gleich mit Hex-Feld
    assert sb.waehler.hex_feld == ""
    sb.taste(ESC)
    sb.taste(ESC)
    assert sb.waehler is None and sb.werte["background-color"] == "#202030"


def test_gesperrtes_icon_laesst_sich_nicht_oeffnen():
    sb = Stylebox({"background-image": "url(x.png)"}, ["background-image", "color"])
    assert sb.zeilen()[0]["text"] == "noch gesperrt"
    for ch in (ord(" "), curses.KEY_RIGHT, curses.KEY_LEFT, ord("#")):
        sb.taste(ch)
        assert sb.waehler is None
    assert "gesperrt" in sb.hinweis
    assert sb.werte == {"background-image": "url(x.png)"}
    assert sb.taste(ENTER) == ("fertig", {})


def test_enter_gibt_nur_geaenderte_gueltige_css_zurueck():
    sb = Stylebox(dict(START, **{"font-size": "12px", "color": "kaputt"}), ALLES)
    assert "color" not in sb.anfang                          # Kaputtes still weg
    sb.taste(curses.KEY_RIGHT)                               # dashed → dotted
    erg = sb.taste(ENTER)
    assert erg == ("fertig", {"border-style": "dotted"})
    assert stil.pruefen(sb.ergebnis, ALLES) == sb.ergebnis
    assert sb.ergebnis == {"border-style": "dotted"}


def test_entfernen_setzt_nicht_gesetzt_und_gibt_none_zurueck():
    sb = Stylebox(START, ALLES)
    for ch in (curses.KEY_BACKSPACE, 127, 8, curses.KEY_DC):
        sb.feld = 0
        sb.werte["border-style"] = "dashed"
        sb.taste(ch)
        assert "border-style" not in sb.werte
    assert sb.zeilen()[0]["text"] == "‹ keine ›"
    sb.taste(curses.KEY_DOWN)
    sb.taste(curses.KEY_DC)                                  # Rahmenfarbe weg
    assert sb.zeilen()[1]["text"] == "‹ keine ›" and sb.zeilen()[1]["farbe"] is None
    for _ in range(3):
        sb.taste(9)                                          # Muster: nie gesetzt
    sb.taste(curses.KEY_BACKSPACE)
    erg = sb.taste(ENTER)
    assert erg == ("fertig", {"border-style": None, "border-color": None})
    assert stil.pruefen(sb.ergebnis, ALLES, entfernen=True) == sb.ergebnis
    assert stil.anwenden(START, sb.ergebnis) == {"background-color": "#202030", "color": "#ffffff"}


def test_entfernt_wieder_setzen_und_r_zurueck_auf_anfang():
    sb = Stylebox(START, ALLES)
    sb.taste(curses.KEY_BACKSPACE)
    sb.taste(curses.KEY_RIGHT)                               # wieder gesetzt: keine → solid
    sb.taste(curses.KEY_RIGHT)
    assert sb.werte["border-style"] == "dashed"
    assert sb.taste(ENTER) == ("fertig", {})                 # wie am Anfang
    sb = Stylebox(START, ALLES)
    sb.taste(curses.KEY_DOWN)
    sb.taste(curses.KEY_DC)
    sb.taste(ord(" "))                                       # Farbwähler wie sonst
    assert sb.waehler is not None and sb.waehler.hex == "#ffffff"
    tippen(sb, "#123456")
    sb.taste(ENTER)
    assert sb.werte["border-color"] == "#123456"
    sb.taste(ord("r"))                                       # zurück auf den Anfang
    assert sb.werte["border-color"] == "#ff8800"
    sb.taste(curses.KEY_DC)
    sb.taste(ord("r"))
    assert sb.werte["border-color"] == "#ff8800"
    # neu gesetzt und wieder entfernt → None (Aufrufer räumt auf); r → gar nichts
    sb.taste(curses.KEY_DOWN)
    sb.taste(curses.KEY_DOWN)
    sb.taste(curses.KEY_DOWN)                                # Muster
    sb.taste(ord(" "))
    sb.taste(curses.KEY_DC)
    assert sb.taste(ENTER) == ("fertig", {"--zentrale-muster": None})
    sb = Stylebox({"color": "kaputt"}, ["color"])            # kaputter Anfang
    sb.taste(curses.KEY_DC)
    assert sb.taste(ENTER) == ("fertig", {"color": None})
    sb = Stylebox({"color": "kaputt"}, ["color"])
    sb.taste(curses.KEY_DC)
    sb.taste(ord("r"))
    assert sb.taste(ENTER) == ("fertig", {})


def test_entfernen_beim_gesperrten_icon_geht_nicht():
    sb = Stylebox({"background-image": "url(x.png)"}, ["background-image"])
    for ch in (curses.KEY_BACKSPACE, curses.KEY_DC, ord("r")):
        sb.taste(ch)
    assert "gesperrt" in sb.hinweis
    assert sb.taste(ENTER) == ("fertig", {})


def test_abbruch_nach_entfernen_laesst_das_original():
    original = dict(START)
    sb = Stylebox(original, ALLES)
    sb.taste(curses.KEY_BACKSPACE)
    assert sb.taste(ESC) == ("abbruch",) and sb.ergebnis is None
    assert original == START


def test_vorschau_ohne_entfernte_eigenschaft():
    sb = Stylebox(START, ALLES, text="Uni")
    sb.feld = ALLES.index("background-color")
    sb.taste(curses.KEY_DC)
    bild = sb.vorschau(9, 5, grund=(1, 2, 3))
    assert bild[0][0][2] == (1, 2, 3) and bild[2][4][2] == (1, 2, 3)   # Fläche des Themes
    sb.feld = 0
    sb.taste(curses.KEY_DC)                                  # Rahmenstil weg → wie ohne Stil
    assert sb.vorschau(4, 3)[0][0][0] == RAHMEN_ZEICHEN["solid"][0]
    z = _Z()
    sb.zeichne(z, 0, 0, 14, 70)
    assert "‹ keine ›" in z.text()


def test_esc_gibt_none():
    sb = Stylebox(START, ALLES)
    sb.taste(curses.KEY_RIGHT)
    assert sb.taste(ESC) == ("abbruch",)
    assert sb.ergebnis is None


def test_vorschau_rahmen_farben_muster_text():
    sb = Stylebox(START, ALLES, text="Uni")
    bild = sb.vorschau(9, 5)
    assert "".join(ch for ch, _f, _b in bild[0]) == "┌╌╌╌╌╌╌╌┐"
    assert bild[0][0][1] == (255, 136, 0) and bild[0][0][2] == (32, 32, 48)
    assert "".join(ch for ch, _f, _b in bild[2]) == "╎  Uni  ╎"
    assert bild[2][3][1] == (255, 255, 255)
    for name, zeichen in RAHMEN_ZEICHEN.items():
        sb.werte["border-style"] = name
        assert sb.vorschau(4, 3)[0][0][0] == zeichen[0]
    sb.werte["--zentrale-muster"] = "raster"
    assert sb.vorschau(9, 5)[1][1][0] == "░"
    nur_schrift = Stylebox({"color": "#ff0000"}, ["color"], text="Kopf")
    oben = nur_schrift.vorschau(8, 3, grund=(0, 0, 0))[0]
    assert {ch for ch, _f, _b in oben} == {" "}              # kein Rahmen angeboten


def test_stylebox_zeichnen_haelt_das_budget():
    z = _Z(true=True, schon=150)
    sb = Stylebox(START, ALLES)
    sb.zeichne(z, 0, 0, 14, 70)
    assert not z.PIX["voll"]
    assert "noch gesperrt" in z.text() and "Uni" not in z.text()
    schmal = _Z()
    sb.zeichne(schmal, 0, 0, 20, 40)                         # Vorschau rutscht nach unten
    assert "Beispiel" in schmal.text()
