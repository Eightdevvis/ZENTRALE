"""
Bilder auf dem Desk (2026-10-10, memory/system/desk_view.md „Bild"):
Sashas ASCII-Filter als Python (core/bild_vorschau.py), Bilder in den
Desk-Ordner übernehmen (core/desk_bild.py), der file-Knoten in der
.canvas-Datei (core/desk.py), die Routen, die Art „bild" im Canvas und das
Öffnen im Bildbetrachter (tui/ansichten/bild_betrachter.py) — ohne echten
Betrachter zu starten.
"""
import io
import json
import os
import subprocess
import urllib.error

import pytest
from PIL import Image

import abgleich_auswahl
import abgleich_zusammenfuehren as zf
import bild_vorschau as bv
import desk
import desk_bild


@pytest.fixture(autouse=True)
def _frisch(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_NUTZER_ORDNER", str(tmp_path / "nutzer"))
    bv.cache_leeren()


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def halb_halb(pfad, links=(0, 0, 0), rechts=(255, 255, 255), groesse=(80, 40)):
    """Links eine Farbe, rechts eine andere."""
    img = Image.new("RGB", groesse, links)
    img.paste(Image.new("RGB", (groesse[0] // 2, groesse[1]), rechts), (groesse[0] // 2, 0))
    img.save(pfad)
    return str(pfad)


def zeichen(zeilen):
    return ["".join(z for z, _f in reihe) for reihe in zeilen]


# ── Der Filter ────────────────────────────────────────────────────────

def test_filter_schwarz_weiss_mono(tmp_path):
    z = bv.vorschau(halb_halb(tmp_path / "a.png"), 10, 3)
    # Die Kante in der Mitte wird beim Verkleinern weich (wie drawImage im
    # Browser) — gezählt wird außen.
    assert [r[:4] + r[-4:] for r in zeichen(z)] == ["    @@@@"] * 3
    assert all(f is None for reihe in z for _z, f in reihe)


def test_filter_invert_und_kleine_rampe(tmp_path):
    img = Image.open(halb_halb(tmp_path / "a.png"))
    z = bv.filtern(img, 4, 1, invert=True, rampe=bv.RAMPE_KLEIN)
    assert zeichen(z)[0][0] == "@" and zeichen(z)[0][-1] == " "


def test_auto_levels_zieht_flaue_bilder_auseinander(tmp_path):
    """100 gegen 150 Grau: ohne Stretch beides Mitte der Rampe, mit Stretch
    (1 %/99 %) wie schwarz/weiß — wie stretchCanvas im Original."""
    p = halb_halb(tmp_path / "flau.png", (100, 100, 100), (150, 150, 150))
    assert [r[:4] + r[-4:] for r in zeichen(bv.vorschau(p, 10, 2))] == ["    @@@@"] * 2
    flach = Image.new("RGB", (20, 10), (120, 120, 120))
    assert bv.auto_levels(flach).getpixel((0, 0)) == (120, 120, 120)   # flacher Kanal bleibt


def test_gamma_hebt_mitteltoene(tmp_path):
    Image.new("RGB", (20, 10), (128, 128, 128)).save(tmp_path / "g.png")
    img = Image.open(tmp_path / "g.png")
    hell = zeichen(bv.filtern(img, 2, 1, gamma=0.5))[0]
    dunkel = zeichen(bv.filtern(img, 2, 1, gamma=2.0))[0]
    assert bv.RAMPE_FOTO.index(hell[0]) > bv.RAMPE_FOTO.index(dunkel[0])


def test_farbe_gibt_blockfarbe_leerzeichen_ohne(tmp_path):
    p = halb_halb(tmp_path / "r.png", (0, 0, 0), (255, 0, 0))
    z = bv.vorschau(p, 10, 2, "farbe")
    links, rechts = z[0][0], z[0][9]
    assert links == [" ", None]
    assert rechts[0] != " " and rechts[1] == "#ff0000"


def test_zelle_ist_doppelt_so_hoch(tmp_path):
    assert bv.zellen_fuer(200, 100, 32) == 8
    assert bv.zellen_fuer(100, 100, 32) == 16


def test_palette_hoechstens_32_farben(tmp_path):
    img = Image.new("RGB", (64, 64))
    img.putdata([(x * 4, y * 4, (x * y) % 256) for y in range(64) for x in range(64)])
    img.save(tmp_path / "bunt.png")
    z = bv.vorschau(str(tmp_path / "bunt.png"), 40, 20, "farbe")
    farben = {f for reihe in z for _z, f in reihe if f}
    assert 1 < len(farben) <= bv.FARBEN_HOECHSTENS
    gekappt = bv.palette_kappen([(i, 255 - i, (i * 7) % 256) for i in range(256)], 8)
    assert len(set(gekappt)) <= 8 and len(gekappt) == 256


def test_rgb_256_wie_in_der_tui():
    """Die Kopie im Kern rechnet wie tui/pixel.py (gleiche Farbpaare)."""
    from tui import pixel
    for c in [(0, 0, 0), (255, 0, 0), (12, 200, 99), (128, 128, 128), (250, 250, 251)]:
        assert bv.rgb_256(c) == pixel.rgb_256(c)
        n = bv.rgb_256(c)
        assert bv.xterm_rgb(n) == pixel.xterm_rgb(n)


def test_cache_nach_datei_stand(tmp_path):
    p = halb_halb(tmp_path / "c.png")
    a = bv.vorschau(p, 6, 2)
    assert bv.vorschau(p, 6, 2) is a                 # gemerkt
    assert bv.vorschau(p, 6, 2, "farbe") is not a    # anderer Modus
    halb_halb(p, (255, 255, 255), (0, 0, 0))
    os.utime(p, (1, 1))                              # anderer Stand
    z = zeichen(bv.vorschau(p, 6, 2))
    assert [r[0] + r[-1] for r in z] == ["@ "] * 2


def test_kein_bild_und_weg(tmp_path):
    (tmp_path / "x.png").write_text("kein bild")
    with pytest.raises(bv.KeinBild):
        bv.vorschau(str(tmp_path / "x.png"), 4, 2)
    with pytest.raises(FileNotFoundError):
        bv.vorschau(str(tmp_path / "fehlt.png"), 4, 2)


# ── Übernehmen in den Desk-Ordner ─────────────────────────────────────

def input_ordner():
    import nutzer_ordner
    return nutzer_ordner.unterordner("Input")


def test_uebernehmen_kopiert_nach_bilder(tmp_path):
    halb_halb(os.path.join(input_ordner(), "Foto 1.png"), groesse=(320, 160))
    info = desk_bild.uebernehmen("Foto 1.png")
    assert info["datei"] == "bilder/Foto 1.png" and info["titel"] == "Foto 1"
    assert info["w"] == 34 and info["h"] == 8 + 3          # 32 innen, 2:1 → 8 Zeilen
    ziel = os.path.join(desk.ordner(), "bilder", "Foto 1.png")
    assert os.path.isfile(ziel)
    assert os.path.isfile(os.path.join(input_ordner(), "Foto 1.png"))   # Quelle bleibt
    assert desk_bild.uebernehmen("Foto 1.png")["datei"] == "bilder/Foto 1.png"   # gleiches Bild
    anders = halb_halb(tmp_path / "Foto 1.png", (9, 9, 9))
    assert desk_bild.uebernehmen(anders)["datei"] == "bilder/Foto 1-2.png"     # Pfad, anderer Inhalt
    assert [q["name"] for q in desk_bild.quellen()] == ["Foto 1.png"]


def test_uebernehmen_nur_echte_bilder(tmp_path):
    (tmp_path / "falsch.png").write_text("text")
    with pytest.raises(desk.DeskFehler) as e:
        desk_bild.uebernehmen(str(tmp_path / "falsch.png"))
    assert e.value.code == 422
    (tmp_path / "notiz.txt").write_text("x")
    with pytest.raises(desk.DeskFehler):
        desk_bild.uebernehmen(str(tmp_path / "notiz.txt"))
    with pytest.raises(desk.DeskFehler) as e:
        desk_bild.uebernehmen("gibtsnicht.png")
    assert e.value.code == 404
    assert not os.path.exists(os.path.join(desk.ordner(), "bilder", "falsch.png"))


@pytest.mark.parametrize("datei", ["../x.png", "/etc/x.png", "bilder/x.txt", "", "a//b.png"])
def test_datei_ohne_weg_hinaus(datei):
    with pytest.raises(desk.DeskFehler):
        desk_bild.pfad(datei)


def test_vorschau_weg_und_kein_bild():
    assert desk_bild.vorschau("bilder/fehlt.png", 10, 4)["status"] == "weg"
    os.makedirs(desk_bild.bilder_ordner(), exist_ok=True)
    with open(os.path.join(desk_bild.bilder_ordner(), "kaputt.png"), "w") as f:
        f.write("x")
    v = desk_bild.vorschau("bilder/kaputt.png", 10, 4)
    assert v["status"] == "kein_bild" and "kein bild" in v["text"]


# ── Der Knoten in der .canvas-Datei ───────────────────────────────────

def test_bild_knoten_rundreise_mit_eigenen_feldern():
    desk.anlegen("Geige")
    st = desk.laden("Geige")["stand"]
    el = {"id": "b1", "art": "bild", "x": 2, "y": 3, "w": 34, "h": 11,
          "datei": "bilder/geige.png", "titel": "", "modus": "mono"}
    d = desk.speichern("Geige", [el], [], st)
    with open(os.path.join(desk.ordner(), "Geige.canvas")) as f:
        roh = json.load(f)
    k = roh["nodes"][0]
    assert k["type"] == "file" and k["file"] == "bilder/geige.png"
    assert "zentrale_titel" not in k and "zentrale_bildmodus" not in k
    # Obsidian setzt eine Farbe dazu — sie muss jedes Speichern überleben.
    k["color"] = "4"
    k["obsidian_irgendwas"] = {"a": 1}
    with open(os.path.join(desk.ordner(), "Geige.canvas"), "w") as f:
        json.dump(roh, f)
    d = desk.laden("Geige")
    b = d["elemente"][0]
    assert b["art"] == "bild" and b["datei"] == "bilder/geige.png" and b["modus"] == "mono"
    b.update(titel="  Meine   Geige ", modus="farbe")
    desk.speichern("Geige", [b], [], d["stand"])
    with open(os.path.join(desk.ordner(), "Geige.canvas")) as f:
        k = json.load(f)["nodes"][0]
    assert k["zentrale_titel"] == "Meine Geige" and k["zentrale_bildmodus"] == "farbe"
    assert k["color"] == "4" and k["obsidian_irgendwas"] == {"a": 1}
    d = desk.laden("Geige")
    assert d["elemente"][0]["titel"] == "Meine Geige" and d["elemente"][0]["modus"] == "farbe"
    b = dict(d["elemente"][0], titel="", modus="mono")
    desk.speichern("Geige", [b], [], d["stand"])
    with open(os.path.join(desk.ordner(), "Geige.canvas")) as f:
        k = json.load(f)["nodes"][0]
    assert "zentrale_titel" not in k and "zentrale_bildmodus" not in k and k["color"] == "4"


def test_neues_bild_mit_falschem_pfad_wird_abgelehnt():
    desk.anlegen("x")
    st = desk.laden("x")["stand"]
    el = {"id": "b1", "art": "bild", "x": 0, "y": 0, "w": 10, "h": 5, "datei": "../geheim.png"}
    with pytest.raises(desk.DeskFehler):
        desk.speichern("x", [el], [], st)


def test_abgleich_nimmt_bilder_mit_und_als_ganzes():
    """Bilder im Desk-Ordner gehen mit dem Abgleich (data/desk/**); als
    Binärdatei werden sie nie zusammengeführt, sondern ganz genommen."""
    assert abgleich_auswahl.passt("data/desk/bilder/geige.png", abgleich_auswahl.ABGLEICH)
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 10, 10)).save(buf, "PNG")
    png = buf.getvalue()
    assert zf.art("data/desk/bilder/geige.png", png) == "ganz"
    neu = png + b"\x00"
    assert zf.zusammenfuehren("data/desk/bilder/geige.png", png, neu, png).inhalt == neu


# ── Routen ────────────────────────────────────────────────────────────

def test_routen(client):
    halb_halb(os.path.join(input_ordner(), "r.png"))
    assert client.get("/api/desk-bild/quellen").get_json()["quellen"][0]["name"] == "r.png"
    r = client.post("/api/desk-bild", json={"quelle": "r.png"})
    assert r.status_code == 201 and r.get_json()["datei"] == "bilder/r.png"
    v = client.post("/api/desk-bild/vorschau",
                    json={"datei": "bilder/r.png", "w": 8, "h": 2, "modus": "farbe"}).get_json()
    assert v["status"] == "ok" and len(v["zeilen"]) == 2 and len(v["zeilen"][0]) == 8
    assert client.post("/api/desk-bild/vorschau",
                       json={"datei": "bilder/weg.png", "w": 8, "h": 2}).get_json()["status"] == "weg"
    assert client.post("/api/desk-bild/vorschau",
                       json={"datei": "../x.png", "w": 8, "h": 2}).status_code == 400
    assert client.post("/api/desk-bild/vorschau",
                       json={"datei": "bilder/r.png", "w": 8, "h": 2, "modus": "x"}).status_code == 400
    o = client.post("/api/desk-bild/oeffnen", json={"datei": "bilder/r.png"}).get_json()
    assert o["da"] and o["pfad"].endswith(os.path.join("bilder", "r.png")) and o["betrachter"] == "system"
    r = client.get("/api/desk-bild/datei?datei=bilder/r.png")
    assert r.status_code == 200 and r.data[:4] == b"\x89PNG"
    assert client.get("/api/desk-bild/datei?datei=bilder/weg.png").status_code == 404
    assert client.post("/api/desk-bild", json={"quelle": ""}).status_code == 400


# ── TUI: Art „bild" und Öffnen ────────────────────────────────────────

def test_art_bild_zeichnet_titel_und_vorschau_f_schaltet():
    from tui.bausteine.canvas_bild import Bild, titel
    b = Bild()
    el = b.neu("b", 0, 0, "bilder/Geige.jpg", 12, 6)
    assert titel(el) == "Geige"
    assert b.zeichne(el, 10, 4)[1] == [("lädt …", "leise")]
    el["_vorschau"] = {"status": "ok", "zeilen": [[["@", "#ff0000"], [" ", None], ["#", None]]]}
    zeilen = b.zeichne(el, 10, 4)
    assert zeilen[0] == [("Geige", "bild_titel")]
    assert zeilen[1] == [("@", "#ff0000"), (" ", "bild"), ("#", "bild")]
    assert b.taste(el, "f") is True and el["modus"] == "farbe" and "_vorschau" not in el
    assert b.taste(el, "x") is False
    el["_vorschau"] = {"status": "weg", "text": "bild fehlt: bilder/Geige.jpg"}
    assert b.zeichne(el, 30, 4)[1] == [("bild fehlt: bilder/Geige.jpg", "leise")]
    assert b.oeffnen(el) == ("bild_oeffnen", "bilder/Geige.jpg")
    m = b.modal(el)
    for ch in b"Neu":
        m.taste(ch)
    assert m.taste(10) == "speichern" and m.aenderungen() == {"titel": "Neu"}


def test_betrachter_befehl_und_abgeloest(monkeypatch, tmp_path):
    from tui.ansichten import bild_betrachter as bb
    monkeypatch.setattr(bb.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(bb.sys, "platform", "linux")
    assert bb.befehl(["/a/b.png"]) == ["/usr/bin/xdg-open", "/a/b.png"]
    assert bb.befehl(["/a/b.png"], "feh -F") == ["feh", "-F", "/a/b.png"]
    monkeypatch.setattr(bb.shutil, "which", lambda n: "/usr/bin/gio" if n == "gio" else None)
    assert bb.befehl(["/a/b.png"]) == ["/usr/bin/gio", "open", "/a/b.png"]
    with pytest.raises(OSError):
        bb.befehl(["/a/b.png"], "feh")                # nicht installiert
    monkeypatch.setattr(bb.shutil, "which", lambda n: None)
    with pytest.raises(OSError):
        bb.befehl(["/a/b.png"])
    gestartet = []
    monkeypatch.setattr(bb.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(bb.subprocess, "Popen", lambda cmd, **kw: gestartet.append((cmd, kw)))
    assert bb.oeffnen(["/a/b.png"], "feh") == "feh"
    cmd, kw = gestartet[0]
    assert cmd == ["feh", "/a/b.png"] and kw["start_new_session"] is True
    assert kw["stdin"] is kw["stdout"] is kw["stderr"] is subprocess.DEVNULL


class Schirm:
    def getch(self):
        return -1

    def getmaxyx(self):
        return (30, 100)

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def ansicht(monkeypatch, client):
    import curses
    from tui.ansichten import desk as desk_ansicht
    from tui.ansichten import kontext
    monkeypatch.setattr(curses, "keyname", lambda c: b"")

    def api(pfad, method="GET", body=None, timeout=3.0):
        r = client.open(pfad, method=method, json=body)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(pfad, r.status_code, "x", {}, io.BytesIO(r.data))
        return r.get_json()
    monkeypatch.setattr(desk_ansicht, "api_call", api)
    z = kontext.Kontext(Schirm(), None, False, None)
    z.apply_theme("night")
    return desk_ansicht.Desk(z)


def test_ansicht_bild_hinlegen_vorschau_oeffnen(ansicht, monkeypatch):
    import curses
    from tui.ansichten import desk as desk_ansicht
    d, D = ansicht, ansicht.DESK
    halb_halb(os.path.join(input_ordner(), "foto.png"), groesse=(200, 100))
    desk.anlegen("Bilder")
    d.oeffnen()
    d.taste(10)                                    # „Bilder" öffnen
    d.draw_desk(2, 0, 26, 100)
    d.taste(ord("+"))
    d.taste(curses.KEY_DOWN)                       # „bild"
    d.taste(10)
    assert D["bild_wahl"]["quellen"][0]["name"] == "foto.png"
    d.taste(10)                                    # foto.png nehmen
    assert D["bild_wahl"] is None and D["canvas"].modus == "greifen"
    d.taste(10)                                    # ablegen → gespeichert
    el = desk.laden("Bilder")["elemente"][0]
    assert el["art"] == "bild" and el["datei"] == "bilder/foto.png"
    d.draw_desk(2, 0, 26, 100)
    b = D["canvas"].elemente[0]
    assert b["_vorschau"]["status"] == "ok"
    with open(os.path.join(desk.ordner(), "Bilder.canvas")) as f:
        assert "_vorschau" not in f.read()         # Zwischengelegtes bleibt in der TUI
    d.taste(ord("f"))                              # farbe, gespeichert
    assert desk.laden("Bilder")["elemente"][0]["modus"] == "farbe"
    d.draw_desk(2, 0, 26, 100)
    assert any(f for reihe in b["_vorschau"]["zeilen"] for _z, f in reihe)
    geoeffnet = []
    monkeypatch.setattr(desk_ansicht.bild_betrachter, "oeffnen",
                        lambda dateien, betrachter: geoeffnet.append((dateien, betrachter)) or "feh")
    d.taste(ord("o"))
    assert geoeffnet == [([os.path.join(os.path.realpath(desk.ordner()), "bilder", "foto.png")],
                          "system")]
    assert D["msg"] == "geöffnet mit feh"
    os.unlink(os.path.join(desk.ordner(), "bilder", "foto.png"))
    d.taste(ord("o"))
    assert "fehlt" in D["msg"] and len(geoeffnet) == 1


def test_ansicht_bild_per_pfad_getippt(ansicht, tmp_path):
    import curses
    d, D = ansicht, ansicht.DESK
    p = halb_halb(tmp_path / "anderswo.png")
    desk.anlegen("P")
    d.oeffnen()
    d.taste(10)
    d.draw_desk(2, 0, 26, 100)
    d.taste(ord("+"))
    d.taste(curses.KEY_DOWN)
    d.taste(10)
    d.taste(curses.KEY_DOWN)                       # (keine Bilder) → „pfad tippen …"
    d.taste(10)
    assert D["bild_wahl"]["pfad"] is not None
    for ch in p.encode():
        d.taste(ch)
    d.taste(10)
    assert D["canvas"].modus == "greifen"
    d.taste(27)                                    # esc: neues Bild wieder weg
    assert D["canvas"].elemente == []
