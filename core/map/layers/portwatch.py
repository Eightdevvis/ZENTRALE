# core/map/layers/portwatch.py
#
# Quelle für den Sub-Layer „Chokepoints" des Handelsrouten-Overlays.
# Institution: IMF PortWatch (https://portwatch.imf.org) — offizielle,
# TÄGLICH aktualisierte Schätzungen des Schiffsverkehrs an den großen
# maritimen Engstellen (Suez, Panama, Hormuz, Malakka, …).
#
# WICHTIG — Lizenz/Provenienz (siehe memory/maps_quellen.md):
#   PortWatch-Daten sind NICHT public domain (anders als Natural Earth). Die
#   IMF-Terms erlauben Anzeige mit Namensnennung, aber keine Weiterverteilung.
#   Konsequenz, die dieser Code erzwingt:
#     • Daten werden LIVE von der ArcGIS-API geholt und nur LOKAL gecacht
#       (Cache = letzte bekannte Lage, fürs Offline-Substrat) — wie ein
#       Browser-Cache, KEINE Weitergabe an Dritte.
#     • Der Cache liegt unter data/cache/ und ist .gitignore't → die Daten
#       landen NIE im Repo (nur Natural Earth, das gemeinfrei ist, wird
#       committet).
#     • Jedes Feature trägt seine Provenienz mit (source/url/license/
#       retrieved_at/vintage), damit die UI „wer sagt das, wann erhoben"
#       zeigen kann.
#
# Mechanik: zwei ArcGIS-FeatureServer-Layer werden per `portid` gejoint:
#   • PortWatch_chokepoints_database  → STRUKTUR: 28 Punkte (lat/lon, Name,
#     Durchschnitts-Verkehr, Top-Industrien). Ändert sich selten.
#   • Daily_Chokepoints_Data          → DYNAMIK: Tageszeile je Chokepoint
#     (n_total, n_tanker, … capacity). Wir ziehen NUR das jüngste Datum.

import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..projection import lonlat_to_world

# Provenienz — hängt an jeder Antwort. license bewusst knapp + verlinkt.
SOURCE = {
    "name": "IMF PortWatch",
    "url": "https://portwatch.imf.org",
    "license": "IMF Terms — Anzeige mit Namensnennung, keine Weiterverteilung",
    "license_url": "https://www.imf.org/en/about/copyright-and-terms",
    "commit_ok": False,      # NICHT ins Git-Repo (nur lokal cachen)
}

_ARCGIS = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/"
           "services")
_CHOKE_GEO = _ARCGIS + "/PortWatch_chokepoints_database/FeatureServer/0/query"
_CHOKE_DAILY = _ARCGIS + "/Daily_Chokepoints_Data/FeatureServer/0/query"

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache")
_CACHE_FILE = os.path.join(_CACHE_DIR, "portwatch_chokepoints.json")


