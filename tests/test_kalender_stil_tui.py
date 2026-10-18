"""
Kalender-TUI: die Stylebox (im Fenster „advanced") und wie ein gestylter
Termin aussieht.

Sasha, 10.10.2026: „Im Terminformular gibt es NUR eine Option ‚Stylebox'
(kein eigenes ‚color'-Feld). Von dort öffnen sich die Bausteine, und das
Ergebnis wird auf den Termin (seinen Container/Kasten im Kalender)
angewendet." Geprüft: Formular + Stylebox (kalender_werkzeuge.py), Anzeige
in A/B/C (kalender_ansichten.py, kalender_stil.py) und die Farbpaare
(kalender.py). Reine Logik — ohne Terminal und ohne Backend.
"""
import curses
from datetime import date

from tui.ansichten import kalender_ansichten as ka
from tui.ansichten import kalender_beispiel as kb
from tui.ansichten import kalender_stil as ks
from tui.ansichten import kalender_werkzeuge as kw

TAG = date(2026, 10, 7)
STIL = {"border-style": "double", "border-color": "#ff8800", "background-color": "#202030",
        "color": "#ffffff", "--zentrale-muster": "punkte"}
UNI = {"day": "2026-10-07", "label": "Uni", "time": "08:00", "ende": "12:00",
       "stil": STIL, "kennung": "k-uni"}
KINO = {"day": "2026-10-07", "label": "Kino", "time": "19:00", "ende": "21:00",
        "kennung": "k-kino"}


def text(zeile):
    return "".join(t for t, _r in zeile)


def daten(view="week", termine=None):
    return kb.api_daten(view, ref="2026-10-07", heute="2026-10-05",
                        termine=termine if termine is not None else [UNI, KINO], routinen=[])


def _feld(f, name):
    return next(x for x in f.felder if x.name == name)


def _auf(f, name):
    f.i = [x.name for x in f.felder].index(name)


def _stil(f):
    return _feld(f, "advanced").adv["stil"]


def _setze_stil(f, st):
    _feld(f, "advanced").adv["stil"] = dict(st)


def _zur_stylebox(f):
    """Formular → Fenster „advanced" → Zeile Stylebox → Stylebox offen."""
    _auf(f, "advanced")
    assert f.taste(10) == "weiter" and f.box is not None       # Enter speichert hier nicht
    f.taste(258)                                               # Typ normal: ↓ = Stylebox
    assert f.box.reihe == "stil"
    f.taste(10)
    assert f.box.unter is not None


# ── Formular: die Stylebox liegt im Fenster „advanced" (11.10.2026) ───
def test_neu_hat_kein_feld_stylebox_mehr_nur_advanced():
    f = kw.formular_neu(TAG, TAG)
    namen = [x.name for x in f.felder]
    assert "stil" not in namen and "liste" not in namen and namen.count("advanced") == 1
    assert _feld(f, "advanced").beschriftung == "Advanced"
    assert kw.kalender_advanced.zusammenfassung(next(x for x in f.felder if x.art == "advanced").adv) == "typ normal · stil keine"


def test_enter_oeffnet_die_stylebox_fertig_uebernimmt_esc_laesst():
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Uni"
    _zur_stylebox(f)
    assert f.box.unter.text == "Uni"                           # Vorschau mit dem Titel
    f.taste(-1)                                                # Takt der Schleife: nichts
    assert f.box.unter is not None
    f.taste(curses.KEY_RIGHT)                                  # Rahmen: ‹ keine › → solid
    f.taste(curses.KEY_RIGHT)                                  # → dashed
    f.taste(10)                                                # Stylebox: nehmen
    assert f.box is not None and f.box.unter is None
    assert f.box.stil == {"border-style": "dashed"}
    assert _stil(f) == {}                                      # noch nicht im Formular
    f.taste(10)                                                # Stylebox wieder auf
    f.taste(curses.KEY_RIGHT)
    f.taste(27)                                                # Esc nur in der Box
    assert f.box.unter is None and f.box.stil == {"border-style": "dashed"}
    assert f.taste(19) == "weiter" and f.box is None           # Strg-S: übernehmen
    assert _stil(f) == {"border-style": "dashed"}
    zeile = kw.kalender_advanced.zusammenfassung(next(x for x in f.felder if x.art == "advanced").adv)
    assert zeile == "typ normal · stil ┌╌┐"


def test_esc_im_fenster_verwirft_den_neuen_stil():
    f = kw.formular_neu(TAG, TAG)
    _zur_stylebox(f)
    f.taste(curses.KEY_RIGHT)
    f.taste(10)
    assert f.box.stil == {"border-style": "solid"}
    f.taste(27)
    assert f.box is None and _stil(f) == {}


