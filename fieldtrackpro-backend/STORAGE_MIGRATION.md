# Storage migration plan: Render local disk -> S3-compatible bucket

Everything the API stores as a file (outlet proof photos, visit photos/documents/orders,
visit signatures, payment proofs, requirement photos) goes through
`app/services/storage_service.py` and a provider chosen by `STORAGE_PROVIDER`
(`LOCAL` disk, or `MINIO` = any S3-compatible service). No business code touches file
paths, and the database stores only a relative `storage_key` (never an absolute URL).
Moving storage is therefore a data copy plus an environment change - no code change.

## 1. Choose a provider

| Provider | Endpoint (`MINIO_ENDPOINT`, host only, no `https://`) | `MINIO_REGION` | Notes |
|---|---|---|---|
| Cloudflare R2 | `<account-id>.r2.cloudflarestorage.com` | `auto` | No egress fees; good default. |
| AWS S3 | `s3.ap-south-1.amazonaws.com` (Mumbai) | `ap-south-1` | Use the region of the bucket. |
| DigitalOcean Spaces | `blr1.digitaloceanspaces.com` | `blr1` | Flat monthly price includes transfer. |
| Backblaze B2 (S3 API) | `s3.us-west-004.backblazeb2.com` | `us-west-004` | Cheap storage; use the endpoint shown for the bucket. |
| Self-hosted MinIO | `minio.internal:9000` | (empty) | You run and back it up yourself. |

Always set `MINIO_SECURE=true` for anything reachable over the internet.
Setting `MINIO_REGION` explicitly matters: without it the client calls
`GetBucketLocation` before signing, which least-privilege keys usually cannot do.

## 2. Create a PRIVATE bucket

* One bucket per environment (e.g. `fieldtrackpro-media-prod`). The production config
  check rejects bucket names containing `dev`.
* No public ACL, no "public access" / static-website setting, no public read policy.
* CORS is **not needed**: browsers and the Android app never talk to the bucket by
  themselves origin-to-origin; the API either streams bytes
  (`GET /customers/outlet-proofs/{id}/image`) or hands out a short-lived presigned GET URL.
* Enable versioning (S3/R2/B2) if you want protection from accidental overwrite.

## 3. Least-privilege credentials

