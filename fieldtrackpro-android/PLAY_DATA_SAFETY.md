# FieldTrack Pro - Google Play Data Safety helper

Package `com.fieldtrackpro.android`, version 1.1.0 (versionCode 4). Source of truth for the Play Console
"Data safety" and "App content" forms. Re-check it whenever a permission, SDK or API field changes.
Items marked **OWNER** must be supplied or confirmed by the owner.

## Summary answers

| Question | Answer |
|---|---|
| Collects user data? | Yes (it is a business app for employees of one company) |
| Shares data with third parties? | No (see "Sharing" below; the company backend and Firebase Cloud Messaging are service providers acting for the company) |
| Encrypted in transit? | Yes - all traffic is HTTPS (cleartext is not permitted in release builds) |
| Data stored on device encrypted? | Yes - tokens and the offline queue use Keystore-backed EncryptedSharedPreferences; photos live in app-private storage; app data is excluded from cloud backup and device transfer |
| Users can request deletion? | Yes - in the app (Profile > Request account deletion, asks for the current password) and on the web (`DELETION_URL`, a release-build requirement) |
| Independent security review? | Not claimed |
| Ads / analytics / crash-reporting SDK? | None. No advertising ID, no Crashlytics/Analytics ("crash-free" means no crash data is collected) |

## Data types collected

| Play category / type | What exactly | Required? | Purpose | Shared? |
|---|---|---|---|---|
| Location > Precise location | GPS fix at user-initiated capture only: check-in, check-out, start/end day, outlet position or outlet proof photo, "suggest location". The map screen shows the live position while it is open (not sent). Accuracy and a mock-location flag travel with the fix. No background collection. | Required for check-in/out | App functionality (verify the rep is at the outlet), fraud prevention | No |
| Photos and videos > Photos | Outlet / visit / order photos, payment-proof photos, live outlet-proof photo. Payment proofs are downsampled (max 1600 px, JPEG q82) before upload. | Optional per feature, required for proof flows | App functionality | No |
| Personal info > Name, Email address, Phone number | Employee name, work email, mobile number, employee code (account and profile) | Required | Account management, app functionality | No |
| Personal info > Other info | Employee code, territory, role; handwritten **signature** images captured at a visit | Required (code) / per feature (signature) | App functionality | No |
| Financial info > Payment info (records, not card data) | Amounts, method, cheque no., UTR reference collected from customers and entered by the rep. No card numbers, no payment processing in the app. | Per feature | App functionality | No |
| App info and performance / Device or other IDs | Device **model** (Build.MODEL) attached to outlet-proof uploads; FCM registration token (push notifications) | Model: required for outlet proof; token: optional (push) | Fraud prevention / app functionality | FCM token goes to Google FCM (service provider) |
| App activity | Visit, check-in/out, order, requirement-form and payment records created by the rep | Required | App functionality | No |

Not collected: contacts, SMS, call logs, files/docs outside the app, microphone, calendar, health, web browsing, advertising ID, background location, gallery contents (photo pickers return only the chosen file).

## Sharing

No data is sold or shared for advertising. Data goes only to the company's own FieldTrack Pro backend (HTTPS) and, for push
notifications, the device token goes to Firebase Cloud Messaging. Map tiles are fetched from the configured tile server
(`MAPLIBRE_TILE_URL`); the request contains map coordinates of the viewport (see OWNER note).

## Deletion

- In app: Profile > Request account deletion. The user re-enters the current password; the backend deletes the account and
  anonymises personal data (business and financial records are retained as required by law); the app then erases
  all local data for that user (tokens, offline queue, conflicts, proof photos, drafts, prefs, scheduled work).
- On the web: `DELETION_URL` (release builds fail without an https URL). **OWNER:** the page must exist, name the app and
  the developer, state what is deleted and what is retained, and give the retention period.
- Privacy policy: `PRIVACY_POLICY_URL` (also linked from the app). **OWNER:** must describe everything in this file.

## Permissions and rationales (declared in the merged release manifest)

No `ACCESS_BACKGROUND_LOCATION`, no `READ_MEDIA_*`/storage permissions.

| Permission | In-app disclosure shown before the system prompt | Why |
|---|---|---|
| `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION` | Yes (LOCATION) | Verify presence at the outlet on check-in/out, record outlet GPS, show nearby outlets. Captured only on tap and while the map is open. |
| `CAMERA` | Yes (CAMERA); `uses-feature camera required=false` | Outlet, order and payment-proof photos taken on demand. |
| `POST_NOTIFICATIONS` | Yes (NOTIFICATIONS), requested after sign-in | Visit assignments and plan changes. |
| `INTERNET`, `ACCESS_NETWORK_STATE` | n/a (normal) | API calls, sync when back online. |
| `FOREGROUND_SERVICE`, `WAKE_LOCK`, `RECEIVE_BOOT_COMPLETED` | n/a (library-merged: WorkManager / FCM / geofence receiver) | Resilient upload retry and push delivery. |

If a user permanently denies a permission the app shows a rationale with an **Open app settings** action
(camera, location, notifications).

## Play "App access" note for reviewers

The app is login-only (no public sign-up). Reviewers need working credentials: **OWNER must supply a demo
employee account (email or mobile + password), pre-loaded with a few assigned outlets/visits, and enter it under
Play Console > App content > App access.** Suggested note: "Sign in with the provided EMPLOYEE account. Use Today's
Visits > open a visit > Check in (allow location) > Collect payment (allow camera). Location and camera prompts are
preceded by an in-app disclosure. Account deletion: Profile > Request account deletion (needs the account password)."
A demo account must not hold real client data. The account may be flagged "must change password" by the backend;
the app shows a full-screen "Set a new password" screen first in that case, so supply credentials with that flag cleared.

## Other App content declarations (suggested)

- Target audience: 18+ (business app). Not a children's app. Ads: none. Government/news/health/finance-app declarations: not applicable
  (it records payment *collections* but is not a financial services app - **OWNER** to confirm the "Financial features" answer).
- Content rating questionnaire: no user-generated public content, no violence, no purchases.
- Target API: currently 35. Play requires 36 for new apps/updates after 2026-08-31 (see engineering notes in the build report).
