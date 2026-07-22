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
# Format: die Kontrolldatei liegt als ZIP im Repo (`control_latest_<jahr>.zip`,
# GeoNames, N≈33k), NICHT als rohes CSV. Wir laden das ZIP, entpacken im Speicher
# und lesen die CSV-Spalten geonameid/longitude/latitude/asciiname/status(+Quellen).

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

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache")
_CACHE_FILE = os.path.join(_CACHE_DIR, "viina_control.json")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch():
    """VIINA-Kontroll-ZIP laden, im Speicher entpacken, CSV lesen. Gibt das
    fertige Cache-Payload (dict) zurück — schreibt NICHT selbst."""
    req = urllib.request.Request(_URL, headers={"User-Agent": "ZENTRALE-maps/1"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        blob = resp.read()

    # Sicherung: kam versehentlich der LFS-Pointer statt der Binärdatei?
    if blob[:40].startswith(b"version https://git-lfs"):
        raise ValueError("VIINA: LFS-Pointer statt ZIP erhalten (falsche URL?)")

    zf = zipfile.ZipFile(io.BytesIO(blob))
    member = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
    if member is None:
        raise ValueError("VIINA-ZIP enthält kein CSV")

    with zf.open(member) as fh:
        reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"))
        items = []
        max_date = None
        for row in reader:
            lon, lat = _num(row.get("longitude")), _num(row.get("latitude"))
            if lon is None or lat is None:
                continue
            wx, wy = lonlat_to_world(lon, lat)
            items.append({
                "geonameid": row.get("geonameid"),
                "name": row.get("asciiname"),
                "lon": lon, "lat": lat, "wx": wx, "wy": wy,
                # Konsens-Status (Mehrheitsvotum) …
                "status": row.get("status"),
                # … plus Einzelquellen, damit man sie vergleichen kann
                "status_dsm": row.get("status_dsm"),
                "status_isw": row.get("status_isw"),
                "status_wiki": row.get("status_wiki"),
            })
            d = row.get("date")
            if d and (max_date is None or d > max_date):
                max_date = d

    # Leeres Ergebnis NICHT cachen (sonst cache-first für immer leer, kein Retry).
    if not items:
        raise ValueError("VIINA: 0 Orte im ZIP — nicht cachen (falsche URL/leer?)")

    return {
        "schema": 1,
        "source": SOURCE,
        "year": _YEAR,
        # Stand: jüngstes Datum in der Datei, sonst Abrufdatum (Snapshot „latest").
        "vintage": max_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
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
    """Ukraine-Gebietskontrolle je Ort (Sub-Layer control-ua), cache-first.
    None, wenn weder Cache noch Netz da (Layer liefert dann „keine Daten")."""
    cached = _read(_CACHE_FILE)
    if cached is not None:
        return cached
    try:
        payload = _fetch()
        _write(_CACHE_FILE, payload)
        return payload
    except Exception:
        return None


if __name__ == "__main__":      # `python -m map.layers.viina` → Cache füllen
    p = refresh()
    print("VIINA-Kontrolle gecacht: %d Orte (Stand %s, Jahr %s) — geholt %s"
          % (p["count"], p["vintage"], p["year"], p["retrieved_at"]))
