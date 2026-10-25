"""
Das Schaufenster (core/shop.py, ui/routen/shop.py, tui/ansichten/shop.py,
2026-10-10, memory/hub/shop.md): der Katalog ist eine schema.org-ItemList
mit echten Stücken (Preis 0), jede Adresse ist gültig, Filter greifen, holen
ist idempotent, der Besitz kommt zurück (auch von einem anderen Rechner),
Antworten passen zu openapi.yaml, und die Ansicht geht Kategorien, Themen und
holen richtig durch — über den echten Flask-Weg.
"""
import io
import json
import os
import types
import urllib.error

import pytest
import yaml
from jsonschema import Draft202012Validator

import abgleich_auswahl
import adressen
import shop

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture(scope="module")
def spec():
    with open(os.path.join(ROOT, "openapi.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def passt(spec, name, wert):
    schema = {"components": spec["components"], "$ref": "#/components/schemas/%s" % name}
    v = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    fehler = [e.message for e in v.iter_errors(wert)]
    assert not fehler, (name, fehler)


# ── Katalog ──────────────────────────────────────────────────────────

def test_katalog_ist_schema_org_itemlist_mit_preis_null():
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        roh = json.load(f)
    assert roh["@context"] == "https://schema.org" and roh["@type"] == "ItemList"
    stuecke = shop.pruefen(roh)
    assert stuecke
    for el, s in zip(roh["itemListElement"], stuecke):
        assert el["@type"] == "ListItem" and isinstance(el["position"], int)
        assert s["@type"] in shop.TYPEN and s["name"] and s["description"]
        assert s["offers"] == {"@type": "Offer", "price": "0", "priceCurrency": "EUR",
                               "availability": "https://schema.org/InStock"}
        assert isinstance(s["keywords"], list) and s["keywords"]


def test_jede_adresse_ist_gueltig_und_kanonisch():
    for s in shop.katalog()["itemListElement"]:
        it = s["item"]
        a = adressen.lesen(it["@id"])
        assert a == ("shop", (it["category"], it["identifier"]), {})
        assert adressen.kanonisch(it["@id"]) == it["@id"]


def test_icons_sind_alle_motive_des_rads():
    """Sasha (Nachtrag 2026-10-10): ALLE App-Icons aus dem Rad sind holbar."""
    from tui import pixel
    from tui.ansichten import startseite
    icons = {s["item"]["identifier"]: s["item"] for s in shop.katalog("icons")["itemListElement"]}
    # Seit 2026-10-10 (Werkstatt) steht desk nicht mehr im Rad, sein Motiv
    # bleibt holbar; die Motive des Erschaffen-Rads (werkstatt, shop) sind
    # (noch) keine Ware. Darum: jedes App-Rad-Symbol ist da, nichts Erfundenes.
    assert set(startseite.RAD_SYMBOLE) <= set(icons) <= set(pixel.FESTE_MOTIVE) | {"elektronik"}
    for kennung, it in icons.items():
        assert it["@type"] == "ImageObject"
        assert {"@type": "PropertyValue", "name": "pixel_motiv", "value": kennung} \
            in it["additionalProperty"]


def test_agenten_avatare_sind_noch_leer():
    """Nichts Erfundenes. Apps: seit 2026-10-25 Budget, installierbar
    (tests/test_app_installation.py)."""
    for k in ("agenten", "avatare"):
        assert shop.katalog(k)["itemListElement"] == []
    kats = {k["id"]: k["anzahl"] for k in shop.uebersicht()["kategorien"]}
    assert list(kats) == list(shop.KATEGORIE_IDS)
    assert kats["apps"] == 1 and kats["icons"] == 10 and kats["bauteile"] >= 1


def test_jede_app_sagt_woher_sie_kommt():
    """Eine App im Laden ist holbar: git-Repo in downloadUrl, Name der App."""
    budget = shop.stueck("apps", "budget")
    assert budget["@type"] == "SoftwareApplication"
    assert budget["downloadUrl"] == "ssh://git@github.com/Eightdevvis/budgeter.git"
    assert {"@type": "PropertyValue", "name": "app_name", "value": "budget"} \
        in budget["additionalProperty"]


def test_desk_view_vorlage_steht_unter_bauteile():
    it = shop.stueck("bauteile", "desk-view")
    assert it["applicationCategory"] == "Vorlage"


def test_bauteile_verweisen_auf_echte_kachel_arten():
    import kacheln
    arten = {"zentrale://%s/%s" % (app, art) for app, q in kacheln.QUELLEN.items()
             for art in getattr(q, "ARTEN", {})}
    assert arten
    for el in shop.katalog("bauteile")["itemListElement"]:
        if "isBasedOn" in el["item"]:
            assert el["item"]["isBasedOn"] in arten


def test_filter_kategorie_und_thema():
    alle = shop.katalog()["itemListElement"]
    icons = shop.katalog("icons")["itemListElement"]
    assert 0 < len(icons) < len(alle)
    assert all(e["item"]["category"] == "icons" for e in icons)
    planen = shop.katalog(thema="planen")["itemListElement"]
    assert planen and all("planen" in e["item"]["keywords"] for e in planen)
    both = shop.katalog("icons", "planen")["itemListElement"]
    assert {e["item"]["identifier"] for e in both} == {"kalender", "fokus"}
    assert [e["position"] for e in both] == [1, 2]                 # neu gezählt
    assert shop.katalog(thema="gibtsnicht")["numberOfItems"] == 0
    with pytest.raises(shop.ShopFehler) as e:
        shop.katalog("moebel")
    assert e.value.code == 400


def test_kaputter_katalog_ist_laut(tmp_path, monkeypatch):
    p = tmp_path / "k.jsonld"
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        roh = json.load(f)
    roh["itemListElement"][0]["item"]["@id"] = "zentrale://shop/icons/falsch"
    p.write_text(json.dumps(roh), encoding="utf-8")
    monkeypatch.setenv("ZENTRALE_SHOP_KATALOG", str(p))
    with pytest.raises(shop.ShopFehler) as e:
        shop.katalog()
    assert e.value.code == 503
    p.write_text("{kein json", encoding="utf-8")
    with pytest.raises(shop.ShopFehler):
        shop.katalog()


# ── Holen und Besitz ─────────────────────────────────────────────────

def test_holen_ist_idempotent_und_besitz_kommt_zurueck():
    a = shop.adresse("icons", "post")
    r1 = shop.holen(a)
    assert r1["neu"] and r1["geholt"] and r1["adresse"] == a
    r2 = shop.holen(a)
    assert not r2["neu"] and r2["am"] == r1["am"]
    shop.holen(shop.adresse("bauteile", "desk-view"))
    b = shop.besitz()
    assert [e["item"]["typeOfGood"]["@id"] for e in b["itemListElement"]].count(a) == 1
    assert b["numberOfItems"] == 2
    nur_icons = shop.besitz("icons")["itemListElement"]
    assert len(nur_icons) == 1
    gut = nur_icons[0]["item"]
    assert gut["@type"] == "OwnershipInfo" and gut["typeOfGood"]["name"] == "Post"
    # die Datei selbst: ItemList von OwnershipInfo, nur der Verweis
    with open(shop.besitz_datei(), encoding="utf-8") as f:
        datei = json.load(f)
    assert datei["@type"] == "ItemList"
    assert {"@id": a} in [e["item"]["typeOfGood"] for e in datei["itemListElement"]]


def test_besitz_vereinigt_die_rechner(tmp_path):
    a = shop.adresse("icons", "karte")
    fremd = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "item": {
            "@type": "OwnershipInfo", "ownedFrom": "2026-10-01T09:00:00+02:00",
            "typeOfGood": {"@id": a}}},
        {"@type": "ListItem", "position": 2, "item": {
            "@type": "OwnershipInfo", "ownedFrom": "2026-10-02T09:00:00+02:00",
            "typeOfGood": {"@id": "zentrale://shop/icons/weg"}}}]}
    os.makedirs(shop.ordner(), exist_ok=True)
    with open(os.path.join(shop.ordner(), "besitz-anderer.jsonld"), "w", encoding="utf-8") as f:
        json.dump(fremd, f)
    r = shop.holen(a)
    assert not r["neu"] and r["am"] == "2026-10-01T09:00:00+02:00"
    ids = {e["item"]["typeOfGood"]["@id"]: e["item"]["typeOfGood"]
           for e in shop.besitz("icons")["itemListElement"]}
    assert ids["zentrale://shop/icons/weg"] == {"@id": "zentrale://shop/icons/weg",
                                                 "category": "icons", "identifier": "weg"}
    assert not os.path.exists(shop.besitz_datei())       # nichts Neues geschrieben


