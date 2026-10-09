"""
Trockentest des Prüfstands (scripts/pruefstand.py, memory/ki/pruefstand.md).

Der echte Prüfstand kostet Geld und läuft deshalb nie in pytest. Hier läuft
seine MECHANIK mit gefälschtem Modell und gefälschtem Richter: ein Fall geht
über die echte Route (/api/chat → kern.chat → Werkzeug-Schleife → echte
Werkzeuge) gegen einen Wegwerf-Kalender, die Uhr steht auf dem 08.10.2026,
die Websuche antwortet nach Fall-Vorgabe, ein Skript drückt die Knöpfe —
und danach müssen Endzustand, Metriken und Belegprüfung das Richtige sagen.

Das Modell spielt dabei den 08.10. nach: Uhrzeit ändern ohne Ende, eine
Frage stellen, auf die keine Antwort kommt, trotzdem eintragen, und
„18:10–19:00" melden.
"""
import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from pruefstand_teile import (bericht, endzustand, faelle, kind, metriken,  # noqa: E402
                              richter, umgebung, uhr)
from test_cloud_loop import FakeBlock, FakeClient  # noqa: E402

import ai_backends  # noqa: E402
import cloud  # noqa: E402
import kalender  # noqa: E402


FALL = {
    "id": "trocken",
    "titel": "Trockentest",
    "jetzt": "2026-10-08T15:24",
    "kalender": {
        "termine": [{"tag": dt.date(2026, 10, 9), "label": "Drive",
                     "zeit": "18:30", "ende": "19:30"}],
        "routinen": [{"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TH",
                      "zeit": "17:45", "ende": "18:30", "ort": "Geigenschule"}],
    },
    "netz": {"suche": [{"wenn": "ferien", "treffer": [
        {"titel": "Ferien Saarland - Schulferien.org", "url": "https://schulferien.example",
         "text": "Kalender Saarland 2026 Download als PDF"}]}]},
    "antworten": {"erlaubnis": "ja", "knopf": None},
    "zuege": [{"sagt": "geige ist donnerstags 18:10-19 uhr, wann sind die ferien?",
               "erwartet": {"rueckfrage": False}}],
    "endzustand": [
        {"was": "Geige 22.10. 18:10–19:00", "am": "2026-10-22", "label": "geige",
         "findet_statt": True, "beginn": "18:10", "ende": "19:00"},
        {"was": "Geige fällt 15.10. aus", "am": "2026-10-15", "label": "geige",
         "findet_statt": False},
        {"was": "Eine Regel", "regeln": {"label": "geige", "anzahl": 1}},
        {"was": "Drive bleibt", "am": "2026-10-09", "label": "drive", "findet_statt": True},
    ],
}

# Das gefälschte Modell: vier Runden wie am 08.10.
RUNDEN = [
    {"stop_reason": "tool_use", "content": [
        FakeBlock("tool_use", name="web_search", input={"query": "Herbstferien Saarland 2026"},
                  id="t1"),
        FakeBlock("tool_use", name="edit_calendar_routine",
                  input={"label": "Geigenstunde", "aktion": "aendern", "time": "18:10"}, id="t2")]},
    {"stop_reason": "tool_use", "content": [
        FakeBlock("tool_use", name="ask_choice",
                  input={"frage": "Pause bis 16.10. eintragen?", "optionen": ["ja", "nein"]},
                  id="t3")]},
    {"stop_reason": "tool_use", "content": [
        FakeBlock("tool_use", name="add_calendar_pause",
                  input={"label": "Geigenstunde", "von": "2026-10-05", "bis": "2026-10-16"},
                  id="t4")]},
    {"stop_reason": "end_turn", "text": ["Steht: Geige donnerstags 18:10–19:00, "
                                         "Ferien bis 16.10."],
     "content": [FakeBlock("text", text="Steht.")]},
]


