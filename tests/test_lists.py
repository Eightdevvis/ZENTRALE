"""
Listen-Kern (core/lists.py): die Verschachtelung.

Einträge sind seit dem Verschachteln-Feature Mischtypen — jeder kann selbst
wieder Unterpunkte (eigenes 'items') tragen ODER eine ganze eingeordnete
Unterliste sein ODER beides. Geprüft wird, dass

  - Unterpunkte beliebig tief angehängt werden,
  - toggle/delete den ganzen Baum treffen (nicht nur die oberste Ebene),
  - eine ganze Liste sauber in eine andere wandert (ids kollisionsfrei neu).

Wir biegen die Registry auf eine tmp-Datei um, damit die echte data/lists.json
unberührt bleibt und der Test deterministisch läuft.
"""
import importlib

import pytest

import lists as L  # core/ liegt via conftest auf sys.path


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    """Frische, leere Registries in tmp-Dateien — BEIDE (privat + features),
    sonst greift _load/_save auf die echte data/features.json zu."""
    f = tmp_path / "lists.json"
    monkeypatch.setattr(L, "_REGISTRY", str(f))
    monkeypatch.setattr(L, "_FEATURES", str(tmp_path / "features.json"))
    monkeypatch.setattr(L, "_DATA_DIR", str(tmp_path))
    return f


def _get(lid):
    return next(x for x in L.list_lists() if x["id"] == lid)


def test_subitem_makes_item_a_container(reg):
    lst = L.create_list("trading")
    top = L.add_item(lst["id"], "Setup")
    sub = L.add_item(lst["id"], "Broker wählen", parent_iid=top["id"])
    # Der Unterpunkt hängt UNTER dem Eltern-Eintrag, nicht auf der obersten Ebene.
    d = _get(lst["id"])
    assert len(d["items"]) == 1
    assert d["items"][0]["items"][0]["text"] == "Broker wählen"
    # ids sind über den ganzen Baum eindeutig (gemeinsame next_item-Quelle).
    assert sub["id"] != top["id"]


def test_arbitrary_depth(reg):
    lst = L.create_list("tief")
    a = L.add_item(lst["id"], "a")
    b = L.add_item(lst["id"], "b", parent_iid=a["id"])
    c = L.add_item(lst["id"], "c", parent_iid=b["id"])
    d = _get(lst["id"])
    assert d["items"][0]["items"][0]["items"][0]["text"] == "c"
    assert {a["id"], b["id"], c["id"]} == {1, 2, 3}


