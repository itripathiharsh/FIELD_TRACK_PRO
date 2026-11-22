# In-app updates

Status: implemented in the app (1.3.0+) and tested locally. **Nothing is published or deployed yet.**

## 1. Architecture

```
Vercel (existing free project, fieldtrack-pro-rosy.vercel.app)      FieldTrack Pro app
  /downloads/app-update.json   <-- GET on every app open ----------  AppUpdateController
  /downloads/releases/FieldTrackPro-<name>-<code>.apk  <-- download   (UpdateNetwork, own HTTPS-only client)
                                                                      verify size + SHA-256 + package + version + signing cert
                                                                      Android PackageInstaller -> system confirmation
```

- **No backend change, no API change.** The manifest and APKs are static files on the Vercel site that already
  serves the landing page and `FieldTrackPro.apk`. The landing page's `apk-meta.json` is left as it is.
- **Manifest** (`app-update.json`): `versionCode`, `versionName`, `apkUrl`, `apkSha256`, `apkSizeBytes`,
  `minSupportedVersionCode`, `mandatory`, `releaseNotes`, `publishedAt`, `packageName`, `schema`.
- **App code** (`app/src/main/java/com/fieldtrackpro/android/update/`):
  - `UpdatePolicy`: decisions (never a downgrade; mandatory if flagged or installed < minimum; "Later" snooze).
  - `UpdateManifest`: parsing and validation (https, allowed host, SHA-256 format, package, minimum ≤ version).
  - `UpdateNetwork`: manifest fetch and resumable APK download; refuses any non-https or non-allowed host on
    every hop, including redirects; never sends the login token.
  - `ApkVerifier`: package name, exact versionCode, newer than installed, **same signing certificate** as the
    installed app.
  - `UpdateInstaller` + `UpdateInstallReceiver`: Android PackageInstaller session; on Android 12+ the session
    requires user action, so Android always shows its confirmation.
  - `AppUpdateController` (state machine) and `AppUpdateViewModel`; UI in `ui/screens/update/UpdateScreens.kt`.
- **Config** (`app/build.gradle.kts`): `UPDATE_MANIFEST_URL` (default
  `https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json`; blank disables) and `UPDATE_ALLOWED_HOSTS`
  (default `fieldtrack-pro-rosy.vercel.app`). Release builds fail if the manifest URL is not https on an allowed host.

## 2. Publishing a new version

1. Bump `appVersionCode` (must increase) and `appVersionName` in `app/build.gradle.kts`; build and sign the APK
   **with the same key as the installed app**.
2. Generate the release files:
   ```
   python tools/make_update_manifest.py --apk <signed.apk> --out build/update-release \
       --note "What changed 1" --note "What changed 2" \
       --previous https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json \
       --expected-cert <signer SHA-256>  [--mandatory] [--min-supported <versionCode>]
   ```
   It refuses a non-increasing versionCode, a wrong package and a different signing certificate, and writes
   `app-update.json` plus `releases/FieldTrackPro-<name>-<code>.apk`.
3. Copy both into `fieldtrackpro-web/public/downloads/` (optionally also overwrite `FieldTrackPro.apk` and
   `apk-meta.json` for the landing page), then deploy the web project to production (needs your approval each time).
4. Users get it the next time they open the app. To pull a bad release, re-publish the previous manifest (the app
   never downgrades; affected users get the next fixed version).

APK files are immutable (versioned names), so a download in progress is never corrupted by a new upload, and
`Cache-Control: max-age=0, must-revalidate` (already set for `/downloads/*.apk`) keeps the manifest fresh.

## 3. What users see

- **On every app open** (and when returning to the app, at most hourly): a check of the manifest.
- **Optional update**: popup with version, size, release notes, **Update now** and **Later**. "Later" hides that
  version for 24 h (72 h after the third "Later"); a newer version is offered immediately.
- **Mandatory update** (flag, or installed version below `minSupportedVersionCode`): a full-screen "Update
  required" page replaces the app. Back leaves the app. It stays enforced after a restart even offline (the last
  manifest is cached). Unsynced items stay on the phone and sync after the update.
- **Update now**: progress bar (MB and %), verification, then Android's own install screen. Interrupted downloads
  resume where they stopped (HTTP Range) after **Retry**.
- After installing, Android shows "App installed" with **Open**; the user opens the new version normally.

## 4. Android permissions

| Permission | Why |
|---|---|
| `REQUEST_INSTALL_PACKAGES` (manifest) | Lets FieldTrack Pro hand an APK to the system installer. The user must also switch on **Settings → Install unknown apps → FieldTrack Pro** once; the app opens that setting and continues when the user comes back. |
| `INTERNET` (already present) | Manifest and APK download. |

No storage permission: downloads go to the app's private cache (`cache/updates/`), old versions are deleted.
Android always asks the user to confirm an install, and refuses an update signed with a different key.

## 5. Security summary

HTTPS only, host allow-list on every request and redirect, SHA-256 and size check, package/version/signature check
before installing, never a downgrade, no login token sent to the download host, the system installer with a
mandatory confirmation, invalid or tampered manifests ignored. Residual risk: whoever controls the Vercel
project could publish a misleading manifest (e.g. flag an update as mandatory), but cannot get a tampered APK
installed without the signing key.

## Rollout notes (decisions for you)

- The APK currently in the field (1.2.0) has no updater, so **1.3.0 must be installed manually once**; from then on
  updates arrive in the app.
- The field APK and this build are signed with the **debug key of one development PC**
  (certificate SHA-256 `0b0c796c…3c32ef`). Updates only work while that same key signs every release. Moving to a
  proper release key later forces every user to uninstall and reinstall once (losing unsynced items on the phone).
  The best moment to switch is the manual 1.3.0 rollout, after everyone has synced.
- Users' phones must allow installs from FieldTrack Pro (one-time setting); some company-managed phones block it.
