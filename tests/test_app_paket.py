"""The package builder for one app (memory/hub/app_delivery_plan.md step 4a,
scripts/app_paket_bauen.py): positive list per repo, never data/.git/keys,
same input → same sha256."""
import json
import os
import subprocess
import sys
import tarfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "scripts"))
import app_paket_bauen as apb  # noqa: E402

MANIFEST = 'name = "sparbuch"\nversion = "0.2.0"\ntitel = "Sparbuch"\nansichten = ["terminal"]\n'


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo,
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "sparbuch"
    (r / "sparbuch").mkdir(parents=True)
    (r / "app.toml").write_text(MANIFEST, encoding="utf-8")
    (r / "sparbuch" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (r / "sparbuch" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(r / "sparbuch" / "run.sh", 0o755)
    (r / "README.md").write_text("not listed\n", encoding="utf-8")
    (r / "paket.txt").write_text("# list\napp.toml\nsparbuch/\n", encoding="utf-8")
    _git(r, "init", "-q", "-b", "main")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "app")
    return r


def _names(path):
    with tarfile.open(path) as t:
        return sorted(t.getnames())


def test_builds_the_listed_tracked_files_with_name_and_version(repo, tmp_path):
    (repo / "sparbuch" / "scratch.py").write_text("untracked\n", encoding="utf-8")
    path, info = apb.build(repo, tmp_path / "out")
    assert os.path.basename(path) == "sparbuch-0.2.0.tar.gz"
    assert _names(path) == ["sparbuch-0.2.0/app.toml", "sparbuch-0.2.0/sparbuch/__init__.py",
                            "sparbuch-0.2.0/sparbuch/run.sh"]
    with open(tmp_path / "out" / "sparbuch-0.2.0.json", encoding="utf-8") as f:
        assert json.load(f) == info
    assert info["name"] == "sparbuch" and info["version"] == "0.2.0"
    assert info["size"] == os.path.getsize(path)
    with tarfile.open(path) as t:
        members = {m.name: m for m in t.getmembers()}
    assert members["sparbuch-0.2.0/sparbuch/run.sh"].mode == 0o755
    assert members["sparbuch-0.2.0/app.toml"].mode == 0o644


def test_same_input_same_sha256(repo, tmp_path):
    _, first = apb.build(repo, tmp_path / "a")
    os.utime(repo / "app.toml", (1, 1))                 # another clock, same files
    _, second = apb.build(repo, tmp_path / "b")
    assert first == second
    (repo / "app.toml").write_text(MANIFEST + "# changed\n", encoding="utf-8")
    _, third = apb.build(repo, tmp_path / "c")
    assert third["sha256"] != first["sha256"]


@pytest.mark.parametrize("listed, why", [
    ("data/", "data"),
    ("sparbuch/geheim.key", "key"),
    (".env", "secret"),
    ("sparbuch/../.git/config", "git"),
])
def test_refuses_what_never_goes_into_a_package(repo, tmp_path, listed, why):
    for rel in ("data/x.json", "sparbuch/geheim.key", ".env"):
        os.makedirs(os.path.dirname(repo / rel), exist_ok=True)
        (repo / rel).write_text("secret\n", encoding="utf-8")
    _git(repo, "add", "-f", ".")
    _git(repo, "commit", "-qm", "oops")
    with open(repo / "paket.txt", "a", encoding="utf-8") as f:
        f.write(listed + "\n")
    with pytest.raises(apb.PackageError) as e:
        apb.build(repo, tmp_path / "out")
    assert "never in a package" in str(e.value), why
    assert not os.path.exists(tmp_path / "out" / "sparbuch-0.2.0.tar.gz")


def test_needs_its_list_and_its_app_toml(repo, tmp_path):
    (repo / "paket.txt").write_text("sparbuch/\n", encoding="utf-8")
    with pytest.raises(apb.PackageError, match="app.toml is not in the package list"):
        apb.build(repo, tmp_path / "out")
    os.remove(repo / "paket.txt")
    with pytest.raises(apb.PackageError, match="no paket.txt"):
        apb.build(repo, tmp_path / "out")


def test_command_line(repo, tmp_path):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "app_paket_bauen.py"),
                        str(repo), "--target", str(tmp_path / "out")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "sparbuch-0.2.0.tar.gz" in r.stdout
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "app_paket_bauen.py"),
                        str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 1 and "no paket.txt" in r.stderr
