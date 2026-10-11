"""Die Anbindungs-Pipe: Beschreibung statt Python-Adapter (2026-10-11).

Geprüft wird, was die Werkstatt später verlässt: dass eine Anbindungs-
Beschreibung STRENG geprüft wird (Format, Platzhalter, Rückbau passt zur Art,
kein Schlüssel in der Datei), dass der allgemeine Adapter daraus dieselben
Schutzschichten macht wie beim Kalender (Nachlesen, Vergleich mit
Normalisierung, Zurücknehmen), dass die Stufen sich aus der Beschreibung
ergeben (ohne Nachlesen/Rückbau: gefragt und „nicht belegt“), und dass die
Probefahrt je Aktion ehrlich berichtet. Zwei echte Fälle: ein MCP-Server
(tests/fixtures/mcp_notizen.py, ein Kindprozess) und der eigene Kalender über
HTTP (Flask-Test-Client).
"""
import copy
import json
import os

import pytest

import ai_config
import fehlercodes
import werkzeug_befund
import werkzeug_erzeuger as wz
from werkzeug_erzeuger import (aktive, allgemein, anbindung, harness, probefahrt,
                               transport as tr, vergleich, vorlage)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIZEN = os.path.join(ROOT, "tests", "fixtures", "anbindung_notizen.json")
KALENDER = os.path.join(anbindung.VORLAGEN_DIR, "kalender_kern.json")


def _laden(pfad):
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def notizen():
    return _laden(NOTIZEN)


@pytest.fixture
def mcp(notizen):
    """Die Notizen-Anbindung mit echtem Kindprozess (Fake-MCP-Server)."""
    quelle = allgemein.quelle_aus(notizen)
    yield quelle
    quelle.adapter.schliessen()


def _aktion(besch, name):
    return next(a for a in besch["aktionen"] if a["name"] == name)


def _ausfuehren(quelle, name, args):
    a = next(a for a in quelle.aktionen if a["name"] == name)
    return harness.ausfuehren(quelle, a, args)


# ══ Format und Prüfung ═════════════════════════════════════════════════

def test_mitgelieferte_beschreibungen_sind_in_ordnung(notizen):
    for besch in (notizen, _laden(KALENDER)):
        p = anbindung.pruefen(besch, vertrauen=True)
        assert p.ok, p.fehler
        assert not p.warnungen, p.warnungen        # jede Aktion hat eine Probe


def _ohne(pfad_teile):
    def fn(b):
        z = b
        for t in pfad_teile[:-1]:
            z = z[t]
        del z[pfad_teile[-1]]
    return fn


def _setze(pfad_teile, wert):
    def fn(b):
        z = b
        for t in pfad_teile[:-1]:
            z = z[t]
        z[pfad_teile[-1]] = wert
    return fn


A_CREATE, A_EDIT, A_DEL = 0, 1, 2

FEHLERFAELLE = [
    ("unbekannter Schlüssel im Kopf", _setze(["zufall"], 1), "zufall"),
    ("Format fehlt", _ohne(["format"]), "format"),
    ("Vorsilbe klein geschrieben", _setze(["praefix"], "nt"), "praefix"),
    ("Bereich gibt es nicht", _setze(["bereich"], "essen"), "bereich"),
    ("Name ohne Vorsilbe", _setze(["aktionen", A_CREATE, "name"], "create_note"), "beginnen"),
    ("Aktionsname doppelt", _setze(["aktionen", A_EDIT, "name"], "nt_create_note"), "doppelt"),
    ("Aufruf passt nicht zum Transport", _setze(["aktionen", A_CREATE, "aufruf"], {"methode": "GET", "pfad": "/x"}),
     "bei transport 'mcp'"),
    ("Platzhalter ohne Argument", _setze(["aktionen", A_CREATE, "aufruf", "argumente", "title"], "{titel}"),
     "Platzhalter {titel}"),
    ("kennung hat keinen Teil", _setze(["aktionen", A_EDIT, "aufruf", "argumente", "id"], "{kennung.day}"),
     "keinen Teil"),
    ("Rückbau passt nicht zur Art", _setze(["aktionen", A_CREATE, "zurueck"],
                                          {"wiederherstellen": {"werkzeug": "x"}}), "bei 'anlegen'"),
    ("Nachlesen ohne Kennung", _ohne(["aktionen", A_CREATE, "kennung_aus"]), "braucht 'kennung_aus'"),
    ("ändern ohne Kennung aus Argument", _setze(["aktionen", A_EDIT, "kennung_aus"], {"antwort": "/id"}),
     "aus einem Argument"),
    ("Nachlesen unbekannt", _setze(["aktionen", A_CREATE, "nachlesen"], "nix"), "steht nicht im Kopf"),
    ("Vergleich auf unbekanntes Feld", _setze(["aktionen", A_CREATE, "vergleich", "farbe"], {"norm": "text"}),
     "kein Argument 'farbe'"),
    ("Vergleich: Norm gibt es nicht", _setze(["aktionen", A_CREATE, "vergleich", "title", "norm"], "ungefaehr"), "ungefaehr"),
    ("zeitpunkt ohne Zeitzone", _setze(["aktionen", A_CREATE, "vergleich", "title", "norm"], "zeitpunkt"), "zeitzone"),
    ("Muster ohne Gruppe", _setze(["aktionen", A_CREATE, "vergleich", "title", "muster"], "abc"), "EINE Gruppe"),
    ("Probe-Argument gibt es nicht", _setze(["aktionen", A_CREATE, "probe", "argumente", "farbe"], "rot"), "kein Argument 'farbe'"),
    ("ändern: Probe ohne vorher", _setze(["aktionen", A_EDIT, "probe", "vorher"], "nt_read_note"), "anlegenden Aktion"),
    ("kein JSON Schema im inputSchema", _setze(["aktionen", A_CREATE, "inputSchema", "properties", "title", "type"], "zeichen"),
     "JSON Schema"),
    ("Schlüssel in der Datei", _setze(["beschreibung"], "Zugang: sk-ant-api03-abcdefghijklmnop"), "Schlüssel"),
    ("Auth mit Schlüssel statt Namen",
     _setze(["transport"], {"art": "http", "basis": "http://x", "auth": {"art": "bearer", "einstellung": "sk-ant-123456789"}}),
     "einstellung"),
    ("Python-Transport in Nutzerdatei", _setze(["transport"], {"art": "python", "modul": "os"}), "Python-Transport"),
    ("reserviertes Feld", _setze(["aktionen", A_EDIT, "inputSchema", "properties", "alt"], {"type": "string"}), "'alt'"),
    ("Kennungsteil änderbar",
     lambda b: (b["nachlesen"]["notiz"].update({"teile": ["title"]}),
                b["aktionen"][A_EDIT].update({"kennung_aus": {"argument": "kennung"}})), "änderbar"),
]


