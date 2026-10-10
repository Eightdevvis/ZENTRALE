"""
Listen- und Graph-Kacheln (2026-10-10, memory/system/hub_bauplan.md
„Kacheln"): die Quellen core/kachel_fokus.py (`fokus`/`liste`) und
core/kachel_graph.py (`graph`/`verlauf`) hinter dem Hub core/kacheln.py —
Katalog mit Werten, die erst beim Fragen feststehen (JSON Schema, oneOf
zur Fragezeit), Bild in
w×h Zellen, blättern, „+N", Adressen, „weg", und: die Kacheln schreiben
nie. Listen und Graphen liegen im Wegwerf-Ordner (conftest 7f).
"""
import json
import os
import types
from datetime import date, timedelta

import pytest

import farbrollen
import graphs
import kachel_parameter
import kachel_fokus as kf
import kachel_graph as kg
import kacheln
import lists
from kachel_form import KachelFehler

HEUTE = date.today()


def text(zeile):
    return "".join(t for t, _r in zeile)


def bildtext(antwort):
    return [text(z) for z in antwort["zeilen"]]


def holen(adresse, w=36, h=12, **mehr):
    return kacheln.holen(dict({"adresse": adresse, "w": w, "h": h}, **mehr))


def listen_adresse(lid, erledigte=False, tiefe=3):
    return "zentrale://fokus/liste?erledigte=%s&liste=%s&tiefe=%d" % (
        "true" if erledigte else "false", lid, tiefe)


def graph_adresse(gid, tage=14):
    return "zentrale://graph/verlauf?graph=%s&tage=%d" % (gid, tage)


@pytest.fixture
def einkauf():
    """Eine Liste mit offenen, erledigten und verschachtelten Punkten."""
    l = lists.create_list("Einkauf")
    lid = l["id"]
    for t in ("Milch", "Brot", "Eier"):
        lists.add_item(lid, t)
    ordner = lists.add_item(lid, "Baumarkt")
    for t in ("Schrauben", "Dübel"):
        lists.add_item(lid, t, ordner["id"])
    tief = lists.add_item(lid, "Farbe", ordner["id"])
    lists.add_item(lid, "weiß", tief["id"])
    lists.toggle_item(lid, 2)                         # Brot erledigt
    return lid


@pytest.fixture
def schlaf():
    g = graphs.create_graph("Schlaf", "period")
    for i, (a, b) in enumerate([(1380, 420), (1410, 450), (0, 480)]):
        graphs.log_value(g["id"], (HEUTE - timedelta(days=i)).isoformat(), a, b)
    return g["id"]


@pytest.fixture
def gewicht():
    g = graphs.create_graph("Gewicht", "number", unit="kg")
    for i, v in enumerate([80.5, 81, 79.5, 80, 82]):
        graphs.log_value(g["id"], (HEUTE - timedelta(days=i)).isoformat(), v)
    return g["id"]


def _dateien():
    """Alle Dateien im Listen-/Graph-Ordner mit Inhalt und Zeitstempel."""
    ordner = lists._DATA_DIR
    return {n: (open(os.path.join(ordner, n), "rb").read(),
                os.stat(os.path.join(ordner, n)).st_mtime_ns)
            for n in sorted(os.listdir(ordner))}


# ── Katalog: Werte, die erst beim Fragen feststehen ──────────────────

def test_katalog_ohne_listen_und_graphen_bietet_sie_nicht_an():
    apps = [e["app"] for e in kacheln.katalog()]
    assert "fokus" not in apps and "graph" not in apps and "kalender" in apps


