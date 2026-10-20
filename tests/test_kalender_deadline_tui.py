"""Ganztägiges gestapelt + Termintyp deadline in der TUI (20.10.2026).

Sasha: „ganztägige events: ich habe 2 am freitag angelegt und es wird nur
eins angezeigt, fix das, sie sollen sich oben stacken. füg noch einen eigenen
typen ‚deadline' hinzu … rot leuchten … je näher man ihr kommt … nich oben
… sondern halt mit ner uhrzeit, nur nen textoverlap".

Ohne Terminal: die Ansichten sind reine Funktionen (kalender_ansichten),
das Leuchten rechnet mit der gestellten Uhr (core/uhr.py) — datumsunabhängig.
"""
import curses
from datetime import datetime, timedelta

import pytest

import kalender_deadline as kern_dl
import uhr
from tui.ansichten import kalender_advanced as kadv
from tui.ansichten import kalender_ansichten as ka
from tui.ansichten import kalender_beispiel as kb
from tui.ansichten import kalender_deadline as kdl
from tui.ansichten import kalender_werkzeuge as kw

FR = "2026-10-23"                    # ein Freitag
REF = "2026-10-21"
JETZT = datetime(2026, 10, 21, 12, 0)
STRG_S = 19


def daten(view="week", termine=(), routinen=()):
    return kb.api_daten(view, ref=REF, heute=REF, termine=list(termine), routinen=list(routinen))


def text(z):
    return "".join(t for t, _r in z)


def zellen(z):
    return [(ch, r) for t, r in z for ch in t]


def ganztags(n, tag=FR, **mehr):
    return [{"day": tag, "label": "Ganz%d" % i, **mehr} for i in range(1, n + 1)]


# ── 1. Ganztägiges gestapelt ───────────────────────────────────────────
@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_c_ganztaegige_stapeln_sich(n):
    zeilen = [text(z) for z in ka.ansicht_c(daten(termine=ganztags(n)), 130, 36)]
    sichtbar = [i for i in range(1, n + 1) if any("Ganz%d" % i in z for z in zeilen)]
    if n <= ka.GANZTAGS_ZEILEN:
        assert sichtbar == list(range(1, n + 1))
        assert not any("mehr" in z for z in zeilen)
    else:                                         # 4 Zeilen: 3 Titel + „+2 mehr"
        assert sichtbar == [1, 2, 3]
        assert any("+%d mehr" % (n - 3) in z for z in zeilen)
    # jede in ihrer eigenen Zeile, direkt untereinander ab Zeile 2
    reihen = [next(k for k, z in enumerate(zeilen) if "Ganz%d" % i in z) for i in sichtbar]
    assert reihen == list(range(2, 2 + len(sichtbar)))
    assert "ganzt." in zeilen[2]


def test_c_zone_so_hoch_wie_der_volle_tag_und_achse_darunter():
    termine = ganztags(3) + ganztags(1, tag="2026-10-19") + [
        {"day": "2026-10-19", "label": "Frueh", "time": "08:00", "ende": "09:00"}]
    zeilen = [text(z) for z in ka.ansicht_c(daten(termine=termine), 130, 36)]
    assert "Ganz1" in zeilen[2]                         # Montag: eine, Freitag: drei
    assert "08:00" in zeilen[5] and "Frueh" in zeilen[5]   # Achse beginnt unter der Zone


def test_c_auswahl_trifft_jeden_im_stapel_auch_hinter_plus_n():
    d = daten(termine=ganztags(6))
    akz = ka.ROLLE["a_akzent"] + ka.INV
    for t in kw.eintraege(d, datetime.fromisoformat(FR).date(), False):
        zeilen = ka.ansicht_c(d, 130, 36, auswahl={"tag": FR, "roh": t["roh"]})
        assert any(t["label"] in tx for z in zeilen for tx, r in z if r == akz), t["label"]


def test_c_uncommitted_ganztaegig_als_glas_in_eigener_zeile():
    termine = ganztags(1) + [{"day": FR, "label": "Vielleicht", "layer": "uncommitted"}]
    zeilen = ka.ansicht_c(daten(termine=termine), 130, 36)
    z = next(z for z in zeilen if "Vielleicht" in text(z))
    assert any(ka.GLAS in r for _t, r in z)
    assert "Ganz1" not in text(z)


def test_a_und_b_zeigen_beide_ganztaegigen():
    d = daten("month", termine=ganztags(2))
    a = [text(z) for z in ka.ansicht_a(d, 120, 40, auswahl={"tag": FR})]
    assert any("Ganz1" in z for z in a) and any("Ganz2" in z for z in a)
    b = [text(z) for z in ka.ansicht_b(d, 130, 44)]
    assert any("Ganz1" in z for z in b) and any("Ganz2" in z for z in b)


# ── 2. Deadline: Leuchten über die Zeit ────────────────────────────────
def _dl(time="23:59", vorwarnung=3 * 1440, **mehr):
    return {"day": FR, "label": "Analysis HÜ", "time": time, "typ": "deadline",
            "vorwarnung": vorwarnung, **mehr}


