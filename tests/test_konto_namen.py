"""Kontonamen auf dem Gerät (core/konto.py) gegen dieselben Fälle wie der
Server (tests/daten/konto_namen.json, cloud/test/name.test.ts): nur
Benutzernamen, keine Mail, keine erzeugten Nummern."""
import json
import os

import pytest

import konto

FAELLE = json.load(open(os.path.join(os.path.dirname(__file__), "daten", "konto_namen.json"),
                        encoding="utf-8"))


def test_listen_wie_in_der_gemeinsamen_datei():
    assert konto.RESERVIERT == set(FAELLE["reserviert"])
    assert konto.RESERVIERT_ANFANG == tuple(FAELLE["reserviert_anfang"])


def test_gute_namen_normalisiert_und_nicht_reserviert():
    for ein, aus in FAELLE["gut"]:
        assert konto.neuer_name(ein) == aus


def test_schlechte_namen_abgelehnt():
    for s in FAELLE["schlecht"]:
        with pytest.raises(konto.KontoFehler):
            konto.name_lesen(s)


def test_reserviert_nur_beim_anlegen():
    for r in FAELLE["reserviert"] + FAELLE["reserviert_faelle"]:
        assert konto.name_lesen(r)                     # anmelden: nur ein unbekannter Name
        with pytest.raises(konto.KontoFehler, match="reserved"):
            konto.neuer_name(r)


def test_mail_bekommt_den_hinweis():
    for m in FAELLE["mail"]:
        with pytest.raises(konto.KontoFehler) as e:
            konto.name_lesen(m)
        assert str(e.value) == konto.KEINE_MAIL


def test_nfc():
    zerlegt = "émile"                             # é als e + Akzent
    with pytest.raises(konto.KontoFehler):
        konto.name_lesen(zerlegt)                      # bleibt kein a–z, auch nach NFC
    assert konto.name_lesen("Ångstrom".replace("Å", "a")) == "angstrom"
