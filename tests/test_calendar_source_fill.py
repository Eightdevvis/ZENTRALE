"""Switching the calendar app to zencloud when the first fill takes long or
is interrupted; the Google sync alarm when the source is not google; no
Google and no .ics work with zencloud/lokal. Occasion 2026-10-29: Sasha
switched the laptop, the CLI hung silently for minutes, after Ctrl-C it only
said "already zencloud", and ZENTRALE kept showing "Google-Sync Zugang
abgelaufen". Docs: memory/hub/adapter.md ("Die Quelle der Kalender-App")."""
import os
import subprocess
import time

import pytest

import abgleich
import adapter
import adapter_ablauf
import kalender_einstellung as ke
import kalender_sync_zustand
from zentrale_cli import befehle
from test_adapter import Spiel, _basis, _kalender_da, _mitte_spiel, _skript


@pytest.fixture(autouse=True)
def _own_sync_state(tmp_path, monkeypatch):
    # Otherwise the Google sync state is shared by the whole session (venv guard).
    monkeypatch.setenv("ZENTRALE_KALENDER_SYNC_ZUSTAND", str(tmp_path / "sync_zustand.json"))
    monkeypatch.setenv("ZENTRALE_LANG", "en")


def _fake_sync(monkeypatch, do):
    """Replace abgleich.abgleichen with `do(wurzel)`; counts the runs."""
    runs = []

    def run(w, **_kw):
        runs.append(w)
        return do(w)
    monkeypatch.setattr(abgleich, "abgleichen", run)
    return runs


def _rule(root):
    """What the real sync does before sending (core/abgleich._adapter_vorher)."""
    return adapter.vor_abgleich(root, abgleich.ordner(), [adapter.KALENDER_MUSTER],
                                mitte_hat_kalender=abgleich.mitte_hat_kalender,
                                basis_kennt=abgleich.basis_kennt)


def _ctrl_c(_w):
    raise KeyboardInterrupt


def _goes_out(_w):
    """Like a sync that succeeded: the base knows the calendar afterwards."""
    _basis(abgleich.ordner(), ["data/kalender/termine/a.ics"])


# ── 1. Ctrl-C during the first fill ────────────────────────────────────

def test_ctrl_c_during_fill_keeps_zencloud_and_the_command_continues(monkeypatch, tmp_path):
    _mitte_spiel(monkeypatch, tmp_path, hat=False)
    ics = _kalender_da(tmp_path)
    _fake_sync(monkeypatch, _ctrl_c)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "interrupted" and r["fehler"] is None
    # The value stays (no rollback to google — Google would run again),
    # nothing deleted, and the fill counts as pending.
    assert ke.quelle() == "zencloud" and ics.exists()
    assert adapter_ablauf.calendar_fill_pending(wurzel=tmp_path)
    # The same command again continues instead of "already zencloud".
    runs = _fake_sync(monkeypatch, _goes_out)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "continued" and r["beiseite"] is None and len(runs) == 1
    assert ics.exists() and not adapter_ablauf.calendar_fill_pending(wurzel=tmp_path)
    # Only now: nothing left to do.
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "gleich"
    assert len(runs) == 1


def test_continuing_decides_nothing_before_the_sync(monkeypatch, tmp_path):
    """If the interrupted state did reach the hub (the hub now says "has a
    calendar" — it is our own), continuing must NOT set aside beforehand:
    the sync first finishes its plan (then the base knows the calendar),
    only then vor_abgleich asks."""
    _mitte_spiel(monkeypatch, tmp_path, hat=True)
    ics = _kalender_da(tmp_path)
    ke.schreiben(ke.HAUPT, "zencloud")
    seen = []

    def finish_plan_then_rule(w):
        seen.append(ics.exists())
        _basis(abgleich.ordner(), ["data/kalender/termine/a.ics"])     # plan finished
        seen.append(_rule(tmp_path))
    _fake_sync(monkeypatch, finish_plan_then_rule)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "continued" and r["beiseite"] is None
    assert seen == [True, None] and ics.exists()


def test_continuing_after_another_device_filled_sets_aside_by_the_rule(monkeypatch, tmp_path):
    """If another device filled the cloud meanwhile, "the cloud is never
    overwritten" applies — inside the sync, never deleted."""
    _mitte_spiel(monkeypatch, tmp_path, hat=True)
    _kalender_da(tmp_path)
    ke.schreiben(ke.HAUPT, "zencloud")
    _fake_sync(monkeypatch, lambda w: _rule(tmp_path))
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "continued" and r["beiseite"]
    assert os.path.exists(os.path.join(r["beiseite"], "termine", "a.ics"))


