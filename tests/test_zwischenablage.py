"""Zwischenablage im Chat: /paste und Strg+V (tui/ansichten/zwischenablage.py,
chat_ablage.py) — 2026-10-08. Sasha: „ich wollte jetzt mal nen bild in die
ki reinpasten … aber da passiert nix." xclip ist hier immer eine Attrappe."""
import base64
import os
import subprocess
from collections import defaultdict

import pytest

from tui.ansichten import chat as chatmod
from tui.ansichten import chat_ablage, chat_befehle, zwischenablage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 300_000
X11 = {"DISPLAY": ":0"}


def _da(name):
    return "/usr/bin/" + name


def _xclip(inhalte, mitschnitt=None):
    """subprocess.run-Ersatz: inhalte = {target: bytes}; TARGETS ergibt sich."""
    def run(cmd, **k):
        if mitschnitt is not None:
            mitschnitt.append(cmd)
        assert cmd[:4] == ["xclip", "-selection", "clipboard", "-o"] and k.get("timeout")
        ziel = cmd[cmd.index("-t") + 1]
        if ziel == "TARGETS":
            if not inhalte:
                return subprocess.CompletedProcess(cmd, 1, b"", b"Error: target TARGETS not available")
            return subprocess.CompletedProcess(cmd, 0, "\n".join(["TARGETS"] + list(inhalte)).encode(), b"")
        if ziel in inhalte:
            return subprocess.CompletedProcess(cmd, 0, inhalte[ziel], b"")
        return subprocess.CompletedProcess(cmd, 1, b"", b"")
    return run


# ── Lesen ─────────────────────────────────────────────────────────────

def test_bild_wird_gelesen_png_zuerst():
    z = zwischenablage.lesen(X11, _da, _xclip({"image/jpeg": b"\xff\xd8\xff", "image/png": PNG,
                                               "UTF8_STRING": b"x"}))
    assert z.art == "bild" and z.mime == "image/png" and z.daten == PNG


def test_strg_v_prueft_nur_und_liest_kein_bild():
    gelesen = []
    z = zwischenablage.lesen(X11, _da, _xclip({"image/png": PNG}, gelesen), bild_holen=False)
    assert z.art == "bild" and z.daten == b""
    assert all("image/png" not in c for c in gelesen)       # nur TARGETS


def test_text_und_leer():
    z = zwischenablage.lesen(X11, _da, _xclip({"UTF8_STRING": "grüße".encode()}))
    assert (z.art, z.daten) == ("text", "grüße")
    assert zwischenablage.lesen(X11, _da, _xclip({})).art == "leer"
    assert zwischenablage.lesen(X11, _da, _xclip({"UTF8_STRING": b""})).art == "leer"


def test_fremdes_bildformat_ehrlich_abgelehnt():
    z = zwischenablage.lesen(X11, _da, _xclip({"image/bmp": b"BM"}))
    assert z.art == "nein" and "bmp" in z.grund and "png" in z.grund


def test_ohne_bildschirm_oder_ohne_xclip():
    def nie(*a, **k):
        raise AssertionError("darf nichts starten")
    z = zwischenablage.lesen({}, _da, nie)
    assert z.art == "nein" and "ohne bildschirm" in z.grund
    z = zwischenablage.lesen(X11, lambda n: None, nie)
    assert z.art == "nein" and "xclip fehlt" in z.grund


def test_haengt_oder_fehlt_beim_starten():
    def haengt(cmd, **k):
        raise subprocess.TimeoutExpired(cmd, k["timeout"])

    def weg(cmd, **k):
        raise FileNotFoundError(cmd[0])
    assert "antwortet nicht" in zwischenablage.lesen(X11, _da, haengt).grund
    assert zwischenablage.lesen(X11, _da, weg).art == "nein"


def test_wayland_nimmt_wl_paste():
    befehle = []

    def run(cmd, **k):
        befehle.append(cmd)
        if cmd == ["wl-paste", "--list-types"]:
            return subprocess.CompletedProcess(cmd, 0, b"image/png\n", b"")
        return subprocess.CompletedProcess(cmd, 0, PNG, b"")
    z = zwischenablage.lesen({"WAYLAND_DISPLAY": "wayland-0"}, _da, run)
    assert z.art == "bild" and befehle[1][-1] == "image/png"


def test_echte_xclip_attrappe_im_pfad(tmp_path, monkeypatch):
    """Die Argumente stimmen auch mit einem echten Prozess: ein Skript namens
    xclip, das TARGETS und ein PNG liefert."""
    bild = tmp_path / "b.png"
    bild.write_bytes(PNG[:64])
    skript = tmp_path / "xclip"
    skript.write_text('#!/bin/sh\ncase "$*" in\n  *TARGETS*) printf "TARGETS\\nimage/png\\n";;\n'
                      '  *image/png*) cat "%s";;\n  *) exit 1;;\nesac\n' % bild)
    skript.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    z = zwischenablage.lesen({"DISPLAY": ":0"})
    assert z.art == "bild" and z.daten == PNG[:64]