@pytest.mark.parametrize("adresse, code", [
    ("zentrale://shop/icons/gibtsnicht", 404),
    ("zentrale://kalender/2026-10-12", 400),
    ("zentrale://shop/icons", 400),
    ("http://shop/icons/post", 400),
    (None, 400),
])
def test_holen_lehnt_ab(adresse, code):
    with pytest.raises(shop.ShopFehler) as e:
        shop.holen(adresse)
    assert e.value.code == code
    assert shop.besitz()["numberOfItems"] == 0


def test_was_kostet_wird_heute_nicht_geholt(tmp_path, monkeypatch):
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        roh = json.load(f)
    roh["itemListElement"][0]["item"]["offers"]["price"] = "2.50"
    p = tmp_path / "k.jsonld"
    p.write_text(json.dumps(roh), encoding="utf-8")
    monkeypatch.setenv("ZENTRALE_SHOP_KATALOG", str(p))
    with pytest.raises(shop.ShopFehler) as e:
        shop.holen(roh["itemListElement"][0]["item"]["@id"])
    assert e.value.code == 402


def test_besitz_ordner_steht_auf_der_positivliste():
    for liste in (abgleich_auswahl.ABGLEICH, abgleich_auswahl.SICHERN):
        assert abgleich_auswahl.passt("data/shop/besitz-pc.jsonld", liste)
    assert not abgleich_auswahl.passt("data/shop/.besitz-pc.jsonld.1.2.tmp",
                                      abgleich_auswahl.ABGLEICH)


