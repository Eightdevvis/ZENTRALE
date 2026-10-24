"""
Soll-Zeit einer Deadline und der Modus Muss | Soll (24.10.2026).

Sasha: „eigene deadlines hinzufügen wird mir zu wirr … KEINE DOPPELTEN
deadlines im kalender, ein modus, in dem man soll und muss umschalten kann."
EIN Eintrag: `time` = Muss (die echte Abgabe), `soll_abstand` (Minuten ≤ 0)
= die eigene Wunsch-Abgabe davor. Geprüft:
  * Kern: Validierung (SOLL-UNGUELTIG, SOLL-NACH-MUSS, nur bei deadline),
    abgelehnt = nichts geschrieben; .ics X-ZENTRALE-SOLL hin und zurück;
    /api/calendar liefert soll_abstand + soll_zeit; Routen setzen es;
  * Alarm und Imprint nennen beide (Muss bleibt die Wahrheit);
  * TUI: Modus Soll zeichnet an der Soll-Zeile, Muss an der Muss-Zeile, nie
    beide; Leuchten relativ zur aktiven Zeit; Taste S, Hot Reload;
  * Formular: Zeile „Soll" (feste Plätze), „Di 18:00" oder „-2d18h".
Uhr über core/uhr.py gestellt (datumsunabhängig).
"""
import curses
import os
import sys
import types
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest
from icalendar import Calendar

import kalender
import kalender_deadline as kd
import kalender_ics_abbildung as abb
import kalender_kennung as kk
import uhr
from kalender_fehler import KalenderAbgelehnt
from tui.ansichten import kalender_advanced as kadv
from tui.ansichten import kalender_ansichten as ka
from tui.ansichten import kalender_beispiel as kb
from tui.ansichten import kalender_bedienung as kbed
from tui.ansichten import kalender_deadline as kdl
from tui.ansichten import kalender_werkzeuge as kw

FR = date(2026, 10, 30)                  # Freitag: Muss 12:00
DI = "2026-10-27"                        # Soll Di 18:00 = −2d18h
SOLL = -(2 * 1440 + 18 * 60)
STRG_S = 19


# ── Kern: Prüfen und .ics ──────────────────────────────────────────────
def test_soll_pruefen():
    assert kd.soll_pruefen("-2d18h") == SOLL and kd.soll_pruefen(SOLL) == SOLL
    assert kd.soll_pruefen(0) == 0 and kd.soll_pruefen("-14h15m") == -855
    for wert, code in (("+1h", "SOLL-NACH-MUSS"), (60, "SOLL-NACH-MUSS"),
                       ("-30d", "SOLL-UNGUELTIG"), ("bald", "SOLL-UNGUELTIG"),
                       (True, "SOLL-UNGUELTIG")):
        with pytest.raises(KalenderAbgelehnt) as e:
            kd.soll_pruefen(wert)
        assert e.value.code == code, wert
    assert kd.soll_text(-8625) == "-5d23h45m"


def test_ics_soll_hin_und_zurueck():
    e = {"label": "Analysis HÜ", "time": "12:00", "typ": "deadline", "vorwarnung": 4320,
         "soll_abstand": SOLL}
    kal = abb.termin_kalender(FR.isoformat(), e, "s1@zentrale")
    roh = kal.to_ical().decode()
    assert "X-ZENTRALE-SOLL:-P2DT18H" in roh and "X-ZENTRALE-EXTRAS" not in roh
    assert abb.lesen(Calendar.from_ical(kal.to_ical()))[0]["daten"] == e
    r = {"label": "TP HÜ", "rrule": "FREQ=WEEKLY;BYDAY=TH", "time": "12:00",
         "seit": "2026-10-22", "typ": "deadline", "vorwarnung": 4320, "soll_abstand": -8625}
    kal = abb.routine_kalender(r, "s2@zentrale")
    assert "X-ZENTRALE-SOLL:-P5DT23H45M" in kal.to_ical().decode()
    assert abb.lesen(Calendar.from_ical(kal.to_ical()))[0]["daten"] == r


# ── Kern mit Speicher ──────────────────────────────────────────────────
@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    return tmp_path


def _stand(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != ".zentrale.lock"}


