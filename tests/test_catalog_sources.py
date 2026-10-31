"""Catalog v2 (memory/hub/app_delivery_plan.md step 3): an app item points
at one or more `sources` ("<kind>:<ref>"), may carry a dock card, and the
old `downloadUrl` reads as one `git` source. The node picks by its setting
`source_order`."""
import json

import pytest

import ai_config
import app_installation
import app_register
import shop

TWO = {"@type": "SoftwareApplication", "@id": "zentrale://shop/apps/pdf", "identifier": "pdf",
       "name": "PDF", "description": "t", "category": "apps",
       "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
       "additionalProperty": [
           {"@type": "PropertyValue", "name": "app_name", "value": "pdf"},
           {"@type": "PropertyValue", "name": "sources",
            "value": ["flatpak:org.gnome.Papers", "git:https://example.org/x/pdf.git"]},
           {"@type": "PropertyValue", "name": "dock_card",
            "value": {"start": "flatpak run org.gnome.Papers", "ansichten": ["fenster"]}}]}


def _catalog(tmp_path, monkeypatch, *items):
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        k = json.load(f)
    for i, it in enumerate(items):
        k["itemListElement"].append({"@type": "ListItem", "position": 100 + i, "item": it})
    p = tmp_path / "katalog.jsonld"
    p.write_text(json.dumps(k), encoding="utf-8")
    monkeypatch.setenv("ZENTRALE_SHOP_KATALOG", str(p))
    return k


def test_old_catalog_is_unchanged_in_the_api():
    from ui.app import app
    app.config.update(TESTING=True)
    with open(shop.STANDARD_KATALOG, encoding="utf-8") as f:
        raw = json.load(f)
    served = app.test_client().get("/api/shop").get_json()
    assert [el["item"] for el in served["itemListElement"]] == \
        [el["item"] for el in raw["itemListElement"]]


def test_download_url_reads_as_one_git_source():
    budget = shop.stueck("apps", "budget")
    assert app_register.sources(budget) == [
        {"kind": "git", "ref": "ssh://git@github.com/Eightdevvis/budgeter.git"}]
    assert app_register.dock_card(budget) is None
    assert app_register.sources(shop.stueck("apps", "cloud")) == []      # built in


def test_item_with_two_sources_is_picked_by_the_node_setting(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch, TWO)
    it = shop.stueck("apps", "pdf")
    assert app_register.dock_card(it)["start"] == "flatpak run org.gnome.Papers"
    both = ("flatpak", "git")
    assert app_register.pick_source(it, both)["kind"] == "flatpak"      # default order
    ai_config.set_override(app_register.SOURCE_ORDER, ["git"])
    try:
        assert app_register.pick_source(it, both) == {"kind": "git", "ref": "https://example.org/x/pdf.git"}
    finally:
        ai_config.set_override(app_register.SOURCE_ORDER, None)
    monkeypatch.setenv("ZENTRALE_SOURCE_ORDER", "git, flatpak")
    assert app_register.pick_source(it, both)["kind"] == "git"
    assert app_register.pick_source(it, ("flatpak",))["kind"] == "flatpak"   # only what the node has
    assert app_register.pick_source(it, ("apt",)) is None


def test_without_an_installer_for_any_source_install_says_so(tmp_path, monkeypatch):
    only_flatpak = json.loads(json.dumps(TWO))
    only_flatpak["additionalProperty"][1]["value"] = ["flatpak:org.gnome.Papers"]
    _catalog(tmp_path, monkeypatch, only_flatpak)
    with pytest.raises(app_installation.InstallFehler) as e:
        app_installation.laden("zentrale://shop/apps/pdf")
    assert e.value.code == 501 and "flatpak" in str(e.value)


@pytest.mark.parametrize("sources, card", [
    ("flatpak:x", None),                       # not a list
    ([], None),
    (["no-colon"], None),
    (["Flat Pak:x"], None),
    (["git:ftp://x/y.git"], None),              # git ref checked like downloadUrl
    (["flatpak:x"], ["start"]),                 # card not an object
    (["flatpak:x"], {"start": 1}),
    (["flatpak:x"], {"ansichten": "fenster"}),
])
def test_broken_sources_or_dock_card_break_the_catalog(tmp_path, monkeypatch, sources, card):
    bad = json.loads(json.dumps(TWO))
    bad["additionalProperty"][1]["value"] = sources
    bad["additionalProperty"][2]["value"] = card
    _catalog(tmp_path, monkeypatch, bad)
    with pytest.raises(shop.ShopFehler) as e:
        shop.katalog()
    assert e.value.code == 503
