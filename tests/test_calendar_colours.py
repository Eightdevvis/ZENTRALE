"""
Calendar colours: one rule for every front (core/calendar_colours.py, 2026-10-29).

Checked: colour key (course incl. short forms, list source, group), slot
lookup and assignment (the old TUI rule, unchanged), style precedence
(X-ZENTRALE-STIL > COLOR > span > course > layer), the palette data file
(agrees with the TUI's xterm indexes, phone copy byte-identical), the synced
table (format, migration of the old local file, sync merge converges), the
/api/calendar annotation, and that the phone's test vectors are current.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import abgleich_auswahl
import abgleich_zusammenfuehren as az
import calendar_colours as cc
import eingebaute_apps
import kalender
import kalender_speicher

ROOT = Path(__file__).resolve().parent.parent


# ── Keys ────────────────────────────────────────────────────────────────
def test_course_key_merges_variants():
    s = cc.course_key
    assert s("Exphy Mathe") == s("ExPhy Tutorium") == s("Experimentalphysik mathe") \
        == s("Experimentalphysik")
    assert s("Analysis Saalübung") == s("Analysis I") == s("Analysis I @ HS 1") == "analysis"
    assert s("TP Sprechstunde Jonas (Mi)") == "theoretische" == s("Theoretische Physik Ia")
    assert s("Ana Tutorium Jäger") == "analysis"
    assert s("Allgemeine Chemie für Nebenfächler (Mo)") == s("Allgemeine Chemie (Do)")
    assert s("Geigenstunde @ Geigenschule") == s("Geigenstunde")
    assert s("ExPhy-Übung") == "experimentalphysik"
    assert s("") == s(None) == ""


def test_entry_key_source_beats_title_and_group_key():
    e = {"label": "todo", "quelle": {"art": "liste", "id": "l_todo"}}
    assert cc.entry_key(e) == "quelle:l_todo"
    assert cc.entry_key({"label": "Analysis I"}) == "analysis"
    assert cc.entry_key({"label": ""}) is None
    assert cc.entry_group_key({"kategorie": "uni"}) == "gruppe:uni"
    assert cc.entry_group_key({"kategorie": "custom", "kategorie_name": " Musik "}) == "gruppe:custom:musik"
    assert cc.entry_group_key({"kategorie": "keine"}) is None
    assert cc.entry_group_key({"kategorie": "custom"}) is None


# ── Slots ───────────────────────────────────────────────────────────────
def _days(*per_day):
    return [dict(label=l) for labels in per_day for l in labels]


def test_assign_gives_recurring_courses_distinct_fixed_slots():
    titles = ["Allgemeine Chemie (Mi)", "Analysis I", "Experimentalphysik",
              "Theoretische Physik Ia", "Parkour"]
    entries = _days(titles, titles, ["Lea"])          # Lea once: no slot
    slots = {}
    new = cc.assign(entries, slots)
    assert set(new) == set(slots) == {cc.course_key(t) for t in titles}
    assert sorted(slots.values()) == sorted(cc.ASSIGN_ORDER[:5])
    before = dict(slots)
    assert cc.assign(entries + _days(["Zumba", "Zumba"]), slots) == ["zumba"]
    assert {k: slots[k] for k in before} == before, "a slot never moves"
    assert cc.slot_for("lea", slots) == cc.fallback_slot("lea")
    assert cc.slot_for(None, slots) is None


def test_assign_skips_spans_and_phases_and_counts_groups():
    entries = [{"label": "Urlaub", "spanning": True}] * 2 + \
              [{"label": "Schlaf", "layer": "rhythmus"}] * 2 + \
              [{"label": "Analysis I", "kategorie": "uni"}, {"label": "Chemie", "kategorie": "uni"}]
    slots = {}
    cc.assign(entries, slots)
    assert set(slots) == {"gruppe:uni"}


def test_full_table_falls_back_to_crc32():
    slots = {"k%d" % i: i for i in range(cc.SLOT_COUNT)}
    cc.assign(_days(["Neu", "Neu"]), slots)
    assert slots["neu"] == cc.fallback_slot("neu")


def test_fallback_slot_is_crc32():
    import zlib
    for k in ("analysis", "quelle:l_todo", "gruppe:uni", "äöü"):
        assert cc.fallback_slot(k) == zlib.crc32(k.encode()) % 12


# ── Precedence ──────────────────────────────────────────────────────────
def test_style_from_ics_precedence():
    assert cc.style_from_ics("border-color: #FF8800", "red") == {"border-color": "#ff8800"}
    assert cc.style_from_ics(None, "darkorange") == {"background-color": "#ff8c00"}
    assert cc.style_from_ics(None, "#00ff00") == {"background-color": "#00ff00"}
    assert cc.style_from_ics("kaputt", "red") is None          # broken STIL: no COLOR either
    assert cc.style_from_ics("width: 3px", None) is None       # not offered
    assert cc.style_from_ics(None, "nocolour") is None
    assert cc.style_from_ics("", "red") is None


def test_resolve_order():
    slots = {"analysis": 3}
    assert cc.resolve(None, "analysis", slots)["role"] == "t3"
    assert cc.resolve(None, "analysis", slots)["source"] == "course"
    st = {"background-color": "#112233"}
    r = cc.resolve(st, "analysis", slots)
    assert (r["source"], r["role"], r["style"]) == ("style", "t3", st)
    assert cc.resolve(None, "analysis", slots, span=True)["role"] == "sp1"
    r = cc.resolve(None, None, slots)
    assert (r["source"], r["role"]) == ("layer", None)


def test_block_colours_follow_palette_and_style():
    pal = cc.load_palette()
    r = cc.resolve(None, "analysis", {"analysis": 3})
    night = cc.block_colours(r, "night")
    assert night["fill"] == pal["themes"]["night"]["roles"]["t3"]["fill"]
    assert night["text"] == pal["themes"]["night"]["roles"]["t3"]["on_fill"]
    r = cc.resolve({"border-color": "#ff0000"}, "analysis", {"analysis": 3})
    assert cc.block_colours(r, "day")["border"] == "#ff0000"
    assert cc.block_colours(r, "day")["fill"] == pal["themes"]["day"]["roles"]["t3"]["fill"]
    r = cc.resolve({"background-color": "#ffffff"}, "x", {})
    assert cc.block_colours(r, "night")["text"] == "#000000"
    assert cc.block_colours(cc.resolve(None, None, {}), "day", layer_default="#ff5500")["fill"] == "#ff5500"


def test_tui_style_box_agrees_with_core_block_colours():
    """The TUI draws a style with its own helper (kalender_stil.farben, it
    cannot import the core); both must mean the same."""
    from tui.ansichten import kalender_stil as ks
    for st in ({"background-color": "#ffffff"}, {"background-color": "#102030"},
               {"background-color": "#102030", "color": "#ffeedd"},
               {"color": "#ff8800"}, {"border-color": "#00ff00", "color": "#123456"}):
        core = cc.block_colours(cc.resolve(st, "k", {}), "night")
        tui = ks.farben(st)
        if tui["grund"]:
            assert core["fill"] == tui["grund"], st
        assert core["text"] == tui["schrift"], st
        assert core["border"] == tui["rand"], st


# ── Palette ─────────────────────────────────────────────────────────────
def test_palette_hex_matches_tui_xterm_indexes():
    from tui import pixel
    from tui.ansichten import farben
    pal = cc.load_palette()
    assert pal["format"] == "zentrale-calendar-palette/1"
    for theme, bg in (("night", 16), ("day", 231)):
        t = pal["themes"][theme]
        assert set(t["roles"]) == set(farben.KAL[theme]), theme
        assert t["background"]["xterm"] == farben.THEMES[theme]["bg256"] == bg
        for name, (fg, fl, of, _r8) in farben.KAL[theme].items():
            role = t["roles"][name]
            assert role["xterm"] == [fg, fl, of], (theme, name)
            for k, n in (("text", fg), ("fill", fl), ("on_fill", of)):
                assert role[k] == "#%02x%02x%02x" % pixel.xterm_rgb(n), (theme, name, k)
        d = farben.DECKKRAFT[theme]
        assert t["opacity"] == {"fill": d["flaeche"], "text": d["schrift"], "glass": d["glas"]}


def test_phone_bundles_the_same_palette():
    assert (ROOT / "mobile/assets/calendar_palette.json").read_bytes() == cc.PALETTE_PATH.read_bytes()
    assert "assets/calendar_palette.json" in (ROOT / "mobile/pubspec.yaml").read_text()


# ── The synced table ────────────────────────────────────────────────────
def test_table_format_and_tolerance():
    txt = cc.table_text({"b": 1, "a": 0})
    assert json.loads(txt) == {"format": cc.FORMAT, "slots": {"a": 0, "b": 1}}
    assert cc.parse_table(txt) == {"a": 0, "b": 1}
    assert cc.parse_table('{"analysis": 3, "x": 12, "y": true}') == {"analysis": 3}   # old flat file
    assert cc.parse_table("kaputt") == cc.parse_table("[1]") == {}
    assert cc.parse_table('{"format": "other/9", "slots": {"a": 1}}') == {}


def test_table_is_synced_calendar_app_data():
    rel = "data/calendar_colours.json"
    assert abgleich_auswahl.passt(rel) and rel in abgleich_auswahl.ABGLEICH
    assert rel in eingebaute_apps.EINGEBAUT["kalender"]["daten"]["muster"]
    assert az.art(rel) == "calendar_colours"
    p = kalender_speicher.pfade(kalender.CAL_PATH)["colours"]
    assert p.name == "calendar_colours.json" and p.parent == kalender.CAL_PATH.parent


def test_migration_takes_old_table_over_once_and_keeps_it(tmp_path):
    old = tmp_path / "state" / "kalender_farben.json"
    old.parent.mkdir()
    old.write_text(json.dumps({"analysis": 3, "chemie": 1, "quelle:l_x": 7}))
    new = tmp_path / "data" / "calendar_colours.json"
    new.parent.mkdir()
    new.write_text(cc.table_text({"analysis": 5}))           # the cloud's slot wins
    r = cc.migrate(new, str(old))
    assert (r["migrated"], r["taken"], r["kept"]) == (True, 2, 1)
    assert cc.read_table(new) == {"analysis": 5, "chemie": 1, "quelle:l_x": 7}
    assert old.exists() and json.loads(old.read_text())["analysis"] == 3   # backup untouched
    assert Path(str(old) + ".migrated").exists()
    new.write_text(cc.table_text({}))
    assert cc.migrate(new, str(old))["migrated"] is False                # once only
    assert cc.read_table(new) == {}


def test_migration_without_old_file_does_nothing(tmp_path):
    assert cc.migrate(tmp_path / "c.json", str(tmp_path / "nope.json"))["migrated"] is False
    assert not (tmp_path / "c.json").exists()


def _b(slots):
    return cc.table_text(slots).encode()


def test_sync_merge_two_devices_converge():
    """Laptop and PC both assign new keys offline, partly the same key with
    different slots. Whoever reaches the cloud first keeps its slot; after a
    round everyone holds the cloud's table — the same bytes."""
    basis = _b({"analysis": 0})
    laptop = _b({"analysis": 0, "chemie": 3})
    pc = _b({"analysis": 0, "chemie": 1, "parkour": 3})
    cloud = basis
    # laptop first
    r = az.zusammenfuehren("data/calendar_colours.json", basis, laptop, cloud)
    cloud = laptop_now = r.inhalt
    assert not r.konflikte
    # then the PC
    r = az.zusammenfuehren("data/calendar_colours.json", basis, pc, cloud)
    assert not r.konflikte
    cloud = pc_now = r.inhalt
    assert cc.parse_table(cloud) == {"analysis": 0, "chemie": 3, "parkour": 3}
    # laptop again: takes the cloud
    r = az.zusammenfuehren("data/calendar_colours.json", laptop_now, laptop_now, cloud)
    assert r.inhalt == pc_now == cloud


