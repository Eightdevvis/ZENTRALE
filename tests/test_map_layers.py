"""
Maps Achse-2-Overlay-Engine (core/map/layers + render.viewport).

Netzunabhängig: die einzige externe Quelle (IMF PortWatch) wird über
portwatch.chokepoints gemockt, damit die Tests offline + deterministisch laufen
und NICHT vom gitignorierten Cache abhängen.
"""
from map import render, layers
from map.layers import trade, portwatch
from map.projection import lonlat_to_world


def test_viewport_world_bounds():
    """Weltansicht (zoom 0): Bounds plausibel, Skalen positiv, Mitte normalisiert."""
    vp = render.viewport(0.0, 20.0, 0.0, 120, 40, aspect=0.5)
    assert vp["west"] < vp["east"]
    assert vp["south"] < vp["north"]
    assert vp["sx"] > 0 and vp["sy"] > 0
    assert vp["cols"] == 120 and vp["rows"] == 40


def test_viewport_projects_center_to_middle():
    """Der Viewport-Mittelpunkt landet in der Rastermitte (±halbe Zelle)."""
    cx, cy = 12.0, 48.0
    vp = render.viewport(cx, cy, 3.0, 100, 50, aspect=1.0)
    wx, wy = lonlat_to_world(cx, cy)
    col = (wx - vp["x0"]) * vp["sx"]
    row = (wy - vp["y0"]) * vp["sy"]
    assert abs(col - 50) < 1.0
    assert abs(row - 25) < 1.0


def test_registry_lists_trade_with_provenance():
    reg = layers.registry()
    trade_meta = next(m for m in reg if m["id"] == "trade")
    sub = next(s for s in trade_meta["subs"] if s["id"] == "chokepoints")
    assert sub["time"] is True                       # Tagesdaten → Achse 3
    assert sub["source"]["name"] == "IMF PortWatch"
    assert sub["source"]["commit_ok"] is False        # lizenziert → nicht committen


def test_unknown_layer_returns_none():
    assert layers.layer_features("does-not-exist", 0, 0, 0, 80, 30) is None


def _fake_payload():
    # zwei Punkte: einer in Weltsicht sichtbar, einer am extremen Südpol (geclippt)
    suez_wx, suez_wy = lonlat_to_world(32.4, 30.6)
    far_wx, far_wy = lonlat_to_world(0.0, -84.0)
    return {
        "source": portwatch.SOURCE,
        "vintage": "2026-06-07",
        "retrieved_at": "2026-06-07T00:00:00+00:00",
        "items": [
            {"name": "Suez Canal", "wx": suez_wx, "wy": suez_wy,
             "today": {"total": 54}, "year_total": 19787,
             "industries": ["Mineral Products", None, None]},
            {"name": "Südpol-Dummy", "wx": far_wx, "wy": far_wy,
             "today": {"total": 1}, "year_total": 9, "industries": [None]},
        ],
    }


def test_trade_features_projects_and_clips(monkeypatch):
    monkeypatch.setattr(portwatch, "chokepoints", _fake_payload)
    out = trade.features(0.0, 20.0, 0.0, 120, 40, aspect=0.5, sub="chokepoints")
    assert out["source"]["name"] == "IMF PortWatch"
    assert out["vintage"] == "2026-06-07"
    names = {p["name"] for p in out["points"]}
    assert "Suez Canal" in names                     # im Sichtfenster
    suez = next(p for p in out["points"] if p["name"] == "Suez Canal")
    assert suez["value"] == 54                        # heutiger Verkehr durchgereicht
    assert 0 <= suez["col"] <= 120 and 0 <= suez["row"] <= 40
    # Der Südpol-Punkt liegt jenseits der Mercator-Grenze → nicht im View.
    assert "Südpol-Dummy" not in names


def test_trade_features_unavailable_when_source_down(monkeypatch):
    monkeypatch.setattr(portwatch, "chokepoints", lambda: None)
    out = trade.features(0.0, 20.0, 0.0, 120, 40, sub="chokepoints")
    assert out["unavailable"] is True
    assert out["points"] == []
    assert out["source"]["name"] == "IMF PortWatch"   # Provenienz trotzdem da


def test_trade_unknown_sub_returns_none():
    assert trade.features(0, 0, 0, 80, 30, sub="pipelines") is None


def _fake_routes():
    # ein Segment quer durch die Weltsicht (Atlantik-nah)
    a = lonlat_to_world(-40.0, 20.0)
    b = lonlat_to_world(10.0, 10.0)
    c = lonlat_to_world(40.0, 30.0)
    return {"source": portwatch.SOURCE, "vintage": "2023-02-28",
            "retrieved_at": "2023-02-28T00:00:00+00:00",
            "segments": [[min(a[0], c[0]), min(a[1], b[1]),
                          max(a[0], c[0]), max(c[1], a[1]),
                          [list(a), list(b), list(c)]]]}


def test_trade_routes_projects_lines(monkeypatch):
    monkeypatch.setattr(portwatch, "routes", _fake_routes)
    out = trade.features(0.0, 20.0, 0.0, 120, 40, sub="routes")
    assert out["sub"] == "routes"
    assert len(out["lines"]) == 1
    assert len(out["lines"][0]) >= 2          # projizierte Polylinie
    assert "points" not in out                # nur Linien bei sub=routes
    assert out["vintage"] == "2023-02-28"


def test_trade_composite_has_both(monkeypatch):
    monkeypatch.setattr(portwatch, "routes", _fake_routes)
    monkeypatch.setattr(portwatch, "chokepoints", _fake_payload)
    out = trade.features(0.0, 20.0, 0.0, 120, 40)   # kein sub → Komposit
    assert out["sub"] == "all"
    assert len(out["lines"]) == 1
    assert any(p["name"] == "Suez Canal" for p in out["points"])
    # tagesaktueller Chokepoint-Stand gewinnt über statischen Routen-Stand
    assert out["vintage"] == "2026-06-07"
    assert out["unavailable"] is False


def test_project_polyline_simplifies():
    vp = render.viewport(0.0, 20.0, 0.0, 100, 40, aspect=0.5)
    a = lonlat_to_world(0.0, 0.0)
    line = render.project_polyline(vp, [a, a, a])   # selbe Zelle → kollabiert
    assert len(line) == 1