@pytest.mark.parametrize("beschreibung, aendern, fragment", FEHLERFAELLE, ids=[f[0] for f in FEHLERFAELLE])
def test_fehlerhafte_beschreibung_wird_mit_der_stelle_abgelehnt(notizen, beschreibung, aendern, fragment):
    aendern(notizen)
    p = anbindung.pruefen(notizen, vertrauen=False)
    assert not p.ok
    assert any(fragment in m for m in p.fehler), (fragment, p.fehler)
    assert all(m.startswith("/") or "/" in m for m in p.fehler)      # jede Meldung nennt die Stelle


def test_alle_meldungen_auf_einmal_nicht_nur_die_erste(notizen):
    notizen["praefix"] = "nt"
    notizen["aktionen"][A_CREATE]["aufruf"]["argumente"]["title"] = "{titel}"
    notizen["aktionen"][A_EDIT]["kennung_aus"] = {"antwort": "/id"}
    # Das Grundschema scheitert zuerst und nennt nur seine Stellen; ohne den Kopf-Fehler die übrigen alle
    notizen["praefix"] = "NT"
    p = anbindung.pruefen(notizen)
    assert len(p.fehler) >= 2


def test_yaml_ist_dasselbe_wie_json(notizen, tmp_path):
    yaml = pytest.importorskip("yaml")
    pfad = tmp_path / "notizen.yaml"
    pfad.write_text(yaml.safe_dump(notizen, allow_unicode=True), encoding="utf-8")
    assert anbindung.laden(str(pfad), vertrauen=False) == notizen


def test_kaputte_datei_ist_eine_meldung_kein_absturz(tmp_path):
    pfad = tmp_path / "kaputt.json"
    pfad.write_text("{nicht json", encoding="utf-8")
    with pytest.raises(anbindung.AnbindungFehler) as e:
        anbindung.laden(str(pfad))
    assert "nicht lesbar" in str(e.value)


def test_das_schema_ist_selbst_ein_gueltiges_json_schema():
    import jsonschema
    s = _laden(anbindung.SCHEMA_DATEI)
    jsonschema.Draft202012Validator.check_schema(s)
    assert s["$schema"].endswith("2020-12/schema")


# ══ Stufen ═════════════════════════════════════════════════════════════

def test_stufen_ergeben_sich_aus_der_beschreibung(notizen):
    assert anbindung.stufen(notizen) == {
        "nt_create_note": "voll", "nt_edit_note": "voll", "nt_delete_note": "voll",
        "nt_purge_note": "einmalig", "nt_read_note": "lesen", "nt_list_notes": "lesen"}


@pytest.mark.parametrize("weg, aktion, erwartet", [
    (["nachlesen"], "nt_create_note", "gefragt"),
    (["zurueck"], "nt_create_note", "gefragt"),
    (["kennung_aus"], "nt_create_note", "gefragt"),
    (["zurueck"], "nt_edit_note", "gefragt"),
    (["zurueck"], "nt_delete_note", "einmalig"),
    (["nachlesen"], "nt_delete_note", "einmalig"),
])
def test_ohne_kennung_nachlesen_oder_rueckbau_keine_volle_stufe(notizen, weg, aktion, erwartet):
    a = _aktion(notizen, aktion)
    for k in weg:
        a.pop(k)
    assert anbindung.stufe(notizen, a) == erwartet


def test_ohne_beleg_fragt_es_jedes_mal_und_sagt_nicht_belegt(notizen):
    """Stufe 2: Lesen frei, Schreiben mit Rückfrage, Ergebnis „nicht belegt“,
    kein Dauer-Ja, nichts wird nachgelesen oder zurückgebaut."""
    a = _aktion(notizen, "nt_create_note")
    for k in ("nachlesen", "zurueck", "kennung_aus", "vergleich"):
        a.pop(k)
    gesendet = []

    class Skript:
        def aufrufen(self, aufruf):
            gesendet.append(aufruf)
            return tr.Antwort(daten={"id": "n1"}, text="{}")

        def schliessen(self):
            pass

    quelle = allgemein.quelle_aus(notizen, trans=Skript())
    w = {x.name: x for x in wz.werkzeuge(quelle)}["nt_create_note"]
    assert w.erlaubnis and w.immer_erlaubbar is False
    assert "nicht nachprüfen" in w.frage({"title": "Milch"})
    r = w.ausfuehrer({"title": "Milch"})
    assert r.status == "ok" and "NICHT belegt" in r and r.beleg == ""
    assert [g["werkzeug"] for g in gesendet] == ["create_note"]       # genau ein Aufruf: kein Nachlesen
    lesen = {x.name: x for x in wz.werkzeuge(quelle)}["nt_list_notes"]
    assert lesen.erlaubnis is False


def test_loeschen_ohne_wiederherstellen_nur_dieses_mal(mcp):
    w = {x.name: x for x in wz.werkzeuge(mcp)}
    assert w["nt_purge_note"].immer_erlaubbar is False
    assert w["nt_delete_note"].immer_erlaubbar is False         # Löschen war nie „immer“
    assert "darum nur dieses eine Mal" in w["nt_purge_note"].frage({"kennung": "n1"})
    assert w["nt_create_note"].immer_erlaubbar is True          # volle Stufe, anlegen