def test_sync_merge_never_overwrites_the_cloud_and_ignores_deletes():
    m = cc.merge(_b({"a": 1, "b": 2}), _b({"a": 4}), _b({"a": 1, "b": 2}))
    assert cc.parse_table(m) == {"a": 1, "b": 2}
    assert cc.parse_table(cc.merge(None, _b({"x": 1}), b"kaputt")) == {"x": 1}


# ── /api/calendar ───────────────────────────────────────────────────────
def test_annotate_view_assigns_saves_and_annotates(tmp_path):
    view = {"days": {"2026-10-05": [{"label": "Analysis I", "kategorie": "uni"}],
                     "2026-10-06": [{"label": "Analysis Übung", "kategorie": "uni"},
                                    {"label": "Lea"}]}}
    p = tmp_path / "calendar_colours.json"
    cc.annotate_view(view, p)
    slots = cc.read_table(p)
    assert set(slots) == {"analysis", "gruppe:uni"}
    a = view["days"]["2026-10-05"][0]["colour"]
    assert a == {"key": "analysis", "slot": slots["analysis"],
                 "group_key": "gruppe:uni", "group_slot": slots["gruppe:uni"]}
    assert view["days"]["2026-10-06"][1]["colour"]["slot"] == cc.fallback_slot("lea")


