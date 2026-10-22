"""Das Konto (core/konto.py) gegen eine gespielte Cloud (tests/_falsche_cloud.py):
anlegen, anmelden auf einem zweiten Gerät, falsches Passwort, Notfall,
Passwort ändern, abmelden. Der Server bekommt nie Passwort oder Schlüssel."""
import json
import os
import stat

import pytest

import dateien
import konto
import konto_schluessel as ks
from _falsche_cloud import FalscheCloud

KLEIN = {"name": "argon2id", "t": 1, "m": 64, "p": 1}   # schnell; das Schema ist dasselbe
PW = "ein-langes-passwort"


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setattr(ks, "KDF_VORGABE", KLEIN)
    monkeypatch.setattr(dateien, "knoten", lambda: "laptop")
    c.tmp = tmp_path
    yield c
    c.stopp()


def _geraet(cloud, monkeypatch, name):
    monkeypatch.setenv("ZENTRALE_KONTO_DATEI", str(cloud.tmp / name / "konto.json"))
    monkeypatch.setattr(dateien, "knoten", lambda: name)


def _anlegen(cloud, mail="Sasha@Example.org"):
    e = konto.Entwurf(PW)
    return e, konto.anlegen(e, mail, "EINLADUNG-1", PW)


def test_anlegen_meldet_an_und_legt_schluessel_600_ab(cloud):
    e, d = _anlegen(cloud)
    assert d["mail"] == "sasha@example.org"
    assert konto.konto_schluessel() == e.konto_schluessel
    assert stat.S_IMODE(os.stat(konto.datei()).st_mode) == 0o600
    assert "EINLADUNG-1" not in cloud.zustand.codes          # Code verbraucht


def test_der_server_sieht_nie_passwort_oder_schluessel(cloud):
    e, _ = _anlegen(cloud)
    gespeichert = json.dumps(cloud.zustand.konten)
    assert PW not in gespeichert
    assert e.konto_schluessel.decode() not in gespeichert
    assert e.notfall_text not in gespeichert


def test_zweites_geraet_bekommt_denselben_konto_schluessel(cloud, monkeypatch):
    e, _ = _anlegen(cloud)
    _geraet(cloud, monkeypatch, "minipc")
    assert not konto.angemeldet()
    d = konto.anmelden("sasha@example.org", PW)
    assert d["knoten"] == "minipc"
    assert konto.konto_schluessel() == e.konto_schluessel


def test_falsches_passwort_klarer_fehler_und_nichts_abgelegt(cloud, monkeypatch):
    _anlegen(cloud)
    _geraet(cloud, monkeypatch, "minipc")
    with pytest.raises(konto.KontoFehler, match="Wrong email or password"):
        konto.anmelden("sasha@example.org", "falsch-falsch-falsch")
    assert not os.path.exists(konto.datei())


def test_ungueltiger_code_klarer_fehler(cloud):
    with pytest.raises(konto.KontoFehler, match="invite code"):
        konto.anlegen(konto.Entwurf(PW), "a@b.c", "GIBTSNICHT", PW)


def test_zu_kurzes_passwort_wird_abgelehnt(cloud):
    with pytest.raises(konto.KontoFehler, match="at least"):
        konto.Entwurf("kurz")


def test_notfall_neues_passwort_daten_bleiben_altes_geht_nicht_mehr(cloud, monkeypatch):
    e, _ = _anlegen(cloud)
    _geraet(cloud, monkeypatch, "neu")
    d = konto.wiederherstellen("sasha@example.org", e.notfall_text.lower(), "ganz-neues-passwort")
    assert konto.konto_schluessel() == e.konto_schluessel
    assert d["mail"] == "sasha@example.org"
    konto.abmelden()
    with pytest.raises(konto.KontoFehler):
        konto.anmelden("sasha@example.org", PW)
    konto.anmelden("sasha@example.org", "ganz-neues-passwort")


def test_falscher_notfallschluessel_klarer_fehler(cloud):
    _anlegen(cloud)
    with pytest.raises(konto.KontoFehler, match="does not match"):
        konto.wiederherstellen("sasha@example.org", ks.notfall_text(os.urandom(32)), "ganz-neues-passwort")


def test_passwort_aendern_prueft_das_alte(cloud, monkeypatch):
    e, _ = _anlegen(cloud)
    with pytest.raises(konto.KontoFehler, match="Wrong"):
        konto.passwort_aendern("falsch-falsch-falsch", "noch-ein-passwort")
    konto.passwort_aendern(PW, "noch-ein-passwort")
    _geraet(cloud, monkeypatch, "pc")
    konto.anmelden("sasha@example.org", "noch-ein-passwort")
    assert konto.konto_schluessel() == e.konto_schluessel


def test_abmelden_loescht_alles_und_beendet_die_sitzung(cloud):
    _anlegen(cloud)
    assert cloud.zustand.sitzungen
    assert konto.abmelden() is True
    assert not os.path.exists(konto.datei())
    assert not cloud.zustand.sitzungen
    assert konto.abmelden() is False
    with pytest.raises(konto.KontoFehler, match="Not logged in"):
        konto.konto_schluessel()


def test_cloud_nicht_erreichbar_klarer_englischer_fehler(monkeypatch):
    monkeypatch.setenv("ZENTRALE_CLOUD", "http://127.0.0.1:9")
    with pytest.raises(konto.KontoFehler, match="Cannot reach the ZENTRALE cloud"):
        konto.anmelden("a@b.c", PW)