def _get(url, params, timeout=20):
    """Eine ArcGIS-Query als JSON. Wirft bei Netz-/Parse-Fehler (Aufrufer fängt)."""
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "ZENTRALE-maps/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch():
    """Live von PortWatch holen: Geometrie + jüngste Tagesdaten, gejoint.
    Gibt das fertige Cache-Payload (dict) zurück — schreibt NICHT selbst."""
    geo = _get(_CHOKE_GEO, {
        "where": "1=1",
        "outFields": ("portid,portname,fullname,lat,lon,vessel_count_total,"
                      "vessel_count_tanker,vessel_count_container,"
                      "vessel_count_dry_bulk,industry_top1,industry_top2,"
                      "industry_top3"),
        "outSR": "4326", "returnGeometry": "false", "f": "json",
    })

    # Jüngstes verfügbares Datum der Tagesdaten ermitteln (max(date)).
    stat = _get(_CHOKE_DAILY, {
        "where": "1=1",
        "outStatistics": json.dumps([{
            "statisticType": "max", "onStatisticField": "date",
            "outStatisticFieldName": "maxd"}]),
        "f": "json",
    })
    # ArcGIS liefert max(dateOnly) je nach Layer als ISO-String ("2026-06-07")
    # ODER als Epoch-Millis — beides abfangen.
    mv = stat["features"][0]["attributes"]["maxd"]
    if isinstance(mv, str):
        d = datetime.strptime(mv[:10], "%Y-%m-%d")
    else:
        d = datetime.fromtimestamp(mv / 1000.0, tz=timezone.utc)
    y, m, day = d.year, d.month, d.day

    # Nur die Zeilen dieses Tages. Über die Integer-Felder filtern (robust gegen
    # ArcGIS-Datumsformat-Eigenheiten).
    daily = _get(_CHOKE_DAILY, {
        "where": "year=%d AND month=%d AND day=%d" % (y, m, day),
        "outFields": ("portid,n_total,n_container,n_dry_bulk,"
                      "n_general_cargo,n_roro,n_tanker,capacity"),
        "returnGeometry": "false", "f": "json",
    })
    by_id = {f["attributes"]["portid"]: f["attributes"]
             for f in daily.get("features", [])}

    items = []
    for f in geo.get("features", []):
        a = f["attributes"]
        lon, lat = a.get("lon"), a.get("lat")
        if lon is None or lat is None:
            continue
        wx, wy = lonlat_to_world(lon, lat)
        dy = by_id.get(a["portid"], {})
        items.append({
            "portid": a["portid"],
            "name": a.get("fullname") or a.get("portname") or "?",
            "lon": lon, "lat": lat, "wx": wx, "wy": wy,
            # heutiger Verkehr (Dynamik) …
            "today": {
                "total": dy.get("n_total"), "tanker": dy.get("n_tanker"),
                "container": dy.get("n_container"),
                "dry_bulk": dy.get("n_dry_bulk"),
                "general_cargo": dy.get("n_general_cargo"),
                "roro": dy.get("n_roro"), "capacity": dy.get("capacity"),
            },
            # … vs. Jahressumme (Struktur-Kontext), plus Top-Industrien
            "year_total": a.get("vessel_count_total"),
            "industries": [a.get("industry_top1"), a.get("industry_top2"),
                           a.get("industry_top3")],
        })

    return {
        "schema": 1,
        "source": SOURCE,
        "vintage": "%04d-%02d-%02d" % (y, m, day),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
    }


def _read_cache():
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_cache(payload):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    tmp = _CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, _CACHE_FILE)      # atomar, kein halb-geschriebener Cache


def refresh():
    """Frische Daten holen UND cachen. Für Bootstrap / periodischen Job
    (`python -m map.layers.portwatch`). Wirft bei Netzfehler weiter."""
    payload = _fetch()
    _write_cache(payload)
    return payload


def chokepoints():
    """Chokepoint-Daten fürs Overlay (Offline-zuerst): liefert IMMER aus dem
    lokalen Cache, ohne pro Anfrage ins Netz zu gehen (sonst friert ein
    pollendes Frontend ein). Fehlt der Cache komplett, wird EINMAL gebootstrappt.
    Aktualisiert wird über refresh() (Cron/manuell) — der Stand steht in
    `vintage`/`retrieved_at`, die Front zeigt ihn an.

    Rückgabe: das Cache-Payload (siehe _fetch) oder None, wenn weder Cache noch
    Netz verfügbar (Front zeigt dann „Quelle nicht erreichbar")."""
    cached = _read_cache()
    if cached is not None:
        return cached
    try:
        return refresh()
    except Exception:
        return None


if __name__ == "__main__":      # `python -m map.layers.portwatch` → Cache füllen
    p = refresh()
    print("PortWatch-Chokepoints gecacht: %d Punkte, Stand %s (geholt %s)"
          % (len(p["items"]), p["vintage"], p["retrieved_at"]))
