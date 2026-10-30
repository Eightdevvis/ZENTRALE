"""Developer kit — only in a checkout, never in the package (deploy/paket.txt
is a positive list and does not name it).

The fakes the tests use (fake cloud, fake systemd) and the developer installer
mode built on them (`zentrale dev`, memory/hub/building_kit_plan.md 5.4), so
what Sasha clicks through is what CI checks. Nothing here ever touches the
real installation: devkit/guard.py refuses every path and environment that
reaches it.
"""