def _richter_attrappe(gesehen):
    def fragen(system, text, modell):
        gesehen.append(text)
        return json.dumps({"behauptungen": [
            {"zug": 1, "behauptung": "Suche fand Schulferien.org", "urteil": "belegt",
             "quelle": "T1.1", "zitat": "Ferien Saarland - Schulferien.org"},
            {"zug": 1, "behauptung": "Ferien bis 16.10.", "urteil": "belegt",
             "quelle": "T1.1", "zitat": "Herbstferien bis 16.10."},      # erfunden
            {"zug": 1, "behauptung": "Geige 18:10–19:00", "urteil": "falsch",
             "quelle": "P1", "zitat": "Geigenstunde"},
        ]}), "richter-attrappe"
    return fragen


@pytest.fixture
def lauf(monkeypatch, tmp_path):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "chat_cloud_kind", lambda: "anthropic")
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "claude")
    monkeypatch.setattr(cloud, "_model", lambda: "claude-sonnet-5")
    monkeypatch.setattr(cloud.graph, "einmal_seeden", lambda *a, **k: None)
    client = FakeClient([dict(r) for r in RUNDEN])
    monkeypatch.setattr(cloud, "_get_client", lambda: client)
    cal_vorher = kalender.CAL_PATH
    gesehen = []
    erg = kind.ausfuehren(FALL, code_wurzel=ROOT, tmp=str(tmp_path / "probe"),
                          richter_fragen=_richter_attrappe(gesehen))
    return {"erg": erg, "client": client, "richter_text": gesehen,
            "cal_vorher": cal_vorher, "tmp": tmp_path}


def test_lauf_geht_ueber_die_echte_route_und_stoppt_nicht(lauf):
    erg = lauf["erg"]
    assert not erg.get("absturz"), erg.get("absturz")
    zug = erg["zuege"][0]
    assert [w["name"] for w in zug["werkzeuge"]] == [
        "web_search", "edit_calendar_routine", "ask_choice", "add_calendar_pause"]
    assert "18:10–19:00" in zug["antwort"]
    assert len(lauf["client"].calls) == 4             # vier Modell-Runden


def test_uhr_steht_auf_dem_fall(lauf):
    zug = lauf["erg"]["zuege"][0]
    assert "8. Oktober 2026" in zug["kontext"]


def test_websuche_antwortet_nach_fall_vorgabe(lauf):
    zug = lauf["erg"]["zuege"][0]
    such = zug["werkzeuge"][0]["ergebnis"]
    assert "Schulferien.org" in such and "16.10" not in such
    assert lauf["erg"]["netz"][0][0] == "suche"


def test_knopf_ohne_antwort_und_gate_mit_ja(lauf):
    zug = lauf["erg"]["zuege"][0]
    arten = [f["art"] for f in zug["fragen"]]
    assert "knopf" in arten and "erlaubnis" in arten
    knopf = next(f for f in zug["fragen"] if f["art"] == "knopf")
    assert knopf["antwort"] is None
    assert zug["werkzeuge"][2]["ergebnis"].startswith("Sasha hat NICHT geantwortet")


def test_endzustand_findet_die_falsche_erfolgsmeldung(lauf):
    ez = {e["was"]: e for e in lauf["erg"]["endzustand"]}
    assert not ez["Geige 22.10. 18:10–19:00"]["ok"]
    assert "Ende 18:30 statt 19:00" in ez["Geige 22.10. 18:10–19:00"]["grund"]
    assert ez["Geige fällt 15.10. aus"]["ok"]
    assert ez["Eine Regel"]["ok"] and ez["Drive bleibt"]["ok"]


def test_metriken(lauf):
    m = lauf["erg"]["metriken"]
    assert m["werkzeug_aufrufe"] == 4
    assert m["knopf_fragen"] == 1
    assert m["handelt_ohne_antwort"] == [
        "Zug 1: add_calendar_pause nach unbeantworteter Frage"]
    assert m["rueckfragen"] == [{"zug": 1, "erwartet": False, "gestellt": True, "ok": False}]
    assert lauf["erg"]["kosten_eur"] > 0                 # gebucht (in die Test-Datei)


def test_richter_sieht_quellen_und_erfundenes_zitat_faellt_durch(lauf):
    text = lauf["richter_text"][0]
    assert '<quelle id="T1.1">' in text and '<quelle id="P1">' in text
    b = lauf["erg"]["richter"]["behauptungen"]
    assert b[0]["urteil"] == "belegt" and not b[0]["vermerk"]
    assert b[1]["urteil"] == "unbelegt" and "nicht in der Quelle" in b[1]["vermerk"]
    assert b[2]["urteil"] == "falsch"
    assert lauf["erg"]["richter"]["zaehlung"]["fehler"] == 2


