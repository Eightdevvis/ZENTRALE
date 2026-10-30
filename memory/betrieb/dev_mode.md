# Developer installer mode — `zentrale dev`

**Stand 2026-10-30: built** (build step 0 of
[../hub/building_kit_plan.md](../hub/building_kit_plan.md), section 5.4).
Walk through every stage of the consumer journey on one machine, without
reinstalling anything real.

## What a profile is

An isolated ZENTRALE home: its own `HOME` (so its own
`~/.local/share/zentrale`, `~/.config/zentrale`, `~/.local/bin/zentrale`), its
own fake systemd, the dev root's fake cloud, its own device name
(`ZENTRALE_NODE_NAME` = profile name). A profile is installed by the **real**
`deploy/install.sh` and driven by its **own installed** `zentrale` (`setup`,
`update`, `timers` …). Only the edges are fake:

| Edge | Fake | Shared with the tests |
|---|---|---|
| cloud | `devkit/fake_cloud.py` (was `tests/_falsche_cloud.py`), state in a JSON file so all profiles and commands share it | yes, same class |
| systemd | `devkit/fake_systemd.py`: a `systemctl` that keeps enabled/active state, refuses units without a file, logs every call, never runs anything | yes, `tests/test_timer.py` |
| venv | linked from the venv `zentrale dev` runs in (`ZENTRALE_REUSE_VENV`), not built | yes |
| release tarballs | built from the checkout by `scripts/paket_bauen.py` (same positive list; new uncommitted files included), or dropped into `releases/` by hand | yes |

So a profile is made in about 2–5 s and reset in about 1–3 s.

## Layout

```
~/.local/state/zentrale-dev/        dev root (ZENTRALE_DEV_ROOT overrides)
  cloud/state.json  port  serve     fake cloud: accounts, its port, offered release
  releases/zentrale-<N>.tar.gz      local tarballs (".from-checkout" beside = rebuilt each use)
  profiles/<name>/profile.json      state, start release, params, online
  profiles/<name>/home/             the profile's HOME
  profiles/<name>/systemd/          its fake systemd
```

## Commands (in words — Sasha types them himself)

- **new** a profile with a name, optionally a start state, a start release
  and an account (another profile's account = a second device of it).
- **states** lists the start states and which are not built yet.
- **shell** opens a shell inside a profile; there `zentrale` is the profile's
  own. **run** runs the profile's `zentrale` once with the given words.
- **update** plays `zentrale update` in a profile up to release M (served by
  the fake cloud from `releases/`), keeper included.
- **reset** reinstalls the profile into its start state (its account stays in
  the fake cloud — like reinstalling a real device); **delete** removes it;
  **cloud-reset** empties the fake cloud; **release** lists or builds tarballs.
- Only in a developer checkout: the profile's installed `zentrale dev` says so.

## Start states — data, not if-chains

`devkit/states.py`: a state is a list of step names; a step is one function
in `STEPS`. New state = one line in `STATES`; new journey stage = one function.

| State | Steps |
|---|---|
| fresh | install (install.sh with an invite code, keeper timers, no login) |
| logged-in | install → login (`zentrale setup` with typed answers: create, or log in when the account exists) |
| offline | … → the cloud address leads nowhere |
| removed | … → the server ends this device's sessions and drops its description (what build step 8 will do); next sync: "Not logged in" |
| wizard | install → wizard (params `step`) — listed, refused until build step 2 adds the `wizard` step |

"On an old release N" is orthogonal: every state takes a start release.
Release N built from today's checkout has today's code; true old code comes
with build step 6 (archive of every released tarball → drop it into
`releases/`).

## Never the real installation

`devkit/guard.py`, checked on every command and every subprocess:
"real" comes from the user table, never from `$HOME`/`ZENTRALE_*`. The dev
root may not be inside or contain `~/.local/share/zentrale`,
`~/.config/zentrale`, `~/.config/systemd/user`, `~/.local/bin/zentrale`, the
home itself or the checkout. A profile's environment must have `HOME`, the
fake `systemctl` and the unit folder inside the dev root, and every
path-valued `ZENTRALE_*`/`XDG_*` too; inherited `ZENTRALE_*`, `XDG_*`,
`PYTHONPATH`, the session bus and `TMUX` are dropped. Deleting only inside
`profiles/`. Test: `tests/test_dev_mode.py` (also snapshots the real places
before and after).