# ══ Vorlagen, Zeiger, Vergleich ════════════════════════════════════════

def test_vorlage_fuellt_typgetreu_und_laesst_fehlendes_weg():
    ctx = {"n": 3, "liste": ["a"], "kennung": vorlage.Kennung("x|y", {"p": "x", "q": "y"}), "alt": {"o": "", "z": None}}
    assert vorlage.text("{n}", ctx) == 3 and vorlage.text("{liste}", ctx) == ["a"]
    assert vorlage.text("a {n} {kennung.q}", ctx) == "a 3 y"
    assert vorlage.fuellen({"a": "{n}", "b": "{fehlt}", "c": {"d": "{fehlt}"}, "e": 5}, ctx) == {"a": 3, "e": 5}
    assert vorlage.fuellen({"a": "{alt.o}"}, ctx) == {"a": ""}                      # leer ist ein Wert
    assert vorlage.fuellen({"a": "{alt.z|neu}", "b": "{alt.nix|}"}, ctx) == {"a": "neu", "b": ""}
    assert vorlage.text("/p/{kennung.q}", ctx, "pfad") == "/p/y"
    assert vorlage.text("/a b/{kennung}", {"kennung": "x/y"}, "pfad") == "/a b/x%2Fy"
    with pytest.raises(vorlage.Fehlt):
        vorlage.text("/p/{fehlt}", ctx, "pfad")


def test_zeiger_mit_stern():
    d = {"days": {"a": [{"l": 1}, {"l": 2}], "b": [{"l": 3}]}, "x": {"~/": 4}}
    assert vorlage.zeiger_eins(d, "/days/a/1/l") == 2
    assert [e["l"] for e in vorlage.zeiger_alle(d, "/days/*")] == [1, 2, 3]
    assert vorlage.zeiger_eins(d, "/x/~0~1") == 4
    assert vorlage.zeiger_alle(d, "/nix") == [] and vorlage.zeiger_eins(d, "/nix", 7) == 7


@pytest.mark.parametrize("norm, a, b, gleich", [
    ("text", "  Hallo   Welt ", "Hallo Welt", True), ("text", "a", "A", False),
    ("zahl", 3, "3.0", True), ("zahl", "3,5", 3.5, True), ("zahl", 3, 4, False),
    ("datum", "2026-11-03", "2026-11-03T09:00:00", True), ("datum", "2026-11-03", "20261103", True),
    ("datum", "2026-11-03", "2026-11-04", False),
    ("uhrzeit", "9:00", "09:00", True), ("uhrzeit", "09:00", "09:00:00", True),
    ("uhrzeit", "09:00", "2026-11-03T09:00:00+01:00", True), ("uhrzeit", "09:00", "10:00", False),
    ("zeitpunkt", "2026-11-03T09:00", "2026-11-03T08:00:00Z", True),         # Berlin im Winter: +1
    ("zeitpunkt", "2026-11-03T09:00+01:00", "2026-11-03T08:00:00+00:00", True),
    ("zeitpunkt", "2026-11-03T09:00", "2026-11-03T09:00:00Z", False),
    ("liste-ungeordnet", ["b", "a"], ["a", "b"], True), ("liste-ungeordnet", ["a"], ["a", "b"], False),
    ("wahrheit", True, "ja", True), ("wahrheit", "false", 0, True), ("wahrheit", True, "nein", False),
])
def test_normalisierung(norm, a, b, gleich):
    assert vergleich.gleich(norm, a, b, "Europe/Berlin") is gleich


def test_nicht_vergleichbares_ist_eine_abweichung_kein_absturz():
    r = vergleich.abweichungen({"t": {"norm": "uhrzeit"}}, {"t": "09:00"}, {"t": "gegen Mittag"})
    assert len(r) == 1 and "keine Uhrzeit" in r[0]
    r = vergleich.abweichungen({"t": {"norm": "zeitpunkt"}}, {"t": "2026-11-03T09:00"}, {"t": "2026-11-03T09:00"})
    assert "Zeitzone" in r[0]                                    # ohne Zeitzone nie raten


def test_vergleich_nur_was_verlangt_wurde_und_muster():
    regeln = {"ort": {"norm": "text"}, "bis": {"norm": "datum", "feld": "/rrule", "muster": "UNTIL=(\\d{8})"}}
    e = {"ort": "Praxis", "rrule": "FREQ=WEEKLY;UNTIL=20261201T235959"}
    assert vergleich.abweichungen(regeln, {"bis": "2026-12-01"}, e) == []                 # ort nicht verlangt
    assert vergleich.abweichungen(regeln, {"bis": "2026-12-02"}, e)
    assert vergleich.abweichungen(regeln, {"ort": "Praxis"}, {"rrule": "x"}) == ["ort verlangt 'Praxis', steht nicht da"]


# ══ Allgemeiner Adapter am MCP-Server ══════════════════════════════════

def test_werkzeuge_aus_der_beschreibung_wie_beim_kalender(mcp):
    ws = {w.name: w for w in wz.werkzeuge(mcp)}
    assert list(ws) == ["nt_create_note", "nt_edit_note", "nt_delete_note", "nt_purge_note",
                        "nt_read_note", "nt_list_notes"]
    for w in ws.values():
        assert w.klein is None and w.gross and w.erzeugt == "notizen" and w.bereich == "notiz"
        assert "x-zentrale" not in str(w.parameter) and "aufruf" not in str(w.parameter)
    assert ws["nt_create_note"].worte == ("Notiz angelegt", "Notiz anlegen")
    assert ws["nt_create_note"].parameter["required"] == ["title"]
    # Prompt-Cache: dieselben Bytes bei jedem Bau
    neu = allgemein.quelle_aus(_laden(NOTIZEN))
    assert [w.parameter for w in wz.werkzeuge(neu)] == [w.parameter for w in ws.values()]


