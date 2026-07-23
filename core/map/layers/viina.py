# core/map/layers/viina.py
#
# Quelle für den Sub-Layer „control-ua" des politischen Overlays (Achse 2):
# Gebietskontrolle in der Ukraine („die Flächen" — wer kontrolliert welchen Ort).
# Projekt: VIINA — Violent Incident Information from News Articles (Yuri Zhukov,
# Yale/U-Michigan, https://github.com/zhukovyuri/VIINA). Liefert je Ort täglich
# einen Kontroll-Status (UA / RU / CONTESTED) auf GeoNames-Ebene.
#
# EHRLICHKEITS-Hinweis (siehe memory/maps_quellen.md, „genau EINE Primärquelle"):
#   Die Kontroll-Ebene von VIINA ist ein ABGELEITETES Aggregat — Mehrheitsvotum
#   über DeepStateMap (`status_dsm`), ISW (`status_isw`) und Wikipedia
#   (`status_wiki`). Das ist streng genommen keine reine Primärquelle. Wir führen
#   sie darum bewusst als deklariert-abgeleiteten Sekundär-Overlay und geben die
#   Einzel-Stati mit, damit man sehen kann, wer was sagt (Charter: „Quellen
#   gegeneinander sehen"). Für die Ukraine existiert offen KEINE permissive
#   Primär-Flächenquelle (liveuamap = proprietär/paid, DeepStateMap = Zugang an
#   Ukraine-Defense/Charity gebunden) — VIINA ist die committbare Option.
#
# Lizenz: Open Database License (ODbL) — Namensnennung + Share-alike →
#   `commit_ok = True` (mit Copyleft). Wie UCDP holen wir live + cachen lokal.
#
# Format: ZWEI VIINA-Dateien werden gejoint (die Kontrolldatei trägt KEINE
# Koordinaten). (1) `control_latest_<jahr>.zip` (git-LFS) — je Ort und TAG eine
# Zeile mit Kontroll-Status; Spalten geonameid/date/status(+Einzelquellen). Das
# ist eine ganze Tageszeitreihe (~6,7 Mio Zeilen, ~33k Orte je Jahr). (2) Der
# Gazetteer `gn_UA_tess.geojson` — je geonameid Punkt (latitude/longitude) + Name
# (+Polygon für später). Wir nehmen je Ort die JÜNGSTE Status-Zeile (Gegenwarts-
# Snapshot) und joinen über geonameid auf die Koordinaten.

import io
import os
import csv
import json
import zipfile
import urllib.request
from datetime import datetime, timezone

from ..projection import lonlat_to_world

# Provenienz — hängt an jeder Antwort.
SOURCE = {
    "name": "VIINA — Territorial Control (Zhukov, Yale/U-Michigan)",
    "url": "https://github.com/zhukovyuri/VIINA",
    "license": "ODbL (Namensnennung + Share-alike)",
    "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
    "attribution": "VIINA (Yuri M. Zhukov) — Mehrheitsvotum aus DeepStateMap/ISW/Wikipedia",
    "commit_ok": True,       # ODbL → committbar (Share-alike beachten)
    "derived": True,         # KEINE reine Primärquelle: Aggregat mehrerer Quellen
}

# Kontrolljahr (Dateiname Data/control_latest_<jahr>.zip). Default: laufendes
# Jahr; per VIINA_YEAR überschreibbar (z.B. für die Zeitachse später).
# WICHTIG: Die ZIPs liegen als git-LFS-Objekte → der normale raw-Endpoint gibt
# nur den LFS-Pointer zurück. Der echte Binär-Inhalt kommt über media.github…/
# media/ (Branch `main`, Ordner `Data`). Diese Jahresdatei ist groß → der
# einmalige Abruf gehört auf einen echten Rechner (wie der density-Ingest).
_YEAR = os.environ.get("VIINA_YEAR") or str(datetime.now(timezone.utc).year)
_MEDIA = "https://media.githubusercontent.com/media/zhukovyuri/VIINA/main/Data"
_URL = "%s/control_latest_%s.zip" % (_MEDIA, _YEAR)

# Gazetteer geonameid → Koordinaten+Name (statische Struktur, ändert sich kaum).
# KEIN git-LFS → normaler raw-Endpoint liefert die echte Datei (~31 MB).
_GAZETTEER_URL = (
    "https://raw.githubusercontent.com/zhukovyuri/VIINA/main/Data/gn_UA_tess.geojson")

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache")
_CACHE_FILE = os.path.join(_CACHE_DIR, "viina_control.json")


