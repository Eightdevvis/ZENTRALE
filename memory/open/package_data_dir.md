# Packages copy the program per user because data lives next to the code

**Stand 2026-10-30:** Open, does not wait for Sasha. From the apt/pacman build,
23.10.2026 (`memory/betrieb/verteilung.md`).

The core finds its data as `<root>/data` (~17 modules) and resolves paths with
`realpath`. So the .deb/PKGBUILD starter copies the program once per user to
`~/.local/share/zentrale/paket/<version>/` with `data -> ../../data`. Clean
fix: take the data folder from one setting/env var, then the program can run
straight from `/usr/lib/zentrale`. Bigger core change.
