"""
Kalender-Formular: feste Plätze und Ganztägig über Advanced hinweg.

Sasha, 18.10.2026:
1. „ich hab stylebox gemacht auf nen ganztag termin und dann … stand da
   uhrzeit fehlt weil es nich mehr als ganztag selektierbar war" — die
   Bearbeiten-Kästen einer Serie hatten kein Feld „Ganztägig", „Von" war
   Pflicht.
2. „wenn ganztag is und dann eine wiederholung eingestellt wird dann shiftet
   sich die box … das sollte eigentlich nie passieren" — Felder wechseln nie
   den Platz, der Kasten ändert seine Höhe nicht; was nicht gilt, steht
   gedämpft („—") und wird übersprungen.
Reine Logik — ohne Terminal und ohne Backend.
"""
import curses
from datetime import date

from tui.ansichten import kalender_advanced as ka
from tui.ansichten import kalender_phasen as kp
from tui.ansichten import kalender_werkzeuge as kw

TAG = date(2026, 10, 7)          # Mittwoch
TAB, ENTER, ESC, STRG_S = 9, 10, 27, 19


def _feld(f, name):
    return next(x for x in f.felder if x.name == name)


def _setze(f, name, wert):
    x = _feld(f, name)
    x.wahl = x.optionen.index(wert)


def _plaetze(f):
    return [b for b, *_r in f.zeilen()]


def _stylebox_und_zurueck(f):
    """Advanced → Stylebox → Rahmen ändern → nehmen → Fenster übernehmen."""
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(ENTER)
    assert f.box is not None
    f.taste(curses.KEY_DOWN)                       # Typ normal: ↓ = Stylebox
    assert f.box.reihe == "stil"
    f.taste(ENTER)
    f.taste(curses.KEY_RIGHT)
    f.taste(ENTER)                                 # Stylebox: nehmen
    assert f.taste(STRG_S) == "weiter" and f.box is None


# ── 2: feste Plätze ────────────────────────────────────────────────────
def test_feldpositionen_aendern_sich_nicht_beim_umschalten_von_ganztaegig_und_wiederholung():
    f = kw.formular_neu(TAG, TAG)
    plaetze = _plaetze(f)
    assert len(plaetze) == len(f.felder)           # alle Felder, immer
    for ganz in ("nein", "ja"):
        for wied in kw.WIEDERHOLUNG:
            _setze(f, "ganz", ganz)
            _setze(f, "wied", wied)
            assert _plaetze(f) == plaetze, (ganz, wied)
    # ganztägig + wöchentlich: Uhrzeit und Letzter Tag gelten nicht → „—"
    _setze(f, "ganz", "ja")
    _setze(f, "wied", "wöchentlich")
    werte = {b: w for b, w, *_r in f.zeilen()}
    assert werte["Von"] == werte["Bis"] == werte["Letzter Tag"] == kw.NICHT_AKTIV
    assert werte["An Tagen"] == "" and werte["Abstand"] == "1"
    gilt = dict(zip([x.name for x in f.felder], f.gilt()))
    assert not gilt["von"] and not gilt["letzter"] and gilt["wtage"]
    # „Letzter Tag" steht direkt unter „Tag", „Tage" gibt es nicht mehr
    assert plaetze[1:4] == ["Tag", "Letzter Tag", "Ganztägig"] and "Tage" not in plaetze
    # keine eigene Zeile „Name der Gruppe": „eigene" klappt in der Zeile auf
    assert "Name der Gruppe" not in plaetze
    _setze(f, "gruppe", "eigene")
    assert _plaetze(f) == plaetze