# ── Routen gegen openapi.yaml ────────────────────────────────────────

def test_routen_passen_zur_datei(spec, client):
    r = client.get("/api/shop")
    assert r.status_code == 200 and r.mimetype == "application/ld+json"
    passt(spec, "ShopKatalog", r.get_json())
    r = client.get("/api/shop?kategorie=icons&thema=planen")
    passt(spec, "ShopKatalog", r.get_json())
    assert r.get_json()["numberOfItems"] == 2
    passt(spec, "ShopUebersicht", client.get("/api/shop/kategorien").get_json())
    r = client.get("/api/shop/icons/post")
    assert r.status_code == 200
    passt(spec, "ShopStueck", r.get_json())
    body = {"adresse": "zentrale://shop/icons/post"}
    passt(spec, "ShopHolenAnfrage", body)
    r = client.post("/api/shop/holen", json=body)
    assert r.status_code == 200 and r.get_json()["neu"]
    passt(spec, "ShopHolenAntwort", r.get_json())
    assert client.post("/api/shop/holen", json=body).get_json()["neu"] is False
    r = client.get("/api/shop/besitz?kategorie=icons")
    passt(spec, "ShopBesitz", r.get_json())
    assert r.get_json()["itemListElement"][0]["item"]["typeOfGood"]["@id"] == body["adresse"]
    assert client.get("/api/shop/besitz?kategorie=apps").get_json()["numberOfItems"] == 0


@pytest.mark.parametrize("methode, pfad, body, status", [
    ("GET", "/api/shop?kategorie=moebel", None, 400),
    ("GET", "/api/shop/icons/gibtsnicht", None, 404),
    ("GET", "/api/shop/moebel/x", None, 400),
    ("POST", "/api/shop/holen", {}, 400),
    ("POST", "/api/shop/holen", {"adresse": "zentrale://shop/icons/nix"}, 404),
    ("GET", "/api/shop/besitz?kategorie=moebel", None, 400),
])
def test_fehler_passen(spec, client, methode, pfad, body, status):
    r = client.open(pfad, method=methode, json=body)
    assert r.status_code == status
    passt(spec, "ShopFehler", r.get_json())
    vorlage = pfad.split("?")[0]
    if vorlage.count("/") == 4:
        vorlage = "/api/shop/{kategorie}/{kennung}"
    assert str(status) in spec["paths"][vorlage][methode.lower()]["responses"]


# ── Die Ansicht (über den echten Flask-Weg) ──────────────────────────

class _Schirm:
    def __init__(self):
        self.zellen = {}

    def getmaxyx(self):
        return 40, 140

    def addstr(self, y, x, text, attr=0):
        for i, ch in enumerate(text):
            self.zellen[(y, x + i)] = ch

    def zeile(self, y):
        return "".join(self.zellen.get((y, x), " ") for x in range(140))


