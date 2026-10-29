# test_pruefstand_isolation is red on main

**Stand 2026-10-29:** Open, does not wait for Sasha. Reported 25.10.2026 by
the store-install agent: in the full suite (5621 green, 1 skipped, 1 red)
`test_pruefstand_isolation` fails on the `SYSTEMD_USER` setting — on
`origin/main` as well, so not caused by the store work. Still red on
29.10.2026 (`9dd72e3`).

Cause: `tests/conftest.py` (~406) redirects `ZENTRALE_SYSTEMD_USER_DIR`, but
`scripts/pruefstand_teile/umgebung.py` does not. The test
(`tests/test_pruefstand_isolation.py`) demands that the test bench redirects
every `ZENTRALE_<NAME>_DIR` the tests redirect, otherwise the bench writes
into Sasha's real data. Fix: add `SYSTEMD_USER` in `umgebung.py`.
