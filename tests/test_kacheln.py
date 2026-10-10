"""
Kacheln (2026-10-10, memory/system/hub_bauplan.md „Kacheln"): der Hub
core/kacheln.py mit Katalog und Adressen, die Quelle core/kachel_kalender.py
(Woche/Monat, fest und mitlaufend, +N, blättern) und die Routen
/api/kacheln, /api/kachel, /api/kachel/aktion. Der Kalender liegt im
Wegwerf-Ordner (conftest).
"""
import json
import types
from datetime import date, timedelta

import pytest

import adressen
import farbrollen
import kachel_kalender as kk
import kacheln
import kalender
from kachel_form import KachelWeg

HEUTE = date(2026, 10, 14)                     # ein Mittwoch
WOCHE = {"modus": "fest", "von": "2026-10-12", "bis": "2026-10-18"}


@pytest.fixture
def termine():
    kalender.ensure_init()
    kalender.add_entry("termine", "2026-10-12", "Arzt", "09:00")
    kalender.add_entry("termine", "2026-10-12", "Geburtstag Oma")      # ganztägig
    for i in range(5):
        kalender.add_entry("termine", "2026-10-14", "Probe %d" % i, "1%d:00" % i)
    kalender.add_entry("termine", "2026-10-30", "Abgabe", "23:00")


def adresse(ref=WOCHE):
    return adressen.bauen("kalender", ["ausschnitt"], ref)


def anfrage(ref=WOCHE, w=90, h=5, **mehr):
    return dict({"adresse": adresse(ref), "w": w, "h": h}, **mehr)


def text(zeile):
    return "".join(t for t, _r in zeile)


# ── Hub: Form der Anfrage und Antwort ─────────────────────────────────

def test_antwort_hat_die_form_und_ueberlebt_json(termine):
    status, a = kacheln.holen(anfrage())
    assert status == 200
    assert set(a) == {"form", "zeilen", "text", "stand", "ttl", "oben", "oben_max", "bevorzugt"}
    assert a["form"] == "zeilen" and a["bevorzugt"] == {"w": 90, "h": 7}
    assert json.loads(json.dumps(a)) == a
    for zeile in a["zeilen"]:
        for st in zeile:
            assert isinstance(st, list) and len(st) == 2 and all(isinstance(x, str) for x in st)
            assert st[1] in farbrollen.ROLLEN                      # nur Bedeutungen, keine Farben
    assert "Arzt" in a["text"] and a["ttl"] == 60
    # gleicher Inhalt, gleicher Stand → „unverändert"
    status, b = kacheln.holen(anfrage(stand=a["stand"]))
    assert b == {"unveraendert": True, "stand": a["stand"], "ttl": 60}


def test_groesse_als_groesse_feld_geht_auch(termine):
    a = kacheln.holen({"adresse": adresse(), "groesse": {"w": 90, "h": 5}})[1]
    assert a["zeilen"] == kacheln.holen(anfrage())[1]["zeilen"]


@pytest.mark.parametrize("w,h", [(90, 5), (55, 4), (49, 2), (83, 10), (300, 40)])
def test_die_app_kuerzt_auf_w_mal_h(termine, w, h):
    for ref in (WOCHE, {"modus": "fest", "von": "2026-10-05", "bis": "2026-10-31"}):
        status, a = kacheln.holen(anfrage(ref, w, h))
        if "zu_klein" in a:
            continue
        assert len(a["zeilen"]) <= h
        assert all(len(text(z)) <= w for z in a["zeilen"])


def test_zu_klein_sagt_die_mindestgroesse(termine):
    assert kacheln.holen(anfrage(w=3, h=1))[1]["zu_klein"] == {"w": 6, "h": 2}    # ARTEN.min
    # 0×0: nichts wird gezeichnet, aber die Größe für genau diesen Bezug kommt
    monat = {"modus": "fest", "von": "2026-10-01", "bis": "2026-10-31"}
    assert kacheln.holen(anfrage(monat, w=0, h=0))[1]["bevorzugt"] == {"w": 7 * 11 + 6, "h": 1 + 5 * 3}
    a = kacheln.holen(anfrage(w=20, h=5))[1]                       # 7 Spalten passen nicht
    assert a["zu_klein"] == {"w": 7 * kk.SPALTE_MIN + 6, "h": 2}
    monat = {"modus": "fest", "von": "2026-10-01", "bis": "2026-10-31"}
    assert kacheln.holen(anfrage(monat, w=30, h=20))[1]["zu_klein"]["w"] == 7 * kk.ZELLE_MIN + 6


