# Tutor manifest needs `[daten]`

**Stand 2026-10-30:** Open, does not wait for Sasha. Found 23.10.2026 when the
cloud became an app (`memory/hub/cloud_app.md`).

`language-tutor/app.toml` has no `[daten]` section, so
`core/eingebaute_apps.py` carries a fallback entry for the tutor's patterns.
Add to the tutor repo:

```toml
[daten]
muster = ["tutor/data/tutor_config.json", "tutor/data/aktiver_stand",
          "tutor/data/staende/**", "tutor/data/es/**"]
abgleichen = true
```

Then remove the fallback in `core/eingebaute_apps.py` and its test case.
