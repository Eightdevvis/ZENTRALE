# tests/test_map_viina.py
#
# Deckt zwei Dinge ab: (1) den Join, an dem der Layer zuvor still auf 0 Orte lief
# — die VIINA-Kontrolldatei trägt KEINE Koordinaten (nur geonameid+Status je Tag),
# die kommen aus dem Gazetteer `gn_UA_tess.geojson`. (2) die Achse-3-Zeitreise:
# je Ort eine komprimierte Konsens-Zeitachse (Change-Points), aus der `control(at)`
# den Stand an einem Tag auflöst. Netz ist gemockt (`_download`) → offline.

import io
import csv
import json
import zipfile

from map.layers import viina


def _control_zip(rows):
    """Baut eine control_latest-ZIP im Speicher (Spalten wie im echten File)."""
    cols = ["geonameid", "date", "status_wiki", "status_boost",
            "status_dsm", "status_isw", "status", "vcontrol_version"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("control_latest_2026.csv", buf.getvalue())
    return zbuf.getvalue()


def _gazetteer_geojson(feats):
    return json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             # geonameid steht im echten File als Float ('461727.0')
             "properties": {"geonameid": float(g), "asciiname": n,
                            "latitude": lat, "longitude": lon},
             "geometry": None}
            for g, n, lon, lat in feats
        ],
    }).encode("utf-8")


# 461727 = Olenevka: durchgehend RU (1 Change-Point).
# 700000 = Kupiansk: UA am 01.01., RU ab 15.03. (2 Change-Points, Wechsel).
# 999999 = ohne Gazetteer-Koordinate → fällt aus dem Join.
def _fake_download(url, timeout=180):
    if url == viina._GAZETTEER_URL:
        return _gazetteer_geojson([
            (461727, "Olenevka", 32.53, 45.38),
            (700000, "Kupiansk", 37.62, 49.71),
        ])
    return _control_zip([
        {"geonameid": "461727", "date": "20260101", "status": "RU",
         "status_dsm": "RU", "status_isw": "RU", "status_wiki": "RU",
         "status_boost": "RU"},
        {"geonameid": "461727", "date": "20260315", "status": "RU"},
        {"geonameid": "700000", "date": "20260101", "status": "UA",
         "status_dsm": "UA", "status_isw": "UA", "status_wiki": "UA",
         "status_boost": "UA"},
        {"geonameid": "700000", "date": "20260315", "status": "RU",
         "status_dsm": "RU", "status_isw": "CONTESTED", "status_wiki": "RU",
         "status_boost": "RU"},
        {"geonameid": "999999", "date": "20260315", "status": "UA"},
    ])


def test_iso_date():
    assert viina._iso_date("20260722") == "2026-07-22"
    assert viina._iso_date("2026-07-22") == "2026-07-22"   # schon ISO → durch
    assert viina._iso_date(None) is None


def test_fetch_builds_timelines(monkeypatch):
    monkeypatch.setattr(viina, "_download", _fake_download)
    payload = viina._fetch()

    assert payload["schema"] == 2
    assert payload["count"] == 2                 # 999999 ohne Koordinate raus
    assert payload["date_min"] == "2026-01-01"
    assert payload["date_max"] == "2026-03-15"

    by_id = {i["geonameid"]: i for i in payload["items"]}
    assert set(by_id) == {"461727", "700000"}

    # Olenevka: durchgehend RU → EIN Change-Point (Lauflängen-Kompression).
    assert by_id["461727"]["timeline"] == [["2026-01-01", "RU"]]
    # Kupiansk: Wechsel UA→RU → ZWEI Change-Points.
    assert by_id["700000"]["timeline"] == [["2026-01-01", "UA"], ["2026-03-15", "RU"]]
    # jüngste Einzelquellen mitgeführt (für den Gegenwarts-Vergleich)
    assert by_id["700000"]["status_isw"] == "CONTESTED"
    assert by_id["700000"]["name"] == "Kupiansk"


def test_asof():
    tl = [["2026-01-01", "UA"], ["2026-03-15", "RU"]]
    assert viina._asof(tl, None) == ["2026-03-15", "RU"]     # jüngster
    assert viina._asof(tl, "2026-03-15") == ["2026-03-15", "RU"]  # genau am Wechsel
    assert viina._asof(tl, "2026-02-01") == ["2026-01-01", "UA"]  # davor
    assert viina._asof(tl, "2026-06-01") == ["2026-03-15", "RU"]  # weit danach
    assert viina._asof(tl, "2025-12-31") is None             # vor dem ersten Tag
    assert viina._asof([], "2026-01-01") is None


def _cache_from_fetch(monkeypatch):
    monkeypatch.setattr(viina, "_download", _fake_download)
    return viina._fetch()


def test_control_time_travel(monkeypatch):
    cache = _cache_from_fetch(monkeypatch)
    monkeypatch.setattr(viina, "_read", lambda _path: cache)

    # Gegenwart (at=None): Kupiansk jüngster Stand RU, Einzelquellen befüllt.
    now = {i["geonameid"]: i for i in viina.control()["items"]}
    assert now["700000"]["status"] == "RU"
    assert now["700000"]["status_isw"] == "CONTESTED"

    # Rückblick 01.02.: Kupiansk war noch UA; Einzelquellen bei Zeitreise = None.
    past = viina.control(at="2026-02-01")
    pm = {i["geonameid"]: i for i in past["items"]}
    assert pm["700000"]["status"] == "UA"
    assert pm["700000"]["status_isw"] is None
    assert past["vintage"] == "2026-02-01"

    # Vor date_min: alle Orte ungetrackt → leer (ehrlich, keine Daten).
    assert viina.control(at="2025-06-01")["count"] == 0


def test_control_schema1_passthrough(monkeypatch):
    # Alt-Cache ohne timeline → unverändert zurück, at ignoriert (Abwärtskompat).
    flat = {"schema": 1, "items": [{"geonameid": "1", "wx": 0.5, "wy": 0.5,
                                    "status": "UA"}]}
    monkeypatch.setattr(viina, "_read", lambda _path: flat)
    assert viina.control(at="2020-01-01") is flat


def test_fetch_raises_when_no_join(monkeypatch):
    # Gazetteer ohne passende ids → 0 Orte → NICHT cachen (Guard wirft).
    def only_mismatched(url, timeout=180):
        if url == viina._GAZETTEER_URL:
            return _gazetteer_geojson([(111, "X", 30.0, 50.0)])
        return _control_zip([{"geonameid": "222", "date": "20260722",
                              "status": "UA"}])
    monkeypatch.setattr(viina, "_download", only_mismatched)
    try:
        viina._fetch()
        assert False, "erwartete ValueError bei 0 Join-Treffern"
    except ValueError:
        pass
