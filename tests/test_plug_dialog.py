"""The plug dialog at install and the Run-gate follow-ups (building kit step 11;
core/plugs.py, core/plug_store.py, core/generations.keep; memory/hub/port_types.md).

  - installing an app with `needs = ["model"]` lists the providers here;
    refusing leaves the app installed and the port `off`; confirming plugs it
    in through the gate; a required socket left unplugged withdraws the install
  - the same rules over HTTP (the TUI store) and at the terminal (`zentrale apps`)
  - `zentrale adapter calendar` re-plugs through the gate
  - guard: nothing outside core/wires.py writes the owners of the wires
  - the apply agent on the keeper: reconciles the node's own wires, adopts
    synced instance wires, rolls back on a failed health check
  - the node's own wires go into its description; others read them back
"""
import ast
import io
import json
import os
import subprocess

import pytest

import abgleich_apps
import ai_config
import app_installation
import generations
import kalender_einstellung as ke
import plug_store
import plugs
import shop
import wires
from zentrale_cli import befehle, haupt
from zentrale_cli.ausgabe import Terminal

NODE = "testnode"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDRESS = "zentrale://shop/apps/sparbuch"
MODEL = "zentrale://adapter/port/model"

MANIFEST = '''name = "sparbuch"
version = "0.1.0"
titel = "Sparbuch"
start = "python -m sparbuch"
adresse = "http://127.0.0.1:5999"
ansichten = ["terminal"]
needs = [{needs}]
[ansicht.terminal]
start = "python -m sparbuch tui"
'''


@pytest.fixture
def settings(_test_ordner, monkeypatch):
    path = _test_ordner / "ai_config.json"
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(path))
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setenv("ZENTRALE_NODE_NAME", NODE)
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    return path


def _git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                   check=True, capture_output=True)


def _store_app(tmp_path, monkeypatch, needs):
    repo = tmp_path / "source" / "sparbuch"
    repo.mkdir(parents=True)
    (repo / "app.toml").write_text(MANIFEST.replace("{needs}", needs), encoding="utf-8")
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("add", ".", cwd=repo)
    _git("commit", "-qm", "app", cwd=repo)
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        catalog = json.load(f)
    catalog["itemListElement"].append({"@type": "ListItem", "position": 99, "item": {
        "@type": "SoftwareApplication", "@id": ADDRESS, "identifier": "sparbuch",
        "name": "Sparbuch", "description": "test", "category": "apps", "keywords": ["geld"],
        "downloadUrl": repo.as_uri(),
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
        "additionalProperty": [{"@type": "PropertyValue", "name": "app_name", "value": "sparbuch"}]}})
    k = tmp_path / "catalog.jsonld"
    k.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("ZENTRALE_SHOP_KATALOG", str(k))


@pytest.fixture
def model_app(settings, tmp_path, monkeypatch):
    """A store app that needs a model (optional, the registry default 0..1)."""
    _store_app(tmp_path, monkeypatch, '"model"')
    app_installation.installieren(ADDRESS, ["terminal"])


@pytest.fixture
def required_app(settings, tmp_path, monkeypatch):
    _store_app(tmp_path, monkeypatch, '{type = "model", occurrences = [1, 1]}')
    app_installation.installieren(ADDRESS, ["terminal"])


class Play(Terminal):
    def __init__(self, *answers, interactive=True):
        super().__init__(aus=io.StringIO(), ein=io.StringIO("".join(a + "\n" for a in answers)))
        self.interaktiv = interactive

    @property
    def text(self):
        return self.aus.getvalue()


def _plug_wire():
    return next((w for w in wires.sketch(NODE)["wires"] if w["to"] == "zentrale://sparbuch/port/model"), None)


# ── Step 11 acceptance ─────────────────────────────────────────────────────

def test_installing_an_app_that_needs_a_model_lists_the_providers(model_app):
    socks = plugs.sockets("sparbuch")
    assert [(s["need"], s["type"], s["min"]) for s in socks] == [("model", "model", 0)]
    assert [p["port"] for p in socks[0]["providers"]] == [MODEL]
    assert socks[0]["wire"] is None


def test_refusing_leaves_the_app_installed_and_the_port_off(model_app):
    r = app_installation.plug("sparbuch", {"model": None})
    assert r["ok"] and not r["withdrawn"] and r["unmet"] == []
    assert app_installation.eintrag("sparbuch") is not None           # still installed
    w = _plug_wire()
    assert w["state"] == "off" and w["owner"] == "app:sparbuch" and w["from"] == MODEL
    assert r["diff"] == ["+ Sparbuch model → Adapter model on sparbuch (off)"]
    # stored with the instance, in the synced adapter folder
    assert [x["id"] for x in plug_store.read(plug_store.instance_file("sparbuch"))] == ["plug/sparbuch/model"]
    assert generations.Store().current_hash(NODE) == r["generation"]