def test_continuing_offline_stays_incomplete(monkeypatch, tmp_path):
    _mitte_spiel(monkeypatch, tmp_path, hat=False)
    ics = _kalender_da(tmp_path)
    ke.schreiben(ke.HAUPT, "zencloud")

    def offline(_w):
        raise OSError("no connection")
    _fake_sync(monkeypatch, offline)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "incomplete" and "no connection" in r["fehler"]
    assert ke.quelle() == "zencloud" and ics.exists()
    _fake_sync(monkeypatch, _ctrl_c)
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "interrupted"
    _fake_sync(monkeypatch, lambda w: None)              # went out, but without the calendar
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "incomplete"


def test_fill_pending_only_with_zencloud_events_and_no_base(monkeypatch, tmp_path):
    _mitte_spiel(monkeypatch, tmp_path)
    assert not adapter_ablauf.calendar_fill_pending(wurzel=tmp_path)      # no setting
    ke.schreiben(ke.HAUPT, "zencloud")
    assert not adapter_ablauf.calendar_fill_pending(wurzel=tmp_path)      # no events
    _kalender_da(tmp_path)
    assert adapter_ablauf.calendar_fill_pending(wurzel=tmp_path)
    assert adapter_ablauf.calendar_file_count(wurzel=tmp_path) == 1
    _basis(abgleich.ordner(), ["data/kalender/termine/a.ics"])
    assert not adapter_ablauf.calendar_fill_pending(wurzel=tmp_path)
    for q in ("google", "lokal"):
        ke.schreiben(ke.HAUPT, q)
        _basis(abgleich.ordner(), [])
        assert not adapter_ablauf.calendar_fill_pending(wurzel=tmp_path)


def test_error_after_sending_does_not_roll_back(monkeypatch, tmp_path):
    """If the state (with the setting in it) did go out and the error came
    only afterwards, the hub rules — no rollback to google."""
    _mitte_spiel(monkeypatch, tmp_path)
    answers = iter([False, True])
    monkeypatch.setattr(abgleich, "mitte_hat_kalender", lambda ordner="data/kalender": next(answers))
    _kalender_da(tmp_path)

    def broken_late(_w):
        raise OSError("connection lost after sending")
    _fake_sync(monkeypatch, broken_late)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "fuellt" and r["fehler"] and ke.quelle() == "zencloud"


# ── CLI: sign of life and Ctrl-C ───────────────────────────────────────

def test_cli_says_what_comes_and_what_holds_after_ctrl_c(monkeypatch, tmp_path):
    from zentrale_cli import haupt
    _mitte_spiel(monkeypatch, tmp_path, hat=False)
    monkeypatch.setattr(befehle, "WURZEL", str(tmp_path))
    _kalender_da(tmp_path)
    _fake_sync(monkeypatch, _ctrl_c)
    term = Spiel()
    assert haupt.main(["adapter", "calendar", "zencloud"], term) == 130
    assert "Uploading the calendar to the cloud (1 files)" in term.text
    assert "stays zencloud, nothing was deleted" in term.text
    term = Spiel()
    assert haupt.main(["adapter", "calendar"], term) == 0
    assert "not fully in the cloud yet" in term.text
    term = Spiel()
    befehle.adapter_liste(term)
    assert "not fully in the cloud yet" in term.text
    _fake_sync(monkeypatch, _goes_out)
    term = Spiel()
    assert haupt.main(["adapter", "calendar", "zencloud"], term) == 0
    assert "Syncing the calendar with the cloud (1 files" in term.text
    assert "now done" in term.text and "done after" in term.text
    term = Spiel()
    assert haupt.main(["adapter", "calendar", "zencloud"], term) == 0
    assert "already zencloud" in term.text and "not fully" not in term.text


def test_cli_speaks_german_first(monkeypatch, tmp_path):
    from zentrale_cli import haupt
    monkeypatch.delenv("ZENTRALE_LANG")
    _mitte_spiel(monkeypatch, tmp_path, hat=False)
    monkeypatch.setattr(befehle, "WURZEL", str(tmp_path))
    _kalender_da(tmp_path)
    _fake_sync(monkeypatch, _ctrl_c)
    term = Spiel()
    assert haupt.main(["adapter", "calendar", "zencloud"], term) == 130
    assert "Lade den Kalender in die Cloud (1 Dateien)" in term.text
    assert "bleibt zencloud, nichts wurde gelöscht" in term.text


def test_sign_of_life_ticks_during_the_sync():
    term = Spiel()
    alive = befehle.SignOfLife(term, interval=0.01)
    alive.report("syncing", n=590, upload=True)
    until = time.monotonic() + 5
    while "still syncing" not in term.text and time.monotonic() < until:
        time.sleep(0.01)
    alive.report("done")
    assert "(590 files)" in term.text and "still syncing" in term.text
    assert "done after" in term.text
    n = term.text.count("still syncing")
    time.sleep(0.05)                                   # silent afterwards (checks something NOT coming)
    assert term.text.count("still syncing") == n and alive._thread is None


