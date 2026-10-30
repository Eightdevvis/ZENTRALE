"""Schematix, the wiring map (memory/hub/schematix.md; building kit steps
13–15, memory/hub/building_kit_plan.md section 8).

Step 13 acceptance: the map of an account shows laptop, mini, apps and sync
wires exactly as `zentrale status` on each node — two devices on the dev
kit's fake cloud (devkit/fake_cloud.py), each with its own settings, each
publishing its description; the map is built on the laptop."""
import io
import re

import pytest

import abgleich_apps
import ai_config
import cloud_notices
import dateien
import konto
import konto_schluessel as ks
import schematix_map
import schematix_store
import schematix_versions
import wires
from devkit.fake_cloud import FalscheCloud
from zentrale_cli import befehle, haupt
from zentrale_cli.ausgabe import Terminal
from zentrale_cli.texte import t

PW = "ein-langes-passwort"
CODE = "ZB-AAAA-BBBB-CCCC-DDDD"


class Play(Terminal):
    def __init__(self):
        super().__init__(aus=io.StringIO(), ein=io.StringIO(""))

    @property
    def text(self):
        return self.aus.getvalue()


class Device:
    """One node in this process: own folders, own settings, own name."""

    def __init__(self, mp, tmp, name):
        self.mp, self.name = mp, name
        self.folder = tmp / name
        self.root = self.folder / "zentrale"
        (self.root / "data").mkdir(parents=True)
        (self.root / "VERSION").write_text("44\n")
        self.config, self.overrides = {}, {}

    def me(self):
        self.mp.setenv("ZENTRALE_ABGLEICH_DIR", str(self.folder / "abgleich"))
        self.mp.setenv("ZENTRALE_KONTO_DATEI", str(self.folder / "konto.json"))
        self.mp.setenv("ZENTRALE_NUTZUNG_DIR", str(self.folder / "state"))
        self.mp.setenv("ZENTRALE_GENERATIONS", str(self.folder / "generations"))
        self.mp.setenv("ZENTRALE_NODE_NAME", self.name)
        self.mp.setattr(dateien, "knoten", lambda: self.name)
        self.mp.setattr(befehle, "WURZEL", str(self.root))
        self.mp.setattr(ai_config, "_config", self.config)
        self.mp.setattr(ai_config, "_overrides", self.overrides)
        return self

    def status(self):
        self.me()
        term = Play()
        assert haupt.main(["status"], term=term) == 0
        return term.text


@pytest.fixture
def cloud(monkeypatch):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "http")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WEG", "mitte")
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    monkeypatch.setattr(cloud_notices, "_release", "44")
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    yield c
    c.stopp()


@pytest.fixture
def two(cloud, monkeypatch, tmp_path):
    """minipc creates the account, laptop logs in; different sync choices."""
    mini = Device(monkeypatch, tmp_path, "minipc").me()
    konto.anlegen(konto.Entwurf(PW), "sasha", CODE, PW)
    abgleich_apps.setzen({"fokus": True, "notizen": False, "tutor": True})
    befehle.geraet_melden()
    laptop = Device(monkeypatch, tmp_path, "laptop").me()
    konto.anmelden("sasha", PW)
    abgleich_apps.setzen({"fokus": True, "notizen": True, "tutor": False, "graph": False})
    befehle.geraet_melden()
    return mini, laptop