def test_confirming_plugs_it_in_and_the_round_trip_writes_nothing(model_app):
    r = app_installation.plug("sparbuch", {"model": MODEL})
    assert r["ok"] and _plug_wire()["state"] == "live"
    path = plug_store.instance_file("sparbuch")
    before = open(path, "rb").read()
    assert wires.write(wires.all_wires(NODE)) == []
    assert open(path, "rb").read() == before
    again = app_installation.plug("sparbuch", {"model": None})        # re-plug later: off
    assert again["diff"] == ["~ Sparbuch model → Adapter model on sparbuch: live → off"]


def test_a_provider_that_does_not_fit_is_refused_at_its_socket(model_app):
    r = app_installation.plug("sparbuch", {"model": "zentrale://cloud/port/sync"})
    assert not r["ok"] and r["errors"][0]["need"] == "model" and _plug_wire() is None


def test_a_required_socket_left_off_withdraws_the_install(required_app):
    assert plugs.unmet("sparbuch") == ["model"]
    r = app_installation.plug("sparbuch", {"model": None})
    assert not r["ok"] and r["withdrawn"] and r["unmet"] == ["model"]
    assert r["errors"][0]["code"] == "unmet-requirement" and r["errors"][0]["need"] == "model"
    assert app_installation.eintrag("sparbuch") is None              # the install does not count
    assert _plug_wire() is None
    # the rest of the node compiles again (nothing hangs on the withdrawn app)
    assert generations.in_effect(NODE)[1] == []


def test_a_required_socket_plugged_in_counts(required_app):
    r = app_installation.plug("sparbuch", {"model": MODEL})
    assert r["ok"] and not r["withdrawn"] and app_installation.eintrag("sparbuch") is not None
    assert r["diff"] == ["+ Sparbuch model → Adapter model on sparbuch"]


# ── The same rules over HTTP (the TUI store) and at the terminal ───────────

def test_routes(model_app):
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    r = c.get("/api/apps/sparbuch/plugs")
    assert r.status_code == 200 and r.json["sockets"][0]["providers"][0]["port"] == MODEL
    assert c.get("/api/apps/nope/plugs").status_code == 404
    assert c.post("/api/apps/sparbuch/plugs", json={"choices": [1]}).status_code == 400
    r = c.post("/api/apps/sparbuch/plugs", json={"choices": {"model": MODEL}})
    assert r.status_code == 200 and r.json["ok"] and _plug_wire()["state"] == "live"


def _api(client):
    import urllib.error

    def api(path, method="GET", body=None, timeout=3.0):
        r = client.open(path, method=method, json=body)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(path, r.status_code, "x", {}, io.BytesIO(r.data))
        return r.get_json()
    return api