def test_anlegen_nachlesen_vergleichen_end_zu_end(mcp):
    r = _ausfuehren(mcp, "nt_create_note", {"title": "Milch", "text": "zwei  Liter", "tags": ["b", "a"]})
    assert r.status == "ok" and r == "Notiz „Milch“ EINGETRAGEN (#n1)."
    assert r.beleg == r
    gelesen = _ausfuehren(mcp, "nt_list_notes", {})
    assert "#n1 Milch" in gelesen
    assert "Milch" in _ausfuehren(mcp, "nt_read_note", {"id": "n1"})


def test_aendern_und_loeschen_mit_beleg(mcp):
    _ausfuehren(mcp, "nt_create_note", {"title": "Milch", "tags": ["a"]})
    r = _ausfuehren(mcp, "nt_edit_note", {"kennung": "n1", "title": "Hafermilch"})
    assert r == "Notiz „Hafermilch“ GEÄNDERT (#n1)."
    r = _ausfuehren(mcp, "nt_delete_note", {"kennung": "n1"})
    assert r.status == "ok" and "GELÖSCHT" in r
    assert _ausfuehren(mcp, "nt_list_notes", {}) == "Keine Notizen."


@pytest.mark.parametrize("name, args, code", [
    ("nt_create_note", {}, "NT-TITEL-LEER"),
    ("nt_create_note", {"title": "x", "tags": "a"}, "NT-WERT-UNGUELTIG"),          # Typ
    ("nt_create_note", {"title": "x", "farbe": "rot"}, "NT-UNBEKANNTES-FELD"),
    ("nt_edit_note", {"kennung": "n99", "title": "x"}, "NT-NICHT-GEFUNDEN"),
    ("nt_edit_note", {"kennung": "n1"}, "NT-NICHTS-ZU-AENDERN"),
    ("nt_delete_note", {"kennung": "n99"}, "NT-NICHT-GEFUNDEN"),
    ("nt_read_note", {"id": "n99"}, "NT-NICHT-GEFUNDEN"),
])
def test_abbruch_mit_code_und_nichts_geaendert(mcp, name, args, code):
    _ausfuehren(mcp, "nt_create_note", {"title": "da"})
    r = _ausfuehren(mcp, name, args)
    assert r.status == "fehlgeschlagen" and r.code == code, r
    assert fehlercodes.bekannt(code)
    assert "ABGEBROCHEN" in r and code in r
    assert "da" in _ausfuehren(mcp, "nt_list_notes", {})                    # alles wie vorher


def test_verfaelschtes_nachlesen_wird_zurueckgenommen(notizen, monkeypatch):
    """Der Server speichert, liest aber etwas anderes zurück → der Erzeuger
    löscht, was er angelegt hat, und meldet es."""
    monkeypatch.setenv("NOTIZEN_FEHLER", "1")
    quelle = allgemein.quelle_aus(notizen)
    try:
        r = _ausfuehren(quelle, "nt_create_note", {"title": "klein"})
        assert r.status == "fehlgeschlagen" and r.code == "W-NICHT-GESPEICHERT"
        assert "wieder gelöscht" in r and "title verlangt 'klein', steht 'KLEIN'" in r
        assert quelle.adapter.transport.aufrufen(
            {"werkzeug": "list_notes", "argumente": {}}).daten == {"notes": []}
    finally:
        quelle.adapter.schliessen()


def test_doppelt_anlegen_mit_natuerlicher_kennung_wird_abgelehnt():
    """Das Programm vergibt keine Kennung: die Kennung besteht aus Angaben.
    Gibt es sie schon, legt die Anbindung nichts doppelt an."""
    besch = _laden(KALENDER)
    app = pytest.importorskip("ui.app").app
    quelle = allgemein.quelle_aus(besch, sender=probefahrt.wsgi_sender(app.test_client()))
    args = {"day": "2026-11-03", "label": "Zahnarzt", "time": "09:00"}
    assert _ausfuehren(quelle, "kk_add_entry", args).status == "ok"
    r = _ausfuehren(quelle, "kk_add_entry", args)
    assert r.code == "KK-GIBT-ES-SCHON"
    assert _ausfuehren(quelle, "kk_read_day", {"day": "2026-11-03"}).count("\n- ") == 1


def test_kennung_mit_falscher_form(mcp):
    quelle = allgemein.quelle_aus(_laden(KALENDER), sender=lambda *a: (200, b"{}"))
    r = _ausfuehren(quelle, "kk_edit_entry", {"kennung": "nur-eine-angabe", "ort": "x"})
    assert r.code == "KK-KENNUNG-UNGUELTIG" and "2 Angaben" in r


# ══ Transporte ═════════════════════════════════════════════════════════

class FakeHttp:
    """Ein Programm im Arbeitsspeicher hinter HttpTransport(sender=…)."""

    def __init__(self, antwort=(200, b"{}")):
        self.aufrufe, self.antwort = [], antwort

    def __call__(self, methode, url, kopf, body, zeitlimit):
        self.aufrufe.append((methode, url, dict(kopf), body, zeitlimit))
        a = self.antwort
        if isinstance(a, Exception):
            raise a
        return a(methode, url, body) if callable(a) else a


def _http_besch(**transport):
    b = _laden(KALENDER)
    b["transport"] = {"art": "http", "basis": "http://prog.test/", **transport}
    return b


def test_http_baut_adresse_abfrage_und_body_aus_der_vorlage():
    fake = FakeHttp((200, json.dumps({"days": {"2026-11-03": []}}).encode()))
    quelle = allgemein.quelle_aus(_http_besch(zeitlimit=7), sender=fake)
    assert _ausfuehren(quelle, "kk_read_day", {"day": "2026-11-03"}) == "Am 2026-11-03 ist nichts eingetragen."
    methode, url, kopf, body, limit = fake.aufrufe[0]
    assert (methode, url, limit) == ("GET", "http://prog.test/api/calendar?view=week&ref=2026-11-03", 7)
    assert body is None and kopf["Accept"] == "application/json"


