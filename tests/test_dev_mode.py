"""Developer installer mode (devkit/, `zentrale dev`) and the keeper in the
installer (memory/hub/building_kit_plan.md 5.2, 5.4; build steps 0 and 1).

Profiles are installed by the real deploy/install.sh and driven by their own
installed `zentrale`, against the shared fakes (devkit/fake_cloud.py,
devkit/fake_systemd.py). One dev root per module: building the tarball once
keeps the module at a few seconds per profile."""
import io
import os
import tarfile
import time

import pytest

from devkit import guard, profiles, states, workspace
from zentrale_cli import dev, haupt
from zentrale_cli.ausgabe import Terminal

TIMERS = ["zentrale-abgleich.timer", "zentrale-kalender-sync.timer", "zentrale-update.timer"]
CALENDAR_UNIT = '''    "zentrale-kalender-sync": ("ZENTRALE: calendar bridge (Google via vdirsyncer)",
                               "adapter run", "*:0/3", 600),
'''


def _repack(src, dst, version, edits=None):
    """A copy of release tarball `src` as `version`, files changed by `edits`
    ({path inside: function(text) → text}) — e.g. a release without a unit."""
    edits = dict(edits or {})
    with tarfile.open(src) as alt, tarfile.open(dst, "w:gz", compresslevel=1) as neu:
        for m in alt.getmembers():
            inner = m.name.split("/", 1)[1] if "/" in m.name else ""
            data = alt.extractfile(m).read() if m.isfile() else None
            if inner == "VERSION":
                data = (version + "\n").encode()
            elif inner in edits:
                data = edits.pop(inner)(data.decode()).encode()
            info = tarfile.TarInfo(f"zentrale-{version}" + (f"/{inner}" if inner else ""))
            info.type, info.mode, info.mtime = m.type, m.mode, m.mtime
            if data is not None:
                info.size = len(data)
                neu.addfile(info, io.BytesIO(data))
            else:
                neu.addfile(info)
    assert not edits, f"not in the tarball: {edits}"


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    w = workspace.Workspace(str(tmp_path_factory.mktemp("devroot")))
    built = w.build_release("41")
    os.remove(built + workspace.FROM_CHECKOUT)          # reuse it as a "put there" tarball
    for v in ("40", "2"):
        _repack(built, w.release_path(v), v)

    def without_calendar(text):
        assert CALENDAR_UNIT in text
        return text.replace(CALENDAR_UNIT, "")
    _repack(built, w.release_path("1"), "1", {"zentrale_cli/timer.py": without_calendar})
    return w


def _snapshot():
    """What the real installation looks like (read only): exists, mtime, names."""
    raus = {}
    for place in guard.real_places():
        if os.path.isdir(place):
            raus[place] = (os.stat(place).st_mtime_ns, sorted(os.listdir(place)))
        else:
            raus[place] = os.path.lexists(place)
    return raus


# ── Step 1: the keeper comes with the installer ───────────────────────

def test_fresh_install_enables_the_timers_before_any_login(ws):
    real = _snapshot()
    start = time.monotonic()
    p = profiles.create(ws, "fresh-one", release="41")
    made = time.monotonic() - start
    assert p.installed_release() == "41"
    assert p.fake.unit_files() == ["zentrale-abgleich.service", "zentrale-abgleich.timer",
                                   "zentrale-kalender-sync.service", "zentrale-kalender-sync.timer",
                                   "zentrale-update.service", "zentrale-update.timer"]
    assert sorted(p.fake.enabled()) == TIMERS and sorted(p.fake.active()) == TIMERS
    assert not os.path.exists(os.path.join(p.home, ".config", "zentrale", "konto.json"))
    dienst = open(os.path.join(p.fake.units, "zentrale-abgleich.service")).read()
    assert f"ExecStart={p.hub}/hub/aktuell/bin/zentrale sync --automatic" in dienst
    # Before login the timer's command simply exits 0, quietly.
    r = p.zentrale("sync", "--automatic")
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    # Acceptance of step 0: made and reset in < 10 s; the real installation untouched.
    start = time.monotonic()
    p = profiles.reset(ws, "fresh-one")
    assert made < 10 and time.monotonic() - start < 10
    assert sorted(p.fake.enabled()) == TIMERS
    assert _snapshot() == real