def test_ungueltig_weg_aus_recht(termine, monkeypatch):
    assert kacheln.holen(anfrage({"modus": "fest", "von": "2026-10-01", "bis": "2026-11-15"}))[0] == 400
    s, a = kacheln.holen(anfrage({"modus": "mitlaufend", "tage": 40}))
    assert s == 400 and "höchstens 31 tage" in a["text"]
    assert kacheln.holen(dict(anfrage(), adresse="zentrale://kalender/liste"))[0] == 400
    assert kacheln.holen(dict(anfrage(), adresse="zentrale://gibtsnicht/x"))[1]["fehler"] == "aus"
    assert kacheln.holen(dict(anfrage(), adresse="https://kalender/ausschnitt"))[0] == 400
    assert kacheln.holen({"app": "kalender"})[0] == 400
    assert kacheln.holen(dict(anfrage(), w="breit"))[0] == 400

    def weg(*a):
        raise KachelWeg("gelöscht")

    def kaputt(*a):
        raise RuntimeError("platt")
    quelle = types.SimpleNamespace(APP="probe", ARTEN={"x": {"min": (1, 1)}}, RECHTE=("lesen",),
                                   kachel=weg, aktion=weg)
    monkeypatch.setitem(kacheln.QUELLEN, "probe", quelle)
    probe = {"adresse": "zentrale://probe/x", "w": 10, "h": 3}
    assert kacheln.holen(probe) == (404, {"fehler": "weg"})
    quelle.kachel = kaputt
    s, a = kacheln.holen(probe)
    assert s == 503 and a["fehler"] == "aus"
    quelle.RECHTE = ()                                             # Prüfpunkt im Hub
    assert kacheln.holen(probe)[1]["fehler"] == "recht"


def test_antwort_die_nicht_durch_json_passt_faellt_auf(monkeypatch):
    quelle = types.SimpleNamespace(APP="probe", ARTEN={"x": {}}, RECHTE=("lesen",),
                                   kachel=lambda *a: {"zeilen": [[["a", "dim"]]], "text": date(2026, 1, 1)})
    monkeypatch.setitem(kacheln.QUELLEN, "probe", quelle)
    s, a = kacheln.holen({"adresse": "zentrale://probe/x", "w": 10, "h": 3})
    assert s == 503 and a["fehler"] == "aus"


def test_alte_anfrage_mit_app_art_ref_geht_noch(termine):
    """Ältere Oberflächen auf anderen Rechnern schicken noch {app, art, ref}."""
    alt = {"app": "kalender", "art": "ausschnitt", "ref": WOCHE, "w": 90, "h": 5}
    assert kacheln.holen(alt)[1]["zeilen"] == kacheln.holen(anfrage())[1]["zeilen"]


def test_der_hub_prueft_mit_den_feldern_des_katalogs(termine):
    """Die Regeln stehen in den Feldern (kachel_kalender.ARTEN), der Hub
    prüft sie, bevor die Quelle gefragt wird."""
    def fehler(adr):
        s, a = kacheln.holen({"adresse": adr, "w": 90, "h": 5})
        assert s == 400, a
        return a["text"]
    basis = "zentrale://kalender/ausschnitt?"
    assert "unbekannt: farbe" in fehler(basis + "farbe=rot&modus=mitlaufend&tage=7")
    assert "gilt hier nicht: von" in fehler(basis + "modus=mitlaufend&tage=7&von=2026-10-12")
    assert "tage fehlt" in fehler(basis + "modus=mitlaufend")
    assert "ganze zahl" in fehler(basis + "modus=mitlaufend&tage=sieben")
    assert "art: eins von" in fehler(basis + "modus=irgendwie")
    assert "JJJJ-MM-TT" in fehler(basis + "bis=morgen&modus=fest&von=2026-10-12")
    assert "liegt vor" in fehler(basis + "bis=2026-10-11&modus=fest&von=2026-10-12")
    assert "höchstens 31 tage" in fehler(basis + "bis=2026-11-12&modus=fest&von=2026-10-12")
    assert "doppelt" in fehler(basis + "modus=fest&modus=mitlaufend")
    assert kacheln.holen({"adresse": basis + "modus=mitlaufend&tage=31", "w": 90, "h": 5})[0] == 200


