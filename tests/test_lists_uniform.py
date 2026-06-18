"""
Knoten-Uniformität: ein Knoten ist ein Knoten — egal ob Top-Liste oder
tiefster Unterpunkt, dieselben Operationen müssen gehen.

Gespiegelt wird genau, was die TUI pro Taste tut:
  s  Kind anhängen   → add_item(parent=None|iid)
  r  umbenennen      → rename_list | rename_item
  p  Projekt         → set_project | set_item_project  (+ projects_tree())
  >  einordnen       → nest_list | move_item  (in JEDEN Knoten, beliebig tief)
  d  löschen         → delete_list | delete_item

Der Test läuft über ALLE Knoten eines mehrstufigen Baums (Tiefe 0..3) und
verlangt, dass jede dieser Operationen auf jeder Ebene gleich funktioniert.
Registry zeigt auf eine tmp-Datei — die echte data/lists.json bleibt unberührt.
"""
import pytest

import lists as L  # core/ via conftest auf sys.path


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    f = tmp_path / "lists.json"
    monkeypatch.setattr(L, "_REGISTRY", str(f))
    # BEIDE Registries auf tmp biegen — sonst zieht _load() die ECHTE
    # data/features.json mit rein und _save() schreibt die mutierten
    # Test-Daten dort hinein (hat real l_zentrale zerschossen → r7/r8/…).
    monkeypatch.setattr(L, "_FEATURES", str(tmp_path / "features.json"))
    monkeypatch.setattr(L, "_DATA_DIR", str(tmp_path))
    return f


def _get(lid):
    return next(x for x in L.list_lists() if x["id"] == lid)


# ── Operationen, dispatcht nach Knoten-Art — exakt wie die TUI ───────────────
# Ein Knoten ist ('list', lid) ODER ('item', lid, iid).

def op_add_child(node, text):
    if node[0] == "list":
        return L.add_item(node[1], text, None)
    return L.add_item(node[1], text, parent_iid=node[2])


def op_rename(node, text):
    if node[0] == "list":
        return L.rename_list(node[1], text)
    return L.rename_item(node[1], node[2], text)


def op_project(node, on=True):
    if node[0] == "list":
        return L.set_project(node[1], on)
    return L.set_item_project(node[1], node[2], on)


def op_place(node, target):
    """`>`: node in target einordnen. target-iid None = Listen-Top."""
    into = target[1]
    parent = None if target[0] == "list" else target[2]
    if node[0] == "list":
        return L.nest_list(node[1], into, parent)
    return L.move_item(node[1], node[2], into, parent)


# ── Forest-Helfer ────────────────────────────────────────────────────────────

def all_nodes():
    """Alle Knoten quer durch den Wald: Listen + Einträge jeder Tiefe."""
    nodes = []
    for l in L.list_lists():
        nodes.append(("list", l["id"]))
        for it in L._walk(l.get("items")):
            nodes.append(("item", l["id"], it["id"]))
    return nodes


def all_ids(lid):
    return [it["id"] for it in L._walk(_get(lid).get("items"))]


def build_forest():
    """alpha: a1, a2{ a2a{ a2a1 } }  (Tiefen 1,2,3) · beta: b1."""
    a = L.create_list("alpha")
    L.add_item(a["id"], "a1")
    a2 = L.add_item(a["id"], "a2")
    a2a = L.add_item(a["id"], "a2a", parent_iid=a2["id"])
    L.add_item(a["id"], "a2a1", parent_iid=a2a["id"])
    b = L.create_list("beta")
    L.add_item(b["id"], "b1")
    return a["id"], b["id"]


def _child_ids(node):
    """direkte Kinder-ids eines Knotens (Liste oder Eintrag)."""
    if node[0] == "list":
        items = _get(node[1]).get("items") or []
    else:
        it = L._find_item(_get(node[1]).get("items"), node[2])
        items = (it or {}).get("items") or []
    return [c["id"] for c in items if isinstance(c, dict)]


# ── Tests ────────────────────────────────────────────────────────────────────

def test_add_child_works_on_every_node(reg):
    build_forest()
    for node in all_nodes():
        before = set(_child_ids(node))
        child = op_add_child(node, "neu")
        after = set(_child_ids(node))
        # genau das neue Kind ist als DIREKTES Kind dieses Knotens dazugekommen
        assert after - before == {child["id"]}, f"add child scheiterte auf {node}"


def test_rename_works_on_every_node(reg):
    build_forest()
    for i, node in enumerate(all_nodes()):
        op_rename(node, f"r{i}")
        if node[0] == "list":
            assert _get(node[1])["name"] == f"r{i}"
        else:
            assert L._find_item(_get(node[1]).get("items"), node[2])["text"] == f"r{i}"


