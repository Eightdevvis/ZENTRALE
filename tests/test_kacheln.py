"""
Kacheln (2026-10-10, memory/system/hub_bauplan.md „Kacheln"): der Hub
core/kacheln.py, die Quelle core/kachel_kalender.py (Woche/Monat, fest und
mitlaufend, +N, blättern) und die Routen /api/kachel, /api/kachel/aktion.
Der Kalender liegt im Wegwerf-Ordner (conftest).
"""
import json
import types
from datetime import date, timedelta

import pytest

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


def anfrage(ref=WOCHE, w=90, h=5, **mehr):
    return dict({"app": "kalender", "art": "ausschnitt", "ref": ref, "w": w, "h": h}, **mehr)


def text(zeile):
    return "".join(t for t, _r in zeile)


# ── Hub: Form der Anfrage und Antwort ─────────────────────────────────

def test_antwort_hat_die_form_und_ueberlebt_json(termine):
    status, a = kacheln.holen(anfrage())
    assert status == 200
    assert set(a) == {"zeilen", "text", "stand", "ttl", "oben", "oben_max"}
    assert json.loads(json.dumps(a)) == a
    for zeile in a["zeilen"]:
        for st in zeile:
            assert isinstance(st, list) and len(st) == 2 and all(isinstance(x, str) for x in st)
    assert "Arzt" in a["text"] and a["ttl"] == 60
    # gleicher Inhalt, gleicher Stand → „unverändert"
    status, b = kacheln.holen(anfrage(stand=a["stand"]))
    assert b == {"unveraendert": True, "stand": a["stand"], "ttl": 60}


def test_groesse_als_groesse_feld_geht_auch(termine):
    a = kacheln.holen({"app": "kalender", "art": "ausschnitt", "ref": WOCHE,
                       "groesse": {"w": 90, "h": 5}})[1]
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
    a = kacheln.holen(anfrage(w=20, h=5))[1]                       # 7 Spalten passen nicht
    assert a["zu_klein"] == {"w": 7 * kk.SPALTE_MIN + 6, "h": 2}
    monat = {"modus": "fest", "von": "2026-10-01", "bis": "2026-10-31"}
    assert kacheln.holen(anfrage(monat, w=30, h=20))[1]["zu_klein"]["w"] == 7 * kk.ZELLE_MIN + 6


def test_ungueltig_weg_aus_recht(termine, monkeypatch):
    assert kacheln.holen(anfrage({"modus": "fest", "von": "2026-10-01", "bis": "2026-11-15"}))[0] == 400
    s, a = kacheln.holen(anfrage({"modus": "mitlaufend", "tage": 40}))
    assert s == 400 and "höchstens 31 tage" in a["text"]
    assert kacheln.holen(dict(anfrage(), art="liste"))[0] == 400
    assert kacheln.holen(dict(anfrage(), app="gibtsnicht"))[1]["fehler"] == "aus"
    assert kacheln.holen({"app": "kalender"})[0] == 400
    assert kacheln.holen(dict(anfrage(), w="breit"))[0] == 400

    def weg(*a):
        raise KachelWeg("gelöscht")

    def kaputt(*a):
        raise RuntimeError("platt")
    quelle = types.SimpleNamespace(APP="probe", ARTEN={"x": {"min": (1, 1)}}, RECHTE=("lesen",),
                                   kachel=weg, aktion=weg)
    monkeypatch.setitem(kacheln.QUELLEN, "probe", quelle)
    probe = {"app": "probe", "art": "x", "ref": {}, "w": 10, "h": 3}
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
    s, a = kacheln.holen({"app": "probe", "art": "x", "ref": {}, "w": 10, "h": 3})
    assert s == 503 and a["fehler"] == "aus"


# ── Kalender: Woche ───────────────────────────────────────────────────

def test_woche_kopf_ganztags_zuerst_heute_und_plus_n(termine):
    a = kk.kachel("ausschnitt", WOCHE, 90, 5, heute=HEUTE)
    kopf = a["zeilen"][0]
    assert text(kopf).startswith("Mo 12.10.")
    assert ["Mi 14.10.".ljust(12), "kal"] in kopf                 # heute in der Kalender-Farbe
    assert ["Mo 12.10.".ljust(12), "dim"] in kopf
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
    # der heutige Tag steht immer vorn und in „kal"
    assert kk.kachel("ausschnitt", ref, 40, 4, heute=HEUTE)["zeilen"][0][0][1] == "kal"


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
    assert any(["14", "kal"] == st for st in a["zeilen"][4])       # heute
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

def test_oeffnen_sagt_wohin():
    s, a = kacheln.aktion(dict(anfrage(), aktion="oeffnen"))
    assert (s, a) == (200, {"zeige": {"ansicht": "kalender", "ziel": "2026-10-12"}})
    s, a = kacheln.aktion(dict(anfrage({"modus": "mitlaufend", "tage": 7}), aktion="oeffnen"))
    assert a["zeige"]["ziel"] == date.today().isoformat()
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
    assert r.get_json() == {"zeige": {"ansicht": "kalender", "ziel": "2026-10-12"}}
