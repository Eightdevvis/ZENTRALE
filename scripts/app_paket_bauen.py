#!/usr/bin/env python3
"""Build the package of one app (memory/hub/app_delivery_plan.md step 4a).

    scripts/app_paket_bauen.py <app repo> [--target DIR]

Reads the app's positive list `<repo>/paket.txt` (same format as
deploy/paket.txt: one path per line, folders recursive, `source => target`,
'#' comments) and writes

    <target>/<name>-<version>.tar.gz     top folder <name>-<version>/
    <target>/<name>-<version>.json       {name, version, sha256, size}

`name` and `version` come from the app's `app.toml`, which must be in the
list. Only what git tracks goes in (commit first, then build). Refused even
when listed: data/, .git, venv, keys and secrets (*.key, *.pem, *.enc,
*.schluessel, .env, ai_config.json) — the same guard as the core package
(scripts/paket_bauen.py), minus memory/ and tests/, which an app may ship.

Reproducible: the same files give the same bytes (sorted, fixed owner, fixed
mtime, gzip header without a time stamp), so the same input always has the
same sha256 — what the `zentrale-package` source adapter checks (step 4c).
"""

import argparse
import fnmatch
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paket_bauen  # noqa: E402

LIST = "paket.txt"
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$")
FORBIDDEN_DIRS = ("data", ".git", "venv", ".venv", "__pycache__", ".claude", "dist")
FORBIDDEN_NAMES = ("*.enc", "*.enc.bak", "ai_config.json", "*.schluessel", "*.pyc",
                   "*.key", "*.pem", ".env", "id_rsa*", "id_ed25519*")
MTIME = 0                     # every member; no clock in a package


class PackageError(Exception):
    pass


def forbidden(rel: str) -> bool:
    parts = rel.replace(os.sep, "/").split("/")
    if any(p in FORBIDDEN_DIRS for p in parts):
        return True
    return any(fnmatch.fnmatch(parts[-1], m) for m in FORBIDDEN_NAMES)


def files(repo) -> list:
    """→ sorted [(source_abs, target_rel)] from the repo's positive list."""
    path = os.path.join(repo, LIST)
    if not os.path.isfile(path):
        raise PackageError(f"{repo}: no {LIST} — the app says what goes into its package")
    listed = paket_bauen.liste_lesen(path)
    for source, target in listed:
        if forbidden(source.rstrip("/")) or forbidden(target.rstrip("/")):
            raise PackageError(f"never in a package: {source}")
    try:
        pairs = paket_bauen.dateien(repo, listed, guard=forbidden)
    except paket_bauen.PaketFehler as e:
        raise PackageError(str(e))
    return pairs


def manifest(repo, pairs) -> dict:
    if not any(target == "app.toml" for _, target in pairs):
        raise PackageError("app.toml is not in the package list")
    try:
        with open(os.path.join(repo, "app.toml"), "rb") as f:
            m = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise PackageError(f"app.toml unreadable: {e}")
    name, version = str(m.get("name") or ""), str(m.get("version") or "")
    if not NAME.match(name):
        raise PackageError(f"app.toml: name {name!r} is not a valid app name")
    if not VERSION.match(version):
        raise PackageError(f"app.toml: version {version!r} missing or invalid")
    return m


def build(repo, target=None) -> tuple:
    """→ (path of the package, {name, version, sha256, size})."""
    repo = os.path.abspath(repo)
    pairs = files(repo)
    m = manifest(repo, pairs)
    name, version = m["name"], m["version"]
    top = f"{name}-{version}"
    target = os.path.abspath(target or os.path.join(repo, "dist"))
    os.makedirs(target, exist_ok=True)

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for source, rel in pairs:
            info = tar.gettarinfo(source, arcname=f"{top}/{rel}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = MTIME
            info.mode = 0o755 if info.mode & 0o111 else 0o644
            with open(source, "rb") as f:
                tar.addfile(info, f)
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    data = packed.getvalue()

    path = os.path.join(target, top + ".tar.gz")
    with open(path, "wb") as f:
        f.write(data)
    info = {"name": name, "version": version, "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data)}
    with open(os.path.join(target, top + ".json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
        f.write("\n")
    return path, info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", help="the app's repository (with app.toml and paket.txt)")
    ap.add_argument("--target", help="instead of <repo>/dist/")
    a = ap.parse_args(argv)
    try:
        path, info = build(a.repo, a.target)
    except PackageError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{path}  ({info['size'] / 1e6:.2f} MB, sha256 {info['sha256'][:16]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