def test_unbekannte_rolle_einer_quelle_wird_text_und_roh_ist_reserviert(monkeypatch):
    quelle = types.SimpleNamespace(APP="probe", ARTEN={"x": {}}, RECHTE=("lesen",),
                                   kachel=lambda *a: {"zeilen": [[["a", "kal"], ["b", "heute"]]]})
    monkeypatch.setitem(kacheln.QUELLEN, "probe", quelle)
    a = kacheln.holen({"adresse": "zentrale://probe/x", "w": 10, "h": 3})[1]
    assert a["zeilen"] == [[["a", "text"], ["b", "heute"]]]
    s, a = kacheln.holen({"adresse": "zentrale://probe/x", "w": 10, "h": 3, "form": "roh"})
    assert s == 400 and "roh" in a["text"]


def test_langsame_quelle_wird_gemeldet(monkeypatch):
    gemeldet = []
    monkeypatch.setattr(kacheln.state, "push_log", gemeldet.append)
    uhr = iter([0.0, 2.0])
    monkeypatch.setattr(kacheln.time, "monotonic", lambda: next(uhr))
    quelle = types.SimpleNamespace(APP="probe", ARTEN={"x": {}}, RECHTE=("lesen",),
                                   kachel=lambda *a: {"zeilen": []})
    monkeypatch.setitem(kacheln.QUELLEN, "probe", quelle)
    assert kacheln.holen({"adresse": "zentrale://probe/x", "w": 10, "h": 3})[0] == 200
    assert gemeldet and "2.0 s" in gemeldet[0]


# ── Katalog ───────────────────────────────────────────────────────────

def test_katalog_form_und_kalender_eintrag():
    k = kacheln.katalog()
    assert json.loads(json.dumps(k)) == k
    (e,) = [x for x in k if x["app"] == "kalender"]
    assert set(e) == {"app", "art", "titel", "min", "bevorzugt", "max", "ttl", "parameter",
                      "aktionen", "formen"}
    # Ohne max der Quelle: die neutrale Grenze des Hubs (2026-10-10)
    assert e["max"] == {"w": kacheln.GROESSE_GRENZE, "h": kacheln.GROESSE_GRENZE}
    assert e["art"] == "ausschnitt" and e["titel"] == "kalender"
    assert e["min"] == {"w": 6, "h": 2} and e["bevorzugt"] == {"w": 90, "h": 7} and e["ttl"] == 60
    assert e["aktionen"] == ["oeffnen"] and e["formen"] == ["zeilen"]
    # parameter = JSON Schema 2020-12 (2026-10-10, Standards statt Eigenformat)
    s = e["parameter"]
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert s["type"] == "object" and s["additionalProperties"] is False
    p = s["properties"]
    assert list(p) == ["modus", "tage", "von", "bis"]
    assert p["modus"]["default"] == "mitlaufend"
    assert [w["const"] for w in p["modus"]["oneOf"]] == ["mitlaufend", "fest"]
    assert (p["tage"]["type"], p["tage"]["minimum"], p["tage"]["maximum"], p["tage"]["default"]) \
        == ("integer", 1, 31, 7)
    assert p["von"]["format"] == "date" and p["von"]["default"] == date.today().isoformat()
    assert p["bis"]["default"] == (date.today() + timedelta(days=6)).isoformat()
    fest = [t["then"] for t in s["allOf"] if t["if"]["properties"]["modus"]["const"] == "fest"]
    assert fest == [{"required": ["von", "bis"], "properties": {"tage": False}}]
    for name, prop in p.items():
        assert prop["title"] and prop["type"] in ("string", "integer")
    # die Quelle selbst trägt kein Datum (das kommt zur Fragezeit)
    assert "default" not in kk.ARTEN["ausschnitt"]["parameter"]["properties"]["von"]