def _flatten_tree(nodes):
    """Projekt-Baum (projects_tree) rekursiv zu einer flachen Knotenliste."""
    out = []
    for n in nodes:
        out.append(n)
        out.extend(_flatten_tree(n.get("children") or []))
    return out


def test_project_flag_works_on_every_node_and_shows_in_projects(reg):
    build_forest()
    nodes = all_nodes()
    for node in nodes:
        op_project(node, True)
    # projects_tree() verschachtelt geflaggte Knoten; flach gerechnet muss
    # JEDER Knoten (Liste wie Eintrag jeder Tiefe) genau einmal auftauchen.
    flat = _flatten_tree(L.projects_tree())
    assert len(flat) == len(nodes), (len(flat), len(nodes))
    # und wieder ausschaltbar
    for node in nodes:
        op_project(node, False)
    assert L.projects_tree() == []


def test_einordnen_reaches_any_node_any_depth(reg):
    """`>` von jedem Knoten in jeden anderen — exemplarisch über Ebenen/Listen."""
    a, b = build_forest()
    a2 = next(i["id"] for i in _get(a)["items"] if i["text"] == "a2")
    a2a = _get(a)["items"][1]["items"][0]["id"]
    a2a1 = _get(a)["items"][1]["items"][0]["items"][0]["id"]
    b1 = _get(b)["items"][0]["id"]

    # 1) Eintrag (beta/b1) unter einen TIEFEN Eintrag (alpha, Tiefe 3) einordnen
    op_place(("item", b, b1), ("item", a, a2a1))
    assert b1 not in all_ids(b), "b1 nicht aus beta gelöst"
    a2a1_node = L._find_item(_get(a).get("items"), a2a1)
    assert any(c.get("text") == "b1" for c in a2a1_node.get("items", [])), "b1 nicht unter a2a1"

    # 2) Eintrag an einen Listen-Top einer ANDEREN Liste (parent None)
    moved = op_place(("item", a, a2), ("list", b))
    assert moved["id"] in [c["id"] for c in _get(b)["items"]], "a2 nicht auf beta-Top"
    # a2 nahm seinen Teilbaum (a2a) mit
    assert L._find_item(_get(b).get("items"), moved["id"]).get("items"), "Teilbaum verloren"


def test_einordnen_whole_list_into_deep_item(reg):
    a, b = build_forest()
    a2a = _get(a)["items"][1]["items"][0]["id"]
    # ganze Liste beta UNTER einen Tiefe-2-Eintrag von alpha einordnen
    node = op_place(("list", b), ("item", a, a2a))
    assert all(x["id"] != b for x in L.list_lists()), "beta noch im Top-Level"
    host = L._find_item(_get(a).get("items"), a2a)
    assert any(c["id"] == node["id"] for c in host.get("items", [])), "beta nicht unter a2a"


def test_einordnen_into_own_subtree_is_rejected(reg):
    a, _ = build_forest()
    a2 = next(i["id"] for i in _get(a)["items"] if i["text"] == "a2")
    a2a = _get(a)["items"][1]["items"][0]["id"]
    # in einen eigenen Nachkommen → Zyklus, muss abgelehnt werden
    with pytest.raises(ValueError):
        L.move_item(a, a2, a, parent_iid=a2a)
    # in sich selbst → ebenfalls abgelehnt
    with pytest.raises(ValueError):
        L.move_item(a, a2, a, parent_iid=a2)
    # Liste in sich selbst → abgelehnt
    with pytest.raises(ValueError):
        L.nest_list(a, a)


def test_ids_stay_unique_after_cross_tree_moves(reg):
    a, b = build_forest()
    a2 = next(i["id"] for i in _get(a)["items"] if i["text"] == "a2")
    a2a = _get(a)["items"][1]["items"][0]["id"]
    b1 = _get(b)["items"][0]["id"]
    op_place(("item", b, b1), ("item", a, a2a))   # b1 → alpha tief
    op_place(("item", a, a2), ("list", b))         # a2 (+Teilbaum) → beta
    for lid in (a, b):
        ids = all_ids(lid)
        assert len(ids) == len(set(ids)), f"id-Kollision in {lid}: {ids}"


def test_node_progress_uniform_for_list_container_and_leaf(reg):
    a, _ = build_forest()
    lst = _get(a)
    container = lst["items"][1]            # a2 (hat Kinder)
    leaf = lst["items"][0]                 # a1 (Blatt)
    # alle drei liefern ein (done, total)-Paar mit total >= 0
    for node in (lst, container, leaf):
        d, t = L.node_progress(node)
        assert isinstance(d, int) and isinstance(t, int) and 0 <= d <= t
    # Blatt zählt als genau 1 Punkt
    assert L.node_progress(leaf) == (0, 1)
