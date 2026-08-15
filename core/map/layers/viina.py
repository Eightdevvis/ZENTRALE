# core/map/layers/viina.py
#
# Quelle für den Sub-Layer „control-ua" des politischen Overlays (Achse 2):
# Gebietskontrolle in der Ukraine („die Flächen" — wer kontrolliert welchen Ort).
# Projekt: VIINA — Violent Incident Information from News Articles (Yuri Zhukov,
# Yale/U-Michigan, https://github.com/zhukovyuri/VIINA). Liefert je Ort täglich
# einen Kontroll-Status (UA / RU / CONTESTED) auf GeoNames-Ebene.
#
# EHRLICHKEITS-Hinweis (siehe memory/maps/maps_quellen.md, „genau EINE Primärquelle"):
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
# (+Polygon für später). Wir joinen über geonameid auf die Koordinaten.
#
# ACHSE 3 (Zeit): Weil die control-Datei die GANZE Tageszeitreihe trägt, cachen
# wir je Ort die komprimierte Konsens-Zeitachse (nur Change-Points). `control()`
# löst daraus „Status an Datum X" auf (at=None → Gegenwart). So ist der Cache
# klein (Orte ändern selten den Status) und trotzdem voll zeitreisefähig.

import io
import os
import sys
import csv
import json
import time
import zipfile
import itertools
import http.client
import urllib.error
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


def _download(url, timeout=180, tries=3):
    """Ganze Antwort holen, mit Retry+Backoff. Nur im Refresh benutzt (nie im
    Request-Pfad) — die großen Dateien (31-MB-Gazetteer, LFS-ZIP) laufen über
    lahme raw/media-Endpunkte und reißen gelegentlich den Read-Timeout; ein
    schlichter Wiederholversuch fängt die Aussetzer ab, statt den ganzen Job
    (inkl. der teuren Zeitreihen-Sortierung) wegzuwerfen."""
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZENTRALE-maps/1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, http.client.HTTPException,
                TimeoutError, OSError) as e:
            # HTTPException deckt IncompleteRead ab (Abbruch mitten im Stream —
            # bei den großen Dateien hier häufiger als ein sauberer Timeout).
            last = e
            if k + 1 < tries:
                time.sleep(3 * (k + 1))     # kurzer Backoff, dann neu versuchen
    raise last


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


def _timelines():
    """Aus der Jahres-ZIP (Tageszeitreihe) zwei Dinge je Ort: (a) `latest` — die
    JÜNGSTEN Einzelquellen-Stati (für den Gegenwarts-Vergleich) und (b) `timelines`
    — die auf Change-Points komprimierte KONSENS-Zeitachse [[iso_date, status], …]
    aufsteigend. Gibt (latest, timelines, date_min, date_max).

    Speicher: die ~6,7 Mio Zeilen werden als flache Liste (gid, iso_date, status)
    mit internierten Strings gehalten, EINMAL global sortiert und je Ort lauflängen-
    komprimiert — statt 6,7 Mio verschachtelter dict-Einträge."""
    blob = _download(_URL)
    # Sicherung: kam versehentlich der LFS-Pointer statt der Binärdatei?
    if blob[:40].startswith(b"version https://git-lfs"):
        raise ValueError("VIINA: LFS-Pointer statt ZIP erhalten (falsche URL?)")

    zf = zipfile.ZipFile(io.BytesIO(blob))
    member = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
    if member is None:
        raise ValueError("VIINA-ZIP enthält kein CSV")

    rows = []                          # (gid, iso_date, status) — internierte Strings
    latest = {}
    dmin = dmax = None
    with zf.open(member) as fh:
        for row in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
            gid, d = row.get("geonameid"), row.get("date")
            if not gid or not d:
                continue
            di = sys.intern(_iso_date(d))
            rows.append((sys.intern(gid), di, sys.intern(row.get("status") or "")))
            if dmin is None or di < dmin:
                dmin = di
            if dmax is None or di > dmax:
                dmax = di
            cur = latest.get(gid)
            if cur is None or d > cur["date"]:
                latest[gid] = {
                    "date": d,
                    # jüngste Einzelquellen, damit man sie vergleichen kann
                    "status_dsm": row.get("status_dsm"),
                    "status_isw": row.get("status_isw"),
                    "status_wiki": row.get("status_wiki"),
                    "status_boost": row.get("status_boost"),
                }

    rows.sort()                        # nach (gid, iso_date) → je Ort chronologisch
    timelines = {}
    for gid, grp in itertools.groupby(rows, key=lambda t: t[0]):
        tl = []
        prev = None
        for _g, di, st in grp:
            if st != prev:             # nur Change-Points behalten (Lauflängen-Kompression)
                tl.append([di, st])
                prev = st
        timelines[gid] = tl
    return latest, timelines, dmin, dmax


def _iso_date(d):
    """VIINA-Datum 'YYYYMMDD' → 'YYYY-MM-DD' (sonst unverändert)."""
    if d and len(d) == 8 and d.isdigit():
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:])
    return d


