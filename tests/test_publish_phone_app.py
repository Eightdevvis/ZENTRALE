"""scripts/publish_phone_app.py — version bump, APK checks and the upload
order, against a fake cloud client. Never the network."""
import argparse
import ast
import gettext
import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

import cloud_api
import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "scripts"))
import publish_phone_app as pub  # noqa: E402


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    """Messages are matched in English below; German is checked separately."""
    monkeypatch.setenv("ZENTRALE_LANG", "en")


@pytest.fixture(autouse=True)
def _no_real_release_key(tmp_path, monkeypatch):
    """bump/publish check the release key first — never the real one here."""
    monkeypatch.setenv("ZENTRALE_ANDROID_KEY_PROPERTIES", str(tmp_path / "android" / "key.properties"))


def test_every_message_has_a_german_text():
    tree = ast.parse(open(pub.__file__, encoding="utf-8").read())
    msgids = [n.args[0].value for n in ast.walk(tree)
              if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_"]
    assert len(msgids) > 20
    with open(os.path.join(i18n.LOCALE_DIR, "de", "LC_MESSAGES", "zentrale.mo"), "rb") as f:
        de = gettext.GNUTranslations(f)
    for m in msgids:
        assert de.gettext(m) != m, f"no German text for {m!r}"
        assert sorted(re.findall(r"\{(\w+)\}", de.gettext(m))) == sorted(re.findall(r"\{(\w+)\}", m))


class FakeClient:
    def __init__(self, published=None):
        self.published = published
        self.calls = []
        self.zeit = 30
        self.token = "t"

    def get(self, path):
        self.calls.append(("GET", path))
        if self.published is None:
            raise cloud_api.CloudFehler("No release.", "no_release", 404)
        return self.published

    def roh(self, method, path, abfrage=None, roh_body=None, **kw):
        self.calls.append((method, path, abfrage, len(roh_body), self.zeit))
        return 204, {}

    def put(self, path, data):
        self.calls.append(("PUT", path, data))
        return {**data, "published_at": "2026-10-29T10:00:00.000Z"}


def _signed(debug):
    def run(cmd, **kw):
        out = "Owner: CN=Android Debug, O=Android" if debug else "Owner: CN=ZENTRALE, O=Sasha"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    return run


@pytest.fixture
def project(tmp_path, monkeypatch):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("name: zen_mobile\nversion: 0.1.0\n\nenvironment:\n  sdk: ^3.10.0\n")
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"PK\x03\x04 not really an apk")
    meta = tmp_path / "output-metadata.json"
    monkeypatch.setattr(pub.shutil, "which", lambda name: "/usr/bin/" + name)
    return pubspec, apk, meta


def _meta(meta, code):
    meta.write_text(json.dumps({"elements": [{"versionCode": code, "versionName": "x"}]}))


def test_read_and_write_version():
    assert pub.read_version("version: 0.1.0\n") == ("0.1.0", 1)
    assert pub.read_version("a: b\nversion: 1.2.3+42\n") == ("1.2.3", 42)
    assert pub.write_version("x: 1\nversion: 0.1.0\ny: 2\n", "0.2.0", 5) == "x: 1\nversion: 0.2.0+5\ny: 2\n"
    with pytest.raises(pub.PublishError):
        pub.read_version("name: x\n")
    with pytest.raises(pub.PublishError):
        pub.write_version("version: 1\n", "0.1", 0)
    assert pub.next_code(3, 0) == 4
    assert pub.next_code(3, 9) == 10


def test_bump_goes_above_the_published_code(project):
    pubspec, _apk, _meta_path = project
    args = argparse.Namespace(name="0.2.0", offline=False)
    assert pub.cmd_bump(args, lambda: FakeClient({"version_code": 7}), str(pubspec)) == ("0.2.0", 8)
    assert "version: 0.2.0+8" in pubspec.read_text()
    args = argparse.Namespace(name=None, offline=True)
    assert pub.cmd_bump(args, None, str(pubspec)) == ("0.2.0", 9)


def test_publish_uploads_apk_first_then_manifest(project):
    pubspec, apk, meta = project
    pubspec.write_text("version: 0.2.0+8\n")
    _meta(meta, 8)
    c = FakeClient({"version_code": 7})
    args = argparse.Namespace(apk=str(apk), build=False, dry_run=False, notes="Calmer eye")
    m = pub.cmd_publish(args, lambda: c, str(pubspec), str(meta), _signed(False))
    sha = hashlib.sha256(apk.read_bytes()).hexdigest()
    assert c.calls[0] == ("GET", "/v1/phone/release")
    assert c.calls[1] == ("PUT", "/v1/phone/release/8.apk", {"sha256": sha}, apk.stat().st_size,
                          pub.UPLOAD_TIMEOUT)
    assert c.calls[2] == ("PUT", "/v1/phone/release", {
        "version": "0.2.0", "version_code": 8, "sha256": sha, "size": apk.stat().st_size, "notes": "Calmer eye"})
    assert m["version_code"] == 8
    assert c.zeit == 30


def test_publish_refuses_bad_apks(project):
    pubspec, apk, meta = project
    pubspec.write_text("version: 0.2.0+8\n")
    args = argparse.Namespace(apk=str(apk), build=False, dry_run=False, notes="")

    _meta(meta, 7)  # built before the bump
    with pytest.raises(pub.PublishError, match="version code 7"):
        pub.cmd_publish(args, lambda: FakeClient(), str(pubspec), str(meta), _signed(False))

    _meta(meta, 8)
    with pytest.raises(pub.PublishError, match="debug key"):
        pub.cmd_publish(args, lambda: FakeClient(), str(pubspec), str(meta), _signed(True))

    c = FakeClient({"version_code": 8})  # already published
    with pytest.raises(pub.PublishError, match="not higher"):
        pub.cmd_publish(args, lambda: c, str(pubspec), str(meta), _signed(False))
    assert all(call[0] == "GET" for call in c.calls)

    missing = argparse.Namespace(apk=str(apk) + ".gone", build=False, dry_run=False, notes="")
    with pytest.raises(pub.PublishError, match="No APK"):
        pub.cmd_publish(missing, lambda: FakeClient(), str(pubspec), str(meta), _signed(False))


def test_without_metadata_the_file_date_decides(project):
    pubspec, apk, meta = project
    pubspec.write_text("version: 0.2.0+8\n")
    os.utime(apk, (1_000, 1_000))
    with pytest.raises(pub.PublishError, match="older"):
        pub.check_apk(str(apk), 8, str(pubspec), str(meta), _signed(False))
    os.utime(apk, None)
    os.utime(pubspec, (1_000, 1_000))
    warnings = pub.check_apk(str(apk), 8, str(pubspec), str(meta), _signed(False))
    assert len(warnings) == 1


def test_dry_run_uploads_nothing(project):
    pubspec, apk, meta = project
    pubspec.write_text("version: 0.2.0+2\n")
    _meta(meta, 2)
    c = FakeClient()  # nothing published yet → 404 → 0
    args = argparse.Namespace(apk=str(apk), build=False, dry_run=True, notes="")
    assert pub.cmd_publish(args, lambda: c, str(pubspec), str(meta), _signed(False)) is None
    assert c.calls == [("GET", "/v1/phone/release")]
