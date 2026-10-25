"""
Apps aus dem Schaufenster installieren (core/app_installation.py,
POST /api/apps/laden + /api/apps/installieren, 2026-10-25,
memory/hub/shop.md „Apps installieren").

Die App kommt in den Tests aus einem echten git-Repo im Testordner (file://),
der Katalog ist eine Kopie mit dieser Quelle. Geprüft wird: laden zeigt die
Ansichten aus dem app.toml, installieren merkt nur die gewählten, der Ordner
landet an seinem Platz, ein vorhandener Checkout desselben Repos wird
übernommen, ein fremder Ordner nicht überschrieben, und der Hub kennt die App
danach überall (Liste mit Symbol und Ansichten, Start, Werkstatt-Namen).
"""
import json
import os
import struct
import subprocess
import zlib

import pytest

import app_installation as ai
import app_verwaltung
import apps
import shop
import werkstatt

ADRESSE = "zentrale://shop/apps/sparbuch"

MANIFEST = '''name = "sparbuch"
version = "0.1.0"
titel = "Sparbuch"
icon = "icon.png"
start = "python -m sparbuch"
adresse = "http://127.0.0.1:5999"
ansichten = ["browser", "terminal"]
[ansicht.browser]
pfad = "/start"
[ansicht.terminal]
start = "python -m sparbuch tui"
'''


def _png(seite, farbe=(255, 200, 60)):
    roh = b"".join(b"\x00" + bytes(farbe + (255,)) * seite for _ in range(seite))

    def st(art, d):
        return struct.pack(">I", len(d)) + art + d + struct.pack(">I", zlib.crc32(art + d))
    return (b"\x89PNG\r\n\x1a\n" + st(b"IHDR", struct.pack(">IIBBBBB", seite, seite, 8, 6, 0, 0, 0))
            + st(b"IDAT", zlib.compress(roh)) + st(b"IEND", b""))


def _git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                   check=True, capture_output=True)


@pytest.fixture
def laden(tmp_path, monkeypatch):
    """Ein Repo mit app.toml und ein Katalog, der darauf zeigt. → Repo-Pfad."""
    repo = tmp_path / "quelle" / "sparbuch"
    repo.mkdir(parents=True)
    (repo / "app.toml").write_text(MANIFEST, encoding="utf-8")
    (repo / "icon.png").write_bytes(_png(32))
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("add", ".", cwd=repo)
    _git("commit", "-qm", "app", cwd=repo)
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        katalog = json.load(f)
    katalog["itemListElement"].append({"@type": "ListItem", "position": 99, "item": {
        "@type": "SoftwareApplication", "@id": ADRESSE, "identifier": "sparbuch",
        "name": "Sparbuch", "description": "test", "category": "apps", "keywords": ["geld"],
        "downloadUrl": repo.as_uri(),
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
        "additionalProperty": [{"@type": "PropertyValue", "name": "app_name", "value": "sparbuch"}]}})
    k = tmp_path / "katalog.jsonld"
    k.write_text(json.dumps(katalog), encoding="utf-8")
    monkeypatch.setenv("ZENTRALE_SHOP_KATALOG", str(k))
    return repo


def test_laden_zeigt_die_ansichten_und_richtet_noch_nichts_ein(laden):
    r = ai.laden(ADRESSE)
    assert r["name"] == "sparbuch" and r["titel"] == "Sparbuch" and r["neu"] is True
    assert r["ansichten"] == [{"id": "browser", "titel": "im browser"},
                              {"id": "terminal", "titel": "im terminal"}]
    assert r["gewaehlt"] == ["browser", "terminal"] and r["installiert"] is False
    assert ai.alle() == [] and apps.manifest("sparbuch") is None
    assert not os.path.exists(os.path.join(ai.app_ordner(), "sparbuch"))


def test_installieren_merkt_nur_die_gewaehlten(laden):
    ai.laden(ADRESSE)
    r = ai.installieren(ADRESSE, ["browser"])
    ziel = os.path.join(ai.app_ordner(), "sparbuch")
    assert r == {"name": "sparbuch", "titel": "Sparbuch", "ansichten": ["browser"],
                 "ordner": ziel, "adresse": ADRESSE, "neu": True}
    assert os.path.isfile(os.path.join(ziel, "app.toml"))
    assert not os.path.exists(os.path.join(ai.app_ordner(), ai.LADEN, "sparbuch"))
    assert [e["ansichten"] for e in ai.alle()] == [["browser"]]
    assert apps.pfad("sparbuch") == ziel
    # installiert heißt auch geholt
    assert ADRESSE in {o["typeOfGood"]["@id"] for o in
                       (el["item"] for el in shop.besitz("apps")["itemListElement"])}
    # nochmal: nur die Auswahl ändert sich, das erste Datum bleibt
    am = ai.alle()[0]["am"]
    r2 = ai.installieren(ADRESSE, ["terminal", "browser"])
    assert r2["ansichten"] == ["browser", "terminal"] and r2["neu"] is False
    assert ai.alle()[0]["am"] == am
    assert ai.laden(ADRESSE)["gewaehlt"] == ["browser", "terminal"]