def test_route_sends_colour(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "ai_calendar.json")
    from ui.app import app
    app.config["TESTING"] = True
    c = app.test_client()
    for day in ("2026-11-02", "2026-11-03"):
        assert c.post("/api/calendar/entry", json={"day": day, "label": "Analysis I",
                                                   "time": "10:00"}).status_code == 200
    d = c.get("/api/calendar?view=week&ref=2026-11-03").get_json()
    e = d["days"]["2026-11-03"][0]
    assert e["colour"]["key"] == "analysis" and e["colour"]["slot"] == cc.ASSIGN_ORDER[0]
    assert cc.read_table(tmp_path / "calendar_colours.json") == {"analysis": cc.ASSIGN_ORDER[0]}


# ── Phone vectors are current ───────────────────────────────────────────
def test_phone_vectors_are_current():
    target = ROOT / "mobile/test/daten/calendar_colour_vectors.json"
    out = subprocess.run([sys.executable, str(ROOT / "scripts/calendar_colour_vectors.py"), "--stdout"],
                         capture_output=True, text=True, check=True, cwd=ROOT,
                         env={**os.environ, "PYTHONHASHSEED": "0"}).stdout
    assert out == target.read_text(encoding="utf-8"), \
        "run scripts/calendar_colour_vectors.py, then flutter test"
