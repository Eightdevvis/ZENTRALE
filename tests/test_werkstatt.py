"""
Werkstatt, Backend (2026-10-10, memory/hub/werkstatt.md): selbst gebaute
Apps als Ordner mit app.toml (dasselbe Hub-Manifest, gelesen mit tomllib)
+ icon.png aus einem Bild in ~/Zentrale/Input; Fund über core/apps.py;
Kurznamen (reserviert, vergeben); Desks umbenennen/löschen; Routen; Abgleich.
"""
import os
import tomllib

import pytest

import abgleich_auswahl
import apps
import bild_vorschau
import desk
import werkstatt


@pytest.fixture
def input_ordner(tmp_path, monkeypatch):
    """Eigener Nutzerordner mit einem erzeugten Testbild in Input/."""
    from PIL import Image
    monkeypatch.setenv("ZENTRALE_NUTZER_ORDNER", str(tmp_path / "nutzer"))
    ordner = tmp_path / "nutzer" / "Input"
    ordner.mkdir(parents=True)
    bild = Image.new("RGBA", (120, 80), (200, 30, 30, 255))
    for x in range(40, 80):
        for y in range(10, 70):
            bild.putpixel((x, y), (20, 200, 90, 255))
    for x in range(120):                       # oben ein durchsichtiger Streifen
        for y in range(0, 12):
            bild.putpixel((x, y), (0, 0, 0, 0))
    bild.save(ordner / "probe.png")
    (ordner / "kein_bild.png").write_bytes(b"das ist kein bild")
    return ordner


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def manifest_von(slug):
    with open(os.path.join(apps.eigene_ordner(), slug, "app.toml"), "rb") as f:
        return tomllib.load(f)


# ── Kurzname und Name ─────────────────────────────────────────────────

@pytest.mark.parametrize("name, slug", [
    ("Geige", "geige"), ("Geige & Bogen", "geige-bogen"), ("Ärger Öl Süß", "aerger-oel-suess"),
    ("123 Ziffern", "ziffern"), ("!!!", ""), ("x" * 40, "x" * 16)])
def test_slug_aus_name(name, slug):
    assert werkstatt.slug_aus(name) == slug


@pytest.mark.parametrize("name", ["post", "Elektronik", "werkstatt", "Shop", "desk", "tutor"])
def test_feste_namen_sind_reserviert(name):
    with pytest.raises(werkstatt.WerkstattFehler) as e:
        werkstatt.namen_pruefen(name)
    assert e.value.code == 409


@pytest.mark.parametrize("name", ["", "   ", "../x", "a/b", "!!!", "x" * 61])
def test_ungueltige_namen(name):
    with pytest.raises(werkstatt.WerkstattFehler) as e:
        werkstatt.namen_pruefen(name)
    assert e.value.code == 400


# ── Bauen: app.toml, Symbol, Desk ─────────────────────────────────────

def test_bauen_mit_bild_schreibt_manifest_icon_und_desk(input_ordner):
    a = werkstatt.anlegen("Geige", {"bild": "probe.png"})
    assert a["slug"] == "geige" and a["adresse"] == "zentrale://geige/"
    assert a["vorlage"] == "desk" and a["desk"] == "Geige"
    m = manifest_von("geige")                  # tomllib liest, was geschrieben wurde
    assert m["name"] == "Geige" and m["vorlage"] == "desk" and m["icon"] == "icon.png"
    assert m["version"] == werkstatt.VERSION and "start" not in m
    assert desk.laden("Geige")["elemente"] == []
    raster = a["icon"]["raster"]
    assert a["icon"]["art"] == "bild" and len(raster) == bild_vorschau.ICON_SEITE
    assert all(len(z) == bild_vorschau.ICON_SEITE for z in raster)
    farben = {f for z in raster for f in z}
    assert None in farben                      # durchsichtiger Rand bleibt durchsichtig
    assert 2 <= len(farben - {None}) <= bild_vorschau.ICON_FARBEN


