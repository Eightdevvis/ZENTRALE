# test_pruefstand_isolation is red on main

**Stand 2026-10-29:** Open, does not wait for Sasha. Reported 25.10.2026 by
the store-install agent: in the full suite (5621 green, 1 skipped, 1 red)
`test_pruefstand_isolation` fails on the `SYSTEMD_USER` setting — on
`origin/main` as well, so not caused by the store work. Not looked into yet.