def _status_apps(text):
    """{human app name: state text} from the Apps block of `zentrale status`."""
    block = text.split(t("st_apps"), 1)[1].split("\n\n", 1)[0]
    out = {}
    for line in block.splitlines()[1:]:
        m = re.match(r"^\s{2}(.+?)\s{2,}(.+)$", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


STATE_TEXT = {"synced": "st_app_on", "off": "st_app_off", "open": "st_app_open"}


def _map_apps(m, node):
    """{human app name: state text} of one node's app pieces on the map."""
    out = {}
    for p in m["pieces"]:
        if p.get("node") != node or p.get("band") != "software" or "sync" not in p:
            continue
        name = befehle.app_name(p["name"])[0]
        if p["sync"] == "always":
            out[name] = t("st_app_adapter", n=0).split(" — ")[0]
        else:
            out[name] = t(STATE_TEXT[p["sync"]])
    return out


def _without_counts(d):
    return {k: v.split(" — ")[0] for k, v in d.items()}


def test_map_of_the_account_matches_status_on_each_node(two):
    mini, laptop = two
    laptop.me()
    descriptions, notes = schematix_map.account_descriptions()
    assert notes == [] and {d["name"] for d in descriptions} == {"minipc", "laptop"}
    m = schematix_map.build(wires.sketch(), "laptop", schematix_versions.own(str(laptop.root)),
                            descriptions)
    ids = {p["id"] for p in m["pieces"]}
    assert {"node:laptop", "node:minipc", "app:cloud", "app:tutor@minipc", "app:fokus@laptop"} <= ids
    for dev in (mini, laptop):
        status = _without_counts(_status_apps(dev.status()))
        status.pop(befehle.app_name("cloud")[0])            # the account's cloud row: its own piece
        assert len(status) >= 8 and _map_apps(m, dev.name) == status, dev.name
    # Sync wires: from the cloud to the app on that node, owner that node.
    sync = {w["id"]: w for w in m["wires"] if w["type"] == "sync"}
    assert sync["sync/minipc/notizen"]["state"] == "off"
    assert sync["sync/minipc/tutor"]["to_piece"] == "app:tutor@minipc"
    assert sync["sync/laptop/fokus"]["from_piece"] == "app:cloud"
    assert all(w["layer"] == "data" for w in sync.values())
    # The versions panel of the other node comes from its description.
    mini_piece = next(p for p in m["pieces"] if p["id"] == "node:minipc")
    assert mini_piece["versions"]["zentrale"] == "44" and mini_piece["versions"]["auto_update"] is True
    assert mini_piece["cannot_yet"] == []


def test_map_route_lays_out_a_cross_section(two):
    _mini, laptop = two
    laptop.me()
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    m = c.get("/api/schematix/map").json
    y = {p["id"]: p["y"] for p in m["pieces"]}
    assert y["app:cloud"] < y["app:fokus@laptop"] < y["node:laptop"]          # cloud → software → nodes
    assert y["node:laptop"] == y["node:minipc"]
    pieces = c.get("/api/pieces").json["pieces"]
    groups = {p["group"] for p in pieces}
    assert {"node", "device"} <= groups and any(p["id"] == "node:minipc" for p in pieces)


def test_logged_out_shows_this_node_only(monkeypatch):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "datei")
    d, notes = schematix_map.account_descriptions()
    assert d == [] and notes
    m = schematix_map.layout(schematix_map.build(wires.sketch(), wires.node_name(),
                                                 schematix_versions.own(), d, notes))
    assert [p for p in m["pieces"] if p["kind"] == "node"][0]["this"] is True


def test_an_old_node_says_what_it_cannot_do_yet():
    old = {"name": "pi", "programm": "39", "types": {"sync": "1.0.0"}}
    lines = schematix_versions.cannot_yet(old)
    assert any("apply agent" in x for x in lines) and any("versions panel" in x for x in lines)
    assert any("does not speak" in x for x in lines)
    m = schematix_map.build(wires.sketch(), wires.node_name(), schematix_versions.own(), [old])
    pi = next(p for p in m["pieces"] if p["id"] == "node:pi")
    assert pi["managed"] is False and pi["versions"] is None


def test_default_palette_reaches_the_contrast_floor():
    """Sasha's e-ink rule: never below 4.5:1 (measured, never corrected)."""
    measured = schematix_store.measured(schematix_store.default_palette())
    assert measured and min(measured.values()) >= 4.5, measured


def test_palette_role_is_stored_and_measured_not_corrected():
    roles = schematix_store.set_role("dim", "#1a1f1b")          # far too dark: kept as it is
    assert roles["dim"] == "#1a1f1b" and schematix_store.measured(roles)["dim"] < 4.5
    assert schematix_store.set_role("dim", None)["dim"] == schematix_store.default_palette()["dim"]
    with pytest.raises(schematix_store.StoreError):
        schematix_store.set_role("dim", "green")