def test_manifest_hin_und_zurueck_mit_sonderzeichen(tmp_path):
    m = {"name": 'Ä "zitat" \\ back\nzeile', "version": "0.1.0", "vorlage": "desk",
         "icon_motiv": "post", "desk": "x"}
    text = werkstatt.manifest_text(m)
    assert tomllib.loads(text) == m


def test_bauen_mit_motiv_und_vorhandenem_desk(input_ordner):
    desk.anlegen("Cello")
    desk.speichern("Cello", [{"id": "a", "art": "notiz", "x": 0, "y": 0, "w": 10, "h": 4,
                             "text": "bleibt"}])
    a = werkstatt.anlegen("Cello", {"motiv": "klavier"})
    assert a["icon"] == {"art": "motiv", "motiv": "klavier"}
    assert len(desk.laden("Cello")["elemente"]) == 1   # übernommen, nicht überschrieben
    assert manifest_von("cello")["icon_motiv"] == "klavier"


def test_doppelter_name_wird_abgelehnt(input_ordner):
    werkstatt.anlegen("Geige", {"motiv": "post"})
    for name in ("Geige", "geige", "GEIGE."):
        with pytest.raises(werkstatt.WerkstattFehler) as e:
            werkstatt.anlegen(name, {"motiv": "post"})
        assert e.value.code == 409


@pytest.mark.parametrize("icon, code", [
    ({"bild": "fehlt.png"}, 404), ({"bild": "kein_bild.png"}, 400),
    ({"bild": "../../etc/passwd"}, 404), ({"motiv": "Böse Dinge"}, 400), ({}, 400), (None, 400)])
def test_falsches_symbol_laesst_nichts_halbes_liegen(input_ordner, icon, code):
    with pytest.raises(werkstatt.WerkstattFehler) as e:
        werkstatt.anlegen("Geige", icon)
    assert e.value.code == code
    assert werkstatt.liste() == [] and not os.path.exists(os.path.join(apps.eigene_ordner(), "geige"))


def test_unbekannte_vorlage():
    with pytest.raises(werkstatt.WerkstattFehler):
        werkstatt.anlegen("Geige", {"motiv": "post"}, vorlage="spiel")


# ── Fund über core/apps.py ────────────────────────────────────────────

def test_apps_findet_die_eigenen(input_ordner):
    werkstatt.anlegen("Zwei", {"motiv": "post"})
    werkstatt.anlegen("Eins", {"motiv": "graph"})
    os.makedirs(os.path.join(apps.eigene_ordner(), "ohne-manifest"))
    assert apps.eigene_namen() == ["eins", "zwei"]
    assert [m["_slug"] for m in apps.installiert() if "_slug" in m] == ["eins", "zwei"]
    assert apps.manifest("eins")["vorlage"] == "desk"
    assert all("_slug" not in m for m in apps.abonnenten("anwesenheit"))   # keine Rechte
    assert [a["slug"] for a in werkstatt.liste()] == ["eins", "zwei"]


def test_kaputtes_manifest_bricht_die_liste_nicht(input_ordner):
    werkstatt.anlegen("Gut", {"motiv": "post"})
    os.makedirs(os.path.join(apps.eigene_ordner(), "kaputt"))
    with open(os.path.join(apps.eigene_ordner(), "kaputt", "app.toml"), "w") as f:
        f.write("name = \n")
    assert [a["slug"] for a in werkstatt.liste()] == ["gut"]


# ── Ändern, löschen ───────────────────────────────────────────────────

def test_umbenennen_behaelt_kurzname_und_adresse(input_ordner):
    werkstatt.anlegen("Geige", {"motiv": "post"})
    a = werkstatt.aendern("geige", name="Violine")
    assert a["name"] == "Violine" and a["slug"] == "geige" and a["adresse"] == "zentrale://geige/"
    werkstatt.anlegen("Cello", {"motiv": "post"})
    with pytest.raises(werkstatt.WerkstattFehler):
        werkstatt.aendern("cello", name="violine")


