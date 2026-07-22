# core/map/layers/ucdp.py
#
# Quelle für den Sub-Layer „events-ucdp" des politischen Overlays (Achse 2).
# Institution: UCDP — Uppsala Conflict Data Program, Uppsala Universität
# (https://ucdp.uu.se). Der Georeferenced Event Dataset (GED) ist DER
# wissenschaftliche Primär-Datensatz für einzelne bewaffnete Gewaltereignisse
# („die Punkte" — Gefechte, Luftangriffe, einseitige Gewalt), geokodiert bis auf
# Ortsebene, tagesgenau, peer-reviewed. Deckung 1989–heute → ideal auch für die
# spätere Zeitachse (Achse 3).
#
# WICHTIG — Lizenz/Provenienz (siehe memory/maps_quellen.md):
#   UCDP-Daten sind CC BY 4.0 → `commit_ok = True`: anders als IMF PortWatch
#   DARF ein abgeleiteter Auszug (mit Namensnennung) ins Repo. Wir holen die
#   Ereignisse trotzdem LIVE und cachen sie lokal (cache-first wie portwatch.py),
#   denn der Layer ist DYNAMISCH (neue Ereignisse laufend). Ein späterer,
#   committeter Snapshot ist erlaubt, aber nicht nötig für den Betrieb.
#
# Frische (A/B-Trennung, siehe maps_quellen.md):
#   • GED-Kern (`gedevents`) wird jährlich final veröffentlicht.
#   • Der UCDP Candidate Events Dataset liefert MONATLICH neue Ereignisse mit
#     höchstens ~1 Monat Verzug — das ist unser „tagesaktueller" Kanal. Über
#     UCDP_GED_VERSION die gewünschte (Candidate-)Version wählen.
#
# Zugang: Die API verlangt laut Doku einen kostenlosen Token
#   (Header `x-ucdp-access-token`, 5000 Anfragen/Tag). Token via Umgebungs-
#   variable UCDP_ACCESS_TOKEN; fehlt er, wird ohne Header versucht (ältere
#   Endpunkte gingen tokenfrei) — schlägt es fehl, liefert der Layer sauber
#   „keine Daten" (graceful, wie density ohne Ingest).

import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..projection import lonlat_to_world

# Provenienz — hängt an jeder Antwort.
SOURCE = {
    "name": "UCDP GED (Uppsala Conflict Data Program)",
    "url": "https://ucdp.uu.se",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "attribution": "UCDP/Uppsala Universität — Georeferenced Event Dataset",
    "commit_ok": True,       # CC BY 4.0 → abgeleiteter Auszug darf (mit Namensnennung) ins Repo
}

# Version des GED/Candidate-Datensatzes. Für Tagesaktualität eine Candidate-
# Version (Schema 26.0.X = Monat X) setzen; Default die letzte Jahres-Version.
_VERSION = os.environ.get("UCDP_GED_VERSION", "26.1")
_RESOURCE = os.environ.get("UCDP_GED_RESOURCE", "gedevents")
_BASE = "https://ucdpapi.pcr.uu.se/api/%s/%s" % (_RESOURCE, _VERSION)
_TOKEN = os.environ.get("UCDP_ACCESS_TOKEN")

# Der GED umfasst global >350k Ereignisse (1989–heute). Für die GEGENWARTS-
# Sicht cachen wir nur die JÜNGSTEN Ereignisse (nach date_start), gedeckelt —
# hält Cache klein und den Pi flott. Die volle Historie kommt mit Achse 3.
_MAX_EVENTS = int(os.environ.get("UCDP_MAX_EVENTS", "20000"))
_PAGESIZE = 1000
_MAX_PAGES = 500                # harte Obergrenze gegen Endlos-Pagination

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache")
_CACHE_FILE = os.path.join(_CACHE_DIR, "ucdp_ged.json")


def _get(url, timeout=30):
    """Eine GED-API-Seite als JSON. Wirft bei Netz-/Parse-Fehler (Aufrufer fängt)."""
    headers = {"User-Agent": "ZENTRALE-maps/1"}
    if _TOKEN:
        headers["x-ucdp-access-token"] = _TOKEN
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _event_item(a):
    """Eine GED-Ereigniszeile → schlankes, vorprojiziertes Item (oder None,
    wenn Koordinaten fehlen)."""
    lon, lat = a.get("longitude"), a.get("latitude")
    if lon is None or lat is None:
        return None
    wx, wy = lonlat_to_world(float(lon), float(lat))
    return {
        "id": a.get("id"),
        "lon": float(lon), "lat": float(lat), "wx": wx, "wy": wy,
        "date": a.get("date_start"),          # YYYY-MM-DD (tagesgenau)
        "best": a.get("best"),                # beste Todesopfer-Schätzung
        "tov": a.get("type_of_violence"),     # 1=staatl., 2=nicht-staatl., 3=einseitig
        "conflict": a.get("conflict_name"),
        "side_a": a.get("side_a"), "side_b": a.get("side_b"),
        "country": a.get("country"),
    }


def _fetch():
    """Live von der UCDP-API holen: jüngste GED-Ereignisse (paginiert), auf die
    _MAX_EVENTS neuesten gedeckelt. Gibt das fertige Cache-Payload (dict) zurück
    — schreibt NICHT selbst."""
    url = _BASE + "?" + urllib.parse.urlencode({"pagesize": _PAGESIZE, "page": 0})
    items = []
    for _ in range(_MAX_PAGES):
        data = _get(url)
        for f in data.get("Result", []):
            it = _event_item(f)
            if it is not None:
                items.append(it)
        nxt = data.get("NextPageUrl") or ""
        if not nxt:
            break
        url = nxt

    # Ein leeres Ergebnis NICHT als Cache verewigen (sonst liefert cache-first
    # für immer leer + retryt nie). Global-jüngst hat immer Ereignisse → 0 = Fehler.
    if not items:
        raise RuntimeError("UCDP: 0 Ereignisse geholt — nicht cachen")

    # jüngste zuerst; auf Deckel kürzen. Kein Datum → ganz nach hinten.
    items.sort(key=lambda it: it.get("date") or "", reverse=True)
    items = items[:_MAX_EVENTS]
    vintage = items[0]["date"]

    return {
        "schema": 1,
        "source": SOURCE,
        "version": _VERSION,
        "vintage": vintage,           # Datum des jüngsten gecachten Ereignisses
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(path, payload):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, path)             # atomar, kein halb-geschriebener Cache


def refresh():
    """Frisch holen UND cachen (Bootstrap / periodischer Job
    `python -m map.layers.ucdp`). Wirft bei Netzfehler weiter."""
    payload = _fetch()
    _write(_CACHE_FILE, payload)
    return payload


def events():
    """GED-Ereignisse (Sub-Layer events-ucdp) — CACHE-ONLY auf dem Anfrage-Pfad:
    liefert den lokalen Cache oder None. Bewusst KEIN Netz im Request (der Abruf
    paginiert potenziell zehntausende Ereignisse → würde den Request blockieren);
    Befüllen ausschließlich über refresh() / `python -m map.layers.ucdp` (Cron/
    manuell). Stand in `vintage`/`retrieved_at`; None → Layer zeigt „keine Daten"."""
    return _read(_CACHE_FILE)


if __name__ == "__main__":      # `python -m map.layers.ucdp` → Cache füllen
    p = refresh()
    print("UCDP GED gecacht: %d Ereignisse (jüngstes %s, Version %s) — geholt %s"
          % (p["count"], p["vintage"], p["version"], p["retrieved_at"]))
