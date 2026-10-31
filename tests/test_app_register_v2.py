"""Register v2 (memory/hub/app_delivery_plan.md step 1): every entry says its
source {kind, ref}, its version and its data plugs; old entries read as a
`git` source. That an older reader still reads the new file:
tests/test_alte_fassung.py."""
import json
import os

import app_register

OLD = {"name": "budget", "quelle": "zentrale://shop/apps/budget",
       "ordner": "/x/budgeter", "ansichten": ["browser"], "am": "2026-10-25T12:00:00+02:00"}


def _write_raw(d):
    with open(app_register.datei(), "w", encoding="utf-8") as f:
        json.dump(d, f)


def _raw():
    with open(app_register.datei(), encoding="utf-8") as f:
        return json.load(f)


def test_old_entry_reads_as_git_with_nothing_else_changed():
    os.makedirs(os.path.dirname(app_register.datei()), exist_ok=True)
    _write_raw({"apps": [OLD]})
    e = app_register.eintrag("budget")
    assert e == {**OLD, "source": {"kind": "git", "ref": ""}, "version": "", "data": {}}


def test_round_trip_keeps_source_version_and_data():
    entry = {**OLD, "source": {"kind": "zentrale-package", "ref": "https://x/budget.tar.gz"},
             "version": "0.4.1", "data": {"files": "cloud-folder"}}
    app_register.schreiben([entry])
    assert app_register.alle() == [entry]
    raw = _raw()
    assert raw["format"] == app_register.FORMAT == 2
    assert raw["apps"] == [entry]
    app_register.schreiben(app_register.alle())          # stable
    assert _raw() == raw


def test_writing_an_old_entry_upgrades_it():
    app_register.schreiben([OLD])
    assert _raw()["apps"][0]["source"] == {"kind": "git", "ref": ""}


def test_broken_v2_fields_fall_back_instead_of_breaking_the_register():
    os.makedirs(os.path.dirname(app_register.datei()), exist_ok=True)
    _write_raw({"format": 2, "apps": [
        {**OLD, "source": {"kind": "Not A Kind!"}, "version": 3, "data": []},
        {**OLD, "name": "karte", "source": "git"}]})
    for e in app_register.alle():
        assert e["source"] == {"kind": "git", "ref": ""}
        assert e["version"] == "" and e["data"] == {}
