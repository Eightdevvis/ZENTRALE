"""
Aussehen eines Termins (Feld `stil`, core/stil.py) im Kalender-Kern.

Sasha, 10.10.2026: „Im Terminformular gibt es NUR eine Option ‚Stylebox' …
das Ergebnis wird auf den Termin (seinen Kasten im Kalender) angewendet."
Ein Stil ist ein dict aus CSS-Eigenschaften. In .ics: EINE Zeile
X-ZENTRALE-STIL (CSS-Deklarationsliste, TEXT-escaped) und zusätzlich der
Standard COLOR (RFC 7986, CSS3-Farbname) für andere Kalender. Geprüft gegen
BEIDE Speicher.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_ics_abbildung as abb
import kalender_kennung as kk
import stil

pytestmark = pytest.mark.kalender_beide

TAG = "2026-10-14"
STIL = {"border-style": "double", "border-color": "#ff8800", "background-color": "#202030",
        "color": "#ffffff", "--zentrale-muster": "punkte"}


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_entry("termine", TAG, "Uni", time="08:30", ende="10:00", stil=dict(STIL))
    kalender.add_entry("termine", TAG, "Kino", time="19:00", ende="21:00")
    return tmp_path


def _k(label):
    return next(e["kennung"] for e in kk.alle_eintraege() if e["label"] == label)


def _tag():
    return kalender.entries_in_range(date.fromisoformat(TAG), date.fromisoformat(TAG))[TAG]


def _stand(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != ".zentrale.lock"}


# ── core/stil.py: CSS-Text und Farbnamen ───────────────────────────────
def test_css_text_hin_und_zurueck():
    text = stil.als_css(STIL)
    assert text == ("border-style: double; border-color: #ff8800; background-color: #202030; "
                    "color: #ffffff; --zentrale-muster: punkte")
    assert stil.aus_css(text) == STIL
    # ein ; in Klammern/Anführungszeichen trennt nicht
    assert stil.aus_css('background-image: url("a;b"); color: #000000') == {
        "background-image": 'url("a;b")', "color": "#000000"}
    assert stil.als_css({}) == ""
    with pytest.raises(ValueError):
        stil.aus_css("kaputt ohne doppelpunkt")


def test_css3_namen():
    assert len(stil.CSS3_FARBEN) == 147
    assert stil.css_name("#ff8800") == "darkorange"
    assert stil.css_name("#ffa500") == "orange"          # genau getroffen
    assert stil.css_name("unsinn") is None
    assert stil.hex_aus_name("Orange") == "#ffa500"
    assert stil.hex_aus_name("#FFF") == "#ffffff"
    assert stil.hex_aus_name("nichtda") is None
    assert stil.kastenfarbe({"color": "#111111", "border-color": "#222222"}) == "#222222"
    assert stil.kastenfarbe({}) is None


# ── .ics-Abbildung ─────────────────────────────────────────────────────
def test_ics_hin_und_zurueck_alle_arten():
    e = {"label": "Uni", "time": "08:30", "ende": "10:00", "stil": dict(STIL)}
    kal = abb.termin_kalender(TAG, e, "s1@test")
    text = kal.to_ical().decode()
    assert "COLOR:darkslategray" in text                  # Fläche #202030 → nächster Name
    entfaltet = text.replace("\r\n ", "")
    assert ("X-ZENTRALE-STIL:border-style: double\\; border-color: #ff8800\\; "
            "background-color: #202030\\; color: #ffffff\\; --zentrale-muster: punkte") in entfaltet
    assert "X-ZENTRALE-EXTRAS" not in text
    assert abb.datei_lesen(kal.to_ical())[0]["daten"] == e
    sp = {"label": "Messe", "bis": "2026-10-16", "stil": {"border-style": "dashed"}}
    assert abb.datei_lesen(abb.termin_kalender(TAG, sp, "s2@test").to_ical())[0]["daten"] == sp
    sp_ohne_farbe = abb.termin_kalender(TAG, sp, "s2@test").to_ical()
    assert b"COLOR:" not in sp_ohne_farbe                  # keine Farbe → kein COLOR
    r = {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=MO", "time": "18:00",
         "stil": {"color": "#ff0000"}}
    roh = abb.routine_kalender(r, "s3@test", anker=date(2026, 10, 12)).to_ical()
    assert b"COLOR:red" in roh
    assert abb.datei_lesen(roh)[0]["daten"] == r


def test_ics_nur_color_von_aussen_wird_flaeche():
    roh = abb.termin_kalender(TAG, {"label": "Arzt", "time": "09:00"}, "s4@test").to_ical()
    roh = roh.replace(b"SUMMARY:Arzt\r\n", b"SUMMARY:Arzt\r\nCOLOR:tomato\r\n")
    assert abb.datei_lesen(roh)[0]["daten"]["stil"] == {"background-color": "#ff6347"}


def test_ics_stil_entfernt_alte_farbe_kommt_nicht_zurueck():
    roh = abb.termin_kalender(TAG, {"label": "Uni", "stil": {"color": "#ff0000"}},
                              "s5@test").to_ical()
    neu = abb.termin_kalender(TAG, {"label": "Uni"}, "s5@test")
    zus = abb.zusammenfuehren(roh, neu, "s5@test")
    assert b"COLOR" not in zus and b"X-ZENTRALE-STIL" not in zus
    assert "stil" not in abb.datei_lesen(zus)[0]["daten"]


def test_ics_ungepruefter_stil_bleibt_in_den_extras():
    # was sich nicht exakt als CSS zurücklesen lässt, geht verlustfrei in die Extras
    e = {"label": "Alt", "stil": {"color": "#FF0000"}}
    kal = abb.termin_kalender(TAG, e, "s6@test")
    assert b"X-ZENTRALE-STIL" not in kal.to_ical()
    assert abb.datei_lesen(kal.to_ical())[0]["daten"] == e


# ── Speichern, Lesen, Setzen ───────────────────────────────────────────
def test_anlegen_und_lesen(cal):
    uni = next(e for e in _tag() if e["label"] == "Uni")
    assert uni["stil"] == STIL
    assert "stil" not in next(e for e in _tag() if e["label"] == "Kino")
    assert kk.eintrag(_k("Uni"))["stil"] == STIL
    if kalender._speicher().art == "ics":
        texte = [p.read_text() for p in cal.rglob("*.ics")]
        assert any("X-ZENTRALE-STIL:border-style: double" in t.replace("\r\n ", "")
                   and "COLOR:darkslategray" in t for t in texte)


def test_routine_und_spanne_geben_stil_weiter(cal):
    kalender.add_routine("termine", "Geige", "FREQ=WEEKLY;BYDAY=WE", time="18:00",
                         stil={"border-style": "dotted"})
    import kalender_bearbeiten as kb
    assert kb.spanne_neu("termine", TAG, "2026-10-15", "Messe", stil={"color": "#00ff00"})
    assert kb.routine_neu("termine", "Lauf", TAG, "w", stil={"background-color": "#112233"})
    tag = {e["label"]: e for e in _tag()}
    assert tag["Geige"]["stil"] == {"border-style": "dotted"}
    assert tag["Messe"]["stil"] == {"color": "#00ff00"}
    assert tag["Lauf"]["stil"] == {"background-color": "#112233"}


def test_setzen_ersetzt_und_leer_entfernt(cal):
    k = _k("Kino")
    d = kk.stil_setzen(k, {"border-style": "dashed", "border-color": "#FF8800"})
    assert d["stil"] == {"border-style": "dashed", "border-color": "#ff8800"}
    d = kk.stil_setzen(k, {"color": "#000000"})            # ersetzen, nicht mischen
    assert d["stil"] == {"color": "#000000"}
    d = kk.stil_setzen(k, {})
    assert "stil" not in d


def test_ablehnen_schreibt_nichts(cal):
    _k("Kino")                       # JSON-Speicher vergibt beim ersten Lesen Kennungen
    vorher = _stand(cal)
    for falsch in ({"color": "rot"}, {"border-style": "wellig"}, {"font-size": "12px"},
                   "color: red"):
        with pytest.raises(kk.KalenderAbgelehnt) as e:
            kk.stil_setzen(_k("Kino"), falsch)
        assert e.value.code == "STIL-UNGUELTIG"
        with pytest.raises(kk.KalenderAbgelehnt):
            kalender.add_entry("termine", TAG, "Neu", stil=falsch)
    with pytest.raises(kk.KalenderAbgelehnt) as e:
        kalender.add_entry("rhythmus", TAG, "Schlaf", time="23:00", stil={"color": "#000000"})
    assert e.value.code == "IST-PHASE"
    with pytest.raises(kk.KalenderAbgelehnt) as e:
        kk.stil_setzen("gibtsnicht", {"color": "#000000"})
    assert e.value.code == "KENNUNG-UNBEKANNT"
    assert _stand(cal) == vorher


# ── Routen ─────────────────────────────────────────────────────────────
def _client():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))
    from flask import Flask
    from routen import kalender as routen_kalender
    app = Flask(__name__)
    app.register_blueprint(routen_kalender.bp)
    return app.test_client()


def test_routen(cal):
    c = _client()
    k = _k("Kino")
    r = c.post("/api/calendar/stil", json={"kennung": k, "stil": {"color": "#123456"}})
    assert r.status_code == 200 and r.get_json()["stil"] == {"color": "#123456"}
    r = c.post("/api/calendar/stil", json={"kennung": k, "stil": {"color": "blau"}})
    assert r.status_code == 400 and r.get_json()["code"] == "STIL-UNGUELTIG"
    r = c.post("/api/calendar/stil", json={"kennung": k, "stil": {}})
    assert r.status_code == 200 and "stil" not in r.get_json()
    r = c.post("/api/calendar/entry", json={"day": TAG, "label": "Zahnarzt", "time": "12:00",
                                            "stil": {"border-style": "solid"}})
    assert r.status_code == 200
    r = c.post("/api/calendar/spanne", json={"von": "2026-10-20", "bis": "2026-10-21",
                                             "label": "Reise", "stil": {"color": "#00ff00"}})
    assert r.status_code == 200
    r = c.post("/api/calendar/routine", json={"label": "Chor", "seit": TAG, "freq": "w",
                                              "time": "20:00", "stil": {"color": "#0000ff"}})
    assert r.status_code == 200
    woche = c.get(f"/api/calendar?ref={TAG}").get_json()
    st = {e["label"]: e.get("stil") for e in woche["days"][TAG]}
    assert st["Zahnarzt"] == {"border-style": "solid"} and st["Chor"] == {"color": "#0000ff"}
    assert st["Uni"] == STIL
    assert {e["label"]: e.get("stil") for e in kk.alle_eintraege()}["Reise"] == {"color": "#00ff00"}