def test_installieren_ohne_laden_laedt_selbst(laden):
    assert ai.installieren(ADRESSE, ["terminal"])["ansichten"] == ["terminal"]


@pytest.mark.parametrize("ansichten", [[], None, ["fenster"], "browser"])
def test_ansichten_muessen_passen(laden, ansichten):
    with pytest.raises(ai.InstallFehler) as e:
        ai.installieren(ADRESSE, ansichten)
    assert e.value.code == 400
    assert ai.alle() == []


def test_vorhandener_checkout_wird_uebernommen(laden):
    """Sasha entwickelt die App schon neben ZENTRALE: kein zweiter Klon."""
    ziel = os.path.join(ai.app_ordner(), "sparbuch")
    os.makedirs(ai.app_ordner(), exist_ok=True)
    _git("clone", "-q", laden.as_uri(), ziel, cwd=ai.app_ordner())
    (open(os.path.join(ziel, "eigenes.txt"), "w")).write("bleibt")
    assert ai.laden(ADRESSE)["neu"] is False
    ai.installieren(ADRESSE, ["browser", "terminal"])
    assert os.path.isfile(os.path.join(ziel, "eigenes.txt"))


def test_fremder_ordner_wird_nicht_ueberschrieben(laden):
    ziel = os.path.join(ai.app_ordner(), "sparbuch")
    os.makedirs(ziel)
    open(os.path.join(ziel, "app.toml"), "w").write('name = "anders"\n')
    with pytest.raises(ai.InstallFehler) as e:
        ai.laden(ADRESSE)
    assert e.value.code == 409


def test_kaputte_quelle_hinterlaesst_nichts(laden, tmp_path, monkeypatch):
    k = json.loads(open(os.environ["ZENTRALE_SHOP_KATALOG"], encoding="utf-8").read())
    k["itemListElement"][-1]["item"]["downloadUrl"] = (tmp_path / "gibtsnicht").as_uri()
    p = tmp_path / "k2.jsonld"
    p.write_text(json.dumps(k), encoding="utf-8")
    monkeypatch.setenv("ZENTRALE_SHOP_KATALOG", str(p))
    with pytest.raises(ai.InstallFehler) as e:
        ai.laden(ADRESSE)
    assert e.value.code == 502
    assert os.listdir(os.path.join(ai.app_ordner(), ai.LADEN)) == []


def test_nur_apps_lassen_sich_installieren(laden):
    with pytest.raises(ai.InstallFehler):
        ai.laden("zentrale://shop/icons/post")


def test_katalog_ohne_quelle_ist_kaputt(tmp_path, monkeypatch):
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        k = json.load(f)
    for el in k["itemListElement"]:
        if el["item"]["category"] == "apps":
            del el["item"]["downloadUrl"]
    p = tmp_path / "k.jsonld"
    p.write_text(json.dumps(k), encoding="utf-8")
    monkeypatch.setenv("ZENTRALE_SHOP_KATALOG", str(p))
    with pytest.raises(shop.ShopFehler) as e:
        shop.katalog()
    assert e.value.code == 503


def test_repo_schluessel_kennt_die_schreibweisen():
    a = ai._repo_schluessel("git@github.com:Eightdevvis/budgeter.git")
    assert a == ai._repo_schluessel("ssh://git@github.com/Eightdevvis/budgeter.git") \
        == ai._repo_schluessel("https://github.com/Eightdevvis/budgeter") == "github.com/eightdevvis/budgeter"
    assert ai._ordner_name("ssh://git@github.com/Eightdevvis/budgeter.git") == "budgeter"


# ── Der Hub kennt die App danach ─────────────────────────────────────