def test_http_auth_kommt_aus_der_einstellung_nie_aus_der_datei(monkeypatch):
    monkeypatch.setenv("ZENTRALE_PROG_TOKEN", "Geheimwert-12345")
    fake = FakeHttp()
    b = _http_besch(auth={"art": "bearer", "einstellung": "prog_token"})
    assert "Geheimwert" not in json.dumps(b)
    allgemein.quelle_aus(b, sender=fake).adapter.transport.aufrufen({"methode": "GET", "pfad": "/x"})
    assert fake.aufrufe[0][2]["Authorization"] == "Bearer Geheimwert-12345"
    b = _http_besch(auth={"art": "kopfzeile", "einstellung": "prog_token", "kopfzeile": "X-Api-Key"})
    fake = FakeHttp()
    allgemein.quelle_aus(b, sender=fake).adapter.transport.aufrufen({"methode": "GET", "pfad": "/x"})
    assert fake.aufrufe[0][2]["X-Api-Key"] == "Geheimwert-12345"


def test_fehlende_einstellung_sagt_den_namen_nicht_den_wert(monkeypatch):
    monkeypatch.delenv("ZENTRALE_PROG_TOKEN", raising=False)
    quelle = allgemein.quelle_aus(_http_besch(auth={"art": "bearer", "einstellung": "prog_token"}), sender=FakeHttp())
    with pytest.raises(tr.TransportFehler) as e:
        quelle.adapter.transport.aufrufen({"methode": "GET", "pfad": "/x"})
    assert e.value.code == "AUTH-FEHLT" and "prog_token" in e.value.grund


def test_programm_nicht_erreichbar_ist_eine_ablehnung():
    quelle = allgemein.quelle_aus(_http_besch(), sender=FakeHttp(ConnectionRefusedError()))
    r = _ausfuehren(quelle, "kk_read_day", {"day": "2026-11-03"})
    assert r.code == "KK-NICHT-ERREICHBAR" and "nichts gelesen" in r


def test_zeitueberschreitung_nach_dem_senden_ist_nie_nichts_geaendert():
    """Beim Schreiben ist unklar, ob es angekommen ist: das Ergebnis sagt
    „nicht belegt — nachlesen“, nicht „nichts eingetragen“."""
    # Das Nachlesen vor dem Anlegen (Doppelt-Schutz) ist ein Lesen und klappt; das Schreiben bleibt aus.
    fake = FakeHttp(lambda m, u, b: (200, b'{"days": {}}') if m == "GET" else (_ for _ in ()).throw(TimeoutError()))
    quelle = allgemein.quelle_aus(_http_besch(), sender=fake)
    r = _ausfuehren(quelle, "kk_add_entry", {"day": "2026-11-03", "label": "X"})
    assert r.status == "fehlgeschlagen" and r.code == "W-NICHT-GESPEICHERT"
    assert "NICHT belegt" in r and "nichts eingetragen" not in r


def test_fehlerregeln_vom_status_auf_codes():
    fake = FakeHttp(lambda m, u, b: (400, json.dumps({"error": "termin nicht gefunden"}).encode()) if m == "DELETE"
                    else (200, json.dumps({"days": {"2026-11-03": [{"label": "X", "time": "09:00"}]}}).encode()))
    quelle = allgemein.quelle_aus(_http_besch(), sender=fake)
    r = _ausfuehren(quelle, "kk_delete_entry", {"kennung": "2026-11-03|X"})
    assert r.code == "KK-NICHT-GEFUNDEN" and "Dazu gibt es im Kalender nichts" in r
    fake.antwort = (503, b"<html>Wartung</html>")
    r = _ausfuehren(quelle, "kk_read_day", {"day": "2026-11-03"})
    assert r.code == "KK-ABGELEHNT" and "Wartung" in r


def test_python_transport_nur_in_vorlagen(tmp_path):
    b = {"format": "zentrale-anbindung/1", "name": "py", "praefix": "PY", "bereich": "notiz",
         "transport": {"art": "python", "modul": "json"},
         "aktionen": [{"name": "py_loads", "description": "Wandelt etwas in Text.",
                       "inputSchema": {"type": "object", "properties": {"obj": {"type": "string"}}, "required": []},
                       "x-zentrale": {"art": "lesen"},
                       "aufruf": {"funktion": "loads", "argumente": {"obj": "{obj}"}},
                       "ausgabe": {"zeile": "{e.obj}"}}]}
    (tmp_path / "py.json").write_text(json.dumps(b), encoding="utf-8")
    with pytest.raises(anbindung.AnbindungFehler) as e:
        anbindung.laden(str(tmp_path / "py.json"))
    assert "nur in mitgelieferten Vorlagen" in str(e.value)
    assert anbindung.pruefen(b, vertrauen=True).ok
    r = tr.PythonTransport("json").aufrufen({"funktion": "loads", "argumente": {}})
    assert r.fehler                                              # loads() ohne Argument: Fehler des Programms, kein Absturz


def test_mcp_client_tools_list_und_fehler(mcp):
    t = mcp.adapter.transport
    namen = [x["name"] for x in t.werkzeuge()]
    assert {"create_note", "get_note", "update_note", "delete_note"} <= set(namen)
    assert t.server["name"] == "notizen-fake"
    unbekannt = pytest.raises(tr.TransportFehler, t.aufrufen, {"werkzeug": "gibt_es_nicht", "argumente": {}})
    assert unbekannt.value.code == "ABGELEHNT" and "Unknown tool" in unbekannt.value.grund
    fehler = t.aufrufen({"werkzeug": "get_note", "argumente": {"id": "n404"}})
    assert fehler.fehler and fehler.mcp_fehler and "not found" in fehler.text


def test_mcp_server_startet_neu_wenn_er_stirbt(mcp):
    t = mcp.adapter.transport
    t.aufrufen({"werkzeug": "create_note", "argumente": {"title": "a"}})
    t._p.kill()
    t._p.wait()
    r = t.aufrufen({"werkzeug": "list_notes", "argumente": {}})        # frischer Prozess, leerer Speicher
    assert r.daten == {"notes": []}