Create an access key that can only reach this bucket. AWS S3 policy example:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::fieldtrackpro-media-prod"},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
     "Resource": "arn:aws:s3:::fieldtrackpro-media-prod/*"}
  ]
}
```

R2: create an API token with "Object Read & Write" scoped to the one bucket.

The app calls `bucket_exists` / `make_bucket` on first use. With a key that lacks
`ListBucket` / `CreateBucket`, the provider treats an `AccessDenied` answer as "the bucket
was provisioned for us" and carries on (a genuinely missing bucket then fails on the first
upload/download with `STORAGE_UPLOAD_ERROR` / `FILE_NOT_FOUND_IN_STORAGE`). Create the
bucket yourself in the provider console before the cutover.

## 4. Environment variables (production API)

```
STORAGE_PROVIDER=MINIO
MINIO_ENDPOINT=<host from the table above>
MINIO_ACCESS_KEY=<key id>
MINIO_SECRET_KEY=<secret>
MINIO_BUCKET=fieldtrackpro-media-prod
MINIO_SECURE=true
MINIO_REGION=<region from the table above>
MEDIA_SIGNING_SECRET=<already set; used only by the LOCAL provider's signed links>
```

Presigned GET URLs (`MinIOStorageProvider.generate_presigned_url`) are signed locally by
the minio client against the configured endpoint/region, so they work with R2 and S3 as
long as `MINIO_REGION` is set (verified by reading the code and unit tests with a fake
client; it has not been exercised against a live R2/S3 bucket from this repository).
Production startup refuses default credentials (`minioadmin`, ...), localhost endpoints and
dev bucket names.

## 5. Cutover sequence

Do this in a quiet window (field staff mostly offline). Uploads written to the OLD disk
after the final copy would be missed, so either freeze uploads or do the two-pass copy below.

1. **Prepare**: create bucket + key, set the new `MINIO_*` values in a *staging* copy of the
   service (or locally) and smoke-test an upload/download/presigned URL.
2. **Dry run** (writes nothing; prints counts only):
   ```
   export SRC_STORAGE_PROVIDER=LOCAL SRC_MEDIA_STORAGE_PATH=/path/to/old/media
   export DST_STORAGE_PROVIDER=MINIO DST_MINIO_ENDPOINT=... DST_MINIO_ACCESS_KEY=... \
          DST_MINIO_SECRET_KEY=... DST_MINIO_BUCKET=... DST_MINIO_SECURE=true DST_MINIO_REGION=...
   poetry run python scripts/migrate_storage.py --report dryrun.csv
   ```
   Read the counts: `would_copy` should equal the number of stored objects;
   `missing_source` rows (listed in the CSV) are DB rows whose file is already gone -
   decide per case, they can not be recovered by this script.
3. **Pass 1 (live system still running)**:
   `poetry run python scripts/migrate_storage.py --execute --report pass1.csv`
   Resumable: re-run it if interrupted; already-copied, checksum-verified objects are skipped.
4. **Freeze** uploads (maintenance window, or put the API in read-only mode / stop it briefly).
5. **Pass 2** (copies only what changed since pass 1) with
   `--execute --update-provider-column --report final.csv`. The script re-reads every object
   from the destination and compares SHA-256; any `verify_mismatch` / `copy_error` makes the
   exit code non-zero. Do not cut over until the report is clean (or each row is understood).
6. **Switch**: set `STORAGE_PROVIDER=MINIO` and the `MINIO_*` variables on the production API
   and redeploy/restart. Un-freeze.
7. **Smoke test**: open an outlet photo in the admin web, upload a new outlet proof from the
   app, view a visit photo and a payment proof, fetch a presigned URL; check the API log for
   `STORAGE_UNAVAILABLE` / `STORAGE_UPLOAD_ERROR`.
8. **Keep the source for 30 days** (the script never deletes anything). Only after that,
   and after a successful backup restore test, delete the old disk data.

## 6. Backups and lifecycle

* Turn on bucket versioning or provider-side replication; keep database backups and the
  bucket in step (rows point at keys).
* Add a lifecycle rule to expire noncurrent versions after 30-90 days.
* Photos are re-encoded to <= 1600 px JPEG (roughly 150-400 KB each) so storage stays small;
  the unattached-proof cleanup job deletes abandoned new-outlet photos after 48 hours.
* Rejected proofs are kept on purpose (audit trail).

## 7. Cost note

At ~300 KB per photo, 100,000 photos is about 30 GB: well under a few dollars a month on R2,
Spaces or B2 (R2 has no egress fee). S3 adds per-GB transfer charges for downloads. Because
the API streams or presigns on demand and the admin screens only fetch the images being
reviewed, request volume is small.

## 8. Rollback

Because the source is never modified or deleted, rollback is an environment change:
set `STORAGE_PROVIDER=LOCAL` (and the old `MEDIA_STORAGE_PATH`) and restart. Objects uploaded
to the bucket after the cutover would not exist on the old disk: run the script the other way
(`SRC_*` = bucket, `DST_*` = old disk, `--execute`) before rolling back if any uploads
happened. `outlet_proofs.storage_provider` records which provider holds each proof; if you
rolled back, re-run `--update-provider-column` with the `DST_*` pointing at the old provider.

## 9. Script reference

`scripts/migrate_storage.py` - dry-run by default, `--execute` to copy, `--report file.csv`,
`--limit N`, `--update-provider-column`. Source and destination are configured only via
`SRC_*` / `DST_*` variables (`*_STORAGE_PROVIDER`, `*_MEDIA_STORAGE_PATH`, `*_MINIO_ENDPOINT`,
`*_MINIO_ACCESS_KEY`, `*_MINIO_SECRET_KEY`, `*_MINIO_BUCKET`, `*_MINIO_SECURE`,
`*_MINIO_REGION`). It reads the database named by `DATABASE_URL`, prints counts only (never
keys or credentials), and covers `outlet_proofs`, `visit_media`, `visit_signatures`,
`payment_proofs` and `customer_requirements.photo_storage_key`
(a test fails if a new `*storage_key*` column is added to a model without being listed).
