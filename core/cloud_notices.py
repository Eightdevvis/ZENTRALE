# core/cloud_notices.py
#
# What the cloud told this device on the side, kept so `zentrale status`,
# `devices`, the TUI and later Schematix can show it without asking the
# network (memory/hub/building_kit_plan.md, build steps 7 and 8):
#
#   insecure  this release is marked insecure: the answers carried
#             `Deprecation: @<unix seconds>` (RFC 9745) and
#             `Link: <advisory>; rel="deprecation"`. Sync keeps working —
#             support is forever; the owner decides (update or remove).
#   removed   this device was removed from the account (401 device_removed):
#             the automatic sync stays quiet, `status` says why. Logging in
#             again clears it.
#
# cloud_api.Client calls observe() on every answer. One small JSON file in
# the state folder (same folder as the cloud usage cache, setting
# `nutzung_dir`); written only when something changes. No terminal, no
# network, never raises.

import datetime
import json
import os
import re

import ai_config
import dateien

RELEASE_HEADER = "Zentrale-Release"
_DEPRECATION = re.compile(r"^@(-?\d+)$")
_LINK = re.compile(r'<([^>]*)>\s*;[^,]*rel="?deprecation"?', re.I)
_release = None


def release() -> str:
    """The version this program reports (core/knoten.fassung, read once)."""
    global _release
    if _release is None:
        import knoten
        _release = knoten.fassung()
    return _release


def path() -> str:
    own = ai_config.setting("nutzung_dir")
    if own:
        base = os.path.abspath(os.path.expanduser(str(own)))
    else:
        base = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                            "zentrale")
    return os.path.join(base, "cloud_notices.json")


def _read() -> dict:
    try:
        with open(path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d: dict):
    try:
        os.makedirs(os.path.dirname(path()), exist_ok=True)
        dateien.json_schreiben(path(), d)
    except OSError:
        pass


def _header(headers, name):
    try:
        return (headers.get(name) or "").strip() if headers is not None else ""
    except AttributeError:
        return ""


def parse_deprecation(headers):
    """→ {since: ISO date-time, link: url|None} or None (RFC 9745 headers)."""
    m = _DEPRECATION.match(_header(headers, "Deprecation"))
    if not m:
        return None
    since = datetime.datetime.fromtimestamp(int(m.group(1)), datetime.timezone.utc)
    link = _LINK.search(_header(headers, "Link"))
    return {"since": since.isoformat(timespec="seconds"), "link": link.group(1) if link else None}


def observe(status: int, code: str, headers):
    """Called by cloud_api for every answer (also errors). Never raises."""
    try:
        d = _read()
        new = dict(d)
        dep = parse_deprecation(headers)
        if dep:
            new["insecure"] = dict(dep, version=release())
        else:
            new.pop("insecure", None)
        if code == "device_removed":
            new.setdefault("removed", datetime.datetime.now(datetime.timezone.utc)
                           .isoformat(timespec="seconds"))
        if new != d:
            _write(new)
    except Exception:   # noqa: BLE001 — a side note must never break a request
        pass


def insecure():
    """{since, link, version} when THIS release was reported insecure, else None.
    After an update the old note no longer counts."""
    i = _read().get("insecure")
    return i if isinstance(i, dict) and i.get("version") == release() else None


def removed():
    """ISO time this device learned it was removed, else None."""
    r = _read().get("removed")
    return r if isinstance(r, str) else None


def clear_removed():
    """After a new login (core/konto.py) the device is back."""
    d = _read()
    if d.pop("removed", None) is not None:
        _write(d)
