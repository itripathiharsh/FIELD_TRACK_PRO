# Secret Rotation Record — FT-043

**Date:** 2026-08-08
**Phase:** 0 (safety)
**Rule:** No secret value — old or new — is recorded in this document, in any other
document, in any log, or in any source file.

---

## 1. Exposure assessment

### What was exposed

`fieldtrackpro-backend/.env` (present in the working tree) contained real, working values for:

| Key | Nature | Status |
|---|---|---|
| `DATABASE_URL` | PostgreSQL superuser (`postgres`) credentials for `fieldtrackpro_dev` | **ROTATED** |
| `JWT_SECRET` | HS256 signing key for all access tokens | **ROTATED** |

Non-sensitive keys also present: `ENVIRONMENT`, `API_V1_PREFIX`, `DEBUG`, `CORS_ALLOWED_ORIGINS`.

### Blast radius

| Question | Finding |
|---|---|
| Was `.env` committed to version control? | **No — the project is not under version control at all.** No `.git`/`.hg`/`.svn` exists. |
| Is there history to purge? | **No.** Not applicable. |
| Is `.env` gitignored for the future? | **Yes** — `fieldtrackpro-backend/.gitignore` matches `.env` (plus `.env.local`, `.env.*.local`). |
| Do any other files contain the secret values? | **No.** Every `.py .ts .tsx .js .json .kt .md .toml .ini .yml .yaml .html .bru .example` file under the project root was scanned for the literal values. The only match was `.env` itself. |
| Did `.env.example` leak real values? | **No** — it contained placeholders. |

**Assessed severity:** the credentials were exposed on the local filesystem only, with
no distribution channel. Rotation was performed regardless, as required.

---

## 2. Remediation performed

### 2.1 Database credential rotation — with privilege reduction

The previous connection string used the **`postgres` superuser**. Rather than simply
changing that password, a dedicated least-privilege application role was created.

Rationale:
* The `postgres` superuser is machine-wide; changing its password could break unrelated
  local projects.
* More importantly, **a superuser bypasses all GRANT/REVOKE rules.** FT-032 requires
  making `geo_verification_logs` insert-only at the database level. That control is
  *impossible* while the application connects as a superuser. This change is therefore a
  prerequisite for FT-032 in Phase 2.

Actions:
1. Created role `fieldtrack_app` with `LOGIN` and a newly generated 32-character random password.
2. Granted only what the application needs:
   * `CONNECT` on `fieldtrackpro_dev`
   * `USAGE` on schema `public`
   * `SELECT, INSERT, UPDATE, DELETE` on all existing tables
   * `USAGE, SELECT` on all sequences
   * matching `ALTER DEFAULT PRIVILEGES` so future tables inherit the same grants
3. Updated `DATABASE_URL` in `.env` to use `fieldtrack_app`.

Verification:
* Application connects successfully — `current_user` = `fieldtrack_app`.
* Reads succeed (2 users).
* Writes succeed (INSERT probe inside a rolled-back transaction).
* PostGIS reachable (`PostGIS_Version()` non-null).
* `rolsuper` = **false** — confirmed not a superuser.
* Full unit suite (88) and the new integration suite both run against the new role.

### 2.2 JWT signing secret rotation

1. Generated a new 64-character cryptographically random secret
   (`RandomNumberGenerator`, base64, URL-safe substitutions).
2. Replaced `JWT_SECRET` in `.env`.

Verification:
* A token signed with the **previous** secret is now **rejected** (`JWTError`) —
  rotation is effective, confirming the old key is dead.
* A token signed with the **new** secret signs and verifies correctly, round-tripping
  its `role` claim.

### 2.3 Session invalidation

All access tokens issued under the old signing key became invalid automatically.
Refresh tokens are opaque (SHA-256 at rest) and unaffected by JWT rotation, so they were
explicitly revoked:

* `UPDATE refresh_tokens SET revoked = true WHERE revoked = false` → **8 rows revoked**.
* Post-state: 8 rows, all `revoked = true`.

No user data was deleted; the rows are retained for audit continuity.

### 2.4 Hygiene

* Temporary files used to stage the generated values were deleted immediately after
  `.env` was written. No plaintext secret remains outside `.env`.
* The pre-rotation `.env` was archived **outside the source tree** at
  `C:\Users\Admin\FieldTrackPro_Backups\.env.PHASE0_PRE_ROTATION.bak` for emergency
  rollback only. It must be destroyed once Phase 1 is accepted.
* `.env.example` was rewritten: placeholders only, guidance on generating strong
  secrets, an explicit warning never to commit `.env`, a recommendation to use a
  non-superuser role, and the previously missing `STORAGE_PROVIDER`,
  `MEDIA_STORAGE_PATH`, MinIO and JWT-lifetime keys (this also closes **FT-056**).
* Confirmed `.env.example` contains no real secret value.

---

## 3. Residual risk

| Risk | Status |
|---|---|
| Old JWT secret still accepted | **Closed** — verified rejected. |
| Old DB credential still used by the app | **Closed** — app now uses `fieldtrack_app`. |
| `postgres` superuser password unchanged | **Accepted (documented).** Out of scope: machine-wide account, not used by the application any more. Should be rotated by the environment owner separately. |
| Secret in VCS history | **Not applicable** — no VCS. |
| Pre-rotation `.env` backup exists | **Open, tracked** — destroy after Phase 1 acceptance. |
| Secret in developer shell history / logs | **Accepted.** Values were never echoed to stdout by the rotation procedure. |

---

## 4. Follow-up owned by later phases

* **FT-032 (Phase 2):** now unblocked — `REVOKE UPDATE, DELETE ON geo_verification_logs
  FROM fieldtrack_app` will be enforceable because the app is no longer a superuser.
* **FT-040 (Phase 3):** move the access token out of `localStorage`; refresh token into
  an httpOnly cookie, per Security Design §1.
* **FT-041 (Phase 3):** add login rate limiting (5 attempts / 15 min).