def test_update_from_a_release_without_a_unit_makes_the_unit_appear(ws):
    p = profiles.create(ws, "old-node", state="logged-in", release="1")
    assert p.installed_release() == "1"
    assert p.fake.enabled() == ["zentrale-abgleich.timer", "zentrale-update.timer"]
    assert "zentrale-kalender-sync.timer" not in p.fake.unit_files()
    before, after, r = states.play_update(p, "2")
    assert (before, after, r.returncode) == ("1", "2", 0), r.stdout + r.stderr
    assert p.installed_release() == "2"
    assert "zentrale-kalender-sync.timer" in p.fake.unit_files()
    assert sorted(p.fake.enabled()) == TIMERS
    # Every update runs the keeper again; nothing new → nothing rewritten.
    p.fake.clear_log()
    ws.serve("2")
    with ws.cloud():
        r = p.zentrale("update")
    assert r.returncode == 0 and "--user daemon-reload" not in p.fake.calls()


# ── Step 0: states, guard, CLI ────────────────────────────────────────

def test_states_are_data_and_planned_ones_are_refused(ws, monkeypatch):
    for s in states.STATES:
        assert not states.missing(s) or s.planned, s
    monkeypatch.setattr(states, "STATES", states.STATES + (
        states.State("later", ("install", "teleport"), planned="build step 99"),))
    with pytest.raises(profiles.DevError) as e:
        profiles.create(ws, "later-one", state="later")
    assert e.value.key == "dev_state_planned" and e.value.values["planned"] == "build step 99"
    with pytest.raises(profiles.DevError) as e:
        profiles.create(ws, "nope-one", state="dancing")
    assert e.value.key == "dev_unknown_state"
    assert not os.path.exists(os.path.join(ws.profiles, "later-one"))


# ── Step 2: setup wizard, automatic update, self-heal ─────────────────

def test_fresh_profile_runs_the_wizard_to_the_end(ws):
    """Acceptance of step 0, wizard part: fresh → the whole wizard, defaults."""
    p = profiles.create(ws, "wiz-fresh", state="wizard", release="41")
    _account, lines = states.wizard_answers(p, 99)
    with ws.cloud():
        r = p.zentrale("setup", answers="\n".join(lines) + "\n")
    assert r.returncode == 0, r.stdout + r.stderr
    for step in ("Step 1 of 5", "A folder that syncs", "automatically", "nobody is logged in"):
        assert step in r.stdout
    assert r.stdout.rstrip().endswith("'zentrale'.")
    assert sorted(p.fake.enabled()) == TIMERS and p.fake.lingering()


def test_wizard_step_n_picks_up_there(ws):
    p = profiles.create(ws, "wiz-two", state="wizard", release="41", params={"step": 2})
    with ws.cloud():
        r = p.zentrale("setup", answers="2\n\n\n")      # auto-update off, rest default
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Picking up where you left off." in r.stdout and "How do you want" not in r.stdout
    assert "Step 3 of 5" in r.stdout and "Step 2 of 5" not in r.stdout
    r = p.zentrale("status")
    assert "Auto-update" in r.stdout and "off" in r.stdout


def test_automatic_update_self_test_broken_release_and_setting_off(ws):
    built = ws.release_path("41")
    _repack(built, ws.release_path("42"), "42")
    _repack(built, ws.release_path("43"), "43",
            {"zentrale_cli/befehle.py": lambda text: "import no_such_module_zz\n" + text})
    _repack(built, ws.release_path("44"), "44")
    p = profiles.create(ws, "auto-node", state="logged-in", release="41")
    p.fake.set_active("zentrale-kern.service")
    p.fake.clear_log()

    def automatic(version):
        ws.serve(version)
        with ws.cloud():
            return p.zentrale("update", "--automatic")
    r = automatic("41")                                       # nothing new → quiet
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    r = automatic("42")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Self-test of 42" in r.stdout and "Self-test: cloud reachable." in r.stdout
    assert p.installed_release() == "42"
    assert "--user try-restart zentrale-kern.service" in p.fake.calls()
    r = automatic("43")                                       # broken → stays, one note
    assert r.returncode == 1 and "no_such_module_zz" in r.stdout
    assert p.installed_release() == "42"
    assert "Update to 43 failed its self-test; staying on 42" in p.zentrale("status").stdout
    assert p.zentrale("update", "auto", "off").returncode == 0
    r = automatic("44")                                       # off → only the hint
    assert (r.returncode, r.stdout) == (0, "")
    assert p.installed_release() == "42"
    assert "Update available: 42 → 44" in p.zentrale("status").stdout


