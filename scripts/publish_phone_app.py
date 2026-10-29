#!/usr/bin/env python3
"""Publish a new version of the phone app to the ZENTRALE cloud (self-update).

    publish_phone_app.py status              installed pubspec version vs. the published one
    publish_phone_app.py bump [--name X.Y.Z] raise the version code in mobile/pubspec.yaml
    publish_phone_app.py publish [--notes TEXT] [--apk PATH] [--build] [--dry-run]

The order is: bump → build the release APK (Sasha, `flutter build apk --release`
in mobile/; `--build` does it here, never by default — the laptop has 3.8 GB RAM)
→ publish. `publish` refuses an APK that was built from another version code,
one signed with the debug key, and a version code that is not higher than the
published one. It uploads the APK first and the manifest last (the cloud only
accepts a manifest whose APK is stored with the same size and SHA-256).

Uses the session of this computer (core/konto.py, `zentrale login`); only
operator accounts (cloud var BETREIBER_NAMEN) may publish.
Docs: memory/system/zen_mobile.md "Self-update", memory/betrieb/phone_app_release.md.
"""

import argparse
import gettext
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOBILE = os.path.join(ROOT, "mobile")
PUBSPEC = os.path.join(MOBILE, "pubspec.yaml")
# Flutter copies the APK here; AGP writes output-metadata.json next to its own copy.
APK = os.path.join(MOBILE, "build", "app", "outputs", "flutter-apk", "app-release.apk")
METADATA = os.path.join(MOBILE, "build", "app", "outputs", "apk", "release", "output-metadata.json")
UPLOAD_TIMEOUT = 900
MAX_CODE = 2_100_000_000

_ = gettext.translation("zentrale", os.path.join(ROOT, "locale"), fallback=True).gettext

_VERSION = re.compile(r"^version:\s*([0-9A-Za-z][0-9A-Za-z._-]*)(?:\+(\d+))?\s*$", re.M)


class PublishError(Exception):
    """A sentence for the human (translated)."""


# ── pubspec ────────────────────────────────────────────────────────────

def read_version(text: str) -> tuple:
    """`version: 0.2.0+7` → ("0.2.0", 7). Without `+N` Flutter uses 1."""
    m = _VERSION.search(text)
    if not m:
        raise PublishError(_("mobile/pubspec.yaml has no 'version:' line."))
    return m.group(1), int(m.group(2) or 1)


def write_version(text: str, name: str, code: int) -> str:
    if not 1 <= code <= MAX_CODE:
        raise PublishError(_("The version code must be between 1 and %d.") % MAX_CODE)
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]{0,63}", name):
        raise PublishError(_("'%s' is not a valid version name.") % name)
    return _VERSION.sub(f"version: {name}+{code}", text, count=1)


def next_code(local: int, published: int) -> int:
    return max(local, published) + 1


