"""The old-release test (memory/hub/building_kit_plan.md 2.4, build step 6):
every released ZENTRALE keeps syncing with today's (support forever, 2.3).

For every release in scripts/release_archive.py: two devices of one account
on this machine (devkit profiles, the real deploy/install.sh, the fake
cloud) — one on the released tarball, rebuilt from its own commit, one on
HEAD. They fill, edit at the same time, delete; both must end with the same
files and nothing lost. server/scripts/paket_hochladen.mjs refuses to
publish while this test is red.

Costs: the released tarballs are built once per machine (dist/releases/);
HEAD's tarball once per run. About 10 s per release.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

from devkit import profiles, workspace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "scripts"))   # last: scripts/abgleich.py must not shadow core/abgleich.py
import release_archive  # noqa: E402

LISTE = [{"id": "einkauf", "name": "Einkauf", "created": "2026-10-01", "next_item": 2,
          "items": [{"id": 1, "text": "Milch", "done": False}]}]


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    w = workspace.Workspace(str(tmp_path_factory.mktemp("devroot-alt")))
    path = w.build_release("head")             # HEAD: a version name no release has
    os.remove(path + workspace.FROM_CHECKOUT)
    return w


class Device:
    def __init__(self, profile):
        self.p = profile
        self.data = os.path.join(profile.hub, "data")
        # `zentrale setup` writes "abgleich_apps": {} (nothing chosen yet) —
        # the devices here sync everything, like after the choice.
        conf = os.path.join(self.data, "ai_config.json")
        with open(conf, encoding="utf-8") as f:
            d = json.load(f)
        d.pop("abgleich_apps", None)
        with open(conf, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def write(self, rel, content):
        p = os.path.join(self.data, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content, indent=2))

    def read(self, rel):
        p = os.path.join(self.data, rel)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return f.read()

    def sync(self):
        r = self.p.zentrale("sync")
        assert r.returncode == 0, f"{self.p.name} ({self.p.installed_release()}): {r.stdout}{r.stderr}"
        return r.stdout


def _pair(ws, version):
    shutil.copyfile(release_archive.ensure(version), ws.release_path(version))
    account = f"acct{version}"
    old = profiles.create(ws, f"old-{version}", "logged-in", release=version,
                          params={"account": account})
    new = profiles.create(ws, f"new-{version}", "logged-in", release="head",
                          params={"account": account})
    assert old.installed_release() == version and new.installed_release() == "head"
    return Device(old), Device(new)


@pytest.mark.parametrize("version", sorted(release_archive.RELEASES, key=int))
def test_old_release_and_head_converge(ws, version):
    old, new = _pair(ws, version)
    with ws.cloud():
        # The old device fills the account, HEAD joins.
        old.write("lists.json", LISTE)
        old.write("gedaechtnis/sasha.md", "# Sasha\nmag Tee\n")
        old.sync()
        new.sync()
        assert json.loads(new.read("lists.json")) == LISTE
        assert new.read("gedaechtnis/sasha.md") == "# Sasha\nmag Tee\n"

        # Both edit at the same time, different files.
        old.write("gedaechtnis/sasha.md", "# Sasha\nmag Tee\nund Kaffee\n")
        liste = json.loads(new.read("lists.json"))
        liste[0]["items"].append({"id": 2, "text": "Brot", "done": False})
        liste[0]["next_item"] = 3
        new.write("lists.json", liste)
        new.write("gedaechtnis/neu.md", "von HEAD\n")
        old.sync()
        new.sync()
        old.sync()
        for rel in ("lists.json", "gedaechtnis/sasha.md", "gedaechtnis/neu.md"):
            assert old.read(rel) is not None and old.read(rel) == new.read(rel), rel
        assert "und Kaffee" in new.read("gedaechtnis/sasha.md")
        assert [i["text"] for i in json.loads(old.read("lists.json"))[0]["items"]] == ["Milch", "Brot"]

        # A deletion on HEAD reaches the old device, and back.
        os.remove(os.path.join(new.data, "gedaechtnis", "neu.md"))
        new.sync()
        old.sync()
        assert old.read("gedaechtnis/neu.md") is None
        os.remove(os.path.join(old.data, "gedaechtnis", "sasha.md"))
        old.sync()
        new.sync()
        assert new.read("gedaechtnis/sasha.md") is None


def test_every_published_release_is_in_the_archive():
    """deploy/RELEASE of every installable release (packages since 37) has
    its line in release_archive.RELEASES with the commit that published it."""
    log = subprocess.run(["git", "-C", ROOT, "log", "--format=%h", "--", "deploy/RELEASE"],
                         capture_output=True, text=True, check=True).stdout.split()
    published = {}
    for commit in log:
        r = subprocess.run(["git", "-C", ROOT, "show", f"{commit}:deploy/RELEASE"],
                           capture_output=True, text=True)
        v = r.stdout.strip()
        if r.returncode == 0 and v.isdigit() and int(v) >= 37:
            published[v] = commit
    assert set(published) == set(release_archive.RELEASES)
    for v, commit in release_archive.RELEASES.items():
        assert subprocess.run(["git", "-C", ROOT, "show", f"{commit}:deploy/RELEASE"],
                              capture_output=True, text=True).stdout.strip() == v


def test_publishing_runs_this_test_first():
    with open(os.path.join(ROOT, "server", "scripts", "paket_hochladen.mjs"), encoding="utf-8") as f:
        script = f.read()
    upload = script.index('hoch(`pakete/')
    gate = script.index("tests/test_alte_fassung.py")
    assert gate < upload


# ── The app register (node-local, never synced) ──────────────────────
#
# Register v2 (memory/hub/app_delivery_plan.md step 1) adds fields; a node
# that goes back to an older release must still read the file the newer one
# wrote. Readers: every archived release that has core/app_register.py, plus
# the last commit before v2 (no release had the register yet on 2026-10-31).

REGISTER_BEFORE_V2 = "4e755ee"

_OLD_READER = r"""
import json, sys, types
folder, reader = sys.argv[1], sys.argv[2]
ai_config = types.ModuleType("ai_config")
ai_config.setting = lambda k, *a: folder if k == "installiert_ordner" else None
dateien = types.ModuleType("dateien")
dateien.knoten = lambda: "node"
sys.modules.update(ai_config=ai_config, dateien=dateien)
ns = {"__file__": reader, "__name__": "app_register"}
exec(compile(open(reader).read(), reader, "exec"), ns)
print(json.dumps([[e["name"], e["ordner"], e["ansichten"]] for e in ns["lesen"]()]))
"""


def _register_readers():
    readers = []
    for commit in [*release_archive.RELEASES.values(), REGISTER_BEFORE_V2]:
        r = subprocess.run(["git", "-C", ROOT, "show", f"{commit}:core/app_register.py"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            readers.append((commit, r.stdout))
    return readers


def test_older_code_reads_the_v2_register(tmp_path):
    import app_register
    app_register.schreiben([
        {"name": "budget", "quelle": "zentrale://shop/apps/budget", "ordner": "/x/budgeter",
         "ansichten": ["browser"], "am": "2026-10-31T12:00:00+01:00",
         "source": {"kind": "zentrale-package", "ref": "https://x/budget.tar.gz"},
         "version": "0.4.1", "data": {"files": "zentrale-data"}}])
    folder = os.path.dirname(app_register.datei())
    os.replace(app_register.datei(), os.path.join(folder, "apps-node.json"))
    readers = _register_readers()
    assert any(c == REGISTER_BEFORE_V2 for c, _ in readers), "the commit before v2 must be readable"
    for commit, source in readers:
        path = tmp_path / f"app_register_{commit}.py"
        path.write_text(source, encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", "-c", _OLD_READER, folder, str(path)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{commit}: {r.stderr}"
        assert json.loads(r.stdout) == [["budget", "/x/budgeter", ["browser"]]], commit
