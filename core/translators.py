# core/translators.py
#
# The translator chain (memory/hub/building_kit_plan.md 2.3, build step 6):
# no major of a contract is ever switched off. A new major N ships with ONE
# translator to the previous major — `up` (N-1 → N) and `down` (N → N-1),
# pure functions with their own vectors in contracts/<name>/<N>/translate.json.
# Any two majors meet through the chain v1 ↔ v2 ↔ v3, so each new major adds
# one translator and never rewrites an old one.
#
# Today every contract is at major 1: the chain is empty. tests/test_contracts.py
# requires a translator here for every contracts/<name>/<N> with N ≥ 2 and
# runs its vectors both ways; the pattern itself is proven on a fixture
# contract with three majors (tests/daten/contracts_fixture/).
#
# Foundation (layer 1): stdlib only.

import copy

# contract name (folder in contracts/) → {major N: (up, down)}
TRANSLATORS = {}


class NoTranslator(LookupError):
    """A step of the chain is missing — never guessed."""


def register(name, major, up, down, registry=None):
    """Register the translator between `major - 1` and `major`."""
    if not isinstance(major, int) or major < 2:
        raise ValueError(f"a translator leads to a major ≥ 2, not {major!r}")
    (TRANSLATORS if registry is None else registry).setdefault(name, {})[major] = (up, down)


def steps(name, frm, to, registry=None) -> list:
    """The functions that carry a document from major `frm` to major `to`."""
    chain = (TRANSLATORS if registry is None else registry).get(name, {})
    out = []
    if to >= frm:
        for n in range(frm + 1, to + 1):
            if n not in chain:
                raise NoTranslator(f"{name}: no translator {n - 1} → {n}")
            out.append(chain[n][0])
    else:
        for n in range(frm, to, -1):
            if n not in chain:
                raise NoTranslator(f"{name}: no translator {n} → {n - 1}")
            out.append(chain[n][1])
    return out


def translate(doc, name, frm, to, registry=None):
    """`doc` in major `frm` → the same content in major `to` (a new object;
    the input is never changed)."""
    out = copy.deepcopy(doc)
    for f in steps(name, frm, to, registry):
        out = f(out)
    return out
