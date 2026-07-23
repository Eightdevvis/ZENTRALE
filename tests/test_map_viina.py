# tests/test_map_viina.py
#
# Deckt den Join ab, an dem der Layer zuvor still auf 0 Orte lief: die VIINA-
# Kontrolldatei trägt KEINE Koordinaten (nur geonameid+Status je Tag), die
# Koordinaten kommen aus dem Gazetteer `gn_UA_tess.geojson`. Netz ist gemockt
# (`_download`), damit der Test offline und deterministisch bleibt.

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


def _fake_download(url, timeout=180):
    if url == viina._GAZETTEER_URL:
        return _gazetteer_geojson([
            (461727, "Olenevka", 32.53, 45.38),
            (700000, "Kupiansk", 37.62, 49.71),
        ])
    # sonst: die Control-ZIP. Kupiansk (700000) hat zwei Tage → jüngster gewinnt.
    return _control_zip([
        {"geonameid": "461727", "date": "20260101", "status": "RU",
         "status_dsm": "RU", "status_isw": "RU", "status_wiki": "RU",
         "status_boost": "RU"},
        {"geonameid": "700000", "date": "20260101", "status": "UA",
         "status_dsm": "UA", "status_isw": "UA", "status_wiki": "UA",
         "status_boost": "UA"},
        {"geonameid": "700000", "date": "20260722", "status": "RU",
         "status_dsm": "RU", "status_isw": "CONTESTED", "status_wiki": "RU",
         "status_boost": "RU"},
        # Ort ohne Gazetteer-Koordinate → muss rausfallen (nicht kartierbar).
        {"geonameid": "999999", "date": "20260722", "status": "UA"},
    ])


def test_iso_date():
    assert viina._iso_date("20260722") == "2026-07-22"
    assert viina._iso_date("2026-07-22") == "2026-07-22"   # schon ISO → durch
    assert viina._iso_date(None) is None


def test_fetch_joins_latest_status(monkeypatch):
    monkeypatch.setattr(viina, "_download", _fake_download)
    payload = viina._fetch()

    assert payload["count"] == 2                 # 999999 ohne Koordinate raus
    assert payload["vintage"] == "2026-07-22"    # jüngstes Datum, ISO-formatiert

    by_id = {i["geonameid"]: i for i in payload["items"]}
    assert set(by_id) == {"461727", "700000"}

    # Kupiansk: jüngste Zeile (20260722) gewinnt gegen den älteren UA-Stand.
    kup = by_id["700000"]
    assert kup["status"] == "RU"
    assert kup["status_isw"] == "CONTESTED"      # Einzelquellen mitgeführt
    assert kup["name"] == "Kupiansk"
    assert kup["lon"] == 37.62 and kup["lat"] == 49.71
    assert kup["wx"] is not None and kup["wy"] is not None


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