def test_katalog_traegt_die_listen_und_graphen_von_jetzt(einkauf, gewicht):
    k = kacheln.katalog()
    assert json.loads(json.dumps(k)) == k
    (lf,) = [e for e in k if e["app"] == "fokus"]
    (gr,) = [e for e in k if e["app"] == "graph"]
    assert lf["art"] == "liste" and gr["art"] == "verlauf"
    assert lf["aktionen"] == ["oeffnen"] and lf["min"] == {"w": 12, "h": 2}
    p = lf["parameter"]["properties"]
    assert p["liste"]["oneOf"] == [{"const": einkauf, "title": "Einkauf"}]
    assert p["erledigte"]["type"] == "boolean" and p["erledigte"]["default"] is False
    assert (p["tiefe"]["minimum"], p["tiefe"]["maximum"]) == (1, 9)
    assert list(p) == ["liste", "erledigte", "tiefe"]
    g = gr["parameter"]["properties"]
    assert g["graph"]["oneOf"] == [{"const": gewicht, "title": "Gewicht"}]
    assert g["tage"]["default"] == 14 and (g["tage"]["minimum"], g["tage"]["maximum"]) == (2, 365)
    # eine neue Liste steht beim nächsten Fragen von selbst drin
    neu = lists.create_list("Ideen")["id"]
    (lf,) = [e for e in kacheln.katalog() if e["app"] == "fokus"]
    assert [w["const"] for w in lf["parameter"]["properties"]["liste"]["oneOf"]] == [einkauf, neu]
    # die Quelle selbst bleibt unverändert (keine Werte im Modul hängen)
    assert "oneOf" not in kf.ARTEN["liste"]["parameter"]["properties"]["liste"]


def test_quelle_die_beim_katalog_stolpert_reisst_ihn_nicht(monkeypatch, einkauf):
    gemeldet = []
    monkeypatch.setattr(kacheln.state, "push_log", gemeldet.append)
    monkeypatch.setattr(kf, "parameter_jetzt", lambda art, schema: 1 / 0)
    apps = [e["app"] for e in kacheln.katalog()]
    assert "fokus" not in apps and "kalender" in apps and gemeldet


def test_wahl_von_jetzt_prueft_der_hub_nur_als_text(einkauf):
    """Die Auswahl steht nur im Katalog; geprüft wird die Form (ein Text) —
    eine gelöschte Liste heißt dann „weg", nicht „ungültig"."""
    schema = kf.ARTEN["liste"]["parameter"]
    roh = {"liste": "l_x", "erledigte": "false", "tiefe": "3"}
    assert kachel_parameter.pruefen(schema, roh) == {"liste": "l_x", "erledigte": False, "tiefe": 3}
    with pytest.raises(KachelFehler, match="liste fehlt"):
        kachel_parameter.pruefen(schema, dict(roh, liste=""))
    assert holen(listen_adresse("l_gibts_nicht"))[1] == {"fehler": "weg"}
    with pytest.raises(ValueError):
        kachel_parameter.schema_pruefen({"type": "object", "properties": {"x": {"type": "kaputt"}}})


# ── Liste: Bild ──────────────────────────────────────────────────────

def test_liste_kopf_fortschritt_einrueckung_und_rollen(einkauf):
    status, a = holen(listen_adresse(einkauf), w=36, h=12)
    assert status == 200 and json.loads(json.dumps(a)) == a
    zeilen = bildtext(a)
    assert zeilen[0].startswith("Einkauf") and zeilen[0].endswith(" 1/6")
    assert "█" in zeilen[0] and "░" in zeilen[0]                # Steine wie in der Ansicht
    rumpf = "\n".join(zeilen[1:])
    assert "Brot" not in rumpf                                   # erledigt: versteckt
    assert "○ Milch" in rumpf and "▾ Baumarkt 0/3" in rumpf
    assert "  ○ Schrauben" in rumpf and "    ○ weiß" in rumpf      # Ebenen eingerückt
    for zeile in a["zeilen"]:
        assert all(r in farbrollen.ROLLEN for _t, r in zeile)
    assert "- [ ] Milch" in a["text"] and "Einkauf (1/6)" in a["text"]


def test_liste_wie_die_ansicht_geordnet(einkauf):
    """Dieselbe Reihenfolge wie die Listen-Ansicht (listen_baum.ordnen):
    was weniger offen hat, steht weiter oben."""
    from tui.ansichten.fokus import liste_ordnen
    lst = next(l for l in lists.read_lists() if l["id"] == einkauf)
    oben = [it["text"] for it, ebene, _a in kf.zeilen_baum(lst["items"]) if ebene == 0]
    assert oben == [it["text"] for it in liste_ordnen(lst["items"])]


