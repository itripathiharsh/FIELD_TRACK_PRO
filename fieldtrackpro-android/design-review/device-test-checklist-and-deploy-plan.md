# Physical-device test checklist and production deployment plan (NOT executed)

Legend: AV = automated verified (JVM tests / local API); PD = physical device verified; P = pending; F = failed.
No physical device was available in this work. Every PD column is **Pending**.

## A. Device checklist

| # | Test | Automated | Physical device |
|---|---|---|---|
| 1 | Camera permission (grant, deny, recover from Settings) | P | P |
| 2 | Camera capture (no "photo could not be processed") | AV (downsample pipeline: normal, small, EXIF-rotated, corrupt/missing) | P |
| 3 | Image preview after capture | P (UI present) | P |
| 4 | Retake | P | P |
| 5 | Continue | P | P |
| 6 | Upload success | AV (API, local) | P |
| 7 | Upload retry after network interruption | P (offline queue exists) | P |
| 8 | First outlet GPS registration | AV (local API, simulated coordinates) | P |
| 9 | First registration auto-accept | AV (pytest) | P |
| 10 | No automatic check-in after registration | AV (pytest: 0 visits) | P |
| 11 | Later GPS change suggestion stays pending | AV (pytest) | P |
| 12 | Admin approval updates coordinates | AV (pytest) | P |
| 13 | Admin rejection keeps old coordinates | AV (pytest) | P |
| 14 | Normal check-in is GPS only | AV (pytest: no photo field) | P |
| 15 | Inside geofence succeeds | AV (pytest) | P |
| 16 | Outside geofence rejected with clear message | AV (pytest) | P |
| 17 | Visit media preview (thumbnails, pinch-zoom, PDF page) | P (compiles; no screenshot test yet) | P |
| 18 | Payment proof preview | P (not changed in this pass) | P |
| 19 | Outlet photo preview | P (not changed in this pass) | P |
| 20 | Payment with valid brand | AV (brand-rule unit tests) | P |
| 21 | Payment with no available brands (message shown) | AV (rules); UI P | P |
| 22 | Login with network interruption (plain message) | P | P |
| 23 | App background/foreground during camera/upload | P | P |
| 24 | App restart and session recovery | P | P |

Also on the phone: shutter button clear of the gesture bar on 3-button and gesture navigation; GPS off, GPS permission denied, accuracy above 30 m.

## B. Production deployment plan (do not run without separate approval)

Known facts: production backend https://51-79-158-138.sslip.io. Production DB revision and running backend release were not read (production must not be touched), so they are **unknown here**.

1. Record the current production backend commit and `alembic current` (read-only, from the server).
2. Take a full `pg_dump` of the production database and verify it restores into a scratch database.
3. Back up the current backend directory/release tag and the uploaded-media volume.
4. Required migration: `a7f1r5t10c4t` (adds `outlet_proofs.auto_accepted`, boolean not null default false; it chains after `s1c0p3d1st5r`). Confirm production is at `s1c0p3d1st5r` first.
5. Deploy backend, run `alembic upgrade head`, restart the service. Setting `OUTLET_PROOF_FIRST_LOCATION_AUTO_ACCEPT=false` disables auto-accept without a rollback.
6. Health checks: `/health`, login, `GET /customers/{id}`, one outlet-proof upload on a test outlet, `GET /brands`, one payment with a valid brand.
7. Android: publish the release APK and update manifest only after step 6 passes and the device checklist is done.
8. Rollback backend: redeploy the previous release. The new column is additive and harmless to old code, so no downgrade is required. If needed: `alembic downgrade s1c0p3d1st5r` drops the column.
9. Rollback APK: keep the previous APK and manifest entry; point the manifest back to it.
10. Data recovery: restore the pg_dump only if data was corrupted. Auto-accepted locations can be reviewed from `outlet_proofs.auto_accepted = true`.
