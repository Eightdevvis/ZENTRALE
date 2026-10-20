"""
Gruppen in der TUI (tui/ansichten/kalender_gruppen.py, Formularfeld).

Sasha, 10.10.2026: „in der monatsansicht seh ich einfach lieber uni uni uni
statt jeden tag welche fächer genau, dafür ist die wochenansicht" — gewählt:
„Uni 08:30–16:00". Geprüft: B fasst je Tag zusammen, A/C nicht; Tab wählt die
Gruppe, Enter zeigt ihre Glieder; das Formular schickt die Gruppe mit. Dazu:
die TUI-Kopie von titel_schluessel rechnet wie der Kern (core/kalender_kategorie.py).
"""
import curses
import os
import sys
from datetime import date

import pytest

from tui.ansichten import kalender_ansichten as ka
from tui.ansichten import kalender_gruppen as kg
from tui.ansichten import kalender_werkzeuge as kw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import kalender_kategorie  # noqa: E402

TAG = date(2026, 10, 7)
HEUTE = date(2026, 10, 7)


def _e(label, t, e, kat="uni", **mehr):
    return {"label": label, "time": t, "ende": e, "layer": "termine", "kategorie": kat,
            "kennung": "k-" + label, **mehr}


def _daten():
    tage = {TAG.isoformat(): [
        _e("Analysis I", "08:30", "10:00"),
        _e("Allgemeine Chemie", "12:15", "13:45"),
        _e("Parkour", "18:00", "19:00", kat="keine"),
        _e("Theoretische Physik", "14:00", "16:00"),
        _e("Chor", "19:30", "21:00", kat="custom", kategorie_name="Musik"),
    ]}
    return {"today": TAG.isoformat(), "ref": TAG.isoformat(), "start": "2026-09-28",
            "end": "2026-11-01", "first": "2026-10-01", "last": "2026-10-31", "days": tage}


def _text(zeilen):
    return "\n".join("".join(t for t, _r in z) for z in zeilen)


def test_b_fasst_gleiche_gruppe_zusammen():
    ts = kw.eintraege(_daten(), TAG, False, monat=True)
    assert [t["label"] for t in ts] == ["Uni", "Parkour", "Musik"]
    uni = ts[0]
    assert (uni["start"], uni["ende"]) == (8 * 60 + 30, 16 * 60)
    assert [g["label"] for g in uni["roh"]["glieder"]] == [
        "Analysis I", "Allgemeine Chemie", "Theoretische Physik"]
    # A und C behalten jedes Fach
    assert len(kw.eintraege(_daten(), TAG, False)) == 5


def test_b_zeigt_uni_von_bis():
    txt = _text(ka.ansicht_b(_daten(), 150, 40))
    assert "08:30–16:00 Uni" in txt and "Analysis" not in txt
    assert "Parkour" in txt


def test_gruppe_hat_eigene_feste_farbe():
    tab = {}
    d = _daten()
    ka.farben_vergeben(d, tab)
    assert "gruppe:uni" in tab
    ts = kw.eintraege(d, TAG, False, monat=True)
    assert ka._rolle(ts[0]) == ka.TITEL_FARBEN[tab["gruppe:uni"]]


def test_auswahl_trifft_die_gruppe():
    d = _daten()
    sel = kw.eintraege(d, TAG, False, monat=True)[0]["roh"]
    neu = kw.eintraege(d, TAG, False, monat=True)[0]["roh"]
    assert sel is not neu and kg.selbe(neu, sel)          # neu gebaut, gleich gemeint
    zeilen = ka.ansicht_b(d, 150, 40, auswahl={"tag": TAG.isoformat(), "roh": sel})
    gewaehlt = [t for z in zeilen for t, r in z if r == "k_akzent_inv" and "Uni" in t]
    assert gewaehlt, "die Gruppe steht in der Akzentfläche"


def test_enter_zeigt_glieder():
    roh = kw.eintraege(_daten(), TAG, False, monat=True)[0]["roh"]
    z = kw.details_gruppe(roh, TAG)
    assert z[0].startswith("Uni") and any("Analysis I" in s for s in z)


def test_text_wird_eng_kuerzer():
    t = kw.eintraege(_daten(), TAG, False, monat=True)[0]
    assert kg.text(t, 20) == "08:30–16:00 Uni"
    assert kg.text(t, 12) == "08:30–16 Uni"
    assert kg.text(t, 9) == "08:30 Uni"
    assert kg.text(t, 4) == "Uni"


