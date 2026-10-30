"""The type registry of the building kit (core/port_types.py, contracts/ports/1,
memory/hub/port_types.md, build step 9): the registry and every schema are
valid 2020-12, every built-in app's ports validate, the manifest reader takes
new and old keys, SemVer ranges, and the vector file is current."""
import json
import os

from jsonschema import Draft202012Validator

import abgleich_apps
import app_ports
import eingebaute_apps
import knoten
import port_types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_schema_and_registry_are_valid():
    Draft202012Validator.check_schema(port_types.schema())
    with open(port_types.REGISTRY, encoding="utf-8") as f:
        assert port_types.check(json.load(f), "registry") == []


def test_every_builtin_manifest_validates_and_has_the_data_socket():
    for name, decl in eingebaute_apps.PORTS.items():
        assert port_types.check(decl, "manifestPorts") == [], name
        for p in decl.get("needs", []) + decl.get("offers", []):
            assert port_types.entry(port_types.need(p)["type"]) is not None, (name, p)
    for name in abgleich_apps.tabelle():
        ids = [n["id"] for n in app_ports.of_app(name)["needs"]]
        assert "data" in ids, f"{name} has data but no `data` socket — declare it in PORTS"
    assert app_ports.of_app("adapter")["needs"][0]["occurrences"] == [1, 1]   # pflicht
    assert port_types.check(eingebaute_apps.INSTANCE_PORTS["kalender"], "manifestPorts") == []
    assert port_types.check(eingebaute_apps.NODE_PORTS, "manifestPorts") == []


def test_manifest_new_keys_and_old_keys():
    m = {"name": "x", "needs": ["model@^1", {"type": "files", "access": "read"}],
         "offers": ["tile:list"],
         "rechte": ["modell", "ereignis:anwesenheit", "kalender:lesen", "mikro", "unbekannt"],
         "liefert": ["kachel:wetter"],
         "daten": {"muster": ["data/x.json"], "abgleichen": True}}
    p = app_ports.of_manifest(m)
    needs = {n["id"]: n for n in p["needs"]}
    assert needs["model"]["range"] == "^1" and not needs["model"].get("legacy")   # new key wins
    assert needs["files"]["access"] == "read"
    assert needs["data"]["type"] == "sync" and needs["data"]["occurrences"] == [0, 1]
    assert needs["event.anwesenheit"]["legacy"] and needs["event.anwesenheit"]["type"] == "event:anwesenheit"
    assert needs["read.kalender"]["type"] == "read:kalender" and needs["mic"]["legacy"]
    assert "unbekannt" not in str(p)
    assert {o["type"] for o in p["offers"]} == {"tile:list", "tile:wetter"}


def test_a_qualifier_only_where_the_family_takes_one():
    assert port_types.entry("event:presence") is not None
    assert port_types.entry("event") is None
    assert port_types.entry("sync:x") is None
    assert port_types.entry("teleport") is None


def test_semver_ranges():
    for version, rng, ok in [
            ("1.4.2", "^1", True), ("2.0.0", "^1", False), ("1.1.0", "^1.2", False),
            ("1.2.9", "^1.2", True), ("0.2.5", "^0.2", True), ("0.3.0", "^0.2", False),
            ("1.2.9", "~1.2", True), ("1.3.0", "~1.2", False), ("1.2.3", "1.2.3", True),
            ("1.2.4", "1.2.3", False), ("9.9.9", "*", True), ("x", "^1", False)]:
        assert port_types.satisfies(version, rng) is ok, (version, rng)


def test_node_description_carries_type_versions_and_apply_agent():
    d = knoten.beschreibung(sys_wurzel="/nonexistent", umgebung={})
    assert d["types"] == port_types.supported() and d["apply_agent"] == port_types.APPLY_AGENT


def test_vector_file_is_current(monkeypatch):
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    import importlib.util
    spec = importlib.util.spec_from_file_location("port_vectors", os.path.join(ROOT, "scripts", "port_vectors.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with open(mod.TARGET, encoding="utf-8") as f:
        assert f.read() == mod.text(), "run scripts/port_vectors.py"


def test_item_vectors_hold():
    with open(os.path.join(port_types.FOLDER, "port_vectors.json"), encoding="utf-8") as f:
        v = json.load(f)
    for i in v["items"]:
        assert (port_types.check(i["item"], i["kind"]) == []) is i["valid"], i
    assert v["manifests"] == json.loads(json.dumps(eingebaute_apps.PORTS))