def test_stufen_werden_mit_der_zeit_kraeftiger():
    roh = _dl()
    zp = datetime(2026, 10, 23, 23, 59)
    stufen = []
    with uhr.gestellt(zp - timedelta(days=4) + timedelta(minutes=1)):
        for _ in range(9):                         # alle 12 h, über die Deadline hinaus
            stufen.append(kdl.stufe(roh, FR))
            uhr.vorstellen(hours=12)
    assert stufen == [0, 0, 1, 1, 2, 2, 3, 3, kdl.STUFE_VORBEI]
    assert [kdl.rolle(s) for s in (0, 1, 2, 3, -1)] == \
        ["k_dl0", "k_dl1", "k_dl2", "k_dl3", "k_dlx"]
    assert kdl.rolle(2, unv=True) == "k_dl2_blass"
    assert not kdl.flaeche(2) and kdl.flaeche(3)


def test_tui_und_kern_lesen_dauer_gleich():
    for s in ("3d", "12h", "1d12h", "90m", "90", "2 tage", "", "bald", "400d"):
        k = kern_dl.dauer_lesen(s)
        k = None if k is None or k > kern_dl.VORWARNUNG_HOECHSTENS else k
        assert kadv._dauer_lesen(s) == k, s
    for m in (0, 45, 2160, 4320):
        assert kadv.dauer_text(m) == kern_dl.dauer_text(m)


# ── 3. Deadline in C, A, B ─────────────────────────────────────────────
def test_c_deadline_ist_linie_ueber_dem_block_ohne_bahn():
    termine = [{"day": FR, "label": "Lernen", "time": "14:00", "ende": "18:00"},
               _dl(time="16:00")]
    with uhr.gestellt(JETZT):
        zeilen = ka.ansicht_c(daten(termine=termine), 130, 36)
    tx = [text(z) for z in zeilen]
    k = next(i for i, z in enumerate(tx) if "⚑16:00 Analy" in z)
    assert tx[k].startswith("│16:00")                   # die Zeile der Uhrzeit
    assert "━" * kdl.LINIE_MIN in tx[k]                 # die Linie bleibt sichtbar
    assert "Lernen" in tx[k - 4]                        # Block darunter bleibt
    # keine Bahn: der Block ist so breit wie ohne Deadline
    ohne = [text(z) for z in ka.ansicht_c(daten(termine=termine[:1]), 130, 36)]
    assert tx[k - 1] == ohne[k - 1] and tx[k + 1] == ohne[k + 1]
    assert not any("Analysis" in z for z in tx[2:4])   # nicht in der Ganztags-Zone
    rollen = {r for _ch, r in zellen(zeilen[k]) if _ch in "⚑━"}
    assert rollen <= {"k_dl1", "k_dl1_inv"}             # 2½ Tage vor 3 Tagen Vorwarnung


def test_c_deadline_ausserhalb_am_rand_und_gewaehlt():
    termine = [_dl(time="23:59"), _dl(time="06:00", label="Frueh-Abgabe")]
    d = daten(termine=termine)
    with uhr.gestellt(JETZT):
        tx = [text(z) for z in ka.ansicht_c(d, 130, 36)]
        assert "▼23:59 Analy" in tx[-2]                  # unterer Rand
        assert "▲06:00 Frueh" in tx[2]                    # oberer Rand
        sel = next(e for e in d["days"][FR] if e["time"] == "23:59")
        zeilen = ka.ansicht_c(d, 130, 36, auswahl={"tag": FR, "roh": sel})
    akz = ka.ROLLE["a_akzent"] + ka.INV
    assert any("23:59 Analy" in t for z in zeilen for t, r in z if r == akz)


def test_c_neon_als_flaeche_und_uncommitted_leise():
    with uhr.gestellt(datetime(2026, 10, 23, 20, 0)):          # 4 h davor: Neon
        z = next(z for z in ka.ansicht_c(daten(termine=[_dl(time="20:00")]), 130, 36)
                 if "Analy" in text(z))
        assert any(r == "k_dl3_inv" and "Analy" in t for t, r in z)
        z = next(z for z in ka.ansicht_c(daten(termine=[_dl(time="20:00", label="HÜ",
                                                             layer="uncommitted")]),
                                         130, 36) if "HÜ" in text(z))
        assert {r for t, r in z if "HÜ" in t} == {"k_dl3_blass"} and "╍" in text(z)


def test_a_und_b_eigene_form():
    d = daten("month", termine=[_dl()])
    with uhr.gestellt(JETZT):
        a = ka.ansicht_a(d, 120, 40, auswahl={"tag": REF})
        z = next(z for z in a if "Analysis" in text(z))
        assert "⚑ 23:59 Analysis HÜ · in 2 T" in text(z)
        assert any(r == "k_dl1" for _t, r in z)
        b = ka.ansicht_b(d, 130, 44)
        z = next(z for z in b if "Analysis" in text(z))
        assert "⚑23:59 Analysis" in text(z) and any(r == "k_dl1" for _t, r in z)


