"""`zentrale dev` — the developer installer mode (memory/hub/building_kit_plan.md
5.4, memory/betrieb/dev_mode.md). Only the front: words in, texts out. The
work is in devkit/ (checkout only, never in the package), so in an installed
hub this command just says it needs a developer checkout.

Each subcommand is one entry in COMMANDS: (handler, fewest words, most words).
"""

import os

from zentrale_cli import WURZEL
from zentrale_cli.aktualisieren import kanal
from zentrale_cli.texte import t


def _devkit():
    try:
        from devkit import guard, profiles, states, workspace
    except ImportError:
        return None
    return guard, profiles, states, workspace


def _options(words, allowed):
    """['--state', 'x', 'name'] → ({'state': 'x'}, ['name']) or None (unknown option)."""
    opts, rest, i = {}, [], 0
    while i < len(words):
        w = words[i]
        if w.startswith("--"):
            key = w[2:]
            if key not in allowed or i + 1 >= len(words):
                return None
            opts[key], i = words[i + 1], i + 2
        else:
            rest.append(w)
            i += 1
    return opts, rest


def _say_step(term):
    return lambda key, **values: term.sag(t(key, **values), "blass")


# ── Subcommands ────────────────────────────────────────────────────────

def cmd_overview(term, kit, ws, words):
    term.sag(t("dev_title"), "fett")
    term.sag(t("dev_root", root=ws.root), "blass")
    cmd_list(term, kit, ws, [])
    term.sag()
    for line in t("dev_usage"):
        term.sag("  " + line)
    return 0


def cmd_list(term, kit, ws, words):
    _g, profiles, _s, _w = kit
    found = profiles.all_profiles(ws)
    if not found:
        term.sag(t("dev_none"))
        return 0
    for p in found:
        d = p.read()
        term.sag(t("dev_line", name=p.name, state=d["state"], release=d["release"],
                   installed=p.installed_release() or "—", account=d.get("account") or "—",
                   online=t("dev_online") if d.get("online", True) else t("dev_offline"))
                 + (t("dev_broken") if d.get("broken") else ""))
    return 0


def cmd_states(term, kit, ws, words):
    _g, _p, states, _w = kit
    for s in states.STATES:
        missing = states.missing(s)
        line = t("dev_state_line", state=s.name, steps=" → ".join(s.steps))
        if missing:
            line += t("dev_state_later", planned=s.planned or "?")
        term.sag("  " + line, "blass" if missing else "")
    term.sag(t("dev_states_release"), "blass")
    return 0


def cmd_new(term, kit, ws, words):
    _g, profiles, _s, _w = kit
    parsed = _options(words, {"state", "release", "account"})
    if not parsed or len(parsed[1]) != 1:
        return _usage(term)
    opts, (name,) = parsed
    params = {"account": opts["account"]} if "account" in opts else {}
    p = profiles.create(ws, name, opts.get("state", "fresh"), opts.get("release"), params,
                        say=_say_step(term))
    term.sag(t("dev_made", name=p.name, state=p.read()["state"], release=p.installed_release()), "gut")
    return 0


def cmd_reset(term, kit, ws, words):
    _g, profiles, _s, _w = kit
    p = profiles.reset(ws, words[0], say=_say_step(term))
    term.sag(t("dev_reset_ok", name=p.name, state=p.read()["state"]), "gut")
    return 0


def cmd_delete(term, kit, ws, words):
    _g, profiles, _s, _w = kit
    profiles.delete(ws, words[0])
    term.sag(t("dev_deleted", name=words[0]), "gut")
    return 0


def cmd_shell(term, kit, ws, words):
    _g, profiles, _s, _w = kit
    p = profiles.Profile(ws, words[0])
    p.read()
    term.sag(t("dev_shell", name=p.name), "blass")
    with ws.cloud():
        return p.interactive([os.environ.get("SHELL") or "bash"])


def cmd_run(term, kit, ws, words):
    _g, profiles, _s, _w = kit
    p = profiles.Profile(ws, words[0])
    p.read()
    with ws.cloud():
        return p.interactive([p.command, *words[1:]])


def cmd_update(term, kit, ws, words):
    _g, profiles, states, _w = kit
    p = profiles.Profile(ws, words[0])
    p.read()
    before, after, r = states.play_update(p, words[1])
    term.sag(t("dev_update", name=p.name, before=before or "—", after=after), "fett")
    for line in (r.stdout + r.stderr).rstrip().splitlines():
        term.sag("  " + line)
    return r.returncode


def cmd_release(term, kit, ws, words):
    if words:
        path = ws.build_release(words[0])
        term.sag(t("dev_release_built", path=path), "gut")
        return 0
    have = ws.release_list()
    term.sag(t("dev_releases", liste=", ".join(have)) if have else t("dev_releases_none"))
    return 0


def cmd_cloud_reset(term, kit, ws, words):
    guard = kit[0]
    for name in ("state.json", "serve"):
        path = os.path.join(ws.cloud_dir, name)
        if os.path.exists(path):
            os.remove(guard.check_inside(path, ws.root))
    term.sag(t("dev_cloud_reset"), "gut")
    return 0


# name → (handler, fewest words after the name, most words; None = any number)
COMMANDS = {
    "": (cmd_overview, 0, 0),
    "list": (cmd_list, 0, 0),
    "states": (cmd_states, 0, 0),
    "new": (cmd_new, 1, None),
    "reset": (cmd_reset, 1, 1),
    "delete": (cmd_delete, 1, 1),
    "shell": (cmd_shell, 1, 1),
    "run": (cmd_run, 1, None),
    "update": (cmd_update, 2, 2),
    "release": (cmd_release, 0, 1),
    "cloud-reset": (cmd_cloud_reset, 0, 0),
}


def _usage(term):
    term.fehler(t("dev_bad_use"))
    return 2


def dev(term, args=()):
    """`zentrale dev [subcommand …]`."""
    kit = _devkit()
    if kit is None or kanal(WURZEL) != "dev":
        term.sag(t("dev_only_checkout"))
        return 1
    guard, profiles, _states, workspace = kit
    words = list(args)
    name = words.pop(0) if words else ""
    entry = COMMANDS.get(name)
    if entry is None:
        return _usage(term)
    handler, fewest, most = entry
    if len(words) < fewest or (most is not None and len(words) > most):
        return _usage(term)
    try:
        ws = workspace.Workspace()
        return handler(term, kit, ws, words)
    except (guard.GuardError, profiles.DevError) as e:
        term.fehler(t(e.key, **e.values))
        return 1