def test_mcp_zeitlimit():
    t = tr.McpTransport(["{python}", "-c", "import time; time.sleep(30)"], zeitlimit=1)
    try:
        with pytest.raises(tr.TransportFehler) as e:
            t.werkzeuge()
        assert e.value.code == "ZEITUEBERSCHREITUNG"
    finally:
        t.schliessen()


def test_mcp_server_der_nicht_startet():
    t = tr.McpTransport(["/gibt/es/nicht"], zeitlimit=1)
    with pytest.raises(tr.TransportFehler) as e:
        t.werkzeuge()
    assert e.value.code == "NICHT-ERREICHBAR"


# ══ Probefahrt ═════════════════════════════════════════════════════════

def test_probefahrt_mcp_voll_gruen(notizen):
    zeilen = probefahrt.fahren(notizen)
    assert probefahrt.gruen(zeilen), probefahrt.bericht(zeilen, True)
    nach = {z["aktion"]: z for z in zeilen}
    assert nach["nt_create_note"]["stufe"] == "voll"
    assert [s["schritt"] for s in nach["nt_create_note"]["schritte"]] == ["anlegen", "nachlesen", "vergleichen", "zurückbauen"]
    assert [s["schritt"] for s in nach["nt_edit_note"]["schritte"]][-2:] == ["zurückbauen (alter Stand)", "Probe-Objekt aufräumen"]
    assert nach["nt_purge_note"]["uebersprungen"] is True        # ohne Rückbau nicht ohne alles=True
    assert probefahrt.bericht(zeilen).endswith("7 von 7 in Ordnung")


def test_probefahrt_alles_fuehrt_auch_ohne_rueckbau_aus(notizen):
    zeilen = probefahrt.fahren(notizen, alles=True)
    assert probefahrt.gruen(zeilen), probefahrt.bericht(zeilen, True)
    z = next(z for z in zeilen if z["aktion"] == "nt_purge_note")
    assert not z.get("uebersprungen")
    assert any("NICHT belegt" in s["text"] for s in z["schritte"])


def test_probefahrt_hinterlaesst_nichts(notizen):
    quelle = allgemein.quelle_aus(notizen)
    try:
        probefahrt.fahren(notizen, quelle, alles=True)
        assert quelle.adapter.transport.aufrufen({"werkzeug": "list_notes", "argumente": {}}).daten == {"notes": []}
    finally:
        quelle.adapter.schliessen()


def test_probefahrt_findet_eine_falsche_beschreibung(notizen):
    """Der Vergleich ist falsch herum beschrieben (Text statt Liste): die
    Probefahrt nennt Aktion, Schritt und warum — und räumt trotzdem auf."""
    _aktion(notizen, "nt_create_note")["aufruf"]["argumente"]["title"] = "x-{title}"      # schickt anderen Titel
    quelle = allgemein.quelle_aus(notizen)
    try:
        zeilen = probefahrt.fahren(notizen, quelle)
        z = next(z for z in zeilen if z["aktion"] == "nt_create_note")
        assert not z["ok"] and "title verlangt 'Probe', steht 'x-Probe'" in z["warum"]
        assert not probefahrt.gruen(zeilen)
        assert quelle.adapter.transport.aufrufen({"werkzeug": "list_notes", "argumente": {}}).daten == {"notes": []}
    finally:
        quelle.adapter.schliessen()


def test_probefahrt_ohne_gueltige_beschreibung_nennt_die_meldungen(notizen):
    notizen["aktionen"][0]["zurueck"] = {"wiederherstellen": {"werkzeug": "x"}}
    zeilen = probefahrt.fahren(notizen)
    assert len(zeilen) == 1 and not zeilen[0]["ok"] and "bei 'anlegen'" in zeilen[0]["warum"]


def test_probefahrt_ohne_probe_argumente_sagt_es(notizen):
    del _aktion(notizen, "nt_list_notes")["probe"]
    z = next(z for z in probefahrt.fahren(notizen) if z["aktion"] == "nt_list_notes")
    assert not z["ok"] and "keine Probe-Argumente" in z["warum"]


# ══ Der eigene Kalender über HTTP ═════════════════════════════════════

@pytest.mark.kalender_beide
def test_kalender_kern_probefahrt_voll_gruen(_kalender_speicher_art):
    app = pytest.importorskip("ui.app").app
    besch = anbindung.laden(KALENDER)
    quelle = allgemein.quelle_aus(besch, sender=probefahrt.wsgi_sender(app.test_client()))
    zeilen = probefahrt.fahren(besch, quelle)
    assert probefahrt.gruen(zeilen), probefahrt.bericht(zeilen, True)
    nach = {z["aktion"]: z for z in zeilen}
    assert {k: v["stufe"] for k, v in nach.items() if k != "(Beschreibung)"} == {
        "kk_read_day": "lesen", "kk_add_entry": "voll", "kk_edit_entry": "voll",
        "kk_delete_entry": "voll", "kk_add_routine": "voll", "kk_delete_routine": "einmalig"}
    # mit alles=True läuft auch das Routine-Löschen (ohne Wiederherstellen) gegen die Test-Kopie
    zeilen = probefahrt.fahren(besch, quelle, alles=True)
    assert probefahrt.gruen(zeilen), probefahrt.bericht(zeilen, True)


