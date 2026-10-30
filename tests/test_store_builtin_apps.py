"""Building kit step 10 (memory/hub/building_kit_plan.md section 4): Cloud and
Cloud folder are store apps — listed, installed at signup, removable — and
the account owns what was installed (GET/PUT /v1/besitz, the fake cloud of
devkit/). A second device on the same account is offered the owned apps."""
import io
import json

import pytest

import abgleich_apps
import account_ownership
import ai_config
import app_installation
import builtin_store_apps as builtin
import dateien
import konto
import konto_schluessel as ks
from devkit.fake_cloud import FalscheCloud
from zentrale_cli import aktualisieren, assistent, befehle, wizard
from zentrale_cli.ausgabe import Terminal

PW = "ein-langes-passwort"
CREATE = ["2", "ZB-AAAA-BBBB-CCCC-DDDD", "sasha", PW, PW, "y"]
LOGIN = ["1", "sasha", PW]
CLOUD = builtin.address("cloud")
FOLDER = builtin.address("cloud_folder")
BUDGET = "zentrale://shop/apps/budget"


class Played(Terminal):
    def __init__(self, *answers):
        super().__init__(aus=io.StringIO(), ein=io.StringIO("".join(a + "\n" for a in answers)))

    @property
    def text(self):
        return self.aus.getvalue()


def _device(monkeypatch, tmp, name):
    """Point every per-device place at tmp/<name> (settings, account file, root)."""
    d = tmp / name
    (d / "hub" / "data").mkdir(parents=True)
    monkeypatch.setattr(dateien, "knoten", lambda: name)
    monkeypatch.setenv("ZENTRALE_KONTO_DATEI", str(d / "konto.json"))
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(d / "abgleich"))
    monkeypatch.setenv("ZENTRALE_HEIM", str(d / "heim"))
    monkeypatch.setenv("ZENTRALE_SHOP_ORDNER", str(d / "shop"))
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(d / "ai_config.json"))
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_overrides", {"cloud_folder_dir": str(d / "cloud-folder")})
    monkeypatch.setattr(befehle, "WURZEL", str(d / "hub"))
    return d


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setenv("ZENTRALE_SYSTEMCTL", str(tmp_path / "no-systemctl"))   # no timers here
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    monkeypatch.setattr(aktualisieren, "kanal", lambda w: "dev")       # no auto-update step
    c.tmp, c.mp = tmp_path, monkeypatch
    yield c
    c.stopp()


def _client():
    from ui.app import app
    app.config["TESTING"] = True
    return app.test_client()


def test_fresh_account_has_both_installed_and_owned(cloud):
    _device(cloud.mp, cloud.tmp, "minipc")
    assert not builtin.installed("cloud")
    term = Played(*CREATE, "")                       # cloud folder: Enter = yes
    assert assistent.setup(term) == 0, term.text
    assert builtin.installed_names() == ["cloud", "cloud_folder"]
    assert set(account_ownership.owned()) == {CLOUD, FOLDER}
    # The store sees it the same way (route of the hub).
    r = _client().get("/api/apps/installed").get_json()
    assert {CLOUD, FOLDER} <= set(r["adressen"])
    # The server only ever got an opaque string.
    blob = cloud.zustand.besitz["sasha"][0]
    assert "cloud_folder" not in blob and "zentrale://" not in blob


def test_remove_and_install_through_the_store(cloud):
    _device(cloud.mp, cloud.tmp, "minipc")
    assert assistent.setup(Played(*CREATE, "")) == 0
    c = _client()
    r = c.post("/api/apps/remove", json={"adresse": FOLDER}).get_json()
    assert r == {"adresse": FOLDER, "name": "cloud_folder", "installiert": False, "war": True}
    r = c.post("/api/apps/remove", json={"adresse": CLOUD}).get_json()
    assert r["war"] is True and not builtin.installed("cloud")
    assert konto.angemeldet()                        # removing the cloud: local, nothing deleted
    assert set(account_ownership.owned()) == {CLOUD, FOLDER}        # ownership stays
    r = c.post("/api/apps/installieren", json={"adresse": CLOUD}).get_json()
    assert r["built_in"] and r["neu"] and builtin.installed("cloud")
    assert c.post("/api/apps/remove", json={"adresse": BUDGET}).status_code == 501
    assert c.post("/api/apps/laden", json={"adresse": FOLDER}).get_json()["installiert"] is False


def test_cloud_needs_an_account(cloud):
    _device(cloud.mp, cloud.tmp, "minipc")
    with pytest.raises(app_installation.InstallFehler) as e:
        app_installation.installieren(CLOUD, None)
    assert e.value.code == 409 and not builtin.installed("cloud")


def test_second_device_is_offered_the_owned_apps(cloud):
    _device(cloud.mp, cloud.tmp, "minipc")
    assert assistent.setup(Played(*CREATE, "")) == 0
    account_ownership.mark([BUDGET])                 # bought/installed on the mini
    _device(cloud.mp, cloud.tmp, "laptop")           # same account, new device
    term = Played(*LOGIN, "")                        # log in, cloud folder: Enter = yes
    assert assistent.setup(term) == 0, term.text
    assert "Your account owns apps that are not on this device yet: Budget" in term.text
    assert "from the store" in term.text
    assert builtin.installed_names() == ["cloud", "cloud_folder"]


def test_purpose_step_installs_an_owned_builtin_app(cloud):
    """Resumed at "what is this device for": the cloud folder was not asked
    in this run, the account owns it → offered and installed on yes."""
    _device(cloud.mp, cloud.tmp, "minipc")
    assert assistent.setup(Played(*CREATE, "")) == 0
    _device(cloud.mp, cloud.tmp, "laptop")
    assert befehle.login(Played("sasha", PW)) == 0
    assistent.cloud_einschalten()
    abgleich_apps.setzen({})                         # nothing decided on this device yet
    term = Played("")                                # install them here: Enter = yes
    names = [s.name for s in wizard.STEPS]
    assert wizard.run(term, start=names.index("purpose")) == 0, term.text
    assert "Install Cloud folder here too?" in term.text
    assert builtin.installed("cloud_folder")
    s = json.load(open(ai_config._CONFIG_PATH, encoding="utf-8"))
    assert s["abgleich_apps"]["cloud_folder"] is True
