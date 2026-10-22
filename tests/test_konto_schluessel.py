"""Das Schlüssel-Schema des Kontos (core/konto_schluessel.py, Bauplan v1).

Die Testvektoren in tests/daten/konto_testvektoren.json sind für ANDERE
Oberflächen da (Handy/Dart, Browser/WebCrypto+argon2-wasm …): wer das Schema
nachbaut, prüft sich Byte für Byte daran. Hier wird zweierlei geprüft:
  1. Python rechnet genau diese Werte (eingefroren — eine Änderung am Schema
     bricht alle anderen Oberflächen und muss bewusst sein).
  2. HKDF ist unabhängig nachgerechnet (RFC 5869 aus HMAC von Hand), damit
     die Vektoren nicht nur „was Python halt tut" sind.
"""
import base64
import hashlib
import hmac
import json
import os

import pytest

import konto_schluessel as ks

VEKTOREN = os.path.join(os.path.dirname(__file__), "daten", "konto_testvektoren.json")


def _hkdf_von_hand(ikm: bytes, info: bytes, laenge=32) -> bytes:
    prk = hmac.new(b"\0" * 32, ikm, hashlib.sha256).digest()          # Extract, Salz = 32 Null-Bytes
    okm, t, i = b"", b"", 1
    while len(okm) < laenge:                                            # Expand
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:laenge]


def _fernet_fest(schluessel: bytes, klartext: bytes, zeit: int, iv: bytes) -> str:
    from cryptography.fernet import Fernet
    return Fernet(schluessel)._encrypt_from_parts(klartext, zeit, iv).decode("ascii")


def vektoren_rechnen():
    """So entstehen die Vektoren — einmal gerechnet, als JSON abgelegt."""
    passwort = "correct horse battery staple"
    salz = bytes(range(16))
    kdf = dict(ks.KDF_VORGABE)
    haupt = ks.hauptschluessel(passwort, salz, kdf)
    notfall = bytes(range(32, 64))
    konto = base64.urlsafe_b64encode(bytes(range(100, 132)))
    zeit, iv = 1761091200, bytes(range(200, 216))
    return {
        "beschreibung": "ZENTRALE Konto-Schlüssel, Bauplan v1 (memory/hub/knoten_beitritt.md). "
                        "Bytes als hex; *_b64u = base64url ohne '='; Fernet-Schlüssel = base64url mit '='.",
        "passwort": passwort,
        "passwort_utf8_nfc_hex": passwort.encode("utf-8").hex(),
        "salz_hex": salz.hex(),
        "salz_b64u": ks.b64u(salz),
        "kdf": kdf,
        "hauptschluessel_hex": haupt.hex(),
        "hkdf": {"hash": "SHA-256", "salz": "keins (RFC 5869: 32 Null-Bytes)", "laenge": 32,
                 "info_anmelden": ks.INFO_ANMELDEN.decode(),
                 "info_verpacken": ks.INFO_VERPACKEN.decode(),
                 "info_notfall": ks.INFO_NOTFALL.decode(),
                 "info_notfall_beweis": ks.INFO_NOTFALL_BEWEIS.decode()},
        "anmelde_schluessel_b64u": ks.anmelde_schluessel(haupt),
        "verpack_schluessel_fernet": ks.verpack_schluessel(haupt).decode("ascii"),
        "notfall_hex": notfall.hex(),
        "notfall_text": ks.notfall_text(notfall),
        "notfall_schluessel_fernet": ks.notfall_schluessel(notfall).decode("ascii"),
        "notfall_beweis_b64u": ks.notfall_beweis(notfall),
        "konto_schluessel": konto.decode("ascii"),
        "fernet_fest": {"zeit": zeit, "iv_hex": iv.hex(),
                        "hinweis": "Fernet würfelt sonst Zeit und IV; mit diesen festen Werten "
                                   "ist das Token reproduzierbar. Jede echte Oberfläche muss "
                                   "zufällige IVs nehmen und darf nur das Entschlüsseln vergleichen."},
        "verpackt_passwort": _fernet_fest(ks.verpack_schluessel(haupt), konto, zeit, iv),
        "verpackt_notfall": _fernet_fest(ks.notfall_schluessel(notfall), konto, zeit, iv),
    }


