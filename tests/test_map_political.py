"""
Politisches / Konflikt-Overlay (core/map/layers/political.py).

Die Live-Quellen (UCDP, VIINA, ACLED) werden gemockt → Tests laufen offline +
deterministisch und hängen NICHT vom gitignorierten Cache ab. Der Sub-Layer
`borders` läuft ECHT gegen die committete Natural-Earth-GeoJSON (Integrations-
check, dass die Datei da ist und lädt).
"""
from map import layers
from map.layers import political, ucdp, viina, acled, borders
from map.projection import lonlat_to_world


# --- Registry / Provenienz -------------------------------------------------

def test_registry_lists_political_with_provenance():
    reg = layers.registry()
    meta = next(m for m in reg if m["id"] == "political")
    subs = {s["id"]: s for s in meta["subs"]}
    # UCDP: committbar (CC BY), zeitfähig
    assert subs["events-ucdp"]["source"]["commit_ok"] is True
    assert subs["events-ucdp"]["time"] is True
    # ACLED: lizenz-gesperrt → NICHT committen
    assert subs["events-acled"]["source"]["commit_ok"] is False
    # VIINA: committbar (ODbL), aber deklariert abgeleitet
    assert subs["control-ua"]["source"]["commit_ok"] is True
    assert subs["control-ua"]["source"].get("derived") is True
    # Grenzen: gemeinfrei
    assert subs["borders"]["source"]["commit_ok"] is True


def test_unknown_sub_returns_none():
    assert political.features(0, 0, 0, 80, 30, sub="troops") is None


def test_unknown_layer_via_registry_none():
    assert layers.layer_features("does-not-exist", 0, 0, 0, 80, 30) is None


# --- Ereignis-Punkte (UCDP), Projektion + Clipping -------------------------

def _fake_ucdp():
    # ein sichtbarer Punkt (Nahost) + einer am Südpol (jenseits Mercator → geclippt)
    kyiv = lonlat_to_world(30.5, 50.4)
    pole = lonlat_to_world(0.0, -84.0)
    return {
        "source": ucdp.SOURCE, "vintage": "2026-07-01",
        "items": [
            {"wx": kyiv[0], "wy": kyiv[1], "best": 12, "conflict": "Russia-Ukraine",
             "side_a": "Russia", "side_b": "Ukraine", "country": "Ukraine",
             "date": "2026-07-01", "tov": 1},
            {"wx": pole[0], "wy": pole[1], "best": 1, "conflict": "Südpol-Dummy",
             "date": "2026-06-01", "country": "Antarctica"},
        ],
    }


def test_ucdp_events_project_and_clip(monkeypatch):
    monkeypatch.setattr(ucdp, "events", _fake_ucdp)
    out = political.features(0.0, 20.0, 0.0, 120, 40, aspect=0.5, sub="events-ucdp")
    assert out["sub"] == "events-ucdp"
    assert out["source"]["name"].startswith("UCDP")
    assert out["vintage"] == "2026-07-01"
    names = {p["name"] for p in out["points"]}
    assert "Russia-Ukraine" in names          # sichtbar
    assert "Südpol-Dummy" not in names        # geclippt
    ev = next(p for p in out["points"] if p["name"] == "Russia-Ukraine")
    assert ev["value"] == 12                   # Todesopfer durchgereicht
    assert ev["cat"] == "event-ucdp"
    assert 0 <= ev["col"] <= 120 and 0 <= ev["row"] <= 40


def test_ucdp_unavailable_when_source_down(monkeypatch):
    monkeypatch.setattr(ucdp, "events", lambda: None)
    out = political.features(0.0, 20.0, 0.0, 120, 40, sub="events-ucdp")
    assert out["unavailable"] is True
    assert out["points"] == []


# --- VIINA-Kontrolle -------------------------------------------------------

def _fake_viina():
    kh = lonlat_to_world(36.3, 49.99)   # Charkiw-Region
    return {
        "source": viina.SOURCE, "vintage": "2026-07-20",
        "items": [
            {"wx": kh[0], "wy": kh[1], "name": "Kupiansk", "status": "RU",
             "status_dsm": "RU", "status_isw": "CONTESTED", "status_wiki": "RU"},
        ],
    }


def test_control_ua_points(monkeypatch):
    monkeypatch.setattr(viina, "control", _fake_viina)
    out = political.features(35.0, 49.0, 4.0, 120, 60, sub="control-ua")
    assert out["sub"] == "control-ua"
    pt = next(p for p in out["points"] if p["name"] == "Kupiansk")
    assert pt["cat"] == "control-ua"
    assert pt["status"] == "RU"
    assert pt["status_isw"] == "CONTESTED"     # Einzelquellen mitgeführt (vergleichbar)


# --- ACLED nur explizit, NICHT im Komposit ---------------------------------

def _fake_acled():
    x = lonlat_to_world(44.0, 33.3)    # Irak
    return {
        "source": acled.SOURCE, "vintage": "2026-07-19",
        "items": [
            {"wx": x[0], "wy": x[1], "best": 3, "event_type": "Battles",
             "sub_event_type": "Armed clash", "side_a": "Militia",
             "side_b": "Forces", "country": "Iraq", "date": "2026-07-19"},
        ],
    }


def test_acled_only_via_explicit_sub(monkeypatch):
    monkeypatch.setattr(acled, "events", _fake_acled)
    out = political.features(44.0, 33.0, 4.0, 120, 60, sub="events-acled")
    assert out["source"]["commit_ok"] is False        # lizenz-gesperrt, Provenienz da
    assert any(p["cat"] == "event-acled" for p in out["points"])


def test_acled_absent_from_composite(monkeypatch):
    # Selbst wenn ACLED Daten hätte: das Standard-Komposit zieht es NICHT.
    monkeypatch.setattr(acled, "events", _fake_acled)
    monkeypatch.setattr(ucdp, "events", lambda: None)
    monkeypatch.setattr(viina, "control", lambda: None)
    out = political.features(44.0, 33.0, 4.0, 120, 60)   # kein sub → Komposit
    assert not any(p.get("cat") == "event-acled" for p in out.get("points", []))


# --- Grenzen: echte committete GeoJSON -------------------------------------

def test_borders_loads_committed_geojson():
    data = borders.load()
    assert data is not None, "ne_10m_admin_0_disputed_areas.geojson fehlt im Repo"
    assert len(data["rings"]) > 0
    assert data["source"]["commit_ok"] is True


def test_borders_sub_lines_only(monkeypatch):
    # Weltsicht: umstrittene Gebiete existieren → Linien, aber KEINE points-Liste.
    out = political.features(80.0, 30.0, 1.0, 160, 80, sub="borders")
    assert out["sub"] == "borders"
    assert "points" not in out
    assert len(out.get("lines", [])) >= 1
    assert out["source"]["name"].startswith("Natural Earth")


# --- Komposit: mehrere Quellen gestapelt -----------------------------------

def test_composite_stacks_sources(monkeypatch):
    monkeypatch.setattr(ucdp, "events", _fake_ucdp)
    monkeypatch.setattr(viina, "control", _fake_viina)
    out = political.features(33.0, 49.0, 3.0, 160, 80)   # kein sub → Komposit
    assert out["sub"] == "all"
    cats = {p["cat"] for p in out["points"]}
    assert "event-ucdp" in cats
    assert "control-ua" in cats
    # mehrere Quellen mitgeführt (UCDP + VIINA + Natural Earth)
    names = {s["name"] for s in out["sources"]}
    assert any(n.startswith("UCDP") for n in names)
    assert any("VIINA" in n for n in names)
    assert out["unavailable"] is False
