"""A fake `systemctl --user` for tests and `zentrale dev` profiles.

`make(folder)` writes an executable `systemctl` into `folder` that
zentrale_cli/timer.py calls through ZENTRALE_SYSTEMCTL. It keeps state like the
real one, as far as the timers need it: a unit can only be enabled when its
file is in the unit folder (ZENTRALE_SYSTEMD_USER_DIR), `enable --now` makes it
active, `disable --now` stops it, `is-enabled`/`is-active` answer with the real
words and exit codes. Every call is one line in `systemctl.log`
("--user enable --now a.timer b.timer"), so tests can read what was asked.

Nothing is ever run: the fake never starts a service. A test or a dev profile
that wants "the sync timer fired" runs the ExecStart line itself.
"""

import json
import os
import sys

SCRIPT = '''#!{python} -I
# Fake systemctl --user, written by devkit/fake_systemd.py. Never runs anything.
import json, os, sys
STATE, LOG, UNITS = {state!r}, {log!r}, {units!r}
args = sys.argv[1:]
with open(LOG, "a", encoding="utf-8") as f:
    f.write(" ".join(args) + "\\n")
if args[:1] == ["--user"]:
    args = args[1:]
try:
    with open(STATE, encoding="utf-8") as f:
        s = json.load(f)
except (OSError, ValueError):
    s = {{"enabled": [], "active": []}}
cmd, rest = (args[0] if args else ""), args[1:]
now = "--now" in rest
units = [u for u in rest if not u.startswith("-")]
code = 0

def save():
    with open(STATE + ".neu", "w", encoding="utf-8") as f:
        json.dump(s, f)
    os.replace(STATE + ".neu", STATE)

if cmd in ("show-environment", "daemon-reload"):
    pass
elif cmd in ("enable", "reenable"):
    for u in units:
        if not os.path.exists(os.path.join(UNITS, u)):
            print(f"Failed to enable unit: Unit file {{u}} does not exist.", file=sys.stderr)
            sys.exit(1)
    for u in units:
        if u not in s["enabled"]:
            s["enabled"].append(u)
        if now and u not in s["active"]:
            s["active"].append(u)
    save()
elif cmd == "disable":
    s["enabled"] = [u for u in s["enabled"] if u not in units]
    if now:
        s["active"] = [u for u in s["active"] if u not in units]
    save()
elif cmd == "is-enabled":
    on = all(u in s["enabled"] for u in units)
    print("enabled" if on else "disabled")
    code = 0 if on else 1
elif cmd == "is-active":
    on = all(u in s["active"] for u in units)
    if "--quiet" not in rest:
        print("active" if on else "inactive")
    code = 0 if on else 3
elif cmd == "try-restart":
    code = 0
elif cmd == "show":
    prop = rest[rest.index("-p") + 1] if "-p" in rest else ""
    print({{"NextElapseUSecRealtime": "n/a", "Result": "success"}}.get(prop, ""))
else:
    print(f"fake systemctl: unknown command {{cmd!r}}", file=sys.stderr)
    code = 1
sys.exit(code)
'''


class FakeSystemd:
    """Paths and state of one fake systemd (a test's or a dev profile's)."""

    def __init__(self, folder):
        self.folder = os.path.abspath(str(folder))
        self.program = os.path.join(self.folder, "systemctl")
        self.units = os.path.join(self.folder, "user")
        self.log = os.path.join(self.folder, "systemctl.log")
        self.state = os.path.join(self.folder, "state.json")

    def env(self) -> dict:
        """What zentrale_cli/timer.py needs to use this fake."""
        return {"ZENTRALE_SYSTEMCTL": self.program, "ZENTRALE_SYSTEMD_USER_DIR": self.units}

    def calls(self) -> list:
        try:
            with open(self.log, encoding="utf-8") as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def clear_log(self):
        if os.path.exists(self.log):
            os.remove(self.log)

    def _read(self) -> dict:
        try:
            with open(self.state, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"enabled": [], "active": []}

    def enabled(self) -> list:
        return list(self._read()["enabled"])

    def active(self) -> list:
        return list(self._read()["active"])

    def set_active(self, unit, on=True):
        """Mark a unit running (e.g. the backend) without the timers."""
        s = self._read()
        s["active"] = [u for u in s["active"] if u != unit] + ([unit] if on else [])
        with open(self.state, "w", encoding="utf-8") as f:
            json.dump(s, f)

    def unit_files(self) -> list:
        return sorted(os.listdir(self.units)) if os.path.isdir(self.units) else []


def make(folder, python=None) -> FakeSystemd:
    """Write the fake into `folder` (created) → FakeSystemd. Idempotent."""
    fake = FakeSystemd(folder)
    os.makedirs(fake.folder, exist_ok=True)
    text = SCRIPT.format(python=python or sys.executable, state=fake.state,
                         log=fake.log, units=fake.units)
    with open(fake.program, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(fake.program, 0o755)
    return fake