def test_farbe_ueber_den_farbwaehler():
    f = kw.formular_neu(TAG, TAG)
    _zur_stylebox(f)
    f.taste(curses.KEY_DOWN)                                   # Rahmenfarbe
    f.taste(ord("#"))
    for ch in "ff8800":
        f.taste(ord(ch))
    for _ in range(3):                                         # Enter bis der Wähler zu ist
        if f.box.unter.waehler is None:
            break
        f.taste(10)
    f.taste(10)                                                # Box: nehmen
    f.taste(19)                                                # Fenster: übernehmen
    # Rahmen war ‹ keine ›: mit der Farbe wird er durchgezogen (stil.stimmig)
    assert _stil(f) == {"border-color": "#ff8800", "border-style": "solid"}


def test_speichern_neu_schickt_stil_mit():
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Uni"
    _feld(f, "von").text, _feld(f, "bis").text = "8", "12"
    _setze_stil(f, STIL)
    assert f.taste(19) == "fertig"                             # Strg-S
    (meth, pfad, body), = f.plan()["aufrufe"]
    assert (meth, pfad) == ("POST", "/api/calendar/entry") and body["stil"] == STIL
    # Wiederholung und Spanne nehmen ihn genauso mit
    w = {"titel": "Uni", "datum": TAG, "ganz": "nein", "von": "08:00", "bis": None,
         "wied": "wöchentlich", "alle": 1, "wtage": [], "wbis": None, "stil": STIL}
    (_m, pfad, body), = kw._neu_plan(w, TAG)[0]
    assert pfad == "/api/calendar/routine" and body["stil"] == STIL
    w = {"titel": "Reise", "datum": TAG, "ganz": "ja", "tage": 3, "wied": "keine", "stil": STIL}
    (_m, pfad, body), = kw._neu_plan(w, TAG)[0]
    assert pfad == "/api/calendar/spanne" and body["stil"] == STIL


def test_backspace_entfernt_den_stil():
    f = kw.formular_bearbeiten(dict(UNI, layer="termine"), TAG, TAG)
    assert _stil(f) == STIL
    _auf(f, "advanced")
    f.taste(10)
    f.taste(258)
    f.taste(127)                                               # ⌫ auf der Zeile Stylebox
    assert f.box.stil == {}
    f.taste(19)
    assert _stil(f) == {}


def test_bearbeiten_stil_per_kennung_nur_wenn_geaendert():
    f = kw.formular_bearbeiten(dict(UNI, layer="termine"), TAG, TAG)
    assert f.taste(19) == "fertig"
    assert all(p != "/api/calendar/stil" for _m, p, _b in f.plan()["aufrufe"])
    f = kw.formular_bearbeiten(dict(UNI, layer="termine"), TAG, TAG)
    _setze_stil(f, {"color": "#00ff00"})
    assert f.taste(19) == "fertig"
    assert ("POST", "/api/calendar/stil", {"kennung": "k-uni", "stil": {"color": "#00ff00"}}) \
        in f.plan()["aufrufe"]


def test_routine_und_spanne_alle_haben_stil_dieser_tag_nicht():
    roh = {"label": "Geige", "time": "18:00", "recurring": True, "rrule": "FREQ=WEEKLY;BYDAY=WE",
           "layer": "termine", "kennung": "k-geige", "stil": {"color": "#ff0000"}}
    frage = kw.formular_bearbeiten(roh, TAG, TAG)
    frage.taste(ord("t"))
    dieser = frage.plan()["weiter"]
    assert "advanced" not in [x.name for x in dieser.felder]
    frage = kw.formular_bearbeiten(roh, TAG, TAG)
    frage.taste(ord("a"))
    alle = frage.plan()["weiter"]
    _setze_stil(alle, {})
    assert alle.taste(19) == "fertig"
    assert ("POST", "/api/calendar/stil", {"kennung": "k-geige", "stil": {}}) \
        in alle.plan()["aufrufe"]
    sp = {"label": "Messe", "spanning": True, "von": "2026-10-06", "bis": "2026-10-08",
          "layer": "termine", "kennung": "k-messe"}
    frage = kw.formular_bearbeiten(sp, TAG, TAG)
    frage.taste(ord("a"))
    assert "advanced" in [x.name for x in frage.plan()["weiter"].felder]


def test_kopie_und_ansehen_tragen_den_stil():
    assert kw.kopie(UNI)["stil"] == STIL
    assert any(z.startswith("Stil") and "fläche #202030" in z for z in kw.details(UNI, TAG))


# ── Anzeige ────────────────────────────────────────────────────────────
def test_ohne_stil_bleibt_alles_wie_es_war():
    ohne = [dict(UNI, stil=None), KINO]
    for ansicht in ("A", "B", "C"):
        zeilen = ka.zeichne(ansicht, daten("month" if ansicht != "C" else "week", ohne), 120, 40)
        assert not any(r.startswith(ks.MARKE) for z in zeilen for _t, r in z)