def test_nichts_bleibt_umgelenkt(lauf):
    import datetime as d
    assert kalender.CAL_PATH == lauf["cal_vorher"]
    assert d.date is uhr._ECHT_DATE and d.datetime is uhr._ECHT_DATETIME
    assert os.path.exists(os.path.join(lauf["tmp"], "probe", "ai_calendar.json")) or \
        os.path.isdir(os.path.join(lauf["tmp"], "probe", "kalender"))


def test_bericht_schreibt_markdown_json_und_transkript(lauf, tmp_path):
    durchgang = {"zeit": "jetzt", "code": "test", "modelle": [], "richter": "x",
                 "faelle": [lauf["erg"], dict(lauf["erg"], id="versteckt", verdeckt=True)],
                 "isolation": "sauber"}
    durchgang["summen"] = bericht.summen(durchgang["faelle"])
    pfad = bericht.schreiben(durchgang, str(tmp_path / "aus"))
    md = open(pfad, encoding="utf-8").read()
    assert "Endzustand" in md and "trocken" in md
    assert "Herbstferien bis 16.10." not in md.split("## Verdeckte")[1]
    assert os.path.exists(tmp_path / "aus" / "transkripte" / "trocken.md")
    assert os.path.exists(tmp_path / "aus" / "verdeckt" / "versteckt.md")
    json.load(open(tmp_path / "aus" / "ergebnis.json", encoding="utf-8"))


# ── Ohne Lauf ──────────────────────────────────────────────────────────

def test_alle_faelle_sind_gueltig():
    alle = faelle.alle()
    assert len(alle) >= 5
    assert any(f.get("verdeckt") for f in alle)
    assert len({f["id"] for f in alle}) == len(alle)


def test_fall_mit_tippfehler_faellt_vor_dem_lauf_auf(tmp_path):
    p = tmp_path / "kaputt.yaml"
    p.write_text("id: x\ntitel: y\nzuege: [{sagt: hallo}]\nendzustand: [{am: 2026-10-08}]\n",
                 encoding="utf-8")
    with pytest.raises(faelle.FallFehler, match="was"):
        faelle.laden(str(p))


def test_uhr_wird_zurueckgestellt():
    with uhr.verstellt(dt.datetime(2026, 10, 8, 15, 24), ROOT):
        from datetime import date as d2
        assert d2.today() == dt.date(2026, 10, 8)
        assert kalender.date.today() == dt.date(2026, 10, 8)
        # Das echte Modul bleibt unberührt (pydantic im SDK vergleicht damit).
        assert dt.datetime is uhr._ECHT_DATETIME
        # Echte Werte (icalendar, dateutil) gelten weiter als datetime.
        assert isinstance(dt.datetime(2026, 1, 1, 8, 0), kalender.datetime)
    import datetime as d
    assert d.date is uhr._ECHT_DATE
    assert kalender.date is uhr._ECHT_DATE
    assert sys.modules["datetime"] is dt


def test_eins_von_besteht_mit_einer_variante(tmp_path):
    kalender.add_routine("termine", "Parkour", "FREQ=WEEKLY;BYDAY=WE", time="18:00", ende="19:00")
    p = {"eins_von": [[{"am": "2026-10-14", "label": "parkour", "findet_statt": True,
                        "beginn": "18:30"}],
                      [{"am": "2026-10-14", "label": "parkour", "findet_statt": True,
                        "beginn": "18:00", "ende": "19:00"}]]}
    assert endzustand.eine(p) is None
    p["eins_von"].pop()
    assert "keine Variante" in endzustand.eine(p)


def test_loeschen_und_neu_wird_gezaehlt():
    erg = {"zuege": [{"werkzeuge": [
        {"name": "edit_calendar_routine", "args": {"label": "Geigenstunde", "aktion": "loeschen"}},
        {"name": "add_calendar_routine", "args": {"label": "Geigenstunde @ Geigenschule"}}]}]}
    m = metriken.berechnen(erg)
    assert m["loeschen_und_neu"] == ["Zug 1: geigenstunde gelöscht und neu angelegt"]


