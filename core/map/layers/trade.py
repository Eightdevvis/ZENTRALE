# core/map/layers/trade.py
#
# Das Handelsrouten-Overlay (Achse 2, erster thematischer Layer). Es ist ein
# KOMPOSIT: es morpht sich aus mehreren Sub-Layern, jeder mit EINER eigenen
# offiziellen Quelle (so bleiben Quellen getrennt + gegeneinander abgleichbar,
# statt vermatscht — siehe memory/maps_quellen.md). Jedes Feature trägt seine
# Provenienz mit.
#
# Sub-Layer (wachsend):
#   • chokepoints — IMF PortWatch, maritime Engstellen + täglicher Schiffsverkehr.
#   (geplant: routes = Global_Shipping_Routes, cables = TeleGeography, …)

from .. import render
from . import portwatch

# Registry-Eintrag für /api/map/layers. `subs` listet die Sub-Layer mit Meta
# (Quelle + ob sie eine Zeitachse haben — Achse 3).
META = {
    "id": "trade",
    "name": "Handelsrouten",
    "subs": [
        {
            "id": "chokepoints",
            "name": "Chokepoints (Schiffsverkehr)",
            "kind": "points",
            "time": True,                 # Tagesdaten → zeitfähig (Achse 3)
            "source": portwatch.SOURCE,
        },
    ],
}

_DEFAULT_SUB = "chokepoints"


def features(cx, cy, zoom, cols, rows, aspect=0.5, sub=None, at=None):
    """Features eines Sub-Layers, projiziert auf das Zellraster der Front —
    dieselbe viewport()-Mathematik wie die Basiskarte (Overlays sitzen passgenau).

    Rückgabe (JSON-fähig): center/zoom/bounds/cols/rows wie base_features, plus
      sub, source, vintage, retrieved_at   — Provenienz
      points: [{name, col, row, value, cat, today, avg_total, industries}, …]
    oder None bei unbekanntem Sub-Layer / fehlender Quelle."""
    sub = sub or _DEFAULT_SUB
    if sub != "chokepoints":
        return None

    data = portwatch.chokepoints()
    vp = render.viewport(cx, cy, zoom, cols, rows, aspect)
    base = {
        "center": [vp["cx"], vp["cy"]], "zoom": vp["zoom"],
        "bounds": [vp["west"], vp["south"], vp["east"], vp["north"]],
        "cols": vp["cols"], "rows": vp["rows"], "sub": sub,
    }
    if data is None:                      # weder Cache noch Netz
        base.update({"source": portwatch.SOURCE, "vintage": None,
                     "retrieved_at": None, "points": [], "unavailable": True})
        return base

    pts = []
    for it in data["items"]:
        wx, wy = it["wx"], it["wy"]
        # nur was im Sichtfenster liegt (Punkt-Clipping)
        if not (vp["x0"] <= wx <= vp["x1"] and vp["y0"] <= wy <= vp["y1"]):
            continue
        pts.append({
            "name": it["name"],
            "col": round((wx - vp["x0"]) * vp["sx"], 2),
            "row": round((wy - vp["y0"]) * vp["sy"], 2),
            "value": (it.get("today") or {}).get("total"),   # heutige Schiffe
            "cat": "chokepoint",
            "today": it.get("today"),
            "year_total": it.get("year_total"),
            "industries": it.get("industries"),
        })

    base.update({
        "source": data["source"], "vintage": data["vintage"],
        "retrieved_at": data["retrieved_at"], "points": pts,
    })
    return base
