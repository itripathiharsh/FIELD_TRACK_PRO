# FieldTrack Pro 1.3.0 – production release

Prepared 22 Nov 2026 on branch `feature/android-premium-ui`. **Not published, not distributed, not device-tested.**

## Release artifact

| Item | Value |
|---|---|
| APK | `F:\Field track pro v2 for test\release-1.3.0\FieldTrackPro-1.3.0-6-release.apk` (outside every repository) |
| SHA-256 | `b4a7c557468035dfd4962fb08bcb1f7906fe33afef3267489372d7a8403831f8` |
| Size | 46,838,761 bytes |
| Package | `com.fieldtrackpro.android` |
| Version | **1.3.0** (versionCode **6**) |
| Signing | APK Signature Scheme v2 + v3, one signer: `CN=FieldTrack Pro Release, O=FieldTrack Pro, C=IN` (RSA 4096, valid until 2054-04-09) |
| Signing certificate SHA-256 | `ff:b2:12:57:b0:93:4c:b1:ac:66:ea:4c:d1:b4:6f:1f:10:a1:61:1b:1c:45:af:ba:6b:f5:b7:b9:63:50:36:5c` |
| Backend | `https://51-79-158-138.sslip.io/` |
| Update manifest | `https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json` |
| Min / target SDK | 26 / 35 |

The build is reproducible: rebuilding from the same commit gave a byte-identical APK.

## Release verification (done)

- `apksigner verify`: v2 + v3 verified, single signer, the certificate above.
- `aapt2 dump badging`: package, version 1.3.0 (6); not debuggable; no `usesCleartextTraffic`; `allowBackup=false`.
- Permissions: INTERNET, ACCESS_FINE/COARSE_LOCATION, POST_NOTIFICATIONS, CAMERA, REQUEST_INSTALL_PACKAGES (new, for updates), plus library-merged ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE, WAKE_LOCK, RECEIVE_BOOT_COMPLETED, FOREGROUND_SERVICE, c2dm RECEIVE, DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION.
- Every URL embedded in the dex: the production backend, the Vercel update and privacy URLs, OpenFreeMap, and library/documentation URLs only. **No** LAN, localhost, 10.0.2.2, Render, staging or demo-tile address.
- Release guard (Gradle): refuses non-https / LAN / localhost / Render backends, a manifest URL off the allowed host, and signing with the Android debug key.
- Unit tests: 494 total, 0 failures (37 opt-in: 36 screenshot renders, 1 release-artifact check that passed when run against this APK).
- Release-artifact check: the app's own manifest validation accepted `app-update.json`; its downloader fetched this APK, survived a dropped connection at 50 %, resumed with HTTP Range from byte 23,419,380 and matched the SHA-256.

## Not verified

- **Not installed or run on a device.** The local emulator needs the Android hypervisor driver (not installed) and no
  phone was connected. Installation, the update popup on a phone, the "Install unknown apps" step and the Android
  installer flow are covered only by unit tests and screenshots.
- `ApkVerifier` (package/version/certificate comparison against the installed app) uses Android's PackageManager; its
  comparison logic is unit-tested, the PackageManager calls are not.

## Signing key – IMPORTANT

- Keystore: `C:\Users\Admin\FieldTrackPro-Signing\fieldtrackpro-release.jks` (PKCS12, alias `fieldtrackpro`).
- Passwords: `C:\Users\Admin\FieldTrackPro-Signing\fieldtrackpro-signing.properties`. Never commit, email or paste it.
- The build finds it through `FIELDTRACK_SIGNING_PROPERTIES` (set in the git-ignored `local.properties`, or as an
  environment variable). Non-secret production settings are in the committed `release.properties`.

**Back it up now.** If this keystore or its password is lost, no future update can ever be installed over 1.3.0;
every user would have to uninstall and reinstall again.
1. Copy **both** files to at least two places you control that are not this PC (e.g. an encrypted USB drive kept
   offline and a company password manager / encrypted cloud vault).
2. Store the password separately from the keystore file where possible (e.g. the password in the password manager,
   the .jks on the USB drive).