@pytest.mark.kalender_beide
def test_kalender_kern_werkzeuge_gegen_den_kalender(_kalender_speicher_art):
    app = pytest.importorskip("ui.app").app
    besch = anbindung.laden(KALENDER)
    quelle = allgemein.quelle_aus(besch, sender=probefahrt.wsgi_sender(app.test_client()))
    r = _ausfuehren(quelle, "kk_add_entry", {"day": "2026-11-03", "label": "Zahnarzt", "time": "09:00", "ort": "Praxis"})
    assert r == "Termin „Zahnarzt“ am 2026-11-03 09:00 EINGETRAGEN (#2026-11-03|Zahnarzt)."
    assert "09:00 Zahnarzt Praxis (Kennung: 2026-11-03|Zahnarzt)" in _ausfuehren(quelle, "kk_read_day", {"day": "2026-11-03"})
    r = _ausfuehren(quelle, "kk_edit_entry", {"kennung": "2026-11-03|Zahnarzt", "ort": "Praxis Nord"})
    assert r.startswith("Termin „Zahnarzt“ am 2026-11-03 09:00 GEÄNDERT") and r.status == "ok"
    # Auflage aus dem Schema: die Uhrzeit ist zweistellig — der Kalender selbst rechnet mit "9:00" falsch
    r = _ausfuehren(quelle, "kk_edit_entry", {"kennung": "2026-11-03|Zahnarzt", "time": "9:00"})
    assert r.code == "KK-WERT-UNGUELTIG" and "pattern" not in r and "time" in r
    r = _ausfuehren(quelle, "kk_add_routine", {"label": "Yoga", "day": "2026-11-03", "bis": "2026-12-01",
                                               "wochentage": ["TU"], "time": "18:00"})
    assert r.status == "ok" and "Routine „Yoga“" in r
    r = _ausfuehren(quelle, "kk_add_routine", {"label": "Yoga2", "day": "2026-11-03", "bis": "2026-12-01",
                                               "wochentage": ["XX"]})
    assert r.code == "KK-WERT-UNGUELTIG" and "XX" in r              # Auswahl in der Liste, vorher nie geprüft
    r = _ausfuehren(quelle, "kk_delete_routine", {"kennung": "2026-11-03|Yoga"})
    assert r.status == "ok" and "NICHT belegt" in r                 # Stufe einmalig
    assert "Yoga" not in _ausfuehren(quelle, "kk_read_day", {"day": "2026-11-10"})
    r = _ausfuehren(quelle, "kk_delete_entry", {"kennung": "2026-11-03|Zahnarzt"})
    assert r.status == "ok" and "GELÖSCHT" in r


def test_kalender_kern_loeschen_stellt_alle_felder_wieder_her(_kalender_speicher_art=None):
    """Wiederherstellen schreibt Beginn, Ende und Ort aus dem alten Stand
    zurück — der Termin steht danach wie vorher da."""
    app = pytest.importorskip("ui.app").app
    besch = anbindung.laden(KALENDER)
    quelle = allgemein.quelle_aus(besch, sender=probefahrt.wsgi_sender(app.test_client()))
    _ausfuehren(quelle, "kk_add_entry", {"day": "2026-11-03", "label": "A", "time": "08:00", "ende": "08:30", "ort": "Hier"})
    a = quelle.adapter
    nl = besch["nachlesen"]["termin"]
    vorher = a.lesen_eintrag(nl, "2026-11-03|A")
    _ausfuehren(quelle, "kk_delete_entry", {"kennung": "2026-11-03|A"})
    assert a.lesen_eintrag(nl, "2026-11-03|A") is None
    a.zurueckbauen(_aktion(besch, "kk_delete_entry"), "2026-11-03|A", {}, vorher)
    # Seit 7f6bf4a vergibt der Kern beim Anlegen eine echte Kennung (uid) — ein
    # über die HTTP-Route wiederhergestellter Termin bekommt eine neue. Alle
    # Felder außer der Kennung müssen gleich sein.
    ohne = lambda e: {k: v for k, v in (e or {}).items() if k not in ("uid", "kennung")}
    assert ohne(a.lesen_eintrag(nl, "2026-11-03|A")) == ohne(vorher)


# ══ Dateien, Einschalten, Register ════════════════════════════════════

def test_vorlage_ist_da_und_standard_aus():
    liste = anbindung.auflisten()
    assert liste["kalender_kern"]["herkunft"] == "vorlage"
    assert not anbindung.eingeschaltet("kalender_kern")
    assert aktive.werkzeuge() == []


def test_einschalten_ueber_die_einstellung_und_nutzerdatei_ersetzt_vorlage(monkeypatch, tmp_path, notizen):
    ordner = anbindung.nutzer_ordner()
    os.makedirs(ordner, exist_ok=True)
    eigene = _laden(KALENDER)
    eigene["aktionen"] = eigene["aktionen"][:1]
    del eigene["aktionen"][0]["probe"]
    with open(os.path.join(ordner, "kalender_kern.json"), "w", encoding="utf-8") as f:
        json.dump(eigene, f)
    assert anbindung.auflisten()["kalender_kern"]["herkunft"] == "nutzer"
    monkeypatch.setenv("ZENTRALE_ANBINDUNG_KALENDER_KERN", "an")
    assert anbindung.eingeschaltet("kalender_kern")
    ws = aktive.werkzeuge()
    assert [w.name for w in ws] == ["kk_read_day"]
    assert aktive.FEHLER == {}


def test_kaputte_datei_verhindert_den_start_nicht(monkeypatch):
    ordner = anbindung.nutzer_ordner()
    os.makedirs(ordner, exist_ok=True)
    with open(os.path.join(ordner, "kaputt.json"), "w", encoding="utf-8") as f:
        f.write('{"format": "zentrale-anbindung/1"}')
    monkeypatch.setenv("ZENTRALE_ANBINDUNG_KAPUTT", "an")
    assert aktive.werkzeuge() == []
    assert "kaputt" in aktive.FEHLER and any("name" in m for m in aktive.FEHLER["kaputt"])


def test_vergebener_werkzeugname_wird_nie_ueberschrieben(monkeypatch):
    monkeypatch.setenv("ZENTRALE_ANBINDUNG_KALENDER_KERN", "an")
    ws = aktive.werkzeuge(belegte_namen={"kk_read_day"})
    assert "kk_read_day" not in [w.name for w in ws] and len(ws) == 5
    assert any("schon vergeben" in m for m in aktive.FEHLER["kalender_kern"])