def test_entwurf_aus_gespraech(tmp_path):
    ordner = tmp_path / "g1"
    ordner.mkdir()
    zeilen = [
        {"art": "nachricht", "rolle": "user", "text": "lösch nyam", "id": "a",
         "ts": "2026-10-08T13:24:04+00:00"},
        {"art": "nachricht", "rolle": "assistant", "text": "erledigt", "id": "b",
         "ts": "2026-10-08T13:24:10+00:00",
         "werkzeuge": [{"name": "delete_calendar_entry", "args": "day=2026-10-08, label=nyam",
                        "ergebnis": "1 Termin(e) gelöscht"}]},
        {"art": "nachricht", "rolle": "user", "text": "danke", "id": "c",
         "ts": "2026-10-08T13:25:00+00:00"},
    ]
    (ordner / "pc.jsonl").write_text("\n".join(json.dumps(z) for z in zeilen), encoding="utf-8")
    text = faelle.entwurf_aus_gespraech(str(tmp_path), "g1", bis_nachricht="b")
    assert "delete_calendar_entry" in text and "lösch nyam" in text and "danke" not in text
    import yaml
    assert yaml.safe_load(text)["zuege"] == [{"sagt": "lösch nyam"}]


def test_netz_attrappe_ohne_regel():
    n = umgebung.NetzAttrappe({})
    assert json.loads(n.get("http://localhost:8888/search?q=x&format=json")) == {"results": []}
    with pytest.raises(RuntimeError):
        n.get("https://example.org/")
    with pytest.raises(RuntimeError):
        n.post("http://x", {})


def test_richter_zitat_normalisiert():
    assert richter.zitat_steht_drin("18:10 – 19:00", "Geige 18:10 - 19:00 Uhr")
    assert not richter.zitat_steht_drin("", "irgendwas")


# Die drei Richter-Zitate aus dem Haiku-Lauf vom 08.10. abends (f01), die
# als „steht nicht in der Quelle" durchfielen, obwohl alles drinstand.
_LSF = ("Termine Gruppe: Übung 1 · Di 10:00 bis 12:00 wöchentl. ab 20.10.2026 "
        "Termine Gruppe: Übung 2 · Do 10:00 bis 12:00 wöchentl. ab 22.10.2026 "
        "Termine Gruppe: Übung 3 · Do 10:00 bis 12:00 wöchentl. ab 22.10.2026 "
        "Termine Gruppe: Übung 4 · Fr 08:30 bis 10:00 wöchentl. ab 23.10.2026 "
        "Termine Gruppe: Übung 5 · Fr 10:00 bis 12:00 wöchentl. ab 23.10.2026")
_KAL = ("Montag, 12.10.2026:\n  #tb989 08:30–10:00 Experimentalphysik @ C6.4 0.10 [termine]\n"
        "Dienstag, 13.10.2026:\n  #t051c 08:30–10:00 Experimentalphysik @ C6.4 0.10 [termine]")


def test_richter_zitat_zusammengefuegte_zeilen_und_zaehlung():
    assert richter.zitat_steht_drin(
        "#tb989 08:30–10:00 Experimentalphysik @ C6.4 0.10 [termine], "
        "#t051c 08:30–10:00 Experimentalphysik @ C6.4 0.10 [termine]", _KAL)
    assert richter.zitat_steht_drin(
        "Di 10:00 bis 12:00, Do 10:00 bis 12:00 ×2, Fr 08:30 bis 10:00, "
        "Fr 10:00 bis 12:00 ×2", _LSF)


def test_richter_zitat_eingeschobene_klammer_des_richters():
    k = "## Was ansteht\nKalender 08.10.2026 bis 09.10.2026:\nDonnerstag, 08.10.2026:"
    assert richter.zitat_steht_drin(
        "Kalender 08.10.2026 bis 09.10.2026: [nur Termine ohne Vorlesungen]", k)
    # „[termine]" steht wörtlich in der Quelle und bleibt Teil des Zitats
    assert not richter.zitat_steht_drin("#tb989 08:30–10:00 Mathe [termine]", _KAL)


