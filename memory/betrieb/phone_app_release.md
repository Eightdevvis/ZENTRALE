# Phone app release (self-update)

How a new version of the phone app gets from a computer onto the phones.
What the app does with it: `memory/system/zen_mobile.md` "Self-update".
Cloud routes: `cloud/src/phone.ts`, `cloud/README.md`.

## The release key (since 2026-10-29)

- `~/.config/zentrale/android/zentrale-release.jks` (PKCS12, RSA 4096, alias
  `zentrale`, valid ~27 years) and `~/.config/zentrale/android/key.properties`
  (`storeFile`, `storePassword`, `keyAlias`, `keyPassword`; store and key
  password are the same, PKCS12 has only one). Both chmod 600, folder 700.
  Created on the laptop. SHA-256 of the certificate:
  `B7:65:9F:32:85:20:76:D1:A4:E0:17:7D:1D:65:CB:5F:EA:BA:43:04:84:6C:84:CE:A3:46:E7:AF:C3:9F:D3:26`.
- **Back up both files** (the .jks and the password from key.properties) into
  the ZENTRALE vault / KeePass. **Lose the key and no installed phone can
  ever update again** — Android only accepts an update signed with the same
  key; every phone would have to uninstall (losing its local data) and
  reinstall.
- Never in git (`mobile/android/.gitignore` ignores `key.properties`, `*.jks`,
  `*.keystore`; the files live outside the repo anyway).
- `mobile/android/app/build.gradle.kts` reads the file from
  `$ZENTRALE_ANDROID_KEY_PROPERTIES` or the default path above. A relative
  `storeFile` is relative to key.properties. Missing → the release build is
  signed with the debug key and Gradle prints a WARNING; the publish script
  refuses such an APK.
- Building on another machine (the PC, more RAM): copy both files there to the
  same path (or point the env var at them).

## One-time: uninstall and reinstall

The APKs on the phone so far were debug-signed. The first release-signed APK
cannot update over them (different key). Once: uninstall the app on the
phone, install the first release-signed APK by hand (USB / file), log in
again. The phone's local data goes with the uninstall; whatever was synced
through the Mitte comes back after logging in. From then on updates come by
themselves.

## Publishing a version

`scripts/publish_phone_app.py` (uses this computer's `zentrale login`
session; only accounts in the cloud var `BETREIBER_NAMEN` may publish):

1. **status** — pubspec version vs. the published one.
2. **bump** — raises the version code in `mobile/pubspec.yaml`
   (`version: <name>+<code>`) above both the local and the published code;
   `--name 0.2.0` changes the name too. Commit the pubspec change.
3. **build** — the release APK in `mobile/` (Flutter release build). Not on the
   3.8 GB laptop if it can be avoided. `publish --build` runs it, never by default.
4. **publish** `--notes "…"` — refuses an APK built from another version code
   (reads AGP's `output-metadata.json`, falls back to the file date), one
   signed with the debug key (checked with the JDK's keytool), and a version
   code not higher than the published one. Uploads the APK first, then the
   manifest. `--dry-run` checks everything and uploads nothing.

Phones see the new version on their next start (or with "Check for update"
in settings).

## Cloud deploy

The routes need a normal Worker deploy once (no D1 migration, R2 only):
in `cloud/`, `wrangler deploy`. Before that, publishing fails with 404.
`BETREIBER_NAMEN` must contain Sasha's account name (it says `sasha`).

## Limits

Workers Free takes request bodies up to 100 MB; the cloud accepts APKs up to
96 MiB (today ~55 MB). Two APKs are kept (current + previous), so ~110 MB of
the 10 GB free R2 storage. The storage brake (`BREMSE_SPEICHER`) applies.

## Google Play (later)

A Play build must not update itself: build it with Gradle property
`zentrale.distribution=play` (or env `ZENTRALE_DISTRIBUTION=play`) →
`BuildConfig.SELF_UPDATE = false`. A copy installed by Play
(`com.android.vending`) has self-update off at runtime anyway. When the Play
track exists, give it a `play` flavor whose manifest removes
`REQUEST_INSTALL_PACKAGES` (`tools:node="remove"`) — Play restricts that
permission.
