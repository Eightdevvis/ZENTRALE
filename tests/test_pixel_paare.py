"""Pixel-Farbpaare (Kontext.pix_attr, 2026-10-21): das Auge im leeren Chat
zeigte gelbe Pixel, weil der Paar-Vorrat mitten im Bild leerlief und
pix_attr dann Bernstein lieferte. Jetzt: feste Theme-Paare doppelt nicht
doppelt anlegen, Pixel-Paare pro Bild wiederverwenden, und wenn es doch
nicht reicht, die nächstliegende vorhandene Pixelfarbe statt Bernstein."""
import curses

import pytest

from tui import pixel
from tui.ansichten import kontext
from tui.ansichten.farben import KAL, MOTIV_FARBEN

AMBER = -7


class _Schirm:
    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def farbcurses(monkeypatch):
    """curses mit 256 Farben/Paaren, das jede init_pair-Belegung mitschreibt."""
    buch = {"paare": {}, "log": []}

    def init_pair(n, fg, bg):
        if not 0 < n < curses.COLOR_PAIRS:
            raise curses.error("paar %d" % n)
        buch["paare"][n] = (fg, bg)
        buch["log"].append(n)
    monkeypatch.setattr(curses, "COLORS", 256, raising=False)
    monkeypatch.setattr(curses, "COLOR_PAIRS", 256, raising=False)
    monkeypatch.setattr(curses, "init_pair", init_pair)
    monkeypatch.setattr(curses, "color_pair", lambda n: n << 8)
    return buch


def _kontext(thema="night"):
    z = kontext.Kontext(_Schirm(), None, True, object())
    z.apply_theme(thema)
    z.C["amber"] = AMBER
    return z


def _auge_bild(z, t_ms, farben="nacht", denkt=False):
    """Ein Bild des Auges durch pix_attr → Liste (Wunsch-RGB-Paar, attr)."""
    z.pix_neues_bild()
    aus = []
    for zeile in pixel.auge_zellen(1.0, t_ms, denkt, farben, "mix"):
        for f in zeile:
            if f:
                aus.append(((f[1], f[2]), z.pix_attr(f[1], f[2])))
    return aus


def test_auge_ohne_bernstein_in_beiden_themen(farbcurses):
    for thema, farben in (("night", "nacht"), ("day", "tag")):
        z = _kontext(thema)
        for t in range(0, 12000, 41):
            bild = _auge_bild(z, t, farben, denkt=t % 2 == 0)
            assert all(a != AMBER for _w, a in bild), (thema, t)
            assert not z.PIX["voll"], (thema, t)


def test_auge_exakt_bei_vorrat_knapp_ueber_einem_bild(farbcurses):
    """Vorrat künstlich klein: nur ein Bild Platz, die vorigen müssen
    wiederverwendet werden — jede Zelle bekommt genau ihre Farbe."""
    z = _kontext()
    z.PIX["base"] = z.PIX["top"] - 105 + 1          # 105 = das farbigste Auge
    for t in range(0, 12000, 41):
        for (fg, bg), attr in _auge_bild(z, t, denkt=t % 3 == 0):
            assert attr != AMBER
            n = attr >> 8
            assert farbcurses["paare"][n] == (z.pix_farbe(fg), z.pix_farbe(bg)), t
        assert not z.PIX["voll"]


def test_vorrat_zu_klein_nimmt_naechste_pixelfarbe_statt_bernstein(farbcurses):
    z = _kontext()
    z.PIX["base"] = z.PIX["top"] - 20 + 1           # viel zu wenig für ein Auge
    bild = _auge_bild(z, 3000)
    assert z.PIX["voll"]
    gruen = {a for _w, a in bild}
    assert AMBER not in gruen
    for a in gruen:                                  # alles Grüntöne/Grund des Auges
        fg, _bg = farbcurses["paare"][a >> 8]
        r, g, b = pixel.xterm_rgb(fg)
        assert g >= r and g >= b, (fg, (r, g, b))


def test_kein_paar_wird_im_laufenden_bild_umdefiniert(farbcurses):
    """curses färbt gezeichnete Zellen mit, wenn ein Paar neu belegt wird —
    darum darf ein Bild nie ein Paar überschreiben, das es selbst benutzt."""
    z = _kontext()
    z.PIX["base"] = z.PIX["top"] - 110 + 1
    for t in range(0, 8000, 53):
        z.pix_neues_bild()
        im_bild = set()
        for zeile in pixel.auge_zellen(1.0, t, t % 2 == 0, "nacht", "mix"):
            for f in zeile:
                if f:
                    vorher = len(farbcurses["log"])
                    n = z.pix_attr(f[1], f[2]) >> 8
                    neu = farbcurses["log"][vorher:]
                    assert not (set(neu) & im_bild), t
                    im_bild.add(n)


def test_feste_paare_ohne_doppelte_und_kalenderfarben_wie_entworfen(farbcurses):
    for thema in ("night", "day"):
        farbcurses["paare"].clear()
        z = _kontext(thema)
        belegt = list(farbcurses["paare"].values())
        assert len(belegt) == len(set(belegt)), thema       # nichts doppelt
        assert z.PIX["top"] - z.PIX["base"] + 1 >= 110, thema  # Platz fürs Auge
        C, bg = z.C, kontext.THEMES[thema]["bg256"]

        def paar(name):
            return farbcurses["paare"][C[name] >> 8]
        for name, (schrift, f_grund, f_schrift, _r) in KAL[thema].items():
            assert paar("k_" + name) == (schrift, bg), name
            assert paar("k_" + name + "_inv") == (f_schrift, f_grund), name
            assert paar("k_" + name + "_blass")[1] == bg, name
        for motiv, farbe in MOTIV_FARBEN[thema].items():
            assert paar("k_m_" + motiv) == (farbe, bg), motiv


def test_pixel_teilt_ein_gleiches_theme_paar(farbcurses):
    z = _kontext()
    th = kontext.THEMES["night"]
    fg, bg = th["ink"][1], th["bg256"]
    vorher = len(farbcurses["log"])
    attr = z.pix_attr(pixel.xterm_rgb(fg), pixel.xterm_rgb(bg))
    assert farbcurses["log"][vorher:] == []           # kein neues Paar
    assert farbcurses["paare"][attr >> 8] == (fg, bg)


def test_pix_frei_zaehlt_nur_das_laufende_bild(farbcurses):
    z = _kontext()
    alle = z.PIX["top"] - z.PIX["base"] + 1
    bild = _auge_bild(z, 1000)
    belegt = len({a for _w, a in bild if (a >> 8) >= z.PIX["base"]})
    assert z.pix_frei() == alle - belegt
    z.pix_neues_bild()
    assert z.pix_frei() == alle


def test_pix_genau_kennt_geteilte_und_meldet_volle(farbcurses):
    z = _kontext()
    th = kontext.THEMES["night"]
    ink = (pixel.xterm_rgb(th["ink"][1]), pixel.xterm_rgb(th["bg256"]))
    assert z.pix_genau(*ink) is not None              # festes Paar zählt als genau
    z.PIX["base"] = z.PIX["top"]                       # nur noch ein Platz
    z.pix_neues_bild()
    assert z.pix_genau((10, 200, 10), (0, 0, 0)) is not None
    assert z.pix_genau((200, 10, 200), (0, 0, 0)) is None   # kein Paar → eigener Rückfall
