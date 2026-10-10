"""
Die HTTP-Schnittstelle des Hubs als OpenAPI 3.1 (openapi.yaml, 2026-10-10,
memory/system/hub_bauplan.md „Standards statt Eigenformat"):
(a) jede Flask-Route unter /api/kachel*, /api/kacheln, /api/desk* steht in
der Datei und umgekehrt (kein Auseinanderlaufen); (b) die Datei selbst
taugt: Aufbau, jeder $ref löst sich auf, jedes Schema ist gültiges JSON
Schema 2020-12; (c) echte Antworten passen zu ihren Schemas; (d) jedes
`parameter` im Katalog ist ein gültiges JSON Schema, seine Vorgaben passen.
`openapi-spec-validator` ist nicht installiert — darum hier mit
`jsonschema` und dem Meta-Schema.
"""
import os
import re

import pytest
import yaml
from jsonschema import Draft202012Validator

import farbrollen
import graphs
import kacheln
import lists

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRAEFIXE = ("/api/kachel", "/api/desk")          # /api/kachel* deckt /api/kacheln mit
METHODEN = {"get", "put", "post", "delete", "patch"}


@pytest.fixture(scope="module")
def spec():
    with open(os.path.join(ROOT, "openapi.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


def passt(spec, name, wert):
    """Wert gegen #/components/schemas/<name> (mit den $refs der Datei)."""
    schema = {"components": spec["components"], "$ref": "#/components/schemas/%s" % name}
    v = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    fehler = [e.message for e in v.iter_errors(wert)]
    assert not fehler, (name, fehler, wert)


# ── (a) Routen ↔ Datei ───────────────────────────────────────────────

def _routen():
    from ui.app import app
    raus = set()
    for r in app.url_map.iter_rules():
        if not r.rule.startswith(PRAEFIXE):
            continue
        pfad = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", r.rule)
        raus |= {(pfad, m.lower()) for m in r.methods if m.lower() in METHODEN}
    return raus


def test_jede_route_steht_in_der_datei_und_umgekehrt(spec):
    beschrieben = {(p, m) for p, ops in spec["paths"].items() for m in ops if m in METHODEN}
    routen = _routen()
    assert routen, "keine Routen gefunden — Präfixe falsch?"
    assert routen - beschrieben == set(), "Route ohne Beschreibung in openapi.yaml"
    assert beschrieben - routen == set(), "openapi.yaml beschreibt eine Route, die es nicht gibt"


# ── (b) Die Datei taugt ──────────────────────────────────────────────

def _refs(x):
    if isinstance(x, dict):
        if isinstance(x.get("$ref"), str):
            yield x["$ref"]
        for v in x.values():
            yield from _refs(v)
    elif isinstance(x, list):
        for v in x:
            yield from _refs(v)


def _zeiger(spec, ref):
    assert ref.startswith("#/"), "nur Verweise in der Datei: %s" % ref
    ziel = spec
    for teil in ref[2:].split("/"):
        teil = teil.replace("~1", "/").replace("~0", "~")
        assert isinstance(ziel, dict) and teil in ziel, "$ref löst sich nicht: %s" % ref
        ziel = ziel[teil]
    return ziel


def test_datei_ist_openapi_3_1_mit_aufgeloesten_verweisen(spec):
    assert re.fullmatch(r"3\.1\.\d+", spec["openapi"])
    assert spec["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"
    assert spec["info"]["title"] and spec["info"]["version"]
    assert spec["servers"][0]["url"].startswith("http://localhost")
    tags = {t["name"] for t in spec["tags"]}
    ids = []
    for pfad, ops in spec["paths"].items():
        assert pfad.startswith("/")
        platzhalter = set(re.findall(r"{([^}]+)}", pfad))
        gemeinsam = {p["name"] for p in ops.get("parameters", []) if p["in"] == "path"}
        for m, op in ops.items():
            if m not in METHODEN:
                continue
            ids.append(op["operationId"])
            assert set(op["tags"]) <= tags and op["responses"]
            for code, antwort in op["responses"].items():
                assert re.fullmatch(r"[1-5]\d\d", code)
                antwort = _zeiger(spec, antwort["$ref"]) if "$ref" in antwort else antwort
                assert antwort["description"]
            eigene = {p["name"] for p in op.get("parameters", []) if p["in"] == "path"}
            assert platzhalter == gemeinsam | eigene, pfad
    assert len(ids) == len(set(ids)), "operationId doppelt"
    for ref in _refs(spec):
        _zeiger(spec, ref)


def test_jedes_schema_der_datei_ist_gueltiges_json_schema(spec):
    for name, schema in spec["components"]["schemas"].items():
        Draft202012Validator.check_schema(schema)
    for pfad, ops in spec["paths"].items():
        for m, op in ops.items():
            if m in METHODEN:
                for inhalt in (op.get("requestBody") or {}).get("content", {}).values():
                    Draft202012Validator.check_schema(inhalt["schema"])


def test_farbrollen_der_datei_sind_das_woerterbuch(spec):
    assert spec["components"]["schemas"]["Farbrolle"]["enum"] == list(farbrollen.ROLLEN)


# ── (c) Echte Antworten passen ───────────────────────────────────────

@pytest.fixture
def liste_und_graph():
    lid = lists.create_list("Einkauf")["id"]
    lists.add_item(lid, "Milch")
    gid = graphs.create_graph("Gewicht", "number", unit="kg")["id"]
    return lid, gid


def test_kachel_antworten_passen(spec, client, liste_und_graph):
    lid, gid = liste_und_graph
    r = client.get("/api/kacheln")
    assert r.status_code == 200 and {e["app"] for e in r.get_json()} == {"kalender", "fokus", "graph"}
    for e in r.get_json():
        passt(spec, "KatalogEintrag", e)
    adressen = ["zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7",
                "zentrale://fokus/liste?erledigte=false&liste=%s&tiefe=3" % lid,
                "zentrale://graph/verlauf?graph=%s&tage=14" % gid]
    for adresse in adressen:
        r = client.post("/api/kachel", json={"adresse": adresse, "w": 60, "h": 8})
        assert r.status_code == 200 and "zeilen" in r.get_json()
        passt(spec, "KachelAntwort", r.get_json())
        passt(spec, "KachelInhalt", r.get_json())
        stand = r.get_json()["stand"]
        r = client.post("/api/kachel", json={"adresse": adresse, "w": 60, "h": 8, "stand": stand})
        passt(spec, "KachelUnveraendert", r.get_json())
        r = client.post("/api/kachel", json={"adresse": adresse, "w": 0, "h": 0})
        passt(spec, "KachelZuKlein", r.get_json())
        r = client.post("/api/kachel/aktion", json={"adresse": adresse, "aktion": "oeffnen"})
        assert r.status_code == 200
        passt(spec, "AktionAntwort", r.get_json())


@pytest.mark.parametrize("anfrage, status", [
    ({"adresse": "zentrale://kalender/ausschnitt?bis=2026-11-30&modus=fest&von=2026-10-01",
      "w": 0, "h": 0}, 400),
    ({"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_weg&tiefe=3", "w": 30, "h": 9}, 404),
    ({"adresse": "zentrale://gibtsnicht/x", "w": 9, "h": 9}, 503),
    ({"w": 1}, 400),
])
def test_kachel_fehler_passen(spec, client, anfrage, status):
    r = client.post("/api/kachel", json=anfrage)
    assert r.status_code == status
    passt(spec, "KachelFehler", r.get_json())
    beschrieben = spec["paths"]["/api/kachel"]["post"]["responses"]
    assert str(status) in beschrieben


def test_desk_antworten_passen(spec, client):
    r = client.post("/api/desk", json={"name": "probe"})
    assert r.status_code == 201
    passt(spec, "Desk", r.get_json())
    stand = r.get_json()["stand"]
    body = {"elemente": [{"id": "a", "art": "notiz", "x": 0, "y": 0, "w": 20, "h": 5, "text": "hallo"},
                         {"id": "k", "art": "kachel", "x": 30, "y": 0, "w": 20, "h": 8,
                          "kachel": {"v": 2, "adresse":
                                     "zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7"}}],
            "verbindungen": [{"id": "v1", "von": "a", "nach": "k"}], "stand": stand}
    passt(spec, "DeskSpeichern", body)
    r = client.put("/api/desk/probe", json=body)
    assert r.status_code == 200
    passt(spec, "Desk", r.get_json())
    passt(spec, "Desk", client.get("/api/desk/probe").get_json())
    passt(spec, "DeskListe", client.get("/api/desk").get_json())
    r = client.put("/api/desk/probe", json=dict(body, stand="alt"))
    assert r.status_code == 409
    passt(spec, "DeskFehler", r.get_json())
    r = client.get("/api/desk/gibtsnicht")
    assert r.status_code == 404
    passt(spec, "DeskFehler", r.get_json())


def test_bild_vorschau_ohne_bild_passt(spec, client):
    r = client.post("/api/desk-bild/vorschau", json={"datei": "bilder/fehlt.png", "w": 10, "h": 4})
    assert r.status_code == 200 and r.get_json()["status"] == "weg"
    passt(spec, "BildVorschau", r.get_json())


# ── (d) parameter im Katalog ─────────────────────────────────────────

def test_jedes_parameter_ist_json_schema_und_seine_vorgaben_passen(liste_und_graph):
    katalog = kacheln.katalog()
    assert katalog
    for e in katalog:
        s = e["parameter"]
        Draft202012Validator.check_schema(s)
        assert s["type"] == "object" and s["additionalProperties"] is False
        for name, prop in s["properties"].items():
            assert prop["title"], (e["app"], name)
            if "default" in prop:
                Draft202012Validator(prop, format_checker=Draft202012Validator.FORMAT_CHECKER) \
                    .validate(prop["default"])
        # Vorgaben (sonst die erste Wahl) ergeben eine gültige Anfrage —
        # bei if/then nur die Felder, die bei diesen Werten gelten
        werte = {n: p.get("default", (p.get("oneOf") or [{}])[0].get("const"))
                 for n, p in s["properties"].items()}
        for regel in s.get("allOf", []):
            wenn = {n: c["const"] for n, c in regel["if"]["properties"].items()}
            if all(werte.get(n) == c for n, c in wenn.items()):
                for n, verboten in regel["then"].get("properties", {}).items():
                    if verboten is False:
                        werte.pop(n, None)
        werte = {n: w for n, w in werte.items() if w is not None}
        Draft202012Validator(s, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(werte)
