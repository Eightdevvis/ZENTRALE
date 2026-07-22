# core/map/layers/political.py
#
# Das politische / Konflikt-Overlay (Achse 2) — der „liveuamap-Gedanke", aber aus
# seriösen Primärquellen und nach der Charter (memory/maps_quellen.md): KOMPOSIT
# aus Sub-Layern, jeder mit GENAU EINER Quelle + mitgeführter Provenienz, jeder
# einzeln togglebar (STAPELN statt verschmelzen — Quellen bleiben vergleichbar).
#
#   • events-ucdp  — bewaffnete Gewaltereignisse als PUNKTE (UCDP GED, CC BY,
#                    weltweit, wissenschaftlicher Primär-Datensatz).
#   • control-ua   — Gebietskontrolle Ukraine als PUNKTE je Ort (VIINA, ODbL;
#                    deklariert abgeleitet — Mehrheitsvotum DeepStateMap/ISW/Wiki).
#   • borders      — umstrittene/abtrünnige Gebiete als LINIEN (Natural Earth, PD).
#   • events-acled — reichere Ereignisse als PUNKTE (ACLED). NUR per ?sub=…, weil
#                    lizenz-gesperrt (nur lokal cachen, nie committen) → NICHT im
#                    Standard-Komposit.
#
# Ohne `sub` (oder sub='all') liefert die Engine das Komposit aus den drei
# COMMITTBAREN Quellen (UCDP + VIINA + Grenzen). ?sub=<id> adressiert einzeln.
#
# Achse 3 (Zeit): die Ereignis-/Kontroll-Sublayer sind zeitfähig (`time: True`,
# UCDP deckt 1989–heute) — der `at`-Parameter wird HEUTE noch ignoriert
# (Gegenwarts-Layer zuerst, Zeitstrahl kommt danach; siehe maps_system.md).

from .. import render
from . import ucdp, acled, viina, borders

META = {
    "id": "political",
    "name": "Politik / Konflikt",
    "subs": [
        {"id": "events-ucdp", "name": "Konfliktereignisse (UCDP)", "kind": "points",
         "time": True, "source": ucdp.SOURCE},
        {"id": "control-ua", "name": "Gebietskontrolle Ukraine (VIINA)",
         "kind": "points", "time": True, "source": viina.SOURCE},
        {"id": "borders", "name": "Umstrittene Gebiete", "kind": "lines",
         "time": False, "source": borders.SOURCE},
        {"id": "events-acled", "name": "Konfliktereignisse (ACLED, nur lokal)",
         "kind": "points", "time": True, "source": acled.SOURCE},
    ],
}

_SUBS = ("all", "events-ucdp", "control-ua", "borders", "events-acled")

# Deckel je Sub-Layer pro Viewport — hält die Antwort klein (ein kleiner
# Ausschnitt kann tausende Ereignisse enthalten). Bei Überschreitung gewinnen
# die stärksten (meiste Todesopfer) und `truncated` wird gesetzt (ehrlich, keine
# stille Kürzung — Charter).
_MAX_POINTS = 3000


def _in_view(vp, wx, wy):
    return vp["x0"] <= wx <= vp["x1"] and vp["y0"] <= wy <= vp["y1"]


def _event_points(vp, payload, src_tag):
    """Ereignis-Items (UCDP/ACLED, gleiches Schema) → projizierte Punkte im
    Viewport. Rückgabe (points, vintage, source, truncated)."""
    if not payload:
        return [], None, None, False
    pts = []
    for it in payload.get("items", []):
        wx, wy = it["wx"], it["wy"]
        if not _in_view(vp, wx, wy):
            continue
        # Name für den Fokus-Text: Konfliktname (UCDP) bzw. Ereignistyp (ACLED).
        name = (it.get("conflict") or it.get("event_type")
                or it.get("country") or "Ereignis")
        pts.append({
            "name": name,
            "col": round((wx - vp["x0"]) * vp["sx"], 2),
            "row": round((wy - vp["y0"]) * vp["sy"], 2),
            "value": it.get("best"),          # Todesopfer-Schätzung
            "cat": "event-" + src_tag,        # event-ucdp / event-acled
            "src": src_tag,
            "date": it.get("date"),
            "side_a": it.get("side_a"), "side_b": it.get("side_b"),
            "country": it.get("country"),
            "tov": it.get("tov"),
            "event_type": it.get("event_type"),
            "sub_event_type": it.get("sub_event_type"),
        })
    truncated = False
    if len(pts) > _MAX_POINTS:
        pts.sort(key=lambda p: (p["value"] or 0), reverse=True)
        pts = pts[:_MAX_POINTS]
        truncated = True
    return pts, payload.get("vintage"), payload.get("source"), truncated


