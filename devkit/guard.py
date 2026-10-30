"""The one guard of `zentrale dev`: never touch the real installation.

"Real" is computed from the account's home in the user table (pwd), never
from $HOME or ZENTRALE_* — those are exactly what a profile bends. The dev
root may neither lie inside a real place nor contain one (a reset deletes
folders), nor lie inside a checkout. Every environment a profile hands to a
subprocess is checked too: its HOME, its fake systemd and every path-valued
ZENTRALE_*/XDG_* variable must point into the dev root.
"""

import os
import pwd

# Variables that point at a read-only place outside the dev root on purpose.
OUTSIDE_OK = {"ZENTRALE_REUSE_VENV"}


class GuardError(Exception):
    """Refused: this would reach the real installation. args[0] = text key."""

    def __init__(self, key, **values):
        super().__init__(key)
        self.key, self.values = key, values


def real_home() -> str:
    return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)


def real_places(checkout=None) -> list:
    """Everything a real ZENTRALE on this account lives in."""
    h = real_home()
    places = [os.path.join(h, ".local", "share", "zentrale"),
              os.path.join(h, ".config", "zentrale"),
              os.path.join(h, ".config", "systemd", "user"),
              os.path.join(h, ".local", "bin", "zentrale")]
    if checkout:
        places.append(os.path.join(os.path.realpath(checkout), "data"))
    return [os.path.realpath(p) for p in places]


def _inside(path, folder) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def check_root(root, checkout=None) -> str:
    """→ the dev root as a real path, or GuardError."""
    r = os.path.realpath(root)
    if r in ("/", real_home()):
        raise GuardError("dev_guard_root", path=r)
    for place in real_places(checkout):
        if _inside(r, place) or _inside(place, r):
            raise GuardError("dev_guard_root", path=r)
    if checkout and _inside(r, os.path.realpath(checkout)):
        raise GuardError("dev_guard_root", path=r)
    return r


def check_inside(path, root) -> str:
    """A path the dev mode writes or deletes must lie inside the dev root."""
    p, r = os.path.realpath(path), os.path.realpath(root)
    if not _inside(p, r) or p == r:
        raise GuardError("dev_guard_path", path=p)
    return p


def check_env(env, root):
    """The environment of a profile subprocess points only into the dev root."""
    r = os.path.realpath(root)
    for key in ("HOME", "ZENTRALE_SYSTEMCTL", "ZENTRALE_SYSTEMD_USER_DIR"):
        if not env.get(key) or not _inside(os.path.realpath(env[key]), r):
            raise GuardError("dev_guard_env", variable=key, path=env.get(key, ""))
    for key, value in env.items():
        if key in OUTSIDE_OK or not key.startswith(("ZENTRALE_", "XDG_")):
            continue
        if value.startswith(os.sep) and not _inside(os.path.realpath(value), r):
            raise GuardError("dev_guard_env", variable=key, path=value)
