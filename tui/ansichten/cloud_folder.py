# tui/ansichten/cloud_folder.py
#
# The Cloud icon in the app wheel (memory/hub/cloud_folder.md, 2026-10-29):
# no view of its own — enter opens the cloud folder (~/Zentrale/Cloud) in the
# desktop's default file manager. Syncing it is the normal sync's job
# (core/abgleich.py); where the folder is, the backend says
# (GET /api/abgleich → cloud_folder, from core/cloud_folder.py) — the TUI
# imports nothing more from the core.
#
# Opened the freedesktop way (xdg-open, else gio; `open` on macOS), so it is
# the same on i3/X11 and sway/Wayland: whatever file manager is the default
# for folders (inode/directory). Only with a graphical session (DISPLAY /
# WAYLAND_DISPLAY) — otherwise xdg-open could start a text program inside
# this terminal and wreck the TUI; then only the path is shown. The phone
# app opens the same synced folder its own way; this file is the desktop.
#
# Started detached (own session, stdio to /dev/null): the file manager must
# not write into curses and must not die with the TUI.

import os
import shutil
import subprocess
import sys
import urllib.parse

from . import basis
from .translate import _

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def command(path, env=None, platform=None):
    """-> argv that opens `path` in the file manager. OSError with a readable
    reason if there is no way."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    if platform == "darwin":
        return ["open", path]
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        raise OSError(_("no graphical session here"))
    opener = shutil.which("xdg-open")
    if opener:
        return [opener, path]
    opener = shutil.which("gio")
    if opener:
        return [opener, "open", path]
    raise OSError(_("neither xdg-open nor gio is installed"))


def backend_is_local(url=None) -> bool:
    host = urllib.parse.urlsplit(url or basis.BASE_URL).hostname or ""
    return host in _LOCAL_HOSTS


def folder_path(api=None):
    """Where the cloud folder is (asked from the backend) or None."""
    try:
        d = (api or basis.api_call)("/api/abgleich")
    except Exception:       # noqa: BLE001 — offline backend is a message, not a crash
        return None
    p = (d or {}).get("cloud_folder")
    return p if isinstance(p, str) and p else None


def open_folder(u=None, api=None, popen=subprocess.Popen):
    """Open the cloud folder (create it first if it is missing). -> message,
    also put into the status line of `u`."""
    path = folder_path(api)
    if path is None:
        msg = _("Cloud folder: the backend is not reachable")
    elif not backend_is_local() and not os.path.isdir(path):
        msg = _("Cloud folder: it lives on the backend's machine ({path})").format(path=path)
    else:
        shown = path.replace(os.path.expanduser("~"), "~", 1)
        try:
            os.makedirs(path, exist_ok=True)
            popen(command(path), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, start_new_session=True)
            msg = _("Cloud folder opened: {path}").format(path=shown)
        except OSError as e:
            msg = _("Cloud folder: {path} ({reason})").format(path=shown, reason=e)
    if u is not None:
        u.bz.cmd_msg = msg
    return msg