def test_register_nimmt_angebundene_werkzeuge_hinten_auf(monkeypatch):
    import importlib
    import werkzeug_register
    assert werkzeug_register.ANGEBUNDEN == []          # Standard aus
    monkeypatch.setenv("ZENTRALE_ANBINDUNG_KALENDER_KERN", "an")
    namen_vorher = [w.name for w in werkzeug_register.WERKZEUGE]
    neu = aktive.werkzeuge(set(namen_vorher))
    assert [w.name for w in neu][0] == "kk_read_day" and set(w.name for w in neu).isdisjoint(namen_vorher)
    assert all(w.klein is None and w.gross for w in neu)


# ══ Fehlercodes ═══════════════════════════════════════════════════════

def test_endungen_der_anbindungen_sind_fuer_jede_vorsilbe_erklaert():
    for endung in fehlercodes.ANBINDUNG_CODES:
        for pre in ("KK", "NT", "X"):
            c = f"{pre}-{endung}"
            assert fehlercodes.bekannt(c)
            t = fehlercodes.erklaeren(c.lower())
            assert t.startswith(c) and "Ursache:" in t and "Was tun:" in t
    assert not fehlercodes.bekannt("KK-ERFUNDEN") and not fehlercodes.bekannt("KKKK-ABGELEHNT")
    assert "Unbekannter Fehlercode" in fehlercodes.erklaeren("KK-ERFUNDEN")


def test_jeder_feste_code_der_vorlagen_ist_erklaert(notizen):
    """Alle Codes, die eine mitgelieferte Beschreibung selbst nennt (fehler,
    fehlt/ungueltig), und alle, die der Adapter erzeugt, gibt es in der Tabelle."""
    for besch in (notizen, _laden(KALENDER)):
        pre = besch["praefix"]
        endungen = {r["code"] for r in besch.get("fehler") or []}
        for a in besch["aktionen"]:
            endungen |= {r["code"] for r in a.get("fehler") or []}
            for f in a["inputSchema"]["properties"].values():
                x = f.get("x-zentrale") or {}
                endungen |= {x[k] for k in ("fehlt", "ungueltig") if x.get(k)}
        for e in sorted(endungen):
            assert fehlercodes.bekannt(f"{pre}-{e}"), f"{pre}-{e}"


def test_der_adapter_nennt_nur_bekannte_endungen():
    import inspect
    import re
    quelle = inspect.getsource(allgemein) + inspect.getsource(tr)
    for m in re.findall(r'(?:Ablehnung|TransportFehler)\("([A-Z-]+)"', quelle):
        assert fehlercodes.bekannt("KK-" + m) or fehlercodes.bekannt(m), m


# ══ Ende zu Ende mit gefälschtem Modell ═══════════════════════════════

def test_ki_werkzeugaufruf_ende_zu_ende(monkeypatch):
    """Ein gefälschtes Modell ruft das angebundene Werkzeug: Gate fragt mit der
    Frage aus den Feldern, das Ergebnis trägt Kopfzeile, Satz und Kennung —
    der Server im Kindprozess hat die Notiz wirklich."""
    import cloud
    import ki_werkzeuge
    import state
    import werkzeug_register
    from test_cloud_loop import FakeClient, _lauf, _msgs, _tool_block
    from profil import gross

    quelle = allgemein.quelle_aus(_laden(NOTIZEN))
    try:
        ws = wz.werkzeuge(quelle)
        monkeypatch.setattr(werkzeug_register, "WERKZEUGE", werkzeug_register.WERKZEUGE + ws)
        monkeypatch.setattr(werkzeug_register, "_NACH_NAME",
                            {**werkzeug_register._NACH_NAME, **{w.name: w for w in ws}})
        monkeypatch.setattr(gross, "TOOLS", werkzeug_register.schema("gross"))
        monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
        monkeypatch.setattr(state, "request_permission", lambda **k: None)
        monkeypatch.setattr(state, "wait_permission", lambda: "ja")
        client = FakeClient([
            {"content": [_tool_block("nt_create_note", {"title": "Milch", "tags": ["x"]})], "stop_reason": "tool_use"},
            {"content": [_tool_block("nt_list_notes", {}, id="toolu_2")], "stop_reason": "tool_use"},
            {"text": ["Erledigt."], "stop_reason": "end_turn"},
        ])
        monkeypatch.setattr(cloud, "_get_client", lambda: client)
        events = _lauf(cloud.chat_stream(_msgs("leg eine Notiz Milch an"), tool_executor=ki_werkzeuge.ausfuehren))
    finally:
        quelle.adapter.schliessen()
    frage = [e["permission"]["frage"] for e in events if isinstance(e, dict) and "permission" in e]
    assert len(frage) == 1 and "Soll ich eine Notiz anlegen" in frage[0] and "Titel Milch" in frage[0]
    ergebnisse = [b["content"] for m in client.calls[-1]["messages"] if m["role"] == "user"
                  and isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_result"]
    assert len(ergebnisse) == 2
    assert ergebnisse[0].startswith("[ergebnis: ok]") and "Notiz „Milch“ EINGETRAGEN (#n1)" in ergebnisse[0]
    assert "#n1 Milch" in ergebnisse[1]
    assert "Erledigt." in events
    # das Modell bekommt reines JSON Schema
    gesehen = next(t for t in client.calls[0]["tools"] if t["name"] == "nt_create_note")
    assert "x-zentrale" not in json.dumps(gesehen) and gesehen["input_schema"]["required"] == ["title"]


def test_das_beispiel_in_der_doku_ist_eine_gueltige_beschreibung():
    """Doku und Code bleiben deckungsgleich: das vollständige Beispiel in
    memory/ki/werkzeug_erzeuger.md besteht die Prüfung."""
    import re
    with open(os.path.join(ROOT, "memory", "ki", "werkzeug_erzeuger.md"), encoding="utf-8") as f:
        text = f.read()
    teil = text[text.index("## Anbindungs-Beschreibung"):]
    beispiel = re.search(r"```json\n(.*?)\n```", teil, re.S).group(1)
    p = anbindung.pruefen(json.loads(beispiel))
    assert p.ok and not p.warnungen, (p.fehler, p.warnungen)
