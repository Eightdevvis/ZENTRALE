"""The contract folder and the translator chain (contracts/README.md,
memory/hub/building_kit_plan.md 2.3/2.4, build step 6).

  - contracts/<name>/<major>/ is well formed and listed in the README;
  - every major ≥ 2 has a translator in core/translators.py whose vectors
    (translate.json) hold both ways;
  - the chain itself (1 ↔ 2 ↔ 3) on a fixture contract.
"""
import json
import os
import re

import pytest

import translators

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS = os.path.join(ROOT, "contracts")
FIXTURE = os.path.join(ROOT, "tests", "daten", "contracts_fixture")


def _majors(root):
    """→ {name: [majors]} of a contracts folder."""
    out = {}
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isdir(p):
            out[name] = sorted(int(m) for m in os.listdir(p)
                               if m.isdigit() and os.path.isdir(os.path.join(p, m)))
    return out


def check_contracts(root, registry):
    """The pattern for every contract folder: majors 1..N without gaps, no
    empty major, and for N ≥ 2 a translator whose cases hold both ways."""
    for name, majors in _majors(root).items():
        assert re.fullmatch(r"[a-z][a-z0-9-]+", name), name
        assert majors == list(range(1, len(majors) + 1)), f"{name}: majors {majors}"
        for m in majors:
            folder = os.path.join(root, name, str(m))
            assert os.listdir(folder), f"{name}/{m} is empty"
            if m == 1:
                continue
            assert m in registry.get(name, {}), f"{name}/{m}: no translator {m - 1} ↔ {m}"
            with open(os.path.join(folder, "translate.json"), encoding="utf-8") as f:
                cases = json.load(f)["cases"]
            assert cases, f"{name}/{m}: translate.json has no cases"
            up, down = registry[name][m]
            for c in cases:
                assert up(json.loads(json.dumps(c["old"]))) == c["new"], (name, m, c)
                assert down(json.loads(json.dumps(c["new"]))) == c["old"], (name, m, c)


def test_contract_folders_hold_and_every_major_has_a_translator():
    check_contracts(CONTRACTS, translators.TRANSLATORS)


def test_readme_lists_every_contract():
    with open(os.path.join(CONTRACTS, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    for name in _majors(CONTRACTS):
        assert f"`{name}`" in readme, name


def test_no_vector_copies_left_behind():
    """One file per vector set — the phone reads contracts/ directly."""
    for name in ("konto_testvektoren.json", "mitte_testvektoren.json",
                 "kalender_testvektoren.json", "calendar_colour_vectors.json"):
        assert not os.path.exists(os.path.join(ROOT, "mobile", "test", "daten", name))
        assert not os.path.exists(os.path.join(ROOT, "tests", "daten", name))


# ── The chain, on a fixture contract with three majors ─────────────────

def _up2(d):
    d = dict(d, format=2)
    d["title"] = d.pop("name")
    return d


def _down2(d):
    d = dict(d, format=1)
    d["name"] = d.pop("title")
    return d


def _up3(d):
    return dict(d, format=3, title={"text": d["title"], "lang": "de"})


def _down3(d):
    return dict(d, format=2, title=d["title"]["text"])


@pytest.fixture
def chain():
    reg = {}
    translators.register("example", 2, _up2, _down2, registry=reg)
    translators.register("example", 3, _up3, _down3, registry=reg)
    return reg


def test_fixture_contract_follows_the_pattern(chain):
    check_contracts(FIXTURE, chain)


def test_missing_translator_fails_the_pattern(chain):
    del chain["example"][3]
    with pytest.raises(AssertionError, match="no translator 2"):
        check_contracts(FIXTURE, chain)


def test_chain_walks_every_step_both_ways(chain):
    with open(os.path.join(FIXTURE, "example", "1", "item.json"), encoding="utf-8") as f:
        v1 = json.load(f)
    v3 = translators.translate(v1, "example", 1, 3, registry=chain)
    assert v3 == {"format": 3, "title": {"text": "Milch", "lang": "de"}, "done": False}
    assert translators.translate(v3, "example", 3, 1, registry=chain) == v1
    assert translators.translate(v1, "example", 1, 1, registry=chain) == v1
    assert v1 == {"format": 1, "name": "Milch", "done": False}      # input untouched
    with pytest.raises(translators.NoTranslator):
        translators.translate(v1, "example", 1, 4, registry=chain)
    with pytest.raises(ValueError):
        translators.register("example", 1, _up2, _down2, registry=chain)
