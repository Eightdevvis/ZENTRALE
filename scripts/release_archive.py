#!/usr/bin/env python3
"""The archive of every released tarball (memory/hub/building_kit_plan.md 2.4,
build step 6) — what tests/test_alte_fassung.py installs as "the old device".

A released tarball is rebuilt from git, never downloaded from the cloud: the
release commit is exported (`git archive`), and THAT commit's own
scripts/paket_bauen.py packs it — the same builder and positive list the
release was published with. The result is kept in the archive folder, so it
is built once per machine:

    dist/releases/zentrale-<N>.tar.gz      (dist/ is never committed)

The folder can be moved with ZENTRALE_RELEASE_ARCHIVE.

RELEASES lists every release that can be installed by deploy/install.sh
(packages exist since release 37) with its commit. A newly published release
gets its line here — server/scripts/paket_hochladen.mjs runs the old-release
test before it uploads anything.

    scripts/release_archive.py            build what is missing, list the archive
    scripts/release_archive.py 41         just that one
"""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# release → commit that published it (git log -- deploy/RELEASE).
RELEASES = {
    "37": "55e1805",
    "38": "b371f7a",
    "39": "7f06637",
    "40": "bc42c51",
    "41": "46a835f",
}


class ArchiveError(Exception):
    pass


def folder() -> str:
    return os.path.abspath(os.path.expanduser(
        os.environ.get("ZENTRALE_RELEASE_ARCHIVE") or os.path.join(ROOT, "dist", "releases")))


def path(version) -> str:
    return os.path.join(folder(), f"zentrale-{version}.tar.gz")


def _git(*args, **kw):
    return subprocess.run(["git", "-C", ROOT, *args], check=True, capture_output=True, **kw)


def build(version) -> str:
    """Rebuild release `version` from its commit into the archive → path."""
    if version not in RELEASES:
        raise ArchiveError(f"unknown release {version!r} (known: {', '.join(RELEASES)})")
    commit = RELEASES[version]
    with tempfile.TemporaryDirectory(prefix="zentrale-release-") as tmp:
        src = os.path.join(tmp, "src")
        os.makedirs(src)
        tar_path = os.path.join(tmp, "src.tar")
        with open(tar_path, "wb") as f:
            f.write(_git("archive", "--format=tar", commit).stdout)
        with tarfile.open(tar_path) as t:
            t.extractall(src, filter="data")
        with open(os.path.join(src, "deploy", "RELEASE"), encoding="utf-8") as f:
            if f.read().strip() != version:
                raise ArchiveError(f"commit {commit} is not release {version}")
        out = os.path.join(tmp, "out")
        r = subprocess.run([sys.executable, os.path.join(src, "scripts", "paket_bauen.py"),
                            "--fassung", version, "--ziel", out],
                           cwd=src, capture_output=True, text=True)
        if r.returncode != 0:
            raise ArchiveError(f"release {version}: paket_bauen failed: {r.stderr.strip()[-500:]}")
        os.makedirs(folder(), exist_ok=True)
        part = path(version) + ".part"
        shutil.copyfile(os.path.join(out, f"zentrale-{version}.tar.gz"), part)
        os.replace(part, path(version))
    return path(version)


def ensure(version) -> str:
    """The archived tarball of `version`, built once if missing."""
    p = path(version)
    return p if os.path.exists(p) else build(version)


def main(argv):
    for v in argv or list(RELEASES):
        print(f"{ensure(v)}  ({os.path.getsize(path(v)) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ArchiveError, subprocess.CalledProcessError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)
