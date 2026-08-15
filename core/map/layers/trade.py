# core/map/layers/trade.py
#
# Das Handelsrouten-Overlay (Achse 2). KOMPOSIT aus Sub-Layern, jeder mit EINER
# offiziellen Quelle + mitgeführter Provenienz (siehe memory/maps/maps_quellen.md):
#   • routes      — Welt-Schifffahrtsrouten als LINIEN (Struktur, statisch).
#   • chokepoints — maritime Engstellen als PUNKTE + täglicher Schiffsverkehr.
# Beide aus IMF PortWatch. Ohne `sub` (oder sub='all') liefert die Engine das
# Komposit (Linien + Punkte) — so wird das „Handelsrouten"-Dach seinem Namen
# gerecht: man sieht die Wege UND die Engstellen.

from .. import render
from . import portwatch

META = {
    "id": "trade",
    "name": "Handelsrouten",
    "subs": [
        {"id": "routes", "name": "Schifffahrtsrouten", "kind": "lines",
         "time": False, "source": portwatch.SOURCE},
        {"id": "chokepoints", "name": "Chokepoints (Schiffsverkehr)",
         "kind": "points", "time": True, "source": portwatch.SOURCE},
    ],
}

_SUBS = ("all", "routes", "chokepoints")


def _routes_lines(vp):
    """Routensegmente, die den Viewport berühren, aufs Zellraster projiziert."""
    data = portwatch.routes()
    if not data:
        return [], None
    lines = []
    for seg in data["segments"]:
        minx, miny, maxx, maxy, pts = seg
        if maxx < vp["x0"] or minx > vp["x1"] or maxy < vp["y0"] or miny > vp["y1"]:
            continue
        proj = render.project_polyline(vp, pts)
        if len(proj) >= 2:
            lines.append(proj)
    return lines, data.get("vintage")


def _choke_points(vp):
    """Chokepoint-Punkte im Viewport, projiziert + mit Tagesverkehr."""
    data = portwatch.chokepoints()
    if not data:
        return [], None
    pts = []
    for it in data["items"]:
        wx, wy = it["wx"], it["wy"]
        if not (vp["x0"] <= wx <= vp["x1"] and vp["y0"] <= wy <= vp["y1"]):
            continue
        pts.append({
            "name": it["name"],
            "col": round((wx - vp["x0"]) * vp["sx"], 2),
            "row": round((wy - vp["y0"]) * vp["sy"], 2),
            "value": (it.get("today") or {}).get("total"),
            "cat": "chokepoint",
            "today": it.get("today"),
            "year_total": it.get("year_total"),
            "industries": it.get("industries"),
        })
    return pts, data.get("vintage")


def features(cx, cy, zoom, cols, rows, aspect=0.5, sub=None, at=None):
    """Features des Handelsrouten-Overlays, projiziert aufs Zellraster der Front
    (gleiche viewport()-Mathematik wie die Basiskarte → passgenau).

    sub: 'routes' (nur Linien), 'chokepoints' (nur Punkte), sonst Komposit (beide).
    Rückgabe (JSON-fähig): center/zoom/bounds/cols/rows + source/vintage +
      lines:[[[col,row],…],…]   (Routen, falls enthalten)
      points:[{name,col,row,value,…},…]   (Chokepoints, falls enthalten)
    None bei unbekanntem Sub-Layer."""
    sub = sub or "all"
    if sub not in _SUBS:
        return None

    vp = render.viewport(cx, cy, zoom, cols, rows, aspect)
    out = {
        "center": [vp["cx"], vp["cy"]], "zoom": vp["zoom"],
        "bounds": [vp["west"], vp["south"], vp["east"], vp["north"]],
        "cols": vp["cols"], "rows": vp["rows"], "sub": sub,
        "source": portwatch.SOURCE,
    }

    routes_vintage = choke_vintage = None
    if sub in ("all", "routes"):
        out["lines"], routes_vintage = _routes_lines(vp)
    if sub in ("all", "chokepoints"):
        out["points"], choke_vintage = _choke_points(vp)

    # Stand: der tagesaktuelle Chokepoint-Stand ist der aussagekräftige; sonst
    # der (statische) Routen-Stand.
    out["vintage"] = choke_vintage or routes_vintage
    out["routes_vintage"] = routes_vintage
    out["unavailable"] = (not out.get("lines")) and (not out.get("points"))
    return out