@pytest.fixture(scope="module")
def gerechnet():
    return vektoren_rechnen()


def test_testvektoren_sind_genau_das_was_python_rechnet(gerechnet):
    with open(VEKTOREN, encoding="utf-8") as f:
        abgelegt = json.load(f)
    assert abgelegt == gerechnet, (
        "Das Schlüssel-Schema hat sich geändert — damit passen Handy, Browser und "
        "Server nicht mehr. Nur bewusst ändern (neue info-Fassung v2) und die "
        "Vektoren neu schreiben.")


def test_hkdf_von_hand_nachgerechnet(gerechnet):
    haupt = bytes.fromhex(gerechnet["hauptschluessel_hex"])
    notfall = bytes.fromhex(gerechnet["notfall_hex"])
    assert ks.b64u(_hkdf_von_hand(haupt, b"zentrale/anmelden/v1")) == gerechnet["anmelde_schluessel_b64u"]
    assert base64.urlsafe_b64encode(_hkdf_von_hand(haupt, b"zentrale/verpacken/v1")).decode() \
        == gerechnet["verpack_schluessel_fernet"]
    assert base64.urlsafe_b64encode(_hkdf_von_hand(notfall, b"zentrale/notfall/v1")).decode() \
        == gerechnet["notfall_schluessel_fernet"]
    assert ks.b64u(_hkdf_von_hand(notfall, b"zentrale/notfall-beweis/v1")) == gerechnet["notfall_beweis_b64u"]


def test_verpacktes_laesst_sich_mit_den_vektoren_auspacken(gerechnet):
    konto = gerechnet["konto_schluessel"].encode()
    assert ks.auspacken(gerechnet["verpack_schluessel_fernet"].encode(),
                        gerechnet["verpackt_passwort"], "x") == konto
    assert ks.auspacken(gerechnet["notfall_schluessel_fernet"].encode(),
                        gerechnet["verpackt_notfall"], "x") == konto


def test_notfall_text_hin_und_zurueck_auch_schlampig_getippt():
    roh = os.urandom(32)
    text = ks.notfall_text(roh)
    gruppen = text.split("-")
    assert len(gruppen) == 13 and all(len(g) == 4 for g in gruppen)
    assert ks.notfall_lesen(text) == roh
    assert ks.notfall_lesen(text.lower().replace("-", " ")) == roh
    with pytest.raises(ks.SchluesselFehler):
        ks.notfall_lesen(text[:-4])


def test_falsches_passwort_packt_nicht_aus():
    klein = {"name": "argon2id", "t": 1, "m": 64, "p": 1}
    konto = ks.neuer_konto_schluessel()
    teile = ks.passwort_teile("richtig-richtig", konto, klein)
    salz = ks.b64u_lesen(teile["salz"])
    falsch = ks.hauptschluessel("falsch-falsch", salz, teile["kdf"])
    with pytest.raises(ks.SchluesselFehler, match="nope"):
        ks.auspacken(ks.verpack_schluessel(falsch), teile["verpackt_passwort"], "nope")
    richtig = ks.hauptschluessel("richtig-richtig", salz, teile["kdf"])
    assert ks.auspacken(ks.verpack_schluessel(richtig), teile["verpackt_passwort"], "x") == konto


def test_kdf_werte_vom_server_auch_mit_langnamen_und_kaputte_abgelehnt():
    assert ks.kdf_lesen({"name": "argon2id", "iterations": 2, "memory": 1024, "parallelism": 2}) \
        == {"name": "argon2id", "t": 2, "m": 1024, "p": 2}
    for kaputt in ({"name": "pbkdf2"}, {"t": 0}, {"m": "viel"}):
        with pytest.raises(ks.SchluesselFehler):
            ks.kdf_lesen(kaputt)