def test_richter_zitat_bleibt_streng():
    # erfunden bleibt erfunden — auch als Stück einer Aufzählung
    assert not richter.zitat_steht_drin("Di 10:00 bis 12:00, Sa 10:00 bis 12:00", _LSF)
    assert not richter.zitat_steht_drin("Herbstferien bis 16.10.", _LSF)
    # nur Kleinkram belegt nichts
    assert not richter.zitat_steht_drin("Di, Do", _LSF)
    assert not richter.zitat_steht_drin("[Ferien bis 16.10.]", _LSF)
    # andere Striche und Anführungszeichen sind dieselben
    assert richter.zitat_steht_drin("„Fr 08:30 bis 10:00\u201c", _LSF)
    assert richter.zitat_steht_drin("08:30\u221210:00 Experimentalphysik", _KAL)


def test_richter_mehrere_quellen_in_einem_feld():
    erg = {"zuege": [{"sagt": "x", "kontext": "", "kalender_danach": "",
                      "werkzeuge": [{"name": "add_calendar_routine", "args": {},
                                     "ergebnis": "Steht jetzt: #r99e1 Vorlesung mo,di"},
                                    {"name": "add_calendar_routine", "args": {},
                                     "ergebnis": "Steht jetzt: #rdcea Mathe di"}]}]}
    roh = {"behauptungen": [
        {"urteil": "belegt", "quelle": "T1.1, T1.2",
         "zitat": "Steht jetzt: #r99e1 Vorlesung mo,di, Steht jetzt: #rdcea Mathe di"},
        {"urteil": "belegt", "quelle": "T1.1, T1.7", "zitat": "Steht jetzt"},
        {"urteil": "belegt", "quelle": "T1.1 und T1.2", "zitat": "Steht jetzt: #r00 erfunden"}]}
    b = richter.nachpruefen(roh, erg)
    assert b[0]["urteil"] == "belegt", b[0]
    assert b[1]["urteil"] == "unbelegt" and "T1.7" in b[1]["vermerk"]
    assert b[2]["urteil"] == "unbelegt" and "Zitat" in b[2]["vermerk"]


def test_rueckfrage_auch_als_bitte_um_angaben():
    zug = {"werkzeuge": [], "antwort": "Da fehlt der Inhalt. Schick mir die Zeiten, "
                                       "dann trag ich sie ein."}
    assert metriken.rueckfrage_gestellt(zug)
    zug["antwort"] = "Steht drin. Sag mir Bescheid, wenn sich was ändert."
    assert not metriken.rueckfrage_gestellt(zug)


def test_richter_zeilen_ueberstehen_anfuehrungszeichen():
    """Im ersten Durchgang brach das JSON des Richters an einem Zitat mit
    Anführungszeichen — Zeilen verlieren dabei höchstens eine Behauptung."""
    text = ('Hier meine Urteile:\n'
            'B ¦ 2 ¦ unbelegt ¦ - ¦ - ¦ Geige fällt bis zum 16.10. aus ¦ Ferien bis 16.10. ¦ nur Links\n'
            'B ¦ 3 ¦ belegt ¦ T3.1 ¦ "OK, 2 Routine(n) \'Geigenstunde\' geändert." ¦ zwei geändert ¦ 2 Regeln ¦ steht da\n'
            'kaputte Zeile ohne Trenner\n')
    roh = richter._zeilen_aus(text)
    assert [b["zug"] for b in roh["behauptungen"]] == [2, 3]
    erg = {"zuege": [{"sagt": "a", "werkzeuge": []}, {"sagt": "b", "werkzeuge": []},
                     {"sagt": "c", "werkzeuge": [{"name": "edit_calendar_routine", "args": {},
                                                  "ergebnis": "OK, 2 Routine(n) 'Geigenstunde' geändert."}]}]}
    b = richter.nachpruefen(roh, erg)
    assert b[0]["urteil"] == "unbelegt" and b[0]["quelle"] == ""
    assert b[1]["urteil"] == "belegt" and not b[1]["vermerk"]
