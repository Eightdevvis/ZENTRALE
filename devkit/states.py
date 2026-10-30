"""Start states of a `zentrale dev` profile — as data, not as if-chains.

A state is a list of step names. A step is one function in STEPS that moves
a profile one stage along the consumer journey (memory/hub/building_kit_plan.md
5.1), using the real programs wherever they exist. A new state is one line in
STATES; a new journey stage is one function in STEPS. A state whose steps are
not all built yet stays listed and says which build step brings it. The
setup wizard state takes params {"step": n} (`zentrale dev new --step n`).

"On an old release N" is not a state of its own: every state takes a release
(`--release N`), the install step installs exactly that tarball.
"""

import os
from dataclasses import dataclass

from devkit.profiles import PASSWORD, DevError


@dataclass(frozen=True)
class State:
    name: str
    steps: tuple
    planned: str = ""          # which build step brings a missing step ("" = all built)


STATES = (
    State("fresh", ("install",)),
    State("logged-in", ("install", "login")),
    State("offline", ("install", "login", "offline")),
    State("removed", ("install", "login", "removed")),
    State("wizard", ("install", "wizard")),
)


def by_name(name) -> State:
    for s in STATES:
        if s.name == name:
            return s
    raise DevError("dev_unknown_state", state=name, states=", ".join(s.name for s in STATES))


def missing(state) -> list:
    return [step for step in state.steps if step not in STEPS]


def plan(name) -> tuple:
    """The steps of a state, or DevError when it is unknown or not built yet."""
    s = by_name(name)
    if missing(s):
        raise DevError("dev_state_planned", state=s.name, steps=", ".join(missing(s)),
                       planned=s.planned or "?")
    return s.steps


# ── Steps ──────────────────────────────────────────────────────────────

def _check(r, key, **values):
    if r.returncode != 0:
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-12:])
        raise DevError(key, output=tail, **values)
    return r


def step_install(p, say):
    """deploy/install.sh of the checkout, as a consumer runs it: invite code,
    download from the (fake) cloud, unpack, link, keeper timers — before any login."""
    ws, d = p.ws, p.read()
    ws.serve(d["release"])
    script = os.path.join(ws.checkout, "deploy", "install.sh")
    _check(p.run(["bash", script, ws.new_invite_code()]), "dev_install_failed")


def _account_answers(p) -> tuple:
    """The typed answers of the wizard's account step: create the account (or
    log in when another profile already made it — a second device of it)."""
    ws, d = p.ws, p.read()
    account = d["params"].get("account") or p.name
    if ws.account_exists(account):
        return account, ["1", account, PASSWORD]
    return account, ["2", ws.new_invite_code(), account, PASSWORD, PASSWORD, "y"]


def wizard_answers(p, steps) -> tuple:
    """Answers for the first `steps` steps of the setup wizard
    (zentrale_cli/wizard.py STEPS): the account step types, every later step
    takes its default (Enter). → (account, lines)"""
    account, lines = _account_answers(p)
    return account, (lines + [""] * (steps - 1)) if steps > 0 else []


def step_login(p, say):
    """`zentrale setup` through the whole wizard, defaults everywhere."""
    account, lines = wizard_answers(p, 99)
    _check(p.zentrale("setup", answers="\n".join(lines) + "\n"), "dev_login_failed")
    p.update(account=account)


def step_wizard(p, say):
    """The setup wizard stands at step n (params {"step": n}, 0 = before the
    first question): `zentrale setup` answers the first n steps and stops
    there, as if the person closed the terminal. The next `zentrale setup`
    in the profile picks up at step n (the wizard remembers where it was)."""
    n = int(p.read()["params"].get("step") or 0)
    if n <= 0:
        return
    account, lines = wizard_answers(p, n)
    r = p.zentrale("setup", answers="\n".join(lines) + "\n")
    if r.returncode not in (0, 130):          # 130: stopped at step n by the end of input
        _check(r, "dev_login_failed")
    p.update(account=account)


def step_offline(p, say):
    """The profile's cloud address leads nowhere from now on."""
    p.update(online=False)


def step_removed(p, say):
    """What `zentrale devices remove` does on the server (build step 8,
    DELETE /v1/knoten/<name>): this device's sessions turn into removed ones
    and its description into a tombstone. Its next sync says it was removed."""
    import datetime
    removed = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with p.ws.cloud_edit() as z:
        for token in [t for t, s in z.sitzungen.items() if s[1] == p.name]:
            z.removed[token] = z.sitzungen.pop(token)
        for konto, nodes in z.knoten.items():
            if p.name in nodes:
                nodes[p.name] = dict(nodes[p.name], removed=removed, removed_by="dev")


STEPS = {
    "install": step_install,
    "login": step_login,
    "offline": step_offline,
    "removed": step_removed,
    "wizard": step_wizard,
}


# ── Playing an update ──────────────────────────────────────────────────

def play_update(p, to_release) -> tuple:
    """`zentrale update` inside the profile from its release to `to_release`
    (a local tarball, built from the checkout if missing), keeper included.
    → (from, to, CompletedProcess). Needs a logged-in profile, like the real one."""
    ws = p.ws
    before = p.installed_release()
    ws.serve(to_release)
    with ws.cloud():
        r = p.zentrale("update")
    return before, to_release, r