@pytest.mark.kalender_beide
def test_anlegen_aendern_und_ablehnen(cal):
    assert kalender.add_entry("termine", FR.isoformat(), "Analysis HÜ", time="12:00",
                              typ="deadline", soll_abstand="-2d18h")
    e = kalender.entries_in_range(FR, FR)[FR.isoformat()][0]
    assert (e["soll_abstand"], e["soll_zeit"]) == (SOLL, "2026-10-27T18:00")
    k = kk.alle_eintraege()[0]["kennung"]
    kalender.add_entry("termine", FR.isoformat(), "Kino", time="19:00", ende="21:00")
    kino = next(x["kennung"] for x in kk.alle_eintraege() if x.get("label") == "Kino")
    vorher = _stand(cal)
    for aufruf, code in ((lambda: kk.eintrag_aendern(k, soll_abstand=60), "SOLL-NACH-MUSS"),
                         (lambda: kk.typ_setzen(k, "deadline", soll_abstand="-40d"),
                          "SOLL-UNGUELTIG"),
                         (lambda: kk.eintrag_aendern(kino, soll_abstand=-60), "UNBEKANNTES-FELD"),
                         (lambda: kalender.add_entry("termine", FR.isoformat(), "X",
                                                     time="10:00", soll_abstand=-60),
                          "UNBEKANNTES-FELD")):
        with pytest.raises(KalenderAbgelehnt) as ex:
            aufruf()
        assert ex.value.code == code
    assert _stand(cal) == vorher
    assert kk.typ_setzen(k, "deadline", soll_abstand=-855)["soll_abstand"] == -855
    assert "soll_abstand" not in kk.eintrag_aendern(k, soll_abstand="")
    kk.typ_setzen(k, "deadline", soll_abstand=-60)
    assert "soll_abstand" not in kk.typ_setzen(k, "normal")


@pytest.mark.kalender_beide
def test_routine_jede_woche_und_routen(cal):
    from ui.app import app
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.post("/api/calendar/routine", json={"label": "Analysis HÜ", "freq": "w",
                                              "seit": FR.isoformat(), "time": "12:00",
                                              "typ": "deadline", "soll_abstand": SOLL})
    assert r.status_code == 200, r.get_json()
    k = r.get_json()["kennung"]
    d = c.get("/api/calendar?view=month&ref=2026-11-06").get_json()
    occ = [e for es in d["days"].values() for e in es if e.get("kennung") == k]
    assert [e["soll_zeit"] for e in occ][:2] == ["2026-10-27T18:00", "2026-11-03T18:00"]
    r = c.put("/api/calendar/routine", json={"kennung": k, "new": {"soll_abstand": "-14h15m"}})
    assert r.get_json()["eintrag"]["soll_abstand"] == -855
    r = c.put("/api/calendar/routine", json={"kennung": k, "new": {"soll_abstand": 5}})
    assert r.status_code == 400 and r.get_json()["code"] == "SOLL-NACH-MUSS"
    r = c.post("/api/calendar/typ", json={"kennung": k, "typ": "deadline", "soll_abstand": ""})
    assert "soll_abstand" not in r.get_json()


@pytest.mark.kalender_beide
def test_alarm_und_imprint_nennen_beide(cal):
    kalender.add_entry("termine", FR.isoformat(), "Analysis HÜ", time="12:00",
                       typ="deadline", vorwarnung=1440, soll_abstand=SOLL)
    with uhr.gestellt(datetime(2026, 10, 25, 12, 0)):          # 2½ Tage vor Soll: still
        assert not [a for a in kalender.open_alarms() if a["kind"] == "Deadline"]
    with uhr.gestellt(datetime(2026, 10, 27, 9, 0)):           # 1 Tag vor Soll: Fenster
        dl = [a["text"] for a in kalender.open_alarms() if a["kind"] == "Deadline"]
        assert dl == ["Deadline Analysis HÜ in 3 Tagen "
                      "(Soll: Di 27.10. 18:00, Muss: Fr 30.10. 12:00)"]
        imp = kalender.imprint_for_prompt(tage=4)
        assert ("[deadline] 12:00 Analysis HÜ (in 3 Tagen · Soll: Di 27.10. 18:00, "
                "Muss: Fr 30.10. 12:00)") in imp
        assert "Wunsch-Abgabe" in imp
        import ki_kalender
        e = kalender.entries_in_range(FR, FR)[FR.isoformat()][0]
        assert "Soll -2d18h vor Muss" in ki_kalender._vorkommen_zeile(e, None, FR.isoformat())
    with uhr.gestellt(datetime(2026, 10, 30, 12, 1)):          # Muss vorbei: Schluss
        assert not [a for a in kalender.open_alarms() if a["kind"] == "Deadline"]


# ── TUI: Modus Muss | Soll ─────────────────────────────────────────────
def _dl(**mehr):
    return {"day": FR.isoformat(), "label": "Analysis HÜ", "time": "12:00",
            "typ": "deadline", "vorwarnung": 3 * 1440, "soll_abstand": SOLL, **mehr}


def _daten(modus, termine=None, ref="2026-10-28", spaeter=None):
    d = kb.api_daten("week", ref=ref, heute=ref, termine=termine or [_dl()], routinen=[])
    kdl.modus_anwenden(d, modus, spaeter)
    return d