def test_erledigte_zeigen_und_tiefe_klappt_zu(einkauf):
    zeilen = bildtext(holen(listen_adresse(einkauf, erledigte=True, tiefe=1), h=12)[1])
    assert any(z.startswith("✓ Brot") for z in zeilen)
    assert any(z.startswith("▸ Baumarkt 0/3") for z in zeilen)  # zu, nur Zahl
    assert not any("Schrauben" in z for z in zeilen)
    zwei = bildtext(holen(listen_adresse(einkauf, tiefe=2), h=12)[1])
    assert any("▸ Farbe 0/1" in z for z in zwei) and not any("weiß" in z for z in zwei)


@pytest.mark.parametrize("w,h", [(12, 2), (12, 5), (20, 3), (36, 4), (80, 30), (400, 400)])
def test_liste_kuerzt_auf_w_mal_h(einkauf, w, h):
    lists.add_item(einkauf, "ein sehr langer punkt, der in keine schmale kachel passt " * 3)
    a = holen(listen_adresse(einkauf, erledigte=True), w=w, h=h)[1]
    assert len(a["zeilen"]) <= h and all(len(z) <= w for z in bildtext(a))


def test_liste_blaettert_mit_plus_n(einkauf):
    a = holen(listen_adresse(einkauf), w=30, h=4)[1]           # Kopf + 3 Zeilen
    zeilen = bildtext(a)
    gesamt = 7                                                  # Milch, Eier, Baumarkt, 3 drunter, weiß
    assert a["oben"] == 0 and a["oben_max"] == gesamt - 3
    assert zeilen[-1] == "+%d weitere" % (gesamt - 2)
    unten = holen(listen_adresse(einkauf), w=30, h=4, oben=99)[1]
    assert unten["oben"] == unten["oben_max"] and "+" not in bildtext(unten)[-1]
    assert bildtext(unten)[-1].strip().endswith("weiß")


def test_leere_und_fertige_liste_sagen_es_leise():
    lid = lists.create_list("Leer")["id"]
    assert bildtext(holen(listen_adresse(lid), h=3)[1])[1] == "noch leer"
    lists.add_item(lid, "x")
    lists.toggle_item(lid, 1)
    assert bildtext(holen(listen_adresse(lid), h=3)[1])[1] == "alles erledigt"


def test_bevorzugt_passt_zur_liste(einkauf):
    a = holen(listen_adresse(einkauf), w=0, h=0)[1]
    assert a["bevorzugt"]["h"] == 1 + 7 and 24 <= a["bevorzugt"]["w"] <= 48


def test_liste_weg_und_falsche_felder(einkauf):
    assert holen(listen_adresse("l_gibtsnicht")) == (404, {"fehler": "weg"})
    assert kacheln.aktion({"adresse": listen_adresse("l_gibtsnicht"),
                           "aktion": "oeffnen"}) == (404, {"fehler": "weg"})
    status, a = holen(listen_adresse(einkauf, tiefe=12))
    assert status == 400 and "9" in a["text"]
    status, a = holen("zentrale://fokus/liste?liste=%s" % einkauf)
    assert status == 400 and "fehlt" in a["text"]


def test_oeffnen_sagt_die_adresse_der_liste(einkauf):
    assert kacheln.aktion({"adresse": listen_adresse(einkauf), "aktion": "oeffnen"}) \
        == (200, {"zeige": {"adresse": "zentrale://fokus/" + einkauf}})


# ── Graph: Bild ──────────────────────────────────────────────────────

def test_graph_zahl_kopf_balken_fuss(gewicht):
    status, a = holen(graph_adresse(gewicht, 14), w=30, h=6)
    assert status == 200 and json.loads(json.dumps(a)) == a
    zeilen = bildtext(a)
    assert len(zeilen) == 6 and all(len(z) == 30 for z in zeilen[:-1])
    assert zeilen[0].startswith("Gewicht kg") and zeilen[0].endswith("80.5 kg")
    assert zeilen[-1].startswith("min 79.5 kg  max 82 kg")
    balken = "".join(zeilen[1:5])
    assert "█" in balken and "·" in zeilen[4]                     # Tage ohne Wert: leiser Punkt
    # heute steht ganz rechts, in der Rolle „heute"
    assert a["zeilen"][4][-1][1] == "heute"
    assert a["oben"] == 0 and a["oben_max"] == 0
    assert "Gewicht, letzte 14 tage" in a["text"]


