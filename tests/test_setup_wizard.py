"""The setup wizard (zentrale_cli/wizard.py, building kit 5.1, build steps
2 and 3): steps as data, defaults on Enter, 'b' goes back, an interrupted
wizard picks up where it stopped, lingering asked without sudo. Played
terminal, fake cloud, fake systemd/loginctl (devkit/fake_systemd.py)."""
import io
import json

import pytest

import ai_config
import dateien
import konto_schluessel as ks
from devkit import fake_systemd
from devkit.fake_cloud import FalscheCloud
from zentrale_cli import aktualisieren, assistent, befehle, wizard
from zentrale_cli.ausgabe import Terminal

PW = "ein-langes-passwort"
CREATE = ["2", "ZB-AAAA-BBBB-CCCC-DDDD", "sasha", PW, PW, "y"]


class Played(Terminal):
    def __init__(self, *answers):
        super().__init__(aus=io.StringIO(), ein=io.StringIO("".join(a + "\n" for a in answers)))

    @property
    def text(self):
        return self.aus.getvalue()


@pytest.fixture
def node(monkeypatch, tmp_path):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    monkeypatch.setattr(dateien, "knoten", lambda: "minipc")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(tmp_path / "abgleich"))
    monkeypatch.setenv("ZENTRALE_HEIM", str(tmp_path / "heim"))
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(tmp_path / "ai_config.json"))
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_overrides", {"cloud_folder_dir": str(tmp_path / "cloud-folder")})
    root = tmp_path / "hub"
    (root / "data").mkdir(parents=True)
    monkeypatch.setattr(befehle, "WURZEL", str(root))
    # An installed node (install.sh): the auto-update step applies.
    monkeypatch.setattr(aktualisieren, "kanal", lambda w: "script")
    monkeypatch.setattr(befehle, "kanal", lambda w: "script")
    fake = fake_systemd.make(tmp_path / "systemd")
    for k, v in fake.env().items():
        monkeypatch.setenv(k, v)
    c.fake, c.tmp = fake, tmp_path
    yield c
    c.stopp()


def _settings(node):
    with open(node.tmp / "ai_config.json", encoding="utf-8") as f:
        return json.load(f)


def test_steps_are_data_in_the_planned_order():
    assert [s.name for s in wizard.STEPS] == ["account", "cloud_folder", "auto_update", "linger", "purpose"]


def test_defaults_all_the_way(node):
    term = Played(*CREATE, "", "", "")            # cloud folder, auto-update, linger: Enter
    assert assistent.setup(term) == 0, term.text
    s = _settings(node)
    assert s["abgleich_apps"] == {"cloud_folder": True}
    assert aktualisieren.auto_on() and node.fake.lingering()
    assert "loginctl --no-ask-password enable-linger" in "\n".join(node.fake.calls())
    assert "(default)" in term.text and "Step 4 of 5" in term.text
    assert s["einrichtung"] and not s.get(wizard.PROGRESS)
    assert "zentrale-update.timer" in node.fake.enabled()
    term = Played()
    befehle.status(term)
    assert "keeps syncing when you are logged out" in term.text and "on (daily)" in term.text


def test_back_goes_to_the_last_question(node):
    term = Played(*CREATE, "2",                    # no cloud folder
                  "b",                             # auto-update: back
                  "1",                             # cloud folder after all
                  "2", "2")                        # auto-update off, no lingering
    assert assistent.setup(term) == 0, term.text
    assert _settings(node)["abgleich_apps"] == {"cloud_folder": True}
    assert aktualisieren.auto_on() is False and not node.fake.lingering()
    assert "syncs only while you are logged in" in term.text


def test_local_then_back_then_local(node):
    term = Played("3", "b", "3", "")              # local, back at auto-update, local, Enter
    assert assistent.setup(term) == 0, term.text
    assert "runs locally" in term.text and not node.zustand.aufrufe
    assert term.text.count("How do you want to use ZENTRALE") == 2


def test_lingering_refused_says_how_and_status_tells(node):
    node.fake.set_linger(allowed=False)
    term = Played(*CREATE, "", "", "")
    assert assistent.setup(term) == 0, term.text
    assert "loginctl enable-linger" in term.text and "only while you are logged in" in term.text
    term = Played()
    befehle.status(term)
    assert "syncs only while you are logged in" in term.text


def test_interrupted_wizard_picks_up_where_it_stopped(node):
    term = Played(*CREATE, "")                     # stops at auto-update (end of input)
    with pytest.raises(EOFError):
        assistent.setup(term, erster_start=True)
    assert _settings(node)[wizard.PROGRESS] == "auto_update"
    assert not befehle.eingerichtet()
    term = Played("2", "")                         # auto-update off, lingering yes
    assert assistent.setup(term) == 0, term.text
    assert "Picking up where you left off." in term.text
    assert "How do you want to use" not in term.text and "A folder that syncs" not in term.text
    assert aktualisieren.auto_on() is False and befehle.eingerichtet()
    # Re-opened later (from the settings): from the start; logged in → no account question.
    term = Played("", "", "")
    assert assistent.setup(term) == 0, term.text
    assert "Picking up" not in term.text and "A folder that syncs" in term.text
