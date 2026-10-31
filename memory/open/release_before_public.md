# Before ZENTRALE goes public

**Stand 2026-10-30:** Open, **waits for Sasha** (decisions). Distribution is
prepared but switched off (`deploy/verteilung.toml`, `oeffentlich = false`;
`memory/betrieb/verteilung.md`). Pillars: anonymity, privacy, open source
(`memory/leitbild.md`).

- **Licence:** proposal AGPL-3.0 (today `LicenseRef-alle-Rechte-vorbehalten`).
- **Maintainer** for .deb/PKGBUILD (today the git mail).
- **Public repo name** (placeholder `OWNER/zentrale`) and where the apt repo
  lives (GitHub Pages or R2, signed); own pacman repo besides the AUR?
- **Personal data out of the package:** persona, prompts and parts of the core
  still name Sasha (see `memory/hub/produkt_inventur.md`).
- **Legal:** copyright of AI-written code, privacy (voice, conversations,
  health), provider terms.
- **Signature** for our own packages ([package_signing.md](package_signing.md)).
- Then: `oeffentlich = true`; `server/src/paket.ts` needs a code-less route if
  the cloud should serve public packages.