def _text(z):
    return "".join(t for t, _r in z)


def _c_zeile(d, wort):
    """(Zeile, Spalte) von `wort` in Ansicht C."""
    for y, z in enumerate(ka.ansicht_c(d, 200, 60, jetzt=datetime(2026, 10, 26, 8, 0))):
        if wort in _text(z):
            return y, _text(z).index(wort)
    return None


def test_modus_legt_um_und_zeichnet_nie_doppelt():
    muss, soll = _daten(kdl.MUSS), _daten(kdl.SOLL)
    assert [e["label"] for e in muss["days"][FR.isoformat()]] == ["Analysis HÜ"]
    assert soll["days"][FR.isoformat()] == [] and len(soll["days"][DI]) == 1
    kopie = soll["days"][DI][0]
    assert (kopie["time"], kopie["muss_tag"], kopie["_echt"]["time"]) == ("18:00", "2026-10-30",
                                                                         "12:00")
    for d, zeit in ((muss, "12:00"), (soll, "18:00")):
        zeilen = [_text(z) for z in ka.ansicht_c(d, 200, 60)]
        treffer = [z for z in zeilen if "Analysis" in z]
        assert len(treffer) == 1 and ("⚑ %s Analysis" % zeit) in treffer[0], treffer
    ym, xm = _c_zeile(muss, "Analysis")
    ys, xs = _c_zeile(soll, "Analysis")
    assert ys > ym and xs < xm                        # Di 18:00: weiter links, weiter unten
    assert "· soll" in _text(ka.ansicht_c(soll, 130, 60)[0])
    assert "· muss" in _text(ka.ansicht_b(_daten(kdl.MUSS), 130, 44)[0])


def test_ohne_soll_in_beiden_modi_gleich():
    t = [_dl(soll_abstand=None)]
    a, b = _daten(kdl.MUSS, t), _daten(kdl.SOLL, t)
    assert a["days"] == b["days"]


def test_soll_aus_der_naechsten_woche_kommt_herein():
    """Muss Mo 02.11. liegt hinter der Woche, das Soll (Fr 30.10.) in ihr."""
    naechste = kb.eintraege(date(2026, 11, 2), date(2026, 11, 8),
                            [_dl(day="2026-11-02", soll_abstand=-3 * 1440)], [])
    d = _daten(kdl.SOLL, [{"day": "2026-10-26", "label": "Frei"}], spaeter=naechste)
    assert [e["label"] for e in d["days"][FR.isoformat()]] == ["Analysis HÜ"]


def test_leuchten_relativ_zur_aktiven_zeit():
    jetzt = datetime(2026, 10, 28, 6, 0)              # nach Soll, 54 h vor Muss
    muss = ka._tag_eintraege(_daten(kdl.MUSS), FR.isoformat(), False)[0]
    soll = ka._tag_eintraege(_daten(kdl.SOLL), DI, False)[0]
    assert kdl.stufe(kdl.dl(soll), soll["tag"], jetzt) == kdl.STUFE_VORBEI
    assert kdl.stufe(kdl.dl(muss), muss["tag"], jetzt) == 1
    assert soll["roh"]["time"] == "12:00" and soll["muss_tag"] == FR.isoformat()
    assert "· muss Fr 12:00" in kdl.a_text(soll, jetzt) and "muss" not in kdl.a_text(muss, jetzt)


def _bedienung(daten_je_ref):
    kal = types.SimpleNamespace(z=types.SimpleNamespace(), K={
        "active": True, "ref": "2026-10-28", "stil": "C", "sdata": None, "data": None,
        "showhidden": False, "msg": "", "modus": "muss"})
    bed = kbed.Bedienung(kal)
    bed._katalog = True
    bed._holen = lambda view, ref: kb.api_daten("month", ref=ref.isoformat(),
                                                heute="2026-10-28", termine=daten_je_ref,
                                                routinen=[])
    return bed


def test_taste_s_schaltet_und_werkzeuge_aendern_am_muss_tag():
    bed = _bedienung([_dl()])
    assert ("S", "modus") in [(k, a) for k, a, *_r in kbed._rest()]
    bed.setze_tag(date.fromisoformat(DI))
    assert bed.termine() == []
    bed.aktion_modus("S")
    assert bed.K["modus"] == "soll" and "soll" in bed.W["msg"]
    assert [t["label"] for t in bed.termine()] == ["Analysis HÜ"]
    assert bed.gewaehlt()["time"] == "12:00" and bed.roh_tag() == FR
    assert "Soll     Di 27.10. 18:00" in kw.details(bed.gewaehlt(), bed.roh_tag())
    bed.aktion_modus("S")
    assert bed.K["modus"] == "muss" and bed.termine() == []


