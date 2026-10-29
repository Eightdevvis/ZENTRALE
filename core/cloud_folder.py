# core/cloud_folder.py
#
# The cloud folder (app `cloud_folder`, memory/hub/cloud_folder.md): one
# visible folder in the home directory, ~/Zentrale/Cloud, where anything can
# be dropped. It syncs through the normal sync over the Mitte — no second
# sync system. Sasha, 2026-10-29: "ne allg cloud app für zentrale, wo man
# einfach nen ordner in den files kriegt der als die allg cloud fungiert …
# dann kann ich da random shit reindumpen."
#
# In the sync namespace the folder is `data/cloud/<path inside>` (like the
# Ablage is `data/ablage/…`, core/abgleich_auswahl.py AUSSEN); WHERE it lives
# on this device is said here. Setting `cloud_folder_dir` (env
# ZENTRALE_CLOUD_FOLDER_DIR) moves it — a machine-level path, may differ per
# device.
#
# Foundation (layer 1, memory/system/bauplan_kern.md): stdlib + ai_config
# only, so the TUI may import it too.

import os

import ai_config

DEFAULT = "~/Zentrale/Cloud"
SETTING = "cloud_folder_dir"
PREFIX = "data/cloud"
PATTERN = PREFIX + "/**"

# Folders that are never synced, anywhere below the cloud folder: version
# control, dependency trees, caches, trash. They are big, rebuildable and
# change all the time (a .git synced file by file would also break the repo
# on the other side). Compared by exact name.
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".cache", ".gradle", ".idea",
    ".Trash", ".Trashes", ".Trash-1000", "$RECYCLE.BIN", ".DS_Store",
})
# Files that are never data: OS litter, editor swap/lock files, downloads
# still in progress.
SKIP_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini", ".directory"})
SKIP_SUFFIXES = (".part", ".crdownload", ".download", ".swp", ".swo", ".tmp", "~")
SKIP_PREFIXES = (".~lock.", "~$", ".#")


def root() -> str:
    """The folder the user sees (absolute)."""
    own = str(ai_config.setting(SETTING) or "").strip() or DEFAULT
    return os.path.abspath(os.path.expanduser(own))


def skip_dir(name: str) -> bool:
    return name in SKIP_DIRS


def skip_file(name: str) -> bool:
    return (name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES)
            or name.startswith(SKIP_PREFIXES))


def excluded(inside: str) -> bool:
    """Is a path inside the cloud folder ("a/b/c.txt", forward slashes) left
    out of the sync? Also refuses anything that could escape the folder
    ("..", empty or absolute parts) — a path from the cloud is only data."""
    parts = inside.split("/")
    if not inside or inside.startswith("/") or any(p in ("", ".", "..") for p in parts):
        return True
    return any(skip_dir(p) for p in parts[:-1]) or skip_file(parts[-1])