def test_c_block_mit_doppelrahmen_flaeche_und_muster():
    zeilen = ka.ansicht_c(daten(), 160, 40)
    alle = [(t, r) for z in zeilen for t, r in z]
    stil_rollen = [r for _t, r in alle if r.startswith(ks.MARKE)]
    assert stil_rollen, "der Block trägt den Stil"
    gestylt = "".join(t for t, r in alle if r.startswith(ks.MARKE))
    assert "╔" in gestylt and "╚" in gestylt and "║" in gestylt and "·" in gestylt
    assert "Uni" in gestylt
    basis, schrift, grund = ks.teile(next(r for t, r in alle if "Uni" in t
                                          and r.startswith(ks.MARKE)))
    assert (schrift, grund) == ("#ffffff", "#202030") and basis.endswith(ka.INV)
    # Kino ohne Stil: wie immer
    assert any("Kino" in t and not r.startswith(ks.MARKE) for t, r in alle)


def test_c_schmaler_block_stuft_ab():
    lw = ka.Leinwand(10, 6)
    ks.c_block(lw, 0, 0, 3, 2, ["Uni", "8–12"], "k_t0_inv", STIL)
    assert lw.z[0][0][0] == "║" and lw.z[0][2][0] == "║"      # nur die Seiten
    lw = ka.Leinwand(10, 6)
    ks.c_block(lw, 0, 0, 2, 2, ["Uni"], "k_t0_inv", STIL)
    assert lw.z[0][0][0] == "U"                                 # zu schmal: kein Rahmen
    lw = ka.Leinwand(10, 6)
    ks.c_block(lw, 0, 0, 6, 4, ["Uni"], "k_t0_inv", STIL, gewaehlt=True)
    assert lw.z[0][0] == ("╔", "k_t0_inv")                      # gewählt: Auswahlfarbe, Form bleibt


def test_a_rahmenzeichen_und_schild():
    zeilen = ka.ansicht_a(daten("month"), 120, 40)
    z = next(z for z in zeilen if "Uni" in text(z))
    assert any(t == "║" and ks.teile(r)[1] == "#ff8800" for t, r in z)
    assert any(" Uni " in t and ks.teile(r)[2] == "#202030" for t, r in z)


def test_b_zeile_in_der_stilfarbe():
    zeilen = ka.ansicht_b(daten("month"), 140, 40)
    z = next(z for z in zeilen if "Uni" in text(z))
    assert any("Uni" in t and ks.teile(r)[1] == "#ffffff" for t, r in z)


def test_vorschau_text():
    assert ks.vorschau_text({}) == "keine"
    assert ks.vorschau_text(STIL) == ("╔═╗ · rand #ff8800 · fläche #202030 · "
                                      "schrift #ffffff · Punkte")
    assert ks.farben({"background-color": "#ffffff"})["schrift"] == "#000000"
    assert ks.von({"stil": {"color": "rot", "border-style": "dashed"}}) == {"border-style": "dashed"}


# ── Farbpaare (kalender.py) ────────────────────────────────────────────
class _Z:
    def __init__(self, voll=False):
        self.C = {"dim": 1, "k_t0": 2, "k_t0_inv": 3, "pix_true": True, "pix_bg": (0, 0, 0),
                  "kal_glas": {"thema": "night", "flaeche": {},
                               "paare": {"dim": ((150, 150, 150), (0, 0, 0), 0),
                                         "k_t0_inv": ((10, 10, 10), (0, 200, 200), 0)}}}
        self.PIX = {"pairs": {}}
        self.voll = voll

    def pix_farbe(self, rgb):
        return tuple(rgb)

    def pix_attr(self, fg, bg):
        if not self.voll:
            self.PIX["pairs"][(tuple(fg), tuple(bg))] = 99
        return 99 if not self.voll else 0


def _kal(z):
    from tui.ansichten.kalender import Kalender
    k = object.__new__(Kalender)
    k.z, k._glas_farben = z, {}
    return k


def test_stil_attr_mischt_mit_der_rueckfallrolle():
    z = _Z()
    k = _kal(z)
    assert k._stil_attr(ks.rolle("k_t0_inv", "#ff8800", None)) == 99
    assert ((255, 136, 0), (0, 200, 200)) in z.PIX["pairs"]     # Grund = Kursfläche
    voll = _Z(voll=True)
    assert _kal(voll)._stil_attr(ks.rolle("k_t0_inv", "#ff8800", None)) == 3   # Paare aus → Rückfall
    ohne = _Z()
    ohne.C["kal_glas"] = None
    assert _kal(ohne)._stil_attr(ks.rolle("k_t0", "#ff8800", None)) == 2


def test_stylebox_entfernt_einzelne_eigenschaft():
    """Rückgabe {"name": None} der Stylebox (af5915e) entfernt die Eigenschaft,
    statt None in den Stil zu schreiben."""
    from tui.ansichten import kalender_advanced, kalender_stil
    adv = kalender_advanced.Advanced({"stil": {"border-style": "double", "color": "#ffffff"}})
    # Stand-in der Stylebox: was ihre Tastentabelle (kalender_kasten) liest
    adv.unter = type("B", (), {"waehler": None, "aktuell": {"art": "wahl"},
                               "taste": lambda self, ch: (
        "fertig", {"border-style": None, "color": "#ff8800"})})()
    adv.taste(10)
    assert adv.unter is None and adv.stil == {"color": "#ff8800"}
    assert kalender_stil.stil_kern.anwenden({"a": 1}, {"a": None}) == {}
