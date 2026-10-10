"""
„Ein Objekt, eine Adresse" (Sasha, 2026-10-10; memory/system/hub_bauplan.md
„Adressen"): core/adressen.py baut und liest zentrale://<app>/<pfad>?…,
die TUI baut dieselbe Schreibweise (desk_neu.adresse) und bildet Adressen
über einen Router auf Ansichten ab (tui/ansichten/sprung.py).
"""
import types
from datetime import date

import pytest

import adressen
from tui.ansichten import desk_neu, sprung


@pytest.mark.parametrize("app,pfad,abfrage", [
    ("kalender", ["2026-10-12"], {}),
    ("kalender", ["ausschnitt"], {"modus": "mitlaufend", "tage": "7"}),
    ("kalender", ["ausschnitt"], {"modus": "fest", "von": "2026-10-12", "bis": "2026-10-18"}),
    ("fokus", ["liste", "l_einkauf"], {}),
    ("notizen", ["Größe & Gewicht/2"], {"q": "a b&c=d", "leer": ""}),
    ("graph", [], {}),
])
def test_bauen_lesen_hin_und_zurueck(app, pfad, abfrage):
    text = adressen.bauen(app, pfad, abfrage)
    a = adressen.lesen(text)
    assert (a.app, list(a.pfad), a.abfrage) == (app, pfad, abfrage)
    assert adressen.kanonisch(text) == text
    assert text.startswith("zentrale://" + app)


def test_eine_schreibweise_je_objekt():
    a = adressen.bauen("kalender", ["ausschnitt"], {"tage": 7, "modus": "mitlaufend"})
    b = adressen.bauen("kalender", ["ausschnitt"], {"modus": "mitlaufend", "tage": "7"})
    assert a == b == "zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7"
    assert adressen.kanonisch("zentrale://kalender/ausschnitt?tage=7&modus=mitlaufend") == a
    assert adressen.bauen("x", ["y"], {"an": True, "aus": False}) == "zentrale://x/y?an=true&aus=false"


@pytest.mark.parametrize("text", [
    None, "", "kalender/2026-10-12", "https://kalender/2026-10-12",
    "zentrale:///ohne-app", "zentrale://Kalender/x", "zentrale://kalender/a//b",
    "zentrale://kalender/x#stelle", "zentrale://kalender/x?a=1&a=2",
    "zentrale://kalender/" + "x" * 3000,
])
def test_kaputtes_wird_abgelehnt(text):
    with pytest.raises(adressen.AdresseFehler):
        adressen.lesen(text)


def test_alter_verweis_wird_adresse():
    assert adressen.aus_verweis("kalender", "ausschnitt", {"modus": "mitlaufend", "tage": 7}) \
        == "zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7"
    with pytest.raises(adressen.AdresseFehler):
        adressen.aus_verweis("kalender", "ausschnitt", {"tief": {"x": 1}})


def test_tui_baut_dieselbe_schreibweise_wie_der_kern():
    for werte in ({"modus": "mitlaufend", "tage": 7},
                  {"modus": "fest", "von": "2026-10-12", "bis": "2026-10-18"},
                  {"an": True, "name": "ä ö/&"}):
        assert desk_neu.adresse("kalender", "ausschnitt", werte) \
            == adressen.bauen("kalender", ["ausschnitt"], werte)
        a = sprung.lesen(desk_neu.adresse("kalender", "ausschnitt", werte))
        assert a == ("kalender", ("ausschnitt",), {k: adressen.wert_text(v) for k, v in werte.items()})


# ── Router der TUI ────────────────────────────────────────────────────

def test_router_reicht_an_den_handler_der_app():
    r = sprung.Router()
    gesehen = []
    r.registrieren("kalender", lambda pfad, abfrage: gesehen.append((pfad, abfrage)) or True)
    assert r.zeigen("zentrale://kalender/2026-10-12")
    assert r.zeigen("zentrale://kalender/ausschnitt?modus=fest&von=2026-10-12")
    assert gesehen == [(("2026-10-12",), {}), (("ausschnitt",), {"modus": "fest", "von": "2026-10-12"})]
    assert not r.zeigen("zentrale://fokus/liste/l1")            # keine App eingetragen
    assert not r.zeigen("https://kalender/2026-10-12")
    assert not r.zeigen(None)
    assert r.kennt("zentrale://kalender/x") and not r.kennt("zentrale://graph/x")


def test_router_der_tui_oeffnet_den_kalender_am_tag():
    tage = []
    kal = types.SimpleNamespace(geoeffnet=0,
                                bedienung=types.SimpleNamespace(setze_tag=tage.append))
    kal.oeffnen = lambda: setattr(kal, "geoeffnet", kal.geoeffnet + 1)
    DESK = {"active": True}
    zeigen = sprung.router_fuer(DESK, kal).zeigen
    assert zeigen("zentrale://kalender/2026-10-12")
    assert DESK["active"] is False and kal.geoeffnet == 1 and tage == [date(2026, 10, 12)]
    assert zeigen("zentrale://kalender/ausschnitt?bis=2026-10-18&modus=fest&von=2026-10-14")
    assert tage[-1] == date(2026, 10, 14)
    assert zeigen("zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7")   # heute: kein Tag gesetzt
    assert len(tage) == 2 and kal.geoeffnet == 3


# ── Zurück zum Öffner (2026-10-10) ────────────────────────────────────

def test_router_bringt_den_oeffner_zurueck_wenn_die_ansicht_zugeht():
    r = sprung.Router()
    ziel = {"active": False}
    zurueck = []
    r.registrieren("kalender", lambda pfad, abfrage: ziel.update(active=True) or True, ziel)
    r.registrieren("fremd", lambda pfad, abfrage: True)          # ohne Zustand
    assert r.zeigen("zentrale://kalender/2026-10-12", zurueck=lambda: zurueck.append(1))
    assert not r.nachsehen() and zurueck == []
    ziel["active"] = False
    assert r.nachsehen() and zurueck == [1]
    assert not r.nachsehen() and zurueck == [1]
    # ohne zurueck, ohne Zustand oder wenn nichts aufging: nichts gemerkt
    assert r.zeigen("zentrale://kalender/2026-10-12")
    ziel["active"] = False
    assert r.zeigen("zentrale://fremd/x", zurueck=lambda: zurueck.append(2))
    assert not r.nachsehen() and zurueck == [1]


def test_router_der_tui_traegt_die_zustaende_der_ansichten_ein():
    K, L, G = {"active": False}, {"active": False}, {"active": False}
    kal = types.SimpleNamespace(K=K, oeffnen=lambda: K.update(active=True),
                                bedienung=types.SimpleNamespace(setze_tag=lambda t: None))
    fokus = types.SimpleNamespace(L=L, zeige_liste=lambda lid, iid=None: L.update(active=True) or True)
    graph = types.SimpleNamespace(G=G, zeige_graph=lambda gid: G.update(active=True) or True)
    DESK = {"active": True}
    r = sprung.router_fuer(DESK, kal, fokus, graph)
    for adresse, zustand in (("zentrale://kalender/2026-10-12", K),
                             ("zentrale://fokus/l_x", L), ("zentrale://graph/g_x", G)):
        DESK["active"] = True
        assert r.zeigen(adresse, zurueck=lambda: DESK.update(active=True))
        assert not DESK["active"] and zustand["active"]
        zustand["active"] = False
        assert r.nachsehen() and DESK["active"]
