# Admin password reset & Super Admin role management

## Roles

| Role | Meaning |
|---|---|
| `EMPLOYEE` | Field staff. Own profile, assigned customers/visits, own requirements. |
| `ADMIN` | Global access to every business screen/API (a strict subset of Super Admin). Cannot change roles. |
| `SUPER_ADMIN` | Everything an Admin can do **plus** role management and protected account operations. |

Roles are stored in `users.role` (PostgreSQL enum `role_enum`). The API authorises against the role **currently in
the database** on every request (`app/core/deps/auth.py`); the `role` claim inside the JWT is informational only, so a
stale or forged claim grants nothing. `require_role(Role.ADMIN)` also admits `SUPER_ADMIN`; `SuperAdminOnly` admits only
`SUPER_ADMIN`. Python code asks `user.is_admin` / `user.is_super_admin` (never `role == Role.ADMIN`).

## Permission matrix (all enforced in the backend)

| Action | Employee | Admin | Super Admin |
|---|---|---|---|
| Reset an **employee's** password | no | yes | yes |
| Reset an **Admin's** password | no | no | yes |
| Reset a Super Admin's (or own) password via the admin endpoint | no | no | no (use *Change Password*; lock-out recovery: see below) |
| Create an `EMPLOYEE` account | no | yes | yes |
| Create an `ADMIN` account (`POST /employees/register`, `POST /users`) | no | **no** | yes |
| Create a `SUPER_ADMIN` account | no | no | **no** (bootstrap script, or promote an Admin) |
| Change any role (`PATCH /users/{id}/role`) | no | **no** (403 + audited) | yes (re-auth + rules below) |
| Edit a Super Admin's profile/contact details | no | **no** | yes |
| Activate/deactivate a Super Admin | no | **no** | yes - never the last active one |
| Read the security audit trail | no | no | yes |
| Excel/MIS import creating `ADMIN` accounts | no | no | yes (import never alters an existing user's role) |

Role transitions go **one step at a time**: `EMPLOYEE <-> ADMIN <-> SUPER_ADMIN`. `EMPLOYEE -> SUPER_ADMIN` and
`SUPER_ADMIN -> EMPLOYEE` are rejected (422 `INVALID_ROLE_TRANSITION`).

## Admin password reset

`POST /api/v1/employees/{employee_id}/reset-password` (Admin or Super Admin; target must have an employee profile).

1. The server generates a random 14-character temporary password (CSPRNG, no look-alike characters, e.g. `Kq7m-Rv4t-Xw9z`).
2. Only its **bcrypt hash** is stored, with `users.temp_password_expires_at = now + TEMP_PASSWORD_EXPIRY_MINUTES`
   (default **30**, range 5-1440) and `employees.must_change_password = true`.
3. Every session of the target dies at once: refresh tokens revoked and `users.token_version` bumped (access tokens
   carry the version they were issued under and are rejected on mismatch). A sign-in lock-out on the account is cleared.
4. The plaintext is returned **once**, in this response only (`Cache-Control: no-store`). It is never stored, never logged
   and there is no endpoint to read it again - a lost password means a new reset.
5. An audit row `ADMIN_PASSWORD_RESET` is written in the same transaction (actor, target, outcome, sessions revoked,
   expiry minutes - never a credential).

Employee side (web **and** Android already implement this):

- Login with the temporary password succeeds but returns `must_change_password: true`.
- That session is **restricted server-side** (independent of the `ENFORCE_PASSWORD_CHANGE` setting): every endpoint answers
  `403 PASSWORD_CHANGE_REQUIRED` except `GET /auth/me`, `POST /auth/logout`, `POST /auth/refresh`,
  `POST /auth/change-password` and `PATCH /users/me/password`.
- Setting a new password (min 8 chars, max 72 bytes, different from the current one) locks the user row, verifies the
  temporary password against the locked current hash, replaces the hash, clears the expiry and the flag, bumps the token
  version and issues a fresh session. The temporary password can never be used again; concurrent attempts are serialised
  so exactly one wins.
- After the expiry the temporary password is rejected at login (`401 AUTH_TEMP_PASSWORD_EXPIRED`, returned only after the
  password itself was correct), at refresh, and on every request of an already-open restricted session.
- An Admin cannot waive the forced change while a temporary password is pending (`409 TEMP_PASSWORD_PENDING`).

Rate limiting: 30 resets / actor / 15 min; wrong current password on the change-password endpoints 10 / account / 15 min
(`429`); sign-in throttling unchanged.

## Role management

`PATCH /api/v1/users/{user_id}/role` with `{"role": "...", "current_password": "<your own>", "confirm": true|false}`.

Checked against locked, current database state in one transaction (a Postgres advisory lock + `FOR UPDATE` on the
actor, the target and every active Super Admin):

- caller must be a Super Admin *right now* (an Admin gets `403 SUPER_ADMIN_REQUIRED` and the attempt is audited);
- the caller's own password is re-verified (rate limited: 5 wrong attempts / 15 min -> `429`) - this is the strongest
  re-authentication the system has; there is **no MFA**, so none is claimed;
- `confirm: true` is mandatory for any change that grants or removes `SUPER_ADMIN` (`422 CONFIRMATION_REQUIRED`);
- a promotion target must be active (`409 ACCOUNT_INACTIVE`);
- the last active Super Admin can never be demoted, deactivated (`409 LAST_SUPER_ADMIN`) or delete their own account
  (`409 LAST_SUPER_ADMIN_CANNOT_DELETE`); concurrent requests cannot both pass the check.

On success the target's `token_version` is bumped and refresh tokens revoked, so the new role (or the loss of privilege)
applies immediately and old sessions cannot keep using it. Changing your **own** role signs you out.

## Audit trail

Table `security_audit_logs` (append-only for the runtime DB role - see `scripts/grant_runtime_role.sql`).
Events: `ADMIN_PASSWORD_RESET`, `ROLE_CHANGE`, `SUPER_ADMIN_BOOTSTRAP`, `ACCOUNT_DEACTIVATED`, `ACCOUNT_ACTIVATED`,
`USER_CREATE_PRIVILEGED`, `EMPLOYEE_UPDATE` (denials). Each row: event, outcome (`SUCCESS`/`DENIED`/`FAILED`), actor,
target, previous/new role, reason code, non-secret details, request id, client IP. Credentials are never recorded
(a deny-list also strips password/token keys). Read via `GET /api/v1/security-audit-logs` (Super Admin) and the
"Security activity" card on the employee profile.

## Database migration

```bash
cd fieldtrackpro-backend
poetry run alembic upgrade head          # applies b9c0d1e2f3a4 (idempotent; safe to re-run)
# then, as the schema OWNER (never the app role), re-apply runtime grants:
psql "$OWNER_DSN" -v owner_role=<owner> -f scripts/grant_runtime_role.sql
```

`b9c0d1e2f3a4_super_admin_role_and_security_audit` adds `SUPER_ADMIN` to `role_enum`, `users.token_version` (default 0),
`users.temp_password_expires_at` (NULL) and `security_audit_logs`. **Nobody is promoted by the migration**; existing
Admins stay Admins and existing sessions keep working. Downgrade (`alembic downgrade -1`) drops the new columns/table
and first demotes any `SUPER_ADMIN` to `ADMIN` (PostgreSQL cannot remove the enum label itself; it is harmless).

## Establishing the first Super Admin (one time, on the server)

There is deliberately **no API for this**. Run on a trusted host with the production environment loaded:

```bash
cd fieldtrackpro-backend
SUPER_ADMIN_BOOTSTRAP_IDENTIFIER='owner@yourcompany.com' \
  poetry run python scripts/bootstrap_super_admin.py \
    --confirm-identifier 'owner@yourcompany.com' \
    --i-understand-production        # required when ENVIRONMENT=production
```

The account must already exist, be active and currently be an `ADMIN` (create one with `scripts/bootstrap_admin.py` if
needed). The script refuses when any Super Admin already exists, promotes exactly the named account in one locked
transaction, ends that account's sessions, writes a `SUPER_ADMIN_BOOTSTRAP` audit row, and never prints or sets a password.

Recovery when **no active** Super Admin remains (all deactivated/locked out):

```bash
SUPER_ADMIN_BOOTSTRAP_IDENTIFIER='...' SUPER_ADMIN_RECOVERY_CONFIRM=RESTORE-SUPER-ADMIN-ACCESS \
  poetry run python scripts/bootstrap_super_admin.py --confirm-identifier '...' --recovery --execute --i-understand-production
```

Recovery is refused while an active Super Admin exists. Anyone with shell + database access can run this script - that is
the trust boundary; protect server access accordingly.

## Known limitations

- No MFA exists; sensitive changes use password re-entry + explicit confirmation only.
- A Super Admin's own forgotten password cannot be reset through the admin endpoint (by design: no account may take over
  a Super Admin). Use the OTP flow (needs SMTP/SMS configured) or the recovery procedure above.
- A reset or role change ends the target's sessions on every device; an old device's later refresh attempt is treated by
  the existing refresh-reuse detection as a replay and revokes that user's other tokens once - the user simply signs in again.
- Admins can still edit each other's contact details (existing behaviour); only Super Admin accounts are protected from Admins.
- Sessions are invalidated by `token_version`; the database is consulted on every request (as before), so no cache can
  serve stale privileges.
