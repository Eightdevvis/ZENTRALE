# Tutor and map through the store

**Stand 2026-10-29:** Open, does not wait for Sasha. Found 25.10.2026 while
building store installs (`20717be`).

Budget (`Eightdevvis/budgeter`) is the first app installed through the store.
Tutor (`language-tutor`) and map (`zentrale-karte`) are still wired in by
hard-coded entries instead of going through the catalog + `app.toml`
install path. Move both onto the same path so there is one way to get an
app, then remove the hard-coded entries.