def test_groesse_text():
    assert zwischenablage.groesse_text(312 * 1024) == "312 KB"
    assert zwischenablage.groesse_text(10) == "1 KB"
    assert zwischenablage.groesse_text(int(1.4 * 1024 * 1024)) == "1,4 MB"


# ── Im Chat ───────────────────────────────────────────────────────────

class FakeZ:
    def __init__(self):
        self.C = defaultdict(int)


@pytest.fixture
def chat(monkeypatch):
    c = chatmod.Chat(FakeZ())
    monkeypatch.setattr(chat_ablage.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda s: target(*args)})())
    return c


def _ablage_mit(monkeypatch, z):
    monkeypatch.setattr(chat_ablage.zwischenablage, "lesen", lambda **k: z)


def test_paste_haengt_bild_an_mit_kaertchen(chat, monkeypatch):
    _ablage_mit(monkeypatch, zwischenablage.Inhalt("bild", PNG, "image/png", None))
    gesendet = []

    def api(pfad, methode="GET", body=None, timeout=3.0):
        gesendet.append((pfad, body))
        return {"id": "a7", "titel": body["pfad"], "art": "bild", "hinweis": ""}
    monkeypatch.setattr(chat_ablage, "api_call", api)
    chat.AI["input"], chat.AI["cur"] = "/paste", 6
    chat.ai_submit()
    pfad, body = gesendet[0]
    assert pfad == "/api/anhang" and base64.b64decode(body["daten"]) == PNG
    assert body["pfad"].startswith("zwischenablage-") and body["pfad"].endswith(".png")
    (a,) = chat.AI["anhaenge"]
    assert a["kaertchen"] == "bild aus der zwischenablage · 293 KB"
    assert chat.AI["input"] == "" and "bild aus der zwischenablage" in chat.AI["msg"]
    zeilen = chat._kasten_zeilen("", 0, chat.AI["anhaenge"], 60, 24, False)
    assert zeilen[0] == ("[▤ bild aus der zwischenablage · 293 KB]", "chip")
    # Mit der nächsten Nachricht geht nur die id mit.
    gestartet = []
    monkeypatch.setattr(chatmod.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda s: gestartet.append(args)})())
    chat.senden("was siehst du?")
    assert gestartet[0][3][0]["id"] == "a7" and chat.AI["anhaenge"] == []


def test_paste_zu_gross_leer_kein_bildschirm(chat, monkeypatch):
    def nie(*a, **k):
        raise AssertionError("darf nicht senden")
    monkeypatch.setattr(chat_ablage, "api_call", nie)
    _ablage_mit(monkeypatch, zwischenablage.Inhalt("bild", b"x" * (5 * 1024 * 1024 + 1),
                                                   "image/png", None))
    chat.befehl("einfuegen", "")
    assert chat.AI["msg"].startswith("bild zu groß (5,0 MB)") and "5 mb" in chat.AI["msg"]
    _ablage_mit(monkeypatch, zwischenablage.Inhalt("leer", None, None, None))
    chat.befehl("einfuegen", "")
    assert chat.AI["msg"] == "die zwischenablage ist leer"
    _ablage_mit(monkeypatch, zwischenablage.Inhalt("nein", None, None, "keine zwischenablage hier"))
    chat.befehl("einfuegen", "")
    assert chat.AI["msg"] == "keine zwischenablage hier" and chat.AI["anhaenge"] == []


def test_paste_mit_text_fuellt_die_eingabe(chat, monkeypatch):
    _ablage_mit(monkeypatch, zwischenablage.Inhalt("text", "hallo welt", None, None))
    chat.AI["input"], chat.AI["cur"] = "/paste", 6
    chat.ai_submit()
    assert (chat.AI["input"], chat.AI["cur"]) == ("hallo welt", 10)


def test_strg_v_bild_nur_hinweis_text_eingefuegt(chat, monkeypatch):
    gefragt = []

    def lesen(**k):
        gefragt.append(k)
        return zwischenablage.Inhalt("bild", b"", "image/png", None)
    monkeypatch.setattr(chat_ablage.zwischenablage, "lesen", lesen)
    chat.taste(22)
    assert chat.AI["msg"] == "bild in der zwischenablage — /paste hängt es an"
    assert gefragt == [{"bild_holen": False}] and chat.AI["anhaenge"] == []
    _ablage_mit(monkeypatch, zwischenablage.Inhalt("text", "ab", None, None))
    chat.AI["input"], chat.AI["cur"] = "xy", 1
    chat.taste(22)
    assert (chat.AI["input"], chat.AI["cur"]) == ("xaby", 3)


def test_befehl_hilfe_und_fussleiste():
    w = chat_befehle.lesen("/paste")
    assert (w.art, w.name) == ("befehl", "einfuegen")
    assert "/paste" in chat_befehle.hilfe_text() and "attach image from clipboard" in chat_befehle.hilfe_text()
    c = chatmod.Chat(FakeZ())
    assert ("ctrl+v", "paste") in c.tasten()