def test_old_code_update_heals_through_the_sync_timer(ws):
    """A node updated by a release without the keeper: the next sync timer run
    (new code via hub/aktuell) runs `timers install` once."""
    p = profiles.create(ws, "heal-node", state="logged-in", release="41")
    for unit in ("zentrale-update.timer", "zentrale-update.service"):
        p.fake.remove_unit(unit)
    with open(os.path.join(p.hub, "keeper.json"), "w") as f:
        f.write('{"release": "40"}')                          # the keeper last ran on 40
    with ws.cloud():
        r = p.zentrale("sync", "--automatic")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "zentrale-update.timer" in p.fake.unit_files() and sorted(p.fake.enabled()) == TIMERS
    p.fake.clear_log()
    with ws.cloud():
        p.zentrale("sync", "--automatic")
    assert "--user daemon-reload" not in p.fake.calls()       # once, not every run


# ── Step 3: lingering ─────────────────────────────────────────────────

def test_lingering_session_less_sync_and_status(ws):
    p = profiles.create(ws, "linger-node", state="logged-in", release="41")
    assert p.fake.lingering()                                 # the wizard's default
    assert "keeps syncing when you are logged out" in p.zentrale("status").stdout
    # The sync unit fires without a login session (no session bus in the env).
    with open(os.path.join(p.fake.units, "zentrale-abgleich.service")) as f:
        exec_start = next(line for line in f.read().splitlines() if line.startswith("ExecStart="))
    cloud_file = os.path.join(p.home, "Zentrale", "Cloud", "note.txt")
    os.makedirs(os.path.dirname(cloud_file), exist_ok=True)
    with open(cloud_file, "w") as f:
        f.write("from the mini\n")
    with ws.cloud():
        r = p.run(exec_start[len("ExecStart="):].split())
    assert r.returncode == 0 and "sent 1" in r.stdout, r.stdout + r.stderr
    p.fake.set_linger(False)
    assert "syncs only while you are logged in" in p.zentrale("status").stdout


def test_second_device_offline_and_removed(ws):
    first = profiles.create(ws, "laptop", state="logged-in", release="41")
    away = profiles.create(ws, "away", state="offline", release="41", params={"account": "laptop"})
    r = away.zentrale("sync")
    assert r.returncode == 1 and "127.0.0.1:9" in r.stderr
    gone = profiles.create(ws, "gone", state="removed", release="41", params={"account": "laptop"})
    with ws.cloud():
        r = gone.zentrale("sync")
        assert r.returncode == 1 and "Not logged in" in r.stderr
        r = first.zentrale("devices")
    assert r.returncode == 0 and "away" in r.stdout and "gone" not in r.stdout


def test_guard_never_the_real_installation(ws, tmp_path):
    home = guard.real_home()
    for root in (home, os.path.join(home, ".local"), os.path.join(home, ".local", "share", "zentrale"),
                 os.path.join(home, ".config", "systemd", "user", "x"), workspace.CHECKOUT,
                 os.path.join(workspace.CHECKOUT, "tests", "x")):
        with pytest.raises(guard.GuardError):
            workspace.Workspace(root)
    p = profiles.Profile(ws, "fresh-one")
    env = p.env()
    assert env["HOME"].startswith(ws.root) and env["ZENTRALE_SYSTEMCTL"].startswith(ws.root)
    assert not any(k.startswith("DBUS") for k in env)
    for bad in ({"HOME": home}, {"ZENTRALE_SYSTEMD_USER_DIR": os.path.join(home, ".config", "systemd", "user")},
                {"ZENTRALE_KONTO_DATEI": os.path.join(home, ".config", "zentrale", "konto.json")}):
        with pytest.raises(guard.GuardError):
            guard.check_env(dict(env, **bad), ws.root)
    with pytest.raises(guard.GuardError):
        guard.check_inside(os.path.join(home, ".local", "share", "zentrale"), ws.root)


def test_cli(ws, monkeypatch):
    monkeypatch.setenv("ZENTRALE_DEV_ROOT", ws.root)

    def run(*words):
        term = Terminal(aus=io.StringIO())
        return haupt.main(["dev", *words], term=term), term.aus.getvalue()
    rc, out = run()
    assert rc == 0 and "fresh-one" in out and "zentrale dev new" in out
    rc, out = run("states")
    assert "wizard" in out and "not built yet" not in out
    assert run("bogus")[0] == 2 and run("reset")[0] == 2 and run("update", "x")[0] == 2
    rc, out = run("delete", "no-such")
    assert rc == 1 and "no profile" in out
    monkeypatch.setattr(dev, "kanal", lambda w: "script")
    rc, out = run()
    assert rc == 1 and "developer checkout" in out