def _fetch():
    """Zeitreisefähiger Cache der Gebietskontrolle: je Ort die Konsens-Zeitachse
    (Change-Points) + jüngste Einzelquellen, über geonameid auf die Gazetteer-
    Koordinaten gejoint. Gibt das fertige Cache-Payload (dict) zurück — schreibt
    NICHT selbst. Reihenfolge: erst Zeitreihe (gibt die große Zeilenliste danach
    frei), dann Gazetteer laden → niedrigerer Speicher-Peak."""
    latest, timelines, dmin, dmax = _timelines()
    gaz = _gazetteer()

    items = []
    for gid, tl in timelines.items():
        coords = gaz.get(gid)
        if coords is None:                 # Ort ohne Koordinate → nicht kartierbar
            continue
        lon, lat, name = coords
        wx, wy = lonlat_to_world(lon, lat)
        st = latest.get(gid) or {}
        items.append({
            "geonameid": gid,
            "name": name,
            "lon": lon, "lat": lat, "wx": wx, "wy": wy,
            # jüngste Einzelquellen (nur für den Gegenwarts-Vergleich aussagekräftig)
            "status_dsm": st.get("status_dsm"),
            "status_isw": st.get("status_isw"),
            "status_wiki": st.get("status_wiki"),
            "status_boost": st.get("status_boost"),
            # Konsens-Zeitachse: nur Change-Points [[iso_date, status], …] aufsteigend
            "timeline": tl,
        })

    # Leeres Ergebnis NICHT cachen (sonst cache-first für immer leer, kein Retry).
    if not items:
        raise ValueError("VIINA: 0 Orte nach Join — nicht cachen (falsche URL/leer?)")

    return {
        "schema": 2,
        "source": SOURCE,
        "year": _YEAR,
        "date_min": dmin,
        "date_max": dmax,
        # Stand: jüngstes Datum in der Zeitreihe, sonst Abrufdatum.
        "vintage": dmax or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
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


def _asof(timeline, at):
    """Letzter Change-Point mit date <= at (oder der jüngste, wenn at None).
    None, wenn der Ort zu at noch nicht getrackt war (at < erstes Datum).
    timeline ist aufsteigend → binäre Suche auf die Daten."""
    if not timeline:
        return None
    if at is None:
        return timeline[-1]
    lo, hi = 0, len(timeline)
    while lo < hi:
        mid = (lo + hi) // 2
        if timeline[mid][0] <= at:
            lo = mid + 1
        else:
            hi = mid
    return timeline[lo - 1] if lo > 0 else None


def control(at=None):
    """Ukraine-Gebietskontrolle je Ort (Sub-Layer control-ua) — CACHE-ONLY auf dem
    Anfrage-Pfad: liefert den lokalen Cache oder None. Kein Netz im Request (der
    Jahres-Download ist groß/LFS); Befüllen nur über refresh() /
    `python -m map.layers.viina`.

    Achse 3: at=None → Gegenwarts-Snapshot (jüngster Stand je Ort). at='YYYY-MM-DD'
    → Status, wie er AN diesem Tag galt (letzter Change-Point <= at); Orte, die zu
    dem Zeitpunkt noch nicht getrackt waren, fallen raus. Rückgabe ist ein FLACHES
    Payload {…, items:[{…, status}]} — kompatibel zum bisherigen Consumer."""
    cache = _read(_CACHE_FILE)
    if not cache:
        return None
    items = cache.get("items", [])
    # Alt-Cache (schema 1, flach ohne timeline) → unverändert, at wird ignoriert.
    if items and "timeline" not in items[0]:
        return cache

    now = at is None
    resolved = []
    for it in items:
        entry = _asof(it.get("timeline"), at)
        if entry is None:                  # Ort zu at noch nicht getrackt → raus
            continue
        resolved.append({
            "geonameid": it.get("geonameid"), "name": it.get("name"),
            "lon": it.get("lon"), "lat": it.get("lat"),
            "wx": it["wx"], "wy": it["wy"],
            "status": entry[1],
            # Einzelquellen nur beim Gegenwarts-Stand aussagekräftig (sonst None).
            "status_dsm": it.get("status_dsm") if now else None,
            "status_isw": it.get("status_isw") if now else None,
            "status_wiki": it.get("status_wiki") if now else None,
            "status_boost": it.get("status_boost") if now else None,
        })

    dmax = cache.get("date_max")
    eff = dmax if now else at             # angezeigter Stand; nach date_max clampen
    if dmax and eff and eff > dmax:
        eff = dmax
    return {
        "schema": cache.get("schema"), "source": cache.get("source"),
        "year": cache.get("year"),
        "date_min": cache.get("date_min"), "date_max": dmax,
        "vintage": eff or cache.get("vintage"),
        "retrieved_at": cache.get("retrieved_at"),
        "count": len(resolved), "items": resolved,
    }


def date_range():
    """(date_min, date_max) der gecachten Zeitreihe oder None — der Zeit-Scrubber
    der Front (Achse 3) liest daraus seine Grenzen."""
    cache = _read(_CACHE_FILE)
    if not cache:
        return None
    dmin, dmax = cache.get("date_min"), cache.get("date_max")
    return (dmin, dmax) if dmin and dmax else None


if __name__ == "__main__":      # `python -m map.layers.viina` → Cache füllen
    p = refresh()
    print("VIINA-Kontrolle gecacht: %d Orte, Zeitachse %s..%s (Jahr %s) — geholt %s"
          % (p["count"], p["date_min"], p["date_max"], p["year"], p["retrieved_at"]))
