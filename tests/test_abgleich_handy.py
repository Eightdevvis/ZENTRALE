"""Das Handy als fremder Knoten an der Mitte (memory/betrieb/abgleich.md,
„Format für fremde Knoten").

Der Knoten hier ist absichtlich NUR nach der Beschreibung gebaut: Fernet aus
AES-CBC und HMAC zusammengesetzt, versteckte Namen per HMAC, Schreiben als
gewöhnlicher Commit (wie die GitHub-API) — kein Code aus core/abgleich*.
Passt die Beschreibung nicht Byte für Byte, wird es hier rot, bevor die
Dart-App daran scheitert.
"""
import base64
import hashlib
import hmac
import json
import os
import struct
import subprocess
import time

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import abgleich
import ai_config
import mobil_kontext
from test_abgleich import LISTE, Welt  # noqa: F401  (Fixture-Bausteine)


# ── Ein fremder Knoten, nur nach der Beschreibung ──────────────────────

class Handy:
    NAME = "handy"

    def __init__(self, welt):
        self.welt = welt
        zeile = (welt.tmp / "schluessel").read_text().strip().encode("ascii")
        roh = base64.urlsafe_b64decode(zeile)
        self.sign, self.enc = roh[:16], roh[16:]
        self.namen_key = hashlib.sha256(b"zentrale-abgleich-namen\x00" + zeile).digest()
        self.klon = welt.tmp / "handy-klon"
        subprocess.run(["git", "clone", "-q", "-b", "abgleich", str(welt.mitte), str(self.klon)],
                       check=True)

    def _git(self, *a):
        return subprocess.run(["git", "-C", str(self.klon), "-c", "user.name=handy",
                               "-c", "user.email=h@x", *a], check=True, capture_output=True)

    # Fernet, Byte für Byte wie beschrieben
    def zu(self, klar: bytes) -> bytes:
        iv = os.urandom(16)
        p = padding.PKCS7(128).padder()
        gefuellt = p.update(klar) + p.finalize()
        e = Cipher(algorithms.AES(self.enc), modes.CBC(iv)).encryptor()
        teil = b"\x80" + struct.pack(">Q", int(time.time())) + iv + e.update(gefuellt) + e.finalize()
        mac = hmac.new(self.sign, teil, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(teil + mac)

    def auf(self, token: bytes) -> bytes:
        roh = base64.urlsafe_b64decode(token)
        assert roh[0] == 0x80
        teil, mac = roh[:-32], roh[-32:]
        assert hmac.compare_digest(mac, hmac.new(self.sign, teil, hashlib.sha256).digest())
        iv, ct = teil[9:25], teil[25:]
        d = Cipher(algorithms.AES(self.enc), modes.CBC(iv)).decryptor()
        u = padding.PKCS7(128).unpadder()
        return u.update(d.update(ct) + d.finalize()) + u.finalize()

    def name(self, rel: str) -> str:
        return hmac.new(self.namen_key, rel.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    # Lesen
    def holen(self):
        self._git("pull", "-q", "--rebase", "origin", "abgleich")

    def inhalt(self):
        return json.loads(self.auf((self.klon / "inhalt.enc").read_bytes()))

    def lesen(self, rel):
        e = self.inhalt()["dateien"][rel]
        assert e["name"] == self.name(rel)
        klar = self.auf((self.klon / "d" / (e["name"] + ".enc")).read_bytes())
        assert hashlib.sha256(klar).hexdigest() == e["sha"]
        return klar

    # Schreiben: nur in den eigenen Eingang
    def schreiben(self, rel, inhalt: bytes):
        self.holen()
        umschlag = json.dumps({"format": 1, "pfad": rel,
                               "inhalt": base64.b64encode(inhalt).decode("ascii")}).encode()
        ziel = self.klon / "knoten" / self.NAME / (self.name(rel) + ".enc")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(self.zu(umschlag))
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "handy")
        self._git("push", "-q", "origin", "HEAD:abgleich")


@pytest.fixture
def welt(tmp_path, monkeypatch):
    return Welt(tmp_path, monkeypatch)


def _ereignis(text):
    return json.dumps({"rolle": "user", "text": text, "id": "e" * 32,
                       "ts": "2026-10-08T10:00:00.000000+00:00", "knoten": "handy"},
                      ensure_ascii=False) + "\n"


# ── Tests ──────────────────────────────────────────────────────────────

def test_handy_liest_die_mitte_nur_nach_der_beschreibung(welt):
    laptop = welt.rechner("laptop")
    laptop.schreiben("gespraeche/g1/kopf.json", {"titel": "Hallo", "titel_von": "sasha"})
    laptop.schreiben("gespraeche/g1/laptop.jsonl", '{"text": "vom Laptop"}\n')
    laptop.schreiben("mobil/kontext.json", {"version": 1, "system": "Du bist ZENTRALE."})
    laptop.abgleichen()
    h = Handy(welt)
    pfade = set(h.inhalt()["dateien"])
    assert "data/gespraeche/g1/laptop.jsonl" in pfade
    assert b"vom Laptop" in h.lesen("data/gespraeche/g1/laptop.jsonl")
    assert json.loads(h.lesen("data/mobil/kontext.json"))["system"] == "Du bist ZENTRALE."


def test_handy_dateien_kommen_auf_die_rechner_und_werden_nie_ueberschrieben(welt):
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    pc.abgleichen()
    h = Handy(welt)
    gid = "20261008-101500-a1b2c3"
    h.schreiben(f"data/gespraeche/{gid}/handy.jsonl", _ereignis("vom Handy").encode())
    h.schreiben("data/gespraeche/_knoten/handy.json", b'{"aktiv": "%s"}' % gid.encode())
    h.schreiben(f"data/gespraeche/{gid}/kopf.json",
                json.dumps({"titel": "Unterwegs", "titel_von": "woerter", "erstellt":
                            "2026-10-08T10:15:00.000000+00:00", "archiviert": False,
                            "projekt": None}).encode())
    b = laptop.abgleichen()
    assert not b.hinweise
    assert "vom Handy" in laptop.lesen(f"gespraeche/{gid}/handy.jsonl")
    assert laptop.json(f"gespraeche/{gid}/kopf.json")["titel"] == "Unterwegs"
    assert laptop.json("gespraeche/_knoten/handy.json")["aktiv"] == gid
    pc.abgleichen()
    assert "vom Handy" in pc.lesen(f"gespraeche/{gid}/handy.jsonl")
    # Die Handy-Dateien bleiben in seinem Eingang; der Kopf (Vorschlag) wurde übernommen.
    drin = set(welt.inhalt()["dateien"])
    assert f"data/gespraeche/{gid}/handy.jsonl" not in drin
    assert f"data/gespraeche/{gid}/kopf.json" in drin
    # Ein Rechner, der die Handy-Datei verändert, setzt sich nie durch.
    laptop.schreiben(f"gespraeche/{gid}/handy.jsonl", "überschrieben\n")
    laptop.abgleichen()
    assert "vom Handy" in laptop.lesen(f"gespraeche/{gid}/handy.jsonl")
    # Das Handy hängt weiter an, die Rechner ziehen nach.
    h.schreiben(f"data/gespraeche/{gid}/handy.jsonl",
                (_ereignis("vom Handy") + _ereignis("noch eins")).encode())
    pc.abgleichen()
    assert "noch eins" in pc.lesen(f"gespraeche/{gid}/handy.jsonl")


def test_kopf_vom_handy_gilt_nur_solange_die_mitte_keinen_hat(welt):
    laptop = welt.rechner("laptop")
    laptop.schreiben("gespraeche/g1/kopf.json", {"titel": "Vom Laptop"})
    laptop.abgleichen()
    h = Handy(welt)
    h.schreiben("data/gespraeche/g1/kopf.json", b'{"titel": "Vom Handy"}')
    laptop.abgleichen()
    assert laptop.json("gespraeche/g1/kopf.json")["titel"] == "Vom Laptop"


def test_handy_darf_keine_fremden_dateien_schreiben(welt):
    laptop = welt.rechner("laptop")
    laptop.schreiben("lists.json", LISTE)
    laptop.schreiben("gespraeche/g1/laptop.jsonl", "a\n")
    laptop.abgleichen()
    h = Handy(welt)
    h.schreiben("data/lists.json", b"[]")
    h.schreiben("data/gespraeche/g1/laptop.jsonl", b"gefaelscht\n")
    b = laptop.abgleichen()
    assert laptop.json("lists.json") == LISTE
    assert laptop.lesen("gespraeche/g1/laptop.jsonl") == "a\n"
    assert len([x for x in b.hinweise if "Eingang handy" in x]) == 2


def test_eingang_mit_falschem_namen_wird_uebergangen(welt):
    laptop = welt.rechner("laptop")
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    h = Handy(welt)
    h.name = lambda rel: "0" * 32                      # Name passt nicht zum Pfad
    h.schreiben("data/gespraeche/g9/handy.jsonl", b"x\n")
    b = laptop.abgleichen()
    assert not laptop.da("gespraeche/g9/handy.jsonl")
    assert any("gehört nicht dorthin" in x for x in b.hinweise)


def test_kontextpaket_ohne_schluessel_und_nur_bei_aenderung(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-geheim-1234567890")
    monkeypatch.setattr(ai_config, "_overrides", {"chat_provider": "claude"})
    p = mobil_kontext.bauen()
    assert set(p) == {"version", "stand", "anbieter", "modell", "effort", "system"}
    assert p["version"] == 1 and p["anbieter"] == "claude"
    assert p["stand"].endswith("+00:00")
    assert isinstance(p["system"], str) and p["system"]
    assert "sk-ant-geheim" not in json.dumps(p)
    assert mobil_kontext.schreiben(str(tmp_path)) is True
    assert mobil_kontext.schreiben(str(tmp_path)) is False     # nichts Neues
    d = json.loads((tmp_path / "data" / "mobil" / "kontext.json").read_text())
    assert d["system"] == p["system"]


def test_kontextpaket_zwei_rechner_kein_widerspruch(welt):
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    laptop.schreiben("mobil/kontext.json", {"version": 1, "system": "A"})
    laptop.abgleichen()
    pc.abgleichen()
    laptop.schreiben("mobil/kontext.json", {"version": 1, "system": "B"})
    pc.schreiben("mobil/kontext.json", {"version": 1, "system": "C"})
    laptop.abgleichen()
    b = pc.abgleichen()
    assert not b.hinweise
    assert pc.json("mobil/kontext.json")["system"] == "C"     # die frische von hier
