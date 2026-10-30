"""Profiles of `zentrale dev` (memory/hub/building_kit_plan.md 5.4): each one
an isolated ZENTRALE home on this machine — its own HOME (so its own
~/.local/share/zentrale, ~/.config/zentrale, ~/.local/bin/zentrale), its own
fake systemd, the dev root's fake cloud, its own device name.

A profile is installed and driven by the REAL programs: deploy/install.sh,
then the profile's own `zentrale` (setup, update, timers …). Only the edges
are fake (cloud, systemd, the venv is linked instead of built). What state a
profile starts in is data — devkit/states.py.

    <root>/profiles/<name>/profile.json   name, state, params, release, online
    <root>/profiles/<name>/home/          the profile's HOME
    <root>/profiles/<name>/systemd/       its fake systemd (devkit/fake_systemd.py)
"""

import json
import os
import re
import shutil
import subprocess
import sys

from devkit import fake_systemd, guard
from devkit.workspace import OFFLINE_CLOUD

NAME = re.compile(r"^[a-z][a-z0-9._-]{2,31}$")     # also a valid account and device name
PASSWORD = "dev-password-only"                      # every dev account; never a real one
MARKER = "profile.json"


class DevError(Exception):
    """A dev command cannot go on. key/values → a text in zentrale_cli/texte.py."""

    def __init__(self, key, **values):
        super().__init__(key)
        self.key, self.values = key, values


class Profile:
    def __init__(self, ws, name):
        if not NAME.match(name or ""):
            raise DevError("dev_bad_name", name=name)
        self.ws, self.name = ws, name
        self.dir = os.path.join(ws.profiles, name)
        self.home = os.path.join(self.dir, "home")
        self.fake = fake_systemd.FakeSystemd(os.path.join(self.dir, "systemd"))

    # ── Settings of the profile ────────────────────────────────────────
    @property
    def exists(self) -> bool:
        return os.path.exists(os.path.join(self.dir, MARKER))

    def read(self) -> dict:
        try:
            with open(os.path.join(self.dir, MARKER), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            raise DevError("dev_no_profile", name=self.name) from None

    def write(self, data):
        with open(os.path.join(self.dir, MARKER), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def update(self, **changes):
        d = self.read()
        d.update(changes)
        self.write(d)

    # ── Paths inside ───────────────────────────────────────────────────
    @property
    def hub(self) -> str:
        return os.path.join(self.home, ".local", "share", "zentrale")

    @property
    def command(self) -> str:
        return os.path.join(self.home, ".local", "bin", "zentrale")

    def installed_release(self) -> str:
        link = os.path.join(self.hub, "hub", "aktuell")
        return os.readlink(link) if os.path.islink(link) else ""

    # ── Environment and running things ─────────────────────────────────
    def env(self) -> dict:
        """The world the profile's programs see. Inherited ZENTRALE_*/XDG_*,
        PYTHONPATH, the session bus and a venv are dropped: nothing from Sasha's
        shell or desktop reaches in, nothing from the profile reaches out."""
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("ZENTRALE_", "XDG_"))
                and k not in ("PYTHONPATH", "DBUS_SESSION_BUS_ADDRESS", "VIRTUAL_ENV", "TMUX")}
        if os.environ.get("ZENTRALE_LANG"):
            base["ZENTRALE_LANG"] = os.environ["ZENTRALE_LANG"]
        d = self.read()
        env = dict(base,
                   HOME=self.home,
                   XDG_CONFIG_HOME=os.path.join(self.home, ".config"),
                   XDG_DATA_HOME=os.path.join(self.home, ".local", "share"),
                   XDG_STATE_HOME=os.path.join(self.home, ".local", "state"),
                   XDG_CACHE_HOME=os.path.join(self.home, ".cache"),
                   PATH=os.path.join(self.home, ".local", "bin") + os.pathsep + base.get("PATH", ""),
                   ZENTRALE_CLOUD=self.ws.cloud_url() if d.get("online", True) else OFFLINE_CLOUD,
                   ZENTRALE_NODE_NAME=self.name,
                   ZENTRALE_REUSE_VENV=venv_of_this_python(),
                   ZENTRALE_DEV_PROFILE=self.name,
                   NO_COLOR=os.environ.get("NO_COLOR", ""),
                   **self.fake.env())
        if not env["NO_COLOR"]:
            del env["NO_COLOR"]
        guard.check_env(env, self.ws.root)
        return env

    def run(self, args, answers=None, timeout=300) -> subprocess.CompletedProcess:
        """Run a program inside the profile (cwd = its HOME), output captured."""
        env = self.env()
        return subprocess.run(args, env=env, cwd=self.home, capture_output=True, text=True,
                              input=answers, timeout=timeout,
                              stdin=None if answers is not None else subprocess.DEVNULL)

    def zentrale(self, *args, answers=None, timeout=300) -> subprocess.CompletedProcess:
        """The profile's own installed `zentrale`."""
        if not os.path.exists(self.command):
            raise DevError("dev_not_installed", name=self.name)
        return self.run([self.command, *args], answers=answers, timeout=timeout)

    def interactive(self, args) -> int:
        """A shell or command with the terminal attached (dev shell / dev run)."""
        return subprocess.call(args, env=self.env(), cwd=self.home)


def venv_of_this_python() -> str:
    """The venv `zentrale dev` runs in — every profile links it instead of
    building its own (ZENTRALE_REUSE_VENV in install.sh and `update`)."""
    if sys.prefix == sys.base_prefix:
        raise DevError("dev_no_venv")
    return sys.prefix


# ── Make, reset, delete ────────────────────────────────────────────────

def all_profiles(ws) -> list:
    return [Profile(ws, n) for n in sorted(os.listdir(ws.profiles))
            if NAME.match(n) and os.path.exists(os.path.join(ws.profiles, n, MARKER))]


def _wipe(p):
    if os.path.lexists(p.dir):
        guard.check_inside(p.dir, p.ws.profiles)
        shutil.rmtree(p.dir)


def create(ws, name, state="fresh", release=None, params=None, say=lambda *a, **k: None):
    """A new profile in `state` (devkit/states.py). An existing one is refused."""
    from devkit import states
    p = Profile(ws, name)
    if p.exists:
        raise DevError("dev_exists", name=name)
    plan = states.plan(state)                       # refuses unknown / not yet built states
    _wipe(p)                                        # leftovers of a broken earlier try
    os.makedirs(p.home)
    fake_systemd.make(p.fake.folder)
    p.write({"name": name, "state": state, "release": release or ws.current_release(),
             "params": dict(params or {}), "online": True})
    try:
        with ws.cloud():
            for step in plan:
                say("dev_step", step=step, name=name)
                states.STEPS[step](p, say)
    except Exception:
        p.update(broken=True)
        raise
    return p


def reset(ws, name, say=lambda *a, **k: None):
    """Back to the state it was made in, with the same settings."""
    p = Profile(ws, name)
    d = p.read()
    delete(ws, name)
    return create(ws, name, d["state"], d["release"], d.get("params"), say)


def delete(ws, name):
    p = Profile(ws, name)
    p.read()                                        # only real profiles
    _wipe(p)