def test_liste_zeigt_symbol_quelle_und_eingerichtete_ansichten(laden):
    ai.installieren(ADRESSE, ["browser"])
    (e,) = [a for a in app_verwaltung.liste() if a["name"] == "sparbuch"]
    assert e["quelle"] == ADRESSE and e["art"] == "prozess"
    assert e["ansichten"] == ["browser", "terminal"]          # das Angebot
    assert e["ansichten_installiert"] == [{"id": "browser", "titel": "im browser",
                                           "url": "http://127.0.0.1:5999/start"}]
    assert e["icon"]["art"] == "bild" and len(e["icon"]["raster"]) == 32
    assert e["icon"]["raster"][0][0] == "#ffc83c"
    # feste Apps: alle Ansichten aus dem Manifest, keine Quelle
    (t,) = [a for a in app_verwaltung.liste() if a["name"] == "tutor"]
    assert t["quelle"] is None and [a["id"] for a in t["ansichten_installiert"]] == t["ansichten"]


def test_werkstatt_vergibt_den_namen_nicht_nochmal(laden):
    ai.installieren(ADRESSE, ["browser"])
    with pytest.raises(werkstatt.WerkstattFehler) as e:
        werkstatt.namen_pruefen("Sparbuch")
    assert e.value.code == 409


def test_routen(laden):
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    r = c.post("/api/apps/laden", json={"adresse": ADRESSE})
    assert r.status_code == 200 and r.get_json()["name"] == "sparbuch"
    r = c.post("/api/apps/installieren", json={"adresse": ADRESSE, "ansichten": []})
    assert r.status_code == 400 and r.get_json()["error"]
    r = c.post("/api/apps/installieren", json={"adresse": ADRESSE, "ansichten": ["terminal"]})
    assert r.status_code == 200 and r.get_json()["ansichten"] == ["terminal"]
    assert any(a["name"] == "sparbuch" for a in c.get("/api/apps").get_json())
    assert c.post("/api/apps/laden", json={"adresse": "zentrale://shop/apps/nix"}).status_code == 404


# ── In der TUI: Schaufenster → Wahl → Rad → öffnen ──────────────────

class _Schirm:
    def __init__(self):
        self.zellen = {}

    def addstr(self, y, x, text, attr=0):
        for i, ch in enumerate(text):
            self.zellen[(y, x + i)] = ch

    def text(self):
        return "\n".join("".join(self.zellen.get((y, x), " ") for x in range(140)) for y in range(40))


@pytest.fixture
def tui(laden, monkeypatch):
    """Shop, eigene Apps und Öffner der TUI über den echten Flask-Weg."""
    import io
    import types
    import urllib.error
    from ui.app import app
    from tui.ansichten import app_oeffnen, eigene_apps, shop as ansicht_shop, sprung, startseite
    app.config.update(TESTING=True)
    client = app.test_client()
    aufrufe = []

    def api(pfad, method="GET", body=None, timeout=3.0):
        aufrufe.append((method, pfad))
        if pfad.endswith("/start"):              # die Test-App gibt es nicht als Prozess
            return {"laeuft": True, "gestartet": True}
        r = client.open(pfad, method=method, json=body)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(pfad, r.status_code, "x", {}, io.BytesIO(r.data))
        return r.get_json()
    for m in (ansicht_shop, eigene_apps, app_oeffnen):
        monkeypatch.setattr(m, "api_call", api)
    monkeypatch.setattr(startseite, "EIGENE_APPS", [])
    schirm = _Schirm()
    z = types.SimpleNamespace(C={k: 0 for k in ("faint", "dim", "ink", "bright", "acc", "warn")},
                              safe_addstr=lambda y, x, t, a=0: schirm.addstr(y, x, t),
                              addclip=lambda y, x, t, w, a=0: schirm.addstr(y, x, str(t)[:max(0, w)]),
                              PIX_MODUS="mix", draw_box=lambda *a, **k: None,
                              pix_attr=lambda fg, bg: 0, stdscr=None)
    bz = types.SimpleNamespace(cmd_msg="")
    router = sprung.Router()
    oeffner = app_oeffnen.AppOeffnen(z, bz)
    oeffner.starten = lambda f: f()
    eigene = eigene_apps.EigeneApps(z, router, types.SimpleNamespace(DESK={}), oeffner)
    eigene.starten = lambda f: f()
    laden_shop = ansicht_shop.Shop(z)
    laden_shop.starten = lambda f: f()
    laden_shop.nach_installieren = eigene.laden
    yield types.SimpleNamespace(shop=laden_shop, eigene=eigene, oeffner=oeffner, router=router,
                                bz=bz, schirm=schirm, aufrufe=aufrufe, startseite=startseite)
    from tui import pixel
    pixel.symbol_austragen("sparbuch")              # das Symbol-Verzeichnis ist global


