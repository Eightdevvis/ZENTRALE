"""
Notiz-Registry (core/notes.py): CRUD gegen ein temporäres data/-Verzeichnis
plus die reinen Layout-Helfer (wrap/height/stack/scatter), die die TUI zum
Zeichnen spiegelt. Kein Terminal, kein Flask — nur die Modul-Logik.
"""
import importlib

import pytest

import notes as notes_mod


@pytest.fixture()
def notes(tmp_path, monkeypatch):
    """core.notes auf ein frisches data/-Verzeichnis umbiegen (isoliert je Test)."""
    reg = tmp_path / "notes.json"
    monkeypatch.setattr(notes_mod, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(notes_mod, "_REGISTRY", str(reg))
    return notes_mod


# ── CRUD ──────────────────────────────────────────────────────────────

def test_create_get_save_list_delete(notes):
    assert notes.list_notes() == []
    n = notes.create_note("Einkauf")
    assert n["id"] == "n_einkauf"
    assert n["blocks"] == [] and n["next_block"] == 1
    assert notes.get_note(n["id"])["title"] == "Einkauf"

    saved = notes.save_note(n["id"], title="Einkauf!", blocks=[
        {"type": "text", "text": "milch"},
        {"type": "list", "items": [{"text": "apfel"}, {"text": "birne", "done": True}]},
    ])
    assert saved["title"] == "Einkauf!"
    assert [b["type"] for b in saved["blocks"]] == ["text", "list"]
    assert saved["next_block"] == 3                     # zwei Blöcke → nächste id 3

    lst = notes.list_notes()
    assert len(lst) == 1 and lst[0]["nblocks"] == 2 and lst[0]["title"] == "Einkauf!"

    notes.delete_note(n["id"])
    assert notes.list_notes() == [] and notes.get_note(n["id"]) is None


def test_slug_collision_is_unique(notes):
    a = notes.create_note("Ideen")
    b = notes.create_note("Ideen")
    assert a["id"] == "n_ideen" and b["id"] == "n_ideen_2"


def test_empty_title_gets_fallback_slug(notes):
    n = notes.create_note("")
    assert n["id"] == "n_notiz" and n["title"] == ""


def test_modified_advances_on_save(notes):
    n = notes.create_note("x")
    notes.save_note(n["id"], blocks=[{"type": "text", "text": "a"}])
    got = notes.get_note(n["id"])
    assert got["modified"] >= got["created"]


def test_save_unknown_raises(notes):
    with pytest.raises(KeyError):
        notes.save_note("n_gibtsnicht", title="x")


def test_list_sorted_newest_first(notes):
    a = notes.create_note("a")
    b = notes.create_note("b")
    notes.save_note(a["id"], blocks=[{"type": "text", "text": "berührt a zuletzt"}])
    ids = [x["id"] for x in notes.list_notes()]
    assert ids[0] == a["id"]                            # a zuletzt geändert → oben


# ── Block-Sanitizing (tolerant gegen krude Bodies) ─────────────────────

def test_clean_blocks_drops_bogus_and_coerces(notes):
    n = notes.create_note("s")
    saved = notes.save_note(n["id"], blocks=[
        {"type": "bogus"},                                     # fällt raus
        {"type": "float", "terms": ["a", "", "   ", "b", {"text": "c"}]},
        {"type": "list", "items": ["nur str fällt raus", {"text": "ok"}]},
    ])
    assert [b["type"] for b in saved["blocks"]] == ["float", "list"]
    fl = saved["blocks"][0]
    assert [t["text"] for t in fl["terms"]] == ["a", "b", "c"]   # leere weg
    assert all(isinstance(t["id"], int) for t in fl["terms"])
    li = saved["blocks"][1]
    assert [it["text"] for it in li["items"]] == ["ok"]          # str-item verworfen


# ── Reine Layout-Helfer ────────────────────────────────────────────────

def test_wrap_text(notes):
    assert notes.wrap_text("hallo welt dies ist test", 10) == ["hallo welt", "dies ist", "test"]
    assert notes.wrap_text("a\nb", 10) == ["a", "b"]            # harte Umbrüche bleiben
    assert notes.wrap_text("", 10) == [""]                     # nie leer
    assert notes.wrap_text("xxxxxxxx", 3) == ["xxx", "xxx", "xx"]  # überlanges Wort


def test_block_height_grows_with_content(notes):
    empty = {"type": "text", "text": ""}
    two = {"type": "text", "text": "eins\nzwei"}
    assert notes.block_height(empty, 40) == 3                  # 1 Inhalt + 2 Rahmen
    assert notes.block_height(two, 40) == 4                    # 2 Zeilen + Rahmen
    lst = {"type": "list", "items": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}
    assert notes.block_height(lst, 40) == 5                    # 3 Items + Rahmen
    fl = {"type": "float", "terms": [{"text": "t%d" % i} for i in range(5)]}
    assert notes.block_height(fl, 40) >= 5                     # gestreut, mehrere Zeilen


def test_stack_layout_is_cumulative(notes):
    blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b\nc"}]
    lay = notes.stack_layout(blocks, 40, gap=1)
    assert lay[0][1] == 0                                      # erster bei y=0
    assert lay[1][1] == lay[0][2] + 1                          # zweiter nach h0 + gap


def test_scatter_deterministic_unique_in_field(notes):
    a = notes.scatter_positions(6, 40, 8)
    b = notes.scatter_positions(6, 40, 8)
    assert a == b                                             # reproduzierbar (kein random)
    assert len(set(a)) == len(a)                             # keine Dubletten
    assert all(0 <= x < 40 and 0 <= y < 8 for x, y in a)     # im Feld