def test_tab_ueberspringt_was_nicht_gilt_und_landet_wieder_am_selben_platz():
    f = kw.formular_neu(TAG, TAG)
    f.i = [x.name for x in f.felder].index("ganz")
    f.taste(curses.KEY_UP)
    assert f.feld.name == "datum"                  # ganztägig nein: Letzter Tag übersprungen
    f.taste(TAB)
    f.taste(curses.KEY_RIGHT)                      # ganztägig: ja
    f.taste(curses.KEY_UP)
    assert f.feld.name == "letzter"                # gilt jetzt
    f.taste(TAB)
    f.taste(TAB)
    assert f.feld.name == "wied"                   # Von/Bis übersprungen
    f.taste(curses.KEY_RIGHT)                      # täglich: Letzter Tag gilt nicht mehr
    f.taste(TAB)
    assert f.feld.name == "alle"
    f.taste(TAB)
    assert f.feld.name == "wbis"                   # An Tagen nur bei wöchentlich
    for _ in range(3):                             # wbis → alle → wied → ganz
        f.taste(curses.KEY_UP)
    assert f.feld.name == "ganz"                   # ↑ überspringt Bis/Von
    f.taste(curses.KEY_UP)
    assert f.feld.name == "datum"                  # mit Wiederholung: Letzter Tag nicht
    # der Platz des Feldes in der Liste ist der, auf dem es steht
    assert [a for _b, _w, a, _h in f.zeilen()].index(True) == \
        [x.name for x in f.felder].index("datum")


def test_was_nicht_gilt_wird_beim_speichern_ignoriert():
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Urlaub"
    _setze(f, "ganz", "ja")
    _feld(f, "von").text = "quatsch"               # gilt nicht → kein Fehler
    assert f.taste(STRG_S) == "fertig"
    assert "von" not in f.antworten


def test_advanced_zeile_liste_bleibt_stehen():
    box = ka.Advanced(ka.wert_von({}))
    reihen = [b for b, *_r in box.zeilen()]
    # „Vorwarnung" (Typ deadline, 20.10.2026) steht ebenfalls immer da
    # „Soll" (Soll-Zeit einer Deadline, 24.10.2026) ebenso
    assert reihen == ["Typ", "Liste", "Vorwarnung", "Soll", "Stylebox", "Status"]
    assert box.zeilen()[1][1] == "—" and box.zeilen()[2][1] == "—" and box.zeilen()[3][1] == "—"
    assert box.gilt() == [True, False, False, False, True, True]
    box.taste(curses.KEY_DOWN)
    assert box.reihe == "stil"                     # Liste und Vorwarnung übersprungen
    box.taste(curses.KEY_UP)
    box.taste(curses.KEY_RIGHT)                    # Typ liste
    assert [b for b, *_r in box.zeilen()] == reihen
    box.taste(curses.KEY_DOWN)
    assert box.reihe == "liste"


def test_phasen_formular_feste_plaetze():
    f = kp.formular_phase(None, [{"schluessel": "s", "name": "Schlaf"}], TAG)
    plaetze = _plaetze(f)
    for opt in _feld(f, "wied").optionen:
        _setze(f, "wied", opt)
        assert _plaetze(f) == plaetze