def test_toggle_and_delete_reach_nested(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    deep = L.add_item(lst["id"], "tief", parent_iid=a["id"])
    # toggle trifft den verschachtelten Eintrag
    L.toggle_item(lst["id"], deep["id"])
    assert _get(lst["id"])["items"][0]["items"][0]["done"] is True
    # delete entfernt den verschachtelten Eintrag (Eltern bleibt)
    L.delete_item(lst["id"], deep["id"])
    a_now = _get(lst["id"])["items"][0]
    assert a_now["text"] == "a" and not a_now.get("items")


def test_delete_parent_removes_subtree(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    L.add_item(lst["id"], "kind", parent_iid=a["id"])
    L.delete_item(lst["id"], a["id"])
    assert _get(lst["id"])["items"] == []


def test_delete_unknown_raises(reg):
    lst = L.create_list("x")
    with pytest.raises(KeyError):
        L.delete_item(lst["id"], 999)


def test_nest_list_into_other(reg):
    src = L.create_list("quelle")
    s1 = L.add_item(src["id"], "s1")
    L.add_item(src["id"], "s1a", parent_iid=s1["id"])
    dest = L.create_list("ziel")
    d1 = L.add_item(dest["id"], "d1")

    node = L.nest_list(src["id"], dest["id"])

    lists = L.list_lists()
    # Quelle ist weg aus dem Top-Level, in der Ziel-Liste als Eintrag drin.
    assert all(x["id"] != src["id"] for x in lists)
    z = _get(dest["id"])
    names = [it["text"] for it in z["items"]]
    assert "d1" in names and "quelle" in names
    # Der eingeordnete Knoten trägt seine Unterpunkte als Kinder mit.
    nested = next(it for it in z["items"] if it["text"] == "quelle")
    assert nested["items"][0]["text"] == "s1"
    assert nested["items"][0]["items"][0]["text"] == "s1a"
    # ids des eingehängten Teilbaums sind im Ziel neu & kollisionsfrei.
    all_ids = [i["id"] for i in L._walk(z["items"])]
    assert len(all_ids) == len(set(all_ids))
    assert d1["id"] not in (nested["id"], nested["items"][0]["id"])
    assert node["id"] == nested["id"]


def test_nest_reids_against_legacy_dest_without_next_item(reg):
    # Alt-Datei: Ziel-Liste ohne next_item, ids 1/2 schon vergeben. Die
    # eingeordnete Quelle (ebenfalls ids ab 1) darf NICHT kollidieren.
    L._save([
        {"id": "l_ziel", "name": "ziel",
         "items": [{"id": 1, "text": "d1"}, {"id": 2, "text": "d2"}]},
        {"id": "l_quelle", "name": "quelle",
         "items": [{"id": 1, "text": "s1"}, {"id": 2, "text": "s2"}]},
    ])
    L.nest_list("l_quelle", "l_ziel")
    z = _get("l_ziel")
    all_ids = [i["id"] for i in L._walk(z["items"])]
    assert len(all_ids) == len(set(all_ids)), all_ids


def test_folder_not_directly_toggleable(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    L.add_item(lst["id"], "kind", parent_iid=a["id"])   # a wird Ordner
    with pytest.raises(ValueError):
        L.toggle_item(lst["id"], a["id"])               # Ordner nicht abhakbar
    # Blatt geht weiterhin
    leaf = _get(lst["id"])["items"][0]["items"][0]
    L.toggle_item(lst["id"], leaf["id"])
    assert _get(lst["id"])["items"][0]["items"][0]["done"] is True


def test_is_done_derived_for_folder(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    k1 = L.add_item(lst["id"], "k1", parent_iid=a["id"])
    k2 = L.add_item(lst["id"], "k2", parent_iid=a["id"])
    folder = _get(lst["id"])["items"][0]
    assert L.is_container(folder) is True
    assert L.is_done(folder) is False                   # noch nichts gehakt
    L.toggle_item(lst["id"], k1["id"])
    assert L.is_done(_get(lst["id"])["items"][0]) is False   # nur 1 von 2
    L.toggle_item(lst["id"], k2["id"])
    assert L.is_done(_get(lst["id"])["items"][0]) is True    # alle Kinder gehakt → Ordner gehakt


def test_is_done_nested_folders(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    b = L.add_item(lst["id"], "b", parent_iid=a["id"])      # a→b Ordnerkette
    leaf = L.add_item(lst["id"], "leaf", parent_iid=b["id"])
    top = _get(lst["id"])["items"][0]
    assert L.is_done(top) is False
    L.toggle_item(lst["id"], leaf["id"])
    assert L.is_done(_get(lst["id"])["items"][0]) is True    # tiefstes Blatt erledigt → alles


def test_leaf_is_done_is_own_flag(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    assert L.is_container(a) is False
    assert L.is_done(_get(lst["id"])["items"][0]) is False
    L.toggle_item(lst["id"], a["id"])
    assert L.is_done(_get(lst["id"])["items"][0]) is True


def test_rename_list_keeps_id(reg):
    lst = L.create_list("alt")
    out = L.rename_list(lst["id"], "neu")
    assert out["name"] == "neu"
    assert out["id"] == lst["id"]          # id bleibt stabil
    assert _get(lst["id"])["name"] == "neu"


def test_rename_list_empty_rejected(reg):
    lst = L.create_list("x")
    with pytest.raises(ValueError):
        L.rename_list(lst["id"], "   ")


def test_rename_item_nested(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    deep = L.add_item(lst["id"], "tief", parent_iid=a["id"])
    L.rename_item(lst["id"], deep["id"], "tiefer")
    assert _get(lst["id"])["items"][0]["items"][0]["text"] == "tiefer"


def test_move_item_out_to_other_list(reg):
    src = L.create_list("quelle")
    a = L.add_item(src["id"], "a")
    sub = L.add_item(src["id"], "a-sub", parent_iid=a["id"])
    dest = L.create_list("ziel")
    d1 = L.add_item(dest["id"], "d1")

    node = L.move_item(src["id"], a["id"], dest["id"])

    # Aus der Quelle raus …
    assert _get(src["id"])["items"] == []
    # … in die Ziel-Liste rein, Teilbaum mitgenommen.
    z = _get(dest["id"])
    moved = next(it for it in z["items"] if it["text"] == "a")
    assert moved["items"][0]["text"] == "a-sub"
    # ids im Ziel kollisionsfrei neu (nicht die der Quelle, nicht die von d1).
    all_ids = [i["id"] for i in L._walk(z["items"])]
    assert len(all_ids) == len(set(all_ids))
    assert d1["id"] not in (moved["id"], moved["items"][0]["id"])
    assert node["id"] == moved["id"]
    assert sub["id"] != moved["items"][0]["id"]  # neu vergeben


def test_move_item_under_parent_in_other_list(reg):
    src = L.create_list("quelle")
    a = L.add_item(src["id"], "a")
    dest = L.create_list("ziel")
    d1 = L.add_item(dest["id"], "d1")
    L.move_item(src["id"], a["id"], dest["id"], parent_iid=d1["id"])
    z = _get(dest["id"])
    assert z["items"][0]["items"][0]["text"] == "a"  # a hängt unter d1


def test_move_item_into_own_subtree_rejected(reg):
    lst = L.create_list("x")
    a = L.add_item(lst["id"], "a")
    sub = L.add_item(lst["id"], "sub", parent_iid=a["id"])
    # a unter seinen eigenen Unterpunkt hängen → Zyklus
    with pytest.raises(ValueError):
        L.move_item(lst["id"], a["id"], lst["id"], parent_iid=sub["id"])


def test_move_item_unknown_raises(reg):
    src = L.create_list("x")
    dest = L.create_list("y")
    with pytest.raises(KeyError):
        L.move_item(src["id"], 999, dest["id"])


def test_nest_into_self_rejected(reg):
    lst = L.create_list("x")
    with pytest.raises(ValueError):
        L.nest_list(lst["id"], lst["id"])


def test_nest_unknown_dest_raises(reg):
    lst = L.create_list("x")
    with pytest.raises(KeyError):
        L.nest_list(lst["id"], "l_gibtsnicht")
