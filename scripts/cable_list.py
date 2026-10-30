#!/usr/bin/env python3
# scripts/cable_list.py
#
# Cable list for the data layer: which app has which files on THIS device,
# and do they go to the cloud? Read only — it never writes anything.
# This is the "data → sync" layer of the building kit
# (memory/hub/building_kit_plan.md, 1.2–1.4) before Schematix exists.
#
# Sasha's learning task (2026-10-30): the frame is done, three functions are
# left — look for "TODO". The script runs at every stage; unfinished parts
# show up as "TODO" in the table.

import os
import sys

# core/ modules import each other without a package name, so core/ itself
# has to be on the search path (same trick as the other scripts here).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))

import abgleich_apps      # noqa: E402  which apps THIS device syncs
import abgleich_auswahl   # noqa: E402  the positive list (the lock)
import apps               # noqa: E402  installed apps and their manifests
import eingebaute_apps    # noqa: E402  built-in apps, as plain data

TODO = "TODO"


def all_apps() -> list:
    """Every app that has data → list of dicts:
    {"name": "fokus", "title": "Listen", "patterns": ["data/lists.json", ...]}

    TODO 1 — two sources:
    - built-in apps: core/eingebaute_apps.py, the dicts EINGEBAUT and ERSATZ.
      Each entry may have "daten" → {"muster": [...], "abgleichen": bool}.
    - apps with their own manifest: apps.installiert() gives the manifests,
      apps.daten(manifest) gives the same {"muster", "abgleichen"} shape.
    Skip apps without data. If an app is in both, which one should win?
    (core/abgleich_apps.py, function tabelle(), answers that.)
    """
    return []


def device_choice(name: str, decisions) -> str:
    """What THIS device decided for app `name` → "yes", "no", "not asked",
    or "all (never chosen)".

    `decisions` is what abgleich_apps.entscheidungen() returned (main() already
    calls it). TODO 2 — read the comment at the top of core/abgleich_apps.py:
    there are three cases, and None is not the same as {}.
    """
    return TODO


def allowed(pattern: str) -> bool:
    """Is `pattern` on the positive list, i.e. may it EVER leave the device?

    TODO 3 — the list is abgleich_auswahl.ABGLEICH. The rule is strict: the
    pattern has to be there exactly as written (see the comment at the top of
    core/abgleich_apps.py, "deny by default").
    Return None while unfinished; the table then shows TODO.
    """
    return None


# ── frame: you don't need to change anything below ──────────────────────────

def _lock_column(patterns: list) -> str:
    marks = [allowed(p) for p in patterns]
    if any(m is None for m in marks):
        return TODO
    blocked = [p for p, ok in zip(patterns, marks) if not ok]
    return "all on the list" if not blocked else "blocked: " + ", ".join(blocked)


def _short(patterns: list, width: int = 38) -> str:
    text = ", ".join(patterns)
    return text if len(text) <= width else text[: width - 1] + "…"


def main() -> int:
    decisions = abgleich_apps.entscheidungen()
    rows = [("App", "Files", "→ Cloud", "Positive list")]
    for app in sorted(all_apps(), key=lambda a: a["name"]):
        rows.append((app["title"], _short(app["patterns"]),
                     device_choice(app["name"], decisions),
                     _lock_column(app["patterns"])))
    if len(rows) == 1:
        rows.append((TODO, "all_apps() returns nothing yet", "", ""))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    for i, row in enumerate(rows):
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip())
        if i == 0:
            print("  ".join("─" * w for w in widths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