def test_graph_periode_als_dauer_und_uhrzeit(schlaf):
    a = holen(graph_adresse(schlaf, 7), w=24, h=5)[1]
    zeilen = bildtext(a)
    assert zeilen[0].endswith("23:00–07:00")                       # letzter Eintrag = heute
    assert zeilen[-1].startswith("min 8h00  max 8h00")


def test_graph_skala_und_zeit():
    s = graphs.create_graph("Laune", "scale")["id"]
    graphs.log_value(s, HEUTE.isoformat(), 5)
    graphs.log_value(s, (HEUTE - timedelta(days=1)).isoformat(), 1)
    a = holen(graph_adresse(s, 2), w=12, h=3)[1]
    balken = bildtext(a)[1]
    assert balken.endswith("█") and "▂" in balken                  # 0–5 fest: 1 ist klein
    z = graphs.create_graph("Einschlafen", "time")["id"]
    graphs.log_value(z, HEUTE.isoformat(), 1395)
    graphs.log_value(z, (HEUTE - timedelta(days=1)).isoformat(), 1350)
    zeilen = bildtext(holen(graph_adresse(z, 2), w=30, h=4)[1])
    assert zeilen[0].endswith("23:15") and zeilen[-1].startswith("min 22:30  max 23:15")


@pytest.mark.parametrize("w,h", [(12, 2), (12, 3), (24, 6), (60, 10), (400, 40)])
def test_graph_kuerzt_auf_w_mal_h(gewicht, w, h):
    for tage in (2, 14, 365):
        a = holen(graph_adresse(gewicht, tage), w=w, h=h)[1]
        assert len(a["zeilen"]) <= h and all(len(z) <= w for z in bildtext(a))


def test_mehr_tage_als_spalten_werden_gemittelt():
    sp = kg.spalten([(HEUTE - timedelta(days=3 - i), v) for i, v in enumerate([1, 3, None, 5])], 2)
    assert sp == [(2.0, False), (5.0, True)]
    assert kg.spalten([(HEUTE, 1), (HEUTE, None)], 6) == [(1, False)] * 3 + [(None, True)] * 3


def test_graph_ohne_werte_sagt_es_leise():
    g = graphs.create_graph("Neu", "number")["id"]
    graphs.log_value(g, (HEUTE - timedelta(days=30)).isoformat(), 4)  # außerhalb
    zeilen = bildtext(holen(graph_adresse(g, 14), w=30, h=6)[1])
    assert zeilen == ["Neu" + " " * 27, "keine werte in 14 tagen"]


def test_graph_weg_und_grenzen(gewicht):
    assert holen(graph_adresse("g_gibtsnicht")) == (404, {"fehler": "weg"})
    status, a = holen(graph_adresse(gewicht, 400))
    assert status == 400 and "365" in a["text"]
    assert kacheln.aktion({"adresse": graph_adresse(gewicht), "aktion": "oeffnen"}) \
        == (200, {"zeige": {"adresse": "zentrale://graph/" + gewicht}})
    assert holen(graph_adresse(gewicht, 30), w=0, h=0)[1]["bevorzugt"] == {"w": 60, "h": 6}


# ── Nur lesen ────────────────────────────────────────────────────────

def test_kacheln_schreiben_nie(einkauf, gewicht):
    lists.set_focus(einkauf, 1)
    vorher = _dateien()
    assert {"lists.json", "graphs.json", gewicht + ".json"} <= set(vorher)
    kacheln.katalog()
    for adr in (listen_adresse(einkauf, True), graph_adresse(gewicht)):
        for w, h in ((0, 0), (36, 12), (12, 2)):
            holen(adr, w=w, h=h, oben=3)
        kacheln.aktion({"adresse": adr, "aktion": "oeffnen"})
    assert _dateien() == vorher