def test_hot_reload_nimmt_den_modus_mit():
    from tui.ansichten.kalender import Kalender
    kal = Kalender.__new__(Kalender)
    kal.K = {"stil": "C", "ref": "2026-10-28", "modus": "soll"}
    kal.bedienung = types.SimpleNamespace(tag=lambda: FR, modus=lambda: kal.K["modus"])
    stand = Kalender.stand_fuer_neustart(kal)
    assert stand["modus"] == "soll"
    kal.K = {"modus": "muss"}
    kal.bedienung.setze_tag = lambda *a: None
    Kalender.stand_nach_neustart(kal, {"modus": "soll"})
    assert kal.K["modus"] == "soll"


# ── Formular: Zeile „Soll" ─────────────────────────────────────────────
def test_soll_lesen_wochentag_und_abstand():
    fr12 = (4, 12 * 60)
    assert kadv.soll_lesen("Di 18:00", fr12) == (SOLL, "")
    assert kadv.soll_lesen("di 18", fr12) == (SOLL, "")
    assert kadv.soll_lesen("-2d18h", None) == (SOLL, "")
    assert kadv.soll_lesen("2d18h", None) == (SOLL, "")
    assert kadv.soll_lesen("Fr 12:15", (3, 12 * 60))[0] == -8625     # TP: Fr der Vorwoche
    assert kadv.soll_lesen("Fr 18:00", (4, 14 * 60))[0] == -9840     # PhyProg: Vorwoche
    assert kadv.soll_lesen("Fr 12:00", fr12)[0] == 0                 # an der Muss-Zeit
    assert kadv.soll_lesen("", fr12) == (None, "")
    assert kadv.soll_lesen("Di 18:00", None)[1] and kadv.soll_lesen("+1h", fr12)[1]
    assert kadv.soll_text(SOLL, fr12) == "Di 18:00" and kadv.soll_text(SOLL) == "-2d18h"
    assert kadv.soll_text(-9840, (4, 14 * 60)) == "Fr 18:00"


def _feld(f, name):
    return next(x for x in f.felder if x.name == name)


def test_formular_soll_feste_plaetze_und_body():
    f = kw.formular_neu(FR, FR)
    f.felder[0].text = "Analysis HÜ"
    _feld(f, "von").text = "12:00"
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    box = f.box
    plaetze = [b for b, *_r in box.zeilen()]
    assert dict((b, w) for b, w, *_r in box.zeilen())["Soll"] == "—"   # normal: gedämpft
    box.taste(curses.KEY_LEFT)                                         # → deadline
    assert [b for b, *_r in box.zeilen()] == plaetze
    box.i = box.reihen().index("soll")
    for ch in "Di 18:00":
        box.taste(ord(ch))
    assert "2d18h vor muss" in dict((b, h) for b, _w, _a, h in box.zeilen())["Soll"]
    f.taste(STRG_S)
    assert f.box is None
    assert f.taste(STRG_S) == "fertig", f.fehler
    (_m, pfad, body), = f.plan()["aufrufe"]
    assert (body["typ"], body["soll_abstand"]) == ("deadline", SOLL)


def test_formular_soll_kaputt_bleibt_im_fenster():
    box = kadv.Advanced(kadv.wert_von({}), muss=(4, 720))
    box.taste(curses.KEY_LEFT)
    box.i = box.reihen().index("soll")
    for ch in "+3h":
        box.taste(ord(ch))
    assert box.taste(STRG_S) == "weiter" and box.reihe == "soll" and box.fehler


def test_bearbeiten_aendert_soll_per_typ_aufruf():
    roh = {"label": "Analysis HÜ", "time": "12:00", "typ": "deadline", "vorwarnung": 4320,
           "soll_abstand": SOLL, "kennung": "k1", "layer": "termine"}
    f = kw.formular_bearbeiten(roh, FR, FR)
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    assert f.box.soll == "Di 18:00"                   # vorbelegt als Wochentag
    f.box.i = f.box.reihen().index("soll")
    f.box.taste(21)                                   # Strg-U
    for ch in "Do 20:00":
        f.box.taste(ord(ch))
    f.taste(STRG_S)
    assert f.taste(STRG_S) == "fertig", f.fehler
    typ = [b for _m, p, b in f.plan()["aufrufe"] if p == "/api/calendar/typ"]
    assert typ == [{"kennung": "k1", "typ": "deadline", "vorwarnung": 4320,
                    "soll_abstand": -(16 * 60)}]
    assert kw.kopie(roh)["soll_abstand"] == SOLL