def _control_points(vp, payload):
    """VIINA-Kontroll-Items → projizierte Punkte im Viewport (je Ort ein Punkt,
    eingefärbt nach Konsens-Status). Rückgabe (points, vintage, source, truncated)."""
    if not payload:
        return [], None, None, False
    pts = []
    for it in payload.get("items", []):
        wx, wy = it["wx"], it["wy"]
        if not _in_view(vp, wx, wy):
            continue
        pts.append({
            "name": it.get("name") or "?",
            "col": round((wx - vp["x0"]) * vp["sx"], 2),
            "row": round((wy - vp["y0"]) * vp["sy"], 2),
            "value": None,
            "cat": "control-ua",
            "src": "viina",
            "status": it.get("status"),           # Konsens (UA/RU/CONTESTED)
            "status_dsm": it.get("status_dsm"),
            "status_isw": it.get("status_isw"),
            "status_wiki": it.get("status_wiki"),
        })
    truncated = False
    if len(pts) > _MAX_POINTS:
        pts = pts[:_MAX_POINTS]
        truncated = True
    return pts, payload.get("vintage"), payload.get("source"), truncated


def _border_lines(vp):
    """Umstrittene-Gebiete-Ringe, die den Viewport berühren, aufs Zellraster
    projiziert. Rückgabe (lines, vintage, source)."""
    data = borders.load()
    if not data:
        return [], None, None
    lines = []
    for minx, miny, maxx, maxy, pts, _name, _cla in data["rings"]:
        if maxx < vp["x0"] or minx > vp["x1"] or maxy < vp["y0"] or miny > vp["y1"]:
            continue
        proj = render.project_polyline(vp, pts)
        if len(proj) >= 2:
            lines.append(proj)
    return lines, data.get("vintage"), data.get("source")


def features(cx, cy, zoom, cols, rows, aspect=0.5, sub=None, at=None):
    """Features des politischen Overlays, projiziert aufs Zellraster der Front
    (gleiche viewport()-Mathematik wie die Basiskarte → passgenau).

    sub: 'events-ucdp' | 'control-ua' | 'borders' | 'events-acled' | sonst
         Komposit (UCDP-Ereignisse + VIINA-Kontrolle + Grenzen; ACLED NUR explizit).
    at:  Achse 3 (Zeit) — HEUTE ignoriert (Gegenwarts-Layer zuerst).
    Rückgabe (JSON-fähig): center/zoom/bounds/cols/rows/sub + sources/source/vintage +
      points:[{name,col,row,value,cat,…},…]   (Ereignisse und/oder Kontrolle)
      lines:[[[col,row],…],…]                  (umstrittene Gebiete, falls enthalten)
    None bei unbekanntem Sub-Layer."""
    sub = sub or "all"
    if sub not in _SUBS:
        return None

    vp = render.viewport(cx, cy, zoom, cols, rows, aspect)
    out = {
        "center": [vp["cx"], vp["cy"]], "zoom": vp["zoom"],
        "bounds": [vp["west"], vp["south"], vp["east"], vp["north"]],
        "cols": vp["cols"], "rows": vp["rows"], "sub": sub,
    }

    points = []
    sources = []
    vintages = []
    truncated = False

    # Provenienz wird aus den SOURCE-Konstanten der AKTIVEN Sub-Layer gesammelt
    # — unabhängig davon, ob gerade Daten im Cache sind. So trägt die Antwort
    # „wer sagt das" IMMER (Charter), auch wenn ein Sub-Layer leer ist.
    if sub in ("all", "events-ucdp"):
        sources.append(ucdp.SOURCE)
        p, v, _s, t = _event_points(vp, ucdp.events(), "ucdp")
        points += p
        truncated = truncated or t
        if v:
            vintages.append(v)

    # ACLED bewusst NUR bei explizitem sub (lizenz-gesperrt → nicht im Komposit).
    if sub == "events-acled":
        sources.append(acled.SOURCE)
        p, v, _s, t = _event_points(vp, acled.events(), "acled")
        points += p
        truncated = truncated or t
        if v:
            vintages.append(v)

    if sub in ("all", "control-ua"):
        sources.append(viina.SOURCE)
        p, v, _s, t = _control_points(vp, viina.control())
        points += p
        truncated = truncated or t
        if v:
            vintages.append(v)

    if sub in ("all", "borders"):
        sources.append(borders.SOURCE)
        lines, v, _s = _border_lines(vp)
        if lines:
            out["lines"] = lines
        if v:
            vintages.append(v)

    if sub != "borders":
        out["points"] = points

    out["sources"] = sources
    out["source"] = sources[0] if sources else None    # Kompat: erste Quelle
    out["vintage"] = max(vintages) if vintages else None
    out["truncated"] = truncated
    out["unavailable"] = (not points) and (not out.get("lines"))
    return out