def test_tui_store_asks_through_the_same_routes(settings, tmp_path, monkeypatch):
    """The TUI store: install → the plug dialog (←→ provider, enter plugs in);
    a required socket left off (esc) → the hub withdraws the install."""
    import curses
    import types
    import yaml
    from jsonschema import Draft202012Validator
    from tui.ansichten import shop as tui_shop
    from ui.app import app
    _store_app(tmp_path, monkeypatch, '{type = "model", occurrences = [1, 1]}')
    app.config.update(TESTING=True)
    monkeypatch.setattr(tui_shop, "api_call", _api(app.test_client()))
    lines = []
    z = types.SimpleNamespace(C={k: 0 for k in ("faint", "dim", "ink", "bright", "acc", "warn")},
                              addclip=lambda y, x, text, w, a=0: lines.append(str(text)),
                              draw_box=lambda *a, **k: None)
    v = tui_shop.Shop(z)
    told = []
    v.nach_installieren = lambda: told.append(1)
    v.SHOP["wahl"] = {"adresse": ADDRESS, "titel": "Sparbuch", "an": ["terminal"]}
    v.installieren()
    assert v.ansicht() == "plug" and told == []
    v._draw_plug(0, 0, 10, 100)
    assert any("Adapter model" in x for x in lines) and any("required" in x for x in lines)
    v.taste(curses.KEY_RIGHT)                    # → leave it off
    v.taste(curses.KEY_LEFT)                     # ← back to the adapter
    v.taste(10)
    assert v.SHOP["plug"] is None and told == [1] and v.SHOP["msg"] == "plugged in ✓"
    assert _plug_wire()["state"] == "live"
    # esc on a fresh install of a required socket: withdrawn, said so
    app_installation.withdraw("sparbuch")
    v.SHOP["wahl"] = {"adresse": ADDRESS, "titel": "Sparbuch", "an": ["terminal"]}
    plug_store.write(plug_store.instance_file("sparbuch"), [])
    v.installieren()
    v.taste(27)
    assert "is not installed" in v.SHOP["msg"] and app_installation.eintrag("sparbuch") is None
    # the answers fit openapi.yaml
    with open(os.path.join(ROOT, "openapi.yaml"), encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    schema = dict(spec["paths"]["/api/apps/{name}/plugs"]["get"]["responses"]["200"]["content"]
                  ["application/json"]["schema"], components=spec["components"])
    app_installation.installieren(ADDRESS, ["terminal"])
    got = app.test_client().get("/api/apps/sparbuch/plugs").get_json()
    assert [e.message for e in Draft202012Validator(schema).iter_errors(got)] == []
    plug = spec["components"]["responses"]["PlugResult"]["content"]["application/json"]["schema"]
    r = app.test_client().post("/api/apps/sparbuch/plugs", json={"choices": {"model": MODEL}})
    assert [e.message for e in Draft202012Validator(dict(plug, components=spec["components"]))
            .iter_errors(r.get_json())] == []


def test_cli_install_asks_and_plugs(settings, tmp_path, monkeypatch):
    _store_app(tmp_path, monkeypatch, '"model"')
    term = Play("1")                                  # 1 = the adapter's model
    assert haupt.main(["apps", "install", "sparbuch"], term=term) == 0, term.text
    assert "Sparbuch is installed." in term.text and "Adapter model" in term.text
    assert _plug_wire()["state"] == "live"
    term = Play("2")                                  # 2 = leave it off
    assert haupt.main(["apps", "plug", "sparbuch"], term=term) == 0, term.text
    assert _plug_wire()["state"] == "off" and "live → off" in term.text


def test_cli_without_a_terminal_leaves_everything_off(settings, tmp_path, monkeypatch):
    _store_app(tmp_path, monkeypatch, '{type = "model", occurrences = [1, 1]}')
    term = Play(interactive=False)
    assert haupt.main(["apps", "install", "sparbuch"], term=term) == 1
    assert "is not installed: model must be plugged in" in term.text
    assert app_installation.eintrag("sparbuch") is None


# ── Follow-up 2: the calendar source through the gate, and the guard ──────

def test_adapter_calendar_goes_through_the_gate(settings, tmp_path, monkeypatch):
    root = tmp_path / "hub"
    monkeypatch.setattr(befehle, "WURZEL", str(root))       # never the checkout's data/
    monkeypatch.setenv("ZENTRALE_ADAPTER_ORDNER", str(root / "data" / "adapter"))
    term = Play()
    assert befehle.adapter_kalender(term, ["lokal"]) == 0, term.text
    assert ke.quelle() == "lokal" and "google → lokal" in term.text
    store = generations.Store()
    gen = store.current(NODE)
    cal = [w for w in gen["wires"] if w["type"] == "calendar-source"]
    assert cal[0]["from"].endswith("/port/" + wires.LOCAL_PORT)
    term = Play()
    assert befehle.adapter_kalender(term, ["lokal"]) == 0
    assert "already lokal" in term.text and store.current_hash(NODE) == gen["hash"]


# The functions that write the stored truth of a wire, and the only files
# that may call them (besides the module that defines each one).
OWNER_WRITERS = {
    "abgleich_apps": {"setzen", "replace"},
    "kalender_einstellung": {"schreiben", "roh_zurueck"},
    "adapter_ablauf": {"kalender_quelle_setzen"},
    "plug_store": {"write"},
}
ALLOWED = {os.path.join("core", "wires.py"), os.path.join("core", "adapter_ablauf.py")}
AREAS = ("core", "ui", "tui", "zentrale_cli", "scripts", "services", "devkit")


def _calls(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    aliases = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                aliases[a.asname or a.name] = a.name
        elif isinstance(n, ast.ImportFrom) and n.module in OWNER_WRITERS:
            for a in n.names:
                if a.name in OWNER_WRITERS[n.module]:
                    yield f"{n.module}.{a.name} (imported by name)"
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and isinstance(n.func.value, ast.Name):
            mod = aliases.get(n.func.value.id)
            if mod in OWNER_WRITERS and n.func.attr in OWNER_WRITERS[mod]:
                yield f"{mod}.{n.func.attr}"
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "set_override" and n.args \
                and isinstance(n.args[0], ast.Constant) and n.args[0].value in ("abgleich_apps",):
            yield "ai_config.set_override('abgleich_apps')"


def test_nothing_outside_the_gate_writes_the_owners_of_wires():
    """Follow-up 2: the sync choice, the calendar source and the plugs are
    written only by the apply agent's hand (core/wires.py; the calendar's one
    writer adapter_ablauf.kalender_quelle_setzen is called only from there)."""
    bad = []
    for area in AREAS:
        for d, _dirs, files in os.walk(os.path.join(ROOT, area)):
            if "__pycache__" in d or "skill_vorlagen" in d:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(d, f), ROOT)
                if rel in ALLOWED or rel[:-3].replace(os.sep, "/") in {f"core/{m}" for m in OWNER_WRITERS}:
                    continue
                bad += [f"{rel}: {c}" for c in _calls(os.path.join(d, f))]
    assert bad == [], "write wires through generations.run, not the owner directly: " + "; ".join(bad)


# ── Follow-up 1: the apply agent on the keeper ────────────────────────────

def _chosen(choice):
    r = generations.choose_sync(choice)
    assert r.ok, r["errors"]


def test_keep_without_a_generation_does_nothing(settings):
    abgleich_apps.replace({"fokus": False})
    assert generations.keep() == {"applied": None, "problems": [], "rolled_back": False, "adopted": None}
    assert abgleich_apps.entscheidungen() == {"fokus": False}


def test_keep_reconciles_the_nodes_own_wires_and_is_idempotent(settings):
    _chosen({"fokus": True, "notizen": True})
    before = open(settings, "rb").read()
    assert generations.keep()["applied"] and open(settings, "rb").read() == before   # nothing to do
    ai_config.set_override("abgleich_apps", {"fokus": False}, persist=True)  # written around the gate
    r = generations.keep()
    assert not r["rolled_back"] and r["problems"] == []
    assert abgleich_apps.entscheidungen() == {"fokus": True, "notizen": True}


def test_keep_adopts_an_instance_wire_that_arrived_through_sync(settings):
    _chosen({"fokus": True})
    store = generations.Store()
    first = store.current_hash(NODE)
    ke.schreiben(ke.HAUPT, "lokal")              # as if another node re-plugged it, synced here
    r = generations.keep()
    assert ke.quelle() == "lokal"                # never pushed back
    assert r["adopted"] and store.current_hash(NODE) == r["adopted"] != first
    assert store.history(NODE)[-1]["note"] == "adopted what arrived through sync"
    assert generations.keep()["adopted"] is None


def test_keep_rolls_back_on_a_failed_health_check(settings):
    _chosen({"fokus": True})
    _chosen({"fokus": False})
    store = generations.Store()
    bad = store.current_hash(NODE)
    abgleich_apps.replace({"fokus": True})      # drifted
    r = generations.keep(health=lambda gen, node, done: ["fokus did not come up"]
                         if gen["hash"] == bad else [])
    assert r["rolled_back"] and store.current_hash(NODE) != bad
    assert abgleich_apps.entscheidungen() == {"fokus": True}


def test_the_sync_timer_runs_the_apply_agent(settings):
    _chosen({"fokus": True})
    abgleich_apps.replace({"fokus": False})
    term = Play(interactive=False)
    assert befehle.sync(term, ["--automatic"]) == 0
    assert abgleich_apps.entscheidungen() == {"fokus": True}


def test_a_device_that_never_chose_keeps_everything(settings):
    gen_sk = generations.with_wires(wires.sketch(NODE), [wires.calendar_wire(ke.HAUPT, "lokal")])
    assert generations.run(gen_sk, writer=lambda *a: None, health=lambda *a: []).ok
    assert abgleich_apps.entscheidungen() is None
    generations.keep()
    assert abgleich_apps.entscheidungen() is None


# ── Follow-up 4: the node's own wires in its description ──────────────────

def test_node_section_holds_only_the_nodes_own_wires(settings):
    _chosen({"fokus": False})
    sec = wires.node_section(NODE)
    assert sec["format"] == wires.NODE_WIRES_FORMAT
    assert {w["type"] for w in sec["wires"]} == {"sync"}
    assert all(w["owner"] == "node:" + NODE for w in sec["wires"])
    back = wires.wires_of_description({"name": NODE, "wires": sec})
    assert back == sec["wires"]
    # another node's wires under this name are not taken
    assert wires.wires_of_description({"name": "minipc", "wires": sec}) == []


def test_the_description_goes_out_only_when_the_wires_changed(settings, monkeypatch):
    from devkit.fake_cloud import FalscheCloud
    import konto
    import konto_schluessel as ks
    c = FalscheCloud()
    try:
        monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
        monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
        konto.anlegen(konto.Entwurf("ein-langes-passwort"), "sasha", "ZB-AAAA-BBBB-CCCC-DDDD",
                      "ein-langes-passwort")
        ai_config.set_override("abgleich_mitte_art", "http")
        name = (konto.lesen() or {}).get("knoten") or NODE
        _chosen({"fokus": False})
        assert befehle.describe_wires() is True
        b = c.zustand.knoten["sasha"][name]
        assert b["wires"]["wires"] and b["wires"]["format"] == wires.NODE_WIRES_FORMAT
        assert befehle.describe_wires() is False           # unchanged → nothing sent
        _chosen({"fokus": True})
        assert befehle.describe_wires() is True
    finally:
        c.stopp()
