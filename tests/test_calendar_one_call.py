"""Guard E6 (memory/hub/kern_auszug_inventur.md, section E; A1 2026-10-31):
one user action in the calendar TUI = at most ONE write call to the core.

Before, editing an entry was up to 7 calls (typ before, the change, group,
style, source, typ after, layer) and "once → series/span" was create +
delete; a failure halfway left a half-changed entry. Now the core does it
all in PUT /api/calendar/edit (core/kalender_bearbeiten.edit, one save).

The guard has three parts:
  * the plan builder `kalender_werkzeuge._plan` refuses more than one call,
  * every plan in tui/ is built by `_plan` (no hand-made {"aufrufe": …}),
  * each edit form gives exactly one call, also with every Advanced change.
Legacy list: empty — no other place needs more than one call. It may only
stay empty.
"""
import ast
import os
from datetime import date

import pytest

from tui.ansichten import kalender_werkzeuge as kw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = date(2026, 10, 7)
LEGACY = set()          # (file, line) of plans that still need several calls — may only shrink

ONCE = {"label": "Zahnarzt", "layer": "termine", "time": "14:00", "ende": "15:00",
        "kennung": "k-zahn"}
SERIES = {"label": "Geige", "layer": "termine", "time": "18:00", "ende": "19:00",
          "recurring": True, "rrule": "FREQ=WEEKLY;BYDAY=WE", "kennung": "k-geige"}
SPAN = {"label": "Messe", "layer": "termine", "spanning": True, "von": "2026-10-06",
        "bis": "2026-10-08", "kennung": "k-messe"}


def _set(f, **values):
    for name, value in values.items():
        x = next(x for x in f.felder if x.name == name)
        if x.art == "wahl":
            x.wahl = x.optionen.index(value)
        else:
            x.text = value


def _status(f, status):
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    box = f.box
    box.i = box.reihen().index("status")
    if box.status != status:
        box.taste(261)
    f.taste(10)
    assert f.box is None


def _one_call(f):
    assert f.taste(19) == "fertig", f.fehler                 # Ctrl-S
    calls = f.plan()["aufrufe"]
    assert len(calls) == 1, calls
    return calls[0]


def test_plan_refuses_a_second_write_call():
    one = ("POST", "/api/calendar/entry", {})
    assert kw._plan([one])["aufrufe"] == [one]
    with pytest.raises(ValueError, match="at most ONE write call"):
        kw._plan([one, ("DELETE", "/api/calendar/eintrag", {})])


def test_every_plan_is_built_by_the_guarded_builder():
    """A dict literal with the key "aufrufe" outside `_plan` would bypass
    the guard."""
    found = set()
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "tui")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            builders = {id(n) for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                        and f.name == "_plan" and name == "kalender_werkzeuge.py"
                        for n in ast.walk(f)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict) and id(node) not in builders and any(
                        isinstance(k, ast.Constant) and k.value == "aufrufe" for k in node.keys):
                    found.add((os.path.relpath(path, ROOT), node.lineno))
    assert found <= LEGACY, "plans built by hand (use kalender_werkzeuge._plan): %s" % found


def test_edit_once_with_every_advanced_change_is_one_call():
    f = kw.formular_bearbeiten(ONCE, TAG, TAG)
    _status(f, "uncommitted")
    _set(f, von="15:00", bis="16:00", ort="Praxis", gruppe="Uni")
    m, path, body = _one_call(f)
    assert (m, path, body["kennung"]) == ("PUT", "/api/calendar/edit", "k-zahn")
    new = body["new"]
    assert (new["time"], new["ort"], new["kategorie"], new["layer"]) == \
        ("15:00", "Praxis", "uni", "uncommitted")


@pytest.mark.parametrize("values,kind", [
    ({"wied": "wöchentlich"}, "routine"),
    ({"wied": "täglich", "wbis": "09.10.2026"}, "spanne"),
])
def test_once_becomes_series_or_span_in_one_call(values, kind):
    f = kw.formular_bearbeiten(ONCE, TAG, TAG)
    _set(f, **values)
    _m, path, body = _one_call(f)
    assert path == "/api/calendar/edit" and body["replace"]["kind"] == kind
    assert body["kennung"] == "k-zahn" and "new" not in body


def test_edit_whole_series_and_whole_span_are_one_call():
    d = kw.formular_bearbeiten(SERIES, TAG, TAG)
    d.taste(ord("a"))
    f = d.plan()["weiter"]
    _status(f, "uncommitted")
    _set(f, titel="Violine", wtage="di do", gruppe="Uni")
    _m, path, body = _one_call(f)
    assert path == "/api/calendar/edit" and body["day"] == "2026-10-07"
    assert body["new"]["wiederholung"]["wochentage"] == ["TU", "TH"]
    d = kw.formular_bearbeiten(SPAN, TAG, TAG)
    d.taste(ord("a"))
    f = d.plan()["weiter"]
    _set(f, erster="13.10.2026", letzter="15.10.2026", gruppe="Uni")
    _m, path, body = _one_call(f)
    assert path == "/api/calendar/edit" and body["new"]["verschieben"] == 7