def test_tui_installieren_mit_wahl_und_oeffnen(tui, monkeypatch):
    import curses
    from tui import pixel
    from tui.ansichten import app_oeffnen
    v, S = tui.shop, tui.shop.SHOP
    v.oeffnen()
    while v.kategorie()["id"] != "apps":
        v.taste(curses.KEY_RIGHT)
    while S["stuecke"][S["sel"]]["identifier"] != "sparbuch":
        v.taste(curses.KEY_DOWN)
    assert v.ansicht() == "apps"
    v.taste(10)                                            # enter: laden
    assert v.ansicht() == "wahl" and S["wahl"]["an"] == ["browser", "terminal"]
    v.draw_shop(0, 0, 30, 120)
    assert "[x] im browser" in tui.schirm.text() and "[x] im terminal" in tui.schirm.text()
    v.taste(32); v.taste(curses.KEY_DOWN); v.taste(32)     # browser aus, terminal aus
    v.taste(10)
    assert S["msg"] == "mindestens eine ansicht wählen" and v.ansicht() == "wahl"
    v.taste(curses.KEY_UP); v.taste(32); v.taste(curses.KEY_DOWN); v.taste(32)
    v.taste(10)                                            # beide: installieren
    assert S["wahl"] is None and S["msg"] == "installiert ✓ — steht im app-rad"
    assert [e["ansichten"] for e in ai.alle()] == [["browser", "terminal"]]
    # im Rad, mit Symbol, Adresse beim Router
    assert ("app:sparbuch", "sparbuch") in tui.startseite.rad_apps()
    assert pixel.hat_symbol("sparbuch")
    # öffnen: zwei Ansichten → Wahl; browser startet die App und öffnet die url
    offen = []
    monkeypatch.setattr(app_oeffnen, "im_browser_oeffnen", lambda url: offen.append(url) or True)
    assert tui.router.zeigen("zentrale://sparbuch/")
    o = tui.oeffner
    assert o.W["active"] and o.ansicht() == "wahl"
    o.taste(10)
    assert not o.W["active"] and offen == ["http://127.0.0.1:5999/start"]
    assert ("POST", "/api/apps/sparbuch/start") in tui.aufrufe
    assert tui.bz.cmd_msg == "„sparbuch\" geht im browser auf"
    # terminal: TUI tritt beiseite, der Starter bekommt die Ansicht
    gerufen = []
    for f in ("def_prog_mode", "reset_prog_mode", "endwin"):
        monkeypatch.setattr(curses, f, lambda *a: None)
    monkeypatch.setattr(app_oeffnen.subprocess, "call", lambda cmd: gerufen.append(cmd) or 0)
    tui.router.zeigen("zentrale://sparbuch/")
    o.taste(curses.KEY_DOWN); o.taste(10)
    assert gerufen and gerufen[0][-3:] == ["sparbuch", "--ansicht", "terminal"]
    # nochmal im Laden: nur eine Ansicht → das Rad öffnet direkt
    v.taste(10)
    assert S["wahl"]["installiert"] is True
    v.taste(32)                                            # browser aus
    v.taste(10)
    assert S["msg"] == "ansichten geändert ✓"
    offen.clear(); gerufen.clear()
    tui.router.zeigen("zentrale://sparbuch/")
    assert not o.W["active"] and gerufen and not offen


def test_starter_kennt_die_terminal_ansicht(laden):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "scripts"))
    import open_app_window
    ai.installieren(ADRESSE, ["terminal"])
    ordner, befehl = open_app_window.fenster_befehl("sparbuch", "terminal")
    assert ordner == os.path.join(ai.app_ordner(), "sparbuch") and befehl[-3:] == ["-m", "sparbuch", "tui"]
    assert open_app_window.fenster_befehl("sparbuch")[0] is None          # kein fenster


def test_antworten_passen_zu_openapi(laden):
    import yaml
    from jsonschema import Draft202012Validator
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "openapi.yaml"), encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    def passt(schema, wert):
        v = Draft202012Validator({"components": spec["components"], **schema})
        assert not [e.message for e in v.iter_errors(wert)]
    from ui.app import app
    c = app.test_client()
    passt({"$ref": "#/components/schemas/AppWahl"},
          c.post("/api/apps/laden", json={"adresse": ADRESSE}).get_json())
    ok = spec["paths"]["/api/apps/installieren"]["post"]["responses"]["200"]
    passt(ok["content"]["application/json"]["schema"],
          c.post("/api/apps/installieren", json={"adresse": ADRESSE, "ansichten": ["browser"]}).get_json())
    for a in c.get("/api/apps").get_json():
        passt({"$ref": "#/components/schemas/App"}, a)
