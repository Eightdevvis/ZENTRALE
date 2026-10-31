"""Lists step 3: where the lists live comes by setting (ZENTRALE_LISTS_DIR,
core/lists.py files()), and the Prüfstand uses that setting instead of
bending lists' module paths.

Risk named in memory/hub/list_extraction_plan.md: if the new way is wrong,
the Prüfstand writes into Sasha's real lists (incl. his tracker l_zentrale).
These tests prove it does not: the "real" place (the test's own folder,
standing in for data/) is the same bytes after a bench set-up plus writes.
"""

import json
import os
import sys

import pytest

import lists

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DATA = os.path.abspath(os.path.join(ROOT, "data"))
BENCH = os.path.join(ROOT, "scripts", "pruefstand_teile", "umgebung.py")


@pytest.fixture
def environ_back():
    """vorbereiten() sets many ZENTRALE_* variables straight in os.environ."""
    before = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(before)


@pytest.fixture
def stand_in_real(_test_ordner):
    """The place the module paths point to (in tests: a test folder, in
    production: data/) with a personal list and the tracker l_zentrale."""
    with open(lists._REGISTRY, "w", encoding="utf-8") as f:
        json.dump([{"id": "l_privat", "name": "Privat", "next_item": 2,
                    "items": [{"id": 1, "text": "geheim", "done": False}]}], f)
    with open(lists._FEATURES, "w", encoding="utf-8") as f:
        json.dump([{"id": "l_zentrale", "name": "zentrale", "next_item": 2,
                    "items": [{"id": 1, "text": "feature", "done": False}]}], f)

    def snapshot():
        folder = os.path.dirname(lists._REGISTRY)
        return {n: open(os.path.join(folder, n), "rb").read() for n in sorted(os.listdir(folder))}
    return snapshot


def _bench():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    try:
        from pruefstand_teile import umgebung
    finally:
        sys.path.remove(os.path.join(ROOT, "scripts"))
    return umgebung


def test_without_setting_the_module_paths_count():
    assert lists.files() == (lists._REGISTRY, lists._FEATURES)


def test_setting_points_both_files_elsewhere(monkeypatch, _test_ordner):
    monkeypatch.setenv(lists.LOCATION_SETTING, str(_test_ordner / "woanders"))
    reg, feat = lists.files()
    assert reg == str(_test_ordner / "woanders" / "lists.json")
    assert feat == str(_test_ordner / "woanders" / "features.json")


def test_bench_never_writes_into_the_real_lists(environ_back, stand_in_real, _test_ordner):
    before = stand_in_real()
    tmp = str(_test_ordner / "bench")
    daten = str(_test_ordner / "keine_echten_daten")      # no keys, no config
    _bench().vorbereiten(tmp, daten)

    reg, feat = lists.files()
    assert os.path.dirname(reg) == os.path.join(tmp, "listen")
    for path in (reg, feat):
        assert not os.path.abspath(path).startswith(REAL_DATA + os.sep)
    assert lists.list_lists() == []                       # the real ones are not even seen

    # what a case does: create, add, tick, rename, delete — also an "l_zentrale"
    a = lists.create_list("Fall")
    lists.add_item(a["id"], "eins")
    lists.toggle_item(a["id"], 1)
    z = lists.create_list("zentrale")
    lists.add_item(z["id"], "neu")
    lists.rename_list(a["id"], "Fall 2")
    lists.delete_list(z["id"])

    assert stand_in_real() == before                       # same bytes, same files
    assert os.path.exists(reg)
    assert [l["name"] for l in lists.list_lists()] == ["Fall 2"]


def test_bench_does_not_bend_lists_module_paths():
    with open(BENCH, encoding="utf-8") as f:
        source = f.read()
    for name in ("_DATA_DIR", "_REGISTRY", "_FEATURES"):
        assert 'setzen(lists, "%s"' % name not in source, (
            "the Prüfstand bends lists.%s again — use the setting "
            "ZENTRALE_LISTS_DIR (core/lists.py files())" % name)
