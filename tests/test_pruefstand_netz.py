"""
Prüfstand: kein Werkzeug darf ins echte Netz (2026-10-10).

Die Messung vom 10.10. zeigte: in f01 lief browser_open am Netz-Ersatz
vorbei auf die echte LSF-Seite — der Browser (Chromium) geht nicht über
net. Jetzt hat die Browser-Sitzung einen Riegel (nur_erlauben), den der
Prüfstand auf den Seiten-Server des Falls setzt, und fetch_document holt
über gedaechtnis.herunterladen, das der Netz-Ersatz übernimmt.

Ohne Chromium: der Abfang-Haken mit Attrappen. Mit echtem Chromium:
tests/test_browser.py, test_pruefstand_riegel_….
"""
import os
import socket
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from pruefstand_teile import umgebung  # noqa: E402

import browser_sitzung  # noqa: E402
import gedaechtnis  # noqa: E402


@pytest.fixture(autouse=True)
def ohne_riegel():
    zurueck = browser_sitzung.nur_erlauben([])
    zurueck()                      # Ausgangslage: kein Riegel
    assert browser_sitzung._nur is None
    yield
    browser_sitzung._nur = None


def test_ohne_riegel_ist_alles_erreichbar():
    assert browser_sitzung.erreichbar("https://www.lsf.uni-saarland.de/x")


def test_riegel_laesst_nur_den_ursprung_durch_und_geht_zurueck():
    zurueck = browser_sitzung.nur_erlauben(["http://127.0.0.1:4711"])
    assert browser_sitzung.erreichbar("http://127.0.0.1:4711/veranstaltung?id=1")
    assert not browser_sitzung.erreichbar("http://127.0.0.1:4712/")       # anderer Port
    assert not browser_sitzung.erreichbar("https://127.0.0.1:4711/")      # anderes Schema
    assert not browser_sitzung.erreichbar("https://www.lsf.uni-saarland.de/")
    zurueck()
    assert browser_sitzung.erreichbar("https://www.lsf.uni-saarland.de/")


def test_leerer_riegel_sperrt_alles():
    umgebung.browser_einsperren(None)
    assert not browser_sitzung.erreichbar("http://127.0.0.1:4711/")
    assert not browser_sitzung.erreichbar("https://example.org/")


class _Rahmen:
    def __init__(self, haupt=True):
        self.parent_frame = None if haupt else object()


class _Anfrage:
    def __init__(self, url, art="document", haupt=True):
        self.url, self.resource_type, self.frame = url, art, _Rahmen(haupt)


class _Route:
    def __init__(self):
        self.abgebrochen = None
        self.geholt = False

    def abort(self, grund):
        self.abgebrochen = grund

    def fulfill(self, status=200, **k):
        self.abgebrochen = f"ersetzt {status}"

    def fetch(self, **k):
        self.geholt = True
        raise AssertionError("ins Netz gegangen")


class _S:
    gid = "g"
    unerreichbar = gesperrt = blockiert = umleitung = download = ""
    rahmen_fremd = 0


@pytest.mark.parametrize("art, haupt", [("document", True), ("image", True),
                                        ("script", True), ("document", False)])
def test_abfang_haken_bricht_alles_draussen_ab_ohne_dns(monkeypatch, art, haupt):
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("DNS")))
    browser_sitzung.nur_erlauben(["http://127.0.0.1:4711"])
    s, route = _S(), _Route()
    browser_sitzung._Arbeiter._abfangen(None, s, route,
                                        _Anfrage("https://cdn.example.org/a", art, haupt))
    hauptseite = art == "document" and haupt
    # Die Hauptseite bekommt eine leere Ersatzseite (sonst stört Chromiums
    # Fehlerseite das nächste Öffnen), alles andere wird abgebrochen.
    assert route.abgebrochen == ("ersetzt 502" if hauptseite else "failed")
    assert not route.geholt
    assert s.unerreichbar == ("https://cdn.example.org/a" if hauptseite else "")


def test_sperre_meldet_nicht_erreichbar():
    s = _S()
    s.unerreichbar = "https://www.lsf.uni-saarland.de/"
    with pytest.raises(browser_sitzung.BrowserFehler) as f:
        browser_sitzung._Arbeiter._sperren_melden(None, s)
    assert f.value.code == "B-LADEN" and "nicht erreichbar" in f.value.grund


def test_adresse_pruefen_fragt_im_riegel_kein_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("DNS")))
    monkeypatch.setattr(browser_sitzung, "_dns", {})
    browser_sitzung.nur_erlauben(["http://127.0.0.1:4711"])
    url, host = browser_sitzung.adresse_pruefen("https://www.lsf.uni-saarland.de/x")
    assert host == "www.lsf.uni-saarland.de"


def test_fetch_document_geht_ueber_den_netz_ersatz():
    netz = umgebung.NetzAttrappe({"seiten": [
        {"wenn": "modulhandbuch", "text": "Modulhandbuch Biophysik: Experimentalphysik I, 9 CP"}]})
    zurueck = netz.einhaengen()
    try:
        assert gedaechtnis.herunterladen.__self__ is netz
        r = gedaechtnis.dokument_holen("https://uni.example/modulhandbuch.html", "Modulhandbuch")
        assert "[Download fehlgeschlagen" not in r
        assert "Experimentalphysik I" in gedaechtnis.dossier_lesen("quellen/modulhandbuch")
        r = gedaechtnis.dokument_holen("https://anderswo.example/x.pdf", "Anderes")
        assert r.startswith("[Download fehlgeschlagen") and "nicht erreichbar" in r
    finally:
        zurueck()
    assert getattr(gedaechtnis.herunterladen, "__self__", None) is None
    assert [p[0] for p in netz.protokoll] == ["seite", "seite"]