def test_alte_wochenliste_wird_gelesen_aber_nicht_umgeschrieben(monkeypatch):
    """Die einmalige »week«-Migration (core/lists.py) läuft beim Lesen nur im
    Speicher — die Datei bleibt, wie Sasha sie hat."""
    alt = [{"id": "l_week", "name": "week", "next_item": 4, "items": [
        {"id": 1, "text": "mon", "items": [{"id": 2, "text": "Joggen", "done": False}]},
        {"id": 3, "text": "Lesen", "done": False}]}]
    with open(lists._REGISTRY, "w", encoding="utf-8") as f:
        json.dump(alt, f)
    monkeypatch.setattr(lists, "_week_migrated", False)
    vorher = _dateien()
    zeilen = bildtext(holen(listen_adresse("l_week"), h=6)[1])
    assert any("○ Joggen" in z for z in zeilen) and not any("mon" in z for z in zeilen)
    kacheln.katalog()
    assert _dateien() == vorher and lists._week_migrated is False


# ── Router der TUI: Adresse → Ansicht ────────────────────────────────

def test_router_oeffnet_liste_eintrag_und_graph():
    from tui.ansichten import sprung
    gesehen = []
    fokus = types.SimpleNamespace(zeige_liste=lambda lid, iid=None: gesehen.append(("l", lid, iid)) or True)
    graph = types.SimpleNamespace(zeige_graph=lambda gid: gesehen.append(("g", gid)) or True)
    DESK = {"active": True}
    zeigen = sprung.router_fuer(DESK, types.SimpleNamespace(), fokus, graph).zeigen
    assert zeigen("zentrale://fokus/l_einkauf") and DESK["active"] is False
    assert zeigen("zentrale://fokus/l_einkauf/12")
    assert zeigen("zentrale://graph/g_schlaf")
    assert not zeigen("zentrale://fokus")                           # kein Objekt
    assert not zeigen("zentrale://fokus/liste?liste=l_einkauf")     # eine Kachel, kein Objekt
    assert gesehen == [("l", "l_einkauf", None), ("l", "l_einkauf", 12), ("g", "g_schlaf")]
    ohne = sprung.router_fuer({}, types.SimpleNamespace())          # alte Aufrufer
    assert not ohne.kennt("zentrale://fokus/l_x") and not ohne.kennt("zentrale://graph/g_x")


def _api(monkeypatch, modul):
    """Die Ansicht fragt das echte Backend (Flask-Test-Client)."""
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    monkeypatch.setattr(modul, "api_call",
                        lambda pfad, method="GET", body=None, timeout=3.0:
                        c.open(pfad, method=method, json=body).get_json())


def test_listen_ansicht_springt_an_liste_ordner_und_punkt(monkeypatch, einkauf):
    from tui.ansichten import fokus as fokus_ansicht
    _api(monkeypatch, fokus_ansicht)
    f = fokus_ansicht.Fokus(types.SimpleNamespace())
    L = f.L
    assert f.zeige_liste(einkauf) and L["active"] and L["view"] == "view"
    assert L["def"]["id"] == einkauf and L["path"] == []
    f.zeige_liste(einkauf, 4)                                       # Ordner Baumarkt: hinein
    assert L["path"] == [4]
    f.zeige_liste(einkauf, 6)                                       # Dübel: Cursor drauf
    assert L["path"] == [4] and f.l_vitems()[L["isel"]]["text"] == "Dübel"
    f.zeige_liste(einkauf, 2)                                       # Brot ist erledigt
    assert L["showdone"] and f.l_vitems()[L["isel"]]["text"] == "Brot"
    f.zeige_liste("l_weg")
    assert L["active"] and L["view"] == "forest" and "nicht mehr" in L["msg"]


def test_graph_werkzeug_springt_an_den_graphen(monkeypatch, gewicht, schlaf):
    from tui.ansichten import graphen as graph_ansicht
    from ui.routen import erfassung
    monkeypatch.setattr(erfassung, "_DATA_DIR", graphs._DATA_DIR)  # /api/data liest dort
    _api(monkeypatch, graph_ansicht)
    g = graph_ansicht.Graphen(types.SimpleNamespace())
    G = g.G
    assert g.zeige_graph(schlaf) and G["active"] and G["view"] == "view"
    assert G["def"]["id"] == schlaf and G["shown"] == {schlaf} and G["vals"]
    g.zeige_graph("g_weg")
    assert G["view"] == "list" and "nicht mehr" in G["msg"]