def test_katalog_nur_mit_lese_recht_und_neue_apps_von_selbst(monkeypatch):
    probe = types.SimpleNamespace(APP="probe", RECHTE=("lesen",), kachel=lambda *a: {},
                                  ARTEN={"x": {"titel": "probe", "min": (2, 1), "max": (9, 9),
                                               "parameter": {"type": "object", "properties": {
                                                   "an": {"type": "boolean", "default": True}}}}})
    monkeypatch.setitem(kacheln.QUELLEN, "probe", probe)
    (e,) = [x for x in kacheln.katalog() if x["app"] == "probe"]
    assert e["max"] == {"w": 9, "h": 9} and e["bevorzugt"] == {"w": 2, "h": 1}
    assert e["aktionen"] == []                                    # kein aktion() → nichts
    probe.RECHTE = ()
    assert [x["app"] for x in kacheln.katalog()] == ["kalender"]


# ── Kalender: Woche ───────────────────────────────────────────────────

def test_woche_kopf_ganztags_zuerst_heute_und_plus_n(termine):
    a = kk.kachel("ausschnitt", WOCHE, 90, 5, heute=HEUTE)
    kopf = a["zeilen"][0]
    assert text(kopf).startswith("Mo 12.10.")
    assert ["Mi 14.10.".ljust(12), "heute"] in kopf               # Bedeutung, nicht Farbe
    assert ["Mo 12.10.".ljust(12), "kopf"] in kopf
    spalte_mo = [text(z).split("│")[0] for z in a["zeilen"][1:]]
    assert spalte_mo[0].startswith("Geburtstag") and spalte_mo[1].startswith("09:00 Arzt")
    spalte_mi = [text(z).split("│")[2].strip() for z in a["zeilen"][1:]]
    assert spalte_mi[:3] == ["10:00 Probe…", "11:00 Probe…", "12:00 Probe…"]
    assert spalte_mi[3] == "+2"                                    # 5 Termine, 4 Zeilen
    assert a["oben_max"] == 1


def test_woche_blaettern_zeigt_den_rest(termine):
    a = kk.kachel("ausschnitt", WOCHE, 90, 5, oben=1, heute=HEUTE)
    spalte_mi = [text(z).split("│")[2].strip() for z in a["zeilen"][1:]]
    assert spalte_mi == ["11:00 Probe…", "12:00 Probe…", "13:00 Probe…", "14:00 Probe…"]
    assert kk.kachel("ausschnitt", WOCHE, 90, 5, oben=99, heute=HEUTE)["oben"] == 1


def test_mitlaufend_rechnet_jeden_tag_neu(termine):
    ref = {"modus": "mitlaufend", "tage": 3}
    assert kk.bereich(ref, HEUTE) == (HEUTE, HEUTE + timedelta(days=2))
    heute = text(kk.kachel("ausschnitt", ref, 40, 4, heute=HEUTE)["zeilen"][0])
    morgen = text(kk.kachel("ausschnitt", ref, 40, 4, heute=HEUTE + timedelta(days=1))["zeilen"][0])
    assert heute.startswith("Mi 14.10.") and morgen.startswith("Do 15.10.")
    # der heutige Tag steht immer vorn und in „heute"
    assert kk.kachel("ausschnitt", ref, 40, 4, heute=HEUTE)["zeilen"][0][0][1] == "heute"


def test_ausgefallenes_fehlt(termine, monkeypatch):
    echt = kalender.month_view

    def mit_ausfall(ref):
        d = echt(ref)
        d["days"].setdefault("2026-10-13", []).append({"label": "Geige", "time": "18:00", "ausfall": "Ferien"})
        return d
    monkeypatch.setattr(kalender, "month_view", mit_ausfall)
    assert "Geige" not in kk.kachel("ausschnitt", WOCHE, 90, 5, heute=HEUTE)["text"]


# ── Kalender: Monat ───────────────────────────────────────────────────

def test_ab_8_tagen_monatsraster_mit_plus_n_und_blaettern(termine):
    ref = {"modus": "fest", "von": "2026-10-05", "bis": "2026-10-31"}
    a = kk.kachel("ausschnitt", ref, 83, 1 + 4 * 3, heute=HEUTE)
    z = [text(x) for x in a["zeilen"]]
    assert z[0].split() == kk.WT                                   # Kopf Mo … So
    assert z[1].startswith("5.10.")                                # erster Tag mit Monat
    woche2 = z[4:7]                                                # 12.–18.
    assert woche2[0].split()[:3] == ["12", "13", "14"] and "+3" in woche2[0]
    assert "Geburtstag" in woche2[1] and "09:00 Arzt" in woche2[2]
    assert any(["14", "heute"] == st for st in a["zeilen"][4])     # heute
    assert a["oben_max"] == 3
    b = kk.kachel("ausschnitt", ref, 83, 13, oben=3, heute=HEUTE)
    assert "13:00 Prob" in text(b["zeilen"][5]) and "+" not in text(b["zeilen"][4])