@pytest.fixture
def ansicht(client, monkeypatch):
    from tui.ansichten import shop as ansicht_shop

    def api(pfad, method="GET", body=None, timeout=3.0):
        r = client.open(pfad, method=method, json=body)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(pfad, r.status_code, "x", {}, io.BytesIO(r.data))
        return r.get_json()
    monkeypatch.setattr(ansicht_shop, "api_call", api)
    schirm = _Schirm()

    def addclip(y, x, text, maxw, attr=0):
        schirm.addstr(y, x, str(text)[:max(0, maxw)])
    z = types.SimpleNamespace(C={k: 0 for k in ("faint", "dim", "ink", "bright", "acc", "warn")},
                              safe_addstr=lambda y, x, t, a=0: schirm.addstr(y, x, t),
                              addclip=addclip, PIX_MODUS="mix",
                              draw_box=lambda *a, **k: None, pix_attr=lambda fg, bg: 0)
    v = ansicht_shop.Shop(z)
    v.schirm = schirm
    return v


def _namen(v):
    return [s["identifier"] for s in v.SHOP["stuecke"]]


def test_ansicht_kategorien_thema_holen(ansicht):
    import curses
    v, S = ansicht, ansicht.SHOP
    assert S["active"] is False and v.z.SHOP is S
    v.oeffnen()
    assert S["active"] and v.kategorie()["id"] == "icons" and len(_namen(v)) == 10
    assert "planen" in S["themen"] and S["thema"] is None
    # ←→ wechselt die Kategorie (rundum), das Thema geht zurück auf „alle"
    v.taste(curses.KEY_RIGHT)
    assert v.kategorie()["id"] == "hintergruende" and "denkadern" in _namen(v)
    v.taste(curses.KEY_LEFT); v.taste(curses.KEY_LEFT)
    assert v.kategorie()["id"] == "avatare" and S["stuecke"] == []
    v.taste(10)                                       # leer: enter tut nichts
    v.taste(curses.KEY_RIGHT)
    # tab: alle → erstes Thema …; der Hub filtert
    v.taste(9)
    assert S["thema"] == S["themen"][0]
    while S["thema"] != "planen":
        v.taste(9)
    assert sorted(_namen(v)) == ["fokus", "kalender"]
    v.taste(curses.KEY_BTAB)
    assert S["thema"] != "planen"
    while S["thema"] != "planen":
        v.taste(9)
    # ↑↓ wählen, enter holt → geholt ✓, nochmal → schon da
    v.taste(curses.KEY_DOWN); v.taste(curses.KEY_DOWN)       # unten bleibt unten
    gewaehlt = S["stuecke"][S["sel"]]["@id"]
    assert S["sel"] == 1
    v.taste(10)
    assert gewaehlt in S["besitz"] and S["msg"] == "geholt ✓"
    v.taste(10)
    assert S["msg"] == "hast du schon ✓"
    assert gewaehlt in [e["item"]["typeOfGood"]["@id"] for e in shop.besitz("icons")["itemListElement"]]
    # wieder öffnen: der Besitz ist markiert
    v.taste(27)
    assert S["active"] is False
    v.oeffnen()
    assert gewaehlt in S["besitz"]


def test_ansicht_zeichnet_leer_und_voll(ansicht):
    import curses
    v = ansicht
    v.oeffnen()
    v.draw_shop(0, 0, 30, 120)
    alles = "\n".join(v.schirm.zeile(y) for y in range(30))
    assert "Icons 10" in alles and "Post" in alles and "kostenlos" in alles
    # Tastenhinweise stehen nur in der Leiste ganz unten (Tastentabelle, 2026-10-11)
    assert "enter = holen" not in alles and "tab wechselt" not in alles
    v.taste(10)
    v.schirm.zellen.clear()
    v.draw_shop(0, 0, 30, 120)
    alles = "\n".join(v.schirm.zeile(y) for y in range(30))
    assert "✓ Post" in alles and "geholt ✓" in alles
    for _ in range(4):                                         # Agenten
        v.taste(curses.KEY_RIGHT)
    v.schirm.zellen.clear()
    v.draw_shop(0, 0, 30, 120)
    assert "noch leer" in "\n".join(v.schirm.zeile(y) for y in range(30))
    for h, w in ((24, 80), (8, 30), (3, 10)):                  # klein: kein Absturz
        v.draw_shop(0, 0, h, w)


def test_ansicht_ohne_backend(ansicht, monkeypatch):
    from tui.ansichten import shop as ansicht_shop

    def weg(*a, **k):
        raise urllib.error.URLError("weg")
    monkeypatch.setattr(ansicht_shop, "api_call", weg)
    ansicht.oeffnen()
    assert ansicht.SHOP["active"] and ansicht.SHOP["msg"] == "backend nicht erreichbar"
    ansicht.taste(9); ansicht.taste(10)
    ansicht.draw_shop(0, 0, 24, 80)