def test_titel_schluessel_kopie_rechnet_wie_der_kern():
    assert ka.KURZFORMEN == kalender_kategorie.KURZFORMEN
    for t in ("Analysis I @ HS 1", "ExPhy-Übung", "exphy", "Theoretische Physik Ia",
              "Allgemeine Chemie für Nebenfächler (Mo)", "", None, "  Chor  ", "A/B"):
        assert ka.titel_schluessel(t) == kalender_kategorie.titel_schluessel(t), t


# ── Formular: Feld „Gruppe" ────────────────────────────────────────────
def _feld(f, name):
    return next(x for x in f.felder if x.name == name)


def _waehle(f, name, wert):
    x = _feld(f, name)
    x.wahl = x.optionen.index(wert)


def test_neuer_termin_mit_gruppe():
    f = kw.formular_neu(TAG, HEUTE)
    _feld(f, "titel").text = "Klausur"
    _feld(f, "von").text = "10:00"
    _waehle(f, "gruppe", "Uni")
    assert f.taste(10) == "fertig"
    (_m, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/entry" and body["kategorie"] == "uni"


def test_neue_routine_mit_eigener_gruppe():
    f = kw.formular_neu(TAG, HEUTE)
    _feld(f, "titel").text = "Chor"
    _feld(f, "von").text = "19:00"
    _waehle(f, "wied", "wöchentlich")
    _waehle(f, "gruppe", "eigene")
    assert f.taste(10) == "weiter" and f.fehler == "name fehlt"
    _feld(f, "gruppe").text = "Musik"
    assert f.taste(10) == "fertig"
    (_m, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/routine"
    assert (body["kategorie"], body["kategorie_name"]) == ("custom", "Musik")


def test_aendern_setzt_gruppe_per_kennung():
    roh = _e("Analysis I", "08:30", "10:00", kat="keine")
    f = kw.formular_bearbeiten(roh, TAG, HEUTE)
    assert _feld(f, "gruppe").roh() == "keine"
    _waehle(f, "gruppe", "Uni")
    assert f.taste(10) == "fertig"
    aufrufe = f.plan()["aufrufe"]
    assert aufrufe[-1] == ("POST", "/api/calendar/kategorie",
                           {"kennung": "k-Analysis I", "kategorie": "uni"})
    # unverändert → kein Aufruf
    f = kw.formular_bearbeiten(_e("Analysis I", "08:30", "10:00"), TAG, HEUTE)
    assert f.taste(10) == "fertig"
    assert all(p != "/api/calendar/kategorie" for _m, p, _b in f.plan()["aufrufe"])


def test_nur_dieser_tag_hat_keine_gruppe():
    roh = _e("Analysis I", "08:30", "10:00", recurring=True, rrule="FREQ=WEEKLY;BYDAY=WE")
    d = kw.formular_bearbeiten(roh, TAG, HEUTE)
    d.taste(ord("t"))
    form = d.plan()["weiter"]
    assert all(f.name != "gruppe" for f in form.felder)


def test_kopie_nimmt_gruppe_mit():
    k = kw.kopie(_e("Chor", "19:30", "21:00", kat="custom", kategorie_name="Musik"))
    assert (k["kategorie"], k["kategorie_name"]) == ("custom", "Musik")
    assert "kategorie" not in kw.kopie(_e("Parkour", "18:00", None, kat="keine"))


@pytest.fixture(autouse=True)
def _namen():
    alt = dict(kg.NAMEN)
    yield
    kg.NAMEN.clear()
    kg.NAMEN.update(alt)


def test_namen_vom_backend():
    kg.namen_setzen([{"schluessel": "uni", "name": "Uni"}, {"schluessel": "sport", "name": "Sport"},
                     {"schluessel": "keine", "name": "keine Gruppe"},
                     {"schluessel": "custom", "name": "eigener Name"}])
    assert kg.NAMEN == {"uni": "Uni", "sport": "Sport"}
    assert kw._gruppe_optionen() == ("keine", "Uni", "Sport", "eigene")
    kg.namen_setzen(None)                   # Backend weg: Namen bleiben
    assert "sport" in kg.NAMEN


# ── „eigene" klappt in derselben Zeile auf (20.10.2026) ────────────────
# Sasha: „name der gruppe muss in bearbeitung und erstellung nicht angezeigt
# werden, einfach so wenn man neu anlegt dass sich das dann aufklappt".
def _zeile(f, beschriftung="Gruppe"):
    return next(w for b, w, *_r in f.zeilen() if b == beschriftung)


def _auf_gruppe(f):
    f.i = [x.name for x in f.felder].index("gruppe")


def test_eigene_gruppe_tippt_in_derselben_zeile():
    f = kw.formular_neu(TAG, HEUTE)
    assert all(x.name != "gruppe_name" for x in f.felder)
    _feld(f, "titel").text = "Chor"
    _feld(f, "von").text = "19:00"
    _auf_gruppe(f)
    assert f.ansicht() == "wahl" and _zeile(f) == "‹ keine ›"
    f.taste(curses.KEY_LEFT)                      # keine → (rückwärts) eigene
    assert f.ansicht() == "wahltext" and _zeile(f) == "‹ eigene: _ ›"
    for b in "Mü sik".encode("utf-8"):            # Leertaste und Umlaute tippen
        f.taste(b)
    assert _zeile(f) == "‹ eigene: Mü sik_ ›"
    for _ in range(5):                            # „ü sik“ weg
        f.taste(curses.KEY_BACKSPACE)
    f.taste(ord("u"))
    assert _feld(f, "gruppe").text == "Mu"
    f.taste(curses.KEY_LEFT)                      # ← wechselt weiter die Option
    vorige = _feld(f, "gruppe").optionen[-2]
    assert _feld(f, "gruppe").roh() == vorige and _zeile(f) == "‹ %s ›" % vorige
    f.taste(curses.KEY_RIGHT)                     # zurück: der Name ist noch da
    assert _zeile(f) == "‹ eigene: Mu_ ›"
    f.taste(9)
    assert f.feld.name == "advanced"              # Tab verlässt die Zeile
    assert _zeile(f) == "‹ eigene: Mu ›"
    assert f.taste(19) == "fertig", f.fehler                # Strg-S
    (_m, _p, body), = f.plan()["aufrufe"]
    assert (body["kategorie"], body["kategorie_name"]) == ("custom", "Mu")


def test_eigene_gruppe_ohne_namen_fehler_und_fokus_bleibt():
    f = kw.formular_neu(TAG, HEUTE)
    _feld(f, "titel").text = "Chor"
    _feld(f, "von").text = "19:00"
    _waehle(f, "gruppe", "eigene")
    _feld(f, "gruppe").text = "   "
    assert f.taste(10) == "weiter" and f.fehler == "name fehlt"
    assert f.feld.name == "gruppe" and f.ansicht() == "wahltext"
    f.taste(ord("X"))
    assert f.fehler == ""                         # wer tippt, sieht den Fehler nicht mehr


def test_bearbeiten_zeigt_eigenen_namen_in_der_zeile():
    roh = _e("Probe", "19:00", "21:00", kat="custom", kategorie_name="Musik")
    f = kw.formular_bearbeiten(roh, TAG, HEUTE)
    assert _zeile(f) == "‹ eigene: Musik ›"
    assert f.taste(10) == "fertig"                # unverändert → kein Aufruf
    assert all(p != "/api/calendar/kategorie" for _m, p, _b in f.plan()["aufrufe"])
    f = kw.formular_bearbeiten(roh, TAG, HEUTE)
    _auf_gruppe(f)
    f.taste(curses.KEY_BACKSPACE)
    assert f.taste(10) == "fertig"
    assert f.plan()["aufrufe"][-1] == ("POST", "/api/calendar/kategorie", {
        "kennung": "k-Probe", "kategorie": "custom", "kategorie_name": "Musi"})


def test_serie_alle_und_spanne_haben_die_eine_zeile():
    serie = _e("Chor", "19:00", "21:00", kat="custom", kategorie_name="Musik",
               recurring=True, rrule="FREQ=WEEKLY;BYDAY=WE")
    spanne = {"label": "Reise", "von": "2026-10-07", "bis": "2026-10-09", "layer": "termine",
              "spanning": True, "kategorie": "custom", "kategorie_name": "Fern", "kennung": "k-r"}
    for roh, name in ((serie, "Musik"), (spanne, "Fern")):
        d = kw.formular_bearbeiten(roh, TAG, HEUTE)
        d.taste(ord("a"))
        f = d.plan()["weiter"]
        assert [x.name for x in f.felder].count("gruppe") == 1
        assert all(x.name != "gruppe_name" for x in f.felder)
        assert _zeile(f) == "‹ eigene: %s ›" % name