def test_monat_ueber_den_monatswechsel(termine):
    ref = {"modus": "fest", "von": "2026-10-26", "bis": "2026-11-08"}
    a = kk.kachel("ausschnitt", ref, 83, 1 + 2 * 3, heute=HEUTE)
    z = [text(x) for x in a["zeilen"]]
    assert z[1].split()[:6] == ["26.10.", "27", "28", "29", "30", "31"]
    assert z[1].split()[6] == "1.11."
    assert "23:00 Abga…" in z[2]


def test_mehr_als_31_tage_klar_abgelehnt():
    for ref in ({"modus": "fest", "von": "2026-10-01", "bis": "2026-11-01"},
                {"modus": "mitlaufend", "tage": 32}):
        with pytest.raises(kk.KachelFehler, match="höchstens 31 tage"):
            kk.bereich(ref, HEUTE)
    with pytest.raises(kk.KachelFehler):
        kk.bereich({"modus": "fest", "von": "2026-10-18", "bis": "2026-10-12"}, HEUTE)
    with pytest.raises(kk.KachelFehler):
        kk.bereich({"modus": "irgendwie"}, HEUTE)


# ── Aktion „oeffnen" ──────────────────────────────────────────────────

def test_oeffnen_sagt_wohin_als_adresse():
    s, a = kacheln.aktion(dict(anfrage(), aktion="oeffnen"))
    assert (s, a) == (200, {"zeige": {"adresse": "zentrale://kalender/2026-10-12"}})
    s, a = kacheln.aktion(dict(anfrage({"modus": "mitlaufend", "tage": 7}), aktion="oeffnen"))
    assert a["zeige"]["adresse"] == "zentrale://kalender/" + date.today().isoformat()
    assert kacheln.aktion(dict(anfrage(), aktion="loeschen"))[0] == 400
    assert kacheln.aktion(anfrage())[0] == 400


# ── Routen ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def test_routen(client, termine):
    r = client.post("/api/kachel", json=anfrage())
    assert r.status_code == 200 and r.get_json()["zeilen"]
    assert client.post("/api/kachel", json=anfrage({"modus": "mitlaufend", "tage": 99})).status_code == 400
    assert client.post("/api/kachel", data="kaputt").status_code == 400
    r = client.post("/api/kachel/aktion", json=dict(anfrage(), aktion="oeffnen"))
    assert r.get_json() == {"zeige": {"adresse": "zentrale://kalender/2026-10-12"}}
    r = client.get("/api/kacheln")
    assert r.status_code == 200 and r.get_json() == kacheln.katalog()


def test_quelle_ohne_gueltige_adresse_beim_oeffnen(monkeypatch):
    quelle = types.SimpleNamespace(APP="probe", ARTEN={"x": {}}, RECHTE=("lesen",),
                                   kachel=lambda *a: {},
                                   aktion=lambda *a: {"zeige": {"ansicht": "kalender"}})
    monkeypatch.setitem(kacheln.QUELLEN, "probe", quelle)
    s, a = kacheln.aktion({"adresse": "zentrale://probe/x", "aktion": "oeffnen"})
    assert s == 503 and "wohin" in a["text"]


def test_ohne_jsonschema_sagt_der_hub_aus_statt_ungeprueft_zu_fragen(monkeypatch):
    """Fehlt das Paket jsonschema auf einem Rechner, fragt der Hub keine
    Quelle ungeprüft, sondern sagt „aus" mit dem Grund (2026-10-10)."""
    import kachel_parameter

    def fehlt():
        raise kachel_parameter.OhnePruefer("jsonschema fehlt (pip install -r requirements.txt)")
    monkeypatch.setattr(kachel_parameter, "_validator", fehlt)
    status, a = kacheln.holen(anfrage())
    assert status == 503 and a["fehler"] == "aus" and "jsonschema" in a["text"]
    assert [e["app"] for e in kacheln.katalog()] == ["kalender"]   # anzeigen geht weiter
