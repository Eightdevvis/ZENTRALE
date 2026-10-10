"""
Termine mit Titel aus einer Liste bzw. einem Projekt (core/kalender_quelle.py).

Sasha, 10.10.2026: im Kalender steht der „variable Container" der Todo-Liste,
als Titel das oberste Item; umsortieren/abhaken ändert den Titel mit — ohne
dass der Kalender geschrieben wird. Geprüft gegen BEIDE Speicher. Listen
liegen nie in echten Daten (conftest lenkt lists um).
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import kalender_ics_abbildung as abb
import kalender_kennung as kk
import kalender_quelle as kq
import lists

pytestmark = pytest.mark.kalender_beide

TAG = "2026-10-14"


@pytest.fixture
def todo():
    l = lists.create_list("todo")
    a = lists.add_item(l["id"], "Steuern planen")
    b = lists.add_item(l["id"], "Bad putzen")
    return {"lid": l["id"], "a": a["id"], "b": b["id"]}


@pytest.fixture
def cal(tmp_path, monkeypatch, todo):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_entry("termine", TAG, "", time="10:00", ende="12:00",
                       quelle={"art": "liste", "id": todo["lid"]})
    kalender.add_entry("termine", TAG, "Kino", time="19:00", ende="21:00")
    return tmp_path


def _stand(tmp_path):
    return {str(p.relative_to(tmp_path)): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != ".zentrale.lock"}


def _tag():
    return kalender.entries_in_range(date.fromisoformat(TAG), date.fromisoformat(TAG))[TAG]


def _fenster():
    return next(e for e in _tag() if e.get("quelle"))


def _k():
    return next(e["kennung"] for e in kk.alle_eintraege() if e.get("quelle"))


# ── Feld und Speicher ──────────────────────────────────────────────────
def test_anlegen_mit_quelle_label_ist_rueckfall(cal, todo):
    e = _fenster()
    assert e["quelle"] == {"art": "liste", "id": todo["lid"]}
    assert e["label"] == "todo"                    # Rückfall = Name der Liste
    assert e["titel_live"] == "Steuern planen"
    assert e["quelle_name"] == "todo"
    assert e["quelle_zustand"] == "ok"
    assert e["quelle_eintrag"] == {"liste": todo["lid"], "id": todo["a"]}
    kino = next(x for x in _tag() if x["label"] == "Kino")
    assert "titel_live" not in kino


def test_ics_hin_und_zurueck():
    for e in ({"label": "todo", "time": "10:00", "ende": "12:00",
               "quelle": {"art": "liste", "id": "l_todo"}},
              {"label": "Haus", "quelle": {"art": "projekt", "id": "l_haus/7"},
               "kategorie": "uni"}):
        kal = abb.termin_kalender(TAG, e, "u1@test")
        text = kal.to_ical().decode()
        assert "X-ZENTRALE-QUELLE:" + kq.als_text(e["quelle"]) in text
        assert "URL:" + kq.adresse(e["quelle"]) in text
        assert "X-ZENTRALE-EXTRAS" not in text
        assert abb.lesen(kal)[0]["daten"] == e
    r = {"label": "todo", "rrule": "FREQ=WEEKLY;BYDAY=MO", "time": "09:00",
         "quelle": {"art": "liste", "id": "l_todo"}}
    assert abb.lesen(abb.routine_kalender(r, "u2@test", anker=date(2026, 10, 12)))[0]["daten"] == r


def test_ics_url_als_rueckweg_und_geloeste_quelle_ohne_alte_url():
    e = {"label": "todo", "quelle": {"art": "liste", "id": "l_todo"}}
    roh = abb.termin_kalender(TAG, e, "u3@test").to_ical()
    ohne_x = b"\r\n".join(z for z in roh.split(b"\r\n") if not z.startswith(b"X-ZENTRALE-QUELLE"))
    assert abb.datei_lesen(ohne_x)[0]["daten"]["quelle"] == {"art": "liste", "id": "l_todo"}
    # Quelle gelöst → zusammenführen bringt die alte zentrale://-URL nicht zurück
    neu = abb.termin_kalender(TAG, {"label": "todo"}, "u3@test")
    zus = abb.zusammenfuehren(roh, neu, "u3@test")
    assert b"zentrale://" not in zus
    assert "quelle" not in abb.datei_lesen(zus)[0]["daten"]


def test_speicher_behaelt_quelle(cal, todo):
    k = _k()
    assert kk.eintrag(k)["quelle"] == {"art": "liste", "id": todo["lid"]}
    if kalender._speicher().art == "ics":
        texte = [p.read_text() for p in cal.rglob("*.ics")]
        assert any(f"X-ZENTRALE-QUELLE:liste:{todo['lid']}" in t
                   and f"URL:zentrale://fokus/{todo['lid']}" in t for t in texte)


# ── Live-Auflösung ─────────────────────────────────────────────────────
def test_umsortieren_aendert_titel_ohne_kalender_schreiben(cal, todo):
    vorher = _stand(cal)
    lists.reorder_item(todo["lid"], todo["b"], -1)
    assert _fenster()["titel_live"] == "Bad putzen"
    assert _stand(cal) == vorher


def test_abgehakt_naechstes_dann_leer(cal, todo):
    lists.toggle_item(todo["lid"], todo["a"])
    assert _fenster()["titel_live"] == "Bad putzen"
    lists.toggle_item(todo["lid"], todo["b"])
    e = _fenster()
    assert e["titel_live"] == "todo — alles erledigt"
    assert e["quelle_zustand"] == "leer"
    assert e["quelle_eintrag"] is None


def test_ordner_oben_gibt_sein_oberstes_blatt(todo):
    lid = lists.create_list("lernen")["id"]
    ordner = lists.add_item(lid, "Analysis")
    lists.add_item(lid, "Blatt 3", parent_iid=ordner["id"])
    lists.add_item(lid, "Vokabeln")
    lists.set_focus(lid, ordner["id"])           # Fokus klebt oben
    r = kq.aufloesen({"art": "liste", "id": lid})
    assert r["titel"] == "Blatt 3" and r["zustand"] == "ok"


def test_geloeschte_liste_faellt_auf_label_zurueck(cal, todo):
    lists.delete_list(todo["lid"])
    e = _fenster()
    assert e["titel_live"] == "todo"
    assert e["quelle_zustand"] == "fehlt"


def test_projekt_naechster_schritt(cal):
    lid = lists.create_list("haus")["id"]
    p = lists.add_item(lid, "Renovieren")
    s1 = lists.add_item(lid, "Farbe kaufen", parent_iid=p["id"])
    lists.add_item(lid, "Streichen", parent_iid=p["id"])
    lists.set_item_project(lid, p["id"], True)
    qid = f"{lid}/{p['id']}"
    d = kk.quelle_setzen(_k(), "projekt", qid)
    assert d["label"] == "Renovieren"
    assert d["titel_live"] == "Farbe kaufen" and d["quelle_name"] == "Renovieren"
    lists.toggle_item(lid, s1["id"])
    assert _fenster()["titel_live"] == "Streichen"
    # Auswahl nennt Listen und Projekte mit dem, was oben steht
    aus = kq.auswahl()
    assert {"art": "projekt", "id": qid, "name": "Renovieren", "titel": "Streichen",
            "zustand": "ok"} in aus["projekte"]
    assert any(x["id"] == lid and x["art"] == "liste" for x in aus["listen"])


def test_einmal_lesen_je_abruf(cal, todo, monkeypatch):
    kalender.add_entry("termine", TAG, "", time="14:00", ende="15:00",
                       quelle={"art": "liste", "id": todo["lid"]})
    zaehler = []
    echt = lists.read_lists
    monkeypatch.setattr(lists, "read_lists", lambda: zaehler.append(1) or echt())
    assert len([e for e in _tag() if e.get("quelle")]) == 2
    assert len(zaehler) == 1


# ── Lesetext der KI ────────────────────────────────────────────────────
def test_imprint_zeile(cal, todo):
    text = kalender.render_range_for_tool(date.fromisoformat(TAG), date.fromisoformat(TAG))
    assert "10:00-12:00 Steuern planen (aus Liste: todo)" in text
    assert "Kino" in text
    gefiltert = kalender.render_range_for_tool(date.fromisoformat(TAG),
                                               date.fromisoformat(TAG), suche="steuern")
    assert "Steuern planen" in gefiltert and "Kino" not in gefiltert


# ── Setzen, Lösen, Ablehnen ────────────────────────────────────────────
def test_setzen_und_loesen(cal, todo):
    kino = next(e["kennung"] for e in kk.alle_eintraege() if e["label"] == "Kino")
    d = kk.quelle_setzen(kino, "liste", todo["lid"], label="Kino-Zeit")
    assert d["label"] == "Kino-Zeit" and d["titel_live"] == "Steuern planen"
    d = kk.quelle_loesen(kino, titel_uebernehmen=True)
    assert "quelle" not in d and d["label"] == "Steuern planen"
    d = kk.quelle_loesen(_k())
    assert "quelle" not in d and d["label"] == "todo"


def test_routine_und_spanne_mit_quelle(cal, todo):
    kalender.add_routine("termine", "", "FREQ=WEEKLY;BYDAY=WE", time="08:00", ende="09:00",
                         quelle={"art": "liste", "id": todo["lid"]})
    kalender.add_span("termine", "2026-10-20", "2026-10-21", "Klausurphase",
                      quelle={"art": "liste", "id": todo["lid"]})
    tag = kalender.entries_in_range(date(2026, 10, 14), date(2026, 10, 21))
    routine = next(e for e in tag[TAG] if e.get("recurring"))
    assert routine["titel_live"] == "Steuern planen" and routine["label"] == "todo"
    spanne = tag["2026-10-21"][0]
    assert spanne["label"] == "Klausurphase" and spanne["titel_live"] == "Steuern planen"


@pytest.mark.parametrize("art, qid, code", [
    ("liste", "l_gibtsnicht", "QUELLE-UNBEKANNT"),
    ("notiz", "l_todo", "QUELLE-ART-UNBEKANNT"),
    ("liste", "../x", "QUELLE-UNGUELTIG"),
])
def test_ablehnungen_schreiben_nichts(cal, todo, art, qid, code):
    kino = next(e["kennung"] for e in kk.alle_eintraege() if e["label"] == "Kino")
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt) as fehler:
        kk.quelle_setzen(kino, art, qid)
    assert fehler.value.code == code
    with pytest.raises(kk.KalenderAbgelehnt) as fehler:
        kalender.add_entry("termine", TAG, "X", quelle={"art": art, "id": qid})
    assert fehler.value.code == code
    assert _stand(cal) == vorher


def test_projekt_muss_projekt_sein_und_loesen_ohne_quelle(cal, todo):
    kino = next(e["kennung"] for e in kk.alle_eintraege() if e["label"] == "Kino")
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt) as fehler:
        kk.quelle_setzen(kino, "projekt", todo["lid"])        # nicht als Projekt markiert
    assert fehler.value.code == "QUELLE-UNBEKANNT"
    with pytest.raises(kk.KalenderAbgelehnt) as fehler:
        kk.quelle_loesen(kino)
    assert fehler.value.code == "OHNE-QUELLE"
    assert _stand(cal) == vorher


def test_phase_bekommt_keine_quelle(cal, todo):
    p = kk.phase_anlegen("Schlaf", "23:00", motiv="schlaf", ende="07:00", von=TAG)
    vorher = _stand(cal)
    with pytest.raises(kk.KalenderAbgelehnt) as fehler:
        kk.quelle_setzen(p["kennung"], "liste", todo["lid"])
    assert fehler.value.code == "IST-PHASE"
    assert _stand(cal) == vorher


def test_uncommitted_und_kategorie_bleiben(cal, todo):
    k = _k()
    kk.kategorie_setzen(k, "uni")
    d = kk.ebene_wechseln(k)
    assert d["layer"] == "uncommitted" and d["kategorie"] == "uni"
    assert d["quelle"] == {"art": "liste", "id": todo["lid"]}
    assert d["titel_live"] == "Steuern planen"


def test_kollision_wie_normaler_termin(cal, todo):
    konflikte = kalender.conflicts_for_proposed("termine", TAG, "Zahnarzt",
                                                time="11:00", ende="11:30")
    assert konflikte, "das Zeitfenster ist belegt"


# ── Routen ─────────────────────────────────────────────────────────────
def test_routen(cal, todo):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))
    from flask import Flask
    from routen import kalender as routen_kalender
    app = Flask(__name__)
    app.register_blueprint(routen_kalender.bp)
    c = app.test_client()
    aus = c.get("/api/calendar/quellen").get_json()
    assert any(x["id"] == todo["lid"] and x["titel"] == "Steuern planen" for x in aus["listen"])
    kino = next(e["kennung"] for e in kk.alle_eintraege() if e["label"] == "Kino")
    r = c.post("/api/calendar/quelle", json={"kennung": kino, "art": "liste", "id": todo["lid"]})
    assert r.status_code == 200 and r.get_json()["titel_live"] == "Steuern planen"
    r = c.post("/api/calendar/quelle", json={"kennung": kino, "art": "liste", "id": "l_weg"})
    assert r.status_code == 400 and r.get_json()["code"] == "QUELLE-UNBEKANNT"
    r = c.delete("/api/calendar/quelle", json={"kennung": kino})
    assert r.status_code == 200 and "quelle" not in r.get_json()
    r = c.post("/api/calendar/entry", json={"day": TAG, "time": "16:00",
                                            "quelle": {"art": "liste", "id": todo["lid"]}})
    assert r.status_code == 200
    woche = c.get(f"/api/calendar?ref={TAG}").get_json()
    fenster = [e for e in woche["days"][TAG] if e.get("quelle")]
    assert len(fenster) == 2 and all(e["titel_live"] == "Steuern planen" for e in fenster)