def _download(url, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "ZENTRALE-maps/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _gazetteer():
    """geonameid → (lon, lat, asciiname) aus VIINAs `gn_UA_tess.geojson`.
    Der Gazetteer trägt die Punktkoordinaten je Ort; die Kontrolldatei hat nur
    den Status. GeoNames-ids stehen dort als Float ('461727.0') → auf str(int)
    normalisieren, damit der Join mit den CSV-ids (String) trifft."""
    fc = json.loads(_download(_GAZETTEER_URL))
    gaz = {}
    for feat in fc.get("features", []):
        p = feat.get("properties") or {}
        gid, lon, lat = p.get("geonameid"), p.get("longitude"), p.get("latitude")
        if gid is None or lon is None or lat is None:
            continue
        gaz[str(int(float(gid)))] = (float(lon), float(lat), p.get("asciiname"))
    if not gaz:
        raise ValueError("VIINA: Gazetteer leer — Join unmöglich")
    return gaz


def _latest_status():
    """Jüngste Kontroll-Zeile je geonameid aus der Jahres-ZIP (die eine ganze
    Tageszeitreihe enthält). Gibt (dict geonameid → status-felder, max_date)."""
    blob = _download(_URL)
    # Sicherung: kam versehentlich der LFS-Pointer statt der Binärdatei?
    if blob[:40].startswith(b"version https://git-lfs"):
        raise ValueError("VIINA: LFS-Pointer statt ZIP erhalten (falsche URL?)")

    zf = zipfile.ZipFile(io.BytesIO(blob))
    member = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
    if member is None:
        raise ValueError("VIINA-ZIP enthält kein CSV")

    latest = {}
    max_date = None
    with zf.open(member) as fh:
        for row in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
            gid, d = row.get("geonameid"), row.get("date")
            if not gid or not d:
                continue
            cur = latest.get(gid)
            if cur is None or d > cur["date"]:
                latest[gid] = {
                    "date": d,
                    # Konsens-Status (Mehrheitsvotum) …
                    "status": row.get("status"),
                    # … plus Einzelquellen, damit man sie vergleichen kann
                    "status_dsm": row.get("status_dsm"),
                    "status_isw": row.get("status_isw"),
                    "status_wiki": row.get("status_wiki"),
                    "status_boost": row.get("status_boost"),
                }
            if max_date is None or d > max_date:
                max_date = d
    return latest, max_date


def _iso_date(d):
    """VIINA-Datum 'YYYYMMDD' → 'YYYY-MM-DD' (sonst unverändert)."""
    if d and len(d) == 8 and d.isdigit():
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:])
    return d


def _fetch():
    """Gegenwarts-Snapshot der Gebietskontrolle: jüngsten Status je Ort holen und
    über geonameid auf die Gazetteer-Koordinaten joinen. Gibt das fertige
    Cache-Payload (dict) zurück — schreibt NICHT selbst."""
    gaz = _gazetteer()
    latest, max_date = _latest_status()

    items = []
    for gid, st in latest.items():
        coords = gaz.get(gid)
        if coords is None:                 # Ort ohne Koordinate → nicht kartierbar
            continue
        lon, lat, name = coords
        wx, wy = lonlat_to_world(lon, lat)
        items.append({
            "geonameid": gid,
            "name": name,
            "lon": lon, "lat": lat, "wx": wx, "wy": wy,
            "status": st["status"],
            "status_dsm": st["status_dsm"],
            "status_isw": st["status_isw"],
            "status_wiki": st["status_wiki"],
            "status_boost": st["status_boost"],
        })

    # Leeres Ergebnis NICHT cachen (sonst cache-first für immer leer, kein Retry).
    if not items:
        raise ValueError("VIINA: 0 Orte nach Join — nicht cachen (falsche URL/leer?)")

    return {
        "schema": 1,
        "source": SOURCE,
        "year": _YEAR,
        # Stand: jüngstes Datum in der Zeitreihe, sonst Abrufdatum.
        "vintage": _iso_date(max_date) or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
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
    `python -m map.layers.viina`). Wirft bei Netzfehler weiter."""
    payload = _fetch()
    _write(_CACHE_FILE, payload)
    return payload


def control():
    """Ukraine-Gebietskontrolle je Ort (Sub-Layer control-ua) — CACHE-ONLY auf
    dem Anfrage-Pfad: liefert den lokalen Cache oder None. WICHTIG: kein Netz im
    Request — der Jahres-Download ist groß (git-LFS) und würde den Request
    minutenlang blockieren. Befüllen ausschließlich über refresh() /
    `python -m map.layers.viina` (einmal auf echtem Rechner). None → „keine Daten"."""
    return _read(_CACHE_FILE)


if __name__ == "__main__":      # `python -m map.layers.viina` → Cache füllen
    p = refresh()
    print("VIINA-Kontrolle gecacht: %d Orte (Stand %s, Jahr %s) — geholt %s"
          % (p["count"], p["vintage"], p["year"], p["retrieved_at"]))