def test_vorbei_grau():
    with uhr.gestellt(datetime(2026, 10, 24, 9, 0)):
        z = next(z for z in ka.ansicht_a(daten("month", termine=[_dl()]), 120, 40,
                                         auswahl={"tag": REF}) if "Analysis" in text(z))
    assert "vorbei" in text(z) and any(r == "k_dlx" for _t, r in z)


# ── 4. Formular: Advanced → Typ deadline, feste Plätze ─────────────────
TAG = datetime.fromisoformat(FR).date()


def _feld(f, name):
    return next(x for x in f.felder if x.name == name)


def _deadline_waehlen(f, vorwarnung=None):
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)                                   # Enter: Fenster advanced
    f.taste(curses.KEY_LEFT)                      # normal → deadline (rückwärts)
    assert f.box.typ == kadv.DEADLINE
    if vorwarnung is not None:
        f.box.i = f.box.reihen().index("vorwarnung")
        f.box.taste(21)                           # Strg-U
        for ch in vorwarnung:
            f.box.taste(ord(ch))
    f.taste(STRG_S)
    assert f.box is None


def test_formular_deadline_feste_plaetze_und_gedaempft():
    f = kw.formular_neu(TAG, TAG)
    vorher = [b for b, *_r in f.zeilen()]
    f.felder[0].text = "Analysis HÜ"
    _deadline_waehlen(f, "1d12h")
    zeilen = {b: w for b, w, _a, _h in f.zeilen()}
    assert [b for b, *_r in f.zeilen()] == vorher
    assert zeilen["Bis"] == zeilen["Ganztägig"] == zeilen["Letzter Tag"] == "—"
    assert zeilen["Von"] == ""
    assert f.taste(STRG_S) == "fertig", f.fehler      # Von leer = 23:59
    (_m, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/entry"
    assert (body["time"], body["typ"], body["vorwarnung"]) == ("23:59", "deadline", 2160)
    assert "ende" not in body


def test_formular_deadline_woechentlich_bleibt_serie():
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Abgabe"
    _feld(f, "von").text = "12:00"
    _feld(f, "wied").wahl = _feld(f, "wied").optionen.index("täglich")
    _feld(f, "wbis").text = "30.10.2026"
    _deadline_waehlen(f)
    assert f.taste(STRG_S) == "fertig", f.fehler
    (_m, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/routine" and body["typ"] == "deadline"


def test_advanced_vorwarnung_kaputt_wird_abgelehnt():
    box = kadv.Advanced(kadv.wert_von({}))
    box.taste(curses.KEY_LEFT)
    box.i = box.reihen().index("vorwarnung")
    box.taste(21)
    for ch in "bald":
        box.taste(ord(ch))
    assert box.taste(STRG_S) == "weiter" and "vorwarnung" in box.fehler
    spanne = kadv.Advanced(kadv.wert_von({}), typen=kadv.TYPEN_SPANNE)
    assert "vorwarnung" not in spanne.reihen()
    for _ in range(3):
        spanne.taste(curses.KEY_RIGHT)
        assert spanne.typ != kadv.DEADLINE


def test_bearbeiten_reihenfolge_der_typ_aufrufe():
    roh = {"label": "Kino", "time": "19:00", "ende": "21:00", "kennung": "k1",
           "layer": "termine"}
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    _deadline_waehlen(f)
    assert f.taste(STRG_S) == "fertig", f.fehler
    pfade = [(m, p) for m, p, _b in f.plan()["aufrufe"]]
    assert pfade == [("PUT", "/api/calendar/eintrag"), ("POST", "/api/calendar/typ")]
    assert f.plan()["aufrufe"][0][2]["new"]["ende"] == ""     # Ende fällt VORHER weg
    # zurück zu normal: der Typ-Aufruf kommt ZUERST (sonst lehnt der Kern das Ende ab)
    roh = {"label": "Analysis HÜ", "time": "23:59", "typ": "deadline", "vorwarnung": 4320,
           "kennung": "k2", "layer": "termine"}
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    assert _feld(f, "bis").aktiv(f.roh_werte()) is False
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    f.taste(curses.KEY_RIGHT)                                 # deadline → normal
    f.taste(STRG_S)
    _feld(f, "von").text = "19:00"
    _feld(f, "bis").text = "+1h"
    assert f.taste(STRG_S) == "fertig", f.fehler
    aufrufe = f.plan()["aufrufe"]
    assert aufrufe[0][1] == "/api/calendar/typ" and aufrufe[0][2]["typ"] == "normal"
    assert aufrufe[1][2]["new"]["ende"] == "20:00"


def test_kopie_und_details():
    roh = {"label": "Analysis HÜ", "time": "23:59", "typ": "deadline", "vorwarnung": 2160,
           "layer": "termine"}
    assert kw.kopie(roh)["typ"] == "deadline" and kw.kopie(roh)["vorwarnung"] == 2160
    with uhr.gestellt(JETZT):
        z = kw.details(roh, TAG)
    assert "Deadline 23:59 · in 2 T" in z and "Vorwarn. 1d12h vorher" in z
