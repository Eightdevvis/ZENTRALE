# core/map/layers/acled.py
#
# Quelle für den optionalen Sub-Layer „events-acled" des politischen Overlays.
# Institution: ACLED — Armed Conflict Location & Event Data (https://acleddata.com).
# Reicher als UCDP (mehr Ereignistypen, u.a. als Einziges nicht-gewaltsame
# „Strategic Developments" wie Truppenverlegungen), akademischer Primär-Datensatz.
#
# WICHTIG — Lizenz/Provenienz (siehe memory/maps/maps_quellen.md):
#   ACLED ist NICHT offen lizenziert. Das EULA erlaubt nur nicht-kommerzielle
#   Nutzung und VERBIETET Weiterverteilung/Republishing der Rohdaten. Konsequenz,
#   die dieser Code erzwingt — exakt wie IMF PortWatch:
#     • `commit_ok = False`: Daten wandern NIE ins Repo.
#     • live geholt, nur LOKAL gecacht (`core/map/data/cache/`, .gitignore't) —
#       wie ein Browser-Cache, keine Weitergabe an Dritte.
#   Darum ist events-acled auch NICHT Teil des Standard-Komposits `political`,
#   sondern nur per `?sub=events-acled` als bewusste lokale Anreicherung.
#
# Zugang: ACLED verlangt Registrierung. Zugangsdaten via Umgebungsvariablen
#   ACLED_API_KEY + ACLED_EMAIL. Fehlen sie, liefert der Layer sauber
#   „keine Daten" (graceful) — kein Crash.

import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..projection import lonlat_to_world

# Provenienz — hängt an jeder Antwort.
SOURCE = {
    "name": "ACLED (Armed Conflict Location & Event Data)",
    "url": "https://acleddata.com",
    "license": "ACLED EULA — nicht-kommerziell, KEINE Weiterverteilung",
    "license_url": "https://acleddata.com/eula",
    "attribution": "ACLED (acleddata.com)",
    "commit_ok": False,      # NICHT ins Git-Repo (nur lokal cachen)
}

_KEY = os.environ.get("ACLED_API_KEY")
_EMAIL = os.environ.get("ACLED_EMAIL")
_BASE = "https://api.acleddata.com/acled/read"

_MAX_EVENTS = int(os.environ.get("ACLED_MAX_EVENTS", "20000"))
_PAGESIZE = 500                 # ACLED-Standard-Seitengröße
_MAX_PAGES = 200                # harte Obergrenze gegen Endlos-Pagination

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache")
_CACHE_FILE = os.path.join(_CACHE_DIR, "acled_events.json")


def _get(params, timeout=30):
    """Eine ACLED-read-Seite als JSON. Wirft bei Netz-/Parse-Fehler."""
    url = _BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ZENTRALE-maps/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _event_item(a):
    """Eine ACLED-Ereigniszeile → schlankes, vorprojiziertes Item (oder None)."""
    lon, lat = a.get("longitude"), a.get("latitude")
    if lon in (None, "") or lat in (None, ""):
        return None
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    wx, wy = lonlat_to_world(lon, lat)
    fat = a.get("fatalities")
    try:
        fat = int(fat) if fat not in (None, "") else None
    except (TypeError, ValueError):
        fat = None
    return {
        "id": a.get("data_id"),
        "lon": lon, "lat": lat, "wx": wx, "wy": wy,
        "date": a.get("event_date"),          # YYYY-MM-DD
        "best": fat,                          # Todesopfer (Vergleichbarkeit zu UCDP.best)
        "event_type": a.get("event_type"),
        "sub_event_type": a.get("sub_event_type"),
        "side_a": a.get("actor1"), "side_b": a.get("actor2"),
        "country": a.get("country"),
    }


def _fetch():
    """Live von ACLED holen: jüngste Ereignisse (paginiert), auf _MAX_EVENTS
    gedeckelt. Gibt das Cache-Payload (dict) zurück — schreibt NICHT selbst.
    Wirft, wenn keine Zugangsdaten gesetzt sind (Aufrufer fängt → „keine Daten")."""
    if not (_KEY and _EMAIL):
        raise RuntimeError("ACLED_API_KEY/ACLED_EMAIL fehlen — Layer bleibt leer")

    items = []
    for page in range(1, _MAX_PAGES + 1):
        data = _get({
            "key": _KEY, "email": _EMAIL,
            "limit": _PAGESIZE, "page": page,
        })
        rows = data.get("data", [])
        if not rows:
            break
        for a in rows:
            it = _event_item(a)
            if it is not None:
                items.append(it)
        if len(rows) < _PAGESIZE or len(items) >= _MAX_EVENTS:
            break

    # Leeres Ergebnis NICHT cachen (sonst cache-first für immer leer, kein Retry).
    if not items:
        raise RuntimeError("ACLED: 0 Ereignisse geholt — nicht cachen")

    items.sort(key=lambda it: it.get("date") or "", reverse=True)
    items = items[:_MAX_EVENTS]
    vintage = items[0]["date"]

    return {
        "schema": 1,
        "source": SOURCE,
        "vintage": vintage,
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
    `python -m map.layers.acled`). Wirft bei Netz-/Zugangs-Fehler weiter."""
    payload = _fetch()
    _write(_CACHE_FILE, payload)
    return payload


def events():
    """ACLED-Ereignisse (Sub-Layer events-acled) — CACHE-ONLY auf dem Anfrage-
    Pfad: liefert den lokalen Cache oder None. Kein Netz im Request; Befüllen nur
    über refresh() / `python -m map.layers.acled` (braucht Key+Email). None →
    Layer zeigt „keine Daten"."""
    return _read(_CACHE_FILE)


if __name__ == "__main__":      # `python -m map.layers.acled` → Cache füllen
    p = refresh()
    print("ACLED gecacht: %d Ereignisse (jüngstes %s) — geholt %s"
          % (p["count"], p["vintage"], p["retrieved_at"]))