# ── 2. Google sync alarm only with source google ───────────────────────

def _expired():
    kalender_sync_zustand.schreiben(3, "zugang", kalender_sync_zustand.ARTEN["zugang"][1])


def test_sync_alarm_disappears_as_soon_as_the_source_is_not_google(monkeypatch, tmp_path):
    _mitte_spiel(monkeypatch, tmp_path)
    _expired()
    assert [a["kind"] for a in kalender_sync_zustand.alarme()] == ["Google-Sync"]
    for q in ("zencloud", "lokal"):
        ke.schreiben(ke.HAUPT, q)
        assert kalender_sync_zustand.alarme() == []
        assert kalender_sync_zustand.bewerten()["problem"] is False
        assert os.path.exists(kalender_sync_zustand.pfad())          # ignored, never deleted
    ke.schreiben(ke.HAUPT, "google")
    assert [a["kind"] for a in kalender_sync_zustand.alarme()] == ["Google-Sync"]


def test_backend_refreshes_the_alarm_at_once(monkeypatch, tmp_path):
    """The running backend recomputed the alarm channel only every ~5 min —
    after switching (another process) the warning stayed until then."""
    import kalender
    import main
    import state
    monkeypatch.setattr(kalender, "open_alarms", lambda *a, **k: [])
    _mitte_spiel(monkeypatch, tmp_path)
    ke.schreiben(ke.HAUPT, "google")
    _expired()
    state.set_alarms(kalender.alarme())
    s = main.refresh_sync_alarm(None)                   # first look: only remember
    assert [a["kind"] for a in state.get_alarms()] == ["Google-Sync"]
    assert main.refresh_sync_alarm(s) == s              # nothing changed
    ke.schreiben(ke.HAUPT, "zencloud")
    s = main.refresh_sync_alarm(s)
    assert state.get_alarms() == []
    ke.schreiben(ke.HAUPT, "google")
    main.refresh_sync_alarm(s)
    assert [a["kind"] for a in state.get_alarms()] == ["Google-Sync"]


def test_change_stamp_also_sees_a_new_sync_state(monkeypatch, tmp_path):
    _mitte_spiel(monkeypatch, tmp_path)
    s = kalender_sync_zustand.change_stamp()
    _expired()
    assert kalender_sync_zustand.change_stamp() != s


# ── 3. zencloud/lokal: nothing touches Google or the .ics ──────────────

def _tree(root):
    out = {}
    for w, _d, fs in os.walk(root):
        for f in fs:
            p = os.path.join(w, f)
            out[p] = (os.stat(p).st_mtime_ns, open(p, "rb").read())
    return out


@pytest.mark.parametrize("quelle", ["zencloud", "lokal"])
def test_no_google_and_no_ics_work(monkeypatch, tmp_path, quelle):
    _mitte_spiel(monkeypatch, tmp_path)
    monkeypatch.setattr(befehle, "WURZEL", str(tmp_path))
    _kalender_da(tmp_path)
    (tmp_path / "data/kalender_verlauf/grabsteine").mkdir(parents=True)
    (tmp_path / "data/kalender_verlauf/grabsteine/x.json").write_text("{}")
    cfg = tmp_path / "vdirsyncer-config"
    cfg.write_text("[general]\n")
    monkeypatch.setenv("ZENTRALE_VDIRSYNCER_CONFIG", str(cfg))
    ke.schreiben(ke.HAUPT, quelle)
    adapter.speichern(adapter.neu("google-kalender", "kalender-vdirsyncer", "kalender",
                                  "Google Calendar", {"vdirsyncer": {"abschnitte": []}}))
    before = _tree(tmp_path)

    def never(*a, **_kw):
        pytest.fail(f"called: {a[:1]}")
    monkeypatch.setattr(subprocess, "run", never)
    monkeypatch.setattr(subprocess, "Popen", never)
    monkeypatch.setattr(kalender_sync_zustand, "schreiben", never)
    monkeypatch.setattr(kalender_sync_zustand, "uebernehmen", never)
    monkeypatch.setattr(adapter_ablauf, "bruecke_lauf", never)
    # The timer: `zentrale adapter run`.
    term = Spiel()
    assert befehle.adapter_lauf(term) == 0 and f"'{quelle}', not google" in term.text
    # The script itself (old service): ends before any work — no vdirsyncer,
    # no ghost cleanup, no backup or rotation, no state file.
    script = _skript()
    for name in ("_spiegeln", "_vdirsyncer", "_google_sichern", "_stand_merken", "_lauf",
                 "_ein_lauf", "_ueber_adapter", "_zustand", "_fehlende"):
        monkeypatch.setattr(script, name, never)
    assert script.main(["zentrale"]) == 0
    assert _tree(tmp_path) == before
    assert not os.path.exists(kalender_sync_zustand.pfad())