# ── the APK ────────────────────────────────────────────────────────────

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def built_code(metadata_path: str = METADATA):
    """The versionCode AGP wrote for the release APK, or None if unknown."""
    try:
        with open(metadata_path, encoding="utf-8") as f:
            d = json.load(f)
        return int(d["elements"][0]["versionCode"])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def debug_signed(apk: str, run=subprocess.run):
    """True if signed with the Android debug key, None if it cannot be checked."""
    if not shutil.which("keytool"):
        return None
    try:
        out = run(["keytool", "-printcert", "-jarfile", apk], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return "CN=Android Debug" in out.stdout


def check_apk(apk: str, code: int, pubspec_path: str = PUBSPEC, metadata_path: str = METADATA,
              run=subprocess.run) -> list:
    """Raise PublishError if this APK must not be published; return warnings."""
    warnings = []
    if not os.path.isfile(apk):
        raise PublishError(_("No APK at %s — build it first (flutter build apk --release in mobile/).") % apk)
    built = built_code(metadata_path)
    if built is None:
        warnings.append(_("Cannot read the build's version code; checking the file date instead."))
        if os.path.getmtime(apk) < os.path.getmtime(pubspec_path):
            raise PublishError(_("The APK is older than mobile/pubspec.yaml — build it again."))
    elif built != code:
        raise PublishError(_("The APK was built with version code %(built)d, pubspec.yaml says %(code)d — "
                             "build it again.") % {"built": built, "code": code})
    signed = debug_signed(apk, run)
    if signed:
        raise PublishError(_("The APK is signed with the debug key. Phones could never update from it to a "
                             "release-signed APK. Check ~/.config/zentrale/android/key.properties and build again."))
    if signed is None:
        warnings.append(_("Could not check the APK signature (keytool missing?)."))
    return warnings


# ── the cloud ──────────────────────────────────────────────────────────

def _client():
    sys.path.insert(0, os.path.join(ROOT, "core"))
    import konto  # noqa: E402 — core/ is only on the path for this script
    c = konto.client()
    if not c.token:
        raise PublishError(_("Not logged in on this computer. Run 'zentrale login' first."))
    return c


def published(client) -> dict:
    """The current manifest, or {} if nothing is published yet."""
    import cloud_api
    try:
        return client.get("/v1/phone/release")
    except cloud_api.CloudFehler as e:
        if e.status == 404:
            return {}
        raise PublishError(str(e)) from None


def upload(client, apk: str, name: str, code: int, notes: str) -> dict:
    import cloud_api
    sha = sha256_file(apk)
    with open(apk, "rb") as f:
        data = f.read()
    manifest = {"version": name, "version_code": code, "sha256": sha, "size": len(data), "notes": notes}
    old_timeout, client.zeit = client.zeit, UPLOAD_TIMEOUT
    try:
        client.roh("PUT", f"/v1/phone/release/{code}.apk", abfrage={"sha256": sha}, roh_body=data)
        client.zeit = old_timeout
        return client.put("/v1/phone/release", manifest)
    except cloud_api.CloudFehler as e:
        raise PublishError(str(e)) from None
    finally:
        client.zeit = old_timeout


# ── commands ───────────────────────────────────────────────────────────

def cmd_status(args, client_factory=_client):
    with open(PUBSPEC, encoding="utf-8") as f:
        name, code = read_version(f.read())
    m = published(client_factory())
    print(_("pubspec.yaml: %(name)s (version code %(code)d)") % {"name": name, "code": code})
    if m:
        print(_("published:    %(name)s (version code %(code)d), %(at)s")
              % {"name": m.get("version"), "code": m.get("version_code"), "at": m.get("published_at")})
    else:
        print(_("published:    nothing yet"))


def cmd_bump(args, client_factory=_client, pubspec_path=PUBSPEC):
    with open(pubspec_path, encoding="utf-8") as f:
        text = f.read()
    name, code = read_version(text)
    remote = 0 if args.offline else int(published(client_factory()).get("version_code") or 0)
    new_code = next_code(code, remote)
    new_name = args.name or name
    with open(pubspec_path, "w", encoding="utf-8") as f:
        f.write(write_version(text, new_name, new_code))
    print(_("mobile/pubspec.yaml is now %(name)s+%(code)d. Next: build the release APK, then publish.")
          % {"name": new_name, "code": new_code})
    return new_name, new_code


def cmd_publish(args, client_factory=_client, pubspec_path=PUBSPEC, metadata_path=METADATA,
                run=subprocess.run):
    with open(pubspec_path, encoding="utf-8") as f:
        name, code = read_version(f.read())
    apk = args.apk or APK
    if args.build:
        if run(["flutter", "build", "apk", "--release"], cwd=MOBILE).returncode != 0:
            raise PublishError(_("flutter build failed."))
    for w in check_apk(apk, code, pubspec_path, metadata_path, run):
        print(_("Warning: %s") % w, file=sys.stderr)
    client = client_factory()
    remote = int(published(client).get("version_code") or 0)
    if code <= remote:
        raise PublishError(_("Version code %(code)d is not higher than the published %(remote)d — run 'bump' "
                             "and build again.") % {"code": code, "remote": remote})
    if args.dry_run:
        print(_("Dry run: would publish %(name)s (version code %(code)d), %(size)d bytes, sha256 %(sha)s.")
              % {"name": name, "code": code, "size": os.path.getsize(apk), "sha": sha256_file(apk)})
        return None
    m = upload(client, apk, name, code, args.notes or "")
    print(_("Published %(name)s (version code %(code)d). Phones see it on their next start.")
          % {"name": m.get("version"), "code": m.get("version_code")})
    return m


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=_("Publish the phone app to the ZENTRALE cloud."))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help=_("pubspec version vs. the published release"))
    b = sub.add_parser("bump", help=_("raise the version code in mobile/pubspec.yaml"))
    b.add_argument("--name", help=_("new version name, e.g. 0.2.0 (default: keep)"))
    b.add_argument("--offline", action="store_true", help=_("do not ask the cloud for its version code"))
    u = sub.add_parser("publish", help=_("upload the built release APK and its manifest"))
    u.add_argument("--notes", default="", help=_("what is new (shown in the app)"))
    u.add_argument("--apk", help=_("path of the APK (default: the Flutter release output)"))
    u.add_argument("--build", action="store_true", help=_("run 'flutter build apk --release' first (needs RAM)"))
    u.add_argument("--dry-run", action="store_true", help=_("check everything, upload nothing"))
    args = p.parse_args(argv)
    try:
        {"status": cmd_status, "bump": cmd_bump, "publish": cmd_publish}[args.command](args)
    except PublishError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