3. Test a backup once: on another machine, `keytool -list -v -keystore fieldtrackpro-release.jks` must show
   SHA-256 `FF:B2:12:57:…:50:36:5C`.
4. Limit access to the people who publish releases.

## Existing users: one-time reinstall required

The APK currently in the field (1.2.0, versionCode 5) is signed with a **development (debug) key**
(certificate `0b0c796c…3c32ef`). Android will not install 1.3.0 over it ("App not installed" / package conflict).
This is a one-time change; after it, every update arrives in the app.

Before switching, for each user:
1. Open the old app with internet on and make sure nothing is waiting to sync (Profile shows no unsynced items /
   the offline banner is gone). **Uninstalling deletes anything not yet synced.**
2. Uninstall the old FieldTrack Pro.
3. Install 1.3.0 (below) and sign in again.

## Installing the first production version (per phone)

1. Open the APK link on the phone (after publishing: `https://fieldtrack-pro-rosy.vercel.app/downloads/FieldTrackPro.apk`).
2. When Android asks, allow the browser to install apps (Settings → Install unknown apps → your browser).
3. Install, open FieldTrack Pro, sign in.
4. The first time an update is offered, tap **Update now**, then **Allow installs** and switch on
   "Install unknown apps" for FieldTrack Pro; come back and Android shows its install screen. Tap **Update**.
   From then on updates need only **Update now** → **Update**.

## Publishing (only after your approval)

The publish bundle is ready at `F:\Field track pro v2 for test\release-1.3.0\vercel-public\`:

```
privacy.html                     -> https://fieldtrack-pro-rosy.vercel.app/privacy.html   (linked from the app)
account-deletion.html            -> https://fieldtrack-pro-rosy.vercel.app/account-deletion.html
downloads/app-update.json        -> update manifest for 1.3.0 (6)
downloads/releases/FieldTrackPro-1.3.0-6.apk
downloads/FieldTrackPro.apk      -> same APK for the landing page download button
downloads/apk-meta.json          -> landing page metadata (same format as today)
```

1. **Review `privacy.html` and `account-deletion.html`** (drafted from the app's data-safety record; the company
   name, contact route and retention wording need the owner's confirmation).
2. Copy the bundle into `fieldtrackpro-web/public/` **of the checkout that production is deployed from**
   (`feature/landing-page-apk`, worktree `_wt_landing`); `public/downloads/` is git-ignored there.
3. Deploy that web build to production the same way as the current deployment.
4. Check: `app-update.json` returns 200 with SHA-256 `b4a7c557…31f8`; the APK URL returns 200, 46,838,761 bytes and
   the same SHA-256; both pages open.

Publish `app-update.json` only together with the APK it points to, never before.

## Future releases

1. Increase `appVersionCode` (and `appVersionName`) in `app/build.gradle.kts`.
2. `./gradlew assembleRelease` (signing comes from the external file).
3. ```
   python tools/make_update_manifest.py --apk app/build/outputs/apk/release/app-release.apk \
     --out ../release-<version>/vercel-public/downloads \
     --expected-cert ffb21257b0934cb1ac66ea4cd1b46f1f10a1611b1c45afba6bf5b7b96350365c \
     --previous https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json \
     --note "…" [--mandatory] [--min-supported <code>]
   ```
4. Optionally run the release-artifact check:
   `./gradlew testDebugUnitTest --tests "*ReleaseArtifactVerificationTest*" -PreleaseManifest=<…>/app-update.json -PreleaseApk=<…>/releases/<apk>`
5. Copy into the web `public/downloads/`, deploy, verify the URLs and checksum. Users get the popup the next time
   they open the app.

## Other notes

- Push notifications (FCM) remain off, as in the current field app: there is no `google-services.json` for this
  project. In-app notifications still sync periodically.
- The outlet map now uses OpenFreeMap (free, no key) instead of the MapLibre demo style.
- Play Store requires target SDK 36 for new uploads after 31 Aug 2026; this sideloaded release targets 35.