def test_symbol_wechseln_bild_und_motiv(input_ordner):
    werkstatt.anlegen("Geige", {"motiv": "post"})
    assert werkstatt.aendern("geige", icon={"bild": "probe.png"})["icon"]["art"] == "bild"
    assert os.path.exists(os.path.join(apps.eigene_ordner(), "geige", "icon.png"))
    a = werkstatt.aendern("geige", icon={"motiv": "karte"})
    assert a["icon"] == {"art": "motiv", "motiv": "karte"}
    assert not os.path.exists(os.path.join(apps.eigene_ordner(), "geige", "icon.png"))


@pytest.mark.parametrize("desk_mit", [False, True])
def test_loeschen_mit_und_ohne_desk(input_ordner, desk_mit):
    werkstatt.anlegen("Geige", {"motiv": "post"})
    werkstatt.loeschen("geige", desk_mit)
    assert werkstatt.liste() == []
    assert ("Geige" in [d["name"] for d in desk.liste()]) is not desk_mit
    with pytest.raises(werkstatt.WerkstattFehler) as e:
        werkstatt.loeschen("geige")
    assert e.value.code == 404


def test_desk_umbenennen_zieht_apps_mit_und_loeschen_schuetzt_sie(input_ordner):
    werkstatt.anlegen("Geige", {"motiv": "post"})
    assert werkstatt.desk_umbenennen("Geige", "Violine") == {"name": "Violine"}
    assert werkstatt.laden("geige")["desk"] == "Violine"
    with pytest.raises(werkstatt.WerkstattFehler) as e:
        werkstatt.desk_loeschen("Violine")
    assert e.value.code == 409
    desk.anlegen("Frei")
    with pytest.raises(werkstatt.WerkstattFehler) as e:
        werkstatt.desk_umbenennen("Frei", "Violine")
    assert e.value.code == 409
    werkstatt.desk_loeschen("Frei")
    assert "Frei" not in [d["name"] for d in desk.liste()]


# ── Routen ────────────────────────────────────────────────────────────

def test_routen_ganzer_weg(client, input_ordner):
    assert client.get("/api/werkstatt/apps").get_json() == {"apps": []}
    assert client.get("/api/werkstatt/vorlagen").get_json()["vorlagen"][0]["id"] == "desk"
    assert {b["name"] for b in client.get("/api/werkstatt/bilder").get_json()["bilder"]} \
        == {"kein_bild.png", "probe.png"}
    r = client.post("/api/werkstatt/name", json={"name": "Geige"})
    assert r.status_code == 200 and r.get_json() == {"name": "Geige", "slug": "geige"}
    r = client.post("/api/werkstatt/apps", json={"name": "Geige", "icon": {"bild": "probe.png"}})
    assert r.status_code == 201 and r.get_json()["slug"] == "geige"
    assert client.post("/api/werkstatt/name", json={"name": "geige"}).status_code == 409
    assert client.post("/api/werkstatt/apps", json={"name": "Geige", "icon": {"motiv": "post"}}).status_code == 409
    r = client.patch("/api/werkstatt/apps/geige", json={"name": "Violine"})
    assert r.get_json()["name"] == "Violine"
    assert client.patch("/api/desk/Geige", json={"name": "Bogen"}).get_json() == {"name": "Bogen"}
    assert client.delete("/api/desk/Bogen").status_code == 409
    assert client.delete("/api/werkstatt/apps/geige?desk=1").get_json() == {"ok": True}
    assert client.get("/api/werkstatt/apps").get_json() == {"apps": []}
    assert client.get("/api/desk").get_json()["desks"] == []
    assert client.delete("/api/werkstatt/apps/geige").status_code == 404
    assert client.delete("/api/werkstatt/apps/..%2Fx").status_code == 404


# ── Abgleich ──────────────────────────────────────────────────────────

def test_apps_ordner_wird_abgeglichen():
    for rel in ("data/apps/geige/app.toml", "data/apps/geige/icon.png"):
        assert abgleich_auswahl.passt(rel, abgleich_auswahl.SICHERN)
        assert abgleich_auswahl.passt(rel, abgleich_auswahl.ABGLEICH)


def test_apps_ordner_standard_liegt_in_data(monkeypatch):
    monkeypatch.delenv("ZENTRALE_APPS_ORDNER")
    assert apps.eigene_ordner().endswith(os.path.join("data", "apps"))