# ── 1: Ganztägig über Advanced → Stylebox hinweg ──────────────────────
def test_neu_ganztaegig_stylebox_zurueck_speichern_ohne_uhrzeit():
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Urlaub"
    _setze(f, "ganz", "ja")
    _stylebox_und_zurueck(f)
    assert _feld(f, "ganz").roh() == "ja"
    assert f.taste(STRG_S) == "fertig", f.fehler
    (_m, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/entry" and "time" not in body and body["stil"]


def test_bearbeiten_ganztaegig_stylebox_zurueck_speichern_ohne_uhrzeit():
    roh = {"day": "2026-10-07", "label": "Urlaub", "kennung": "k-u", "layer": "termine"}
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    assert _feld(f, "ganz").roh() == "ja"
    _stylebox_und_zurueck(f)
    assert _feld(f, "ganz").roh() == "ja"
    assert f.taste(STRG_S) == "fertig", f.fehler
    aufrufe = f.plan()["aufrufe"]
    assert aufrufe[0][2]["new"]["time"] == ""
    assert any(p == "/api/calendar/stil" for _m, p, _b in aufrufe)


def test_ganztaegige_serie_bearbeiten_hat_ganztaegig_und_speichert_ohne_uhrzeit():
    roh = {"day": "2026-10-07", "label": "Gym", "kennung": "k-g", "layer": "termine",
           "recurring": True, "rrule": "FREQ=WEEKLY;BYDAY=WE"}
    d = kw.formular_bearbeiten(roh, TAG, TAG)
    d.taste(ord("a"))                              # alle
    f = d.plan()["weiter"]
    assert _feld(f, "ganz").roh() == "ja"          # vorher: kein Feld, Von Pflicht
    _stylebox_und_zurueck(f)
    assert _feld(f, "ganz").roh() == "ja"
    assert f.taste(STRG_S) == "fertig", f.fehler   # vorher: „uhrzeit fehlt"
    (_m, pfad, body) = f.plan()["aufrufe"][0]
    assert pfad == "/api/calendar/routine" and body["new"]["time"] == ""
    # nur dieser Tag: ebenfalls ganztägig, ohne Uhrzeit speicherbar
    d = kw.formular_bearbeiten(roh, TAG, TAG)
    d.taste(ord("t"))
    f = d.plan()["weiter"]
    assert _feld(f, "ganz").roh() == "ja"
    assert f.taste(STRG_S) == "fertig", f.fehler
    assert "time" not in f.plan()["aufrufe"][0][2]["new"]


def test_serie_mit_uhrzeit_ganztaegig_umschalten_loescht_die_zeit():
    roh = {"day": "2026-10-07", "label": "Geige", "time": "18:00", "ende": "19:00",
           "kennung": "k-g", "layer": "termine", "recurring": True,
           "rrule": "FREQ=WEEKLY;BYDAY=WE"}
    f = kw.formular_bearbeiten(roh, TAG, TAG, fokus="wied")
    assert _feld(f, "ganz").roh() == "nein"
    _setze(f, "ganz", "ja")
    assert f.taste(STRG_S) == "fertig", f.fehler
    neu = f.plan()["aufrufe"][0][2]["new"]
    assert neu["time"] == "" and neu["ende"] == ""


# ── „Letzter Tag" statt „Tage" (20.10.2026) ───────────────────────────
# Sasha: „diese ‚tage'-Option ist etwas random, also unklar, was es macht,
# und wie hinplatziert". Jetzt ein Datum direkt unter „Tag".
def test_letzter_tag_leer_ist_ein_tag_spaeter_ist_spanne_frueher_ist_fehler():
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Urlaub"
    _setze(f, "ganz", "ja")
    assert f.taste(STRG_S) == "fertig", f.fehler
    (_m, pfad, _b), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/entry"
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Urlaub"
    _setze(f, "ganz", "ja")
    _feld(f, "letzter").text = "06.10.2026"
    assert f.taste(STRG_S) == "weiter" and f.fehler == "letzter tag vor dem tag"
    assert f.feld.name == "letzter"
    _feld(f, "letzter").text = "10.10.2026"
    assert f.taste(STRG_S) == "fertig", f.fehler
    (_m, pfad, body), = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/spanne" and (body["von"], body["bis"]) == \
        ("2026-10-07", "2026-10-10")


def test_letzter_tag_gilt_nur_ganztaegig_ohne_wiederholung():
    f = kw.formular_neu(TAG, TAG)
    f.felder[0].text = "Kurs"
    _feld(f, "von").text = "10:00"
    _feld(f, "letzter").text = "quatsch"           # gilt nicht → ignoriert
    assert f.taste(STRG_S) == "fertig", f.fehler
    assert "letzter" not in f.antworten


def test_bearbeiten_ganztaegig_mit_letztem_tag_wird_spanne():
    roh = {"day": "2026-10-07", "label": "Urlaub", "kennung": "k-u", "layer": "termine"}
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    assert _feld(f, "letzter").text == ""
    _feld(f, "letzter").text = "09.10.2026"
    assert f.taste(STRG_S) == "fertig", f.fehler
    aufrufe = f.plan()["aufrufe"]
    assert aufrufe[0][1] == "/api/calendar/spanne" and aufrufe[0][2]["bis"] == "2026-10-09"
    assert aufrufe[-1][:2] == ("DELETE", "/api/calendar/eintrag")


def test_serien_kaesten_haben_keinen_letzten_tag():
    roh = {"day": "2026-10-07", "label": "Gym", "kennung": "k-g", "layer": "termine",
           "recurring": True, "rrule": "FREQ=WEEKLY;BYDAY=WE"}
    for t in ("a", "t"):
        d = kw.formular_bearbeiten(roh, TAG, TAG)
        d.taste(ord(t))
        assert all(x.name != "letzter" for x in d.plan()["weiter"].felder)
