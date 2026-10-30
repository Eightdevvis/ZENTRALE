"""Automatic updates (memory/hub/building_kit_plan.md 5.3, build step 2):
`zentrale update --automatic` against a fake cloud with small packages; the
self-test is injected here (the real one runs in tests/test_dev_mode.py)."""
import io
import os
import sys

import pytest

import ai_config
import dateien
import konto
import konto_schluessel as ks
from devkit import fake_systemd
from devkit.fake_cloud import FalscheCloud
from zentrale_cli import aktualisieren, befehle, haupt
from zentrale_cli.ausgabe import Terminal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "scripts"))
import paket_bauen  # noqa: E402

PW = "ein-langes-passwort"


def _package(tmp_path, version):
    src = tmp_path / f"src-{version}"
    (src / "bin").mkdir(parents=True)
    (src / "bin" / "zentrale").write_text("#!/bin/sh\n")
    (src / "requirements-basis.txt").write_text("")
    path, _n = paket_bauen.bauen(version, root=str(src), ziel_ordner=str(tmp_path / "dist"),
                                 liste=[("bin/zentrale", "bin/zentrale"),
                                        ("requirements-basis.txt", "requirements-basis.txt")])
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def node(tmp_path, monkeypatch):
    """An installed node on release 1, logged in, with a fake systemd."""
    home = tmp_path / "heim"
    old = home / "hub" / "1"
    old.mkdir(parents=True)
    (old / "VERSION").write_text("1\n")
    os.symlink("1", home / "hub" / "aktuell")
    monkeypatch.setenv("ZENTRALE_HEIM", str(home))
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(tmp_path / "ai_config.json"))
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_overrides", {})
    fake = fake_systemd.make(tmp_path / "systemd")
    for k, v in fake.env().items():
        monkeypatch.setenv(k, v)
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    monkeypatch.setattr(dateien, "knoten", lambda: "minipc")
    monkeypatch.setattr(befehle, "WURZEL", str(old))
    konto.anlegen(konto.Entwurf(PW), "sasha", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    c.zustand.paket = ("2", _package(tmp_path, "2"))
    c.home, c.old, c.fake, c.checks, c.venvs = home, old, fake, [], []
    yield c
    c.stopp()


def _auto(node, ok=True):
    term = Terminal(aus=io.StringIO())

    def check(release):
        node.checks.append(os.path.basename(release))
        return ok, "" if ok else "Self-test failed: ImportError: broken"
    rc = aktualisieren.automatic(term, venv=node.venvs.append, wurzel=str(node.old), check=check)
    return rc, term.aus.getvalue()


def test_new_release_is_tested_switched_and_the_backend_restarted(node):
    node.fake.set_active("zentrale-kern.service")
    rc, out = _auto(node)
    assert rc == 0, out
    assert node.checks == ["2"]                                   # self-test before the switch
    assert os.readlink(node.home / "hub" / "aktuell") == "2"
    assert "--user try-restart zentrale-kern.service" in node.fake.calls()
    assert aktualisieren.state() == {}


def test_broken_release_stays_with_one_note(node, monkeypatch):
    rc, out = _auto(node, ok=False)
    assert rc == 1 and "failed its self-test" in out and "ImportError" in out
    assert os.readlink(node.home / "hub" / "aktuell") == "1"
    assert not (node.home / "hub" / "2").exists()
    assert aktualisieren.state()["failed"]["version"] == "2"
    # The next day: one note is enough — no second download, quiet.
    rc, out = _auto(node, ok=False)
    assert rc == 0 and out == "" and node.checks == ["2"]
    monkeypatch.setattr(befehle, "kanal", lambda w: "script")
    term = Terminal(aus=io.StringIO())
    befehle.status(term)
    assert "Update to 2 failed its self-test; staying on 1" in term.aus.getvalue()


def test_setting_off_only_says_update_available(node, monkeypatch):
    assert haupt.main(["update", "auto", "off"], term=Terminal(aus=io.StringIO())) == 0
    assert aktualisieren.auto_on() is False
    rc, out = _auto(node)
    assert rc == 0 and out == "" and node.checks == [] and node.venvs == []
    assert os.readlink(node.home / "hub" / "aktuell") == "1"
    monkeypatch.setattr(befehle, "kanal", lambda w: "script")
    term = Terminal(aus=io.StringIO())
    befehle.status(term)
    text = term.aus.getvalue()
    assert "Update available: 1 → 2" in text and "Auto-update" in text and "off" in text
    # The start line before the TUI says the same.
    monkeypatch.setattr(befehle, "tui", lambda term: 0)
    monkeypatch.setattr(befehle, "eingerichtet", lambda: True)
    term = Terminal(aus=io.StringIO())
    assert haupt.main([], term=term) == 0 and "Update available: 1 → 2" in term.aus.getvalue()


def test_nothing_new_is_quiet_and_package_managers_only_hint(node, monkeypatch):
    node.zustand.paket = ("1", _package(node.home.parent, "1"))
    assert _auto(node) == (0, "")
    node.zustand.paket = ("2", _package(node.home.parent, "2b"))
    (node.old / "KANAL").write_text("pacman\n")
    rc, out = _auto(node)
    assert rc == 0 and out == "" and node.venvs == []
    assert "package manager installs it" in aktualisieren.hint(str(node.old))


def test_update_auto_usage():
    term = Terminal(aus=io.StringIO())
    assert haupt.main(["update", "auto", "maybe"], term=term) == 2
    assert haupt.main(["update", "--sideways"], term=term) == 2
