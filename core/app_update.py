# core/app_update.py
#
# Updating the extracted apps installed from the store (building kit step
# 12, memory/hub/building_kit_plan.md 3.2/3.3): an extracted app is its own
# repository (budget today; tutor and map once they come through the store,
# memory/open/store_tutor_map_migration.md). The bundle (BUNDLE.json in the
# package) lists them without a version: they follow their repository. So the
# automatic update (`zentrale update --automatic`, the daily timer) moves each
# installed checkout forward — fast-forward only, never over local changes —
# and skips every app the node HOLDS (app_register.holds, set in the store).
#
# No terminal, no print: zentrale_cli/aktualisieren.py reports. Foundation
# (layer 1): app_register + git.

import os
import subprocess

import app_register

GIT_TIME = 300


def _git(folder, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0",
               GIT_SSH_COMMAND=os.environ.get("GIT_SSH_COMMAND") or "ssh -o BatchMode=yes")
    try:
        r = subprocess.run(["git", "-C", folder, *args], env=env, capture_output=True,
                           text=True, timeout=GIT_TIME, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, "git is missing on this device"
    except subprocess.TimeoutExpired:
        return 124, "git took too long"


def head(folder) -> str:
    rc, out = _git(folder, "rev-parse", "HEAD")
    return out if rc == 0 else ""


def update_one(entry) -> dict:
    """→ {"name", "result": held|updated|current|skipped|failed, "text"}."""
    name, folder = entry["name"], entry.get("ordner") or ""
    if app_register.held(name):
        return {"name": name, "result": "held", "text": ""}
    if not os.path.isdir(os.path.join(folder, ".git")):
        return {"name": name, "result": "skipped", "text": "not a git checkout"}
    rc, out = _git(folder, "status", "--porcelain", "--untracked-files=no")
    if rc != 0 or out:
        return {"name": name, "result": "skipped", "text": out.splitlines()[0] if out else "git status failed"}
    before = head(folder)
    rc, out = _git(folder, "pull", "--ff-only", "--quiet")
    if rc != 0:
        return {"name": name, "result": "failed", "text": (out.splitlines() or ["?"])[-1][:300]}
    return {"name": name, "result": "updated" if head(folder) != before else "current", "text": ""}


def update_installed() -> list:
    """Every app installed from the store on this node, in name order."""
    return [update_one(e) for e in app_register.alle()]
