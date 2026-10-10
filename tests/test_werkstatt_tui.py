"""
Werkstatt in der TUI (2026-10-10, memory/system/werkstatt.md): drei Räder
auf der Startseite (Apps, Technik, Erschaffen) samt Hot-Reload-Stellung, die
Plätze im Rad, Elektronik als fester Desk, der Schmied Schritt für Schritt
(bauen, abbrechen, Namensprüfung), die eigene App im Rad mit Symbol und
Adresse, Löschen. Die Ansichten reden über api_call direkt mit dem
Flask-Test-Client — also mit dem echten core/werkstatt.py und core/desk.py
in Wegwerf-Ordnern.
"""
import curses
import io
import types
import urllib.error

import pytest

from tui import pixel
from tui import zentrale_tui as zt
from tui.ansichten import desk as desk_ansicht
from tui.ansichten import eigene_apps, kontext, rad_wahl, sprung, startseite
from tui.ansichten import werkstatt as werkstatt_ansicht

ENTER, ESC = 10, 27


class Schirm:
    def getch(self):
        return -1

    def getmaxyx(self):
        return (40, 140)

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def client(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setenv("ZENTRALE_NUTZER_ORDNER", str(tmp_path / "nutzer"))
    (tmp_path / "nutzer" / "Input").mkdir(parents=True)
    bild = Image.new("RGB", (64, 64), (30, 90, 220))
    for x in range(16, 48):
        for y in range(16, 48):
            bild.putpixel((x, y), (250, 200, 40))
    bild.save(tmp_path / "nutzer" / "Input" / "probe.png")
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def u(client, monkeypatch):
    """Ein Bündel wie in run_ui: Desk, Router, eigene Apps, Werkstatt."""
    monkeypatch.setattr(curses, "keyname", lambda c: b"")
    aufrufe = []

    def api(pfad, method="GET", body=None, timeout=3.0):
        aufrufe.append((method, pfad))
        r = client.open(pfad, method=method, json=body)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(pfad, r.status_code, "x", {}, io.BytesIO(r.data))
        return r.get_json()
    for modul in (desk_ansicht, werkstatt_ansicht, eigene_apps):
        monkeypatch.setattr(modul, "api_call", api)
    monkeypatch.setattr(startseite, "EIGENE_APPS", [])
    z = kontext.Kontext(Schirm(), None, False, None)
    z.apply_theme("night")
    d = desk_ansicht.Desk(z)
    kal = types.SimpleNamespace(K={"active": False})
    router = sprung.router_fuer(d.DESK, kal)
    eigene = eigene_apps.EigeneApps(z, router, d)
    eigene.starten = lambda f: f()                 # gleich holen, nicht im Thread
    w = werkstatt_ansicht.Werkstatt(z, eigene, d, router)
    bz = types.SimpleNamespace(cmd_msg="")
    yield types.SimpleNamespace(z=z, desk=d, DESK=d.DESK, router=router, eigene=eigene,
                                werkstatt=w, W=w.W, bz=bz, aufrufe=aufrufe)
    for slug in list(pixel.MOTIVE):                # eingetragene Symbole wieder weg
        pixel.symbol_austragen(slug)


def tippe(w, text):
    for b in text.encode("utf-8"):
        w.taste(b)


def waehle(w, text):
    """Den Punkt mit diesem Text ansteuern und Enter."""
    texte = [t for t, _a in w.punkte()]
    assert any(t.startswith(text) for t in texte), (text, texte)
    w.W["sel"] = next(i for i, t in enumerate(texte) if t.startswith(text))
    w.taste(ENTER)


def bauen(w, name="Geige", symbol="ein bild"):
    w.oeffnen()
    waehle(w, "neue app bauen")
    tippe(w, name)
    w.taste(ENTER)
    waehle(w, symbol)
    if symbol == "ein bild":
        waehle(w, "probe.png")
    waehle(w, "Desk View")
    waehle(w, "weiter")
    waehle(w, "ja, bauen")


# ── Drei Räder ────────────────────────────────────────────────────────

def test_alt_pfeile_gehen_schritt_fuer_schritt_ueber_drei_raeder():
    m = startseite
    meta, rad, trad, erad = {"gsel": 0, "fokus": 0}, {"sel": 0}, {"sel": 0}, {"sel": 0}
    for erwartet in (1, 2, 2):                     # am rechten Rand bleibt es stehen
        m.meta_taste(meta, rad, trad, "alt_rechts", erad)
        assert meta["fokus"] == meta["gsel"] == erwartet
    assert m.meta_taste(meta, rad, trad, "enter", erad) == ("erschaffen", "werkstatt")
    m.meta_taste(meta, rad, trad, "rechts", erad)
    assert erad["sel"] == 1 and rad["sel"] == trad["sel"] == 0
    assert m.meta_taste(meta, rad, trad, "enter", erad) == ("erschaffen", "shop")
    for erwartet in (1, 0, 0):                     # am linken Rand auch
        m.meta_taste(meta, rad, trad, "alt_links", erad)
        assert meta["fokus"] == erwartet
    assert m.meta_taste(meta, rad, trad, "enter", erad) == ("app", "k")


@pytest.mark.parametrize("env, erwartet", [
    ("2,0,1,1", (2, False, 1, 1)), ("1,0,2", (1, False, 2, 0)),   # alte Form: drei Zahlen
    ("9,0,0,0", (2, False, 0, 0)), ("-3,0,0,4", (0, False, 0, 4)), ("murks", (0, False, 0, 0))])
def test_stellung_der_raeder_reist_mit_dem_hot_reload(monkeypatch, env, erwartet):
    monkeypatch.setenv("ZENTRALE_TUI_META", env)
    assert zt._meta_start() == erwartet


def test_hot_reload_schreibt_vier_zahlen():
    import inspect
    quelle = inspect.getsource(zt.main)
    assert '"%d,%d,%d,%d"' in quelle and 'ERAD["sel"]' in quelle


def test_plaetze_im_rad():
    namen = [n for _k, n in startseite.RAD_APPS]
    assert "desk" not in namen and "elektronik" in namen       # desk ist ein Baustein
    assert namen.index("kalender") == 2 and namen[-1] == "elektronik"
    assert startseite.ERSCHAFFEN_APPS == ["werkstatt", "shop"]
    for name in startseite.ERSCHAFFEN_APPS:
        assert pixel.hat_symbol(name)
        zeilen, schrift = pixel.symbol_zellen(name, 1.0, 0)
        assert "".join(c for _x, c, _f, _b in schrift) == name.upper()
    for schluessel in [k for k, _n in startseite.RAD_APPS] + startseite.ERSCHAFFEN_APPS:
        assert schluessel in rad_wahl.OEFFNEN, schluessel


def test_erschaffen_rad_tickt_schnell_und_dreht():
    quelle = open(zt.__file__, encoding="utf-8").read()
    assert 'ERAD["pos"] != ERAD["sel"] or ERAD["schnell"]' in quelle


# ── Elektronik, Shop ──────────────────────────────────────────────────

def test_elektronik_legt_seinen_desk_an_und_esc_fuehrt_zurueck(u):
    assert rad_wahl.oeffnen(u, "e") is None
    D = u.DESK
    assert D["active"] and D["ebene"] == "canvas" and D["desk"] == "Elektronik" and D["direkt"]
    assert ("POST", "/api/desk") in u.aufrufe                  # beim ersten Mal angelegt
    u.desk.taste(ESC)
    assert not D["active"]                                     # zurück aufs Rad, nicht in die Auswahl
    u.aufrufe.clear()
    rad_wahl.oeffnen(u, "e")                                   # zweites Mal: nur laden
    assert D["active"] and ("POST", "/api/desk") not in u.aufrufe


def test_shop_platz_ohne_und_mit_shop(u):
    rad_wahl.oeffnen(u, "shop")
    assert u.bz.cmd_msg == "shop kommt gleich"
    geoeffnet = []
    u.shop = types.SimpleNamespace(oeffnen=lambda: geoeffnet.append(1))
    rad_wahl.oeffnen(u, "shop")
    assert geoeffnet == [1]


# ── Der Schmied ───────────────────────────────────────────────────────

def test_schmied_baut_eine_app_mit_bild_und_sie_steht_im_rad(u):
    w, W = u.werkstatt, u.W
    w.oeffnen()
    assert W["active"] and W["schritt"] == "start" and "Schmied" in w.satz()
    waehle(w, "neue app bauen")
    assert W["schritt"] == "name" and W["feld"] is not None
    tippe(w, "Geige")
    w.taste(ENTER)
    assert W["schritt"] == "icon" and W["neu"]["slug"] == "geige"
    waehle(w, "ein bild")
    assert W["schritt"] == "bild" and [t for t, _a in w.punkte()] == ["probe.png"]
    waehle(w, "probe.png")
    assert W["schritt"] == "vorlage"
    waehle(w, "Desk View")
    assert W["schritt"] == "agent" and "später" in w.satz()
    waehle(w, "weiter")
    assert W["schritt"] == "fertig" and "Geige" in w.satz()
    waehle(w, "ja, bauen")
    assert W["schritt"] == "gebaut" and "App-Rad" in w.satz()
    assert ("app:geige", "geige") in startseite.rad_apps()
    assert pixel.hat_symbol("geige")
    _z, schrift = pixel.symbol_zellen("geige", 1.0, 0)
    assert "".join(c for _x, c, _f, _b in schrift) == "GEIGE"
    w.draw(2, 0, 30, 120)                                      # zeichnen stürzt nicht ab


def test_rad_zeigt_die_neue_app_vorn_als_symbol(u):
    bauen(u.werkstatt)
    labels = [n for _k, n in startseite.rad_apps()]
    i = labels.index("geige")
    zeilen = startseite.rad_zeilen(labels, i, 70, 30, {"geige": 0.0})
    assert [z for z in zeilen if z[3] == "symbol:geige"]
    meta, rad = {"gsel": 0, "fokus": 0}, {"sel": i}
    assert startseite.meta_taste(meta, rad, {"sel": 0}, "enter", {"sel": 0}) == ("app", "app:geige")


def test_eigene_app_oeffnet_ihren_desk_ueber_die_adresse(u):
    bauen(u.werkstatt)
    u.W["active"] = False
    assert rad_wahl.oeffnen(u, "app:geige") is None
    assert u.DESK["active"] and u.DESK["desk"] == "Geige" and u.DESK["direkt"]
    assert u.router.kennt("zentrale://geige/")


def test_schmied_mit_zufallssymbol(u):
    u.werkstatt.zufall.seed(3)
    bauen(u.werkstatt, "Cello", "ein zufälliges")
    a = u.eigene.apps[0]
    assert a["icon"]["art"] == "motiv" and a["icon"]["motiv"] in pixel.FESTE_MOTIVE


def test_esc_geht_schritt_fuer_schritt_zurueck_und_zu(u):
    w, W = u.werkstatt, u.W
    w.oeffnen()
    waehle(w, "neue app bauen")
    tippe(w, "Geige")
    w.taste(ENTER)
    waehle(w, "ein bild")
    for erwartet in ("icon", "name", "start"):
        w.taste(ESC)
        assert W["schritt"] == erwartet
    assert W["neu"] == {}                                      # Halbes vergessen
    w.taste(ESC)
    assert not W["active"]
    assert not [a for a in u.aufrufe if a[0] == "POST" and a[1] == "/api/werkstatt/apps"]


def test_name_leer_oder_vergeben_bleibt_beim_namen(u):
    w, W = u.werkstatt, u.W
    bauen(w, "Geige")
    w.oeffnen()
    waehle(w, "neue app bauen")
    w.taste(ENTER)
    assert W["schritt"] == "name" and W["msg"] == "der name fehlt noch"
    tippe(w, "geige")
    w.taste(ENTER)
    assert W["schritt"] == "name" and "gibt es schon" in W["msg"]
    W["feld"].text, W["feld"].pos = "Post", 4
    w.taste(ENTER)
    assert W["schritt"] == "name" and "feste app" in W["msg"]


def test_kein_bild_im_input(u, tmp_path):
    (tmp_path / "nutzer" / "Input" / "probe.png").unlink()
    w = u.werkstatt
    w.oeffnen()
    waehle(w, "neue app bauen")
    tippe(w, "Geige")
    w.taste(ENTER)
    waehle(w, "ein bild")
    assert "kein Bild" in w.satz() and [t for t, _a in w.punkte()] == ["zurück"]
    w.taste(ENTER)
    assert u.W["schritt"] == "icon"


def test_vorlagen_ansehen_und_damit_bauen(u):
    w = u.werkstatt
    w.oeffnen()
    waehle(w, "vorlagen ansehen")
    assert w.punkte()[0][0].startswith("Desk View — ")
    w.taste(ENTER)
    assert u.W["schritt"] == "name" and u.W["neu"]["vorlage"] == "desk"


# ── Verwalten: Apps und Desks ─────────────────────────────────────────

def test_app_umbenennen_symbol_aendern_und_wegwerfen_mit_desk(u):
    w, W = u.werkstatt, u.W
    bauen(w, "Geige", "ein zufälliges")
    w.oeffnen()
    waehle(w, "deine apps")
    waehle(w, "Geige")
    assert W["schritt"] == "app"
    waehle(w, "umbenennen")
    W["feld"].text, W["feld"].pos = "Violine", 7
    w.taste(ENTER)
    assert W["schritt"] == "app" and W["ziel"]["name"] == "Violine" and W["ziel"]["slug"] == "geige"
    waehle(w, "symbol ändern")
    waehle(w, "ein bild")
    waehle(w, "probe.png")
    assert W["schritt"] == "app" and W["ziel"]["icon"]["art"] == "bild"
    waehle(w, "wegwerfen")
    assert W["schritt"] == "loeschen"
    waehle(w, "ja, wegwerfen")
    assert W["schritt"] == "loeschen_desk" and "Geige" in w.satz()
    waehle(w, "desk auch wegwerfen")
    assert W["schritt"] == "apps" and W["apps"] == []
    assert ("DELETE", "/api/werkstatt/apps/geige?desk=1") in u.aufrufe
    assert ("app:geige", "geige") not in startseite.rad_apps()
    assert not pixel.hat_symbol("geige") and not u.router.kennt("zentrale://geige/")


def test_app_wegwerfen_desk_bleibt(u):
    w = u.werkstatt
    bauen(w, "Geige", "ein zufälliges")
    w.oeffnen()
    waehle(w, "deine apps")
    waehle(w, "Geige")
    waehle(w, "wegwerfen")
    waehle(w, "nein, behalten")
    assert u.W["schritt"] == "app"
    waehle(w, "wegwerfen")
    waehle(w, "ja, wegwerfen")
    waehle(w, "desk behalten")
    w.oeffnen()
    waehle(w, "deine desks")
    assert [t for t, _a in w.punkte()] == ["Geige"]


def test_desks_umbenennen_oeffnen_wegwerfen(u):
    w, W = u.werkstatt, u.W
    rad_wahl.oeffnen(u, "e")
    u.desk.taste(ESC)
    w.oeffnen()
    waehle(w, "deine desks")
    waehle(w, "Elektronik")
    waehle(w, "umbenennen")
    W["feld"].text, W["feld"].pos = "Löten", 5
    w.taste(ENTER)
    assert W["schritt"] == "desk" and W["ziel"]["name"] == "Löten"
    waehle(w, "öffnen")
    assert u.DESK["active"] and u.DESK["desk"] == "Löten"
    u.desk.taste(ESC)                                          # zurück in die Werkstatt
    assert not u.DESK["active"] and W["active"] and W["schritt"] == "desk"
    waehle(w, "wegwerfen")
    waehle(w, "ja, wegwerfen")
    assert W["schritt"] == "desks" and W["desks"] == []


def test_esc_aus_dem_desk_einer_app_fuehrt_in_die_werkstatt(u):
    w, W = u.werkstatt, u.W
    bauen(w)
    waehle(w, "öffnen")
    assert u.DESK["active"] and u.DESK["desk"] == "Geige"
    u.desk.taste(ESC)
    assert not u.DESK["active"] and W["active"]


def test_symbole_aus_dem_shop_stehen_zur_wahl(u, monkeypatch):
    """Was im Shop geholt ist (schema.org-JSON-LD, core/shop.py), steht beim
    Symbol-Schritt mit; ohne Shop-Weg fehlt die Wahl einfach."""
    w = u.werkstatt
    w.oeffnen()
    waehle(w, "neue app bauen")
    tippe(w, "Geige")
    w.taste(ENTER)
    assert [t for t, _a in w.punkte()] == ["ein bild aus dem input-ordner", "ein zufälliges symbol"]
    echt = werkstatt_ansicht.api_call
    besitz = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "item": {
        "@type": "OwnershipInfo", "typeOfGood": {"name": "Karte", "category": "icons",
                                                 "additionalProperty": [{"name": "pixel_motiv", "value": "karte"}]}}}]}
    monkeypatch.setattr(werkstatt_ansicht, "api_call",
                        lambda p, *a, **k: besitz if p.startswith("/api/shop/besitz") else echt(p, *a, **k))
    w.taste(ESC)
    w.taste(ENTER)                                 # Name nochmal bestätigen → Symbol-Schritt
    waehle(w, "aus dem shop: Karte")
    assert u.W["neu"]["icon"] == {"motiv": "karte"} and u.W["schritt"] == "vorlage"
